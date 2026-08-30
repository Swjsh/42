"""desk_live.py -- the two slices of the desk that must be CURRENT, on demand.

WHY (2026-08-30): the app polls payload.json every 30s, but payload.json is only
rewritten when gamma_home.py runs on its schedule -- and that task is disabled during
quiet hours. Measured mid-morning: the file was 32 minutes old while the page polled
it twice a minute. So the page FELT live and the roster underneath could be half an
hour behind, which is the worst combination: a stale number presented with a live
cadence.

The rest of the payload (calendar, desks, cards, answers) is genuinely slow to build
and genuinely slow-moving, so it stays on the scheduled path. Only the two slices that
change minute to minute are served fresh here:

    build_army()      0.24s   who is running, which agents, how full their context is
    gamma_autonomy    0.27s   awake or resting, the governor, what it did on its own

Both are pure reads over files already on disk. Nothing here decides or fires.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))


def main() -> int:
    out: dict = {}
    # Each slice is independent: one failing must not take the other down, because a
    # half-fresh desk still beats a whole stale one.
    try:
        from gamma_cockpit_army import build_army
        out["army"] = build_army()
    except Exception as e:                       # noqa: BLE001
        out["army"] = None
        out["army_error"] = str(e)[:200]
    try:
        import gamma_autonomy
        out["autonomy"] = gamma_autonomy.build()
    except Exception as e:                       # noqa: BLE001
        out["autonomy"] = None
        out["autonomy_error"] = str(e)[:200]
    json.dump(out, sys.stdout, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
