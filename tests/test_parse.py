from app.parse import parse


def test_home():
    t = parse("")
    assert t.kind == "home"
    assert t.tg_url is None


def test_username():
    t = parse("durov")
    assert t.kind == "user"
    assert t.tg_url == "tg://resolve?domain=durov"
    assert t.web_url == "https://t.me/durov"
    assert t.title == "@durov"


def test_username_post():
    t = parse("durov/123")
    assert t.kind == "post"
    assert t.tg_url == "tg://resolve?domain=durov&post=123"
    assert t.web_url == "https://t.me/durov/123"


def test_invite_plus():
    t = parse("+abcDEF")
    assert t.kind == "invite"
    assert t.tg_url == "tg://join?invite=abcDEF"
    assert t.web_url == "https://t.me/+abcDEF"


def test_invite_joinchat():
    t = parse("joinchat/abcDEF")
    assert t.kind == "invite"
    assert t.tg_url == "tg://join?invite=abcDEF"


def test_private_post():
    t = parse("c/123/45")
    assert t.kind == "private_post"
    assert t.tg_url == "tg://privatepost?channel=123&post=45"
    assert t.web_url == "https://t.me/c/123/45"


def test_preview_web_only():
    t = parse("s/channelname")
    assert t.kind == "preview"
    assert t.tg_url is None
    assert t.web_url == "https://t.me/s/channelname"


def test_share_url():
    t = parse("share/url", query="url=https%3A%2F%2Fx.com&text=hi")
    assert t.kind == "share"
    assert t.tg_url == "tg://msg_url?url=https%3A%2F%2Fx.com&text=hi"
    assert t.web_url == "https://t.me/share/url?url=https%3A%2F%2Fx.com&text=hi"


def test_leading_slash_stripped():
    assert parse("/durov").kind == "user"
