"""In-memory кеш редактируемого контента рекламно-советского блока.

Читает из SQLite (таблица ad_slot) с коротким TTL, чтобы админка
пропагейтилась на все воркеры uvicorn максимум за TTL секунд.
Текст инструкции сохраняется в отдельный текстовый файл.
"""
from pathlib import Path
from cachetools import TTLCache

from app import db

# Путь к файлу, где будет лежать наша HTML-инструкция (app/instruction.html)
INSTRUCTION_FILE = Path(__file__).resolve().parent / "instruction.html"

# Короткий TTL: 10 секунд
_cache: TTLCache = TTLCache(maxsize=1, ttl=10)


async def get_current() -> dict:
    """Возвращает актуальный ad-контент (с кешем)."""
    if "cur" in _cache:
        return _cache["cur"]
    try:
        data = await db.load_ad_slot()
    except Exception:
        data = dict(db.DEFAULT_AD)

    # === ЧИТАЕМ ИНСТРУКЦИЮ ИЗ ФАЙЛА ===
    instruction_html = ""
    if INSTRUCTION_FILE.exists():
        instruction_html = INSTRUCTION_FILE.read_text(encoding="utf-8")

    # Добавляем её к данным, которые отдаются в шаблоны
    data["instruction_html"] = instruction_html
    # ==================================

    _cache["cur"] = data
    return data


async def update(data: dict) -> None:
    """Сохраняет новый ad-контент и инвалидирует локальный кеш."""

    # === СОХРАНЯЕМ ИНСТРУКЦИЮ В ФАЙЛ ===
    # Вырезаем instruction_html из словаря data, чтобы не отправлять в базу
    instruction_html = data.pop("instruction_html", "")
    INSTRUCTION_FILE.write_text(instruction_html, encoding="utf-8")
    # ===================================

    # Остальные поля стандартно уходят в БД
    await db.save_ad_slot(data)
    _cache.clear()


def invalidate() -> None:
    """Принудительно очистить кеш (нужно в тестах)."""
    _cache.clear()