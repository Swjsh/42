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
from hq_probe_lib import build_verdicts  # noqa: E402

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
  try {
    const r = await fetch('/api/hq', { cache: 'no-store' });
    const j = await r.json();
    apiAgents = j.liveAgents || [];
    apiError = j.liveAgentsError || null;
    buildId = j.build_id || null;
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
  return {
    pageAgents,
    apiAgents: apiAgents.map((a) => ({ id: a.id, state: a.state })),
    apiError,
    calls,
    buildId,
    documentHidden: document.hidden,
  };
}
"""


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


def rescore(samples_path: Path) -> int:
    """Loads a previously written *.samples.json.gz and re-runs build_verdicts
    with the CURRENT verdict logic (never the logic that was live when the
    samples were captured). Never launches a browser / imports playwright --
    that import only happens inside launch_and_probe, which this path never
    calls."""
    payload = load_samples_gz(samples_path)
    diag = payload.get("environment", {}) or {}
    samples = payload.get("samples", [])
    verdicts = build_verdicts(
        samples,
        payload.get("frame_timestamps_ms", []),
        calls_samples=[s.get("calls") for s in samples],
        scene_ready=diag.get("scene_ready", False),
        build_ids=payload.get("build_ids", []),
        headless=diag.get("headless", True),
    )
    report = {
        "rescored": True,
        "rescored_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_file": str(samples_path),
        "run_started_utc": payload.get("run_started_utc"),
        "url": payload.get("url"),
        "sample_count": len(samples),
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
                headless=not diag.get("gl_is_hardware", False),
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
                    result = {"pageAgents": [], "apiAgents": [], "apiError": str(exc), "calls": None, "buildId": None}
                bid = result.get("buildId")
                build_ids.append(bid)
                samples.append({
                    "t_ms": (time.time() - t0) * 1000.0,
                    "page_agents": result.get("pageAgents") or [],
                    "api_agents": result.get("apiAgents") or [],
                    "calls": result.get("calls"),
                    "document_hidden": result.get("documentHidden"),
                    "api_error": result.get("apiError"),
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
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--seconds", type=int, default=200)
    ap.add_argument("--interval-ms", type=int, default=500)
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--scene-wait-ms", type=int, default=DEFAULT_SCENE_WAIT_MS)
    ap.add_argument("--min-build-age-s", type=float, default=DEFAULT_MIN_BUILD_AGE_S)
    ap.add_argument(
        "--wait-for-stable-build",
        type=float,
        default=0.0,
        help="poll up to N seconds for dashboard/.next/BUILD_ID to settle (no lock, min age met) before refusing (exit 3)",
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
    args = ap.parse_args()

    if args.rescore:
        return rescore(Path(args.rescore))

    refuse_reason = wait_for_stable_build(args.wait_for_stable_build, args.min_build_age_s)
    if refuse_reason:
        print(f"REFUSED to start: {refuse_reason}", file=sys.stderr)
        return 3

    out_path = Path(args.out)
    run = launch_and_probe(args.url, args.seconds, args.interval_ms, out_path, args.scene_wait_ms)
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
        headless=not diag.get("gl_is_hardware", False),
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

    print(json.dumps(report, indent=2))
    return 0 if verdicts.get("run_valid", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
