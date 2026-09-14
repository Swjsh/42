"""hq_screenshot.py -- deterministic, $0, no-LLM headless capture + JS-error diagnosis for
the /hq three.js scene (GOAL-GAMMA-STATION-2026-09-13 items 15-21, "the world").

WHY (2026-09-14 conductor fire): the previous interactive session left `dashboard/components/hq/*`
uncommitted mid-crash-debug (a null `.parent` TypeError somewhere in the r3f render tree, per its
own note: "capture the full stack with a post-load error listener, else bisect one shared file at
a time"). No screenshot/browser-automation tool existed for /hq specifically -- this fills that gap
by reusing the existing CDP client (`cockpit_exercise.CDP`) and the browser-discovery/preflight
pattern from `cockpit_screenshot.py`, instead of re-deriving either.

Usage:
  python setup/scripts/hq_screenshot.py --url http://127.0.0.1:3000/hq --out scratchpad/hq-visuals/hq-check.png

Prints one JSON line: {"ok": bool, "screenshot": path|None, "console_errors": [...], "js_exceptions": [...]}.
`ok` is False if the preflight fails, no browser is found, or the page threw an uncaught exception
after load -- a screenshot can still be written even when `ok` is False (a broken page is still
worth looking at), it is simply not proof the scene renders.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cockpit_screenshot import _browser, preflight  # noqa: E402 -- reuse, don't re-derive

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
CDP_PORT = 9231  # distinct from cockpit_screenshot's 9227 and cockpit_exercise's port


def profile_dir(out: Path) -> Path:
    """The --user-data-dir for the headless capture. MUST be absolute (2026-09-14 debug): a
    relative --user-data-dir silently made Chrome's DevTools port never come up within the poll
    window on this box (the port never opened at all -- every connection attempt timed out, not
    just an empty target list). Confirmed by isolating the one variable: identical launch args
    except an absolute profile dir fixed it outright. Guarded so this specific foot-gun can't
    silently return in a future edit -- see test_hq_screenshot_2026_09_14.py."""
    return (out.parent / ".hq-screenshot-profile").resolve()


async def _capture(browser: Path, url: str, out: Path, width: int, height: int,
                    settle_s: float) -> dict:
    from cockpit_exercise import CDP  # lazy: needs `websockets`, same guard as cockpit_screenshot

    profile = profile_dir(out)
    profile.mkdir(parents=True, exist_ok=True)
    args = [
        str(browser), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
        f"--user-data-dir={profile}", "--hide-scrollbars", f"--remote-debugging-port={CDP_PORT}",
        "--remote-debugging-address=127.0.0.1",
        f"--window-size={width},{height}", "about:blank",
    ]
    proc = subprocess.Popen(args, creationflags=_CREATE_NO_WINDOW,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    result: dict = {"ok": False, "screenshot": None, "console_errors": [], "js_exceptions": [],
                     "note": ""}
    try:
        target = None
        t0 = time.time()
        while time.time() - t0 < 15 and target is None:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json", timeout=2) as resp:
                    for tg in json.loads(resp.read()):
                        if tg.get("type") == "page" and "webSocketDebuggerUrl" in tg:
                            target = tg
                            break
            except (urllib.error.URLError, OSError, json.JSONDecodeError):
                pass
            await asyncio.sleep(0.25)
        if target is None:
            result["note"] = f"CDP endpoint on :{CDP_PORT} never surfaced a page target"
            return result
        cdp = CDP(target["webSocketDebuggerUrl"])
        await cdp.connect()
        await cdp.send("Page.enable")
        await cdp.send("Runtime.enable")
        await cdp.send("Log.enable")
        await cdp.send("Emulation.setDeviceMetricsOverride", {
            "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False,
        })
        await cdp.send("Page.navigate", {"url": url})
        try:
            await cdp.wait_event("Page.loadEventFired", timeout=20)
        except TimeoutError:
            result["note"] = "load event never fired within 20s"
        await asyncio.sleep(settle_s)  # let r3f mount + render a few frames
        shot = await cdp.send("Page.captureScreenshot", {"format": "png"})
        out.write_bytes(base64.b64decode(shot["result"]["data"]))
        result["screenshot"] = str(out)

        # Runtime.exceptionThrown fires on any uncaught error, including React's own
        # error-boundary-less crashes -- this is the "post-load error listener" the
        # prior debug session asked for.
        exc_events = cdp.events_of("Runtime.exceptionThrown")
        for e in exc_events:
            details = e.get("params", {}).get("exceptionDetails", {})
            exc = details.get("exception", {}) or {}
            stack = details.get("stackTrace", {}) or {}
            frames = stack.get("callFrames", [])
            result["js_exceptions"].append({
                "text": exc.get("description") or details.get("text"),
                "url": details.get("url"),
                "line": details.get("lineNumber"),
                "top_frames": [
                    f"{f.get('functionName') or '<anon>'}@{f.get('url')}:{f.get('lineNumber')}"
                    for f in frames[:5]
                ],
            })
        console_errs = [e for e in cdp.events_of("Runtime.consoleAPICalled")
                         if e.get("params", {}).get("type") == "error"]
        for e in console_errs:
            args_ = e.get("params", {}).get("args", [])
            result["console_errors"].append(" ".join(
                str(a.get("value", a.get("description", ""))) for a in args_
            ))
        result["ok"] = out.exists() and out.stat().st_size > 2000 and not result["js_exceptions"]
        await cdp.close()
        return result
    finally:
        proc.kill()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:3000/hq")
    ap.add_argument("--out", default="scratchpad/hq-visuals/hq-check.png")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--settle-s", type=float, default=6.0)
    a = ap.parse_args()

    browser = _browser()
    if browser is None:
        print(json.dumps({"ok": False, "note": "no chrome/edge found"}))
        return 1

    alive, note = preflight(a.url)
    if not alive:
        print(json.dumps({"ok": False, "note": f"preflight failed: {note}"}))
        return 1

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = asyncio.run(_capture(browser, a.url, out, a.width, a.height, a.settle_s))
    except Exception as e:  # noqa: BLE001 -- report, never swallow
        print(json.dumps({"ok": False, "note": f"capture failed: {e}"}))
        return 1
    print(json.dumps(result, indent=None))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
