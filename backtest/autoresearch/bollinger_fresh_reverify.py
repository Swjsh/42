"""Fresh-cache re-verification of the bollinger_squeeze chosen cell (WIRE-BOLLINGER #3).

Re-runs the CHOSEN cell — ATM | stop -8% | tp1 0.30 | sell 0.667 | chandelier-trail 0.15
(the strictly-better sibling of the headline ATM|stop-15 per the 2026-07-02 judge
spot-check: exp $34.9 vs $28.0, max_dd -$139 vs -$266, top5 33% vs 40%) — on the
NOW-FRESH data: SPY master (..2026-06-18) + newest rolling daily file (..2026-07-01),
OPRA real-fills cache last=2026-07-01 per data-coverage.json.

Signals come from the PORTED watcher (lib.watchers.bollinger_squeeze_watcher), with an
in-run parity assertion vs the original family_detectors detector — the same
signal-for-signal check the parity test pins (no parity, no wire).

FRAME CONVENTION (one variable = the fresh tail, nothing else):
  The master CSV stores a FIXED -04:00 offset year-round; the grind pipeline
  (ar.load_data + build_rth) strips tz keeping WALL time, so WINTER sessions parse
  as 10:30..15:55 (true 09:30..14:55 ET — the last true hour clipped). The whole
  validated baseline (316 signals, the elites) sits on that frame. A DST-correct
  UTC->ET re-parse CHANGES the winter signal population (first fresh-run attempt:
  360 signals with 124/80 in/out diffs clustered in Nov-Feb) — that mixes a data-
  convention change with the freshness change and voids comparability. So THIS
  script reproduces the grind frame BYTE-IDENTICALLY (ar.load_data master) and
  appends ONLY the post-2026-06-18 tail from the rolling file (June/July = EDT,
  where both conventions agree). Old-window signals are asserted == 316 exactly.
  The master-offset artifact itself is flagged separately (research-stack-wide).

Gates re-checked on the fresh window (family_grind bars + the L188 dir-null):
  candidate bar: OOS_exp>0, >=4/6 positive quarters, top5<200, n>=20
  stock null   : beats 10-seed random-entry MATCHING-exit null MAX + drop-top5 vs mean
  dir null     : beats 20-seed direction-controlled null (only decisive if the family
                 fires >80% of days — computed + disclosed either way)
  recency      : last-20-trades and 2026-06-19..07-01 fresh-tail P&L disclosed

Output: analysis/recommendations/bollinger-squeeze-fresh-reverify.json
Pure Python, $0, read-only vs production. ONE process (OPRA cache is per-process).

Run: backtest/.venv/Scripts/python.exe -m autoresearch.bollinger_fresh_reverify
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parent.parent
_ROOT = _REPO.parent
for _p in (str(_REPO), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from autoresearch import family_detectors as fdet                      # noqa: E402
from autoresearch import family_grind as fg                            # noqa: E402
from autoresearch import runner as ar                                  # noqa: E402
from autoresearch.recency_check import _latest_rolling, read_cache_last_date  # noqa: E402
from lib.watchers import bollinger_squeeze_watcher as bw               # noqa: E402

OUT = _ROOT / "analysis" / "recommendations" / "bollinger-squeeze-fresh-reverify.json"

# The chosen cell (family-grind elite, ATM column, judge-preferred by robustness)
SO = 0            # ATM
STOP = -0.08
TP1 = 0.30
TQ = 0.667
TRAIL = 0.15

MASTER_END = dt.date(2026, 6, 18)   # grind window end — fresh tail starts after this
GRIND_N_SIGNALS = 316               # family-grind-bollinger_squeeze.json n_signals


def _log(msg: str) -> None:
    print(f"{dt.datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


def _sig_key(s: dict) -> tuple:
    return (str(s["date"]), s["time"], s["bar_idx"], s["side"],
            s["entry_spot"], s["rejection_level"])


def load_grind_frame_plus_tail() -> pd.DataFrame:
    """The grind's frame BYTE-IDENTICALLY (ar.load_data master, wall-time convention)
    + ONLY the post-MASTER_END tail from the newest rolling daily file (EDT months —
    the two conventions agree there). Returns a raw spy frame for build_rth."""
    spy_m, _ = ar.load_data(dt.date(2025, 1, 1), MASTER_END)
    ts_m = pd.to_datetime(spy_m["timestamp_et"])
    if getattr(ts_m.dt, "tz", None) is not None:
        ts_m = ts_m.dt.tz_localize(None)          # wall time AS WRITTEN (grind convention)
    spy_m = spy_m.assign(timestamp_et=ts_m)

    tail = pd.read_csv(_latest_rolling("spy"))
    ts_t = (pd.to_datetime(tail["timestamp_et"], utc=True, format="mixed")
            .dt.tz_convert("America/New_York").dt.tz_localize(None))
    tail = tail.assign(timestamp_et=ts_t)
    tail = tail[ts_t.dt.date > MASTER_END]

    cols = ["timestamp_et", "open", "high", "low", "close", "volume"]
    return pd.concat([spy_m[cols], tail[cols]], ignore_index=True)


def main() -> int:
    t0 = time.time()
    cache_last = read_cache_last_date()
    _log(f"OPRA cache last = {cache_last}; loading grind frame + fresh tail...")
    spy = load_grind_frame_plus_tail()
    rth = fdet.build_rth(spy)
    ndays = rth["date"].nunique()
    first_d, last_d = rth["date"].min(), rth["date"].max()
    _log(f"RTH bars={len(rth)} days={ndays} frame={first_d}..{last_d}")

    # ── signals from the PORTED watcher, parity-asserted vs the original ──────
    sig_port = bw.detect_bollinger_squeeze_frame(rth)
    sig_ref = fdet.detect_bollinger_squeeze(rth)
    parity = [_sig_key(a) for a in sig_ref] == [_sig_key(b) for b in sig_port]
    n_old_window = sum(1 for s in sig_port if s["date"] <= MASTER_END)
    if not parity or n_old_window != GRIND_N_SIGNALS:
        _log(f"PARITY/BASELINE FAIL (parity={parity}, old-window n={n_old_window} "
             f"!= {GRIND_N_SIGNALS}) — aborting (no parity, no wire)")
        OUT.write_text(json.dumps({"error": "parity_or_baseline_fail",
                                   "parity": parity, "n_old_window": n_old_window,
                                   "n_ref": len(sig_ref), "n_port": len(sig_port)},
                                  indent=2, default=str), encoding="utf-8")
        return 1
    signals = sig_port
    n_fresh_signals = sum(1 for s in signals if s["date"] > MASTER_END)
    _log(f"signals={len(signals)} (old window: {n_old_window} == grind {GRIND_N_SIGNALS}; "
         f"fresh tail after {MASTER_END}: {n_fresh_signals}); parity: OK")

    firing = fg.firing_rate(rth, signals)
    directional = fg.is_directional_family(rth, signals)

    # ── the cell, real OPRA fills ──────────────────────────────────────────────
    _log(f"sim_cell ATM|stop{STOP} tp{TP1}/sell{int(TQ*100)}/trail{TRAIL} ...")
    fills, m = fg.sim_cell(rth, signals, SO, STOP, TP1, TQ, TRAIL)
    cb, cb_reasons = fg.candidate_bar(m)
    _log(f"cell: n={m.get('n')} exp=${m.get('exp')} oos_exp=${m.get('oos_exp')} "
         f"wf={m.get('wf')} qpf={m.get('qpf')} top5={m.get('top5_day_pct')}% "
         f"maxDD=${m.get('max_dd')} no_data={m.get('no_data')}")

    # fresh-tail recency (the trades the master-window grind never saw)
    tail_fills = [f for f in fills if fg._tdate(f) > MASTER_END]
    tail_pnl = round(sum(float(f.dollar_pnl) for f in tail_fills), 2)
    ordered = sorted(fills, key=lambda f: f.entry_time_et)
    last20 = ordered[-20:]
    last20_pnl = round(sum(float(f.dollar_pnl) for f in last20), 2)
    last20_wr = round(100 * sum(1 for f in last20 if float(f.dollar_pnl) > 0) / max(1, len(last20)), 1)
    _log(f"fresh tail (> {MASTER_END}): n={len(tail_fills)} pnl=${tail_pnl}; "
         f"last-20 trades pnl=${last20_pnl} wr={last20_wr}%")

    # ── stock null (10 seeds, MATCHING exit) ──────────────────────────────────
    _log("stock random-entry null (10 seeds, matching exit)...")
    window = fdet.FAMILY_WINDOW["bollinger_squeeze"]
    null = fg._run_null(rth, fills, SO, STOP, TP1, TQ, TRAIL, window)
    _log(f"null: pass={null['null_pass']} exp=${null['per_trade']} vs "
         f"max=${null['null_max']} drop5=${null['drop_top5_per_trade']} vs mean=${null['null_mean']}")

    # ── direction-controlled null (L188, 20 seeds) ─────────────────────────────
    _log("direction-controlled null (20 seeds)...")
    dir_null = fg._dir_null(rth, fills, SO, STOP, TP1, TQ, TRAIL, window,
                            null["drop_top5_per_trade"])
    _log(f"dir_null: pass={dir_null['dir_null_pass']} exp=${dir_null['per_trade']} vs "
         f"max=${dir_null['null_max']} (mean=${dir_null['null_mean']})")

    # side split (two-sided check on the fresh frame)
    by_side = defaultdict(lambda: [0.0, 0])
    for f in fills:
        by_side[f.side][0] += float(f.dollar_pnl)
        by_side[f.side][1] += 1
    side_split = {s: {"total": round(v[0], 2), "n": v[1],
                      "exp": round(v[0] / v[1], 2) if v[1] else None}
                  for s, v in by_side.items()}

    verdict_pass = bool(cb and null["null_pass"]
                        and (dir_null["dir_null_pass"] or not directional))
    result = {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "purpose": "WIRE-BOLLINGER step 3 — chosen-cell re-verification on the fresh-to-"
                   f"{cache_last} OPRA cache (alpha-plan rank #2, 2026-07-02)",
        "cell": {"family": "bollinger_squeeze", "strike": "ATM", "strike_offset": SO,
                 "stop_pct": STOP, "tp1": TP1, "tq": TQ, "trail": TRAIL, "qty": fg.QTY},
        "frame": {"first": str(first_d), "last": str(last_d), "trading_days": int(ndays),
                  "opra_cache_last": str(cache_last)},
        "signals": {"n": len(signals), "n_old_window": n_old_window,
                    "old_window_matches_grind_316": n_old_window == GRIND_N_SIGNALS,
                    "n_fresh_tail": n_fresh_signals,
                    "n_call": sum(1 for s in signals if s["side"] == "C"),
                    "n_put": sum(1 for s in signals if s["side"] == "P"),
                    "firing_rate": round(firing, 3), "family_directional": directional,
                    "port_parity_vs_original": parity},
        "frame_convention_disclosure": (
            "Grind wall-time convention reproduced byte-identically (master CSV stores a "
            "fixed -04:00 offset year-round; tz-strip keeps wall time, so winter sessions "
            "run 10:30..15:55 wall = true 09:30..14:55 ET, last true hour clipped). Fresh "
            "tail appended in EDT months where conventions agree. A DST-correct re-parse "
            "changes the winter signal population (360 vs 316) — flagged as a separate "
            "research-stack data artifact, NOT mixed into this re-verification."),
        "metrics": m,
        "candidate_bar": {"pass": cb, "fail_reasons": cb_reasons},
        "null": null,
        "dir_null": dir_null,
        "side_split": side_split,
        "recency": {"fresh_tail_after": str(MASTER_END), "fresh_tail_n": len(tail_fills),
                    "fresh_tail_pnl": tail_pnl, "last20_pnl": last20_pnl,
                    "last20_wr_pct": last20_wr},
        "grind_baseline_2026_06_25": {
            "n": 303, "exp": 34.9, "oos_exp": 43.6, "wf": 1.431, "qpf": 1.0,
            "top5_day_pct": 33.0, "max_dd": -139.2,
            "source": "analysis/recommendations/family-grind-bollinger_squeeze.json"},
        "verdict": "PASS" if verdict_pass else "FAIL",
        "authority": "real OPRA fills (C1); ported-watcher signals parity-asserted vs "
                     "family_detectors (C14); stock null (C3/L58/L171) + dir-null (L188)",
        "elapsed_min": round((time.time() - t0) / 60, 1),
    }
    OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    _log(f"VERDICT={result['verdict']} -> wrote {OUT.name} ({result['elapsed_min']} min)")
    return 0 if verdict_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
