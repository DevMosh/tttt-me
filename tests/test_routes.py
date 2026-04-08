"""E2E-тесты FastAPI-роутов через httpx.AsyncClient."""
import pytest
from httpx import ASGITransport, AsyncClient

from app import ads, avatar, db
from app.config import DOMAIN
from app.main import app


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    # Изолируем БД и очищаем кеш ads перед каждым тестом
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", test_db)
    ads.invalidate()
    yield



@pytest.mark.asyncio
async def test_home_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert DOMAIN in r.text  # Проверяем наличие нового домена


@pytest.mark.asyncio
async def test_username_page(monkeypatch):
    # Мокаем поход в t.me, чтобы тест был офлайновым и быстрым
    from app import avatar

    async def fake_fetch(username):
        return "https://cdn.tg/fake.jpg"
    monkeypatch.setattr(avatar, "fetch_avatar_url", fake_fetch)
    avatar._url_cache.clear()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/durov")
    assert r.status_code == 200
    assert "tg://resolve?domain=durov" in r.text
    assert "https://t.me/durov" in r.text
    assert "@ProxyCatalog_bot" in r.text            # рекламный блок
    assert "/avatar/durov" in r.text                # тег <img> со ссылкой на прокси


@pytest.mark.asyncio
async def test_username_page_no_avatar(monkeypatch):
    # Когда og:image нет — рендерим букву, без /avatar/... в HTML
    from app import avatar

    async def fake_fetch(username):
        return None
    monkeypatch.setattr(avatar, "fetch_avatar_url", fake_fetch)
    avatar._url_cache.clear()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/durov")
    assert r.status_code == 200
    assert "/avatar/durov" not in r.text




@pytest.mark.asyncio
async def test_invite_page():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/+abcDEF")
    assert r.status_code == 200
    assert "tg://join?invite=abcDEF" in r.text


@pytest.mark.asyncio
async def test_preview_no_tg_link():
    # Для /s/... tg://-кнопки быть не должно
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/s/durov")
    assert r.status_code == 200
    assert "tg://" not in r.text
    assert "https://t.me/s/durov" in r.text



@pytest.mark.asyncio
async def test_page_renders_tip_variant_with_proxy(monkeypatch):
    """При label_kind='tip' и proxy_url — зелёная плашка и две кнопки."""
    await db.init_ad_table()
    await ads.update({
        "label_kind": "tip",
        "title": "Быстрый прокси",
        "text": "Подключение одним кликом.",
        "button_text": "Подключить",
        "button_url": "https://t.me/ProxyCatalog_bot?start=ttttme",
        "proxy_url": "tg://proxy?server=a.example&port=443&secret=xyz",
        "fallback_text": "Прокси не работает? Свежий в боте.",
    })

    async def fake_avatar(username):
        return None
    monkeypatch.setattr(avatar, "fetch_avatar_url", fake_avatar)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/durov")

    assert r.status_code == 200
    assert "ad tip" in r.text                              # зелёный вариант
    assert "Совет" in r.text                               # метка
    assert "Быстрый прокси" in r.text                      # заголовок
    assert "tg://proxy?server=a.example" in r.text         # primary-кнопка
    assert "Прокси не работает? Свежий в боте." in r.text  # fallback-подпись
    assert "https://t.me/ProxyCatalog_bot?start=ttttme" in r.text  # fallback-URL


@pytest.mark.asyncio
async def test_page_renders_ad_default_without_proxy(monkeypatch):
    """Дефолтный случай: метка 'Реклама', одна кнопка."""
    await db.init_ad_table()
    # Дефолты уже в БД после init — ничего не меняем

    async def fake_avatar(username):
        return None
    monkeypatch.setattr(avatar, "fetch_avatar_url", fake_avatar)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/durov")

    assert r.status_code == 200
    assert "Реклама" in r.text
    # tip-класс не должен быть на блоке
    assert "ad tip" not in r.text
    assert "@ProxyCatalog_bot" in r.text
