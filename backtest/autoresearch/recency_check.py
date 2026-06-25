"""RECENCY-CONFIRMATION TRACKER — the operationalized CONFIRM-BEFORE-CAPITAL gate.

Generalizes the one-shot `_sunday_fresh_revalidation.py` (which hard-coded the
2026-05-30..06-18 window) into a REUSABLE weekly check. As real OPRA fills accumulate,
this answers "have the edges re-confirmed positive on the freshest weeks yet?" and emits a
machine VERDICT per edge AND per book so NO live flip / capital-scale proceeds on an edge
whose recency verdict is RED, and capital scaling waits for CONFIRM (the yellow-flag gate).

WHAT IT REUSES BYTE-FOR-BIT (no edits to any watcher / params / risk_gate / orchestrator /
heartbeat — Sunday money-path guard):
  - the validated detectors, imported from the same harness modules the Sunday script used
      #1 vwap_continuation        -> _edgehunt_vwap_continuation.detect_signals (THE LIVE detector)
      #2 vwap_reclaim_failed_break -> _sub_struct_vwap_reclaim_failed_break.detect_signals
      #4 vix_regime_dayside        -> _b5_vix_regime_dayside.detect_opt_signals (robust b5 cfg)
  - the real-OPRA fill path (lib.simulator_real.simulate_trade_real) — the WR authority (C1)
  - the data-merge + normalization helpers (_normalize_spy / _align_vix / build_day_contexts)
  - the strike pickers (_strike_from_spot / _nearest_cached_strike) and the b5 robust cfg loader

WHAT IT GENERALIZES:
  - The lookback window is PARAMETERIZED. By default it auto-reads the OPRA cache last-date from
    automation/state/data-coverage.json (option_chain_realfills.last) and looks back
    RECENCY_LOOKBACK_TRADING_DAYS (default 25) trading days of REAL fills from there. Override via
    --lookback / --end / --start. This way the same code runs weekly as the cache extends.
  - Per-edge, per-tier AND per-book VERDICTS are emitted (CONFIRM / YELLOW / RED) against a
    documented n-floor (CONFIRM_N_FLOOR, default 10):
        CONFIRM = recent expectancy/tr > 0 AND n >= floor
        YELLOW  = positive but n < floor, OR mixed (recent <=0 but full-OOS > 0 and n < floor)
        RED     = recent expectancy clearly negative (<0) AND n >= floor
  - CAP-AWARE + PER-ACCOUNT QTY: the verdict is measured on the REALIZABLE book. qty is per
    account (Safe 3 / Bold 5, QTY_BY_ACCOUNT) and lib.cap_admission (-> risk_gate.check_order,
    the default order-admission gate) is applied per account at current equity (Safe $2,000 /
    Bold $1,648) so a fill the live engine would BLOCK is EXCLUDED from the measured book.
    Bold's PRIMARY book is ATM (affordable, median order $680 < $824 cap); ITM-2 is UNAFFORDABLE
    (90.6% RISK_CAP block, B9 re-score) and demoted to a LABELED future-reference (books_future_
    reference) that re-qualifies once Bold equity >= ~$3,570.
  - Writes automation/state/recency-confirmation.json (machine) and appends a dated one-line
    summary to automation/overnight/STATUS.md (the wake-signal).

WEEKLY CADENCE: run as part of the weekly-review / OP-11 OUTER loop (Sunday or any after-hours
evening as recent fills accrue). The gate it enforces: a RED recency verdict on an edge BLOCKS a
live flip of that edge; capital scaling on an edge waits for CONFIRM. Per-book RED is a portfolio
sizing brake. See markdown/planning/LIVE-PATH-WORKPACKAGE.md (confirm-before-capital gate).

DISCLOSURE (C1/C3/C7/OP-14/OP-20): real OPRA fills only (the WR authority); per-trade EXPECTANCY,
not WR alone; recent-window n is SMALL by design (~3-5 trading weeks) — reported honestly, never
hidden; SPY-direction != option edge (C3/L58). RESEARCH ONLY; no live edit, no orders.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/recency_check.py
     [--lookback N] [--end YYYY-MM-DD] [--start YYYY-MM-DD] [--floor N]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    _nearest_cached_strike,
    _strike_from_spot,
    Signal,
)
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
    detect_signals as detect_vwap_continuation,
)
from autoresearch._sub_struct_vwap_reclaim_failed_break import (  # noqa: E402
    detect_signals as detect_reclaim_failed_break,
)
from autoresearch._b5_vix_regime_dayside import (  # noqa: E402
    causal_vix_median,
    vix_slope,
    detect_opt_signals as detect_vix_regime_dayside,
    _swing_stop,
    VIX_MEDIAN_BARS,
    VIX_SLOPE_BARS,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib import cap_admission  # noqa: E402  (the default order-admission gate; risk_gate.check_order)

DATA = REPO / "data"
DATA_COVERAGE = ROOT / "automation" / "state" / "data-coverage.json"
OUT_JSON = ROOT / "automation" / "state" / "recency-confirmation.json"
STATUS_MD = ROOT / "automation" / "overnight" / "STATUS.md"
B5_SCORECARD = ROOT / "analysis" / "recommendations" / "b5-vix-regime-dayside.json"

# ── gate parameters (documented; weekly-stable) ──────────────────────────────────
RECENCY_LOOKBACK_TRADING_DAYS = 25   # default newest-N trading days of REAL fills
CONFIRM_N_FLOOR = 10                 # documented floor: CONFIRM requires recent n >= this
OOS_2026_START = dt.date(2026, 1, 1)  # the larger-n companion window (full OOS 2026)

# sim convention shared with the harnesses (NEG=ITM, POS=OTM)
PREMIUM_STOP_PCT = -0.08
MAX_STRIKE_STEPS = 4

# Per-account live qty (was a single hardcoded QTY=3 — Bold's live qty is 5, Safe 3).
# Used both for the sim (P&L scales with qty) AND for the cap-admission gate.
QTY_BY_ACCOUNT = {"safe": 3, "bold": 5}

# Per-account current equity the cap-admission gate measures against (B9 re-score facts;
# matches analysis/recommendations/B9-CAP-AWARE-RESCORE.json accounts block exactly).
# Safe-2 $2,000/qty3/$600 cap ; Bold $1,648/qty5/$824 cap.
EQUITY_BY_ACCOUNT = {"safe": 2_000.0, "bold": 1_648.0}

# Edge -> validated tier(s). sim_offset: 0=ATM, -2=ITM-2, +2=OTM-2 (the live Safe-2 leak).
# Per the brief: #1 validated ATM (Safe-2) + ITM-2 (Bold); #2 validated ATM + ITM-2;
# #4 validated ATM. The book composition (which edges/tiers feed which account) below.
EDGE_TIERS = {
    "vwap_continuation":          {"ATM": 0, "ITM-2": -2, "OTM-2_live_leak": 2},
    "vwap_reclaim_failed_break":  {"ATM": 0, "ITM-2": -2},
    "vix_regime_dayside":         {"ATM": 0},
}

# Books: per-account, cap-aware on the REALIZABLE (affordable) tier.
#   Safe-2 = ATM #1+#2+#4  (affordable: ATM median order $414 < $600 cap).
#   Bold   = ATM #1+#2     (PRIMARY, affordable: ATM median order $680 < $824 cap).
#
# Bold's PRIMARY book was switched from ITM-2 to ATM: the B9 cap-aware re-score PROVED
# Bold ITM-2 is UNAFFORDABLE (median qty5 order $1,285 > $824 cap, 90.6% RISK_CAP block →
# a survivorship stub) — measuring Bold on ITM-2 reported a FICTIONAL book. ATM is the
# affordable Bold tier ($1.36*5*100 = $680 < $824). The ITM-2 book is RETAINED below as a
# LABELED future-reference only (NOT a primary measured book); it re-qualifies once Bold
# equity >= ~$3,570 (ITM-2 median $2.57 → notional $1,285 fits the 0.50 risk cap then).
#
# Each book carries its (account, equity, qty) so cap-admission runs per-account at the
# account's CURRENT equity — so the recency verdict is on the REALIZABLE book, consistent
# with the rest of the harness (lib.cap_admission / risk_gate.check_order is the default
# order-admission gate).
BOOKS = {
    "Safe2_ATM_1+2+4": {
        "account": "safe",
        "members": [("vwap_continuation", "ATM"),
                    ("vwap_reclaim_failed_break", "ATM"),
                    ("vix_regime_dayside", "ATM")],
    },
    "Bold_ATM_1+2": {
        "account": "bold",
        "members": [("vwap_continuation", "ATM"),
                    ("vwap_reclaim_failed_break", "ATM")],
    },
}

# Future-reference ONLY (NOT a primary measured book; excluded from headline / gate).
# Re-qualifies as a primary Bold book once Bold equity >= ~$3,570 (ITM-2 fits the 0.50 cap).
FUTURE_REFERENCE_BOOKS = {
    "Bold_ITM2_1+2__future_ref_requalifies_at_equity_3570": {
        "account": "bold",
        "members": [("vwap_continuation", "ITM-2"),
                    ("vwap_reclaim_failed_break", "ITM-2")],
        "note": ("FUTURE-REFERENCE ONLY — Bold ITM-2 is UNAFFORDABLE at current equity "
                 "($1,648): median qty5 order $1,285 > $824 cap, 90.6% RISK_CAP block "
                 "(B9 cap-aware re-score). Re-qualifies as a primary Bold book once Bold "
                 "equity >= ~$3,570. NOT in the headline/gate; reported cap-aware for context."),
    },
}


def read_cache_last_date() -> dt.date:
    """Auto-read the OPRA real-fills cache last-date from data-coverage.json."""
    cov = json.loads(DATA_COVERAGE.read_text(encoding="utf-8"))
    last = cov["classes"]["option_chain_realfills"]["last"]
    return dt.date.fromisoformat(last)


def load_merged_spy_vix() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Master + recent daily file, concatenated and de-duped (same as the Sunday driver),
    so the frame covers full IS + the freshest OOS. De-dup is by (timestamp) keep-last."""
    master_spy = pd.read_csv(DATA / "spy_5m_2025-01-01_2026-06-16.csv")
    master_vix = pd.read_csv(DATA / "vix_5m_2025-01-01_2026-06-16.csv")
    recent_spy = pd.read_csv(DATA / "spy_5m_2026-05-19_2026-06-18.csv")
    recent_vix = pd.read_csv(DATA / "vix_5m_2026-05-19_2026-06-18.csv")
    spy = pd.concat([master_spy, recent_spy], ignore_index=True)
    vix = pd.concat([master_vix, recent_vix], ignore_index=True)
    return spy, vix


def resolve_window(args, trading_days: list[dt.date]) -> tuple[dt.date, dt.date, dt.date]:
    """Return (recent_start, recent_end, cache_last). recent_end defaults to the OPRA cache
    last-date (auto-read); recent_start = the Nth-newest trading day at-or-before that end."""
    cache_last = read_cache_last_date()
    end = dt.date.fromisoformat(args.end) if args.end else cache_last
    if args.start:
        start = dt.date.fromisoformat(args.start)
        return start, end, cache_last
    in_range = [d for d in trading_days if d <= end]
    if not in_range:
        raise SystemExit(f"[recency] no trading days <= {end} in frame")
    lookback = max(1, args.lookback)
    start = in_range[-lookback] if len(in_range) >= lookback else in_range[0]
    return start, end, cache_last


def window_metrics(rows: list[dict], start: dt.date, end: dt.date) -> dict:
    """Per-trade metrics restricted to [start, end] inclusive. rows have date/side/pnl."""
    sub = [r for r in rows if start <= dt.date.fromisoformat(r["date"]) <= end]
    if not sub:
        return {"n": 0, "window": f"{start}..{end}"}
    pnl = np.array([r["pnl"] for r in sub], float)
    by_day = defaultdict(float)
    for r in sub:
        by_day[r["date"]] += r["pnl"]
    days = sorted(by_day)
    daily = np.array([by_day[d] for d in days], float)
    return {
        "window": f"{start}..{end}",
        "n": len(sub),
        "n_days": len(days),
        "wr_pct": round(100 * float((pnl > 0).mean()), 1),
        "exp_per_trade": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "sign": "POSITIVE" if pnl.mean() > 0 else ("FLAT" if pnl.mean() == 0 else "NEGATIVE"),
        "best_day": round(float(daily.max()), 2),
        "worst_day": round(float(daily.min()), 2),
        "win_days": int((daily > 0).sum()),
        "loss_days": int((daily < 0).sum()),
        "first_fill": days[0],
        "last_fill": days[-1],
    }


def verdict_for(recent: dict, full_oos: dict, floor: int) -> tuple[str, str]:
    """Per-edge/per-book VERDICT against the documented n-floor.

    CONFIRM = recent expectancy > 0 AND recent n >= floor
    YELLOW  = recent positive but n < floor, OR recent <=0 but n < floor AND full-OOS > 0 (small-n
              wobble against a positive base — not yet a kill)
    RED     = recent expectancy clearly negative (< 0) AND recent n >= floor
    NO_FILLS = recent n == 0 (cannot confirm or reject; treat as YELLOW for gating)
    """
    rn = recent.get("n", 0)
    rexp = recent.get("exp_per_trade")
    foexp = full_oos.get("exp_per_trade")
    if rn == 0:
        return "NO_FILLS", "no fills in recent window — cannot confirm (treat as not-yet-confirmed)"
    if rexp is not None and rexp > 0:
        if rn >= floor:
            return "CONFIRM", f"recent exp +${rexp}/tr, n={rn} >= floor {floor}"
        return "YELLOW", f"recent exp +${rexp}/tr POSITIVE but n={rn} < floor {floor} (small-n)"
    # recent <= 0
    if rn >= floor:
        return "RED", f"recent exp ${rexp}/tr NEGATIVE, n={rn} >= floor {floor} (clear)"
    # negative but small-n: lean on full-OOS base
    base = "positive" if (foexp is not None and foexp > 0) else "non-positive"
    return ("YELLOW",
            f"recent exp ${rexp}/tr <=0 but n={rn} < floor {floor}; full-OOS base {base} "
            f"(${foexp}/tr) -> small-n wobble, not a kill")


def simulate_set(signals, spy, ribbon, vix, *, strike_offset, setup, qty) -> tuple[list[dict], dict]:
    """Run a signal set at one strike tier on real OPRA fills (full frame; window cut later).
    Byte-for-byte the Sunday driver's sim loop, parameterized on `qty` (per-account: Safe 3 /
    Bold 5). Each row also carries the per-contract `entry_premium` so the cap-admission gate
    (lib.cap_admission) can decide admit/block at the account's current equity."""
    rows: list[dict] = []
    n_total = len(signals)
    n_filled = n_miss = n_none = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - strike_offset if sg.side == "P" else atm + strike_offset
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            n_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=qty, setup=setup, strike_override=strike, entry_vix=entry_vix,
            premium_stop_pct=PREMIUM_STOP_PCT)
        if fill is None or fill.dollar_pnl is None:
            n_none += 1
            continue
        n_filled += 1
        rows.append({"date": str(d), "side": sg.side, "strike": int(strike),
                     "pnl": round(float(fill.dollar_pnl), 2),
                     "entry_premium": round(float(fill.entry_premium), 4),
                     "exit": fill.exit_reason.name if fill.exit_reason else "NONE"})
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_miss, "sim_none": n_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


def admit_rows(rows: list[dict], account: str, equity: float, qty: int) -> tuple[list[dict], dict]:
    """Apply the LIVE order-admission gate (lib.cap_admission → risk_gate.check_order) to a
    set of fill-rows at this account/equity/qty. Returns (admitted_rows, admission_summary).

    A row is ADMITTED iff check_order ALLOWS (qty @ entry_premium @ equity): notional <= the
    tighter of (per_trade_risk_cap_pct, v15 tier) AND qty >= min_contracts. A BLOCKED row is
    EXCLUDED from the realizable book entirely (its realizable P&L is $0) — never qty-reduced.
    This makes the recency verdict measure the REALIZABLE book, consistent with the harness."""
    res = cap_admission.admit_book(
        rows, account, equity, qty, enforce_cap=True,
        premium_getter=lambda r: r["entry_premium"])
    admitted = list(res.admitted)
    summary = {
        "account": cap_admission._account_alias(account),
        "equity": equity, "qty": qty,
        "n_total": res.n_total, "n_admitted": len(admitted),
        "n_blocked": len(res.blocked), "block_rate": res.block_rate,
        "block_codes": res.block_codes,
    }
    return admitted, summary


def load_vix_regime_config() -> dict:
    try:
        b5 = json.loads(B5_SCORECARD.read_text(encoding="utf-8"))
        rb = b5.get("headline", {}).get("robust_clearing_cell")
        if rb and rb.get("slope_rule") is not None and rb.get("low_margin") is not None:
            return {"slope_rule": rb["slope_rule"], "low_margin": rb["low_margin"],
                    "source": "b5 robust_clearing_cell"}
    except Exception as e:  # noqa: BLE001
        print(f"[recency] WARN b5 scorecard unreadable ({e}); default vix-regime cfg", flush=True)
    return {"slope_rule": "not_rising", "low_margin": 0.0, "source": "default"}


def detect_all(days, spy, vix) -> dict:
    """Build the signal sets for the three edges (same calls as the Sunday driver)."""
    out = {}
    out["vwap_continuation"] = detect_vwap_continuation(
        days, vix, breakout_only=False, put_needs_rising_vix=False)
    out["vwap_reclaim_failed_break"] = detect_reclaim_failed_break(days)
    vix_g = vix.to_numpy()
    vix_med_g = causal_vix_median(vix_g, VIX_MEDIAN_BARS)
    vix_slp_g = vix_slope(vix_g, VIX_SLOPE_BARS)
    cfg = load_vix_regime_config()
    raw4 = detect_vix_regime_dayside(days, spy, vix_g, vix_med_g, vix_slp_g,
                                     cfg["low_margin"], cfg["slope_rule"])
    out["vix_regime_dayside"] = [Signal(bar_idx=s.gidx, side=s.side,
                                        stop_level=round(_swing_stop(spy, s.gidx, s.side), 2),
                                        note="vix_regime_dayside") for s in raw4]
    out["_vix_cfg"] = cfg
    return out


def book_window(admitted_by_cell: dict, members: list[tuple], account: str,
                start: dt.date, end: dt.date) -> dict:
    """Aggregate the recent-window daily P&L across a book's (edge, tier) members on the
    cap-aware REALIZABLE book (admitted rows) for this account."""
    comb = defaultdict(float)
    n_trades = 0
    for edge, tier in members:
        for r in admitted_by_cell[(edge, tier, account)]:
            d = dt.date.fromisoformat(r["date"])
            if start <= d <= end:
                comb[d] += r["pnl"]
                n_trades += 1
    if not comb:
        return {"n_days": 0, "n_trades": 0, "total_dollar": 0.0, "sign": "FLAT"}
    vals = np.array([comb[d] for d in sorted(comb)], float)
    return {"n_days": len(comb), "n_trades": n_trades,
            "total_dollar": round(float(vals.sum()), 2),
            "daily_mean": round(float(vals.mean()), 2),
            "win_days": int((vals > 0).sum()), "loss_days": int((vals < 0).sum()),
            "best_day": round(float(vals.max()), 2), "worst_day": round(float(vals.min()), 2),
            "sign": "POSITIVE" if vals.sum() > 0 else ("FLAT" if vals.sum() == 0 else "NEGATIVE")}


def book_verdict(recent: dict, full_oos: dict, floor: int) -> tuple[str, str]:
    """Book-level verdict uses the same logic but on TRADE count across the book's members."""
    proxy_recent = {"n": recent.get("n_trades", 0),
                    "exp_per_trade": (recent.get("total_dollar") / recent["n_trades"])
                    if recent.get("n_trades") else None}
    proxy_full = {"exp_per_trade": (full_oos.get("total_dollar") / full_oos["n_trades"])
                  if full_oos.get("n_trades") else None}
    if proxy_recent["exp_per_trade"] is not None:
        proxy_recent["exp_per_trade"] = round(proxy_recent["exp_per_trade"], 2)
    if proxy_full["exp_per_trade"] is not None:
        proxy_full["exp_per_trade"] = round(proxy_full["exp_per_trade"], 2)
    return verdict_for(proxy_recent, proxy_full, floor)


def main() -> int:
    ap = argparse.ArgumentParser(description="Recency-confirmation tracker (confirm-before-capital gate)")
    ap.add_argument("--lookback", type=int, default=RECENCY_LOOKBACK_TRADING_DAYS,
                    help="newest-N trading days of real fills to score (default 25)")
    ap.add_argument("--end", type=str, default=None, help="recent-window end (default = OPRA cache last)")
    ap.add_argument("--start", type=str, default=None, help="explicit recent-window start (overrides lookback)")
    ap.add_argument("--floor", type=int, default=CONFIRM_N_FLOOR, help="CONFIRM n-floor (default 10)")
    args = ap.parse_args()

    print("[recency] loading merged SPY+VIX (master + recent) ...", flush=True)
    spy_raw, vix_raw = load_merged_spy_vix()
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    trading_days = sorted({dc.date for dc in days})
    frame_first, frame_last = spy["timestamp_et"].iloc[0].date(), spy["timestamp_et"].iloc[-1].date()

    recent_start, recent_end, cache_last = resolve_window(args, trading_days)
    window_days = [d for d in trading_days if recent_start <= d <= recent_end]
    print(f"[recency] frame {frame_first}..{frame_last} trading_days={len(trading_days)} | "
          f"OPRA cache last={cache_last} | recent window {recent_start}..{recent_end} "
          f"({len(window_days)} trading days, floor n>={args.floor})", flush=True)

    sigs = detect_all(days, spy, vix)
    vix_cfg = sigs.pop("_vix_cfg")

    # Which (edge, tier) cell feeds which PRIMARY account (drives qty + cap-admission account).
    # Built from the primary BOOKS so the per-edge tier view matches the realizable book.
    primary_account_for: dict[tuple, str] = {}
    for bspec in BOOKS.values():
        for edge, tier in bspec["members"]:
            primary_account_for.setdefault((edge, tier), bspec["account"])

    # Sim cache keyed by (edge, tier, qty) — the cap-blind fills BEFORE admission. qty differs
    # per account (Safe 3 / Bold 5), so a tier used by both is simmed once per distinct qty.
    raw_rows_cache: dict[tuple, tuple[list[dict], dict]] = {}

    def get_raw_rows(edge: str, tier: str, off: int, qty: int) -> tuple[list[dict], dict]:
        key = (edge, tier, qty)
        if key not in raw_rows_cache:
            raw_rows_cache[key] = simulate_set(
                sigs[edge], spy, ribbon, vix, strike_offset=off,
                setup=f"{edge}_{tier}", qty=qty)
        return raw_rows_cache[key]

    # admitted rows keyed by (edge, tier, account) — the REALIZABLE (cap-aware) book per account.
    admitted_by_cell: dict[tuple, list[dict]] = {}

    # Per-edge tier view (cap-aware), keyed exactly as before: edges[edge]["tiers"][tier].
    # The PRIMARY-account (from the book that uses this tier) drives the headline verdict;
    # if a tier is used by no primary book it is still simmed/admitted at Safe qty for context.
    coverage: dict[str, dict] = {}
    edges_out: dict[str, dict] = {}
    for edge, tiers in EDGE_TIERS.items():
        sig = sigs[edge]
        edge_block = {"n_signals": len(sig), "tiers": {}}
        for tier, off in tiers.items():
            acct = primary_account_for.get((edge, tier), "safe")
            qty = QTY_BY_ACCOUNT[acct]
            equity = EQUITY_BY_ACCOUNT[acct]
            raw_rows, cov = get_raw_rows(edge, tier, off, qty)
            admitted, admission = admit_rows(raw_rows, acct, equity, qty)
            admitted_by_cell[(edge, tier, acct)] = admitted
            coverage[f"{edge}/{tier}"] = cov
            # cap-aware (realizable) metrics — the verdict is on the ADMITTED book.
            recent = window_metrics(admitted, recent_start, recent_end)
            full_oos = window_metrics(admitted, OOS_2026_START, recent_end)
            verdict, reason = verdict_for(recent, full_oos, args.floor)
            edge_block["tiers"][tier] = {
                "sim_offset": off, "primary_account": admission["account"],
                "qty": qty, "equity": equity,
                "coverage": cov, "admission": admission,
                "recent_window": recent, "full_oos_2026": full_oos,
                "verdict": verdict, "reason": reason,
                "book_basis": "cap-aware REALIZABLE (lib.cap_admission -> risk_gate.check_order)",
            }
            print(f"[recency] {edge:26s} {tier:14s}(off={off:+d}) {admission['account']:13s} "
                  f"q{qty}: admitted n={recent['n']} exp=${recent.get('exp_per_trade')} "
                  f"{recent.get('sign','-')} -> {verdict} | full-OOS exp=${full_oos.get('exp_per_trade')} "
                  f"| block {admission['n_blocked']}/{admission['n_total']} "
                  f"({admission['block_rate']})", flush=True)
        edges_out[edge] = edge_block

    # Per-book verdicts (PRIMARY books only) on the cap-aware REALIZABLE book.
    books_out: dict[str, dict] = {}
    for book, bspec in BOOKS.items():
        members = bspec["members"]
        acct = bspec["account"]
        qty = QTY_BY_ACCOUNT[acct]
        equity = EQUITY_BY_ACCOUNT[acct]
        # Ensure this book's account-specific admitted cells exist (a tier may have been
        # admitted under a DIFFERENT primary account in the per-edge loop; e.g. ATM #1/#2
        # are admitted for Safe there, but Bold's ATM book needs the qty5/Bold-cap cells).
        for edge, tier in members:
            if (edge, tier, acct) not in admitted_by_cell:
                off = EDGE_TIERS[edge][tier]
                raw_rows, _ = get_raw_rows(edge, tier, off, qty)
                admitted, _adm = admit_rows(raw_rows, acct, equity, qty)
                admitted_by_cell[(edge, tier, acct)] = admitted
        recent = book_window(admitted_by_cell, members, acct, recent_start, recent_end)
        full_oos = book_window(admitted_by_cell, members, acct, OOS_2026_START, recent_end)
        verdict, reason = book_verdict(recent, full_oos, args.floor)
        books_out[book] = {"account": cap_admission._account_alias(acct),
                           "equity": EQUITY_BY_ACCOUNT[acct], "qty": QTY_BY_ACCOUNT[acct],
                           "members": [f"{e}/{t}" for e, t in members],
                           "book_basis": "cap-aware REALIZABLE (lib.cap_admission)",
                           "recent_window": recent, "full_oos_2026": full_oos,
                           "verdict": verdict, "reason": reason}
        print(f"[recency] BOOK {book:22s}: recent ${recent.get('total_dollar')} "
              f"({recent.get('n_trades')}tr/{recent.get('n_days')}d) {recent.get('sign')} -> {verdict}",
              flush=True)

    # Future-reference books (NOT primary, EXCLUDED from headline/gate) — simmed+admitted cap-aware
    # for context only (e.g. Bold ITM-2, which re-qualifies once Bold equity >= ~$3,570).
    future_ref_out: dict[str, dict] = {}
    for book, bspec in FUTURE_REFERENCE_BOOKS.items():
        members = bspec["members"]
        acct = bspec["account"]
        qty = QTY_BY_ACCOUNT[acct]
        equity = EQUITY_BY_ACCOUNT[acct]
        for edge, tier in members:
            if (edge, tier, acct) not in admitted_by_cell:
                off = EDGE_TIERS[edge][tier]
                raw_rows, _ = get_raw_rows(edge, tier, off, qty)
                admitted, _adm = admit_rows(raw_rows, acct, equity, qty)
                admitted_by_cell[(edge, tier, acct)] = admitted
        recent = book_window(admitted_by_cell, members, acct, recent_start, recent_end)
        full_oos = book_window(admitted_by_cell, members, acct, OOS_2026_START, recent_end)
        verdict, reason = book_verdict(recent, full_oos, args.floor)
        future_ref_out[book] = {"account": cap_admission._account_alias(acct),
                                "equity": equity, "qty": qty,
                                "members": [f"{e}/{t}" for e, t in members],
                                "status": "FUTURE-REFERENCE ONLY (excluded from headline/gate)",
                                "note": bspec["note"],
                                "recent_window": recent, "full_oos_2026": full_oos,
                                "verdict": verdict, "reason": reason}
        print(f"[recency] FUTURE-REF {book[:36]:36s}: recent ${recent.get('total_dollar')} "
              f"({recent.get('n_trades')}tr) {recent.get('sign')} -> {verdict} (NOT in gate)",
              flush=True)

    # Headline: any CONFIRM? any RED? overall gate state (PRIMARY edges + PRIMARY books only).
    all_edge_verdicts = [t["verdict"] for e in edges_out.values() for t in e["tiers"].values()]
    all_book_verdicts = [b["verdict"] for b in books_out.values()]
    any_confirm = any(v == "CONFIRM" for v in all_edge_verdicts + all_book_verdicts)
    any_red = any(v == "RED" for v in all_edge_verdicts + all_book_verdicts)
    # The headline gate: are ANY of the validated live tiers confirmed? Bold is now ATM
    # (the affordable tier) — its prior ITM-2 line was a FICTIONAL/unaffordable book.
    live_tier_verdicts = {
        "#1 ATM (Safe-2)": edges_out["vwap_continuation"]["tiers"]["ATM"]["verdict"],
        "#1 ATM (Bold)": edges_out["vwap_continuation"]["tiers"]["ATM"]["verdict"],
        "#2 ATM": edges_out["vwap_reclaim_failed_break"]["tiers"]["ATM"]["verdict"],
        "#4 ATM": edges_out["vix_regime_dayside"]["tiers"]["ATM"]["verdict"],
    }
    edges_confirmed_on_recent = any(v == "CONFIRM" for v in live_tier_verdicts.values())

    summary = {
        "tracker": "RECENCY-CONFIRMATION — the CONFIRM-BEFORE-CAPITAL gate (weekly)",
        "run_date": dt.date.today().isoformat(),
        "cadence": "WEEKLY — fold into weekly-review / OP-11 outer loop as recent fills accrue",
        "gate": ("NO live flip while an edge's recency verdict is RED; capital scaling on an edge "
                 "WAITS for CONFIRM (yellow-flag gate). See markdown/planning/LIVE-PATH-WORKPACKAGE.md."),
        "opra_cache_last": str(cache_last),
        "recent_window": f"{recent_start}..{recent_end}",
        "recent_window_trading_days": len(window_days),
        "lookback_trading_days_requested": args.lookback,
        "confirm_n_floor": args.floor,
        "frame": f"{frame_first}..{frame_last} (master + recent daily concat)",
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "book_basis": ("cap-aware REALIZABLE book — lib.cap_admission (risk_gate.check_order) "
                       "applied per account at current equity; verdict is on the affordable book"),
        "config": {"premium_stop_pct": PREMIUM_STOP_PCT,
                   "qty": QTY_BY_ACCOUNT,            # per-account now (Safe 3 / Bold 5)
                   "equity": EQUITY_BY_ACCOUNT,      # cap measured at current equity per account
                   "cap_gate": "lib.cap_admission.admit_book (enforce_cap=True default)",
                   "snap_radius": MAX_STRIKE_STEPS, "exits": "v15 default", "vix_regime_cfg": vix_cfg},
        "verdict_rules": {
            "CONFIRM": "recent exp/tr > 0 AND recent n >= floor",
            "YELLOW": "positive but n < floor, OR recent<=0 with n<floor (small-n wobble vs full-OOS base)",
            "RED": "recent exp/tr < 0 AND recent n >= floor",
            "NO_FILLS": "recent n == 0 (cannot confirm; gate treats as not-yet-confirmed)",
        },
        "headline": {
            "edges_confirmed_on_recent": edges_confirmed_on_recent,
            "any_confirm": any_confirm,
            "any_red": any_red,
            "live_tier_verdicts": live_tier_verdicts,
        },
        "edges": edges_out,
        "books": books_out,
        "books_future_reference": future_ref_out,
        "DISCLOSURE": {
            "small_n": (f"recent window is {len(window_days)} trading days — n per edge is SMALL by "
                        "design; recent expectancy is a directional sanity check, not a standing-bar "
                        "ratification (the 11-gate bar needs full-history n)"),
            "per_trade": "per-trade EXPECTANCY reported, not WR alone (OP-14)",
            "real_fills": "real OPRA fills only — the WR authority (C1); SPY-direction != option edge (C3/L58)",
            "cap_aware": ("verdict is on the cap-aware REALIZABLE book (lib.cap_admission per account "
                          "at current equity) — Bold's PRIMARY book is now ATM (affordable); ITM-2 is "
                          "UNAFFORDABLE at $1,648 (90.6% RISK_CAP block, B9 re-score) and demoted to "
                          "books_future_reference (re-qualifies at Bold equity >= ~$3,570)"),
            "no_new_ship": "RESEARCH ONLY; no live edit, no orders (money-path guard)",
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    append_status(summary)
    print(f"\n[recency] wrote {OUT_JSON}", flush=True)

    print("\n=== RECENCY-CONFIRMATION VERDICT ===")
    print(f"recent window {recent_start}..{recent_end} ({len(window_days)} trading days), floor n>={args.floor}")
    for tier_name, v in live_tier_verdicts.items():
        print(f"  {tier_name:18s} -> {v}")
    for book, b in books_out.items():
        print(f"  BOOK {book:18s} -> {b['verdict']} (recent ${b['recent_window'].get('total_dollar')})")
    print(f"edges_confirmed_on_recent = {edges_confirmed_on_recent}  |  any_RED = {any_red}")
    print("GATE: RED edge -> no live flip; capital scaling waits for CONFIRM.")
    return 0


def append_status(s: dict) -> None:
    """Prepend a dated one-line wake-signal block to STATUS.md (the OP-25 signal)."""
    h = s["headline"]
    lt = h["live_tier_verdicts"]
    confirms = [k for k, v in lt.items() if v == "CONFIRM"]
    reds = [k for k, v in lt.items() if v == "RED"]
    book_reds = [bk for bk, bv in s["books"].items() if bv["verdict"] == "RED"]
    all_reds = reds + book_reds
    book_line = "; ".join(
        f"{bk}={bv['verdict']} (${bv['recent_window'].get('total_dollar')})"
        for bk, bv in s["books"].items())
    # State must reflect BOTH tier AND book verdicts: an all-YELLOW-tier but RED-book
    # gate is RED-BLOCKED, not YELLOW (logic bug found 2026-06-22). Use the authoritative
    # h["any_red"], which already folds in book-level REDs, not the tier-only `reds`.
    state = ("CONFIRMED" if confirms and not h["any_red"] else
             ("RED-BLOCKED" if h["any_red"] else "YELLOW (not-yet-confirmed)"))
    block = (
        f"## [{s['run_date']}] RECENCY-CONFIRMATION (confirm-before-capital gate) — "
        f"{state} on the freshest {s['recent_window_trading_days']} trading days "
        f"({s['recent_window']}), real OPRA fills, floor n>={s['confirm_n_floor']}\n\n"
        f"> **Signal J wakes to (OP-25).** Weekly recency check (reusable `backtest/autoresearch/"
        f"recency_check.py`, generalizes the Sunday fresh-revalidation; auto-reads OPRA cache last "
        f"= {s['opra_cache_last']}). The CONFIRM-BEFORE-CAPITAL gate: no live flip while an edge is "
        f"RED; capital scaling waits for CONFIRM.\n"
        f"> - **Live-tier verdicts:** "
        + "; ".join(f"{k}={v}" for k, v in lt.items()) + "\n"
        f"> - **Books:** {book_line}\n"
        f"> - **edges_confirmed_on_recent = {h['edges_confirmed_on_recent']}** "
        f"(any RED={h['any_red']}). "
        + ("All live tiers still small-n / not-yet-confirmed on the freshest weeks — full-OOS-2026 "
           "base remains the larger-n companion read; HOLD capital scaling until an edge CONFIRMs."
           if not confirms else
           f"CONFIRMED: {', '.join(confirms)}.")
        + ("" if not all_reds else f" RED-BLOCKED: {', '.join(all_reds)} — no live flip on these.")
        + f"\n> - Files: `automation/state/recency-confirmation.json`, "
          f"`backtest/autoresearch/recency_check.py`.\n\n---\n\n")
    existing = STATUS_MD.read_text(encoding="utf-8") if STATUS_MD.exists() else ""
    # Idempotent: strip any prior RECENCY-CONFIRMATION block(s) before prepending, so the
    # WEEKLY run REPLACES its wake-signal rather than stacking duplicates (the bug found 2026-06-21).
    import re as _re
    existing = _re.sub(
        r"## \[[^\]]*\] RECENCY-CONFIRMATION \(confirm-before-capital gate\).*?\n---\n\n",
        "", existing, flags=_re.DOTALL)
    STATUS_MD.write_text(block + existing, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
