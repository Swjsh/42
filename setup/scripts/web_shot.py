"""web_shot.py -- headless screenshot of ANY url, so Claude can look at a reference design.

WHY (2026-08-30): J, on being shown research summaries instead of designs -- "why are you
not actually crawling the 21st dev sight and looking at things". The in-app Browser pane
cannot composite frames unless the pane is displayed, so every screenshot of an external
page timed out while he was away. cockpit_shot.py already solved this for the local
cockpit with headless Chrome; this is the same trick pointed at the open web, so a
reference component can be LOOKED AT rather than read about second-hand.

Usage:
    python setup/scripts/web_shot.py <url> --name jelly-hero
    python setup/scripts/web_shot.py <url> --name x --width 1440 --height 2400 --wait 12000

Writes analysis/home/_shots/web/<name>.png and prints the path.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
_REPO = Path(__file__).resolve().parent.parent.parent
_SHOTS = _REPO / "analysis" / "home" / "_shots" / "web"

_BROWSERS = (
    Path(r"C:/Program Files/Google/Chrome/Application/chrome.exe"),
    Path(r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
    Path(r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
)


def find_browser() -> Path | None:
    return next((b for b in _BROWSERS if b.is_file()), None)


def shoot(url: str, out: Path, width: int, height: int, wait_ms: int) -> bool:
    browser = find_browser()
    if browser is None:
        print("no Chromium browser found")
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()  # a failed run must never silently return the previous image
    cmd = [
        str(browser), "--headless=new", "--disable-gpu", "--hide-scrollbars",
        # These pages are React apps that fetch their own preview; they need real time,
        # not just a virtual-time budget, before anything is painted.
        f"--virtual-time-budget={wait_ms}",
        f"--window-size={width},{height}",
        f"--screenshot={out}", url,
    ]
    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                          creationflags=_CREATE_NO_WINDOW)
    if not out.is_file():
        print(f"screenshot failed rc={proc.returncode}")
        print((proc.stderr or proc.stdout or "")[-600:])
        return False
    print(f"{out}  ({out.stat().st_size // 1024} KB, {time.time() - started:.1f}s)")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Headlessly screenshot any URL.")
    ap.add_argument("url")
    ap.add_argument("--name", required=True)
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=1200)
    ap.add_argument("--wait", type=int, default=12000)
    args = ap.parse_args()
    ok = shoot(args.url, _SHOTS / f"{args.name}.png", args.width, args.height, args.wait)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
