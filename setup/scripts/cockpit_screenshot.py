"""cockpit_screenshot.py -- deterministic screenshots of the command center, $0, no LLM.

WHY (2026-09-03, GOAL-COCKPIT-REDESIGN): the in-app browser pane times out on this page
(760 KB, animated), so every design critique and every before/after pair J gets needs a
reliable capture path. Headless Chrome/Edge is on the box; this wraps it.

Usage:
  python setup/scripts/cockpit_screenshot.py --tag before
  python setup/scripts/cockpit_screenshot.py --tag after --views command,journal --sizes 1600x950
  python setup/scripts/cockpit_screenshot.py --tag x --url http://localhost:4317/cockpit.html

Writes analysis/home/screens/<tag>-<view>-<WxH>-<theme>.png and prints one line per file.
Themes: "dark" (default page theme) and "light" via Chrome's --force-color-profile is not a
theme switch, so light is captured by appending ?theme=light which gamma_cockpit_ui.py may
honour; if it does not, the light capture is labelled UNVERIFIED in the summary line.
Never edits anything else. Exit 0 unless --strict.

FIX (round-2 review, critical, 2026-09-03): a dead dev server used to produce 9 silent
"successes" -- Chrome's own ERR_CONNECTION_REFUSED error page is a valid PNG well over the
2000-byte floor, so the old `ok = exists and size > 2000` check happily wrote 9 copies of a
browser error card and called it a batch of screenshots. Two independent guards now catch
that failure mode instead of the file-size heuristic alone:
  1. For an http(s) --url, a pre-flight urllib GET confirms the server answers 200 with a
     body that doesn't carry Chrome/edge's own error-page signature, BEFORE Chrome is ever
     spawned -- fails loud and fast instead of writing a plausible-looking PNG.
  2. Every written PNG is hashed; if two DIFFERENT (view, theme) combinations hash
     byte-identical, that's the "N screenshots collapsed to fewer distinct images" tell
     (a dead page renders the same error chrome regardless of theme/route) and is reported
     as a failure, never silently written to disk as if they were distinct captures.

SETTLED SHOTS ARE REAL-TIME CDP CAPTURES (integration pass, 2026-09-04). Under
`--virtual-time-budget` Chrome barely advances the Web Animations clock: every WAAPI
animation that starts from opacity 0 (Sankey ribbons, the cost-pulse fill, the first
two status words of a 30ms stagger) was captured frozen at ~60ms -- ribbons missing,
panels ghosted at 15-30% -- while the same page in a real-time CDP session was fully
drawn. So the settled shot now launches headless Chrome with a DevTools port, waits
for `load`, waits until no finite-duration animation is still running (capped by
--settle-ms), then Page.captureScreenshot. The virtual-time path stays for the
--delays-ms mid-animation samples (that clock IS the sampling mechanism) and as
`--mode virtual` if the websockets client is unavailable.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "analysis" / "home" / "screens"
CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
]
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _browser() -> Path | None:
    for p in CANDIDATES:
        if p.exists():
            return p
    for name in ("chrome", "msedge", "chromium"):
        w = shutil.which(name)
        if w:
            return Path(w)
    return None


# Signatures Chrome/Edge write into their own "can't be reached" interstitial --
# any of these in a fetched body means the target isn't the app, it's a dead-connection
# error page (round-2 review: this exact page was screenshotted 9 times as if it were
# the dashboard). Lowercase; matched case-insensitively.
_ERROR_PAGE_SIGNATURES = (
    "err_connection_refused",
    "this site can’t be reached",
    "this site can't be reached",
    "refused to connect",
    "err_name_not_resolved",
    "err_connection_timed_out",
)


def preflight(url: str, timeout_s: float = 5.0) -> tuple[bool, str]:
    """For an http(s) URL, confirms the server answers 200 with real body content
    before Chrome is ever spawned. Non-http(s) URLs (file://) skip this -- there is
    no server to be down. Returns (alive, note)."""
    if not url.lower().startswith(("http://", "https://")):
        return True, "non-http url, preflight skipped"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cockpit_screenshot-preflight"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 -- localhost dev server only
            status = resp.status
            body = resp.read(8192).decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        return False, f"preflight GET failed: {e}"
    except OSError as e:
        return False, f"preflight GET failed: {e}"
    if status != 200:
        return False, f"preflight got HTTP {status}"
    lower = body.lower()
    for sig in _ERROR_PAGE_SIGNATURES:
        if sig in lower:
            return False, f"preflight body matches browser error-page signature: {sig!r}"
    return True, f"preflight ok ({status}, {len(body)}B sampled)"


def shoot(browser: Path, url: str, out: Path, size: str, dark: bool, budget_ms: int) -> tuple[bool, str]:
    w, h = size.split("x")
    profile = OUT_DIR / ".profile"
    profile.mkdir(parents=True, exist_ok=True)
    args = [
        str(browser), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
        f"--user-data-dir={profile}", "--hide-scrollbars",
        f"--window-size={w},{h}", f"--screenshot={out}", f"--virtual-time-budget={budget_ms}",
        "--run-all-compositor-stages-before-draw",
    ]
    if dark:
        args.append("--force-dark-mode")
    args.append(url)
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=90, creationflags=_CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return False, "timeout"
    ok = out.exists() and out.stat().st_size > 2000
    return ok, (r.stderr or "").strip().splitlines()[-1:] and (r.stderr.strip().splitlines()[-1][:120]) or ""


CDP_PORT = 9227   # distinct from cockpit_exercise.py's port so the two never collide
_SETTLE_JS = ("(function(){var a=document.getAnimations();return a.filter(function(x){"
              "var t=x.effect&&x.effect.getComputedTiming();"
              "return x.playState==='running'&&t&&isFinite(t.endTime);}).length;})()")


def shoot_cdp(browser: Path, url: str, out: Path, size: str, settle_ms: int) -> tuple[bool, str]:
    """Settled capture over a real-time DevTools session (see module docstring)."""
    try:
        import asyncio
        import base64
        import json
        from cockpit_exercise import CDP
    except Exception as e:  # noqa: BLE001 -- websockets missing, etc.: caller falls back
        return False, f"cdp mode unavailable: {e}"
    w, h = size.split("x")
    profile = OUT_DIR / ".profile-cdp"
    profile.mkdir(parents=True, exist_ok=True)
    args = [
        str(browser), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
        f"--user-data-dir={profile}", "--hide-scrollbars", f"--remote-debugging-port={CDP_PORT}",
        f"--window-size={w},{h}", "about:blank",
    ]

    async def go() -> tuple[bool, str]:
        proc = subprocess.Popen(args, creationflags=_CREATE_NO_WINDOW,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
                return False, f"CDP endpoint on :{CDP_PORT} never surfaced a page target"
            cdp = CDP(target["webSocketDebuggerUrl"])
            await cdp.connect()
            await cdp.send("Page.enable")
            await cdp.send("Runtime.enable")
            await cdp.send("Emulation.setDeviceMetricsOverride", {
                "width": int(w), "height": int(h), "deviceScaleFactor": 1, "mobile": False,
            })
            await cdp.send("Page.navigate", {"url": url})
            try:
                await cdp.wait_event("Page.loadEventFired", timeout=20)
            except TimeoutError:
                pass
            t1 = time.time()
            running = None
            while time.time() - t1 < settle_ms / 1000:
                running, _ = await cdp.eval(_SETTLE_JS)
                if running == 0:
                    break
                await asyncio.sleep(0.15)
            await asyncio.sleep(0.25)
            shot = await cdp.send("Page.captureScreenshot", {"format": "png"})
            out.write_bytes(base64.b64decode(shot["result"]["data"]))
            await cdp.close()
            ok = out.exists() and out.stat().st_size > 2000
            return ok, f"cdp settled: running_anims={running} after {int((time.time()-t1)*1000)}ms"
        finally:
            proc.kill()

    try:
        return asyncio.run(go())
    except Exception as e:  # noqa: BLE001 -- reported, never silently swallowed
        return False, f"cdp capture failed: {e}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--url", default="http://localhost:4317/cockpit.html")
    # Quiet Command (2026-09-03) collapsed Overview/Desks/Orchestration/Engine room/
    # Agents/Army/Cards/Activity into aliases of the one Command view (they still
    # render -- vOverview() etc. all delegate to vCommand() -- but a review pass that
    # screenshots them as if they were distinct pages just gets N identical images and
    # reads that as a bug (round-2 review, critical, 2x: "the four overview screenshots
    # are pixel-identical to command"). Default to the actual four nav tabs; pass an
    # explicit --views to still capture a legacy alias id on purpose.
    ap.add_argument("--views", default="command,autonomy,journal,answers")
    ap.add_argument("--sizes", default="1600x950,1440x900")
    ap.add_argument("--themes", default="dark,light")
    ap.add_argument("--budget-ms", type=int, default=6000)
    ap.add_argument("--mode", choices=("cdp", "virtual"), default="cdp",
                    help="settled-shot mechanism: 'cdp' (real-time DevTools session, waits for "
                         "animations to finish -- the default) or 'virtual' (--virtual-time-budget, "
                         "which freezes WAAPI early; kept for comparison)")
    ap.add_argument("--settle-ms", type=int, default=4000,
                    help="cdp mode: max wait for running animations to finish before capture")
    # MID-ANIMATION STILLS (R5b, 2026-09-03). A settled screenshot cannot show a
    # choreography -- stars -> orchestrator rise -> bento settle -> beams power-up ->
    # rings fill -> figures count up all finish before --budget-ms 6000 draws. The
    # mechanism is already here: --virtual-time-budget IS the clock, so sampling the
    # choreography means asking for a SMALLER budget, not sleeping. Chrome advances
    # virtual time as fast as it can and (with --run-all-compositor-stages-before-draw,
    # already passed) draws the frame at exactly that virtual timestamp, so the same
    # delay yields the same frame every run -- deterministic, not a race.
    #
    # HONEST LIMIT, and it belongs on the same line as any still this produces: the
    # number is VIRTUAL milliseconds since navigation start, not wall clock. CSS and
    # rAF animations honour it; anything a script kicks off after a real network round
    # trip may not have started yet at a small delay. A still is a SAMPLE of the
    # choreography, never proof that a given frame appears on a real machine.
    ap.add_argument("--delays-ms", default="",
                     help="comma-separated virtual-time samples for mid-animation stills, "
                          "e.g. '400,1200'. Empty (default) = settled shot only, byte-identical "
                          "to pre-flag behaviour. Each sample adds one PNG tagged @<n>ms.")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()

    browser = _browser()
    if browser is None:
        print("NO BROWSER: no chrome/edge found -- screenshots UNVERIFIED")
        return 1 if a.strict else 0

    alive, note = preflight(a.url)
    if not alive:
        print(f"SERVER DOWN, refusing to capture: {note} (url={a.url})")
        print("fix: start the dev server (or pass --url file:///path/to/index.html) and re-run")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        delays = [int(d) for d in a.delays_ms.split(",") if d.strip()]
    except ValueError:
        print(f"BAD --delays-ms {a.delays_ms!r}: expected comma-separated integers")
        return 1
    if any(d <= 0 for d in delays):
        print(f"BAD --delays-ms {a.delays_ms!r}: every sample must be > 0")
        return 1
    fails = 0
    # hash -> [(view, size, theme, suffix, relpath), ...] -- lets us catch the exact
    # round-2 failure mode (multiple named captures collapsing to one distinct image)
    # instead of trusting "file exists and is a plausible size".
    hash_seen: dict[str, list[tuple[str, str, str, str, str]]] = {}
    for view in [v for v in a.views.split(",") if v]:
        for size in [s for s in a.sizes.split(",") if s]:
            for theme in [t for t in a.themes.split(",") if t]:
                dark = theme == "dark"
                sep = "&" if "?" in a.url else "?"
                url = f"{a.url}{sep}theme={theme}#{view}"
                # (None,) is the settled shot; each delay adds one mid-animation sample.
                for delay in (None, *delays):
                    suffix = "" if delay is None else f"@{delay}ms"
                    out = OUT_DIR / f"{a.tag}-{view}-{size}-{theme}{suffix}.png"
                    t0 = time.time()
                    if delay is None and a.mode == "cdp":
                        ok, shot_note = shoot_cdp(browser, url, out, size, a.settle_ms)
                        if not ok and "unavailable" in shot_note:
                            ok, shot_note = shoot(browser, url, out, size, dark, a.budget_ms)
                            shot_note = "virtual-time fallback: " + shot_note
                    else:
                        ok, shot_note = shoot(browser, url, out, size, dark,
                                         a.budget_ms if delay is None else delay)
                    fails += 0 if ok else 1
                    rel = out.relative_to(REPO).as_posix()
                    if ok:
                        digest = hashlib.md5(out.read_bytes()).hexdigest()  # noqa: S324 -- dedup only, not security
                        hash_seen.setdefault(digest, []).append((view, size, theme, suffix, rel))
                    print(f"{'OK ' if ok else 'FAIL'} {rel} "
                          f"{int((time.time()-t0)*1000)}ms {shot_note}")
    # Post-batch dedup check: two DIFFERENT (view, theme) captures sharing a hash means
    # the page rendered the same thing regardless of route/theme -- almost always a dead
    # page (error chrome) or a stuck loader, never a legitimate outcome for this app.
    dup_fails = 0
    for digest, entries in hash_seen.items():
        distinct_view_theme = {(v, t) for v, _, t, _, _ in entries}
        if len(distinct_view_theme) > 1:
            dup_fails += 1
            names = ", ".join(rel for *_, rel in entries)
            print(f"DUP HASH {digest[:12]} across {len(distinct_view_theme)} distinct "
                  f"view/theme combos -- these collapsed to one image: {names}")
    fails += dup_fails
    print(f"done: {fails} failures ({dup_fails} duplicate-hash); browser={browser.name}")
    return 1 if (fails and a.strict) else 0


if __name__ == "__main__":
    raise SystemExit(main())
