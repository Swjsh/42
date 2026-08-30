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
    # Lanes are the third fast slice (2026-08-30). They belong here rather than in the
    # baked payload for the same reason the other two do: a lane's whole job is to say
    # whether it is alive RIGHT NOW, and a liveness answer served from a file written on
    # a schedule is the exact staleness this endpoint exists to remove.
    try:
        import gamma_lanes
        out["lanes"] = gamma_lanes.build()
    except Exception as e:                       # noqa: BLE001
        out["lanes"] = None
        out["lanes_error"] = str(e)[:200]
    # The TRADING slice (2026-08-30). Fourth fast group, same contract as the others:
    # a pure read over files already on disk, 0.7s, and independently failable -- a
    # broken P&L read must not take the agent roster down with it.
    try:
        import gamma_glass
        out["glass"] = gamma_glass.build()
    except Exception as e:                       # noqa: BLE001
        out["glass"] = None
        out["glass_error"] = str(e)[:200]
    # WHICH ACTION CARDS HAVE ALREADY BEEN RUN (2026-08-30).
    #
    # J fired a card, watched it finish, and the card sat there with a live-looking
    # Run button -- so it read as "the agent did nothing". The companion's in-memory
    # task registry knew, but it dies on every restart, so after one the card was
    # "new" again. companion-asks.jsonl records `from_card` durably, which is what
    # makes "ran 12:19" survive a restart. The in-memory registry still supplies HOW
    # it went (status/ok/summary); this supplies THAT it happened.
    try:
        out["card_runs"] = _card_runs()
    except Exception as e:                       # noqa: BLE001
        out["card_runs"] = None
        out["card_runs_error"] = str(e)[:200]
    json.dump(out, sys.stdout, default=str)
    return 0


def _card_runs() -> dict:
    """card_id -> the most recent escalation it spawned, from the durable ledger."""
    import json as _json
    path = REPO / "automation" / "state" / "companion-asks.jsonl"
    out: dict = {}
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()[-400:]
    except OSError:
        return out
    for line in lines:
        try:
            r = _json.loads(line)
        except ValueError:
            continue
        cid = r.get("from_card") or r.get("card_id")
        if cid:
            # later lines win: the map ends up holding the MOST RECENT run per card
            out[str(cid)] = {"id": r.get("id"), "ts": r.get("ts")}
    return out


if __name__ == "__main__":
    raise SystemExit(main())
