"""gate_net_cost_resolution_bias.py -- T3, GOAL-RIGHT-TAIL-FOLLOWUPS-2026-09-05.

WHAT THIS MEASURES. `gate_net_cost_walk.py` (N2, GOAL-GATE-NET-COST-2026-09-05) walks every
refused-wave counterfactual through `walk_exit_manager` on the real OPRA **5-minute** bar
cache (`load_contract_bars(..., frame="wall-v1")`). The live engine itself ticks (and its own
hand-checks, per that module's `opt_df_override`/`opt_df_resolution` docstring) at 1-minute
resolution when a 1-minute OPRA cache already exists on disk
(`backtest/data/highres/{symbol}_1m_{date}.csv`, `backtest/tools/_option_bars_1min_cache.py`).
A stop/TP/trail that fires mid-bar on the 1-minute tape can walk to a DIFFERENT exit stage,
time, and price than the same trade walked on 5-minute bars -- this module quantifies that
resolution bias so N2's headline $ figures carry an honest error bar instead of an implicit
"5-minute is exact" assumption.

SCOPE, PER THE GOAL. Only rows in `walk-2026-09-05.json` that are (a) `walk_ok: true` AND
(b) already have a 1-minute OPRA CSV cached on disk for their exact `contract` + entry date
are re-walked -- ZERO new data fetch (this reads the cache file directly, never
`_option_bars_1min_cache.fetch_1min_cached`'s REST-fetch branch, which this module never
imports at all). If fewer than 20 rows qualify, this module says so explicitly rather than
reporting a false-confidence n.

REUSES gate_net_cost_walk.py's OWN machinery byte-for-byte (WalkCtx, _iter_wave_buckets,
_row_lookup_index, _stop_level_for_wave_row, _side_from_char, _walk_entry) -- this module
adds NO new walking logic, only a second `_walk_entry` call per qualifying row with
`opt_df_override` set to the cached 1-minute frame and `opt_df_resolution="1min"` (both
parameters `_walk_entry` already exposed for exactly this hand-check use case).

OUTPUT: analysis/gate-net-cost/resolution-bias-2026-09-05.json (full per-row + per-stage
detail) and an appended "## Error bar (T3, 1-min vs 5-min resolution bias)" section on both
analysis/gate-net-cost/GATE-NET-COST-2026-09-05.json and .md. Idempotent (recomputes fully
each run against the on-disk cache + walk-2026-09-05.json; never mutates either input file).

$0, read-only, no new fetch, no trading-path file touched.
"""
from __future__ import annotations

import collections
import json
import statistics
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

import gate_net_cost_walk as gncw  # noqa: E402

WALK_PATH = REPO / "analysis" / "gate-net-cost" / "walk-2026-09-05.json"
OUT_JSON = REPO / "analysis" / "gate-net-cost" / "resolution-bias-2026-09-05.json"
NET_COST_JSON = REPO / "analysis" / "gate-net-cost" / "GATE-NET-COST-2026-09-05.json"
NET_COST_MD = REPO / "analysis" / "gate-net-cost" / "GATE-NET-COST-2026-09-05.md"
HIGHRES_DIR = REPO / "backtest" / "data" / "highres"
MIN_N_FOR_CONFIDENCE = 20


def _read_1min_cache_hit_only(symbol: str, date_et: str) -> "pd.DataFrame | None":
    """Cache-HIT-ONLY read of backtest/data/highres/{symbol}_1m_{date}.csv -- the exact file
    `_option_bars_1min_cache.fetch_1min_cached` writes/reads, but this function NEVER falls
    through to that module's REST-fetch branch (it does not import that module at all), so a
    cache miss returns None rather than triggering a new network fetch -- required by the
    goal's OPERATING RULES ('no new data fetch')."""
    cache_path = HIGHRES_DIR / f"{symbol}_1m_{date_et}.csv"
    if not cache_path.exists():
        return None
    df = pd.read_csv(cache_path)
    # Two column conventions coexist on disk: the _option_bars_1min_cache.py convention
    # (timestamp_et, ET-naive already) and an older/other-producer convention seen on 2 of
    # the 262 qualifying files this session (timestamp, trade_count, vwap already present,
    # presumed UTC or exchange-tz per its own producer -- normalized the same way
    # `_option_bars_1min_cache.fetch_1min_cached` normalizes a fresh REST pull: to ET,
    # tz-naive). Never guessed silently -- disclosed here, not chased further (2/262 rows,
    # both from the SAME contract/date).
    if "timestamp_et" not in df.columns and "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"], utc=True)
        df["timestamp_et"] = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    else:
        df["timestamp_et"] = pd.to_datetime(df["timestamp_et"]).dt.tz_localize(None)
    # The 1-minute cache (backtest/tools/_option_bars_1min_cache.py) writes only
    # timestamp_et/open/high/low/close/volume -- bar_at_or_after (option_pricing_real.py)
    # also reads `vwap` and `trade_count` to build its OptionBar, but neither field is
    # actually CONSUMED downstream for this walk: `_walk_entry` prices entry off
    # `entry_bar.open`, never `.vwap`, and `walk_exit_manager` never reads either field on
    # `opt_df` rows directly (grepped this session: 0 hits). Backfilling vwap=close and
    # trade_count=0 here is therefore a disclosed SCHEMA-COMPATIBILITY shim, not a pricing
    # assumption -- it exists only so the dataclass construction does not KeyError.
    if "vwap" not in df.columns:
        df["vwap"] = df["close"]
    if "trade_count" not in df.columns:
        df["trade_count"] = 0
    return df


def _qualifying_rows(walk_rows: list[dict]) -> list[dict]:
    out = []
    for r in walk_rows:
        if not r.get("walk_ok"):
            continue
        contract = r.get("contract")
        entry_ts = r.get("entry_ts") or ""
        date = entry_ts[:10]
        if not contract or not date:
            continue
        if (HIGHRES_DIR / f"{contract}_1m_{date}.csv").exists():
            out.append(r)
    return out


def _rewalk_one_row_at_1min(row: dict, ctx: "gncw.WalkCtx",
                             core_index: dict, fleet_index: dict) -> "dict[str, Any] | None":
    """Reconstruct the SAME (arm, side, day, trig_ts, stop_level) inputs the 5-min walk used
    for this wave_id (via the same source-row lookup gate_net_cost_walk.run_walk performs),
    then re-call `_walk_entry` with the 1-minute cache substituted for the 5-minute one.
    Returns None (never raises) if the wave can no longer be resolved -- fail-open, matching
    the parent module's own per-row contract."""
    wave_id = row.get("wave_id") or ""
    if "|" not in wave_id:
        return None
    date_s, wave_start = wave_id.split("|", 1)
    account = None
    arm = row.get("arm")
    if arm in gncw.ARM_FOR_CORE_ACCOUNT:
        account = gncw.ARM_FOR_CORE_ACCOUNT[arm]
    try:
        if account is not None:
            src_row = core_index.get((account, wave_start))
        else:
            key_ts = str(wave_start)[:19]
            src_row = fleet_index.get(arm, {}).get((arm, key_ts))
    except Exception:  # noqa: BLE001
        return None
    if src_row is None:
        return None
    side = gncw._side_from_char(src_row.get("side"))
    if side is None:
        return None
    try:
        trig_ts = pd.Timestamp(str(wave_start)[:19])
    except Exception:  # noqa: BLE001
        return None
    import datetime as _dt
    try:
        day = _dt.date.fromisoformat(date_s)
    except Exception:  # noqa: BLE001
        return None
    bar_idx, stale = gncw.bar_idx_for_ts(ctx.spy_ts, trig_ts.to_pydatetime())
    if bar_idx is None or stale:
        return None
    stop_level = gncw._stop_level_for_wave_row(src_row, ctx.spy, bar_idx, side)

    opt_1min = _read_1min_cache_hit_only(row["contract"], date_s)
    if opt_1min is None or opt_1min.empty:
        return None

    return gncw._walk_entry(ctx, arm=arm, side=side, day=day, trig_ts=trig_ts,
                             stop_level=stop_level, opt_df_override=opt_1min,
                             opt_df_resolution="1min")


def run() -> dict[str, Any]:
    walk_out = json.loads(WALK_PATH.read_text(encoding="utf-8"))
    walk_rows = walk_out.get("rows", [])
    qualifying = _qualifying_rows(walk_rows)

    if not qualifying:
        return {
            "n_walked_ok_5min": sum(1 for r in walk_rows if r.get("walk_ok")),
            "n_qualifying_1min_cached": 0,
            "insufficient_n": True,
            "note": "0 walk_ok rows have a 1-minute OPRA cache on disk -- no re-walk possible "
                    "without a new fetch, which this module never performs.",
        }

    refusals = json.loads(gncw.REFUSALS_PATH.read_text(encoding="utf-8"))
    fleet_arms = ["safe-3", "risky-1", "risky-3"]
    core_index, fleet_index = gncw._row_lookup_index(fleet_arms)
    ctx = gncw.WalkCtx()

    per_stage_deltas: dict[str, list[float]] = collections.defaultdict(list)
    per_row: list[dict[str, Any]] = []
    n_rewalked = 0
    for row in qualifying:
        res_1min = _rewalk_one_row_at_1min(row, ctx, core_index, fleet_index)
        if res_1min is None or not res_1min.get("walk_ok"):
            per_row.append({
                "wave_id": row["wave_id"], "contract": row["contract"],
                "rewalk_ok": False,
                "rewalk_error": (res_1min or {}).get("walk_error", "could not reconstruct wave inputs"),
            })
            continue
        n_rewalked += 1
        dollars_5min = row.get("realized_if_taken_dollars")
        dollars_1min = res_1min.get("realized_if_taken_dollars")
        delta = None
        if dollars_5min is not None and dollars_1min is not None:
            delta = round(dollars_5min - dollars_1min, 4)
        # Stage bucket keyed on the 5-min walk's OWN exit stage (the stage the N2 net-cost
        # table already attributes this row to) -- so the error bar reads against the SAME
        # stage buckets that table reports, even when the 1-min walk exits at a different stage.
        stage = row.get("exit_stage") or "unknown"
        if delta is not None:
            per_stage_deltas[stage].append(delta)
        per_row.append({
            "wave_id": row["wave_id"], "contract": row["contract"],
            "rewalk_ok": True,
            "exit_stage_5min": row.get("exit_stage"), "exit_stage_1min": res_1min.get("exit_stage"),
            "exit_ts_5min": row.get("exit_ts"), "exit_ts_1min": res_1min.get("exit_ts"),
            "dollars_5min": dollars_5min, "dollars_1min": dollars_1min,
            "delta_5min_minus_1min": delta,
            "stage_changed": row.get("exit_stage") != res_1min.get("exit_stage"),
        })

    stage_summary = {}
    all_deltas: list[float] = []
    for stage, deltas in sorted(per_stage_deltas.items()):
        all_deltas.extend(deltas)
        n = len(deltas)
        n_pos = sum(1 for d in deltas if d > 0)
        n_neg = sum(1 for d in deltas if d < 0)
        n_zero = n - n_pos - n_neg
        stage_summary[stage] = {
            "n": n,
            "mean_delta_5min_minus_1min": round(sum(deltas) / n, 2) if n else None,
            "median_delta_5min_minus_1min": round(statistics.median(deltas), 2) if n else None,
            "n_5min_overstates": n_pos, "n_5min_understates": n_neg, "n_tied": n_zero,
            "sign_consistency_share": round(max(n_pos, n_neg) / n, 4) if n else None,
        }

    overall = None
    if all_deltas:
        n = len(all_deltas)
        n_pos = sum(1 for d in all_deltas if d > 0)
        n_neg = sum(1 for d in all_deltas if d < 0)
        overall = {
            "n": n,
            "mean_delta_5min_minus_1min": round(sum(all_deltas) / n, 2),
            "median_delta_5min_minus_1min": round(statistics.median(all_deltas), 2),
            "n_5min_overstates": n_pos, "n_5min_understates": n - n_pos - n_neg + n_neg,
            "sign_consistency_share": round(max(n_pos, n_neg) / n, 4),
            "n_stage_changed": sum(1 for r in per_row if r.get("rewalk_ok") and r.get("stage_changed")),
        }

    return {
        "_doc": __doc__,
        "n_walked_ok_5min": sum(1 for r in walk_rows if r.get("walk_ok")),
        "n_qualifying_1min_cached": len(qualifying),
        "n_rewalked_ok": n_rewalked,
        "insufficient_n": len(qualifying) < MIN_N_FOR_CONFIDENCE,
        "min_n_for_confidence": MIN_N_FOR_CONFIDENCE,
        "per_exit_stage": stage_summary,
        "overall": overall,
        "rows": per_row,
    }


def _fmt_money(x: "float | None") -> str:
    return "n/a" if x is None else f"${x:,.2f}"


def _append_json(result: dict) -> None:
    if NET_COST_JSON.exists():
        doc = json.loads(NET_COST_JSON.read_text(encoding="utf-8"))
    else:
        doc = {}
    doc["resolution_bias_t3_2026_09_05"] = result
    NET_COST_JSON.write_text(json.dumps(doc, indent=1), encoding="utf-8")


def _append_md(result: dict) -> None:
    marker = "## Error bar (T3, 1-min vs 5-min resolution bias)"
    lines = [marker, ""]
    lines.append(
        f"Of {result['n_walked_ok_5min']} rows N2 walked OK on 5-min OPRA bars, "
        f"{result['n_qualifying_1min_cached']} already have a 1-minute OPRA cache on disk "
        f"(`backtest/data/highres/`) -- re-walked via the SAME `walk_exit_manager` core "
        f"(`gate_net_cost_walk._walk_entry`, `opt_df_resolution=\"1min\"`), zero new fetch. "
        f"{result['n_rewalked_ok']} of those re-walked successfully."
    )
    if result.get("insufficient_n"):
        lines.append("")
        lines.append(
            f"**n={result['n_qualifying_1min_cached']} < {result['min_n_for_confidence']}** -- "
            "reported below as UNVERIFIED / insufficient n, not a negative finding.")
    lines.append("")
    lines.append("| Exit stage | n | mean $ delta (5min-1min) | median $ delta | 5min overstates | 5min understates | sign-consistency |")
    lines.append("|---|---|---|---|---|---|---|")
    for stage, s in sorted(result.get("per_exit_stage", {}).items()):
        lines.append(
            f"| {stage} | {s['n']} | {_fmt_money(s['mean_delta_5min_minus_1min'])} | "
            f"{_fmt_money(s['median_delta_5min_minus_1min'])} | {s['n_5min_overstates']} | "
            f"{s['n_5min_understates']} | {s['sign_consistency_share']:.2%} |")
    overall = result.get("overall")
    if overall:
        lines.append(
            f"| **ALL STAGES** | {overall['n']} | {_fmt_money(overall['mean_delta_5min_minus_1min'])} | "
            f"{_fmt_money(overall['median_delta_5min_minus_1min'])} | {overall['n_5min_overstates']} | "
            f"{overall['n_5min_understates']} | {overall['sign_consistency_share']:.2%} |")
        lines.append("")
        lines.append(f"Exit stage changed between the 5-min and 1-min walk on {overall['n_stage_changed']} "
                      f"of {overall['n']} rows.")
    lines.append("")
    lines.append(
        "This section is APPENDED by `setup/scripts/gate_net_cost_resolution_bias.py` (T3, "
        "GOAL-RIGHT-TAIL-FOLLOWUPS-2026-09-05) and is idempotent -- a re-run replaces this "
        "section in place rather than duplicating it.")
    block = "\n".join(lines)

    text = NET_COST_MD.read_text(encoding="utf-8") if NET_COST_MD.exists() else ""
    start = text.find(marker)
    if start == -1:
        new_text = text.rstrip() + "\n\n" + block + "\n"
    else:
        # Replace from the marker to the next top-level "## " heading (or EOF).
        rest = text[start + len(marker):]
        next_marker_rel = rest.find("\n## ")
        end = start + len(marker) + (next_marker_rel if next_marker_rel != -1 else len(rest))
        new_text = text[:start] + block + "\n" + text[end:]
    NET_COST_MD.write_text(new_text, encoding="utf-8")


def main() -> int:
    result = run()
    OUT_JSON.write_text(json.dumps(result, indent=1), encoding="utf-8")
    _append_json(result)
    _append_md(result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("rows", "_doc")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
