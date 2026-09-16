"""HQ live-agent measurement instrument (coordinator cannot see the HQ world
today: the Claude Browser pane is hidden -> UltraCanvasRoot.tsx's `paused =
gaming || document.hidden` stops rendering there, and hq_capture.ps1 only
gives a single PNG from a visible Edge window). This launches a HEADLESS
Chromium via Playwright, drives the real /hq page with ?diag=1&tier=ultra,
and samples window.__hqLiveAgents + /api/hq's liveAgents + renderer stats
over time, then runs them through hq_probe_lib.py's pure verdict logic.

HARDENED 2026-09-14 (this run's own first fire was INVALID, not a real
FAIL): dashboard/.next/BUILD_ID was rewritten by another builder's deploy 4s
before the probe loaded the page. The page hit deleted chunks (400) and a
restarting server (net::ERR_CONNECTION_REFUSED), window.__hqLiveAgents never
appeared within the old 15s wait, and the old code still marked perf PASS on
a scene that never rendered. Fixes, all in this file + hq_probe_lib.py:
  1. Sample /api/hq's build_id at start, every ~30s (piggybacked on the
     normal poll tick), and at the end. ANY drift, or scene_ready=false,
     makes the WHOLE RUN invalid (hq_probe_lib.check_run_validity) -- every
     check becomes NO-DATA with the reason, perf is never PASS, exit code 2.
  2. Refuse to start (exit 3) while dashboard/.build.lock exists or
     dashboard/.next/BUILD_ID is younger than --min-build-age-s (90s
     default) -- optionally poll up to --wait-for-stable-build seconds first.
  3. Scene wait 15s -> --scene-wait-ms (90s default; SwiftShader is slow),
     and the readiness gate now also requires a <canvas> element AND the
     page NOT showing StandbyPanel's "Standby" text.
  4. A partial JSON checkpoint is written to --out every ~30s during the
     run (and best-effort on exit) so an external kill (setup/scripts/
     _shared.ps1#Stop-StaleClaudeProcesses reaps python.exe >5min old) can
     never wipe out a run's whole 200s of data.
  5. perf is PASS only when scene_ready AND frames were measured AND
     draw-call samples exist; otherwise NO-DATA, always labeled HEADLESS.

Dependency note (flagged per task instructions, nothing new installed):
  - No Node Playwright in dashboard/node_modules or the repo root.
  - System Python (py -3.13, the WindowsApps python.exe on PATH) already
    has `playwright` 1.57.0 installed (site-packages shows it's pulled in
    by Crawl4AI / tf-playwright-stealth, pre-existing) with Chromium +
    chromium_headless_shell browsers already downloaded to
    %LOCALAPPDATA%\\ms-playwright. This script uses that pre-existing
    install. If it's ever missing, install via:
      python -m pip install playwright && python -m playwright install chromium
  Read-only against the app: no dashboard/ source files are touched.

Usage:
    python setup/scripts/hq_live_probe.py --seconds 200
    python setup/scripts/hq_live_probe.py --seconds 5 --smoke   # quick check
    python setup/scripts/hq_live_probe.py --wait-for-stable-build 300
    python setup/scripts/hq_live_probe.py --plausibility --out <path>

Plausibility checks (SCENE-AUDIT pass, 2026-09-15, `--plausibility`):
    J's own words, having watched a desk clipped into a wall, a pitched
    unreadable smart board, and an agent pacing straight through a wall all
    PASS every check that existed before this pass: "whatever's auditing it
    isn't looking at it like a human would... the object was placed on the
    screen, checkbox, move on." This flag runs a SEPARATE, smaller family
    (~60-90s, no walker traffic required to get a verdict on the static
    checks) that judges "would a human accept this room" instead of "is
    this present" -- implements markdown/doctrine/FRONTEND-OPS.md's "HQ
    scene acceptance" rubric items 2-4:
      wall_penetration   -- any furniture/prop/screen clipping a wall slab
                             (door gaps excluded) by >0.05u.
      walker_wall_cross   -- any sampled live-agent path segment crossing a
                             wall slab outside a real doorway.
      screen_facing       -- cos(angle) between a screen's face normal and
                             the camera, for the live default camera AND a
                             synthetic top-down one; only screens meant to
                             be readable (TwinMonitors, hub panels) gate the
                             verdict -- desk screens/bay signs are
                             informational only.
      desk_clearance /
      desk_orientation    -- every desk >=1.0u clear of the nearest wall and
                             not overlapping other furniture; yaw within
                             +-10deg of its own expected facing.
      label_legibility    -- any visible head-label/plaque under 12px tall
                             at the default camera (excludes a label the
                             runtime declutter resolver already faded to
                             ~0 opacity for being too small -- handled, not
                             an unaddressed violation).
      label_vs_screen_overlap -- (SCREEN-KEEP-OUT pass, 2026-09-15) any
                             visible label covering >10% of a READABLE
                             screen's own projected viewport rect (e.g. a
                             head label drifting over TwinMonitors' glass).
    The actual geometry (wall-slab construction with door gaps, AABB/segment
    intersection, screen-facing cosine) lives in dashboard/lib/
    hq-scene-audit.ts (unit-tested via `node --test
    dashboard/tests/hq-scene-audit.test.ts`, including two regression pins
    against real fixed bugs -- see that file's own header) and runs
    IN-PAGE via window.__hqSceneAudit()/__hqSceneAuditWalkers()/
    __hqSceneAuditWalkerCheck(); this script only launches the browser,
    polls those hooks, and formats the verdicts in this probe's existing
    PASS/FAIL/NO-DATA style. label_legibility alone is pure Python (reuses
    the SAME `.hq-beam` DOM rects check_label_overlap already samples).
    Included automatically inside a normal (non --plausibility) run too --
    riding along in the report's environment.plausibility block (see
    launch_and_probe's own call to compute_plausibility_verdicts near the
    end of its sampling loop) rather than a second browser launch.

Output: JSON to stdout AND automation/state/station/hq-probe-latest.json
(partial checkpoints during the run, final report at the end).
Exit codes: 0 = run valid (verdicts may still individually FAIL/PASS/NO-DATA),
2 = run INVALID (build drift or scene never ready -- see verdicts.invalid_reasons),
3 = refused to start (unstable build -- see stderr).
"""
from __future__ import annotations

import argparse
import atexit
import gzip
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hq_probe_lib import (  # noqa: E402
    SPEED_WINDOW_S_DEFAULT,
    WALK_SPEED_DEFAULT,
    WALK_SPEED_TOL_DEFAULT,
    build_verdicts,
    check_label_legibility,
    check_label_screen_overlap,
    perf_headless_flag,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "automation" / "state" / "station" / "hq-probe-latest.json"
SAMPLE_RUNS_DIR = REPO_ROOT / "automation" / "state" / "station" / "hq-probe-runs"
SAMPLE_RUNS_RETENTION_KEEP = 20
DASHBOARD_DIR = REPO_ROOT / "dashboard"
BUILD_ID_PATH = DASHBOARD_DIR / ".next" / "BUILD_ID"
BUILD_LOCK_PATH = DASHBOARD_DIR / ".build.lock"

DEFAULT_URL = "http://127.0.0.1:3000/hq?diag=1&tier=ultra"
DEFAULT_MIN_BUILD_AGE_S = 90.0
DEFAULT_SCENE_WAIT_MS = 90_000
PARTIAL_WRITE_INTERVAL_S = 30.0

# In-page hook installed BEFORE navigation so it wraps the real rAF loop
# r3f's Canvas uses (frameloop="always" in UltraCanvasRoot.tsx when not
# paused/gaming). Ring-buffered so a long run can't leak memory.
RAF_HOOK_SCRIPT = """
(() => {
  window.__probeRaf = [];
  const orig = window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame = (cb) => orig((t) => {
    window.__probeRaf.push(t);
    if (window.__probeRaf.length > 20000) window.__probeRaf.shift();
    return cb(t);
  });
})();
"""

FETCH_BUILD_ID_SCRIPT = (
    "async () => { try { const r = await fetch('/api/hq', { cache: 'no-store' }); "
    "const j = await r.json(); return j.build_id ?? null; } catch (e) { return null; } }"
)

# Attempt 1: new-headless Chromium with real GPU access via ANGLE/D3D11 (this
# box has an NVIDIA RTX 5080 -- hardware GL is available if Chromium is
# allowed to use it). Attempt 2 (fallback only) is the old SwiftShader
# software-rasterizer path. Never render a visible window either way.
HARDWARE_GL_ARGS = [
    "--headless=new",
    "--use-angle=d3d11",
    "--enable-gpu",
    "--ignore-gpu-blocklist",
    "--disable-gpu-sandbox",
    "--no-sandbox",
]

SOFTWARE_GL_ARGS = [
    "--headless=new",
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-webgl",
    "--enable-webgl2",
    "--ignore-gpu-blocklist",
    "--enable-unsafe-swiftshader",
    "--disable-gpu-sandbox",
    "--no-sandbox",
]

# Reads the UNMASKED_RENDERER string via WEBGL_debug_renderer_info -- the
# only reliable way to tell "real NVIDIA GPU" apart from "SwiftShader
# pretending to be a GL context" (both create a context successfully;
# only the renderer string tells them apart).
GL_RENDERER_SCRIPT = """
() => {
  try {
    const c = document.createElement('canvas');
    const gl = c.getContext('webgl2') || c.getContext('webgl');
    if (!gl) return null;
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    if (!ext) return gl.getParameter(gl.RENDERER);
    return gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
  } catch (e) {
    return null;
  }
}
"""

SAMPLE_SCRIPT = """
async () => {
  let apiAgents = [];
  let apiError = null;
  let buildId = null;
  // PROBE-16 (coordinator, 2026-09-15): mirrors UltraCanvasRoot.tsx's own
  // `paused = gaming || hidden || brainBusy` byte-for-byte (that component
  // sets frameloop="never" and hides the canvas exactly when this is
  // true -- see hq_probe_lib.py's PAUSE_FRAME_GAP_MAX_S header for the
  // full PROBE-16 writeup). Sourced from the SAME /api/hq JSON this
  // function already fetches for apiAgents -- zero extra network cost.
  // null (not false) when the fetch itself failed, so a caller can tell
  // "known not paused" from "unknown" (never silently read as un-paused).
  let paused = null;
  try {
    const r = await fetch('/api/hq', { cache: 'no-store' });
    const j = await r.json();
    apiAgents = j.liveAgents || [];
    apiError = j.liveAgentsError || null;
    buildId = j.build_id || null;
    const brainBusy = !!(j.runtime && j.runtime.brain && j.runtime.brain.busy === true);
    paused = j.mode === 'gaming' || document.hidden || brainBusy;
  } catch (e) {
    apiError = String(e);
  }
  const pageAgents = window.__hqLiveAgents || [];
  let calls = null;
  try {
    calls = window.__hqGl && window.__hqGl.info ? window.__hqGl.info.render.calls : null;
  } catch (e) {
    calls = null;
  }
  // PROBE-11 (coordinator, 2026-09-15): speech-bubble overlap instrument.
  // NO stable DOM hook exists for "a declutter-registered label" -- the
  // registry (dashboard/components/hq/useLabelDeclutter.ts) is a
  // module-scope Map of React refs, invisible to an outside page.evaluate()
  // script, and no label/plaque wrapper carries a data attribute (only
  // Hud.tsx's FIXED overlay chrome does, via [data-hq-obstacle] --
  // LabelDeclutterManager.tsx's own OBSTACLE_SELECTOR comment). The most
  // specific EXISTING selector is `.hq-beam` (the shared CSS class every
  // label/plaque box's visible border/background lives on -- LiveAgents.tsx,
  // Agent.tsx, GammaCharacter.tsx, BrainCore.tsx's plaque all use it) but it
  // is NOT exclusive to declutter-managed labels (HoloChart.tsx,
  // Scene.tsx's trade-action strip, and StationModule.tsx also render
  // `.hq-beam` boxes that never register with useLabelDeclutter) -- read
  // this as "every declutter label plus some non-label decoration", not
  // "every declutter label and nothing else". No id is recoverable this
  // way either (the declutter id -- e.g. "live:<agentId>" -- lives only in
  // the React-side registry key, never written to the DOM), so
  // check_label_overlap identifies live-agent bubbles by TEXT match against
  // page_agents' own bubble string, not by id.
  //
  // Opacity: NEITHER the declutter resolver's own fade (written to the
  // OUTER wrapper div) NOR the camera-distance fade (written to the
  // measureRef div, `.hq-beam`'s parent in LiveAgents/Agent/
  // GammaCharacter, or `.hq-beam` itself in BrainCore) land on `.hq-beam`
  // as its OWN inline style -- getComputedStyle(el).opacity alone would
  // always read "1". CSS opacity composites multiplicatively down the
  // ancestor chain at render time, so the only way to recover the true
  // ON-SCREEN opacity from outside React is to walk up and multiply each
  // ancestor's own computed opacity (bounded to a few hops -- these label
  // trees are shallow, and unbounded walking risks climbing into
  // unrelated ancestors of a non-label `.hq-beam`).
  function effectiveLabelOpacity(el) {
    let o = 1;
    let node = el;
    let hops = 0;
    while (node && node.nodeType === 1 && hops < 8) {
      const cs = window.getComputedStyle(node);
      if (cs.display === 'none' || cs.visibility === 'hidden') return 0;
      const v = parseFloat(cs.opacity);
      if (!Number.isNaN(v)) o *= v;
      if (node === document.body) break;
      node = node.parentElement;
      hops += 1;
    }
    return o;
  }
  let labelRects = [];
  try {
    const nodes = document.querySelectorAll('.hq-beam');
    for (let i = 0; i < nodes.length && labelRects.length < 60; i++) {
      const el = nodes[i];
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      const opacity = effectiveLabelOpacity(el);
      labelRects.push({
        id: null, // not discoverable from the DOM -- see comment above
        text: (el.innerText || '').slice(0, 60),
        x: r.left,
        y: r.top,
        w: r.width,
        h: r.height,
        opacity,
        visible: opacity > 0.01 && r.width > 0 && r.height > 0,
      });
    }
  } catch (e) {
    labelRects = [];
  }
  return {
    pageAgents,
    apiAgents: apiAgents.map((a) => ({ id: a.id, state: a.state })),
    apiError,
    calls,
    buildId,
    documentHidden: document.hidden,
    paused,
    labelRects,
    // In-page timestamp, captured in the SAME evaluate() call that reads
    // window.__hqLiveAgents -- used by check_walk_speed instead of the
    // Python wall-clock time this CDP round-trip finishes (which has
    // 0.198-0.808s jitter unrelated to true agent speed; WALK-SPEED-DIAG
    // coordinator finding, 2026-09-15).
    pageTMs: performance.now(),
  };
}
"""


PLAUSIBILITY_SAMPLE_INTERVAL_S = 0.25  # <=4x/s per this pass's own task spec
PLAUSIBILITY_DEFAULT_SECONDS = 60


def _plausibility_no_data(reason: str) -> Dict[str, Any]:
    return {"verdict": "NO-DATA", "detail": {"reason": reason}}


def compute_plausibility_verdicts(page: Any, seconds: float, scene_ready: bool) -> Dict[str, Any]:
    """Runs the "would a human accept this room" check family (see this
    module's own docstring) against an ALREADY-NAVIGATED `page`. Shared by
    BOTH run_plausibility's own short standalone run and launch_and_probe's
    full run (called near the end of its own sampling loop) -- one code
    path, never a second copy that could drift. Pure read-only page.evaluate
    calls; never navigates, never touches dashboard/ source.

    wall_penetration/screen_facing/desk_clearance/desk_orientation come from
    ONE call to window.__hqSceneAudit() (dashboard/lib/hq-scene-audit.ts) --
    the static scene geometry doesn't change tick-to-tick, so one snapshot
    is sufficient (unlike walker_wall_cross, which needs a position HISTORY
    to detect a crossing SEGMENT, not just a single point-in-time reading).
    """
    if not scene_ready:
        no_data = _plausibility_no_data("scene never became ready")
        return {
            "wall_penetration": no_data, "walker_wall_cross": no_data, "screen_facing": no_data,
            "desk_clearance": no_data, "desk_orientation": no_data, "label_legibility": no_data,
            "label_vs_screen_overlap": no_data,
        }

    try:
        static_report = page.evaluate(
            "async () => (window.__hqSceneAudit ? await window.__hqSceneAudit() : { ok: false, reason: 'window.__hqSceneAudit is not set -- ?diag=1 missing or scene not mounted' })"
        ) or {}
    except Exception as exc:  # noqa: BLE001
        static_report = {"ok": False, "reason": f"window.__hqSceneAudit() threw: {exc!r}"}

    if not static_report.get("ok"):
        no_hook = _plausibility_no_data(str(static_report.get("reason", "window.__hqSceneAudit unavailable")))
        return {
            "wall_penetration": no_hook, "walker_wall_cross": no_hook, "screen_facing": no_hook,
            "desk_clearance": no_hook, "desk_orientation": no_hook, "label_legibility": no_hook,
            "label_vs_screen_overlap": no_hook,
        }

    # Walker positions + label rects: sampled over time (a wall CROSSING is
    # a property of a SEGMENT between two ticks, not a single point) at
    # <=4x/s -- deliberately cheap, this is a DOM/JS-array read per tick,
    # never a screenshot or a full page.evaluate of the whole scene graph.
    label_samples: List[Dict[str, Any]] = []
    n_ticks = max(1, int(seconds / PLAUSIBILITY_SAMPLE_INTERVAL_S))
    for _ in range(n_ticks):
        tick_t0 = time.time()
        try:
            page.evaluate("() => { if (window.__hqSceneAuditWalkers) window.__hqSceneAuditWalkers(); }")
        except Exception:  # noqa: BLE001
            pass
        try:
            # LEGIBILITY-FLOOR fix (2026-09-15): opacity now travels with
            # each rect, via the SAME ancestor-walk `effectiveLabelOpacity`
            # already uses a few lines above for the richer (non-
            # plausibility) capture -- CSS opacity composites down the
            # declutter wrapper chain (see that function's own comment),
            # so a plain getComputedStyle(el).opacity here would always
            # read "1" even for a label the resolver just faded to 0.
            # check_label_legibility uses this to exclude a label the
            # runtime already hid for being too small, rather than double-
            # counting it as an unaddressed violation.
            rects = page.evaluate(
                "() => Array.from(document.querySelectorAll('.hq-beam')).slice(0, 60).map((el) => { "
                "const r = el.getBoundingClientRect(); "
                "let o = 1; let node = el; let hops = 0; "
                "while (node && node.nodeType === 1 && hops < 8) { "
                "const cs = window.getComputedStyle(node); "
                "if (cs.display === 'none' || cs.visibility === 'hidden') { o = 0; break; } "
                "const v = parseFloat(cs.opacity); if (!Number.isNaN(v)) o *= v; "
                "if (node === document.body) break; node = node.parentElement; hops += 1; } "
                "return { x: r.left, y: r.top, w: r.width, h: r.height, text: (el.innerText || '').slice(0, 60), visible: r.width > 0 && r.height > 0, opacity: o }; })"
            )
        except Exception:  # noqa: BLE001
            rects = []
        # SCREEN-KEEP-OUT PER-TICK FIX (2026-09-16, root cause: this loop's
        # own screen_viewport_rects used to be captured ONCE, outside this
        # loop, from the single static_report snapshot above -- correct
        # only when the camera never moves (the `?tour=0` static overview
        # this worker's own --plausibility check happened to run against),
        # wrong for the REAL full-probe camera, which auto-orbits/drifts the
        # whole run. hq-scene-audit.ts#computeScreenViewportRectsReport is
        # the same screen-only projection, callable per tick (cheap -- a
        # handful of screens, not the full wall/desk/furniture traversal),
        # so this now captures THIS tick's own screen rects to pair with
        # THIS tick's label rects. Falls back to `None` (check_label_screen
        # _overlap then uses the caller-supplied static list) on any build
        # that predates the `window.__hqSceneAuditScreens` hook, or on any
        # per-tick eval failure -- never a hard failure of the whole run.
        try:
            screens_report = page.evaluate(
                "async () => (window.__hqSceneAuditScreens ? await window.__hqSceneAuditScreens() : null)"
            )
            tick_screen_rects = (
                screens_report.get("screenViewportRects")
                if isinstance(screens_report, dict) and screens_report.get("ok")
                else None
            )
        except Exception:  # noqa: BLE001
            tick_screen_rects = None
        label_samples.append({"label_rects": rects, "screen_rects": tick_screen_rects})
        elapsed = time.time() - tick_t0
        time.sleep(max(0.0, PLAUSIBILITY_SAMPLE_INTERVAL_S - elapsed))

    try:
        tracks_raw = page.evaluate(
            "() => window.__hqSceneAuditWalkers ? window.__hqSceneAuditWalkers() : { tracks: [] }"
        ) or {}
        tracks = tracks_raw.get("tracks", []) if isinstance(tracks_raw, dict) else []
    except Exception:  # noqa: BLE001
        tracks = []

    if tracks:
        try:
            walker_wall_cross = page.evaluate(
                "async (tracks) => (window.__hqSceneAuditWalkerCheck "
                "? await window.__hqSceneAuditWalkerCheck(tracks) "
                ": { verdict: 'NO-DATA', detail: { reason: 'window.__hqSceneAuditWalkerCheck is not set' } })",
                tracks,
            )
        except Exception as exc:  # noqa: BLE001
            walker_wall_cross = _plausibility_no_data(f"__hqSceneAuditWalkerCheck threw: {exc!r}")
    else:
        walker_wall_cross = _plausibility_no_data("no live agents were on window.__hqLiveAgents this run -- nothing to trace")

    screen_viewport_rects = static_report.get("screenViewportRects", [])
    return {
        "wall_penetration": static_report.get("wallPenetration", _plausibility_no_data("missing from __hqSceneAudit() report")),
        "screen_facing": static_report.get("screenFacing", _plausibility_no_data("missing from __hqSceneAudit() report")),
        "desk_clearance": static_report.get("deskClearance", _plausibility_no_data("missing from __hqSceneAudit() report")),
        "desk_orientation": static_report.get("deskOrientation", _plausibility_no_data("missing from __hqSceneAudit() report")),
        "walker_wall_cross": walker_wall_cross,
        "label_legibility": check_label_legibility(label_samples),
        "label_vs_screen_overlap": check_label_screen_overlap(label_samples, screen_viewport_rects),
    }


def print_plausibility_lines(plausibility: Dict[str, Any]) -> None:
    """PASS/FAIL/NO-DATA <check>: <one-line evidence> -- same style every
    other check_* verdict in this probe already prints via main()'s own
    json.dumps of the report (this is the human-skimmable stderr/stdout
    echo, not a second source of truth)."""
    for name, result in plausibility.items():
        verdict = result.get("verdict", "NO-DATA")
        detail = result.get("detail", {})
        if verdict == "NO-DATA":
            evidence = detail.get("reason", "no evidence")
        elif verdict == "FAIL":
            violations = detail.get("violations") or []
            evidence = f"{len(violations)} violation(s) -- first: {violations[0]}" if violations else json.dumps(detail)[:160]
        else:
            evidence = json.dumps({k: v for k, v in detail.items() if k not in ("violations",)})[:160]
        print(f"{verdict} {name}: {evidence}")


def run_plausibility(url: str, seconds: float, out_path: Path, scene_wait_ms: int, min_build_age_s: float) -> int:
    """Standalone ~60-90s path (--plausibility): launches its OWN headless
    page (lighter than launch_and_probe's full RAF-hook/build-drift-guarded
    session -- this check family doesn't need frame timestamps or draw-call
    counts), waits for window.__hqSceneAudit to exist, then delegates all
    real work to compute_plausibility_verdicts (the SAME function
    launch_and_probe's full run calls) so there is exactly one
    implementation of "what counts as plausible", never two."""
    from playwright.sync_api import sync_playwright

    refuse_reason = check_build_stable(min_build_age_s)
    if refuse_reason:
        print(f"REFUSED to start: {refuse_reason}", file=sys.stderr)
        return 3

    diag: Dict[str, Any] = {}
    plausibility: Dict[str, Any] = {}
    browser = None
    context = None
    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(headless=True, args=HARDWARE_GL_ARGS)
                context = browser.new_context(viewport={"width": 1600, "height": 900})
                page = context.new_page()
                gl_renderer = page.evaluate(GL_RENDERER_SCRIPT)
                gl_is_hardware = bool(gl_renderer) and "nvidia" in gl_renderer.lower()
            except Exception as exc:  # noqa: BLE001
                gl_is_hardware = False
                diag["gl_fallback_reason"] = f"hardware GL launch raised {exc!r}"
            if not gl_is_hardware:
                diag.setdefault("gl_fallback_reason", "hardware GL probe did not report an NVIDIA renderer -- falling back to SwiftShader")
                _close_quietly(context)
                _close_quietly(browser)
                browser = pw.chromium.launch(headless=True, args=SOFTWARE_GL_ARGS)
                context = browser.new_context(viewport={"width": 1600, "height": 900})
                page = context.new_page()
            diag["gl_is_hardware"] = gl_is_hardware

            page.goto(url, wait_until="load", timeout=60000)
            scene_ready = True
            try:
                # Waits for at least one FURNITURE-tagged object, not just
                # window.__hqScene's existence -- HubRoom's table/chair
                # InstancedKitPool mounts are wrapped in <Suspense> (GLTF
                # loads async), so __hqScene can exist with the room shell
                # already tagged "wall" well before furniture finishes
                # loading. Calling window.__hqSceneAudit() during that gap
                # is exactly what produced a false "no furniture/screen
                # objects" NO-DATA on this pass's own first real run.
                page.wait_for_function(
                    "() => window.__hqSceneAudit !== undefined && !!window.__hqScene && !!document.querySelector('canvas') "
                    "&& (() => { let found = false; window.__hqScene.traverse((o) => { "
                    "if (o.userData && o.userData.hqKind === 'furniture') found = true; }); return found; })()",
                    timeout=scene_wait_ms,
                )
            except Exception as exc:  # noqa: BLE001
                scene_ready = False
                diag["scene_ready_wait_error"] = str(exc)
            diag["scene_ready"] = scene_ready

            plausibility = compute_plausibility_verdicts(page, seconds, scene_ready)

            _close_quietly(context)
            _close_quietly(browser)
            context = None
            browser = None
    finally:
        _close_quietly(context)
        _close_quietly(browser)

    print_plausibility_lines(plausibility)
    report = {
        "run_started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "plausibility_only": True,
        "url": url,
        "requested_seconds": seconds,
        "environment": {"headless": True, **diag},
        "plausibility": plausibility,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    any_fail = any(v.get("verdict") == "FAIL" for v in plausibility.values())
    return 1 if any_fail else 0


def check_build_stable(min_age_s: float = DEFAULT_MIN_BUILD_AGE_S) -> Optional[str]:
    """Returns None if the build looks stable enough to probe against, else
    the reason string a caller should print + exit 3 on. Two guards, same
    logic setup/scripts/run-dashboard-keepalive.ps1's own stale-build guard
    uses: a fresh .build.lock means a builder actively owns this exact
    build/restart transition (racing them here would fight, not help), and
    a just-written BUILD_ID may still be mid-settle (server process hasn't
    necessarily restarted onto it yet)."""
    if BUILD_LOCK_PATH.exists():
        return f"dashboard/.build.lock exists at {BUILD_LOCK_PATH} -- another builder owns this build/restart cycle"
    if not BUILD_ID_PATH.exists():
        return f"no build found -- {BUILD_ID_PATH} does not exist (run 'npm run build' first)"
    age_s = time.time() - BUILD_ID_PATH.stat().st_mtime
    if age_s < min_age_s:
        return f"BUILD_ID is {age_s:.1f}s old (< {min_age_s:.0f}s minimum) -- deploy still settling"
    return None


def wait_for_stable_build(max_wait_s: float, min_age_s: float, poll_s: float = 5.0) -> Optional[str]:
    """Polls check_build_stable up to max_wait_s. Returns None once stable,
    else the LAST reason seen (caller exits 3). max_wait_s=0 (default) means
    a single check, no polling."""
    reason = check_build_stable(min_age_s)
    if not reason:
        return None
    deadline = time.time() + max_wait_s
    while reason and time.time() < deadline:
        time.sleep(poll_s)
        reason = check_build_stable(min_age_s)
    return reason


def _safe_build_id_for_filename(build_id: Optional[str]) -> str:
    if not build_id:
        return "unknown"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(build_id))[:64]


def samples_gz_path_for_run(run_started_utc_fs_safe: str, build_id: Optional[str], runs_dir: Path = SAMPLE_RUNS_DIR) -> Path:
    return runs_dir / f"{run_started_utc_fs_safe}-{_safe_build_id_for_filename(build_id)}.samples.json.gz"


def write_samples_gz(
    path: Path,
    run_started_utc: str,
    url: str,
    diag: Dict[str, Any],
    samples: List[Dict[str, Any]],
    frame_timestamps_ms: List[float],
    build_ids: List[Optional[str]],
) -> None:
    """Writes the RAW per-tick data every check_* function in hq_probe_lib
    consumes -- everything build_verdicts needs to be re-run later against a
    changed verdict function, without re-launching a browser. This is the gap
    hq-probe-latest.json alone leaves: that file keeps only the AGGREGATED
    verdict, so when 3d7681b4 changed check_walk_out's grace-window logic,
    the previous run's raw walk_out samples were gone and it could not be
    re-scored -- only re-run live."""
    payload = {
        "run_started_utc": run_started_utc,
        "url": url,
        "environment": diag,
        "samples": samples,
        "frame_timestamps_ms": frame_timestamps_ms,
        "build_ids": build_ids,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload).encode("utf-8")
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp_path, "wb") as f:
        f.write(data)
    tmp_path.replace(path)


def load_samples_gz(path: Path) -> Dict[str, Any]:
    with gzip.open(path, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def enforce_samples_retention(runs_dir: Path = SAMPLE_RUNS_DIR, keep: int = SAMPLE_RUNS_RETENTION_KEEP) -> List[Path]:
    """Deletes all but the newest `keep` *.samples.json.gz files (by mtime).
    Returns the paths deleted (empty list if within the cap or dir absent)."""
    if not runs_dir.exists():
        return []
    files = sorted(runs_dir.glob("*.samples.json.gz"), key=lambda p: p.stat().st_mtime)
    excess = len(files) - keep
    if excess <= 0:
        return []
    deleted: List[Path] = []
    for f in files[:excess]:
        try:
            f.unlink()
            deleted.append(f)
        except OSError:
            pass
    return deleted


def rescore(
    samples_path: Path,
    page_refresh_ms: Optional[int] = None,
    walk_speed: float = WALK_SPEED_DEFAULT,
    walk_speed_tol: float = WALK_SPEED_TOL_DEFAULT,
    speed_window_s: float = SPEED_WINDOW_S_DEFAULT,
) -> int:
    """Loads a previously written *.samples.json.gz and re-runs build_verdicts
    with the CURRENT verdict logic (never the logic that was live when the
    samples were captured). Never launches a browser / imports playwright --
    that import only happens inside launch_and_probe, which this path never
    calls."""
    payload = load_samples_gz(samples_path)
    diag = payload.get("environment", {}) or {}
    samples = payload.get("samples", [])
    # Single source of truth (see perf_headless_flag docstring): derived from
    # the recorded gl_is_hardware field, NEVER from diag's own 'headless'
    # literal (always True -- Playwright always launches headless=True, an
    # unrelated "no visible window" fact). This is the same call
    # write_partial/main() make on the live path -- one rule, two callers.
    headless, gl_backend_reason = perf_headless_flag(diag)
    verdicts = build_verdicts(
        samples,
        payload.get("frame_timestamps_ms", []),
        calls_samples=[s.get("calls") for s in samples],
        scene_ready=diag.get("scene_ready", False),
        build_ids=payload.get("build_ids", []),
        headless=headless,
        url=payload.get("url"),
        page_refresh_ms=page_refresh_ms,
        walk_speed=walk_speed,
        walk_speed_tol=walk_speed_tol,
        speed_window_s=speed_window_s,
    )
    report = {
        "rescored": True,
        "rescored_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_file": str(samples_path),
        "run_started_utc": payload.get("run_started_utc"),
        "url": payload.get("url"),
        "sample_count": len(samples),
        # Carries gl_is_hardware/gl_renderer/gl_backend forward from the
        # samples file so a reader never sees environment.gl_is_hardware as
        # a bare None just because rescore omitted the block entirely.
        "environment": diag,
        "gl_backend_recorded": gl_backend_reason is None,
        "verdicts": verdicts,
    }
    print(json.dumps(report, indent=2))
    return 0 if verdicts.get("run_valid", True) else 2


def _close_quietly(obj: Any) -> None:
    if obj is None:
        return
    try:
        obj.close()
    except Exception:  # noqa: BLE001
        pass


def launch_and_probe(
    url: str,
    seconds: int,
    interval_ms: int,
    out_path: Path,
    scene_wait_ms: int,
    page_refresh_ms: Optional[int] = None,
) -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright

    samples: List[Dict[str, Any]] = []
    diag: Dict[str, Any] = {}
    build_ids: List[Optional[str]] = []
    frame_timestamps_ms: List[float] = []
    now_struct = time.gmtime()
    run_started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", now_struct)
    run_started_fs_safe = time.strftime("%Y%m%dT%H%M%SZ", now_struct)
    samples_gz_state: Dict[str, Optional[Path]] = {"path": None}

    def write_partial(reason: str) -> None:
        try:
            verdicts = build_verdicts(
                samples,
                frame_timestamps_ms,
                calls_samples=[s.get("calls") for s in samples],
                scene_ready=diag.get("scene_ready", False),
                build_ids=build_ids,
                headless=perf_headless_flag(diag)[0],
                url=url,
                page_refresh_ms=page_refresh_ms,
            )
            report = {
                "run_started_utc": run_started_utc,
                "partial": True,
                "partial_reason": reason,
                "url": url,
                "sample_count": len(samples),
                "environment": {
                    "headless": True,
                    **diag,
                },
                "verdicts": verdicts,
            }
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001
            # Checkpoint failures must never crash the run they're protecting.
            pass

        # Raw per-tick samples, so a later verdict-logic change can be
        # re-scored against THIS run without a browser (see write_samples_gz
        # docstring). Isolated in its own try -- a gz-write hiccup must not
        # take down the aggregated checkpoint above.
        try:
            if samples_gz_state["path"] is None:
                samples_gz_state["path"] = samples_gz_path_for_run(
                    run_started_fs_safe, diag.get("build_id_start")
                )
            write_samples_gz(
                samples_gz_state["path"],
                run_started_utc,
                url,
                {
                    "headless": True,
                    **diag,
                },
                samples,
                frame_timestamps_ms,
                build_ids,
            )
            enforce_samples_retention()
        except Exception:  # noqa: BLE001
            pass

    # Best-effort last-gasp checkpoint. NOTE (verify-don't-claim): this
    # covers a clean Python exit (return, uncaught exception, KeyboardInterrupt)
    # but CANNOT run after an external forceful kill -- Windows
    # Stop-Process/TerminateProcess (what _shared.ps1's reaper uses) gives no
    # unwind, so no atexit/finally/signal handler fires. The 30s periodic
    # checkpoint below is the real defense against that case; this is only
    # the belt for every other exit path.
    def _atexit_partial() -> None:
        write_partial("process exiting (atexit)")

    atexit.register(_atexit_partial)

    browser = None
    context = None
    try:
        with sync_playwright() as pw:
            # Try hardware GL first (this box has an NVIDIA RTX 5080).
            # Verify via UNMASKED_RENDERER on a throwaway blank-page canvas
            # BEFORE navigating to the real app -- if it doesn't report
            # NVIDIA, tear down and relaunch with SwiftShader rather than
            # silently sampling perf off a software rasterizer.
            gl_renderer: Optional[str] = None
            gl_is_hardware = False
            gl_fallback_reason: Optional[str] = None
            try:
                browser = pw.chromium.launch(headless=True, args=HARDWARE_GL_ARGS)
                context = browser.new_context(viewport={"width": 1600, "height": 900})
                page = context.new_page()
                gl_renderer = page.evaluate(GL_RENDERER_SCRIPT)
                gl_is_hardware = bool(gl_renderer) and "nvidia" in gl_renderer.lower()
            except Exception as exc:  # noqa: BLE001
                gl_fallback_reason = f"hardware GL launch raised {exc!r}"
                gl_is_hardware = False

            if not gl_is_hardware:
                if gl_fallback_reason is None:
                    gl_fallback_reason = (
                        f"hardware GL probe did not report an NVIDIA renderer "
                        f"(got {gl_renderer!r}) -- falling back to SwiftShader"
                    )
                _close_quietly(context)
                _close_quietly(browser)
                browser = pw.chromium.launch(headless=True, args=SOFTWARE_GL_ARGS)
                context = browser.new_context(viewport={"width": 1600, "height": 900})
                page = context.new_page()
                gl_renderer = page.evaluate(GL_RENDERER_SCRIPT)

            diag["gl_renderer"] = gl_renderer
            diag["gl_is_hardware"] = gl_is_hardware
            diag["gl_backend"] = (
                "hardware (ANGLE/D3D11, NVIDIA)" if gl_is_hardware
                else "swiftshader (software) -- NOT the real GPU"
            )
            if gl_fallback_reason:
                diag["gl_fallback_reason"] = gl_fallback_reason

            page.add_init_script(RAF_HOOK_SCRIPT)

            console_errors: List[str] = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

            t0 = time.time()
            page.goto(url, wait_until="load", timeout=60000)

            # WebGL2 sanity: verify a real WebGL2 context is actually creatable
            # in this headless page, independent of whether the app itself
            # managed to use it.
            webgl2_ok = page.evaluate(
                "() => { const c = document.createElement('canvas'); "
                "const gl = c.getContext('webgl2'); return !!gl; }"
            )
            diag["webgl2_context_creatable"] = webgl2_ok

            start_build_id = page.evaluate(FETCH_BUILD_ID_SCRIPT)
            diag["build_id_start"] = start_build_id
            build_ids.append(start_build_id)
            write_partial("preflight")

            # Readiness signal, hardened: window.__hqLiveAgents existing is
            # proof the ultra-tier r3f Canvas mounted, but the INVALID run
            # showed that alone isn't enough -- a page mid-ChunkLoadError can
            # still eval that check true against a stale bundle. Now ALSO
            # requires a real <canvas> element on the page AND that
            # StandbyPanel's "Standby" text is NOT showing (paused/gaming/
            # hidden state, or a page that rendered nothing at all).
            scene_ready = True
            try:
                page.wait_for_function(
                    "() => window.__hqLiveAgents !== undefined "
                    "&& !!document.querySelector('canvas') "
                    "&& !(document.body.innerText || '').includes('Standby')",
                    timeout=scene_wait_ms,
                )
            except Exception as exc:  # noqa: BLE001
                scene_ready = False
                diag["scene_ready_wait_error"] = str(exc)
            diag["scene_ready"] = scene_ready
            diag["hq_gl_exposed"] = page.evaluate("() => !!window.__hqGl")
            if not diag["hq_gl_exposed"]:
                diag["hq_gl_note"] = (
                    "window.__hqGl is not set. Was previously true on tier=ultra "
                    "unconditionally (UltraCanvasRoot.tsx's onCreated never called "
                    "hq-motion-diag.ts#exposeSceneForDiag) -- fixed alongside this "
                    "probe hardening pass by wiring it in behind the same ?diag=1 "
                    "gate CanvasRoot.tsx's TV tier already used. If this is still "
                    "false, either ?diag=1 is missing from the URL or the app fix "
                    "did not land."
                )

            diag["document_hidden_at_start"] = page.evaluate("() => document.hidden")
            diag["mode_at_start"] = page.evaluate(
                "async () => { try { const r = await fetch('/api/hq'); const j = await r.json(); "
                "return j.mode ?? null; } catch (e) { return null; } }"
            )
            write_partial("post-readiness-gate")

            # Let the scene settle a moment before sampling begins.
            page.wait_for_timeout(1000)

            n_ticks = max(1, int((seconds * 1000) / interval_ms))
            last_partial_write = time.time()
            for _ in range(n_ticks):
                tick_t0 = time.time()
                try:
                    result = page.evaluate(SAMPLE_SCRIPT)
                except Exception as exc:  # noqa: BLE001
                    result = {
                        "pageAgents": [], "apiAgents": [], "apiError": str(exc), "calls": None,
                        "buildId": None, "labelRects": [], "paused": None,
                    }
                bid = result.get("buildId")
                build_ids.append(bid)
                host_t_ms = (time.time() - t0) * 1000.0
                samples.append({
                    # NOTE: 't_ms' stays host wall-clock (time since run
                    # start) -- every OTHER check (spawn_latency, walk_out,
                    # page_api_parity) keys thresholds off it and is out of
                    # scope for this pass. 'page_t_ms' (in-page
                    # performance.now(), same evaluate() call as
                    # pageAgents) is the new field check_walk_speed prefers
                    # -- see hq_probe_lib._resolved_t_ms. 'host_t_ms' is
                    # 't_ms' by another name, kept explicit for diagnostics.
                    "t_ms": host_t_ms,
                    "host_t_ms": host_t_ms,
                    "page_t_ms": result.get("pageTMs"),
                    "page_agents": result.get("pageAgents") or [],
                    "api_agents": result.get("apiAgents") or [],
                    "calls": result.get("calls"),
                    "document_hidden": result.get("documentHidden"),
                    "api_error": result.get("apiError"),
                    # PROBE-16: mirrors UltraCanvasRoot.tsx's own `paused`
                    # boolean -- see SAMPLE_SCRIPT's own comment. None
                    # (not False) on any samples file captured before this
                    # field existed, or on a tick where the /api/hq fetch
                    # itself failed -- check_walk_speed's frame-timestamp
                    # pause signal (_paused_frame_gaps) is what still works
                    # on those.
                    "paused": result.get("paused"),
                    # PROBE-11: '.hq-beam' rects captured the SAME
                    # evaluate() call as pageAgents -- see SAMPLE_SCRIPT's
                    # own comment for the DOM-hook and opacity caveats.
                    # Absent (None/[]) on any samples file captured before
                    # this field existed -- check_label_overlap reports
                    # NO-DATA in that case, never a false PASS/FAIL.
                    "label_rects": result.get("labelRects") or [],
                })

                if time.time() - last_partial_write >= PARTIAL_WRITE_INTERVAL_S:
                    last_partial_write = time.time()
                    write_partial("30s checkpoint")

                elapsed = time.time() - tick_t0
                sleep_s = max(0.0, (interval_ms / 1000.0) - elapsed)
                time.sleep(sleep_s)

            frame_timestamps_ms = page.evaluate("() => window.__probeRaf || []")
            diag["console_error_count"] = len(console_errors)
            diag["console_errors_sample"] = console_errors[:10]

            end_build_id = page.evaluate(FETCH_BUILD_ID_SCRIPT)
            diag["build_id_end"] = end_build_id
            build_ids.append(end_build_id)

            # SCENE-AUDIT pass (2026-09-15): the "would a human accept this
            # room" check family (see this module's own docstring), riding
            # along on this ALREADY-OPEN page rather than a second browser
            # launch. Capped at 30s regardless of --seconds -- the static
            # checks (wall/screen/desk) only need one snapshot, and 30s of
            # walker-position sampling at 4x/s is plenty to catch a real
            # wall-crossing without meaningfully extending a 200s run.
            # Wrapped so a failure here NEVER takes down the primary run
            # this function exists to protect (same "checkpoint failures
            # must never crash the run" discipline write_partial already
            # uses above).
            try:
                diag["plausibility"] = compute_plausibility_verdicts(page, min(30.0, float(seconds)), diag.get("scene_ready", False))
            except Exception as exc:  # noqa: BLE001
                diag["plausibility"] = {"error": f"compute_plausibility_verdicts threw: {exc!r}"}

            # Final raw-sample write with the complete frame_timestamps_ms +
            # end build_id -- the 30s periodic checkpoints above may have
            # missed the last <30s of ticks.
            write_partial("final capture")

            _close_quietly(context)
            _close_quietly(browser)
            context = None
            browser = None

        return {
            "samples": samples,
            "frame_timestamps_ms": frame_timestamps_ms,
            "diag": diag,
            "build_ids": build_ids,
            # Captured ONCE at the top of this function and reused for both
            # the samples.json.gz filename stamp and the final report below
            # -- previously main() re-stamped its own run_started_utc AFTER
            # the run finished (a 2026-09-15 bookkeeping bug: the filename
            # said 06:46:29Z, the JSON said 06:50:37Z, 4+ minutes apart for
            # the SAME run).
            "run_started_utc": run_started_utc,
        }
    finally:
        # Every exit path -- normal return, exception, KeyboardInterrupt --
        # lands here. See the atexit note above for what this can't cover.
        _close_quietly(context)
        _close_quietly(browser)
        atexit.unregister(_atexit_partial)


def main() -> int:
    # 2026-09-15: a label text containing an emoji (the head-label model
    # glyph, e.g. U+1F3E0) crashed print_plausibility_lines with
    # UnicodeEncodeError under Windows' cp1252 console AFTER the run had
    # already recorded -- the motion check lines were lost (C7: audit the
    # output, not the exit code). Force UTF-8 stdout with replacement so a
    # glyph can never take the verdict lines down with it.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--seconds", type=int, default=200)
    ap.add_argument("--interval-ms", type=int, default=500)
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--scene-wait-ms", type=int, default=DEFAULT_SCENE_WAIT_MS)
    ap.add_argument("--min-build-age-s", type=float, default=DEFAULT_MIN_BUILD_AGE_S)
    ap.add_argument(
        "--page-refresh-ms",
        type=int,
        default=None,
        help=(
            "override the page's real data-refresh cadence spawn_latency judges "
            "against (default: derived from --url's kiosk=1 query param -- "
            "15000 normally, 60000 for kiosk; see dashboard/app/hq/page.tsx:34)"
        ),
    )
    ap.add_argument(
        "--wait-for-stable-build",
        type=float,
        default=0.0,
        help="poll up to N seconds for dashboard/.next/BUILD_ID to settle (no lock, min age met) before refusing (exit 3)",
    )
    ap.add_argument(
        "--walk-speed",
        type=float,
        default=WALK_SPEED_DEFAULT,
        help=(
            "configured design walking speed (u/s) check_walk_speed judges the "
            "steady walking/leaving median against (default: 0.7, from "
            "dashboard/components/hq/KitAgent.tsx:85 WALK_SPEED)"
        ),
    )
    ap.add_argument(
        "--walk-speed-tol",
        type=float,
        default=WALK_SPEED_TOL_DEFAULT,
        help="fractional tolerance around --walk-speed for the median check (default: 0.15 = +/-15%%)",
    )
    ap.add_argument(
        "--speed-window-s",
        type=float,
        default=SPEED_WINDOW_S_DEFAULT,
        help=(
            "check_walk_speed measures speed over windows of at least this "
            "many seconds (averaging out the 250ms diag-publish / ~500ms "
            "probe-sample quantization) instead of per-tick -- default 2.0. "
            "Teleport detection is unaffected (always per-tick, strict)."
        ),
    )
    ap.add_argument(
        "--rescore",
        default=None,
        metavar="PATH",
        help=(
            "re-run build_verdicts against a previously written "
            "*.samples.json.gz file with the CURRENT verdict logic, print "
            "the verdict JSON, and exit -- no browser is launched, no "
            "--url/--seconds/build-stability args apply"
        ),
    )
    ap.add_argument(
        "--plausibility",
        action="store_true",
        help=(
            "run ONLY the 'would a human accept this room' check family "
            "(wall_penetration/walker_wall_cross/screen_facing/"
            "desk_clearance/desk_orientation/label_legibility/"
            "label_vs_screen_overlap -- see this "
            "module's own docstring) in ~60-90s, no full sampling run. A "
            "normal run without this flag still runs the same family, "
            "riding along in environment.plausibility."
        ),
    )
    ap.add_argument(
        "--plausibility-seconds",
        type=float,
        default=PLAUSIBILITY_DEFAULT_SECONDS,
        help="walker-position sampling window for --plausibility's own walker_wall_cross check (default 60s)",
    )
    args = ap.parse_args()

    if args.plausibility:
        return run_plausibility(args.url, args.plausibility_seconds, Path(args.out), args.scene_wait_ms, args.min_build_age_s)

    if args.rescore:
        return rescore(
            Path(args.rescore),
            page_refresh_ms=args.page_refresh_ms,
            walk_speed=args.walk_speed,
            walk_speed_tol=args.walk_speed_tol,
            speed_window_s=args.speed_window_s,
        )

    refuse_reason = wait_for_stable_build(args.wait_for_stable_build, args.min_build_age_s)
    if refuse_reason:
        print(f"REFUSED to start: {refuse_reason}", file=sys.stderr)
        return 3

    out_path = Path(args.out)
    run = launch_and_probe(
        args.url, args.seconds, args.interval_ms, out_path, args.scene_wait_ms,
        page_refresh_ms=args.page_refresh_ms,
    )
    samples = run["samples"]
    frame_ts = run["frame_timestamps_ms"]
    build_ids = run["build_ids"]
    diag = run["diag"]
    scene_ready = diag.get("scene_ready", False)
    calls_samples = [s.get("calls") for s in samples]
    verdicts = build_verdicts(
        samples,
        frame_ts,
        calls_samples=calls_samples,
        scene_ready=scene_ready,
        build_ids=build_ids,
        headless=perf_headless_flag(diag)[0],
        url=args.url,
        page_refresh_ms=args.page_refresh_ms,
        walk_speed=args.walk_speed,
        walk_speed_tol=args.walk_speed_tol,
        speed_window_s=args.speed_window_s,
    )

    report = {
        # Same run_started_utc launch_and_probe stamped its samples.json.gz
        # filename with -- see that function's return dict for why this must
        # not be re-captured here.
        "run_started_utc": run.get("run_started_utc"),
        "partial": False,
        "url": args.url,
        "requested_seconds": args.seconds,
        "interval_ms": args.interval_ms,
        "sample_count": len(samples),
        "frame_count": len(frame_ts),
        "build_id_start": diag.get("build_id_start"),
        "build_id_end": diag.get("build_id_end"),
        "build_id_distinct": sorted({b for b in build_ids if b}),
        "environment": {
            "headless": True,
            **diag,
        },
        "verdicts": verdicts,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    plausibility = diag.get("plausibility")
    if isinstance(plausibility, dict) and "error" not in plausibility:
        print_plausibility_lines(plausibility)

    print(json.dumps(report, indent=2))
    return 0 if verdicts.get("run_valid", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
