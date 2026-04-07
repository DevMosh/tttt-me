"""Работа с SQLite для агрегированных счётчиков кликов.

Запись в БД не на каждый запрос, а раз в N секунд из памяти —
для 30k/день это даёт максимум ~3 write-транзакции в минуту.
"""
from pathlib import Path

import aiosqlite

# Путь к файлу БД. В проде переопределяется через env DATABASE_PATH
# в systemd-юните (/var/lib/tttt/stats.db).
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "stats.db"


async def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Создаёт таблицу counters, если её ещё нет."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS counters (
                name  TEXT PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        await db.commit()


async def flush_counters(delta: dict[str, int], db_path: Path = DEFAULT_DB_PATH) -> None:
    """Прибавляет значения из delta к БД и обнуляет их после записи.

    delta — словарь {имя_счётчика: прирост}. Ключи upsert-ятся.
    """
    if not delta:
        return
    async with aiosqlite.connect(db_path) as db:
        for name, value in delta.items():
            if value == 0:
                continue
            # UPSERT: создаём строку или прибавляем к существующей
            await db.execute(
                """
                INSERT INTO counters(name, value) VALUES(?, ?)
                ON CONFLICT(name) DO UPDATE SET value = value + excluded.value
                """,
                (name, value),
            )
        await db.commit()


async def read_counters(db_path: Path = DEFAULT_DB_PATH) -> dict[str, int]:
    """Читает текущие значения всех счётчиков (для /stats или отладки)."""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT name, value FROM counters") as cur:
            rows = await cur.fetchall()
    return {name: value for name, value in rows}
