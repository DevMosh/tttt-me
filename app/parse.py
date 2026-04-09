"""Parse incoming tttt.me path into Telegram deep-link + web fallback."""
from dataclasses import dataclass
from urllib.parse import quote

# Подтягиваем домен из конфига, если вы его создавали, либо оставляем хардкод
try:
    from app.config import DOMAIN
except ImportError:
    DOMAIN = "tg-open.org"


@dataclass(frozen=True)
class Target:
    tg_url: str | None   # tg://... (None if only web makes sense)
    web_url: str         # https://t.me/...
    title: str           # human-readable heading
    kind: str            # 'user', 'post', 'invite', 'private_post', 'preview', 'share', 'home', 'stickers', 'settings'


def parse(path: str, query: str = "") -> Target:
    """
    path: URL path without leading slash, e.g. 'durov/123' or '+abcDEF'.
    query: raw query string without leading '?', e.g. 'start=prx_16'.
    """
    path = path.lstrip("/")
    if not path:
        return Target(None, "https://t.me/", DOMAIN, "home")

    # Вспомогательная функция для безопасного добавления query-параметров к ссылкам
    def add_q(url: str | None) -> str | None:
        if not url or not query:
            return url
        # Если в ссылке уже есть знак '?', добавляем через '&', иначе через '?'
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}{query}"

    segments = path.split("/")
    first = segments[0]

    # 1. Инвайты (/+invite или /joinchat/invite)
    if first.startswith("+"):
        invite = first[1:]
        return Target(
            tg_url=add_q(f"tg://join?invite={quote(invite, safe='')}"),
            web_url=add_q(f"https://t.me/+{quote(invite, safe='')}"),
            title="Telegram invite",
            kind="invite",
        )
    if first == "joinchat" and len(segments) >= 2:
        invite = segments[1]
        return Target(
            tg_url=add_q(f"tg://join?invite={quote(invite, safe='')}"),
            web_url=add_q(f"https://t.me/joinchat/{quote(invite, safe='')}"),
            title="Telegram invite",
            kind="invite",
        )

    # 2. Приватные каналы и посты (/c/channel/post)
    if first == "c" and len(segments) >= 3:
        channel, post = segments[1], segments[2]
        return Target(
            tg_url=add_q(f"tg://privatepost?channel={channel}&post={post}"),
            web_url=add_q(f"https://t.me/c/{channel}/{post}"),
            title="Telegram post",
            kind="private_post",
        )

    # 3. Превью каналов web-only (/s/channel)
    if first == "s" and len(segments) >= 2:
        channel = segments[1]
        return Target(
            tg_url=None,
            web_url=add_q(f"https://t.me/s/{quote(channel, safe='')}"),
            title=f"@{channel}",
            kind="preview",
        )

    # 4. Шеринг текста или ссылки (/share/url)
    if first == "share" and len(segments) >= 2 and segments[1] == "url":
        return Target(
            tg_url=add_q("tg://msg_url"),
            web_url=add_q("https://t.me/share/url"),
            title="Share via Telegram",
            kind="share"
        )

    # 5. СТИКЕРЫ (addstickers/Name)
    if first == "addstickers" and len(segments) >= 2:
        set_name = segments[1]
        return Target(
            tg_url=add_q(f"tg://addstickers?set={quote(set_name, safe='')}"),
            web_url=add_q(f"https://t.me/addstickers/{quote(set_name, safe='')}"),
            title="Telegram Stickers",
            kind="stickers"
        )

    # 6. СИСТЕМНЫЕ ССЫЛКИ (прокси, язык, темы)
    if first in ("proxy", "socks", "setlanguage", "bg"):
        return Target(
            tg_url=add_q(f"tg://{first}"),
            web_url=add_q(f"https://t.me/{first}"),
            title="Telegram Settings",
            kind="settings"
        )

    # 7. Пользователи, каналы, боты и публичные посты (/username или /username/123)
    username = first
    if len(segments) >= 2 and segments[1].isdigit():
        post = segments[1]
        return Target(
            tg_url=add_q(f"tg://resolve?domain={quote(username, safe='')}&post={post}"),
            web_url=add_q(f"https://t.me/{quote(username, safe='')}/{post}"),
            title=f"@{username}",
            kind="post",
        )

    # Базовый fallback (для юзернеймов и ботов)
    return Target(
        tg_url=add_q(f"tg://resolve?domain={quote(username, safe='')}"),
        web_url=add_q(f"https://t.me/{quote(username, safe='')}"),
        title=f"@{username}",
        kind="user",
    )