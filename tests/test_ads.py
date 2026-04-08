"""Тесты БД-слоя ad_slot и in-memory кеша."""
import pytest

from app import ads, db


@pytest.fixture(autouse=True)
def _tmp_db(tmp_path, monkeypatch):
    # Подменяем путь к БД на временный файл и чистим кеш перед каждым тестом
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", test_db)
    ads.invalidate()
    yield test_db


@pytest.mark.asyncio
async def test_init_inserts_default():
    await db.init_ad_table()
    row = await db.load_ad_slot()
    assert row["label_kind"] == "ad"
    assert row["title"] == db.DEFAULT_AD["title"]
    assert row["proxy_url"] == ""


@pytest.mark.asyncio
async def test_init_is_idempotent():
    # Повторный init не должен перетирать существующую строку
    await db.init_ad_table()
    await db.save_ad_slot({**db.DEFAULT_AD, "title": "Custom"})
    await db.init_ad_table()
    row = await db.load_ad_slot()
    assert row["title"] == "Custom"


@pytest.mark.asyncio
async def test_save_and_load_roundtrip():
    await db.init_ad_table()
    new = {
        "label_kind": "tip",
        "title": "Быстрый прокси",
        "text": "Подключись одним кликом.",
        "button_text": "Подключить",
        "button_url": "tg://proxy?server=a&port=443&secret=x",
        "proxy_url": "tg://proxy?server=a&port=443&secret=x",
        "fallback_text": "Не работает? Бот выдаст новый.",
    }
    await db.save_ad_slot(new)
    row = await db.load_ad_slot()
    for k, v in new.items():
        assert row[k] == v


@pytest.mark.asyncio
async def test_ads_cache_returns_same_dict_twice():
    await db.init_ad_table()
    a = await ads.get_current()
    b = await ads.get_current()
    # Из кеша должен прийти тот же объект (identity), без повторного SELECT
    assert a is b


@pytest.mark.asyncio
async def test_ads_update_invalidates_cache():
    await db.init_ad_table()
    before = await ads.get_current()
    assert before["title"] == db.DEFAULT_AD["title"]

    new = {**db.DEFAULT_AD, "title": "Changed via admin"}
    await ads.update(new)

    after = await ads.get_current()
    assert after["title"] == "Changed via admin"
