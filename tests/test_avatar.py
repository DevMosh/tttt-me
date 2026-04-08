"""Тесты получения и кеширования аватарок Telegram."""
from unittest.mock import AsyncMock, patch

import pytest

from app import avatar


@pytest.fixture(autouse=True)
def _clear_caches():
    # Перед каждым тестом очищаем оба кеша avatar-модуля
    avatar._url_cache.clear()
    avatar._bytes_cache.clear()
    yield


@pytest.mark.asyncio
async def test_fetch_avatar_url_parses_og_image():
    html = (
        '<html><head>'
        '<meta property="og:image" content="https://cdn.tg/avatar.jpg">'
        '</head></html>'
    )
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.text = html

    with patch("app.avatar.httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_response)

        url = await avatar.fetch_avatar_url("durov")

    assert url == "https://cdn.tg/avatar.jpg"
    # Второй вызов должен попасть в кеш — без обращения к httpx
    assert avatar._url_cache["durov"] == "https://cdn.tg/avatar.jpg"


@pytest.mark.asyncio
async def test_fetch_avatar_url_no_og_image():
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.text = "<html><head></head></html>"

    with patch("app.avatar.httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_response)

        url = await avatar.fetch_avatar_url("empty")

    assert url is None
    # None тоже кешируется — чтобы не долбить TG повторно
    assert avatar._url_cache["empty"] is None


@pytest.mark.asyncio
async def test_fetch_avatar_url_404():
    mock_response = AsyncMock()
    mock_response.status_code = 404
    mock_response.text = ""

    with patch("app.avatar.httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_response)

        url = await avatar.fetch_avatar_url("nonexistent")

    assert url is None


@pytest.mark.asyncio
async def test_fetch_avatar_url_rejects_garbage_username():
    # Не ходим в сеть, если username явно мусорный
    url = await avatar.fetch_avatar_url("not valid!!")
    assert url is None


@pytest.mark.asyncio
async def test_fetch_avatar_bytes_returns_content():
    avatar._url_cache["durov"] = "https://cdn.tg/avatar.jpg"

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.content = b"\xff\xd8\xff binary jpeg bytes"
    mock_response.headers = {"content-type": "image/jpeg"}

    with patch("app.avatar.httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_response)

        result = await avatar.fetch_avatar_bytes("durov")

    assert result is not None
    content_type, data = result
    assert content_type == "image/jpeg"
    assert data.startswith(b"\xff\xd8\xff")
