"""cockpit_shot.py -- give Claude eyes on the cockpit.

WHY (2026-08-29): J asked for a real design pass and said "do what you need to do to open it
and take screenshots or find a tool online that give claude eyes to see it". The in-app
Browser pane cannot composite frames unless the pane is actually displayed, so every
screenshot attempt timed out while he was away, and design work was reduced to measuring the
DOM and guessing. Headless Chrome needs no pane, no npm install, and no extension: Chrome
ships a --screenshot flag.

Usage:
    python setup/scripts/cockpit_shot.py                  # army view, 1920x1400
    python setup/scripts/cockpit_shot.py --view cards
    python setup/scripts/cockpit_shot.py --width 1440 --height 900 --name before
    python setup/scripts/cockpit_shot.py --file            # shoot the file:// copy instead

Writes analysis/home/_shots/<name>.png and prints the path so it can be Read straight back.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

# Windows spawns a console window for every child process unless told not to -- and a
# console that appears while J is gaming steals focus mid-match (2026-08-29 incident).
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_REPO = Path(__file__).resolve().parent.parent.parent
_SHOTS = _REPO / "analysis" / "home" / "_shots"

# Edge is the fallback because it is the same Chromium engine; the page targets Chromium only.
_BROWSERS = (
    Path(r"C:/Program Files/Google/Chrome/Application/chrome.exe"),
    Path(r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
    Path(r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
)


def find_browser() -> Path | None:
    for candidate in _BROWSERS:
        if candidate.is_file():
            return candidate
    return None


def shoot(url: str, out: Path, width: int, height: int, wait_ms: int) -> bool:
    browser = find_browser()
    if browser is None:
        print("no Chromium browser found; looked in:", *[str(b) for b in _BROWSERS], sep="\n  ")
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()  # so a failed run cannot silently return the previous image
    cmd = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        # virtual-time-budget lets the page finish its own JS render + first poll before the
        # frame is captured; without it the shot lands on an empty #view.
        f"--virtual-time-budget={wait_ms}",
        f"--window-size={width},{height}",
        f"--screenshot={out}",
        url,
    ]
    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                          creationflags=_CREATE_NO_WINDOW)
    if not out.is_file():
        print("screenshot failed rc=%s" % proc.returncode)
        print((proc.stderr or proc.stdout or "")[-800:])
        return False
    print(f"{out}  ({out.stat().st_size // 1024} KB, {time.time() - started:.1f}s)")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Screenshot the Gamma cockpit headlessly.")
    ap.add_argument("--view", default="army", help="cockpit view id (army, cards, overview, ...)")
    ap.add_argument("--name", default=None, help="output filename stem (default: the view id)")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1400)
    ap.add_argument("--wait", type=int, default=6000, help="virtual time budget in ms")
    ap.add_argument("--file", action="store_true", help="shoot the file:// copy, not the served one")
    args = ap.parse_args()

    if args.file:
        url = (_REPO / "analysis" / "home" / "index.html").as_uri() + "#" + args.view
    else:
        # Cache-bust: Chrome will happily serve a stale copy and the shot then shows the
        # PREVIOUS design, which is the worst possible failure for a visual iteration loop.
        url = f"http://127.0.0.1:4317/cockpit.html?shot={int(time.time())}#{args.view}"

    out = _SHOTS / f"{args.name or args.view}.png"
    return 0 if shoot(url, out, args.width, args.height, args.wait) else 1


if __name__ == "__main__":
    raise SystemExit(main())
