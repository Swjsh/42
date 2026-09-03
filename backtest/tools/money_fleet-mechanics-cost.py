"""money_fleet-mechanics-cost.py -- H9 FLEET MECHANICS (2026-09-03, Sonnet, read-only).

Extends the CLOSED queue items FLEET-STALE-SIGNAL-SKIPS-STRUCTURE-STOP (never fired with a
position, downgraded to guard-only) and FLEET-SIGNAL-UNREADABLE-WITH-POSITION (filed, join to
trades-enriched explicitly marked "not run") over the last 15 trading sessions
(2026-08-13..2026-09-02, i.e. NOT including the still-live 2026-09-03 session).

Three parts:

  A. SKIP CENSUS + WOULD-HAVE-FIRED COSTING. For every fleet-arm tick where
     `signal_status` collapses `usable_signal` to None (signal_stale_*, signal_unreadable,
     no_signal_file -- see fleet_live.py:112-122) while a `stop_mode=="structure"` leg is
     open, reconstruct what the structure check WOULD have seen: `shared-signal.json`'s
     "spot" field is verified (build_shared_signal.py:150, `"spy": row.get("spy")`) to be a
     verbatim passthrough of core-decisions.jsonl's `spy` field for account=="safe" (the
     fleet's producer account, build_shared_signal.py:238 default). So core-decisions.jsonl
     (safe account) rows in the same window are the ground-truth proxy for the value the
     skipped tick could not read. Apply `_structure_stop_hit` (exit_manager.py:140-149:
     call exits when close < trigger_level, put exits when close > trigger_level) using the
     nearest core "safe" row at-or-before the skipped tick's timestamp (same day). A
     "would-have-fired" tick prices its cost as the premium held at the skip tick
     (`exit_pass[].worst_premium`, the conservative/adverse side) minus the premium at the
     position's ACTUAL later exit (from trades-enriched.jsonl, joined by arm+symbol+date),
     qty x multiplier(100) x contracts. Positive = money the skip cost (held through a worse
     exit); negative = the skip happened to help (delay paid off).

  B. CROSS-ARM EXIT-TIMING LAG. For (date, symbol) pairs where safe-2 (core, direct
     structure-check every tick) and >=1 fleet arm (safe-3/risky-1, gated by the shared
     signal) both BOUGHT the same OCC contract the same day (fills-ledger.jsonl, ground
     truth), compare each side's LAST sell fill of the day (position-closing leg) --
     lag_minutes = fleet_last_sell_ts - safe2_last_sell_ts, and a per-contract price delta
     (fleet's qty-weighted avg sell price - safe-2's) x 100, disclosed per-contract (arms
     size differently, so a raw qty-scaled dollar total would conflate lag cost with sizing
     policy).

  C. EXIT-STATE SAVE-RACE SCAN (light, exploratory; FLEET-EXIT-STATE-SAVE-PER-SYMBOL is a
     FILED theoretical risk, not yet verified to have manifested). Flags any (arm, symbol,
     day) with >=2 SELL fills on the same open_qty-consuming leg within 90s of each other
     (candidate double-fire pattern) for manual follow-up -- NOT a proof of the race, a
     screen for it.

Read-only: parses automation/state/fleet/*/decisions.jsonl, automation/state/core-decisions.
jsonl, automation/state/fills-ledger.jsonl, analysis/trades-enriched.jsonl. No writes to any
of those paths, no network, no broker/MCP calls.
"""
from __future__ import annotations

import json
import re
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
FLEET_DIR = REPO_ROOT / "automation" / "state" / "fleet"
CORE_DECISIONS = REPO_ROOT / "automation" / "state" / "core-decisions.jsonl"
FILLS_LEDGER = REPO_ROOT / "automation" / "state" / "fills-ledger.jsonl"
TRADES_ENRICHED = REPO_ROOT / "analysis" / "trades-enriched.jsonl"

WINDOW_START = "2026-08-13"
WINDOW_END = "2026-09-02"
FLEET_ARMS = ["safe-1", "safe-3", "risky-1", "risky-3"]
MULTIPLIER = 100

_STALE_RE = re.compile(r"^signal_stale_(\d+)s$")
_OCC_RE = re.compile(r"^SPY\d{6}([CP])\d{8}$")

RNG_SEED = 20260903


# --------------------------------------------------------------------------- loaders ----
def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _date_of(ts: str | None) -> str | None:
    if not isinstance(ts, str) or len(ts) < 10:
        return None
    return ts[:10]


def _parse_ts(ts: str | None) -> datetime | None:
    if not isinstance(ts, str):
        return None
    t = ts[:26]
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(t, fmt)
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except ValueError:
            continue
    return None


def occ_side(symbol: str | None) -> str | None:
    if not isinstance(symbol, str):
        return None
    m = _OCC_RE.match(symbol)
    return m.group(1) if m else None


def parse_stale_age_sec(status: str | None) -> int | None:
    if not isinstance(status, str):
        return None
    m = _STALE_RE.match(status)
    return int(m.group(1)) if m else None


def is_unreadable(status: str | None) -> bool:
    return isinstance(status, str) and status.startswith("signal_unreadable")


def is_no_signal_file(status: str | None) -> bool:
    return status == "no_signal_file"


def skip_qty_val(rec: dict[str, Any]) -> float:
    return rec.get("open_qty") or 0


# --------------------------------------------------------------------------- core proxy -
def build_core_safe_series(start: str, end: str) -> list[tuple[datetime, float]]:
    """(ts, spy) for account=="safe" core-decisions.jsonl rows in [start,end], sorted.
    This is the verbatim source of shared-signal.json's "spot" field (see module docstring)
    -- i.e. exactly what a fleet tick's structure check would have used had the signal been
    readable at that instant."""
    rows = _load_jsonl(CORE_DECISIONS)
    out = []
    for r in rows:
        if r.get("account") != "safe":
            continue
        d = _date_of(r.get("ts_et"))
        if d is None or not (start <= d <= end):
            continue
        spy = r.get("spy")
        ts = _parse_ts(r.get("ts_et"))
        if ts is None or spy is None:
            continue
        out.append((ts, float(spy)))
    out.sort(key=lambda x: x[0])
    return out


def nearest_prior_spy(series: list[tuple[datetime, float]], ts: datetime,
                       max_lookback_min: float = 10.0) -> tuple[float | None, float | None]:
    """Latest (spy, age_minutes) at-or-before ts within max_lookback_min, else (None, None).
    series must be sorted ascending by ts."""
    best = None
    for t, spy in series:
        if t > ts:
            break
        best = (t, spy)
    if best is None:
        return None, None
    age_min = (ts - best[0]).total_seconds() / 60.0
    if age_min > max_lookback_min:
        return None, None
    return best[1], age_min


# --------------------------------------------------------------------------- part A -----
def part_a_skip_census(arms: list[str], start: str, end: str,
                        core_series: list[tuple[datetime, float]]) -> dict[str, Any]:
    trades = _load_jsonl(TRADES_ENRICHED)
    # index trades-enriched structure_stop exits by (arm, symbol, date) -> list of rows
    exits_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for t in trades:
        if "_meta" in t:
            continue
        key = (t.get("arm"), t.get("symbol"), t.get("date"))
        exits_by_key[key].append(t)

    # fills-ledger: ground-truth SELL fills per (arm, symbol, date), sorted by time -- used
    # to find the ACTUAL fill that closed the position after a would-have-fired skip tick,
    # which is more direct than trades-enriched's per-whole-trade aggregate (and covers
    # dates trades-enriched hasn't been re-run for yet, e.g. the tail of the window).
    fills = _load_jsonl(FILLS_LEDGER)
    sells_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for f in fills:
        if f.get("side") != "sell" or not f.get("is_option"):
            continue
        key = (f.get("arm"), f.get("symbol"), f.get("date_et"))
        sells_by_key[key].append(f)
    for k in sells_by_key:
        sells_by_key[k].sort(key=lambda f: f.get("ts_et", ""))

    out: dict[str, Any] = {"window": [start, end], "arms": {}}
    all_would_fire_costs: list[float] = []
    root_causes: dict[str, int] = defaultdict(int)

    for arm in arms:
        path = FLEET_DIR / arm / "decisions.jsonl"
        rows = _load_jsonl(path)
        per_day: dict[str, dict[str, int]] = defaultdict(lambda: {
            "total_ticks": 0, "stale_ticks": 0, "stale_open": 0,
            "unreadable_ticks": 0, "unreadable_open": 0, "no_signal_file_open": 0,
        })
        would_fire_records = []
        skip_open_structure_ticks = []  # every tick where a structure leg was open+skipped

        for row in rows:
            d = _date_of(row.get("ts_et"))
            if d is None or not (start <= d <= end):
                continue
            status = row.get("signal_status")
            flat = row.get("flat")
            position_open = flat is False
            bucket = per_day[d]
            bucket["total_ticks"] += 1

            age = parse_stale_age_sec(status)
            unreadable = is_unreadable(status)
            no_sig = is_no_signal_file(status)
            if age is not None:
                bucket["stale_ticks"] += 1
                if position_open:
                    bucket["stale_open"] += 1
            elif unreadable:
                bucket["unreadable_ticks"] += 1
                if unreadable:
                    root_causes[str(status)[:60]] += 1
                if position_open:
                    bucket["unreadable_open"] += 1
            elif no_sig and position_open:
                bucket["no_signal_file_open"] += 1

            skip_kind = "stale" if age is not None else ("unreadable" if unreadable else
                                                           ("no_signal_file" if no_sig else None))
            if skip_kind is None or not position_open:
                continue

            for leg in (row.get("exit_pass") or []):
                if leg.get("stop_mode") != "structure":
                    continue
                if (leg.get("open_qty") or 0) <= 0:
                    continue
                if leg.get("last_closed_5m_close") is not None:
                    continue  # this leg's structure check wasn't actually starved this tick
                symbol = leg.get("symbol")
                trigger_level = leg.get("trigger_level")
                side = occ_side(symbol)
                ts = _parse_ts(row.get("ts_et"))
                rec = {
                    "date": d, "ts_et": row.get("ts_et"), "symbol": symbol,
                    "side": side, "trigger_level": trigger_level,
                    "open_qty": leg.get("open_qty"), "worst_premium": leg.get("worst_premium"),
                    "best_premium": leg.get("best_premium"), "skip_kind": skip_kind,
                    "signal_status": status,
                }
                skip_open_structure_ticks.append(rec)
                if trigger_level is None or side is None or ts is None:
                    rec["would_have_fired"] = None
                    rec["proxy_note"] = "missing trigger_level/side/ts -- cannot evaluate"
                    continue
                proxy_spy, age_min = nearest_prior_spy(core_series, ts)
                if proxy_spy is None:
                    rec["would_have_fired"] = None
                    rec["proxy_note"] = "no core-safe proxy row within 10min lookback"
                    continue
                rec["proxy_spy"] = proxy_spy
                rec["proxy_age_min"] = round(age_min, 2)
                hit = (proxy_spy < trigger_level) if side == "C" else (proxy_spy > trigger_level)
                rec["would_have_fired"] = hit
                if hit:
                    would_fire_records.append(rec)

        # cost each would-fire tick against the FIRST actual SELL fill on that arm+symbol
        # at-or-after the skip tick (ground truth from fills-ledger; this is the fill that
        # would have been REPLACED by an immediate structure-stop sell had the tick not
        # been skipped). Falls back to trades-enriched's whole-trade implied exit price if
        # no matching fill exists (shouldn't happen for a genuinely open leg, but keep the
        # fallback for robustness rather than silently dropping the record).
        for rec in would_fire_records:
            key = (arm, rec["symbol"], rec["date"])
            skip_ts = rec["ts_et"]
            next_sell = next(
                (f for f in sells_by_key.get(key, []) if f.get("ts_et", "") >= skip_ts), None
            )
            if next_sell is not None:
                fill_ts = _parse_ts(next_sell.get("ts_et"))
                skip_dt = _parse_ts(skip_ts)
                delay_min = ((fill_ts - skip_dt).total_seconds() / 60.0
                             if fill_ts and skip_dt else None)
                cost = (rec["worst_premium"] - next_sell.get("price", 0)) * skip_qty_val(rec) \
                    * MULTIPLIER
                rec["actual_next_sell_fill"] = {
                    "ts_et": next_sell.get("ts_et"), "price": next_sell.get("price"),
                    "qty": next_sell.get("qty"),
                }
                rec["delay_to_actual_exit_minutes"] = (round(delay_min, 2)
                                                         if delay_min is not None else None)
                rec["cost_dollars"] = round(cost, 2)
                rec["cost_method"] = "fills_ledger_next_sell"
                all_would_fire_costs.append(cost)
                continue
            candidates = exits_by_key.get(key, [])
            if not candidates:
                rec["cost_dollars"] = None
                rec["cost_note"] = "no fills-ledger sell and no trades-enriched row"
                continue
            tr = candidates[0]
            entry_price = tr.get("entry_price")
            qty = tr.get("qty")
            pnl = tr.get("realized_pnl")
            if None in (entry_price, qty, pnl) or qty in (0, None):
                rec["cost_dollars"] = None
                rec["cost_note"] = "trades-enriched row missing entry_price/qty/pnl"
                continue
            implied_exit_price = entry_price + (pnl / (qty * MULTIPLIER))
            cost = (rec["worst_premium"] - implied_exit_price) * skip_qty_val(rec) * MULTIPLIER
            rec["actual_exit_price_implied"] = round(implied_exit_price, 4)
            rec["actual_realized_pnl_whole_trade"] = pnl
            rec["cost_dollars"] = round(cost, 2)
            rec["cost_method"] = "trades_enriched_implied"
            all_would_fire_costs.append(cost)

        total_stale_open = sum(v["stale_open"] for v in per_day.values())
        total_unreadable_open = sum(v["unreadable_open"] for v in per_day.values())
        total_no_sig_open = sum(v["no_signal_file_open"] for v in per_day.values())

        out["arms"][arm] = {
            "decisions_path": str(path.relative_to(REPO_ROOT)),
            "n_days_in_window": len(per_day),
            "per_day": {d: dict(v) for d, v in sorted(per_day.items())},
            "total_stale_with_open_position": total_stale_open,
            "total_unreadable_with_open_position": total_unreadable_open,
            "total_no_signal_file_with_open_position": total_no_sig_open,
            "skip_ticks_with_open_structure_leg_n": len(skip_open_structure_ticks),
            "would_have_fired_n": len(would_fire_records),
            "would_have_fired_records": would_fire_records,
            "skip_ticks_detail_sample": skip_open_structure_ticks[:5],
        }

    out["root_cause_message_histogram"] = dict(root_causes)
    out["would_fire_costs_pooled"] = all_would_fire_costs
    return out


# --------------------------------------------------------------------------- bootstrap --
def bootstrap_ci(values: list[float], n_resamples: int = 5000, seed: int = RNG_SEED
                  ) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "ci_2.5": None, "ci_97.5": None}
    import random
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_resamples):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(statistics.fmean(sample))
    means.sort()
    lo = means[int(0.025 * n_resamples)]
    hi = means[min(int(0.975 * n_resamples), n_resamples - 1)]
    return {
        "n": n, "mean": round(statistics.fmean(values), 2),
        "ci_2.5": round(lo, 2), "ci_97.5": round(hi, 2),
        "n_resamples": n_resamples,
    }


# --------------------------------------------------------------------------- part B -----
def part_b_cross_arm_lag(start: str, end: str) -> dict[str, Any]:
    fills = _load_jsonl(FILLS_LEDGER)
    fills = [f for f in fills if f.get("is_option") and (d := _date_of(f.get("date_et")))
             and start <= d <= end]  # noqa: E501 (walrus for readability)

    by_arm_symbol_day: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for f in fills:
        key = (f.get("arm"), f.get("symbol"), f.get("date_et"))
        by_arm_symbol_day[key].append(f)

    # symbols bought by safe-2 (core) that day
    core_symbols: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for f in fills:
        if f.get("arm") == "safe-2" and f.get("side") == "buy":
            core_symbols[(f.get("symbol"), f.get("date_et"))].append(f)

    pairs = []
    for (symbol, date), _buys in core_symbols.items():
        core_sells = sorted(
            [f for f in by_arm_symbol_day.get(("safe-2", symbol, date), [])
             if f.get("side") == "sell"],
            key=lambda f: f.get("ts_et", ""),
        )
        if not core_sells:
            continue
        core_last = core_sells[-1]
        core_last_ts = _parse_ts(core_last.get("ts_et"))
        core_qty = sum(f.get("qty", 0) for f in core_sells)
        core_vwap = (sum(f.get("qty", 0) * f.get("price", 0) for f in core_sells) / core_qty
                     if core_qty else None)

        for fleet_arm in ("safe-3", "risky-1"):
            fleet_sells = sorted(
                [f for f in by_arm_symbol_day.get((fleet_arm, symbol, date), [])
                 if f.get("side") == "sell"],
                key=lambda f: f.get("ts_et", ""),
            )
            if not fleet_sells:
                continue
            fleet_last = fleet_sells[-1]
            fleet_last_ts = _parse_ts(fleet_last.get("ts_et"))
            fleet_qty = sum(f.get("qty", 0) for f in fleet_sells)
            fleet_vwap = (sum(f.get("qty", 0) * f.get("price", 0) for f in fleet_sells)
                          / fleet_qty if fleet_qty else None)
            if core_last_ts is None or fleet_last_ts is None:
                continue
            lag_min = (fleet_last_ts - core_last_ts).total_seconds() / 60.0
            price_delta_per_contract = (
                round((fleet_vwap - core_vwap) * MULTIPLIER, 2)
                if (fleet_vwap is not None and core_vwap is not None) else None
            )
            pairs.append({
                "date": date, "symbol": symbol, "fleet_arm": fleet_arm,
                "core_last_sell_ts_et": core_last.get("ts_et"),
                "fleet_last_sell_ts_et": fleet_last.get("ts_et"),
                "lag_minutes_fleet_minus_core": round(lag_min, 2),
                "core_vwap_sell_price": round(core_vwap, 4) if core_vwap else None,
                "fleet_vwap_sell_price": round(fleet_vwap, 4) if fleet_vwap else None,
                "price_delta_per_contract_dollars": price_delta_per_contract,
                "core_qty": core_qty, "fleet_qty": fleet_qty,
            })

    lags = [p["lag_minutes_fleet_minus_core"] for p in pairs]
    deltas = [p["price_delta_per_contract_dollars"] for p in pairs
              if p["price_delta_per_contract_dollars"] is not None]
    return {
        "window": [start, end],
        "n_matched_pairs": len(pairs),
        "pairs": pairs,
        "lag_minutes_ci": bootstrap_ci(lags) if lags else None,
        "price_delta_per_contract_ci": bootstrap_ci(deltas) if deltas else None,
    }


# --------------------------------------------------------------------------- part C -----
def part_c_save_race_scan(start: str, end: str) -> dict[str, Any]:
    fills = _load_jsonl(FILLS_LEDGER)
    fills = [f for f in fills if f.get("is_option") and f.get("side") == "sell"
             and f.get("arm") in ("safe-1", "safe-3", "risky-1", "risky-3")
             and (d := _date_of(f.get("date_et"))) and start <= d <= end]  # noqa: E501

    by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for f in fills:
        key = (f.get("arm"), f.get("symbol"), f.get("date_et"))
        by_key[key].append(f)

    candidates = []
    for key, group in by_key.items():
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda f: f.get("ts_et", ""))
        for i in range(1, len(group)):
            t0 = _parse_ts(group[i - 1].get("ts_et"))
            t1 = _parse_ts(group[i].get("ts_et"))
            if t0 is None or t1 is None:
                continue
            gap_s = (t1 - t0).total_seconds()
            if gap_s <= 90:
                candidates.append({
                    "arm": key[0], "symbol": key[1], "date": key[2],
                    "gap_seconds": round(gap_s, 1),
                    "fill_1": {"ts_et": group[i - 1].get("ts_et"), "qty": group[i - 1].get("qty"),
                               "price": group[i - 1].get("price")},
                    "fill_2": {"ts_et": group[i].get("ts_et"), "qty": group[i].get("qty"),
                               "price": group[i].get("price")},
                })

    return {
        "window": [start, end],
        "method": "screen only -- flags SELL fills on the same arm+symbol+day within 90s of "
                  "each other as candidate double-fire patterns consistent with the "
                  "FLEET-EXIT-STATE-SAVE-PER-SYMBOL theoretical race (per-symbol save happens "
                  "once after the whole tick's loop, exit_actuator.py ~798-799). This does "
                  "NOT prove the race fired -- back-to-back sells 90s apart are also the "
                  "normal TP1-then-runner-stop sequence on a fast-moving tick. Every candidate "
                  "below needs a manual read of its decisions.jsonl rows before being called a "
                  "race hit.",
        "n_candidates": len(candidates),
        "candidates": candidates,
    }


# --------------------------------------------------------------------------- winners ----
def winners_check(part_a: dict[str, Any]) -> dict[str, Any]:
    """Would any of the 4 named big winning days (08-06, 08-13, 08-27, 08-28) have been
    blocked/hurt by a proposed fix (e.g. flatten-on-N-stale-ticks, or evaluate structure from
    the arm's own last bar)? A fix here only ever ADDS a structure-stop evaluation on ticks
    that currently skip it -- it can only trigger exits, never block entries -- so the
    relevant question is whether any would-have-fired tick landed on one of those 4 dates."""
    winner_dates = {"2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"}
    hits = []
    for arm, data in part_a["arms"].items():
        for rec in data.get("would_have_fired_records", []):
            if rec["date"] in winner_dates:
                hits.append({"arm": arm, **rec})
    return {
        "winner_dates_checked": sorted(winner_dates),
        "would_have_fired_on_winner_day_n": len(hits),
        "hits": hits,
        "verdict": ("NO_IMPACT_ON_WINNERS" if not hits else
                    "REVIEW -- a would-have-fired tick landed on a winning day"),
    }


def main() -> None:
    core_series = build_core_safe_series(WINDOW_START, WINDOW_END)
    part_a = part_a_skip_census(FLEET_ARMS, WINDOW_START, WINDOW_END, core_series)
    part_b = part_b_cross_arm_lag(WINDOW_START, WINDOW_END)
    part_c = part_c_save_race_scan(WINDOW_START, WINDOW_END)
    winners = winners_check(part_a)

    result = {
        "hypothesis": "H9_FLEET_MECHANICS",
        "window": [WINDOW_START, WINDOW_END],
        "core_safe_proxy_rows_n": len(core_series),
        "part_a_skip_census_and_costing": part_a,
        "part_b_cross_arm_exit_lag": part_b,
        "part_c_exit_state_save_race_scan": part_c,
        "winners_check": winners,
        "would_fire_cost_ci_pooled": bootstrap_ci(part_a["would_fire_costs_pooled"]),
    }
    out_path = REPO_ROOT / "analysis" / "deep-research" / "2026-09-03-money" / "fleet-mechanics-cost.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "would_fire_n_by_arm": {a: d["would_have_fired_n"] for a, d in part_a["arms"].items()},
        "unreadable_open_by_arm": {a: d["total_unreadable_with_open_position"]
                                    for a, d in part_a["arms"].items()},
        "stale_open_by_arm": {a: d["total_stale_with_open_position"]
                               for a, d in part_a["arms"].items()},
        "would_fire_cost_ci": result["would_fire_cost_ci_pooled"],
        "cross_arm_pairs_n": part_b["n_matched_pairs"],
        "lag_ci": part_b["lag_minutes_ci"],
        "price_delta_ci": part_b["price_delta_per_contract_ci"],
        "save_race_candidates_n": part_c["n_candidates"],
        "winners_verdict": winners["verdict"],
        "out_path": str(out_path.relative_to(REPO_ROOT)),
    }, indent=2))


if __name__ == "__main__":
    main()
