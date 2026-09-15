"""HQ live-agent measurement instrument (coordinator cannot see the HQ world
today: the Claude Browser pane is hidden -> UltraCanvasRoot.tsx's `paused =
gaming || document.hidden` stops rendering there, and hq_capture.ps1 only
gives a single PNG from a visible Edge window). This launches a HEADLESS
Chromium via Playwright, drives the real /hq page with ?diag=1&tier=ultra,
and samples window.__hqLiveAgents + /api/hq's liveAgents + renderer stats
over time, then runs them through hq_probe_lib.py's pure verdict logic.

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
    python setup/scripts/hq_live_probe.py --seconds 240
    python setup/scripts/hq_live_probe.py --seconds 5 --smoke   # quick check

Output: JSON to stdout AND automation/state/station/hq-probe-latest.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hq_probe_lib import build_verdicts  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "automation" / "state" / "station" / "hq-probe-latest.json"

DEFAULT_URL = "http://127.0.0.1:3000/hq?diag=1&tier=ultra"

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

SAMPLE_SCRIPT = """
async () => {
  let apiAgents = [];
  let apiError = null;
  try {
    const r = await fetch('/api/hq', { cache: 'no-store' });
    const j = await r.json();
    apiAgents = j.liveAgents || [];
    apiError = j.liveAgentsError || null;
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
    documentHidden: document.hidden,
  };
}
"""


def launch_and_probe(url: str, seconds: int, interval_ms: int) -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright

    samples: List[Dict[str, Any]] = []
    diag: Dict[str, Any] = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--use-gl=angle",
                "--use-angle=swiftshader",
                "--enable-webgl",
                "--enable-webgl2",
                "--ignore-gpu-blocklist",
                "--enable-unsafe-swiftshader",
                "--disable-gpu-sandbox",
                "--no-sandbox",
            ],
        )
        context = browser.new_context(viewport={"width": 1600, "height": 900})
        page = context.new_page()
        page.add_init_script(RAF_HOOK_SCRIPT)

        console_errors: List[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        t0 = time.time()
        page.goto(url, wait_until="load", timeout=60000)

        # WebGL2 sanity: verify a real WebGL2 context is actually creatable
        # in this headless page (the swiftshader-flags concern from the
        # task brief), independent of whether the app itself managed to use it.
        webgl2_ok = page.evaluate(
            "() => { const c = document.createElement('canvas'); "
            "const gl = c.getContext('webgl2'); return !!gl; }"
        )
        diag["webgl2_context_creatable"] = webgl2_ok

        # Readiness signal: window.__hqLiveAgents (set by LiveAgents.tsx's
        # ensureDiagInterval, ~250ms after that component mounts) is proof
        # the ultra-tier r3f Canvas actually mounted and is rendering, not
        # just that the HTML shell loaded. Primary because it is reliably
        # wired for tier=ultra; window.__hqGl (hq-motion-diag.ts's
        # exposeSceneForDiag) is checked too but is NOT actually called from
        # UltraCanvasRoot.tsx's onCreated (verified by reading that file --
        # only CanvasRoot.tsx's TV tier appears to wire it) despite the
        # module's own doc comment saying every CanvasRoot should call it.
        # FINDING, not a probe bug: draw-call sampling below will read
        # `calls: null` on tier=ultra for this reason -- flagged in the
        # perf verdict's own detail rather than silently degrading.
        scene_ready = True
        try:
            page.wait_for_function("() => window.__hqLiveAgents !== undefined", timeout=15000)
        except Exception as exc:  # noqa: BLE001
            scene_ready = False
            diag["scene_ready_wait_error"] = str(exc)
        diag["scene_ready"] = scene_ready
        diag["hq_gl_exposed"] = page.evaluate("() => !!window.__hqGl")
        if not diag["hq_gl_exposed"]:
            diag["hq_gl_note"] = (
                "window.__hqGl is never set on tier=ultra -- UltraCanvasRoot.tsx's "
                "onCreated does not call hq-motion-diag.ts#exposeSceneForDiag "
                "(CanvasRoot.tsx's TV tier does). draw-call sampling is NO-DATA "
                "for this reason, not a probe defect. App code not touched (read-only)."
            )

        diag["document_hidden_at_start"] = page.evaluate("() => document.hidden")
        diag["mode_at_start"] = page.evaluate(
            "async () => { try { const r = await fetch('/api/hq'); const j = await r.json(); "
            "return j.mode ?? null; } catch (e) { return null; } }"
        )

        # Let the scene settle a moment before sampling begins.
        page.wait_for_timeout(1000)

        n_ticks = max(1, int((seconds * 1000) / interval_ms))
        for _ in range(n_ticks):
            tick_t0 = time.time()
            try:
                result = page.evaluate(SAMPLE_SCRIPT)
            except Exception as exc:  # noqa: BLE001
                result = {"pageAgents": [], "apiAgents": [], "apiError": str(exc), "calls": None}
            samples.append({
                "t_ms": (time.time() - t0) * 1000.0,
                "page_agents": result.get("pageAgents") or [],
                "api_agents": result.get("apiAgents") or [],
                "calls": result.get("calls"),
                "document_hidden": result.get("documentHidden"),
                "api_error": result.get("apiError"),
            })
            elapsed = time.time() - tick_t0
            sleep_s = max(0.0, (interval_ms / 1000.0) - elapsed)
            time.sleep(sleep_s)

        frame_timestamps_ms = page.evaluate("() => window.__probeRaf || []")
        diag["console_error_count"] = len(console_errors)
        diag["console_errors_sample"] = console_errors[:10]

        context.close()
        browser.close()

    return {"samples": samples, "frame_timestamps_ms": frame_timestamps_ms, "diag": diag}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--seconds", type=int, default=240)
    ap.add_argument("--interval-ms", type=int, default=500)
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    run = launch_and_probe(args.url, args.seconds, args.interval_ms)
    samples = run["samples"]
    frame_ts = run["frame_timestamps_ms"]
    verdicts = build_verdicts(samples, frame_ts)

    report = {
        "run_started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "url": args.url,
        "requested_seconds": args.seconds,
        "interval_ms": args.interval_ms,
        "sample_count": len(samples),
        "frame_count": len(frame_ts),
        "environment": {
            "headless": True,
            "gl_backend": "swiftshader (software) -- NOT the real GPU",
            **run["diag"],
        },
        "verdicts": verdicts,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
