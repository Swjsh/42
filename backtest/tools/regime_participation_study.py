"""regime_participation_study.py -- PERFORMANCE x PARTICIPATION decomposition by archetype
(2026-08-02, REGIME-PARTICIPATION task).

THE FINDING BEING DECOMPOSED: engine-fullhist-replay-2026-07-23 (191 real-OPRA trades,
2025-01-02..2026-07-22, current live core-Safe engine) shows gap-go = 60.5% of ALL P&L on
~22% of days, while trend-up/trend-down/V-reversal/inverted-V are all underpowered (n<15).
This module answers PARTICIPATION (why so few entries on trend days) and PERFORMANCE (is
gap-go's dominance edge or concentration) as two SEPARATE questions from separate sources.

PURE FUNCTIONS (guarded by test_regime_participation_study.py, fixture-based, no I/O):
  performance_by_archetype()      -- trade log x archetype -> n/WR/total/mean/concentration
  recent_n_trading_days()         -- last-N-distinct-dates selector (RECENCY_LOOKBACK convention)
  core_decisions_participation()  -- pre-classified core-decisions events x archetype -> histogram

I/O GLUE (main(), not unit-tested -- reads real files, mirrors every other tool in this repo):
  - analysis/recommendations/engine-fullhist-replay-2026-07-23.json  (191-trade log, PERFORMANCE)
  - analysis/regime-library/day-archetypes.json                     (WS6 archetype tags, via regime_slice)
  - automation/state/core-decisions.jsonl                            (LIVE window, filtered armed=True)
  - analysis/regime-library/participation-replay-fullhist-2026-08-02.json (built by
    regime_participation_replay.py -- full-population bear-side decision trace, already
    archetype-tagged; this module just re-presents its by_archetype block, no logic duplicated)

CORE-DECISIONS SCOPE: only 'safe' and 'bold' accounts (the CORE engine -- the one that
produced the $4,808.75/191-trade finding), NOT the 4 fleet_rest arms (those are a different
risk-profile experiment, out of this task's scope). armed=True filter is TASK-SPECIFIED:
off-hours diagnostic rows carry armed:false and would inflate denominators.

OUTPUT: analysis/regime-library/REGIME-PARTICIPATION-STUDY-2026-08-02.json
Run: backtest/.venv/Scripts/python.exe backtest/tools/regime_participation_study.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]     # backtest/
ROOT = REPO.parent                              # repo root
TOOLS = REPO / "tools"
for _p in (str(ROOT), str(REPO), str(TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.regime_slice import load_library  # noqa: E402

TRADES_JSON = ROOT / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
LIBRARY_JSON = ROOT / "analysis" / "regime-library" / "day-archetypes.json"
CORE_DECISIONS = ROOT / "automation" / "state" / "core-decisions.jsonl"
REPLAY_JSON = ROOT / "analysis" / "regime-library" / "participation-replay-fullhist-2026-08-02.json"
OUT_JSON = ROOT / "analysis" / "regime-library" / "REGIME-PARTICIPATION-STUDY-2026-08-02.json"

CORE_ACCOUNTS = ("safe", "bold")
RECENCY_LOOKBACK_TRADING_DAYS = 25   # matches backtest/autoresearch/recency_check.py convention


# =============================================================================== PERFORMANCE

def performance_by_archetype(trades: list[dict], archetype_lookup: dict[str, str]) -> dict[str, dict]:
    """trades: [{"date": "YYYY-MM-DD", "dollar_pnl": float}, ...] (extra keys ignored).
    archetype_lookup: {"YYYY-MM-DD": archetype_str}. Pure -- no I/O, no clock.

    For each archetype: n_trades, n_days (distinct trade dates), total, mean_trade,
    win_rate, and the CONCENTRATION check the task asks for explicitly --
    top_day (best single calendar day's $ within the archetype) and its SHARE of the
    archetype's total (top_day_total / total, when total != 0), plus drop-best-day and
    drop-best-trade deltas. A share near/above 100% on a positive archetype means "this
    archetype's edge IS one outlier day", not a regime effect.
    """
    by_arch: dict[str, list[dict]] = {}
    untagged: list[dict] = []
    for t in trades:
        arch = archetype_lookup.get(t["date"])
        if arch is None:
            untagged.append(t)
            continue
        by_arch.setdefault(arch, []).append(t)

    out: dict[str, dict] = {}
    for arch, rows in by_arch.items():
        n = len(rows)
        total = round(sum(r["dollar_pnl"] for r in rows), 2)
        wins = sum(1 for r in rows if r["dollar_pnl"] > 0)
        by_day: dict[str, float] = {}
        for r in rows:
            by_day[r["date"]] = round(by_day.get(r["date"], 0.0) + r["dollar_pnl"], 2)
        n_days = len(by_day)
        top_day_date, top_day_total = max(by_day.items(), key=lambda kv: kv[1])
        top_trade = max(rows, key=lambda r: r["dollar_pnl"])
        drop_best_day_total = round(total - top_day_total, 2)
        drop_best_trade_total = round(total - top_trade["dollar_pnl"], 2)
        out[arch] = {
            "n_trades": n,
            "n_days": n_days,
            "total_pnl": total,
            "mean_trade_pnl": round(total / n, 2) if n else None,
            "mean_day_pnl": round(total / n_days, 2) if n_days else None,
            "win_rate": round(wins / n, 4) if n else None,
            "top_day": {"date": top_day_date, "total": top_day_total},
            "top_day_share_of_total": (round(top_day_total / total, 4)
                                        if total not in (0, 0.0) else None),
            "drop_best_day_total": drop_best_day_total,
            "drop_best_day_still_positive": drop_best_day_total > 0,
            "top_trade": {"date": top_trade["date"], "dollar_pnl": top_trade["dollar_pnl"]},
            "drop_best_trade_total": drop_best_trade_total,
            "drop_best_trade_still_positive": drop_best_trade_total > 0,
            "underpowered_n_lt_15": n < 15,
        }
    if untagged:
        out["UNTAGGED"] = {"n_trades": len(untagged),
                            "dates": sorted({t["date"] for t in untagged})}
    return out


def recent_n_trading_days(all_dates: list[str], n: int = RECENCY_LOOKBACK_TRADING_DAYS) -> list[str]:
    """Newest n distinct ISO dates from all_dates, ascending. Pure, no clock (caller supplies
    'all_dates' -- the population's own date list, never wall-clock 'today')."""
    uniq = sorted(set(all_dates))
    return uniq[-n:] if n else uniq


# =============================================================================== PARTICIPATION (live)

def core_decisions_participation(events_by_account: dict[str, list[dict]],
                                  archetype_lookup: dict[str, str]) -> dict:
    """events_by_account: {"safe": [event_dict, ...], "bold": [...]}, each event already
    classified (participation_cascade.classify_core_row shape: side/setup/tier/stage/
    category/blocker) and carrying a 'date' key (YYYY-MM-DD, the event's ts_start date).
    Pure -- no I/O. Returns per-account-per-archetype stage/blocker histograms."""
    out: dict[str, dict] = {}
    for account, events in events_by_account.items():
        by_arch: dict[str, list[dict]] = {}
        for e in events:
            arch = archetype_lookup.get(e["date"], "UNTAGGED")
            by_arch.setdefault(arch, []).append(e)
        acc_out: dict[str, dict] = {}
        for arch, evs in by_arch.items():
            stage_counts = Counter(e["stage"] for e in evs)
            dates = sorted({e["date"] for e in evs})
            blocker_events = [e for e in evs if e["stage"] not in ("NO_DATA", "NO_SIGNAL",
                                                                     "PLACED", "FILLED")]
            blockers = Counter((e["category"], e["blocker"] or e["stage"]) for e in blocker_events)
            acc_out[arch] = {
                "n_days_observed": len(dates),
                "dates": dates,
                "n_events": len(evs),
                "by_stage": dict(stage_counts),
                "n_entered": stage_counts.get("PLACED", 0) + stage_counts.get("FILLED", 0),
                "top_blockers": [{"category": cat, "blocker": name, "n": n}
                                  for (cat, name), n in blockers.most_common()],
            }
        out[account] = acc_out
    return out


# =============================================================================== I/O glue

def log(msg: str) -> None:
    print(f"[regime-participation-study] {msg}", flush=True)


def _load_core_decisions_events(core_glob_dir: Path) -> dict[str, list[dict]]:
    """Reads core-decisions*.jsonl, filters armed==True (task-specified -- off-hours
    diagnostic rows carry armed:false and would inflate denominators), splits by account,
    and runs the SAME participation_cascade.build_events dedup every other consumer of this
    ledger uses (REUSED, not reimplemented) so a persistent condition across many ticks
    counts as ONE event, not N. Returns {"safe": [...], "bold": [...]}."""
    import participation_cascade as pc

    rows_by_account: dict[str, list[dict]] = {"safe": [], "bold": []}
    n_total = 0
    n_armed = 0
    for p in sorted(core_glob_dir.glob("core-decisions*.jsonl")):
        for row in pc._iter_jsonl(p):
            n_total += 1
            if row.get("armed") is not True:
                continue
            n_armed += 1
            acc = row.get("account")
            if acc in rows_by_account:
                rows_by_account[acc].append(row)
    log(f"  core-decisions: {n_total} total rows, {n_armed} armed==True "
        f"(safe={len(rows_by_account['safe'])}, bold={len(rows_by_account['bold'])})")

    events_by_account: dict[str, list[dict]] = {}
    for acc, rows in rows_by_account.items():
        rows_by_date: dict[str, list[dict]] = {}
        for r in rows:
            d = str(r.get("ts_et") or "")[:10]
            if d:
                rows_by_date.setdefault(d, []).append(r)
        events: list[dict] = []
        for d, day_rows in rows_by_date.items():
            day_events = pc.build_events(day_rows, acc, "core")
            for e in day_events:
                e["date"] = d
            events.extend(day_events)
        events_by_account[acc] = events
    return events_by_account


def main() -> int:
    log("loading regime library")
    lib = load_library(LIBRARY_JSON)
    archetype_lookup = {d: rec["archetype"] for d, rec in lib["days"].items()}

    log(f"loading trade log: {TRADES_JSON.name}")
    trades_doc = json.loads(TRADES_JSON.read_text(encoding="utf-8"))
    trades = [{"date": t["date"], "dollar_pnl": t["dollar_pnl"], "setup": t.get("setup"),
               "side": t.get("side")} for t in trades_doc["trades"]]
    all_trade_dates = sorted({t["date"] for t in trades})
    log(f"  {len(trades)} trades, {len(all_trade_dates)} distinct trade dates, "
        f"{all_trade_dates[0]}..{all_trade_dates[-1]}")

    perf_full = performance_by_archetype(trades, archetype_lookup)

    recent_dates = recent_n_trading_days(all_trade_dates, RECENCY_LOOKBACK_TRADING_DAYS)
    recent_set = set(recent_dates)
    trades_recent = [t for t in trades if t["date"] in recent_set]
    perf_recent = performance_by_archetype(trades_recent, archetype_lookup)
    log(f"  recent-{RECENCY_LOOKBACK_TRADING_DAYS} window: {recent_dates[0]}..{recent_dates[-1]} "
        f"({len(trades_recent)} trades)")

    log("loading + classifying core-decisions.jsonl (armed==True only)")
    events_by_account = _load_core_decisions_events(ROOT / "automation" / "state")
    core_part = core_decisions_participation(events_by_account, archetype_lookup)
    core_dates = sorted({e["date"] for evs in events_by_account.values() for e in evs})
    log(f"  live core-decisions window observed: "
        f"{core_dates[0] if core_dates else 'n/a'}..{core_dates[-1] if core_dates else 'n/a'}")

    replay_by_archetype = None
    replay_window = None
    replay_anchor = None
    if REPLAY_JSON.exists():
        log(f"loading full-population replay decision trace: {REPLAY_JSON.name}")
        replay_doc = json.loads(REPLAY_JSON.read_text(encoding="utf-8"))
        replay_by_archetype = replay_doc["by_archetype"]
        replay_window = replay_doc["window"]
        replay_anchor = replay_doc["anchor_crosscheck"]
    else:
        log(f"  WARNING: {REPLAY_JSON} not found -- run regime_participation_replay.py first")

    out = {
        "generated_at": dt.datetime.now().isoformat(),
        "tool": "backtest/tools/regime_participation_study.py",
        "sources": {
            "performance_trade_log": str(TRADES_JSON.relative_to(ROOT)),
            "regime_library": str(LIBRARY_JSON.relative_to(ROOT)),
            "core_decisions_live": str(CORE_DECISIONS.relative_to(ROOT)),
            "full_population_replay": (str(REPLAY_JSON.relative_to(ROOT))
                                        if REPLAY_JSON.exists() else None),
        },
        "performance": {
            "full_population": {"window": [all_trade_dates[0], all_trade_dates[-1]],
                                 "n_trades": len(trades), "by_archetype": perf_full},
            "recent_window": {"window": [recent_dates[0], recent_dates[-1]],
                               "n_trading_days": len(recent_dates),
                               "n_trades": len(trades_recent), "by_archetype": perf_recent},
        },
        "participation_live_window": {
            "window_observed": [core_dates[0], core_dates[-1]] if core_dates else None,
            "note": ("LIVE core-decisions.jsonl, armed==True only, safe+bold accounts, "
                     "deduped via participation_cascade.build_events. This is the ONLY "
                     "source in this study with risk-gate (SIZING_REFUSED-equivalent = "
                     "RISK_GATE_DENY) visibility and the ONLY source covering BOTH sides "
                     "(bull+bear), but over a short live window."),
            "by_account": core_part,
        },
        "participation_full_population_replay": {
            "window": replay_window,
            "anchor_crosscheck": replay_anchor,
            "note": ("bear-side RIDE_THE_RIBBON candidate/gate trace, "
                     "backtest/tools/regime_participation_replay.py. See that script's "
                     "SCOPE DISCLOSURE for limits (bear-only, no risk-gate visibility, "
                     "small anchor drift vs the 2026-07-27 LADDER-FULLHIST pin -- disclosed, "
                     "does not affect candidate/blocker COUNTS)."),
            "by_archetype": replay_by_archetype,
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
