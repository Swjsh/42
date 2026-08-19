"""Refresh the book-equity snapshot the exposure ceiling divides by. $0, no LLM, no orders.

WHY THIS EXISTS (2026-08-19). The book-level exposure cap (book_exposure.py, armed
2026-08-18) needs ONE number the engine never had in one place: aggregate equity across all
active arms. I wired `record_arm_equity` into `heartbeat_core._execute` -- which only runs on
an ENTER verdict. On 2026-08-19 the engine ticked 772 times and the cap was DEGRADED for the
entire session, because no arm had refreshed its equity before the first entry attempt. It
failed OPEN, exactly as designed, so nothing was mis-blocked -- but the protection was inert
all day. A guard that only arms itself after the thing it guards has already happened is not
a guard.

WHY NOT JUST FETCH ON EVERY TICK: that is 2 extra REST round-trips per minute per account on
the 1-minute hot path, for a denominator that moves slowly. Aggregate book equity is not a
tick-scale quantity. A periodic refresher is the right shape: cheap, off the hot path, and it
cannot add latency to an entry decision.

STALENESS IS STILL ENFORCED downstream -- book_exposure.EQUITY_STALE_MINUTES rejects readings
older than its window and degrades to fail-open. This script's job is simply to keep the
snapshot inside that window.

Run it premarket and periodically during RTH. Safe to run any time: it only reads /v2/account
and writes one small JSON file.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "setup" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "automation" / "state" / "fleet"))

import book_exposure as bx  # noqa: E402
import et_clock  # noqa: E402


def _creds_for_arms() -> dict:
    """{arm: {key, secret, base_url}} from the gitignored fleet secrets store."""
    try:
        import fleet_broker  # noqa: PLC0415
        return fleet_broker.load_creds()
    except Exception as exc:  # noqa: BLE001
        print(f"[book_equity_refresh] cannot load creds: {exc}", file=sys.stderr)
        return {}


def refresh(state_dir: Path | None = None) -> dict:
    """Record every active arm's live equity. Returns a summary; never raises."""
    state_dir = Path(state_dir) if state_dir else (REPO_ROOT / "automation" / "state")
    now_iso = et_clock.et_now().isoformat()
    creds = _creds_for_arms()
    arms = bx.active_spy_arms()
    out: dict = {"ts_et": now_iso, "recorded": {}, "failed": {}}
    for arm in arms:
        aid = str(arm["arm_id"])
        c = creds.get(aid)
        if not c:
            out["failed"][aid] = "no creds in secrets.json"
            continue
        try:
            req = urllib.request.Request(
                c["base_url"].rstrip("/") + "/v2/account",
                headers={"APCA-API-KEY-ID": c["key"], "APCA-API-SECRET-KEY": c["secret"]})
            data = json.loads(urllib.request.urlopen(req, timeout=15).read())
            equity = float(data["equity"])
        except Exception as exc:  # noqa: BLE001 -- one bad arm must not stop the rest
            out["failed"][aid] = f"{type(exc).__name__}: {str(exc)[:60]}"
            continue
        bx.record_arm_equity(aid, equity, state_dir, now_iso)
        out["recorded"][aid] = round(equity, 2)
    return out


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = refresh()
    if a.json:
        print(json.dumps(res, indent=2))
        return 0
    print(f"BOOK EQUITY REFRESH  {res['ts_et'][:19]} ET")
    total = 0.0
    for arm, eq in res["recorded"].items():
        total += eq
        print(f"   {arm:<10} ${eq:>10,.2f}")
    print(f"   {'BOOK':<10} ${total:>10,.2f}   ({len(res['recorded'])} arm(s))")
    for arm, why in res["failed"].items():
        print(f"   !! {arm}: {why}")
    # Show what the cap now sees -- proving the refresh actually cleared the degrade.
    state = REPO_ROOT / "automation" / "state"
    ev = bx.evaluate_live(state, res["ts_et"])
    if ev.get("degraded"):
        print(f"   cap: STILL DEGRADED -- {ev['degraded']}")
        return 1
    print(f"   cap: OK -- exposure {ev['projected_pct']:.1%} of ${ev['book_equity']:,.0f} "
          f"(ceiling {ev['max_pct']:.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
