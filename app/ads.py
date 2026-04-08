"""In-memory кеш редактируемого контента рекламно-советского блока.

Читает из SQLite (таблица ad_slot) с коротким TTL, чтобы админка
пропагейтилась на все воркеры uvicorn максимум за TTL секунд.
"""
from cachetools import TTLCache

from app import db

# Короткий TTL: 10 секунд достаточно, чтобы после нажатия "Сохранить"
# изменения появились у всех пользователей почти мгновенно.
_cache: TTLCache = TTLCache(maxsize=1, ttl=10)


async def get_current() -> dict:
    """Возвращает актуальный ad-контент (с кешем).

    Если таблица ad_slot ещё не создана (например, в тестах без init) —
    возвращаем дефолтный контент, не падая с OperationalError.
    """
    if "cur" in _cache:
        return _cache["cur"]
    try:
        data = await db.load_ad_slot()
    except Exception:
        data = dict(db.DEFAULT_AD)
    _cache["cur"] = data
    return data



async def update(data: dict) -> None:
    """Сохраняет новый ad-контент и инвалидирует локальный кеш."""
    await db.save_ad_slot(data)
    # Очищаем — следующий get_current подтянет свежую строку.
    # Другие воркеры догонят через TTL.
    _cache.clear()


def invalidate() -> None:
    """Принудительно очистить кеш (нужно в тестах)."""
    _cache.clear()
