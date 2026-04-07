"""FastAPI-приложение tttt.me: главная страница и catch-all редирект."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import cache
from app.parse import parse


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
    title="tttt.me",
    docs_url=None,        # публичный сервис — Swagger не нужен
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


# Раздача статики (в проде её перехватит Caddy, но локально нужна)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    """Домашняя страница с инпутом для вставки t.me-ссылки."""
    return templates.TemplateResponse(request, "home.html")


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



@app.get("/{full_path:path}", response_class=HTMLResponse)
async def redirect_page(full_path: str, request: Request) -> HTMLResponse:
    """
    Catch-all: парсим путь + query, отдаём страницу с кнопками
    «Открыть в Telegram» / «Открыть в браузере» и рекламным блоком.
    """
    query = request.url.query  # сырая query-строка без ведущего '?'
    target = parse(full_path, query=query)

    # Считаем просмотры страниц-редиректов (без сохранения самого пути)
    cache.incr("pageview")

    return templates.TemplateResponse(
        request,
        "page.html",
        {
            "target": target,
            # Ссылка, на которую уйдёт авто-редирект через 10 с.
            # Если tg:// отсутствует (например, /s/...), используем web.
            "auto_url": target.tg_url or target.web_url,
        },
    )

