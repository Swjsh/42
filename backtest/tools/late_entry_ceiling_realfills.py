"""late_entry_ceiling_realfills.py -- Q2 forensic (J-directed 2026-07-23). Upgrades the
2026-07-21 chef study (SPY-spot-direction proxy) to REAL per-episode option-economics P&L
via backtest/lib/exit_manager_walk.py for every bear-only SKIP_LATE_ENTRY episode across the
engine's full retained decision history.

Frozen pre-reg: analysis/recommendations/late-entry-ceiling-realfills-prereg-2026-07-23.json.

ANALYSIS ONLY: no trading-path file touched. No broker imports beyond the pre-existing real-
OPRA cache (backtest/data/options/*.csv, extended this session via the read-only
_alpaca_creds.py market-data pattern -- tools/_fetch_late_entry_contracts_2026_07_23.py,
tools/_fetch_spy_5m_2026_07_23.py -- both already run, cache populated before this script).

Run: backtest/.venv/Scripts/python.exe backtest/tools/late_entry_ceiling_realfills.py
"""
from __future__ import annotations

import datetime as dt
import glob
import hashlib
import json
import math
import statistics as _stats
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]           # backtest/
ROOT = REPO.parent
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

import strategies as fleet_strategies  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

DATA = REPO / "data"
SPY_FILE = DATA / "spy_5m_2025-01-01_2026-07-22.csv"
SPY_SUPPLEMENT_2026_07_23 = DATA / "spy_5m_2026-07-23_supplement.csv"
TIME_STOP_ET = dt.time(15, 40)   # current live params.json value, verified 2026-07-23
GAP_MAX_SEC = 180                # <=3 min = same episode, matches 07-21 chef study convention

DECISION_FILES = ["automation/state/core-decisions.jsonl"] + glob.glob(
    str(ROOT / "automation" / "state" / "fleet" / "*" / "decisions.jsonl"))

PREREG = ROOT / "analysis" / "recommendations" / "late-entry-ceiling-realfills-prereg-2026-07-23.json"
OUT_JSON = ROOT / "analysis" / "recommendations" / "late-entry-ceiling-realfills-2026-07-23.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "late-entry-ceiling-realfills-2026-07-23.md"


def log(msg: str) -> None:
    print(f"[late-entry-realfills] {msg}", flush=True)


def load_spy_full() -> pd.DataFrame:
    base = pd.read_csv(SPY_FILE)
    base["timestamp_et"] = pd.to_datetime(base["timestamp_et"])
    if SPY_SUPPLEMENT_2026_07_23.exists():
        sup = pd.read_csv(SPY_SUPPLEMENT_2026_07_23)
        sup["timestamp_et"] = pd.to_datetime(sup["timestamp_et"])
        base = pd.concat([base, sup], ignore_index=True).sort_values("timestamp_et").reset_index(drop=True)
    return base


def build_ribbon_lookup(spy_df: pd.DataFrame) -> pd.DataFrame:
    ts = spy_df["timestamp_et"]
    ts_naive = ts.dt.tz_localize(None) if getattr(ts.dt, "tz", None) is not None else ts
    rth_mask = (ts_naive.dt.time >= dt.time(9, 30)) & (ts_naive.dt.time < dt.time(16, 0))
    spy_rth = spy_df.loc[rth_mask].assign(timestamp_et=ts_naive.loc[rth_mask]).reset_index(drop=True)
    ribbon = compute_ribbon(spy_rth["close"])
    out = spy_rth[["timestamp_et"]].copy()
    out["stack"] = ribbon["stack"].values
    return out.sort_values("timestamp_et").reset_index(drop=True)


def ribbon_tick_df_for(opt_df: pd.DataFrame, ribbon_lookup: pd.DataFrame) -> pd.DataFrame:
    left = opt_df[["timestamp_et"]].copy()
    if getattr(left["timestamp_et"].dt, "tz", None) is not None:
        left["timestamp_et"] = left["timestamp_et"].dt.tz_localize(None)
    right = ribbon_lookup.copy()
    left = left.sort_values("timestamp_et", kind="stable")
    right = right.sort_values("timestamp_et", kind="stable")
    merged = pd.merge_asof(left, right, on="timestamp_et", direction="backward")
    assert len(merged) == len(opt_df)
    return merged.reset_index(drop=True)[["stack"]]


def load_bear_skip_late_entry_rows() -> list[dict]:
    rows = []
    for fp in DECISION_FILES:
        p = Path(fp)
        if not p.exists():
            continue
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("action") == "SKIP_LATE_ENTRY" and d.get("side") == "P" and d.get("verdict") == "ENTER_BEAR":
                    rows.append({"src": fp, "ts": d.get("ts_et"), "account": d.get("account"),
                                "spy": d.get("spy"), "trigger_level": d.get("trigger_level_exact")})
    return rows


def group_episodes(rows: list[dict]) -> list[dict]:
    rows = sorted(rows, key=lambda r: (r["account"], r["ts"]))
    episodes = []
    cur = None
    for r in rows:
        ts = dt.datetime.fromisoformat(r["ts"])
        if cur is None or r["account"] != cur["account"] or (ts - cur["last_ts"]).total_seconds() > GAP_MAX_SEC:
            if cur is not None:
                episodes.append(cur)
            cur = {"account": r["account"], "first_ts": ts, "last_ts": ts, "n_fires": 1,
                   "first_spy": r["spy"], "trigger_level": r["trigger_level"]}
        else:
            cur["last_ts"] = ts
            cur["n_fires"] += 1
            if cur["trigger_level"] is None and r["trigger_level"] is not None:
                cur["trigger_level"] = r["trigger_level"]
    if cur is not None:
        episodes.append(cur)
    return episodes


def _content_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def preflight(episodes: list[dict]) -> dict:
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    sig = [{"account": e["account"], "first_ts": e["first_ts"].isoformat()} for e in episodes]
    return {
        "n_episodes": len(episodes),
        "n_episodes_ok": len(episodes) == preg["population"]["n_episodes"],
        "content_sha256_16": _content_hash(sig)[:16],
        "preregistration_version": preg.get("version"),
    }


def one_sided_p_mean_gt_0(pnls: list[float]) -> "float | None":
    """Two-tailed-symmetric one-sided p that the true mean is > 0, from a t-approximation.
    None below n=2 (undefined). Pure, no I/O."""
    n = len(pnls)
    if n < 2:
        return None
    mean = _stats.mean(pnls)
    sd = _stats.stdev(pnls)
    t = (mean / (sd / math.sqrt(n))) if sd > 0 else float("inf")
    if not math.isfinite(t):
        return 0.0 if mean > 0 else 1.0
    p = 0.5 * math.erfc(abs(t) / math.sqrt(2))
    return round(1.0 - p, 4) if t < 0 else round(p, 4)


ADVISORY_FLOOR = 15


def compute_verdict(replayed: list[dict]) -> dict:
    """Pure function: replayed episode rows (each with 'pnl', 'date', 'episode_first_block_et')
    -> {verdict, verdict_reason, ...stats}. Operationalizes the frozen pre-reg's prose
    ('clearly positive' for MOVE_TO_X, 'negative or flat' for KEEP) via three pre-committed,
    non-cherry-picked statistics: sign, one-sided significance (p<=0.25, generous given small n),
    and win rate (>=0.45, a bare-coin-flip bar) -- ALL must hold for MOVE_TO_X."""
    n = len(replayed)
    pnls = [r["pnl"] for r in replayed]
    total_pnl = round(sum(pnls), 2)
    wins = [p for p in pnls if p > 0]
    win_rate = round(len(wins) / n, 4) if n else None
    p_one_sided_gt0 = one_sided_p_mean_gt_0(pnls)
    n_distinct_signal_buckets = len(set((r["date"], r["episode_first_block_et"][11:16]) for r in replayed))

    clearly_positive = bool(total_pnl > 0 and p_one_sided_gt0 is not None and p_one_sided_gt0 <= 0.25
                            and (win_rate or 0) >= 0.45)

    if n < ADVISORY_FLOOR or n_distinct_signal_buckets < ADVISORY_FLOOR:
        verdict = "RETEST_INSUFFICIENT_N"
        verdict_reason = (f"n={n} replayed episodes ({n_distinct_signal_buckets} distinct "
                          f"date+time signal buckets, since safe/bold mirror the same underlying "
                          f"trigger) -- below the advisory evidence floor ({ADVISORY_FLOOR}).")
    elif not clearly_positive:
        verdict = "KEEP"
        verdict_reason = (f"n={n} clears the raw-leg floor; aggregate real-fills P&L is "
                          f"${total_pnl:+.2f} but NOT clearly positive: one-sided p(mean>0)="
                          f"{p_one_sided_gt0} and win rate={win_rate} -- the ceiling is correctly "
                          f"avoiding a low-hit-rate cohort with no demonstrable edge.")
    else:
        verdict = "MOVE_TO_X"
        verdict_reason = (f"n={n} clears the floor; aggregate real-fills P&L ${total_pnl:+.2f}, "
                          f"p(mean>0)={p_one_sided_gt0}, win_rate={win_rate} -- clearly positive by "
                          f"the pre-registered bar. Candidate for loosening (check the band detail "
                          f"before acting on the 15:45+ scar band, which stays blocked regardless "
                          f"of any P&L argument -- exchange constraint, not a strategy-quality one).")

    return {
        "verdict": verdict, "verdict_reason": verdict_reason, "total_pnl": total_pnl, "n": n,
        "win_rate": win_rate, "mean_pnl_per_leg": round(total_pnl / n, 2) if n else None,
        "p_one_sided_mean_gt_0": p_one_sided_gt0,
        "n_distinct_date_time_signal_buckets": n_distinct_signal_buckets,
        "clearly_positive_by_prereg_bar": clearly_positive,
    }


def replay_episode(ep: dict, control_shape: dict, spy_full: pd.DataFrame,
                   ribbon_lookup: pd.DataFrame) -> dict:
    date = ep["first_ts"].date()
    strike = round(ep["first_spy"])
    symbol = option_symbol(date, strike, "P")
    opt_df = load_contract_bars(symbol)
    if opt_df is None or opt_df.empty:
        return {"symbol": symbol, "date": str(date), "account": ep["account"],
                "status": "NO_OPRA_CACHE", "pnl": None}

    day_spy = spy_full.loc[spy_full["timestamp_et"].dt.date == date].reset_index(drop=True)
    if day_spy.empty:
        return {"symbol": symbol, "date": str(date), "account": ep["account"],
                "status": "NO_SPY_DAY", "pnl": None}

    # entry premium: contract's OWN bar open at/after the first block-fire minute
    opt_ts = opt_df["timestamp_et"]
    if getattr(opt_ts.dt, "tz", None) is not None:
        opt_ts = opt_ts.dt.tz_localize(None)
        opt_df = opt_df.assign(timestamp_et=opt_ts)
    entry_bar = opt_df.loc[opt_ts >= ep["first_ts"]]
    if entry_bar.empty:
        return {"symbol": symbol, "date": str(date), "account": ep["account"],
                "status": "NO_ENTRY_BAR", "pnl": None}
    entry_row = entry_bar.iloc[0]
    entry_time_et = entry_row["timestamp_et"].to_pydatetime()
    entry_premium = float(entry_row["open"])

    rtd = ribbon_tick_df_for(opt_df, ribbon_lookup)
    res = walk_exit_manager(
        symbol=symbol, side="P", entry_time_et=entry_time_et, entry_premium=entry_premium, qty=3,
        exit_shape=control_shape, structure_stop_enabled=True, trigger_level=ep["trigger_level"],
        strategy="ribbon_ride", time_stop_et=TIME_STOP_ET, opt_df=opt_df, ribbon_tick_df=rtd,
        five_min_spy_df=day_spy,
    )
    return {
        "symbol": symbol, "date": str(date), "account": ep["account"],
        "episode_first_block_et": ep["first_ts"].isoformat(), "episode_last_block_et": ep["last_ts"].isoformat(),
        "n_block_fires": ep["n_fires"], "spy_at_first_block": ep["first_spy"],
        "trigger_level": ep["trigger_level"], "status": "REPLAYED",
        "entry_time_et": entry_time_et.isoformat(), "entry_premium": round(entry_premium, 4),
        "pnl": res.dollar_pnl, "exit_reason": res.exit_reason, "hold_minutes": res.hold_minutes,
        "resolved_stop_mode": res.stop_mode,
    }


def main() -> int:
    rows = load_bear_skip_late_entry_rows()
    episodes = group_episodes(rows)
    pf = preflight(episodes)
    log(f"preflight: {pf}")
    if not pf["n_episodes_ok"]:
        print("[late-entry-realfills] PREFLIGHT FAILED -- episode population drifted from the "
              "frozen pre-registration. Aborting.", file=sys.stderr)
        return 1

    log("loading SPY 5m (base + 2026-07-23 supplement)")
    spy_full = load_spy_full()
    log(f"  spy_full rows={len(spy_full)} range={spy_full['timestamp_et'].min()}..{spy_full['timestamp_et'].max()}")
    ribbon_lookup = build_ribbon_lookup(spy_full)

    control_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    log(f"control_shape={control_shape}")

    results = [replay_episode(ep, control_shape, spy_full, ribbon_lookup) for ep in episodes]
    replayed = [r for r in results if r["status"] == "REPLAYED"]
    excluded = [r for r in results if r["status"] != "REPLAYED"]
    log(f"n_episodes={len(episodes)} n_replayed={len(replayed)} n_excluded={len(excluded)}")
    for r in excluded:
        log(f"  EXCLUDED {r['symbol']} {r['status']}")

    by_account = defaultdict(list)
    for r in replayed:
        by_account[r["account"]].append(r)
    per_account = {acct: {"n": len(rs), "total_pnl": round(sum(r["pnl"] for r in rs), 2),
                          "win_rate": round(sum(1 for r in rs if r["pnl"] > 0) / len(rs), 4) if rs else None}
                   for acct, rs in by_account.items()}

    by_exit_reason = defaultdict(list)
    for r in replayed:
        key = r["exit_reason"].split(" @")[0]
        by_exit_reason[key].append(r["pnl"])
    per_exit_reason = {k: {"n": len(v), "total_pnl": round(sum(v), 2)} for k, v in by_exit_reason.items()}

    vd = compute_verdict(replayed)
    total_pnl, n, win_rate = vd["total_pnl"], vd["n"], vd["win_rate"]
    verdict, verdict_reason = vd["verdict"], vd["verdict_reason"]
    p_one_sided_gt0 = vd["p_one_sided_mean_gt_0"]
    n_distinct_signal_buckets = vd["n_distinct_date_time_signal_buckets"]
    clearly_positive = vd["clearly_positive_by_prereg_bar"]

    out = {
        "_doc": "Q2 late-entry-ceiling real-fills upgrade -- frozen pre-registered, real OPRA "
                "fills via exit_manager_walk, bear-only SKIP_LATE_ENTRY episodes. ANALYSIS ONLY.",
        "generated_at": dt.datetime.now().isoformat(),
        "preregistration_file": str(PREREG.relative_to(ROOT)).replace("\\", "/"),
        "preflight": pf,
        "control_shape": control_shape,
        "population": {"n_episodes": len(episodes), "n_replayed": n, "n_excluded": len(excluded),
                       "excluded_detail": excluded},
        "headline": {"total_pnl": total_pnl, "n": n, "win_rate": win_rate,
                    "mean_pnl_per_leg": round(total_pnl / n, 2) if n else None,
                    "p_one_sided_mean_gt_0": p_one_sided_gt0,
                    "n_distinct_date_time_signal_buckets": n_distinct_signal_buckets,
                    "clearly_positive_by_prereg_bar": clearly_positive},
        "per_account": per_account,
        "per_exit_reason": per_exit_reason,
        "verdict": verdict, "verdict_reason": verdict_reason,
        "advisory_evidence_floor": ADVISORY_FLOOR,
        "episode_detail": replayed,
        "reconciliation_2026_07_21_chef_study": (
            "strategy/candidates/2026-07-21-202600-late-entry-ceiling-reconsider.md used a "
            "SPY-spot-direction proxy on 19 ALL-DIRECTION episodes (10-31% favorable-direction "
            "rate depending on ceiling tested) and found REJECTED (do not loosen). This study "
            "restricts to n={} BEAR-ONLY episodes (larger/fresher window, 07-07..07-23 vs that "
            "study's 07-07..07-21) and replays REAL option P&L via exit_manager_walk instead of "
            "a spot proxy.".format(n)
        ),
        "disclosures": [
            "Strike convention: ATM (round(SPY spot at first block-fire)) uniformly for BOTH "
            "accounts -- the blocked entries never reached strike selection. Matches Safe's real "
            "V15_SAFE_TIERS convention exactly; Bold's real convention is OTM-2, so Bold-episode "
            "P&L here is a same-methodology-as-Safe approximation, not Bold's actual tier -- "
            "disclosed, not hidden.",
            "qty=3 (Rule 6 floor) uniformly -- blocked entries never reached position sizing.",
            "trigger_level used only where directly logged in the live decision "
            "(trigger_level_exact, 2/21 episodes); all others fall back to stop_mode=='premium' "
            "(premium_stop_pct=-0.20) identically to how a real entry with no recoverable level "
            "resolves live -- never a fabricated level.",
            "C6 fill-mark convention (exit_manager_walk.py): market-style stages fill at that "
            "bar's close minus $0.02 slippage; limit-style stages fill exactly at the triggered "
            "premium level. Frictionless beyond that.",
            "2026-07-23's SPY 5-min series comes from a same-session supplemental fetch "
            "(spy_5m_2026-07-23_supplement.csv, read-only market data, same _alpaca_creds.py "
            "pattern as tools/fetch_option_data.py) -- the shared cache stops at 2026-07-22.",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")
    log(f"VERDICT: {verdict} -- {verdict_reason}")
    return 0


def write_markdown(out: dict) -> None:
    h = out["headline"]
    L = [
        "# Q2 -- Late-entry ceiling real-fills upgrade (2026-07-23)",
        "",
        f"Generated {out['generated_at']}. Runner: `backtest/tools/late_entry_ceiling_realfills.py`. "
        f"Pre-reg: `{out['preregistration_file']}`.",
        "",
        f"## VERDICT: **{out['verdict']}**",
        "",
        out["verdict_reason"],
        "",
        f"**Decisive number:** aggregate real-fills P&L across n={h['n']} replayed bear-only "
        f"SKIP_LATE_ENTRY episodes = ${h['total_pnl']:+,.2f}, win rate {h['win_rate']}.",
        "",
        f"Population: {out['population']['n_episodes']} episodes total, {out['population']['n_replayed']} "
        f"replayed, {out['population']['n_excluded']} excluded (no OPRA/SPY coverage).",
        "",
        "## Per account",
        "",
        "| account | n | total pnl | win rate |",
        "|---|--:|--:|--:|",
    ]
    for acct, v in out["per_account"].items():
        L.append(f"| {acct} | {v['n']} | ${v['total_pnl']:+,.2f} | {v['win_rate']} |")
    L += ["", "## Per exit reason", "", "| exit reason | n | total pnl |", "|---|--:|--:|"]
    for k, v in out["per_exit_reason"].items():
        L.append(f"| {k} | {v['n']} | ${v['total_pnl']:+,.2f} |")
    L += [
        "",
        "## Episode detail",
        "",
        "| date | account | block time | n fires | SPY | strike | trigger | entry prem | pnl | exit reason |",
        "|---|---|---|--:|--:|--:|--:|--:|--:|---|",
    ]
    for r in out["episode_detail"]:
        L.append(f"| {r['date']} | {r['account']} | {r['episode_first_block_et'][11:16]} | "
                 f"{r['n_block_fires']} | {r['spy_at_first_block']} | {r['symbol'][-8:]} | "
                 f"{r.get('trigger_level')} | {r['entry_premium']} | ${r['pnl']:+,.2f} | {r['exit_reason']} |")
    if out["population"]["excluded_detail"]:
        L += ["", "## Excluded episodes", "", "| symbol | date | account | status |", "|---|---|---|---|"]
        for e in out["population"]["excluded_detail"]:
            L.append(f"| {e['symbol']} | {e['date']} | {e['account']} | {e['status']} |")
    L += [
        "",
        "## Reconciliation vs the 2026-07-21 chef study",
        "",
        out["reconciliation_2026_07_21_chef_study"],
        "",
        "## Disclosed limitations",
        "",
    ]
    for d in out["disclosures"]:
        L.append(f"- {d}")
    L += [
        "",
        "---",
        "_Source: `backtest/tools/late_entry_ceiling_realfills.py`. Full per-episode detail in "
        "the companion `.json`._",
    ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
