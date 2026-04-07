"""Тесты счётчика кликов /hit + батчинга в памяти."""
import pytest
from httpx import ASGITransport, AsyncClient

from app import cache
from app.main import app


@pytest.mark.asyncio
async def test_hit_increments_buffer():
    # Чистим буфер перед тестом, чтобы не зависеть от предыдущих
    cache._buffer.clear()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r1 = await ac.post("/hit?b=tg")
        r2 = await ac.post("/hit?b=tg")
        r3 = await ac.post("/hit?b=ad")
    assert r1.status_code == 204
    assert r2.status_code == 204
    assert r3.status_code == 204
    assert cache._buffer["tg"] == 2
    assert cache._buffer["ad"] == 1


@pytest.mark.asyncio
async def test_hit_unknown_bucket_ignored():
    cache._buffer.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/hit?b=evil")
    assert r.status_code == 204
    # Неизвестные бакеты не попадают в буфер
    assert "evil" not in cache._buffer


@pytest.mark.asyncio
async def test_pageview_incremented_on_redirect_page():
    cache._buffer.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.get("/durov")
    assert cache._buffer["pageview"] == 1


@pytest.mark.asyncio
async def test_flush_writes_to_db(tmp_path, monkeypatch):
    # Подменяем путь к БД на временный файл
    from app import db
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", test_db)

    await db.init_db(test_db)
    await db.flush_counters({"tg": 5, "ad": 3}, test_db)
    await db.flush_counters({"tg": 2}, test_db)

    counters = await db.read_counters(test_db)
    assert counters == {"tg": 7, "ad": 3}
