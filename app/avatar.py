"""Получение и проксирование аватарок Telegram-каналов/юзеров.

Идём на https://t.me/<username>, парсим og:image регексом, кешируем
URL на 24 часа и байты картинки на 1 час — чтобы при всплесках
не бить в CDN Telegram на каждый хит.
"""
import asyncio
import re

import httpx
from cachetools import TTLCache

# Кеш URL og:image: {username -> url|None}. None = у канала нет аватарки.
_url_cache: TTLCache = TTLCache(maxsize=10_000, ttl=86_400)

# Кеш самих байтов картинки: {username -> (content_type, bytes)}.
# Небольшой, горячие каналы всё равно закешит Caddy/браузер через Cache-Control.
_bytes_cache: TTLCache = TTLCache(maxsize=500, ttl=3_600)

# Ограничиваем одновременные запросы к t.me, чтобы всплеск новых
# username не завалил event loop и не словил rate limit от TG.
_semaphore = asyncio.Semaphore(10)

# Регекс для <meta property="og:image" content="...">. Порядок атрибутов
# может быть любым, используем нежадный поиск content="...".
_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# Таймауты должны быть короткими — мы не хотим блокировать ответ
# пользователю дольше 2-3 секунд, если TG тормозит.
_TIMEOUT = httpx.Timeout(3.0, connect=2.0)


async def fetch_avatar_url(username: str) -> str | None:
    """Возвращает URL аватарки канала/юзера или None, если её нет."""
    if not username or not username.replace("_", "").isalnum():
        # Защита от мусорных username — не ходим на TG за ерундой
        return None

    if username in _url_cache:
        return _url_cache[username]

    url = f"https://t.me/{username}"
    try:
        async with _semaphore:
            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as c:
                r = await c.get(url)
    except Exception:
        # Сеть/таймаут — кешируем None на TTL, чтобы не долбить TG
        _url_cache[username] = None
        return None

    if r.status_code != 200:
        _url_cache[username] = None
        return None

    match = _OG_IMAGE_RE.search(r.text)
    if not match:
        # Страница есть, но og:image отсутствует (например, пустой канал)
        _url_cache[username] = None
        return None

    og_url = match.group(1)
    # Telegram иногда отдаёт заглушку без реального фото — она содержит
    # "emoji" или не является картинкой. Фильтруем самые очевидные кейсы.
    if not og_url.startswith("http"):
        _url_cache[username] = None
        return None

    _url_cache[username] = og_url
    return og_url


async def fetch_avatar_bytes(username: str) -> tuple[str, bytes] | None:
    """Скачивает байты аватарки и кеширует их. Возвращает (content_type, bytes)."""
    if username in _bytes_cache:
        return _bytes_cache[username]

    og_url = await fetch_avatar_url(username)
    if not og_url:
        return None

    try:
        async with _semaphore:
            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as c:
                r = await c.get(og_url)
    except Exception:
        return None

    if r.status_code != 200:
        return None

    content_type = r.headers.get("content-type", "image/jpeg")
    data = r.content
    _bytes_cache[username] = (content_type, data)
    return content_type, data
