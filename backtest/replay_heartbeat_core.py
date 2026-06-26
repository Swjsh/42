"""replay_heartbeat_core.py — historical parity check of the LIVE wiring.

Proves heartbeat_core's payload assembly (ribbon/vix/levels/htf/baselines/bar_idx) reproduces
the production backtest's per-bar decision. Runs the real orchestrator on historical days
(ground truth), then for each evaluated bar rebuilds heartbeat_core's payload from the SAME
bars + injected VIX + the orchestrator's own levels, calls the engine decision boundary
(decide_payload), and compares.

The KEY metric is SCORE agreement (bear_score/bull_score) — that isolates the wiring (does my
live assembly feed the engine the same inputs?) from gate-config differences. Action agreement
is reported too. $0, offline, no market impact. Run: python backtest/replay_heartbeat_core.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import time as dtime
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
for p in ("backtest", "setup/scripts"):
    sys.path.insert(0, str(REPO / p))

from lib.orchestrator import run_backtest, _align_vix_to_spy  # noqa: E402
from lib.levels import detect_levels_at_bar, _detect_from_history  # noqa: E402
from lib.engine.engine_cli import decide_payload  # noqa: E402
import datetime as _dt  # noqa: E402
import heartbeat_core as hc  # noqa: E402

SPY_CSV = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-06-24.csv"
VIX_CSV = REPO / "backtest" / "data" / "vix_5m_2026-05-19_2026-06-24.csv"
N_DAYS = 8  # most-recent trading days in the file to replay (rest seeds levels/ribbon)


def main() -> int:
    spy = pd.read_csv(SPY_CSV)
    vix = pd.read_csv(VIX_CSV)
    # Parse EXACTLY like the orchestrator (pd.to_datetime WITHOUT utc -> keeps the ET offset),
    # then RTH-filter on .dt.time. This makes our spy index == run_backtest's spy_df index so the
    # decision row's bar_idx aligns directly. (utc=True made run_backtest RTH-filter on UTC time.)
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
    vix["timestamp_et"] = pd.to_datetime(vix["timestamp_et"])
    spy = spy[(spy["timestamp_et"].dt.time >= dtime(9, 30))
              & (spy["timestamp_et"].dt.time < dtime(16, 0))].reset_index(drop=True)
    spy["date"] = spy["timestamp_et"].dt.date
    days = sorted(spy["date"].unique())[-N_DAYS:]
    start, end = days[0], days[-1]
    print(f"replaying {len(days)} days: {start} .. {end}  (spy rows={len(spy)})")

    # 1) ground truth from the real engine. Align by the decision's OWN bar_idx (which indexes
    # run_backtest's spy_df == our identically-parsed RTH spy) — no fragile timestamp lookup.
    from lib.orchestrator import _params_to_kwargs
    _p = json.loads((REPO / "automation" / "state" / "params.json").read_text(encoding="utf-8"))
    res = run_backtest(spy.drop(columns=["date"]), vix, start_date=start, end_date=end,
                       **_params_to_kwargs(_p))
    decs = [d for d in res.decisions if isinstance(d.get("bar_idx"), int)]
    print("ground-truth decision keys:", sorted(list(res.decisions[0].keys()))[:14] if res.decisions else [])
    print(f"ground-truth evaluated bars: {len(decs)}  | orch trades: {len(res.trades)}")

    # 2) vix aligned to spy bars (same as orchestrator)
    vix_al = _align_vix_to_spy(spy.drop(columns=["date"]), vix)

    # VIX-MA PORT: orchestrator.py:801-817 verbatim — per-day prior-only VIX MAs from vix_df.
    # Inject the historical ground-truth dicts (NOT the live yfinance daily fetch, which won't
    # match). No-op on bear_score under current params (VIX_DECLINING_REQUIRED_BEAR off), but
    # keeps the input faithful so the field is correct the day J flips the flag.
    _vr = vix.copy()
    _vr["_date"] = pd.to_datetime(_vr["timestamp_et"], utc=True).dt.date
    _cbd = _vr.groupby("_date")["close"].last()
    _ds = sorted(_cbd.index)
    _ma5_per_day, _ma20_per_day = {}, {}
    for _di, _d in enumerate(_ds):
        if _di >= 5:
            _ma5_per_day[_d] = sum(_cbd[_ds[_di - 5 + _j]] for _j in range(5)) / 5.0
        if _di >= 20:
            _ma20_per_day[_d] = sum(_cbd[_ds[_di - 20 + _j]] for _j in range(20)) / 20.0

    # 3) replay heartbeat_core per evaluated bar
    spy2 = spy.copy()
    spy2["timestamp"] = spy2["timestamp_et"]
    params = json.loads((REPO / "automation" / "state" / "params.json").read_text(encoding="utf-8"))

    # LEVEL-SET PORT (census root-cause #1): the orchestrator FREEZES level_set once per day
    # at the day's first evaluated bar (orchestrator.py:914-920, _level_per_day cache keyed on
    # bar_date, computed from spy_df_full[ts <= first-eval-bar_time] via _detect_from_history)
    # and reuses level_set.active for EVERY bar of the day. detect_levels_at_bar(idx) instead
    # RE-derives per bar, so today's session-H/L + last_close/round-number levels drift bar-by-bar
    # -> a level_rejection trigger fires (or not) differently at the trigger bar -> filter-10
    # blocker mismatch. Reproduce the orchestrator's per-day freeze here and inject THAT.
    # include_first_hour_high is False under production params (_params_to_kwargs never maps it,
    # run_backtest defaults False) -> effective_levels == level_set.active, fhh_level==None.
    _spy_nb = spy2.drop(columns=["timestamp", "date"]).copy()  # _detect_from_history needs timestamp_et only
    _level_per_day: dict = {}
    _bar_date = spy2["timestamp_et"].dt.date
    _bar_time = spy2["timestamp_et"].dt.time
    for _i in range(len(spy2)):
        _bd = _bar_date.iloc[_i]
        if _bd in _level_per_day:
            continue
        # orchestrator's first level-cache bar = first bar of the date at/after 09:35 (the
        # time-window gate at orchestrator.py:890 skips < 09:35 BEFORE the level block).
        if _bar_time.iloc[_i] < _dt.time(9, 35):
            continue
        _hist = _spy_nb.iloc[: _i + 1].copy()  # spy_df_full[ts <= bar_time]; RTH-only (same as orch here)
        _level_per_day[_bd] = _detect_from_history(_hist, _bd)

    m = Counter()  # per-input match tallies
    bear_diffs = []
    hb_enters: dict[int, str] = {}  # bar_idx -> side ('P'/'C'); one ENTER per unique bar
    seen_bars: set[int] = set()
    n = 0
    for d in decs:
        idx = d["bar_idx"]
        if idx < 60 or idx + 2 > len(spy2):
            continue
        ts = spy2["timestamp_et"].iloc[idx]
        hist = spy2.iloc[: idx + 2]  # trigger=idx (n-2), confirmation=idx+1
        try:
            vix_now = float(vix_al.iloc[idx]); vix_prior = float(vix_al.iloc[idx - 1])
            # LEVEL-SET PORT: inject the orchestrator's per-day-FROZEN level_set.active/.multi_day
            # (not a per-bar re-derivation) so the trigger bar sees the SAME levels the orch saw.
            ls = _level_per_day.get(ts.date())
            if ls is None:  # pre-09:35 bar (shouldn't be an evaluated decision) — fall back
                ls = detect_levels_at_bar(spy2.drop(columns=["timestamp", "date"]), idx, ts)
            _bd = ts.date()
            vix5 = _ma5_per_day.get(_bd, 0.0); vix20 = _ma20_per_day.get(_bd, 0.0)
            payload = hc._build_payload(hist, params, vix=(vix_now, vix_prior),
                                        levels=(list(ls.active), list(ls.multi_day)),
                                        vix_ma=(vix5, vix20))
            if payload is None:
                continue
            v = decide_payload(payload)
        except Exception as e:  # noqa: BLE001
            m[f"replay_err:{type(e).__name__}"] += 1
            continue
        n += 1
        bc = payload["bar_ctx"]
        # LEVEL_STATES diagnostic: on bars where the orch fired a sequence_* trigger, confirm the
        # heartbeat-reconstructed bounce_history reaches the >=3-entry depth the trigger needs.
        _tf = d.get("triggers_fired") or []
        if "sequence_rejection" in _tf or "sequence_reclaim" in _tf:
            m["orch_had_seq"] += 1
            _lvls = bc.get("level_states") or {}
            if any((s.get("role") == "broken_to_resistance" and len(s.get("bounce_history", [])) >= 3)
                   or (s.get("role") == "broken_to_support" and len(s.get("bounce_history", [])) >= 3)
                   for s in _lvls.values()):
                m["hb_has_seq_state"] += 1
        # ---- INPUT DIAGNOSIS: where does my live assembly diverge from the orchestrator? ----
        if abs(float(bc["bar"]["close"]) - float(d.get("spy_close", -1))) < 0.01:
            m["spy_close_aligned"] += 1                      # same bar (offset sanity)
        if bc["ribbon_now"]["stack"] == d.get("ribbon_stack"):
            m["ribbon_stack_match"] += 1
        if d.get("ribbon_spread_cents") is not None and bc["ribbon_now"]["spread_cents"] is not None \
                and abs(bc["ribbon_now"]["spread_cents"] - d["ribbon_spread_cents"]) <= 1.0:
            m["spread_within_1c"] += 1
        if d.get("vix") is not None and abs(bc["vix_now"] - d["vix"]) <= 0.05:
            m["vix_within_0.05"] += 1
        if bc["htf_15m_stack"] == d.get("htf_15m_stack"):
            m["htf_match"] += 1
        # ---- SCORE ----
        gb, hb = d.get("bear_score"), v.get("bear_score")
        if isinstance(gb, (int, float)) and isinstance(hb, (int, float)):
            bear_diffs.append(abs(gb - hb))
            if gb == hb:
                m["bear_score_exact"] += 1
        _vd = v.get("verdict") or ""
        if _vd.startswith("ENTER") and idx not in seen_bars:
            seen_bars.add(idx)
            hb_enters[idx] = "P" if _vd == "ENTER_BEAR" else "C"

    # =====================================================================
    # ENTRY-FIDELITY GATE (permanent — the FINAL arm-gate, 2026-06-25)
    # ---------------------------------------------------------------------
    # Does heartbeat_core ENTER at the SAME bars/sides the production backtest
    # actually TRADES?  The raw per-bar ENTER stream over-counts for two reasons,
    # BOTH of which the live engine resolves but a stateless decide_payload does not:
    #   (a) DEDUP — while a position is open the live broker FLAT-verify
    #       (fleet_broker.is_flat_spy_options) returns NOT_FLAT, so no new entry
    #       fires. The orchestrator's equivalent is `skip_until_idx`: it does not
    #       even EVALUATE bars inside an open-position window, so those bars carry
    #       NO decision row. We model this with the orch trades' own exit bars.
    #   (b) QUALITY-LOCK — among FLAT bars, the orchestrator's per-day escalation
    #       lock (setup_quality_taken_today, orchestrator.py ~1170-1262) blocks a
    #       same-or-lower-quality re-entry on the same setup (action=SKIP_QUALITY_LOCK).
    #       heartbeat_core ports this lock (_quality_lock_check). The orch decision
    #       ledger is the GROUND TRUTH for the lock state: a SKIP_QUALITY_LOCK row is
    #       seeded by the orch's true per-day taken-quality — including entries the
    #       orch took then nulled by risk-sizing, which a from-scratch live
    #       reconstruction cannot see. So we gate the heartbeat ENTERs against the
    #       orch's OWN per-bar action: an ENTER survives iff the orch did not block
    #       that bar via the quality-lock.
    # After (a)+(b) the heartbeat trade set must EQUAL the backtest trade set
    # (same bar, same side). MATCHED == orch trades, EXTRA == 0, MISSED == 0.
    # =====================================================================
    ts_to_idx = {ts: i for i, ts in enumerate(spy["timestamp_et"])}

    def _bar_of(ts_val):
        if ts_val is None:
            return None
        t = pd.Timestamp(ts_val)
        bi = ts_to_idx.get(t)
        if bi is None:
            mm = spy[spy["timestamp_et"] == t]
            bi = int(mm.index[0]) if not mm.empty else None
        return bi

    orch_by_bar: dict[int, str] = {}   # entry bar_idx -> side
    blocked_pre: set[int] = set()      # bars inside an open-position window (dedup)
    for t in res.trades:
        ei = _bar_of(getattr(t, "entry_time_et", None))
        if ei is None:
            continue
        orch_by_bar[ei] = getattr(t, "side", "P")
        xi = _bar_of(getattr(t, "runner_exit_time_et", None))
        end = xi if xi is not None else ei + 5
        for bb in range(ei + 1, end + 1):
            blocked_pre.add(bb)

    orch_action = {d["bar_idx"]: d.get("action") for d in decs}
    LOCK_BLOCKS = {"SKIP_QUALITY_LOCK"}
    # deduped + quality-lock-gated heartbeat trades
    hb_trades = [b for b in sorted(hb_enters)
                 if b not in blocked_pre and orch_action.get(b) not in LOCK_BLOCKS]
    matched = [b for b in hb_trades if orch_by_bar.get(b) == hb_enters[b]]
    extra = [b for b in hb_trades if b not in matched]
    missed = [b for b in orch_by_bar if b not in set(hb_trades)]

    print("\n===== HEARTBEAT_CORE WIRING PARITY vs PRODUCTION BACKTEST =====")
    print(f"bars compared: {n}")
    print("\nINPUT FIDELITY (my live assembly vs the orchestrator's per-bar values):")
    for k in ("spy_close_aligned", "ribbon_stack_match", "spread_within_1c", "vix_within_0.05", "htf_match"):
        print(f"  {k:20} {m[k]:4}/{n} = {m[k]/n:.1%}" if n else k)
    print("\nSCORE:")
    score_ok = True
    if bear_diffs:
        score_pct = m['bear_score_exact'] / len(bear_diffs)
        print(f"  bear_score exact     {m['bear_score_exact']:4}/{len(bear_diffs)} = {score_pct:.1%}")
        print(f"  avg |bear diff|      {sum(bear_diffs)/len(bear_diffs):.2f}")
        score_ok = score_pct >= 0.95
    if m.get("orch_had_seq"):
        print(f"  seq-state depth>=3   {m['hb_has_seq_state']:4}/{m['orch_had_seq']} (hb reconstructed >=3-entry bounce_history on orch sequence_* bars)")

    print("\nENTRY FIDELITY (deduped + quality-lock-gated heartbeat trades vs backtest trades):")
    print(f"  raw heartbeat ENTER bars (pre-dedup/lock): {len(hb_enters)} -> {sorted(hb_enters)}")
    print(f"  backtest (orch) trades:                    {len(orch_by_bar)} -> {sorted(orch_by_bar)}")
    print(f"  deduped+lock-gated heartbeat trades:       {len(hb_trades)} -> {hb_trades}")
    print(f"  MATCHED (same bar+side): {len(matched)}/{len(orch_by_bar)}")
    print(f"  HEARTBEAT EXTRA (over-trade): {len(extra)} -> {extra}")
    print(f"  MISSED (orch took, hb skipped): {len(missed)} -> {missed}")
    errs = {k: c for k, c in m.items() if k.startswith("replay_err")}
    if errs:
        print("  replay errors:", errs)

    # ---- GATE VERDICT: fail loud so this is a STANDING arm-gate, not a one-off report ----
    entry_faithful = (len(extra) == 0 and len(missed) == 0 and len(matched) == len(orch_by_bar))
    ok = entry_faithful and score_ok
    print("\n===== ARM-GATE =====")
    print(f"  score parity >=95%:  {'PASS' if score_ok else 'FAIL'}")
    print(f"  entry fidelity:      {'PASS' if entry_faithful else 'FAIL'} "
          f"(matched={len(matched)}/{len(orch_by_bar)}, extra={len(extra)}, missed={len(missed)})")
    print(f"  ARM-READY: {'YES' if ok else 'NO'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
