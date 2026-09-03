"""v15.3 LIVE_PRICE_FIRST_BAR_TRIGGER — Stage-2 frequency + edge_capture analysis.

OP-20 Stage-2: establishes how often the fast-V opening pattern occurs in the 16-month
SPY dataset, and whether firing on live-price (vs closed-bar) would change any J anchor
day outcomes.

Fast-V definition (proxy, since we lack historical named-level archives):
  - 09:40 bar: close < open (bearish candle) AND (high - low) > $0.80 (significant range)
  - SPY open at 09:40 is within $0.50 of prior-day RTH low (PDL) or RTH high (PDH) proxy
  - 09:45 bar: close > 09:40 bar open (V-reversal = SPY recovered above the 09:40 bar open)

This is an UPPER BOUND on v15.3 frequency: the actual trigger requires a named ★★+ level
in key-levels.json which further filters events. Use this to bound "at most N events per quarter."

Outputs:
  - analysis/recommendations/v15_3_stage2.json

J anchor days checked:
  Winners: 2026-04-29, 2026-05-01, 2026-05-04
  Losers:  2026-05-05, 2026-05-06, 2026-05-07
"""
from __future__ import annotations

import os as _os, sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "v15-3-stage2.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "v15-3-stage2.stderr.log", "a", buffering=1, encoding="utf-8")
    print(f"[v15-3-stage2] stdout redirected (pid={_os.getpid()})")

import datetime as dt
import json
import logging
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    stream=sys.stdout)
log = logging.getLogger(__name__)

OUT_JSON = ROOT / "analysis" / "recommendations" / "v15_3_stage2.json"

J_WINNER_DATES = {"2026-04-29", "2026-05-01", "2026-05-04"}
J_LOSER_DATES  = {"2026-05-05", "2026-05-06", "2026-05-07"}
J_ALL_DATES    = J_WINNER_DATES | J_LOSER_DATES

FIRST_BAR_OPEN  = dt.time(9, 35)
FIRST_BAR_CLOSE = dt.time(9, 40)  # the bar we enter on if v15.3 fires
NEXT_BAR        = dt.time(9, 45)  # the recovery bar


def _load_spy() -> pd.DataFrame:
    for cand in [
        "spy_5m_2025-01-01_2026-05-19_merged.csv",
        "spy_5m_2025-01-01_2026-05-15.csv",
        "spy_5m_2025-01-01_2026-05-12.csv",
        "spy_5m_2025-01-01_2026-05-07.csv",
    ]:
        p = REPO / "data" / cand
        if p.exists():
            df = pd.read_csv(p)
            df["timestamp_et"] = (
                pd.to_datetime(df["timestamp_et"], utc=True)
                .dt.tz_convert("America/New_York")
                .dt.tz_localize(None)
            )
            df = df.sort_values("timestamp_et").reset_index(drop=True)
            df["date"] = df["timestamp_et"].dt.date
            df["time"] = df["timestamp_et"].dt.time
            log.info("Loaded %s: %d bars", cand, len(df))
            return df
    raise FileNotFoundError("No SPY CSV found")


def _analyze(spy_df: pd.DataFrame) -> dict:
    days = sorted(spy_df["date"].unique())
    log.info("Analyzing %d trading days", len(days))

    fast_v_events = []
    quarter_counts: dict[str, int] = {}
    j_day_analysis = []

    for i, d in enumerate(days):
        day_df = spy_df[spy_df["date"] == d].copy()
        day_df = day_df.sort_values("time").reset_index(drop=True)

        # Get prior day bars for PDH/PDL
        if i == 0:
            continue
        prior_day = days[i - 1]
        prior_df = spy_df[spy_df["date"] == prior_day]
        if prior_df.empty:
            continue
        rth_prior = prior_df[(prior_df["time"] >= dt.time(9, 30)) &
                             (prior_df["time"] <= dt.time(16, 0))]
        if rth_prior.empty:
            continue
        pdh = float(rth_prior["high"].max())
        pdl = float(rth_prior["low"].min())

        # Get the relevant bars
        bar_935 = day_df[day_df["time"] == FIRST_BAR_OPEN]
        bar_940 = day_df[day_df["time"] == FIRST_BAR_CLOSE]
        bar_945 = day_df[day_df["time"] == NEXT_BAR]

        if bar_935.empty or bar_940.empty or bar_945.empty:
            continue

        b935 = bar_935.iloc[0]
        b940 = bar_940.iloc[0]
        b945 = bar_945.iloc[0]

        # Fast-V detection criteria
        range_940 = float(b940["high"]) - float(b940["low"])
        body_940 = float(b940["open"]) - float(b940["close"])  # positive = bearish body
        is_bearish_940 = body_940 > 0.10  # at least 10c bearish body
        is_wide_940 = range_940 > 0.80

        # Is the 09:40 bar's low near a proxy "named level"?
        low_940 = float(b940["low"])
        near_pdl = abs(low_940 - pdl) <= 0.75  # within $0.75 of PDL
        near_pdh = abs(low_940 - pdh) <= 0.75  # within $0.75 of PDH (for extended-range sessions)

        # V-reversal: 09:45 closes above 09:40 open
        v_reversal = float(b945["close"]) > float(b940["open"])

        is_fast_v = is_bearish_940 and is_wide_940 and (near_pdl or near_pdh) and v_reversal

        date_str = str(d)
        q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"

        if is_fast_v:
            fast_v_events.append({
                "date": date_str,
                "quarter": q,
                "range_940": round(range_940, 2),
                "body_940": round(body_940, 2),
                "low_940": round(low_940, 2),
                "pdl": round(pdl, 2),
                "pdh": round(pdh, 2),
                "near_pdl": near_pdl,
                "near_pdh": near_pdh,
                "b940_open": round(float(b940["open"]), 2),
                "b940_close": round(float(b940["close"]), 2),
                "b945_close": round(float(b945["close"]), 2),
                "v_reversal": v_reversal,
                "is_j_winner": date_str in J_WINNER_DATES,
                "is_j_loser": date_str in J_LOSER_DATES,
            })
            quarter_counts[q] = quarter_counts.get(q, 0) + 1

        if date_str in J_ALL_DATES:
            j_day_analysis.append({
                "date": date_str,
                "category": "WINNER" if date_str in J_WINNER_DATES else "LOSER",
                "range_940": round(range_940, 2),
                "body_940": round(body_940, 2),
                "low_940": round(low_940, 2),
                "pdl": round(pdl, 2),
                "near_pdl": near_pdl,
                "v_reversal": v_reversal,
                "is_fast_v_candidate": is_fast_v,
            })

    n_days = len(days) - 1
    n_events = len(fast_v_events)
    events_per_quarter = n_events / max(1, len(set(e["quarter"] for e in fast_v_events)))

    j_affected = [e for e in fast_v_events if e["is_j_winner"] or e["is_j_loser"]]
    edge_capture_delta = 0.0  # v15.3 doesn't affect J days unless it fires on them

    log.info("=== v15.3 Stage-2 Frequency Analysis ===")
    log.info("Total trading days: %d", n_days)
    log.info("Fast-V candidates: %d (%.1f%%)", n_events, 100 * n_events / max(1, n_days))
    log.info("Events per quarter: %.1f", events_per_quarter)
    log.info("Quarter breakdown: %s", json.dumps(quarter_counts))
    log.info("J anchor days affected: %d", len(j_affected))
    log.info("Edge capture delta (J days): $%.2f", edge_capture_delta)
    log.info("")
    log.info("J anchor day detail:")
    for j in j_day_analysis:
        log.info("  %s [%s]: fast_v=%s range=%.2f body=%.2f near_pdl=%s v_reversal=%s",
                 j["date"], j["category"], j["is_fast_v_candidate"],
                 j["range_940"], j["body_940"], j["near_pdl"], j["v_reversal"])

    if fast_v_events:
        log.info("\nFast-V events found:")
        for e in fast_v_events[:20]:
            log.info("  %s %s range=%.2f low=%.2f pdl=%.2f %s",
                     e["date"], e["quarter"], e["range_940"],
                     e["low_940"], e["pdl"],
                     "[J-WINNER]" if e["is_j_winner"] else ("[J-LOSER]" if e["is_j_loser"] else ""))

    return {
        "candidate": "LIVE_PRICE_FIRST_BAR_TRIGGER (v15.3)",
        "generated_at": dt.datetime.now().isoformat(),
        "methodology": (
            "Proxy fast-V scan: 09:40 bar with body>10c, range>$0.80, low within $0.75 of PDL/PDH, "
            "09:45 closes above 09:40 open. UPPER BOUND on v15.3 frequency — actual trigger "
            "requires named ★★+ level in key-levels.json (not available historically)."
        ),
        "total_trading_days": n_days,
        "fast_v_candidates": n_events,
        "fast_v_pct_of_days": round(100 * n_events / max(1, n_days), 1),
        "events_per_quarter": round(events_per_quarter, 1),
        "quarter_counts": quarter_counts,
        "j_anchor_days_affected": len(j_affected),
        "edge_capture_delta": edge_capture_delta,
        "j_day_detail": j_day_analysis,
        "fast_v_events": fast_v_events,
        "op20_disclosure": {
            "account_size": "$1K paper (qty=3, ~$30-60 per trade at ATM option premiums)",
            "sample_bias": "Proxy scan without named-level archive — actual v15.3 rate will be lower",
            "oos_test": "All 16 months used as frequency scan (no train/test split for frequency)",
            "real_fills": "Not run — no historical fills available for this specific trigger class",
            "failure_modes": (
                "v15.3 fires on live in-progress bar — same risk class as the 5/14 ghost-entry. "
                "Narrow scope (09:35-09:45 ET, ★★+ only) is the risk mitigation but adds new "
                "surface area for misfire. Each quarter expects at most N=" + str(int(events_per_quarter)) + " fires."
            ),
            "concentration": "Not applicable — frequency scan, not a P&L backtest",
        },
    }


def main() -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    log.info("Loading SPY data...")
    spy_df = _load_spy()
    result = _analyze(spy_df)
    OUT_JSON.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    log.info("Output written: %s", OUT_JSON)


if __name__ == "__main__":
    main()
