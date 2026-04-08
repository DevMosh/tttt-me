"""Работа с SQLite для агрегированных счётчиков кликов.

Запись в БД не на каждый запрос, а раз в N секунд из памяти —
для 30k/день это даёт максимум ~3 write-транзакции в минуту.
"""
from pathlib import Path

import aiosqlite

# Путь к файлу БД. В проде переопределяется через env DATABASE_PATH
# в systemd-юните (/var/lib/tttt/stats.db).
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "stats.db"


async def init_db(db_path: Path | None = None) -> None:
    """Создаёт таблицу counters, если её ещё нет."""
    db_path = db_path or DEFAULT_DB_PATH
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


async def flush_counters(delta: dict[str, int], db_path: Path | None = None) -> None:
    """Прибавляет значения из delta к БД и обнуляет их после записи.

    delta — словарь {имя_счётчика: прирост}. Ключи upsert-ятся.
    """
    if not delta:
        return
    db_path = db_path or DEFAULT_DB_PATH

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


async def read_counters(db_path: Path | None = None) -> dict[str, int]:
    """Читает текущие значения всех счётчиков (для /stats или отладки)."""
    db_path = db_path or DEFAULT_DB_PATH
    async with aiosqlite.connect(db_path) as db:

        async with db.execute("SELECT name, value FROM counters") as cur:
            rows = await cur.fetchall()
    return {name: value for name, value in rows}


# ---------- ad_slot: редактируемый контент рекламного/советского блока ----------

# Дефолтный контент, который подставляется при первом старте и если что-то
# обнулили через админку. label_kind: "ad" | "tip".
DEFAULT_AD: dict = {
    "label_kind": "ad",
    "title": "@ProxyCatalog_bot",
    "text": "Telegram постоянно зависает и обновляется? Настрой стабильный прокси в один клик.",
    "button_text": "Включить прокси",
    "button_url": "https://t.me/ProxyCatalog_bot?start=ttttme",
    "proxy_url": "",  # пустая строка = прямой прокси не показываем
    "fallback_text": "Если прокси не заработал — свежий в боте",
}


async def init_ad_table(db_path: Path | None = None) -> None:
    """Создаёт таблицу ad_slot и заполняет дефолтом, если пусто."""
    db_path = db_path or DEFAULT_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS ad_slot (
                id            TEXT PRIMARY KEY,
                label_kind    TEXT NOT NULL,
                title         TEXT NOT NULL,
                text          TEXT NOT NULL,
                button_text   TEXT NOT NULL,
                button_url    TEXT NOT NULL,
                proxy_url     TEXT NOT NULL DEFAULT '',
                fallback_text TEXT NOT NULL DEFAULT '',
                updated_at    INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # Вставляем дефолт, если строки ещё нет. INSERT OR IGNORE удобнее,
        # чем SELECT COUNT — одна транзакция, без гонок.
        await db.execute(
            """
            INSERT OR IGNORE INTO ad_slot
                (id, label_kind, title, text, button_text, button_url,
                 proxy_url, fallback_text, updated_at)
            VALUES ('current', ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                DEFAULT_AD["label_kind"],
                DEFAULT_AD["title"],
                DEFAULT_AD["text"],
                DEFAULT_AD["button_text"],
                DEFAULT_AD["button_url"],
                DEFAULT_AD["proxy_url"],
                DEFAULT_AD["fallback_text"],
            ),
        )
        await db.commit()


async def load_ad_slot(db_path: Path | None = None) -> dict:
    """Читает текущий ad-контент. Возвращает dict с дефолтами,
    если строки или даже самой таблицы ещё нет (удобно для тестов)."""
    db_path = db_path or DEFAULT_DB_PATH
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT label_kind, title, text, button_text, button_url, "
                "proxy_url, fallback_text FROM ad_slot WHERE id='current'"
            ) as cur:
                row = await cur.fetchone()
    except aiosqlite.OperationalError:
        # Таблицы ещё нет (например, lifespan не запускался в тестах)
        return dict(DEFAULT_AD)
    if row is None:
        return dict(DEFAULT_AD)
    return {k: row[k] for k in row.keys()}



async def save_ad_slot(data: dict, db_path: Path | None = None) -> None:
    """Сохраняет ad-контент. Ожидает те же ключи, что в DEFAULT_AD."""
    import time
    db_path = db_path or DEFAULT_DB_PATH
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO ad_slot
                (id, label_kind, title, text, button_text, button_url,
                 proxy_url, fallback_text, updated_at)
            VALUES ('current', ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                label_kind    = excluded.label_kind,
                title         = excluded.title,
                text          = excluded.text,
                button_text   = excluded.button_text,
                button_url    = excluded.button_url,
                proxy_url     = excluded.proxy_url,
                fallback_text = excluded.fallback_text,
                updated_at    = excluded.updated_at
            """,
            (
                data["label_kind"],
                data["title"],
                data["text"],
                data["button_text"],
                data["button_url"],
                data.get("proxy_url", ""),
                data.get("fallback_text", ""),
                int(time.time()),
            ),
        )
        await db.commit()
