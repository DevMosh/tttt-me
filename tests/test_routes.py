"""E2E-тесты FastAPI-роутов через httpx.AsyncClient."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_home_ok():
    # Главная должна отдать HTML с формой
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "tttt.me" in r.text


@pytest.mark.asyncio
async def test_username_page():
    # /durov должна отрендерить страницу с tg://resolve и https://t.me/durov
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/durov")
    assert r.status_code == 200
    assert "tg://resolve?domain=durov" in r.text
    assert "https://t.me/durov" in r.text
    assert "@ProxyCatalog_bot" in r.text  # рекламный блок присутствует


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
