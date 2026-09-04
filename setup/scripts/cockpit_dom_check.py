"""cockpit_dom_check.py -- headless DOM self-check for the redesigned cockpit page.

WORKSTREAM H_tests_a11y_sweep (COCKPIT-DESIGN-SPEC-2026-09-03.md, section 8).
Loads `analysis/home/index.html` (or a caller-supplied URL) in headless
Chrome/Edge with `?selfcheck=1`, waits for `gamma_cockpit_js.py`'s own
`selfCheck()` to finish (it writes a small honesty report onto
`<html data-selfcheck='{...}'>` about 500ms after the page settles), then
parses that attribute and prints one machine-readable summary line:

    SELFCHECK overflow_x=<bool> tiles=<n> small_text=<n> bad_text=<n> theme=<dark|light>

This never fabricates a report. If Chrome/Edge cannot be found at all this
prints "NO BROWSER" and exits 2 -- never a fake pass (C7: silent success is
failure). If the page loaded but the selfcheck attribute never appeared
(a real render failure, not a missing browser), that is reported and treated
as a failure (exit 1), not silently skipped.

Usage:
    python setup/scripts/cockpit_dom_check.py
    python setup/scripts/cockpit_dom_check.py --theme light
    python setup/scripts/cockpit_dom_check.py --hash gfx        # WS-C's fixture page
    python setup/scripts/cockpit_dom_check.py --url file:///... # override the target

Exit codes:
    0  self-check ran and every rail held (no overflow, no small/bad text,
       and -- only when checking the default #command hash -- at least 15
       tiles rendered)
    1  self-check ran but a rail failed (or the report could not be parsed)
    2  no Chrome/Edge found on this machine -- NO BROWSER, result UNVERIFIED
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INDEX_HTML = REPO / "analysis" / "home" / "index.html"

# Same candidate list as cockpit_screenshot.py -- kept in sync deliberately
# rather than importing (this script must run standalone with no page-level
# dependency on that module's CLI surface).
_CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
]
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

MIN_TILES_ON_COMMAND = 15


def _browser() -> Path | None:
    """Reuses cockpit_screenshot's own discovery contract -- imported when the
    sibling module is importable, so a path fix there never has to be
    duplicated here; falls back to the local candidate list otherwise (this
    script must still work standalone)."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import cockpit_screenshot  # noqa: E402 -- optional convenience import

        found = cockpit_screenshot._browser()
        if found is not None:
            return found
    except Exception:  # noqa: BLE001 -- never let a missing sibling module break this
        pass
    for p in _CANDIDATES:
        if p.exists():
            return p
    for name in ("chrome", "msedge", "chromium"):
        w = shutil.which(name)
        if w:
            return Path(w)
    return None


def _target_url(url: str | None, hash_: str, theme: str) -> str:
    if url:
        base = url
    else:
        base = INDEX_HTML.resolve().as_uri()
    sep = "&" if "?" in base else "?"
    q = f"{sep}selfcheck=1"
    if theme == "light":
        q += "&theme=light"
    frag = f"#{hash_}" if hash_ else ""
    # Strip any pre-existing fragment on a caller-supplied --url before adding ours.
    base_no_frag = base.split("#", 1)[0]
    return f"{base_no_frag}{q}{frag}"


def dump_dom(browser: Path, url: str, budget_ms: int, timeout_s: int) -> tuple[bool, str]:
    """Runs headless Chrome/Edge with --dump-dom and returns (ok, dom_text_or_error)."""
    args = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        f"--virtual-time-budget={budget_ms}",
        "--dump-dom",
        url,
    ]
    try:
        r = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout_s,
            encoding="utf-8", errors="replace",
            creationflags=_CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return False, "timeout waiting for --dump-dom"
    if r.returncode != 0 or not r.stdout:
        tail = (r.stderr or "").strip().splitlines()[-1:] or [""]
        return False, "chrome exited %d: %s" % (r.returncode, tail[0][:200])
    return True, r.stdout


_SELFCHECK_RE = re.compile(r'data-selfcheck="([^"]*)"')


def parse_selfcheck(dom_text: str) -> dict | None:
    m = _SELFCHECK_RE.search(dom_text)
    if not m:
        return None
    raw = html_lib.unescape(m.group(1))
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=None,
                     help="page URL to check (default: analysis/home/index.html on disk)")
    ap.add_argument("--theme", default="dark", choices=("dark", "light"))
    ap.add_argument("--hash", default="command",
                     help="URL fragment to route to before checking (default: command; "
                          "pass gfx for WS-C's graphics-fixture page)")
    ap.add_argument("--budget-ms", type=int, default=6000)
    ap.add_argument("--timeout", type=int, default=90)
    a = ap.parse_args()

    if not a.url and not INDEX_HTML.exists():
        print("NO PAGE: %s does not exist -- run setup/scripts/gamma_home.py first" % INDEX_HTML)
        return 1

    browser = _browser()
    if browser is None:
        print("NO BROWSER: no chrome/edge found -- SELFCHECK result UNVERIFIED")
        return 2

    url = _target_url(a.url, a.hash, a.theme)
    ok, payload = dump_dom(browser, url, a.budget_ms, a.timeout)
    if not ok:
        print("SELFCHECK FAILED TO LOAD: %s (url=%s)" % (payload, url))
        return 1

    report = parse_selfcheck(payload)
    if report is None:
        print("SELFCHECK MISSING: no data-selfcheck attribute found on <html> "
              "(the page may have thrown before selfCheck() ran) url=%s" % url)
        return 1
    if "error" in report:
        print("SELFCHECK ERRORED: %s url=%s" % (report["error"], url))
        return 1

    overflow_x = bool(report.get("overflow_x"))
    tiles = int(report.get("tiles") or 0)
    small_text = int(report.get("small_text") or 0)
    bad_text = int(report.get("bad_text") or 0)

    print("SELFCHECK overflow_x=%s tiles=%d small_text=%d bad_text=%d theme=%s"
          % (overflow_x, tiles, small_text, bad_text, a.theme))
    # Offender samples (selfCheck() collects up to a dozen of each) so a failing
    # rail names its culprits instead of just a count.
    for key in ("overflow_samples", "small_samples", "bad_samples"):
        for item in report.get(key) or []:
            print("  %s: %s" % (key.split("_")[0], item))

    fail = overflow_x or small_text > 0 or bad_text > 0
    # The tile-count floor only applies to the real Command view -- WS-C's
    # #gfx fixture page renders a handful of demo tiles by design and is not
    # meant to clear the same bar.
    if a.hash == "command" and tiles < MIN_TILES_ON_COMMAND:
        fail = True
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
