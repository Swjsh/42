"""B4 NOVEL-DATA HUNT: gamma_wall_interaction — INFEASIBLE-WITH-CURRENT-DATA verdict.

HYPOTHESIS
----------
Do 0DTE dealer-gamma CALL/PUT walls + max-pain act as MAGNETS (price drawn to
max-pain / pinned between walls in a long-gamma regime) or as REJECTION barriers
(walls cap the move in a short-gamma regime)? Real-fills test: enter on SPY price
INTERACTING with a gamma wall (touch/reclaim/reject), simulate via the C1 OPRA path,
run all 8 anti-2.10 gates.

THE BLOCKER (why this returns INFEASIBLE, not "no edge")
--------------------------------------------------------
Backtesting wall-interaction requires, AS-OF each historical trading day, the dealer
gamma surface: per-strike OPEN INTEREST + per-contract GAMMA across the full SPY chain.
From that you derive the call wall / put wall / max-pain / zero-gamma flip that price
would have "interacted" with on that day. We DO NOT HAVE that history:

  1. ``journal/gex-archive/`` — the ONLY backtestable GEX history — holds exactly ONE
     dated snapshot (``2026-06-19.json``). Daily capture (``automation/scripts/gex_capture.py``,
     ``Gamma_GexCapture``) only began accruing 2026-06-19. N_usable_days = 1.
  2. The OPRA per-contract bars (``backtest/data/options/SPY*.csv``) carry ONLY
     ``open,high,low,close,volume,vwap,trade_count`` — NO open_interest, NO gamma. OI is a
     daily end-of-day outstanding-contracts figure that is NOT reconstructable from
     intraday price bars.
  3. ``lib.engine.gex_regime.assess_backtest_feasibility()`` is the project's own
     machine-readable verdict: ``can_backtest_now = False`` for exactly this reason.
  4. ``markdown/specs/GEX-PREMARKET-WIRING.md`` §6: "Cannot be backtested — no historical
     full-chain OI/gamma archive (the daily capture is now accruing that)."

Manufacturing the historical wall strikes from anything other than as-of OI+gamma (e.g.
proxying walls with round numbers, OI-less volume peaks, or back-filled greeks) would be a
FABRICATED backtest — the precise class of fake this project bans (C4/L171, BACKTESTING-
PLAYBOOK OP-20). A wall computed without real OI is not the level price actually interacted
with; an "edge" found on it would be an artifact of the proxy, not dealer positioning.

WHAT THIS SCRIPT DOES (honest, per OP-20 + OP-25 fail-loud-never-silent)
-----------------------------------------------------------------------
* Proves the blocker with live evidence (counts the GEX archive, inspects the OPRA CSV
  header, calls the engine's own feasibility assessor, confirms SPY data IS available so
  the bottleneck is unambiguously the GEX side).
* Emits the schema with every gate ``null`` / False and verdict INFEASIBLE — it does NOT
  fabricate trades to manufacture a number.
* Records the exact path-to-backtestable so this hunt can be RE-RUN for real once a few
  months of ``gex-archive/`` snapshots accumulate (the daily capture is already banking).

Pure Python, $0, no live orders, markets closed.
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_b4_gamma_wall_interaction.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]      # backtest/
ROOT = REPO.parent                              # repo root
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OUT = ROOT / "analysis" / "recommendations" / "b4-gamma-wall-interaction.json"
GEX_ARCHIVE = ROOT / "journal" / "gex-archive"
OPRA_DIR = REPO / "data" / "options"

SLUG = "gamma_wall_interaction"
HYPOTHESIS = (
    "0DTE dealer-gamma call/put walls + max-pain as MAGNET (price drawn to max-pain / "
    "pinned between walls under long-gamma) vs REJECTION (walls cap the move under "
    "short-gamma); real-fills entries on SPY price interacting with a gamma wall."
)


def _gex_archive_days() -> list[str]:
    """Every dated GEX snapshot we hold — the entire backtestable wall history."""
    if not GEX_ARCHIVE.exists():
        return []
    return sorted(p.stem for p in GEX_ARCHIVE.glob("*.json"))


def _opra_columns() -> list[str]:
    """Header of a representative OPRA per-contract CSV (proves no OI / no gamma)."""
    csvs = sorted(OPRA_DIR.glob("SPY*.csv"))
    if not csvs:
        return []
    with csvs[0].open("r", encoding="utf-8") as f:
        return f.readline().strip().split(",")


def _spy_day_count() -> dict:
    """Confirm SPY price data IS available, so the bottleneck is unambiguously GEX."""
    try:
        import pandas as pd
        from autoresearch import runner as ar_runner
        spy, _vix = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
        ts = pd.to_datetime(spy["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
        return {
            "available": True,
            "rows": int(len(spy)),
            "trading_days": int(ts.dt.date.nunique()),
            "window": f"{ts.dt.date.min()}..{ts.dt.date.max()}",
        }
    except Exception as e:  # noqa: BLE001 — diagnostic only; never crash the verdict
        return {"available": None, "error": f"{type(e).__name__}: {e}"}


def _feasibility() -> dict:
    """The engine's OWN machine-readable verdict (single source of truth)."""
    try:
        from lib.engine.gex_regime import assess_backtest_feasibility
        return assess_backtest_feasibility()
    except Exception as e:  # noqa: BLE001
        return {"can_backtest_now": None, "error": f"{type(e).__name__}: {e}"}


def main() -> int:
    gex_days = _gex_archive_days()
    opra_cols = _opra_columns()
    spy = _spy_day_count()
    feas = _feasibility()

    has_oi = "open_interest" in opra_cols
    has_gamma = "gamma" in opra_cols
    # Need OI + gamma AS-OF each day for >= ~60 days to mark up walls and get n>=20 trades.
    MIN_GEX_DAYS = 60
    n_gex = len(gex_days)
    infeasible = (n_gex < MIN_GEX_DAYS) and not (has_oi and has_gamma)

    blockers = []
    if n_gex < MIN_GEX_DAYS:
        blockers.append(
            f"gex-archive holds {n_gex} day(s) ({gex_days or 'none'}); need >= "
            f"{MIN_GEX_DAYS} as-of full-chain OI+gamma snapshots to mark walls/max-pain "
            f"across enough days for n>=20 wall-interaction trades. Capture began "
            f"2026-06-19 (Gamma_GexCapture) and is accruing forward."
        )
    if not (has_oi and has_gamma):
        blockers.append(
            f"OPRA per-contract bars carry only {opra_cols} — NO open_interest, NO gamma; "
            f"OI is a daily EOD figure not reconstructable from intraday price bars, so "
            f"historical walls cannot be derived from the data we have."
        )

    # Honest schema: NOTHING is fabricated. Every gate is null/False; verdict INFEASIBLE.
    summary = {
        "kind": "novel-data",
        "slug": SLUG,
        "hypothesis": HYPOTHESIS,
        "run_date": dt.date.today().isoformat(),
        "verdict": "INFEASIBLE_NO_HISTORICAL_DATA",
        "key_finding": (
            "Gamma walls / max-pain CANNOT be backtested on current data. The dealer "
            "gamma surface (as-of per-strike OI + per-contract gamma across the full SPY "
            "chain) exists for exactly 1 day in journal/gex-archive (2026-06-19, capture "
            "started that day); the OPRA price bars carry no OI and no gamma; OI is not "
            "reconstructable from price. Computing historical walls would require "
            "fabricating OI/gamma = a banned fake backtest (C4/L171, OP-20). SPY price "
            "data IS available (342 days) — the sole bottleneck is the dealer-positioning "
            "layer, which is now accruing forward and not yet deep enough to trade-test."
        ),
        # ── evidence ────────────────────────────────────────────────────────────
        "evidence": {
            "gex_archive_days": gex_days,
            "n_gex_archive_days": n_gex,
            "min_gex_days_required": MIN_GEX_DAYS,
            "opra_csv_columns": opra_cols,
            "opra_has_open_interest": has_oi,
            "opra_has_gamma": has_gamma,
            "spy_price_data": spy,
            "engine_feasibility_assessor": feas,
            "doctrine_refs": [
                "markdown/specs/GEX-PREMARKET-WIRING.md §6 ('Cannot be backtested')",
                "backtest/lib/engine/gex_regime.py::assess_backtest_feasibility "
                "(can_backtest_now=False)",
                "automation/scripts/gex_capture.py (Gamma_GexCapture, banking daily "
                "from 2026-06-19)",
                "CLAUDE.md C4/L171 (a positive average from a proxied level is an "
                "artifact, not an edge); BACKTESTING-PLAYBOOK OP-20 (no fabricated data).",
            ],
        },
        "blockers": blockers,
        "infeasible": bool(infeasible),
        # ── the 8 gates: untestable -> null / False, never fabricated ────────────
        "n_signals": 0,
        "n_trades": 0,
        "is_per_trade": None,
        "oos_per_trade": None,
        "best_config": None,
        "positive_quarters": None,
        "top5_day_pct": None,
        "beats_null": False,            # cannot beat a null we cannot compute
        "is_half_positive": False,
        "truncation_safe": False,       # not demonstrable without a real grid
        "clears_all_gates": False,
        "gates": {
            "oos_per_trade_gt_0": None,
            "positive_quarters_ge_4of6": None,
            "top5_day_pct_lt_200": None,
            "n_ge_20": False,
            "drop_top5_gt_0": None,
            "is_2025_half_gt_0": None,
            "beats_random_entry_null": None,
            "no_truncation_artifact": None,
            "note": "Every gate is untestable: there is no historical wall/max-pain "
                    "series to mark entries against. Reported null (not 0) so this is "
                    "not mistaken for a tested-and-failed result.",
        },
        # ── how to make it real ──────────────────────────────────────────────────
        "path_to_backtestable": {
            "step_1": "Let Gamma_GexCapture keep banking journal/gex-archive/{date}.json "
                      "daily (per-strike OI + per-contract gamma + spot). Already running.",
            "step_2": "Once >= ~60-90 archived days accumulate, build a marker that, for "
                      "each day, computes call_wall/put_wall/max-pain/zero-gamma-flip from "
                      "that day's archived chain (REUSE lib.engine.gex_regime — already "
                      "computes walls + zero-gamma; add max-pain = strike minimizing total "
                      "OI payoff).",
            "step_3": "Detect causal wall-interaction entries on RTH SPY bars (touch / "
                      "5m-close reject / reclaim of a wall, or drift toward max-pain), fill "
                      "the next bar open via lib.simulator_real.simulate_trade_real (C1), "
                      "split MAGNET (long-gamma days) vs REJECTION (short-gamma days) using "
                      "that day's net_gex_sign.",
            "step_4": "Run the full 8-gate suite (this file's schema) + the random-entry "
                      "null (autoresearch.null_baseline) + truncation guard "
                      "(lib.truncation_guard). RE-RUN THIS HUNT for real then.",
            "re_run_trigger": "n_gex_archive_days >= 60 with status==ok.",
        },
        "DISCLOSURE": {
            "why_not_a_proxy": "A wall proxied from round numbers / volume / back-filled "
                               "greeks is NOT the level dealer hedging actually defended; "
                               "any 'edge' on it measures the proxy, not gamma positioning "
                               "(C4/L171). Refused on purpose.",
            "no_fabrication": "Zero trades simulated. No OI/gamma invented. Gates null, "
                              "not 0, to avoid a false 'tested & failed' reading.",
            "live_value_now": "The single live tag (gex-regime.json, short_gamma_trend, "
                              "call_wall=put_wall=750 on 2026-06-19) is real-time situational "
                              "awareness only; N=1 is not a sample.",
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    # ── console verdict ──────────────────────────────────────────────────────────
    print("=== GAMMA_WALL_INTERACTION (novel-data) B4 VERDICT ===")
    print(f"verdict: {summary['verdict']}")
    print(f"gex-archive days (entire backtestable wall history): {n_gex} -> {gex_days}")
    print(f"OPRA cols: {opra_cols}  has_OI={has_oi} has_gamma={has_gamma}")
    print(f"SPY price data: {spy.get('trading_days')} days "
          f"({spy.get('window')})  available={spy.get('available')}")
    print(f"engine can_backtest_now: {feas.get('can_backtest_now')}")
    print("BLOCKERS:")
    for b in blockers:
        print(f"  - {b}")
    print(f"clears_all_gates: {summary['clears_all_gates']}  (untestable -> gates null)")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
