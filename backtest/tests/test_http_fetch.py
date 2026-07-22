"""Guard tests for backtest/lib/http_fetch.py (L241 graduation).

Pure-mock tests only (no live network) -- urllib.request.urlopen is patched so
these are deterministic and free.
"""
import urllib.error
import urllib.request
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from backtest.lib.http_fetch import (
    DEFAULT_USER_AGENT,
    HttpFetchBlocked,
    fetch_url_text,
)


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestFetchUrlTextSuccess:
    @patch("backtest.lib.http_fetch.urllib.request.urlopen")
    def test_200_returns_decoded_text(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse(b"hello world")
        result = fetch_url_text("https://example.com/data.txt")
        assert result == "hello world"

    @patch("backtest.lib.http_fetch.urllib.request.urlopen")
    def test_sets_browser_like_user_agent_by_default(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse(b"ok")
        fetch_url_text("https://example.com/data.txt")
        sent_request = mock_urlopen.call_args[0][0]
        assert isinstance(sent_request, urllib.request.Request)
        assert sent_request.get_header("User-agent") == DEFAULT_USER_AGENT
        assert "python-urllib" not in sent_request.get_header("User-agent").lower()

    @patch("backtest.lib.http_fetch.urllib.request.urlopen")
    def test_custom_user_agent_honored(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse(b"ok")
        fetch_url_text("https://example.com/data.txt", user_agent="CustomBot/1.0")
        sent_request = mock_urlopen.call_args[0][0]
        assert sent_request.get_header("User-agent") == "CustomBot/1.0"


class TestFetchUrlTextBlocked:
    @patch("backtest.lib.http_fetch.urllib.request.urlopen")
    def test_403_raises_http_fetch_blocked(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://cdn.example.com/x", 403, "Forbidden", None, None
        )
        with pytest.raises(HttpFetchBlocked) as exc_info:
            fetch_url_text("https://cdn.example.com/x")
        assert exc_info.value.status == 403
        assert "block" in str(exc_info.value).lower()

    @patch("backtest.lib.http_fetch.urllib.request.urlopen")
    def test_429_raises_http_fetch_blocked(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://cdn.example.com/x", 429, "Too Many Requests", None, None
        )
        with pytest.raises(HttpFetchBlocked) as exc_info:
            fetch_url_text("https://cdn.example.com/x")
        assert exc_info.value.status == 429


class TestFetchUrlTextGenuinelyMissing:
    @patch("backtest.lib.http_fetch.urllib.request.urlopen")
    def test_404_fails_open_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://cdn.example.com/holiday.txt", 404, "Not Found", None, None
        )
        result = fetch_url_text("https://cdn.example.com/holiday.txt")
        assert result is None

    @patch("backtest.lib.http_fetch.urllib.request.urlopen")
    def test_other_5xx_fails_open_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://cdn.example.com/x", 503, "Service Unavailable", None, None
        )
        result = fetch_url_text("https://cdn.example.com/x")
        assert result is None

    @patch("backtest.lib.http_fetch.urllib.request.urlopen")
    def test_timeout_fails_open_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = TimeoutError("timed out")
        result = fetch_url_text("https://cdn.example.com/x")
        assert result is None

    @patch("backtest.lib.http_fetch.urllib.request.urlopen")
    def test_connection_error_fails_open_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = ConnectionResetError("reset")
        result = fetch_url_text("https://cdn.example.com/x")
        assert result is None
