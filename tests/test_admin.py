"""Тесты админки: auth, форма, сохранение."""
import base64

import pytest
from httpx import ASGITransport, AsyncClient

from app import ads, db
from app.main import app


@pytest.fixture(autouse=True)
def _setup(tmp_path, monkeypatch):
    # Изолируем БД и задаём тестовые креды
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", test_db)
    monkeypatch.setenv("ADMIN_USER", "tester")
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    ads.invalidate()
    yield


def _auth_header(user: str = "tester", pw: str = "s3cret") -> dict:
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.mark.asyncio
async def test_admin_requires_auth():
    await db.init_ad_table()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/admin")
    assert r.status_code == 401
    assert "www-authenticate" in {k.lower() for k in r.headers.keys()}


@pytest.mark.asyncio
async def test_admin_wrong_password():
    await db.init_ad_table()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/admin", headers=_auth_header(pw="wrong"))
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_admin_form_prefilled():
    await db.init_ad_table()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/admin", headers=_auth_header())
    assert r.status_code == 200
    # Поля формы с дефолтами
    assert 'name="title"' in r.text
    assert "@ProxyCatalog_bot" in r.text
    assert 'value="ad"' in r.text  # селектор Реклама/Совет


@pytest.mark.asyncio
async def test_admin_save_updates_db():
    await db.init_ad_table()
    transport = ASGITransport(app=app)
    # follow_redirects=False — иначе httpx пойдёт за 303 на GET /admin
    async with AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=False
    ) as ac:
        r = await ac.post(
            "/admin",
            headers=_auth_header(),
            data={
                "label_kind": "tip",
                "title": "Быстрый прокси",
                "text": "Подключись одним кликом.",
                "button_text": "Подключить",
                "button_url": "tg://proxy?server=a&port=443&secret=x",
                "proxy_url": "tg://proxy?server=a&port=443&secret=x",
                "fallback_text": "Не работает? Возьми свежий в боте.",
            },
        )
    assert r.status_code == 303
    assert r.headers["location"] == "/admin?saved=1"

    # Проверяем, что данные реально легли в БД
    row = await db.load_ad_slot()
    assert row["label_kind"] == "tip"
    assert row["title"] == "Быстрый прокси"
    assert row["proxy_url"].startswith("tg://proxy")


@pytest.mark.asyncio
async def test_admin_save_validates_label_kind():
    await db.init_ad_table()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=False
    ) as ac:
        r = await ac.post(
            "/admin",
            headers=_auth_header(),
            data={
                "label_kind": "evil",  # недопустимое значение
                "title": "x",
                "text": "x",
                "button_text": "x",
                "button_url": "x",
            },
        )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_admin_save_requires_auth():
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=False
    ) as ac:
        r = await ac.post("/admin", data={"label_kind": "ad"})
    assert r.status_code == 401
