"""FastAPI-приложение: главная страница и catch-all редирект."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import cache, avatar, admin, ads
from app.config import DOMAIN
from app.parse import parse
from app.admin import router as admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Старт: инициализируем БД и поднимаем фоновый flush-loop
    await cache.startup()
    yield
    # Остановка: финальный flush через _flush_once (loop уже отменён)
    await cache._flush_once()


# Корень пакета app/ — отсюда берём templates/ и static/
BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title=DOMAIN,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


# Раздача статики (в проде её перехватит Caddy, но локально нужна)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Подключаем admin-роуты ДО catch-all, иначе /admin съест catch-all
app.include_router(admin_router)


templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    """Домашняя страница с инпутом для вставки t.me-ссылки."""
    ad = await ads.get_current()
    return templates.TemplateResponse(request, "home.html", {"ad": ad, "domain": DOMAIN})



@app.get("/favicon.ico")
async def favicon() -> HTMLResponse:
    # Пустая заглушка, чтобы браузеры не ловили 404.
    # Настоящий фавикон отдаётся через /static/favicon.svg.
    return HTMLResponse(status_code=204)


@app.post("/hit")
async def hit(b: str = Query(..., description="Какую кнопку кликнули: tg|web|ad")) -> Response:
    """Счётчик клика по кнопке. Фронт шлёт sendBeacon/POST при клике."""
    cache.incr(b)
    # 204 — минимум байт, браузеру ничего не рендерить
    return Response(status_code=204)


@app.get("/avatar/{username}")
async def avatar_proxy(username: str) -> Response:
    """Проксирует байты аватарки канала/юзера из Telegram.

    Кешируется и на нашем сервере (памятью), и браузером/Caddy (через
    Cache-Control). Если аватарки нет — отдаём 404, фронт фолбечится
    на букву через onerror.
    """
    result = await avatar.fetch_avatar_bytes(username)
    if result is None:
        return Response(status_code=404)
    content_type, data = result
    return Response(
        content=data,
        media_type=content_type,
        headers={
            # Сутки кеша у клиентов и на CDN-слое перед нами
            "Cache-Control": "public, max-age=86400, immutable",
        },
    )

# Подключаем admin-роутер ДО catch-all, иначе /admin перехватится
# как Telegram-username и админка станет недоступна.


@app.get("/{full_path:path}", response_class=HTMLResponse)
async def redirect_page(full_path: str, request: Request) -> HTMLResponse:
    """
    Catch-all: парсим путь + query, отдаём страницу с кнопками
    «Открыть в Telegram» / «Открыть в браузере» и рекламным блоком.
    """
    query = request.url.query  # сырая query-строка без ведущего '?'
    target = parse(full_path, query=query)

    # Аватарка есть только для публичных каналов/юзеров и постов в них
    avatar_username: str | None = None
    if target.kind in ("user", "post"):
        # Для user/post первый сегмент пути — это username канала
        avatar_username = full_path.lstrip("/").split("/")[0]
        # Прогреваем кеш URL в фоне — картинку запросит сам браузер через /avatar/...
        # Здесь await не нужен, но сделаем его, чтобы 404 сразу проявился и фронт
        # не мигал картинкой-404: если og:image нет — не показываем <img> вообще.
        og_url = await avatar.fetch_avatar_url(avatar_username)
        if og_url is None:
            avatar_username = None


    # Считаем просмотры страниц-редиректов (без сохранения самого пути)
    cache.incr("pageview")

    ad = await ads.get_current()
    return templates.TemplateResponse(
        request,
        "page.html",
        {
            "target": target,
            "auto_url": target.tg_url or target.web_url,
            "avatar_username": avatar_username,
            "ad": ad,
            "domain": DOMAIN
        },
    )



