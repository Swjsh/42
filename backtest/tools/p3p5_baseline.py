"""p3p5_baseline.py -- shared gate-OFF baseline builder for PROFIT-P3 (morning-gate) and
PROFIT-P5 (expected-move-gate) pre-registered studies (analysis/recommendations/
prereg-morning-gate-2026-07-11.json, prereg-expected-move-gate-2026-07-11.json).

REUSE (OP-22, zero reinvention): imports ribbon_ride_strike_exit_ab.py's cohort loader +
OPRA bar fetcher + SS-B replay engine (structure_stop_study.py) UNCHANGED, so this study's
gate-OFF baseline is built through the SAME already-tested pipeline PROFIT-P2 used -- and so
the P3/P5 registrations' own required cross-check ("the two studies' gate-OFF baselines must
match exactly ... a mismatch means one of them drifted") holds BY CONSTRUCTION, since both
runners import THIS module's build_baseline(), not two independent implementations.

STRIKE = OTM-2 (so=2) fixed for BOTH studies. Neither registration names a strike (both test
an ENTRY-TIME / EXPECTED-MOVE gate, not a strike axis), so this is a disclosed FILLED GAP,
not a re-pick of anything the registration froze: OTM-2 is (a) P5's own frozen V2
delta_proxy_table's most natural entry point (that table has no ATM row -- OTM-3/OTM-2/OTM-1/
ITM-2 only) and (b) the sibling PROFIT-P2 script's own CONTROL_STRIKE, i.e. the established
"current-tier" convention for this exact research lineage. DISCLOSED: CLAUDE.md's 2026-07-11
reconciliation records core Safe's LIVE strike truth as ATM (V15_SAFE_TIERS) -- OTM-2 here is
a research-lineage convention choice for gate-isolation purposes, not a claim about the live
account's current strike.

EXIT SHAPE = SS-B (structure_stop_study.SS_B_SHAPE, structure-stop primary + trailing
runner) fixed for BOTH arms of every comparison in both studies -- matches CLAUDE.md's live
chart-stop-primary doctrine (2026-06-18) and is held IDENTICAL between gate-ON and gate-OFF
(only entry inclusion differs, per each registration's own gate_mechanics statement: "a signal
... produces SKIP instead of ENTER ... exactly how the existing 09:35 floor behaves today").

POPULATION = _signal_cache.load_or_build_signals() (cached; n=250 as last built 2025-01-06..
2026-06-17 per PROFIT-P2's own report) -- the SAME generator strategy_space_grind/family_grind
and PROFIT-P2 use ("the runner MUST reuse that generator, not a re-derived signal set").
DISCLOSED WINDOW GAP: the cache's own achieved span is used AS-IS rather than re-run to the
registration's stated 2026-06-25 window end -- a truncation of roughly a week at the tail
(no OPRA/SPY re-fetch performed), disclosed per each registration's own "no silent population
substitution" clause. This is a WINDOW gap, not a SCOPE violation: no excluded setup
(vwap_continuation / j_vwap_reclaim_fb / j_vix_dayside) ever enters the population -- the
cache is built exclusively from ribbon_ride BULLISH_RECLAIM/BEARISH_REJECTION signals.

QTY = 10 (t4 / p5_topcell_real_fills_confirm / structure_stop_study / PROFIT-P2 Layer-A
convention -- dollar figures are RELATIVE for shape/gate comparison, not the OP-16
account-size absolute).

The hypothesis-source window (2026-06-26..2026-07-09) is excluded from the population before
any battery stage runs (no-peeking, matches both registrations byte-for-byte) -- moot in
practice since the cached cohort's own END (2026-06-17/18) already predates it, but the
exclusion filter is applied explicitly anyway so a future cache rebuild that extends past
2026-06-18 stays correct without code changes.

CACHING: the (fetch + SS-B replay) loop is the expensive step (one OPRA contract read per
signal). Cached to analysis/exit-parity/p3p5-baseline-cache.json, keyed on a content hash of
the knobs that determine the result (SO/QTY/SHAPE/hypothesis-window/n_raw_cohort) so a stale
cache is detected and rebuilt rather than silently reused.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

import ribbon_ride_strike_exit_ab as ab       # noqa: E402 -- reused cohort loader + fetcher + SS-B shape
import structure_stop_study as sss            # noqa: E402
from exit_manager import TIME_STOP_ET         # noqa: E402
from autoresearch.strategy_space_grind import OOS_BOUNDARY  # noqa: E402

CACHE_PATH = REPO / "analysis" / "exit-parity" / "p3p5-baseline-cache.json"

SO = 2                       # OTM-2, see module docstring
QTY = ab.QTY                 # 10, Layer-A convention
SHAPE = dict(ab.SS_B_SHAPE)  # SS-B, reused unchanged
HYPOTHESIS_SOURCE_WINDOW = (dt.date(2026, 6, 26), dt.date(2026, 7, 9))  # excluded, no-peeking


def _knob_hash(n_raw: int) -> str:
    payload = json.dumps({"so": SO, "qty": QTY, "shape": SHAPE,
                          "hyp_window": [str(d) for d in HYPOTHESIS_SOURCE_WINDOW],
                          "n_raw": n_raw}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def log(msg: str) -> None:
    print(f"[p3p5-baseline] {msg}", flush=True)


def build_baseline(force: bool = False) -> tuple[list[dict], pd.DataFrame, dict, dict]:
    """Returns (trades, spy_full, spy_by_date, meta).

    trades: list of dicts -- date (dt.date), entry_ts (dt.datetime, ET-naive), side ("C"/"P"),
    direction ("bull"/"bear"), pnl (float), entry_premium (float), structure_fired (bool).
    This is the GATE-OFF population both studies filter down from.
    """
    prepped, spy_full, spy_by_date = ab.load_cohort()
    key = _knob_hash(len(prepped))

    if CACHE_PATH.exists() and not force:
        cached = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if cached.get("knob_hash") == key:
            trades = [
                {**t, "date": dt.date.fromisoformat(t["date"]),
                 "entry_ts": dt.datetime.fromisoformat(t["entry_ts"])}
                for t in cached["trades"]
            ]
            log(f"cache HIT ({CACHE_PATH.name}, hash={key}): n={len(trades)} trades, "
                f"no OPRA re-fetch")
            return trades, spy_full, spy_by_date, cached["meta"]
        log(f"cache STALE (hash {cached.get('knob_hash')} != {key}) -- rebuilding")

    trades: list[dict] = []
    n_no_bars = 0
    n_excluded_hyp_window = 0
    for s in prepped:
        date = s["date_obj"]
        if HYPOTHESIS_SOURCE_WINDOW[0] <= date <= HYPOTHESIS_SOURCE_WINDOW[1]:
            n_excluded_hyp_window += 1
            continue
        fetched = ab.fetch_entry_and_bars(float(s["entry_spot"]), s["side"], date,
                                          s["entry_ts_obj"], SO, old_semantics=False)
        if fetched is None:
            n_no_bars += 1
            continue
        entry_premium, norm_bars = fetched
        r = sss.replay_structure_aware(entry_premium, s["side"], QTY, norm_bars,
                                       s["ss_time"], SHAPE, TIME_STOP_ET)
        trades.append({
            "date": date, "entry_ts": s["entry_ts_obj"], "side": s["side"],
            "direction": s["direction"], "pnl": round(float(r["pnl"]), 2),
            "entry_premium": round(float(entry_premium), 4),
            "structure_fired": bool(r["structure_fired"]),
        })

    meta = {
        "strike_offset": SO, "qty": QTY, "exit_shape": "SS-B",
        "signal_source": "_signal_cache.load_or_build_signals()",
        "n_raw_cohort": len(prepped),
        "n_excluded_hypothesis_source_window": n_excluded_hyp_window,
        "n_no_local_opra_bars": n_no_bars,
        "n_final": len(trades),
        "window_achieved": (f"{min(t['date'] for t in trades)}..{max(t['date'] for t in trades)}"
                            if trades else None),
        "oos_boundary": str(OOS_BOUNDARY),
        "total_pnl": round(sum(t["pnl"] for t in trades), 2),
        "expectancy": round(sum(t["pnl"] for t in trades) / len(trades), 2) if trades else None,
    }

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps({
        "knob_hash": key, "generated_at": dt.datetime.now().isoformat(),
        "meta": meta,
        "trades": [{**t, "date": str(t["date"]), "entry_ts": t["entry_ts"].isoformat()}
                   for t in trades],
    }, indent=2), encoding="utf-8")
    log(f"cache BUILT ({CACHE_PATH.name}, hash={key}): n={len(trades)} trades "
        f"(dropped {n_no_bars} no-bars, {n_excluded_hyp_window} hyp-window), "
        f"exp=${meta['expectancy']}, total=${meta['total_pnl']}")
    return trades, spy_full, spy_by_date, meta


if __name__ == "__main__":
    trades, spy_full, spy_by_date, meta = build_baseline(force="--force" in sys.argv)
    print(json.dumps(meta, indent=2, default=str))
