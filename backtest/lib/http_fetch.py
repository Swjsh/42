"""Shared HTTP text-fetch helper for raw-CDN-scrape data-source studies.

Several free public data vendors (confirmed: FINRA's Reg SHO CDN, see
markdown/doctrine/LESSONS-LEARNED.md L241) return HTTP 403 for Python's default
urllib User-Agent string ("Python-urllib/x.y") while an identical request with a
browser-like User-Agent succeeds. A fetcher written as a bare
`try: urlopen(url) / except Exception: return None` makes a 403/429 UA-or-rate
block INDISTINGUISHABLE from a genuinely-missing file (a real holiday, a symbol
with no data that day) -- the first live run of the FINRA study returned None for
69/69 attempted days and looked exactly like "this free data source is dead,"
which is a plausible and WRONG verdict for a first-pass prospector idea.

`fetch_url_text()` is the shared fix: set a browser-like User-Agent by default
(cheap, no downside), and raise a typed `HttpFetchBlocked` specifically for a
403/429 response so a caller doing a multi-day loop can detect "every day in
this range came back blocked" and surface that distinctly, instead of silently
recording each as "no data" and mis-diagnosing a live, working data source as
dead. A genuine 404 (or any other transient network error) still fails open and
returns None -- that IS the correct behavior for a real missing-file/holiday day.

Any NEW raw-CDN-scrape fetcher added to this codebase (FRED yield-curve files,
CBOE BXM daily files, NYSE TICK/OpenBook files, Treasury.gov yield files, etc --
several proposed in strategy/candidates/_chef-inbox/) should use this helper
instead of hand-rolling its own urllib.request.urlopen call.
"""
from __future__ import annotations

import urllib.error
import urllib.request

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gamma-research/1.0"

# Status codes that mean "you got blocked" (UA sniffing, rate limiting) rather
# than "this resource genuinely doesn't exist." Callers should treat these as
# loud, distinct signals -- not silently equivalent to a 404.
BLOCKED_STATUS_CODES = (403, 429)


class HttpFetchBlocked(Exception):
    """Raised when a fetch gets an HTTP 403/429 -- distinct from a genuine 404 /
    missing-file case. Callers should NOT silently treat this the same as
    "no data that day"; it usually means the vendor's CDN is UA- or rate-
    blocking the request, and the underlying data may actually be live."""

    def __init__(self, url: str, status: int):
        self.url = url
        self.status = status
        super().__init__(
            f"HTTP {status} (looks like a UA/rate block, not missing data): {url}"
        )


def fetch_url_text(
    url: str,
    timeout: float = 15.0,
    user_agent: str = DEFAULT_USER_AGENT,
    encoding: str = "utf-8",
) -> str | None:
    """Fetch `url` as text with a browser-like User-Agent by default.

    Returns:
        The decoded response body on HTTP 200.
        None for a 404 (genuinely-absent file -- fail open, correct for
        holidays / no-data days) or any other transient network error
        (timeout, DNS failure, connection reset).

    Raises:
        HttpFetchBlocked: for HTTP 403 or 429 specifically. Callers looping
        over many dates/symbols should catch this separately from a plain
        None so a systematic block (e.g. every date in a range is 403) can be
        surfaced as "this fetcher is blocked" rather than silently recorded
        as 65 individual "no data" days (L241).
    """
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        if e.code in BLOCKED_STATUS_CODES:
            raise HttpFetchBlocked(url, e.code) from None
        return None
    except Exception:
        return None
    return raw.decode(encoding, errors="replace")
