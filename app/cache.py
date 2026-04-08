"""In-memory буфер счётчиков + фоновый flush в SQLite.

Инкремент — O(1) в памяти, без обращения к диску. Раз в FLUSH_INTERVAL
секунд отдельная asyncio-задача сбрасывает накопленное в БД.
"""
import asyncio
from collections import defaultdict

from app.db import flush_counters, init_db

# Как часто сбрасывать накопленные счётчики в SQLite (секунды).
FLUSH_INTERVAL = 30

# Разрешённые имена кнопок, которые можно инкрементить через /hit.
# Фильтруем, чтобы любой клиент не мог засорить БД произвольными ключами.
ALLOWED_BUCKETS = {"tg", "web", "ad", "pageview"}

# Сам буфер: {имя_счётчика: накопленный_прирост}.
# defaultdict(int) — удобно для += без проверок наличия ключа.
_buffer: dict[str, int] = defaultdict(int)
_lock = asyncio.Lock()


def incr(bucket: str) -> None:
    """Синхронный инкремент — вызывается из обработчиков роутов.

    Блокировка не нужна: GIL обеспечивает атомарность += для int
    внутри одного процесса. При multi-worker uvicorn каждый воркер
    держит свой буфер, и все они независимо flush'ат в SQLite.
    """
    if bucket not in ALLOWED_BUCKETS:
        return
    _buffer[bucket] += 1


async def _flush_once() -> None:
    """Один проход flush: копируем буфер, чистим, пишем в БД."""
    async with _lock:
        if not _buffer:
            return
        delta = dict(_buffer)
        _buffer.clear()
    await flush_counters(delta)


async def flush_loop() -> None:
    """Фоновая задача: вечный цикл flush каждые FLUSH_INTERVAL секунд."""
    while True:
        try:
            await asyncio.sleep(FLUSH_INTERVAL)
            await _flush_once()
        except asyncio.CancelledError:
            # При остановке приложения — финальный flush и выход.
            await _flush_once()
            raise
        except Exception:
            # Не даём фоновой задаче умереть из-за случайной ошибки БД.
            # В проде здесь будет лог через journald.
            pass


async def startup() -> None:
    """Инициализация при старте приложения: создать таблицы, запустить loop."""
    from app.db import init_ad_table
    await init_db()
    await init_ad_table()
    asyncio.create_task(flush_loop())

