#!/usr/bin/env python
"""vix_bull_hard_cap_unblock_shadow.py -- forward accrual for VIX_BULL_HARD_CAP_UNBLOCK.

Pre-registration: `analysis/recommendations/prereg-vix-bull-hard-cap-unblock-shadow-2026-09-05.json`.
Candidate: `strategy/candidates/2026-06-26-vix-bull-hard-cap-revalidate.md`
(real-fills -$471 FULL, -$471 OOS, n=2, from KEEPING the old 18.0 hard cap; candidate proposed
`vix_entry_thresholds.bull_hard_cap` 18.0 -> 22.0 + matching `backtest/lib/filters.py`
`VIX_BULL_HARD_CAP` constant).

CORRECTED PREMISE (found fresh this session, 2026-09-05 -- see prereg for the full note):
this candidate's own `## ADJUDICATION 2026-09-05` section assumed the 18->22 change was still
pending and CONFIG-FROZEN. That is factually wrong as of this script's authoring: BOTH
`automation/state/params.json:vix_entry_thresholds.bull_hard_cap` AND
`backtest/lib/filters.py:VIX_BULL_HARD_CAP` already read **22.0**, pinned by
`backtest/tests/test_no_stale_blocks.py::test_vix_bull_hard_cap_params_unblocked` and
`::test_vix_bull_hard_cap_filters_unblocked` (both PASS). filters.py's own inline comment says
"WS2 unblock 2026-06-26, was 18". So the unblock ALREADY SHIPPED -- there is no live suppression
event left to count. What remains genuinely open is whether the +$471 in-sample benefit HOLDS
forward now that VIX-in-[18,22) bull setups are no longer blocked. That is what this script
accrues: it does NOT scan for blocked/suppressed trades (there aren't any anymore at this
threshold); it scans core-decisions.jsonl for `safe`-arm ENTER_BULL ticks whose `vix` field
falls in [18.0, 22.0) on/after FORWARD_START_DATE, joins each to its real round-trip P&L via
`fills_fifo.mine_real_arm_fills`, and reports forward n / total P&L / win rate against the
candidate's own in-sample baseline (2 winners, +$471 combined) as the comparison bar.

ZERO ENGINE WIRING: reads `core-decisions.jsonl` + `fills-ledger.jsonl` (both read-only) and
writes only to `analysis/recommendations/`. Never imports `heartbeat_core`, `filters` (used only
read-only via backtest/tests, not from this script), `orchestrator`'s live dispatch,
`strategies`, `risk_gate`, `exit_manager`, `fleet_executor`, `fleet_live`, or `params*.json`.
Places no orders. Idempotent full-rewrite, same pattern as `pullback_hold_shadow.py` /
`day_throttle_shadow.py`: deterministic function of its two read-only inputs, safe to re-fire.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fills_fifo  # noqa: E402 -- automation/state/fleet/fills_fifo.py, C14 shared reconstructor

CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
OUT_DIR = REPO / "analysis" / "recommendations"
LEDGER = OUT_DIR / "vix-bull-hard-cap-unblock-shadow-ledger.jsonl"
SUMMARY = OUT_DIR / "vix-bull-hard-cap-unblock-shadow-summary.json"
PREREG_REL = "analysis/recommendations/prereg-vix-bull-hard-cap-unblock-shadow-2026-09-05.json"

ARM = "safe-2"           # Safe params carry the 22.0 cap; Bold has a different (VIX<30) cap
CORE_ACCOUNT = "safe"    # core-decisions.jsonl account field for the Safe tick
VIX_BAND_LOW = 18.0      # inclusive
VIX_BAND_HIGH = 22.0     # exclusive -- the OLD hard cap; anything >=22 is still blocked today
FORWARD_START_DATE = "2026-09-05"  # this script's own authoring date -- rows before this are
                                    # historical/context only, not part of the forward accrual
IS_BASELINE_PNL = 471.0            # candidate's own cited in-sample/OOS benefit from unblocking
IS_BASELINE_N = 2                  # candidate's own cited winner count (4/09 +$205, 4/22 +$266)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        except Exception:  # noqa: BLE001 -- a torn line must never kill the accrual
            continue
    return rows


def _stamp_now_et() -> str:
    try:
        sys.path.insert(0, str(REPO / "setup" / "scripts"))
        from et_clock import et_now  # noqa: PLC0415
        return et_now().isoformat()
    except Exception:  # noqa: BLE001
        return ""


def find_band_entries(core_rows: list[dict]) -> list[dict]:
    """safe-arm ENTER_BULL ticks with vix in [18,22) on/after FORWARD_START_DATE."""
    out = []
    for r in core_rows:
        if r.get("account") != CORE_ACCOUNT:
            continue
        if r.get("verdict") != "ENTER_BULL":
            continue
        ts = r.get("ts_et") or ""
        if ts < FORWARD_START_DATE:
            continue
        vix = r.get("vix")
        if not isinstance(vix, (int, float)):
            continue
        if not (VIX_BAND_LOW <= vix < VIX_BAND_HIGH):
            continue
        out.append({
            "ts_et": ts,
            "core_tick_id": r.get("core_tick_id"),
            "vix": vix,
            "spy": r.get("spy"),
            "setup": r.get("setup"),
            "side": r.get("side"),
        })
    return out


def join_pnl(band_entries: list[dict], round_trips: list[dict]) -> list[dict]:
    """Match each band entry to its round-trip P&L by nearest entry_ts_et (same date,
    within 5 minutes) -- same tolerance convention as fleet_gate_leak_shadow.py's
    ENTRY_WINDOW_SEC=300."""
    from datetime import datetime

    def _parse(ts):
        try:
            return datetime.fromisoformat(ts)
        except Exception:  # noqa: BLE001
            return None

    rt_by_date: dict[str, list[dict]] = {}
    for rt in round_trips:
        d = str(rt.get("date") or "")
        rt_by_date.setdefault(d, []).append(rt)

    out = []
    for e in band_entries:
        e_dt = _parse(e["ts_et"])
        matched = None
        if e_dt is not None:
            date_key = e_dt.strftime("%Y-%m-%d")
            for rt in rt_by_date.get(date_key, []):
                rt_dt = _parse(rt.get("entry_ts_et") or "")
                if rt_dt is None:
                    continue
                if abs((rt_dt - e_dt).total_seconds()) <= 300 and rt.get("side") == "C":
                    matched = rt
                    break
        row = dict(e)
        row["matched"] = matched is not None
        row["real_pnl"] = matched.get("real_pnl") if matched else None
        out.append(row)
    return out


def build_summary(joined: list[dict]) -> dict:
    matched = [r for r in joined if r["matched"] and isinstance(r["real_pnl"], (int, float))]
    total_pnl = sum(r["real_pnl"] for r in matched)
    wins = sum(1 for r in matched if r["real_pnl"] > 0)
    n = len(matched)
    return {
        "n_band_entries_seen": len(joined),
        "n_matched_round_trips": n,
        "forward_total_pnl": round(total_pnl, 2),
        "forward_win_rate": round(wins / n, 4) if n else None,
        "is_baseline_pnl": IS_BASELINE_PNL,
        "is_baseline_n": IS_BASELINE_N,
        "decision_rule": (
            "Forward CI-lower bootstrap PF > 1.0 over n>=15 matched round trips before this "
            "is cited as confirming evidence at the 2026-10-30 config-freeze checkpoint; "
            "n<15 stays UNVERIFIED/insufficient regardless of sign."
        ),
        "status": "ACCRUING" if n < 15 else "SUFFICIENT_N_FOR_REVIEW",
    }


def run() -> dict:
    core_rows = _read_jsonl(CORE_DECISIONS)
    band_entries = find_band_entries(core_rows)
    round_trips = fills_fifo.mine_real_arm_fills(ARM)
    joined = join_pnl(band_entries, round_trips)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("w", encoding="utf-8") as fh:
        for row in joined:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    summary = build_summary(joined)
    summary["_prereg"] = PREREG_REL
    summary["_generated_at_et"] = _stamp_now_et()
    summary["_arm"] = ARM
    summary["_vix_band"] = [VIX_BAND_LOW, VIX_BAND_HIGH]
    summary["_forward_start_date"] = FORWARD_START_DATE
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    out = run()
    print(json.dumps(out, indent=2, sort_keys=True))
