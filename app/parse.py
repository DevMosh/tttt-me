"""Parse incoming tttt.me path into Telegram deep-link + web fallback."""
from dataclasses import dataclass
from urllib.parse import quote, urlencode


@dataclass(frozen=True)
class Target:
    tg_url: str | None   # tg://... (None if only web makes sense, e.g. /s/...)
    web_url: str         # https://t.me/...
    title: str           # human-readable heading
    kind: str            # 'user', 'post', 'invite', 'private_post', 'preview', 'share', 'home'


def parse(path: str, query: str = "") -> Target:
    """
    path: URL path without leading slash, e.g. 'durov/123' or '+abcDEF'.
    query: raw query string without leading '?', e.g. 'url=https%3A%2F%2Fx'.
    """
    path = path.lstrip("/")
    if not path:
        return Target(None, "https://t.me/", "tttt.me", "home")

    segments = path.split("/")
    first = segments[0]

    # /+invite  or  /joinchat/invite
    if first.startswith("+"):
        invite = first[1:]
        return Target(
            tg_url=f"tg://join?invite={quote(invite, safe='')}",
            web_url=f"https://t.me/+{quote(invite, safe='')}",
            title="Telegram invite",
            kind="invite",
        )
    if first == "joinchat" and len(segments) >= 2:
        invite = segments[1]
        return Target(
            tg_url=f"tg://join?invite={quote(invite, safe='')}",
            web_url=f"https://t.me/joinchat/{quote(invite, safe='')}",
            title="Telegram invite",
            kind="invite",
        )

    # /c/<channel>/<post>  — private channel post
    if first == "c" and len(segments) >= 3:
        channel, post = segments[1], segments[2]
        return Target(
            tg_url=f"tg://privatepost?channel={channel}&post={post}",
            web_url=f"https://t.me/c/{channel}/{post}",
            title="Telegram post",
            kind="private_post",
        )

    # /s/<channel>  — preview (web only)
    if first == "s" and len(segments) >= 2:
        channel = segments[1]
        return Target(
            tg_url=None,
            web_url=f"https://t.me/s/{quote(channel, safe='')}",
            title=f"@{channel}",
            kind="preview",
        )

    # /share/url?url=...
    if first == "share" and len(segments) >= 2 and segments[1] == "url":
        # passthrough query as-is to tg://msg_url
        tg = f"tg://msg_url?{query}" if query else "tg://msg_url"
        web = f"https://t.me/share/url?{query}" if query else "https://t.me/share/url"
        return Target(tg_url=tg, web_url=web, title="Share via Telegram", kind="share")

    # /username or /username/<post>
    username = first
    if len(segments) >= 2 and segments[1].isdigit():
        post = segments[1]
        return Target(
            tg_url=f"tg://resolve?domain={quote(username, safe='')}&post={post}",
            web_url=f"https://t.me/{quote(username, safe='')}/{post}",
            title=f"@{username}",
            kind="post",
        )

    return Target(
        tg_url=f"tg://resolve?domain={quote(username, safe='')}",
        web_url=f"https://t.me/{quote(username, safe='')}",
        title=f"@{username}",
        kind="user",
    )
