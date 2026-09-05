"""tp1_fraction_ab_walk.py -- GOAL-TP1-FRACTION-AB-2026-09-05 A1+A2+A3.

Re-walks every real ribbon_ride wave (safe-2/bold-2 core + safe-3/risky-1 fleet) since
2026-06-28 through the LIVE exit shape (setup/scripts/gate_net_cost_walk.py machinery:
WalkCtx, ribbon_tick_df_for, walk_exit_manager with all_exits_market=True, real OPRA 5-min
bars, engine cost model) at tp1_qty_fraction=0.667 (control, matches live registry per
markdown/0dte/EXIT-SHAPE-TRUTH.md) vs 0.8 (treatment, the re-filed pk-2026-06-28-001
ratification) -- everything else (structure stop, chandelier trail, runner target, time
stop) identical between the two walks of the same wave.

REUSES verbatim (never reimplements): WalkCtx, _exit_shape_for_arm, _exit_cfg_for_arm,
grab.ribbon_tick_df_for from gate_net_cost_walk.py / gate_revalidation_ab.py; option_symbol /
load_contract_bars / bar_at_or_after from lib.option_pricing_real; walk_exit_manager from
lib.exit_manager_walk; _swing_stop from autoresearch._b5_vix_regime_dayside;
bar_idx_for_ts from autoresearch.gate_expiry_check.

ENTRY SET (A1): journal/trades.csv rows with a RIDE_THE_RIBBON setup, date >= 2026-06-28,
account_id in {safe, bold, safe-3, risky-1} (the goal's 4 named arms; safe/bold ARE the
core safe-2/bold-2 aliases -- CLAUDE.md's "one account, one execution path", trades.csv logs
the account_id, not the fleet alias). Rows sharing (account_id, date, time_entry) are legs of
ONE wave (TP1 leg + runner leg(s)) -- deduped here exactly on that key.

STOP LEVEL for the structure stop: nearest PRIOR decision row (core: core-decisions.jsonl by
account+side; fleet: fleet/<arm>/decisions.jsonl by side, action startswith "ENTER") within a
30-minute lookback of the recorded entry time. core-decisions rows carry
trigger_level_exact/bull_reclaim_level_raw/bear_rejection_level_raw (side-aware, see
gate_net_cost_walk._stop_level_for_wave_row's discriminating evidence for why side-matching
matters); fleet decisions.jsonl carries NEITHER field (grep-verified empty, 2026-09-05) so
fleet waves always fall through to _swing_stop. Disclosed approximation: the recorded
time_entry is the FILL time, not the original trigger tick, so this is a nearest-prior match,
not an exact one -- every wave's matched decision row is recorded in the output for audit.

REAL FILL OVERRIDE (per _walk_entry's own hand-check convention): strike/entry_premium/qty
are the REAL recorded values from trades.csv, not re-derived from the tier table -- so A/B
deltas isolate the ONE knob (tp1_qty_fraction) with everything else pinned to the actual
trade, not a synthetic reconstruction.

Output: analysis/recommendations/tp1-fraction-ab-2026-09-05.json
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (REPO, BACKTEST, BACKTEST / "lib", BACKTEST / "tools", BACKTEST / "autoresearch",
           FLEET_DIR, REPO / "setup" / "scripts", REPO / "crypto" / "lib"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

from autoresearch.gate_expiry_check import bar_idx_for_ts  # noqa: E402
from autoresearch._b5_vix_regime_dayside import _swing_stop  # noqa: E402
from lib.option_pricing_real import option_symbol, load_contract_bars, bar_at_or_after  # noqa: E402
import gate_net_cost_walk as gncw  # noqa: E402
import gate_revalidation_ab as grab  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402

TRADES_CSV = REPO / "journal" / "trades.csv"
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
OUT_JSON = REPO / "analysis" / "recommendations" / "tp1-fraction-ab-2026-09-05.json"
OUT_MD = REPO / "analysis" / "recommendations" / "tp1-fraction-ab-2026-09-05.md"

ACCT_TO_ARM = {"safe": "safe-2", "bold": "bold-2", "safe-3": "safe-3", "risky-1": "risky-1"}
VALID_ACCT_IDS = set(ACCT_TO_ARM)
FROZEN_START = "2026-08-31"
CONTROL_FRAC = 0.667
TREATMENT_FRAC = 0.8
BOOT_N = 2000
BOOT_SEED = 42


def log(m: str) -> None:
    print(f"[tp1-fraction-ab] {m}", flush=True)


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _parse_strike(contract: str) -> Optional[int]:
    m = re.search(r"\s(\d+)[CP]$", contract.strip())
    return int(m.group(1)) if m else None


def load_waves() -> list[dict]:
    rows = list(csv.DictReader(TRADES_CSV.open(encoding="utf-8-sig")))
    sel = [r for r in rows if "RIDE_THE_RIBBON" in (r.get("setup") or "")
           and (r.get("date") or "") >= "2026-06-28"
           and (r.get("account_id") or "") in VALID_ACCT_IDS]
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in sel:
        groups[(r["account_id"], r["date"], r["time_entry"])].append(r)
    waves = []
    for (acct, date_s, time_entry), legs in groups.items():
        legs_sorted = sorted(legs, key=lambda x: x["time_exit"])
        try:
            qty_total = sum(int(float(l["qty"])) for l in legs_sorted)
            entry_px = float(legs_sorted[0]["entry_px"])
        except (ValueError, TypeError):
            continue
        side = legs_sorted[0]["c_or_p"]
        contract = legs_sorted[0]["contract"]
        strike = _parse_strike(contract)
        if strike is None or side not in ("C", "P"):
            continue
        recorded_pnl = 0.0
        ok = True
        for l in legs_sorted:
            try:
                recorded_pnl += float(l["dollar_pnl"])
            except (ValueError, TypeError):
                ok = False
        if not ok:
            continue
        waves.append({
            "wave_id": f"{acct}|{date_s}|{time_entry}",
            "account_id": acct, "arm": ACCT_TO_ARM[acct], "date": date_s,
            "time_entry": time_entry, "side": side, "strike": strike,
            "entry_px": entry_px, "qty_total": qty_total,
            "n_legs": len(legs_sorted), "recorded_pnl": round(recorded_pnl, 2),
            "recorded_exits": [
                {"time_exit": l["time_exit"], "qty": l["qty"], "exit_px": l["exit_px"],
                 "dollar_pnl": l["dollar_pnl"]} for l in legs_sorted
            ],
        })
    return waves


def build_decision_indices() -> tuple[list[dict], dict[str, list[dict]]]:
    core_rows = [r for r in _load_jsonl(CORE_DECISIONS) if r.get("side") in ("C", "P")]
    core_rows.sort(key=lambda r: r["ts_et"])
    fleet_idx: dict[str, list[dict]] = {}
    for arm in ("safe-3", "risky-1"):
        rows = [r for r in _load_jsonl(FLEET_DIR / arm / "decisions.jsonl")
                if r.get("side") in ("C", "P") and str(r.get("action", "")).startswith("ENTER")]
        rows.sort(key=lambda r: r["ts_et"])
        fleet_idx[arm] = rows
    return core_rows, fleet_idx


def _nearest_prior(rows: list[dict], key_field: str, ts_et_iso: str, side: str,
                    lookback_min: int = 30) -> Optional[dict]:
    target = pd.Timestamp(ts_et_iso)
    best = None
    for r in rows:
        if key_field is not None and r.get(key_field) != side and key_field == "side":
            pass
        try:
            rts = pd.Timestamp(str(r["ts_et"])[:19])
        except Exception:
            continue
        if r.get("side") != side:
            continue
        if rts > target:
            continue
        if (target - rts).total_seconds() > lookback_min * 60:
            continue
        if best is None or rts > pd.Timestamp(str(best["ts_et"])[:19]):
            best = r
    return best


def _stop_level(row: Optional[dict], spy: pd.DataFrame, bar_idx: int, side: str) -> float:
    if row is not None:
        exact = row.get("trigger_level_exact")
        if exact is not None:
            return float(exact)
        side_key = "bear_rejection_level_raw" if side == "P" else "bull_reclaim_level_raw"
        v = row.get(side_key)
        if v is not None:
            return float(v)
    return _swing_stop(spy, bar_idx, side)


def walk_one(ctx: "gncw.WalkCtx", wave: dict, fraction: float, account: Optional[dict],
             matched_row: Optional[dict]) -> dict:
    arm = wave["arm"]
    side = wave["side"]
    day = dt.date.fromisoformat(wave["date"])
    trig_ts = pd.Timestamp(f"{wave['date']} {wave['time_entry']}")
    spy_day = ctx.spy_by_date.get(day)
    if spy_day is None or spy_day.empty:
        return {"walk_ok": False, "walk_error": f"no SPY bars cached for {day}"}
    bar_idx, stale = bar_idx_for_ts(ctx.spy_ts, trig_ts.to_pydatetime())
    if bar_idx is None or stale:
        return {"walk_ok": False, "walk_error": "no usable SPY bar at/before entry"}
    stop_level = _stop_level(matched_row, ctx.spy, bar_idx, side)

    symbol = option_symbol(day, wave["strike"], side)
    opt_df = load_contract_bars(symbol, frame="wall-v1")
    if opt_df is None or opt_df.empty:
        return {"walk_ok": False, "walk_error": f"no OPRA cache for {symbol}", "contract": symbol}
    entry_bar = bar_at_or_after(opt_df, trig_ts.to_pydatetime())
    if entry_bar is None:
        return {"walk_ok": False, "walk_error": f"no {symbol} bar at/after entry", "contract": symbol}
    entry_time_et = entry_bar.timestamp_et

    exit_shape = dict(gncw._exit_shape_for_arm(arm, ctx.accounts, ctx.strat))
    exit_shape["tp1_qty_fraction"] = fraction
    exit_cfg = gncw._exit_cfg_for_arm(arm, ctx.core_cfg)
    rtd = grab.ribbon_tick_df_for(opt_df, ctx.ribbon_lookup)

    try:
        res = walk_exit_manager(
            symbol=symbol, side=side, entry_time_et=entry_time_et,
            entry_premium=float(wave["entry_px"]), qty=int(wave["qty_total"]),
            exit_shape=exit_shape, structure_stop_enabled=exit_cfg["structure_stop_enabled"],
            trigger_level=stop_level, strategy="ribbon_ride", time_stop_et=exit_cfg["time_stop_et"],
            opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=spy_day,
            opt_df_resolution="5min", allow_5min=True, all_exits_market=True,
        )
    except Exception as exc:  # noqa: BLE001
        return {"walk_ok": False, "walk_error": f"walk_exit_manager raised: {exc}", "contract": symbol}

    if res.exit_time_et is None:
        return {"walk_ok": False, "walk_error": "unwalkable (no bars after entry)", "contract": symbol}

    tp1_leg = next((lg for lg in res.legs if lg.stage == "tp1"), None)
    runner_exceeded_tp1 = None
    if tp1_leg is not None:
        mask = opt_df["timestamp_et"] > pd.Timestamp(tp1_leg.ts_et)
        after = opt_df.loc[mask]
        runner_exceeded_tp1 = bool(not after.empty and float(after["close"].max()) > tp1_leg.fill_price)

    return {
        "walk_ok": True, "walk_error": None, "contract": symbol,
        "entry_ts": entry_time_et.isoformat(), "entry_px": round(float(wave["entry_px"]), 4),
        "exit_ts": res.exit_time_et.isoformat(), "exit_reason": res.exit_reason,
        "dollar_pnl": res.dollar_pnl, "hold_minutes": res.hold_minutes,
        "had_tp1_leg": tp1_leg is not None,
        "tp1_fill_price": tp1_leg.fill_price if tp1_leg else None,
        "runner_exceeded_tp1_price": runner_exceeded_tp1,
        "stop_level_used": stop_level, "matched_decision_ts": matched_row.get("ts_et") if matched_row else None,
    }


def bootstrap_ci_lower(deltas: list[float], n: int = BOOT_N, seed: int = BOOT_SEED) -> Optional[float]:
    if not deltas:
        return None
    rng = random.Random(seed)
    means = []
    m = len(deltas)
    for _ in range(n):
        sample = [deltas[rng.randrange(m)] for _ in range(m)]
        means.append(sum(sample) / m)
    means.sort()
    idx = int(round(0.025 * (len(means) - 1)))
    return round(means[idx], 4)


def ex_best_day(rows: list[dict]) -> float:
    """net delta with the single best-performing DAY's waves removed entirely (C4
    concentration-disclosure convention)."""
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r["date"]] += r["delta"]
    if not by_day:
        return 0.0
    best_day = max(by_day, key=lambda d: by_day[d])
    return round(sum(r["delta"] for r in rows if r["date"] != best_day), 2)


def summarize(rows: list[dict], window_name: str) -> dict:
    n = len(rows)
    deltas = [r["delta"] for r in rows]
    net = round(sum(deltas), 2)
    exbd = ex_best_day(rows) if rows else None
    ci_lower = bootstrap_ci_lower(deltas) if deltas else None
    share_runner = None
    with_tp1 = [r for r in rows if r.get("control_runner_exceeded_tp1") is not None]
    if with_tp1:
        share_runner = round(sum(1 for r in with_tp1 if r["control_runner_exceeded_tp1"]) / len(with_tp1), 4)
    return {
        "window": window_name, "n_waves": n, "net_delta_dollars": net,
        "ex_best_day_delta_dollars": exbd,
        "bootstrap_ci_lower_2p5_per_wave_delta": ci_lower,
        "bootstrap_n": BOOT_N, "bootstrap_seed": BOOT_SEED,
        "share_waves_runner_exceeded_tp1_price": share_runner,
        "n_with_tp1_leg": len(with_tp1),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="debug: cap n waves walked")
    args = ap.parse_args()

    waves = load_waves()
    log(f"A1: {len(waves)} real waves since 2026-06-28 across arms "
        f"{sorted(set(w['arm'] for w in waves))}")
    per_arm_counts = defaultdict(int)
    for w in waves:
        per_arm_counts[w["arm"]] += 1
    log(f"per-arm wave counts: {dict(per_arm_counts)}")

    if args.limit:
        waves = waves[: args.limit]

    core_rows, fleet_idx = build_decision_indices()
    ctx = gncw.WalkCtx()

    result_rows = []
    n_ok = 0
    error_counts: dict[str, int] = defaultdict(int)
    for i, w in enumerate(waves):
        if w["arm"] in ("safe-2", "bold-2"):
            acct = "safe" if w["arm"] == "safe-2" else "bold"
            matched = _nearest_prior([r for r in core_rows if r.get("account") == acct],
                                      "side", f"{w['date']} {w['time_entry']}", w["side"])
        else:
            matched = _nearest_prior(fleet_idx.get(w["arm"], []), "side",
                                      f"{w['date']} {w['time_entry']}", w["side"])

        control = walk_one(ctx, w, CONTROL_FRAC, None, matched)
        treatment = walk_one(ctx, w, TREATMENT_FRAC, None, matched)
        row = {"wave_id": w["wave_id"], "arm": w["arm"], "date": w["date"],
               "time_entry": w["time_entry"], "side": w["side"], "recorded_pnl": w["recorded_pnl"],
               "control": control, "treatment": treatment}
        if control.get("walk_ok") and treatment.get("walk_ok"):
            row["delta"] = round(treatment["dollar_pnl"] - control["dollar_pnl"], 2)
            row["control_runner_exceeded_tp1"] = control.get("runner_exceeded_tp1_price")
            n_ok += 1
        else:
            err = control.get("walk_error") or treatment.get("walk_error") or "unknown"
            error_counts[err] += 1
        result_rows.append(row)
        if (i + 1) % 25 == 0:
            log(f"... {i+1}/{len(waves)} walked ({n_ok} ok)")

    ok_rows = [r for r in result_rows if "delta" in r]
    log(f"walked {len(result_rows)} waves, {n_ok} ok, {len(result_rows)-n_ok} errored")
    top_errors = sorted(error_counts.items(), key=lambda kv: -kv[1])[:10]
    log(f"top errors: {top_errors}")

    per_arm_full = {}
    per_arm_frozen = {}
    for arm in sorted(set(w["arm"] for w in waves)):
        arm_rows = [r for r in ok_rows if r["arm"] == arm]
        per_arm_full[arm] = summarize(arm_rows, "full_2026-06-28_to_present")
        frozen_rows = [r for r in arm_rows if r["date"] >= FROZEN_START]
        per_arm_frozen[arm] = summarize(frozen_rows, f"frozen_{FROZEN_START}_to_present")

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "prereg": "analysis/recommendations/prereg-tp1-qty-fraction-safe-0-8-10-30-2026-09-05.json",
        "control_fraction": CONTROL_FRAC, "treatment_fraction": TREATMENT_FRAC,
        "n_waves_total": len(waves), "n_walk_ok": n_ok, "n_walk_error": len(waves) - n_ok,
        "top_error_reasons": top_errors,
        "per_arm_wave_counts": dict(per_arm_counts),
        "per_arm_full_window": per_arm_full,
        "per_arm_frozen_window": per_arm_frozen,
        "rows": result_rows,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
