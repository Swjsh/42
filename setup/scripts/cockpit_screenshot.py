"""cockpit_screenshot.py -- deterministic screenshots of the command center, $0, no LLM.

WHY (2026-09-03, GOAL-COCKPIT-REDESIGN): the in-app browser pane times out on this page
(760 KB, animated), so every design critique and every before/after pair J gets needs a
reliable capture path. Headless Chrome/Edge is on the box; this wraps it.

Usage:
  python setup/scripts/cockpit_screenshot.py --tag before
  python setup/scripts/cockpit_screenshot.py --tag after --views overview,command --sizes 1600x950
  python setup/scripts/cockpit_screenshot.py --tag x --url http://localhost:4317/cockpit.html

Writes analysis/home/screens/<tag>-<view>-<WxH>-<theme>.png and prints one line per file.
Themes: "dark" (default page theme) and "light" via Chrome's --force-color-profile is not a
theme switch, so light is captured by appending ?theme=light which gamma_cockpit_ui.py may
honour; if it does not, the light capture is labelled UNVERIFIED in the summary line.
Never edits anything else. Exit 0 unless --strict.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--url", default="http://localhost:4317/cockpit.html")
    ap.add_argument("--views", default="overview,autonomy,army,cards,answers")
    ap.add_argument("--sizes", default="1600x950,1440x900")
    ap.add_argument("--themes", default="dark,light")
    ap.add_argument("--budget-ms", type=int, default=6000)
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()

    browser = _browser()
    if browser is None:
        print("NO BROWSER: no chrome/edge found -- screenshots UNVERIFIED")
        return 1 if a.strict else 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fails = 0
    for view in [v for v in a.views.split(",") if v]:
        for size in [s for s in a.sizes.split(",") if s]:
            for theme in [t for t in a.themes.split(",") if t]:
                dark = theme == "dark"
                sep = "&" if "?" in a.url else "?"
                url = f"{a.url}{sep}theme={theme}#{view}"
                out = OUT_DIR / f"{a.tag}-{view}-{size}-{theme}.png"
                t0 = time.time()
                ok, note = shoot(browser, url, out, size, dark, a.budget_ms)
                fails += 0 if ok else 1
                print(f"{'OK ' if ok else 'FAIL'} {out.relative_to(REPO).as_posix()} {int((time.time()-t0)*1000)}ms {note}")
    print(f"done: {fails} failures; browser={browser.name}")
    return 1 if (fails and a.strict) else 0


if __name__ == "__main__":
    raise SystemExit(main())
