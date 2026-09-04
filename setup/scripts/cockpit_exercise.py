"""cockpit_exercise.py -- headless CDP behavioral exercise for the redesigned cockpit
page (GOAL-COCKPIT-REDESIGN, Iteration 2 verification pass, 2026-09-03).

WHY THIS EXISTS: cockpit_screenshot.py proves the page RENDERS (a still PNG);
cockpit_dom_check.py proves the DOM is clean (no overflow/small-text/bad-text).
Neither proves the page BEHAVES -- that click/hover/keyboard interactions
actually do what the spec says, that the load choreography actually plays,
and that the numbers on screen actually match the JSON payload the page
loaded. This drives a real headless Chrome over the Chrome DevTools Protocol
(CDP) via raw websockets (no Selenium/Playwright dependency -- the venv only
has `websockets`), dispatches real Input.dispatchMouseEvent/dispatchKeyEvent
so :hover/:focus and native <details> toggling all fire for real, and reports
one JSON verdict plus two themed screenshots.

NEVER clicks a Fire button (`.tile__fire`) -- this is a read-only behavioral
probe, never a trigger for a real action.

Usage:
    backtest/.venv/Scripts/python.exe setup/scripts/cockpit_exercise.py
    backtest/.venv/Scripts/python.exe setup/scripts/cockpit_exercise.py --url http://localhost:4317/cockpit.html?v=i2#command

Prints one line per check plus a final JSON summary line prefixed "RESULT ".
Exit 0 if every check passed and console_errors==0 and dom_ok; else 1.
Exit 2 if no Chrome/Edge could be found, or the CDP endpoint never surfaced
a page target (never a fabricated pass -- C7: silent success is failure).
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCREENS = REPO / "analysis" / "home" / "screens"
PROFILE_DIR = SCREENS / ".cdp-profile"
INDEX_HTML = REPO / "analysis" / "home" / "index.html"
CDP_PORT = 9333
DEFAULT_LIVE_URL = "http://localhost:4317/cockpit.html?v=i2#command"
DEFAULT_HEALTH_URL = "http://localhost:4317/cockpit.html"

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Same discovery contract as cockpit_screenshot.py / cockpit_dom_check.py --
# kept as a literal list (not imported) so this script has zero import-time
# dependency on either sibling module.
CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
]


def _browser() -> Path | None:
    for p in CANDIDATES:
        if p.exists():
            return p
    for name in ("chrome", "msedge", "chromium"):
        w = shutil.which(name)
        if w:
            return Path(w)
    return None


def _server_alive(url: str, timeout_s: float = 3.0) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cockpit_exercise-preflight"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 -- localhost only
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


class CDP:
    """Minimal Chrome DevTools Protocol client over one page-target websocket.
    Async request/response by id, plus a running buffer of unmatched events
    (Page.loadEventFired, Runtime.consoleAPICalled, Log.entryAdded, ...)."""

    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self._ws = None
        self._id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self.events: list[dict] = []
        self._pump_task: asyncio.Task | None = None

    async def connect(self):
        import websockets
        self._ws = await websockets.connect(self.ws_url, max_size=None, ping_interval=None)
        self._pump_task = asyncio.create_task(self._pump())

    async def _pump(self):
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                if "id" in msg:
                    fut = self._pending.pop(msg["id"], None)
                    if fut and not fut.done():
                        fut.set_result(msg)
                else:
                    self.events.append(msg)
        except Exception:  # noqa: BLE001 -- connection closing is expected at teardown
            pass

    async def send(self, method: str, params: dict | None = None, timeout: float = 30.0) -> dict:
        self._id += 1
        mid = self._id
        fut = asyncio.get_event_loop().create_future()
        self._pending[mid] = fut
        await self._ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        return await asyncio.wait_for(fut, timeout=timeout)

    async def wait_event(self, method: str, timeout: float = 30.0) -> dict:
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            for i, ev in enumerate(self.events):
                if ev.get("method") == method:
                    return self.events.pop(i)
            await asyncio.sleep(0.05)
        raise TimeoutError(f"timed out waiting for event {method}")

    def events_of(self, method: str) -> list[dict]:
        return [e for e in self.events if e.get("method") == method]

    async def eval(self, expr: str, await_promise: bool = False, timeout: float = 15.0):
        """Runtime.evaluate wrapper. Returns (value_or_None, exception_text_or_None)."""
        r = await self.send("Runtime.evaluate", {
            "expression": expr, "returnByValue": True, "awaitPromise": await_promise,
        }, timeout=timeout)
        result = r.get("result", {})
        if result.get("exceptionDetails"):
            ex = result["exceptionDetails"]
            return None, (ex.get("exception", {}) or {}).get("description", str(ex))
        return result.get("result", {}).get("value"), None

    async def eval_json(self, js_expr_returning_value: str, timeout: float = 15.0):
        """Evaluates a JS expression, JSON.stringify-wrapped on the JS side, and
        json.loads()'s the result back here. Returns (value_or_None, error_or_None)."""
        val, err = await self.eval(f"JSON.stringify(({js_expr_returning_value}))", timeout=timeout)
        if err:
            return None, err
        if val is None:
            return None, None
        try:
            return json.loads(val), None
        except (json.JSONDecodeError, TypeError) as e:
            return None, f"JSON parse failed: {e}: {val!r}"

    async def rect_of(self, selector: str):
        """Center-point (x, y) of the first element matching selector, or None."""
        val, err = await self.eval_json(
            "(function(){var e=document.querySelector(%s);if(!e)return null;"
            "var r=e.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2,"
            "w:r.width,h:r.height};})()" % json.dumps(selector)
        )
        if err or not val:
            return None
        return val

    async def mouse_move(self, x: float, y: float):
        await self.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})

    async def click_at(self, x: float, y: float, button: str = "left"):
        await self.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        await self.send("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y, "button": button, "clickCount": 1,
        })
        await self.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y, "button": button, "clickCount": 1,
        })

    async def key(self, key: str, code: str, modifiers: int = 0, key_code: int | None = None):
        base = {"key": key, "code": code, "modifiers": modifiers}
        if key_code is not None:
            base["windowsVirtualKeyCode"] = key_code
            base["nativeVirtualKeyCode"] = key_code
        await self.send("Input.dispatchKeyEvent", {**base, "type": "keyDown"})
        await self.send("Input.dispatchKeyEvent", {**base, "type": "keyUp"})

    async def close(self):
        if self._pump_task:
            self._pump_task.cancel()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass


def _mk_check(name: str, ok: bool, evidence: str) -> dict:
    return {"name": name, "ok": bool(ok), "evidence": evidence}


_RING_SEL = ("document.querySelector('.gfx-ringv circle[stroke-dasharray], "
             ".gfx-ringbig circle[stroke-dasharray]')")


async def poll_choreography(cdp: CDP, t0: float, duration_s: float = 2.0,
                             interval_s: float = 0.08) -> list[tuple[int, dict]]:
    """Polls a small state bundle (ring stroke-dashoffset, running-animation count,
    vitals-tile count, stagger-host count) every ~interval_s starting at t0, for
    duration_s. Anchored to t0 (caller passes the domContentEventFired timestamp,
    not loadEventFired) because the boot IIFE runs inline at the bottom of <body>
    and completes its choreography well before the `load` event (which additionally
    waits on fonts/images) -- anchoring samples to `load` was measured to already
    show a SETTLED (0px) ring on both samples, because by the time `load` fired the
    500ms(+stagger delay) WAAPI animation had already finished minutes -- er,
    milliseconds -- earlier. A real wall-clock poll series, not two fixed marks,
    also sidesteps CDP round-trip jitter: two arbitrarily-chosen instants can both
    land after a fast animation finishes even when it definitely ran."""
    series: list[tuple[int, dict]] = []
    end = time.monotonic() + duration_s
    while time.monotonic() < end:
        val, _ = await cdp.eval_json(
            "{ring: (%s) ? getComputedStyle(%s).strokeDashoffset : null,"
            "anims: document.getAnimations().length,"
            "vitals: document.querySelectorAll('.vitals .vital').length,"
            "stagger: document.querySelectorAll('.stagger').length}"
            % (_RING_SEL, _RING_SEL)
        )
        t_ms = int((time.monotonic() - t0) * 1000)
        series.append((t_ms, val or {}))
        await asyncio.sleep(interval_s)
    return series


def _nearest(series: list[tuple[int, dict]], target_ms: int) -> dict:
    if not series:
        return {}
    return min(series, key=lambda p: abs(p[0] - target_ms))[1]


def check_ring_from_series(series: list[tuple[int, dict]]) -> dict:
    rings = [(t, s.get("ring")) for t, s in series if s.get("ring") is not None]
    if not rings:
        return _mk_check("ring_animates", False,
                          "no ring circle[stroke-dasharray] found in DOM during the poll window")
    distinct = {v for _, v in rings}
    near_100 = _nearest(series, 100).get("ring")
    near_900 = _nearest(series, 900).get("ring")
    ok = len(distinct) >= 2
    return _mk_check(
        "ring_animates", ok,
        f"strokeDashoffset samples (t_ms,val)={rings[:12]}{'...' if len(rings) > 12 else ''} "
        f"nearest_100ms={near_100!r} nearest_900ms={near_900!r} distinct_values={len(distinct)}"
    )


async def check_vitals_grid(cdp: CDP) -> dict:
    vlist, err = await cdp.eval_json(
        "Array.prototype.slice.call(document.querySelectorAll('.vitals .vital'))"
        ".map(function(v){return {id:v.id, hasSvg: !!v.querySelector('svg')};})"
    )
    vlist = vlist or []
    ok = len(vlist) >= 6 and all(v.get("hasSvg") for v in vlist)
    return _mk_check("vitals_grid_min6_with_svg", ok,
                      f"count={len(vlist)} ids={[v.get('id') for v in vlist]} "
                      f"all_have_svg={all(v.get('hasSvg') for v in vlist) if vlist else False} err={err}")


def check_load_choreography_from_series(load_ok: bool, series: list[tuple[int, dict]]) -> dict:
    early = _nearest(series, 100)
    late = _nearest(series, max((t for t, _ in series), default=1800))
    ok = bool(load_ok) and (early.get("anims") or 0) > 0 and (late.get("vitals") or 0) >= 6
    return _mk_check(
        "load_choreography_ran", ok,
        f"load_event_fired={load_ok} anims_near_100ms={early.get('anims')} "
        f"@t={late and series[-1][0]}ms: vitals_rendered={late.get('vitals')} "
        f"stagger_hosts={late.get('stagger')} anims_still_running={late.get('anims')} "
        "(NOTE: source has no literal data-loaded marker/attribute -- verified against grep of "
        "gamma_cockpit_js.py/gamma_cockpit_command_js.py/gamma_cockpit_ui_motion.py -- so 'settled' "
        "is proxied via vitals-tile population + .stagger class presence, not a fabricated attribute; "
        "samples anchored to Page.domContentEventFired, not loadEventFired -- see poll_choreography docstring)"
    )


async def check_needs_you_details(cdp: CDP) -> dict:
    """Clicks the FIRST 'Needs you' row's <summary> (not the parent <details> box --
    while closed the box IS just the summary's height, but a rect-of-the-parent
    click landed off-target in an earlier version of this check and produced a
    reversed open/close reading). Body-open state is read from the native
    `::details-content` pseudo-element's computed height, since `.tile__body`
    itself keeps its natural layout height even while its ::details-content
    ancestor is clipped to 0 (an earlier version treated .tile__body height>0 as
    'open' and got a false positive on the CLOSED state)."""
    d_sel = "#group-needs-you details.tile"
    s_sel = "#group-needs-you details.tile summary"
    rect = await cdp.rect_of(s_sel)
    if not rect:
        return _mk_check("needs_you_details_toggle", False,
                          f"no element matched {s_sel!r} (Needs-you group empty or not rendered)")
    x, y = rect["x"], rect["y"]

    async def _state():
        return await cdp.eval_json(
            f"(function(){{var d=document.querySelector({json.dumps(d_sel)});"
            f"var cs=getComputedStyle(d,'::details-content');"
            f"return {{open:d.open, details_content_h: cs?parseFloat(cs.height):null}};}})()"
        )

    # Round-trip, state-agnostic: a rerun against the same headless profile can find
    # the tile already open (localStorage persists tilesLoadOpen() ids across loads --
    # an earlier version of this check assumed 'closed' as the only possible starting
    # state and mis-scored a perfectly-working toggle as a failure). Click 1 must flip
    # `open` away from `before`; click 2 must flip it back.
    before, _ = await _state()
    before_open = bool(before and before.get("open"))
    await cdp.click_at(x, y)
    await asyncio.sleep(0.4)
    after_click1, _ = await _state()
    await cdp.click_at(x, y)
    await asyncio.sleep(0.3)
    after_click2, _ = await _state()

    def _consistent(state: dict | None, expect_open: bool) -> bool:
        if not state or state.get("open") is not expect_open:
            return False
        h = state.get("details_content_h") or 0
        return h > 0 if expect_open else h == 0

    click1_ok = _consistent(after_click1, not before_open)
    click2_ok = _consistent(after_click2, before_open)
    ok = click1_ok and click2_ok
    return _mk_check("needs_you_details_toggle", ok,
                      f"before(open={before_open})={before} after_click_1={after_click1} "
                      f"after_click_2={after_click2}")


async def check_hover_bg(cdp: CDP) -> dict:
    sel = ".vital__head"
    rect = await cdp.rect_of(sel)
    if not rect:
        return _mk_check("hover_changes_background", False, f"no element matched {sel!r}")
    x, y = rect["x"], rect["y"]
    resting, _ = await cdp.eval(f"getComputedStyle(document.querySelector({json.dumps(sel)})).backgroundColor")
    # move away first so the resting sample isn't itself already hovered
    await cdp.mouse_move(2, 2)
    await asyncio.sleep(0.1)
    resting2, _ = await cdp.eval(f"getComputedStyle(document.querySelector({json.dumps(sel)})).backgroundColor")
    await cdp.mouse_move(x, y)
    await asyncio.sleep(0.2)
    hovered, _ = await cdp.eval(f"getComputedStyle(document.querySelector({json.dumps(sel)})).backgroundColor")
    ok = hovered != resting2
    return _mk_check("hover_changes_background", ok,
                      f"selector={sel} resting={resting2!r} hovered={hovered!r} (initial_sample={resting!r})")


async def check_theme_toggle(cdp: CDP) -> dict:
    before, _ = await cdp.eval_json(
        "{theme:document.documentElement.getAttribute('data-theme'),"
        "bg:getComputedStyle(document.body).backgroundColor}"
    )
    rect = await cdp.rect_of("#themebtn")
    if not rect:
        return _mk_check("theme_toggle", False, "no #themebtn found in DOM")
    await cdp.click_at(rect["x"], rect["y"])
    await asyncio.sleep(0.3)
    after, _ = await cdp.eval_json(
        "{theme:document.documentElement.getAttribute('data-theme'),"
        "bg:getComputedStyle(document.body).backgroundColor}"
    )

    def _luma(rgb_str: str | None):
        if not rgb_str:
            return None
        nums = [float(n) for n in rgb_str.replace("rgba(", "").replace("rgb(", "")
                .replace(")", "").split(",")[:3]]
        if len(nums) < 3:
            return None
        r, g, b = nums
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    l1, l2 = _luma((before or {}).get("bg")), _luma((after or {}).get("bg"))
    theme_flipped = bool(before and after and before.get("theme") != after.get("theme"))
    luma_changed = bool(l1 is not None and l2 is not None and abs(l1 - l2) > 5)
    ok = theme_flipped and luma_changed
    return _mk_check("theme_toggle", ok,
                      f"before={before} after={after} luma_before={l1} luma_after={l2} "
                      f"theme_flipped={theme_flipped} luma_changed={luma_changed}")


async def check_j_focus(cdp: CDP) -> dict:
    """document.body.focus() is a documented no-op (body carries no tabindex, so
    script .focus() on it silently does nothing per spec) -- an earlier version
    relied on that as a 'reset to nothing focused' baseline and got a moving-target
    activeElement left over from a previous check's real click. This version
    establishes a KNOWN baseline explicitly: focuses list[0] for real, then verifies
    each 'j' press advances exactly one summary at a time."""
    baseline, _ = await cdp.eval_json(
        "(function(){var l=document.querySelectorAll('.tile > summary');"
        "if(!l.length)return null; l[0].focus();"
        "return {len:l.length, idx:Array.prototype.indexOf.call(l,document.activeElement)};})()"
    )
    if not baseline or baseline.get("idx") != 0:
        return _mk_check("j_moves_focus_to_next_summary", False,
                          f"could not establish baseline focus on summary[0]: {baseline}")
    await cdp.key("j", "KeyJ", key_code=74)
    await asyncio.sleep(0.15)
    after_first, _ = await cdp.eval_json(
        "(function(){var a=document.activeElement;var l=document.querySelectorAll('.tile > summary');"
        "return {tag:a?a.tagName:null, idx:Array.prototype.indexOf.call(l,a)};})()"
    )
    await cdp.key("j", "KeyJ", key_code=74)
    await asyncio.sleep(0.15)
    after_second, _ = await cdp.eval_json(
        "(function(){var a=document.activeElement;var l=document.querySelectorAll('.tile > summary');"
        "return {tag:a?a.tagName:null, idx:Array.prototype.indexOf.call(l,a)};})()"
    )
    first_ok = bool(after_first and after_first.get("tag") == "SUMMARY" and after_first.get("idx") == 1)
    second_ok = bool(after_second and after_second.get("tag") == "SUMMARY" and after_second.get("idx") == 2)
    ok = first_ok and second_ok
    return _mk_check("j_moves_focus_to_next_summary", ok,
                      f"baseline(idx0)={baseline} after_1st_j={after_first} after_2nd_j={after_second}")


async def check_palette(cdp: CDP) -> dict:
    before, _ = await cdp.eval("!!(document.getElementById('pal')&&document.getElementById('pal').classList.contains('on'))")
    await cdp.key("k", "KeyK", modifiers=2, key_code=75)  # modifiers=2 -> Ctrl
    await asyncio.sleep(0.25)
    after, _ = await cdp.eval("!!(document.getElementById('pal')&&document.getElementById('pal').classList.contains('on'))")
    # Escape to close it again so it doesn't leak into later checks/screenshots.
    await cdp.key("Escape", "Escape", key_code=27)
    await asyncio.sleep(0.15)
    ok = (before is False) and (after is True)
    return _mk_check("ctrl_k_opens_palette", ok, f"before={before} after_ctrl_k={after}")


async def check_spend_figure(cdp: CDP) -> dict:
    # NOTE: `D` is declared `const D=__DATA_JSON__` in a plain (non-module) top-level
    # <script> tag -- a top-level const/let does NOT become a `window` property (only
    # `var` does), so `window.D` is always undefined even though the bare identifier
    # `D` resolves fine (Runtime.evaluate shares the page's global lexical scope). An
    # earlier version guarded on `window.D` and always fell through to 'NO DATA'.
    val, err = await cdp.eval_json(
        "(function(){var el=document.querySelector('#vital-budget .vital__figure');"
        "var dom=el?el.textContent:null;"
        "var hasD=(typeof D!=='undefined')&&!!D;"
        "var spent=(hasD&&D.autonomy&&D.autonomy.budget&&D.autonomy.budget.spent_usd!=null)"
        "?D.autonomy.budget.spent_usd:null;"
        "var expected=(spent!=null&&typeof cmdUsd==='function')?cmdUsd(spent):'NO DATA';"
        "return {dom_text:dom, payload_spend_usd:spent, expected_text:expected, D_visible:hasD};})()"
    )
    if err or not val:
        return _mk_check("spend_figure_matches_payload", False, f"eval failed: {err}")
    ok = val.get("dom_text") is not None and val.get("dom_text") == val.get("expected_text")
    return _mk_check("spend_figure_matches_payload", ok, str(val))


async def check_tile_titles(cdp: CDP) -> dict:
    val, err = await cdp.eval_json(
        "Array.prototype.slice.call(document.querySelectorAll('.tile__title')).map(function(e){return e.textContent;})"
    )
    titles = val or []
    bad = []
    import re
    # A COMPLETE word directly followed by an ellipsis ("SCOPE…") is the intended,
    # correct look of _clip()'s truncation (gamma_cockpit_cards.py:_clip breaks at the
    # last whitespace before the cap, so the ellipsis always follows a whole word, not
    # a fragment) -- that is NOT "inside a word". Only flag the ellipsis actually
    # SPLITTING one word into two pieces, word-char immediately on both sides.
    word_ellipsis_re = re.compile(r"\w…\w")
    emoji_re = re.compile(
        "[\U0001F300-\U0001FAFF\u2600-\u27BF]"
    )
    for t in titles:
        if t is None:
            continue
        if "[" in t or "**" in t or word_ellipsis_re.search(t) or emoji_re.search(t):
            bad.append(t)
    ok = len(bad) == 0
    # Codepoint dump for the first offender: the console's own codepage can mangle
    # non-ASCII on print (Windows terminals are a frequent offender here), so report
    # exact U+XXXX values rather than trust the rendered glyph -- this makes a real
    # emoji-in-title and a print-time mojibake artifact distinguishable at a glance.
    codepoints = None
    if bad:
        codepoints = [f"U+{ord(ch):04X}({ch!r})" for ch in bad[0] if ord(ch) > 127]
    return _mk_check("tile_titles_clean", ok,
                      f"count={len(titles)} bad_examples={bad[:5]!r} "
                      f"first_offender_nonascii_codepoints={codepoints} err={err}")


async def run(a: argparse.Namespace) -> dict:
    checks: list[dict] = []
    captures: list[str] = []

    browser = _browser()
    if browser is None:
        return {"fatal": "NO BROWSER: no chrome/edge found on this machine"}

    url = a.url
    fallback_note = ""
    if url is None:
        if _server_alive(DEFAULT_HEALTH_URL):
            url = DEFAULT_LIVE_URL
        else:
            url = INDEX_HTML.resolve().as_uri() + "#command"
            fallback_note = f"http://localhost:4317 down at preflight -- fell back to {url}"
            print(f"NOTE: {fallback_note}")

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    SCREENS.mkdir(parents=True, exist_ok=True)
    chrome_args = [
        str(browser),
        "--headless=new",
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--disable-gpu",
        "--no-default-browser-check",
        "--window-size=1600,950",
    ]
    proc = subprocess.Popen(
        chrome_args, creationflags=_CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        target = None
        t0 = time.monotonic()
        last_err = ""
        while time.monotonic() - t0 < 15:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json", timeout=2) as resp:
                    targets = json.loads(resp.read())
                for t in targets:
                    if t.get("type") == "page" and "webSocketDebuggerUrl" in t:
                        target = t
                        break
                if target:
                    break
            except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
                last_err = str(e)
            await asyncio.sleep(0.25)
        if target is None:
            return {"fatal": f"CDP endpoint on :{CDP_PORT} never surfaced a page target (last_err={last_err})"}

        cdp = CDP(target["webSocketDebuggerUrl"])
        await cdp.connect()
        await cdp.send("Page.enable")
        await cdp.send("Runtime.enable")
        await cdp.send("Log.enable")

        await cdp.send("Page.navigate", {"url": url})
        # domContentEventFired anchors the choreography poll (see poll_choreography
        # docstring: the boot IIFE runs inline at end of <body>, well before `load`,
        # which additionally waits on fonts/images -- anchoring to `load` measured a
        # choreography that had already finished on both samples).
        try:
            await cdp.wait_event("Page.domContentEventFired", timeout=20)
            dcl_ok = True
        except TimeoutError:
            dcl_ok = False
        t_dcl = time.monotonic()
        print(f"navigated to {url} dom_content_event_fired={dcl_ok}")

        # Poll ring/animation/vitals state for ~2s starting right at DOMContentLoaded
        # -- runs FIRST and fast, before any of the slower interaction checks below
        # would otherwise burn the window the choreography actually animates in.
        choreo_series = await poll_choreography(cdp, t_dcl)

        try:
            await cdp.wait_event("Page.loadEventFired", timeout=15)
            load_ok = True
        except TimeoutError:
            load_ok = dcl_ok  # local file:// / already-cached loads may have fired before we asked
        print(f"load_event_fired={load_ok}")

        checks.append(check_ring_from_series(choreo_series))
        checks.append(check_load_choreography_from_series(load_ok, choreo_series))
        checks.append(await check_vitals_grid(cdp))
        checks.append(await check_needs_you_details(cdp))
        checks.append(await check_hover_bg(cdp))
        checks.append(await check_theme_toggle(cdp))
        checks.append(await check_j_focus(cdp))
        checks.append(await check_palette(cdp))
        checks.append(await check_spend_figure(cdp))
        checks.append(await check_tile_titles(cdp))

        console_errs = [e for e in cdp.events_of("Runtime.consoleAPICalled")
                         if e.get("params", {}).get("type") == "error"]
        log_errs = [e for e in cdp.events_of("Log.entryAdded")
                    if (e.get("params", {}).get("entry", {}) or {}).get("level") == "error"]
        console_errors = len(console_errs) + len(log_errs)
        checks.append(_mk_check(
            "zero_console_errors", console_errors == 0,
            f"Runtime.consoleAPICalled(error)={len(console_errs)} Log.entryAdded(error)={len(log_errs)}"
        ))

        # Reset to the actual data-loaded theme state before shooting: the theme
        # check above already clicked #themebtn once, so re-derive current theme
        # rather than assuming 'dark'.
        cur_theme, _ = await cdp.eval("document.documentElement.getAttribute('data-theme')||'dark'")
        want_order = ["dark", "light"] if cur_theme != "light" else ["light", "dark"]
        for theme in ("dark", "light"):
            if theme != cur_theme:
                # flip via the same in-page mechanism the app itself uses, not a
                # raw attribute poke, so CSS actually re-renders.
                await cdp.eval("if(typeof themeToggle==='function')themeToggle();")
                await asyncio.sleep(0.3)
                cur_theme = theme
            await cdp.send("Emulation.setDeviceMetricsOverride", {
                "width": 1600, "height": 950, "deviceScaleFactor": 1, "mobile": False,
            })
            await asyncio.sleep(0.15)
            shot = await cdp.send("Page.captureScreenshot", {"format": "png"})
            data = shot["result"]["data"]
            out = SCREENS / f"i2r1-cdp-{theme}.png"
            out.write_bytes(base64.b64decode(data))
            captures.append(str(out))
            print(f"OK {out.relative_to(REPO).as_posix()} theme={theme}")

        dom_ok = bool(load_ok and any(c["name"] == "vitals_grid_min6_with_svg" and c["ok"] for c in checks))

        await cdp.close()
        return {
            "checks": checks,
            "console_errors": console_errors,
            "dom_ok": dom_ok,
            "captures": captures,
            "url": url,
            "fallback_note": fallback_note,
        }
    finally:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception:  # noqa: BLE001 -- best-effort teardown of a process we spawned
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=None,
                     help="page URL to exercise (default: localhost:4317 cockpit.html?v=i2#command, "
                          "falling back to file:// of analysis/home/index.html if the server is down)")
    a = ap.parse_args()

    result = asyncio.run(run(a))
    if "fatal" in result:
        print(f"FATAL: {result['fatal']}")
        return 2

    for c in result["checks"]:
        print(f"{'PASS' if c['ok'] else 'FAIL'} {c['name']}: {c['evidence']}")
    print("RESULT " + json.dumps({
        "url": result["url"],
        "fallback_note": result["fallback_note"],
        "console_errors": result["console_errors"],
        "dom_ok": result["dom_ok"],
        "captures": result["captures"],
        "n_checks": len(result["checks"]),
        "n_passed": sum(1 for c in result["checks"] if c["ok"]),
    }))
    all_ok = result["dom_ok"] and result["console_errors"] == 0 and all(c["ok"] for c in result["checks"])
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
