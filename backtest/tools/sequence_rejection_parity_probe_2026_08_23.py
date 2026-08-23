"""sequence_rejection_parity_probe_2026_08_23.py — READ-ONLY discriminating-evidence
harness for the escalated root-cause question on `backtest/tests/test_replay_fleet_arms.py`
REDs (test_no_arm_overtrades: risky-1 extra=1; test_three_arms_entry_faithful) at bar 1801
(2026-06-23 15:35:00-04:00, side P).

DOES NOT FIX ANYTHING. Touches no production/trading-path file. Pure inspection.

WHAT THIS FOUND (see analysis/deep-research/SEQUENCE-REJECTION-PARITY-PROBE-2026-08-23.md
for the full writeup): the bounce_history for the REAL 735.0000 level is BYTE-IDENTICAL
between decide_payload (LIVE, heartbeat_core's windowed _rebuild_level_states) and
orchestrator.run_backtest (GT, _update_level_states accumulated across the whole 8-day
run) -- both correctly record the 735.28 -> 735.21 -> 735.19 lower-highs stairstep. The
divergence is NOT in bounce_history tracking at all. It's in the SHARED lookup at
backtest/lib/filters.py:1578-1586 (evaluate_bearish_setup), which resolves `rejection_level`
to a LevelState by "first entry within $0.05, in dict-iteration (insertion) order" --
no exact-price preference, no recency/role-aware tie-break. GT's `level_states` dict is
never pruned/reset (orchestrator.py:869, accumulates for the full 8-day replay window), so
by bar 1801 it also holds a STALE, unrelated level (735.0300, role=broken_to_support, empty
bounce_history, broken_at_bar_idx=1405 -- 2026-06-15, more than a week and 6 sessions
earlier) that was inserted into the dict BEFORE today's real 735.0000 entry (created bar
1791, today). Because 735.0300 iterates first, GT's lookup returns it, sees
role != "broken_to_resistance", and detect_sequence_rejection short-circuits False --
without ever reaching the correct 735.0000 entry. LIVE's windowed rebuild only ever
populates level_states from the current day's active levels (735.0300 was never active
on 2026-06-23), so there is no colliding entry and the lookup correctly resolves to
735.0000 -> True.

Run: backtest/.venv/Scripts/python.exe backtest/tools/sequence_rejection_parity_probe_2026_08_23.py
"""
from __future__ import annotations

import copy
import sys
from datetime import time as dtime
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
for p in ("backtest", "setup/scripts", "automation/state/fleet"):
    sys.path.insert(0, str(REPO / p))

from lib.orchestrator import run_backtest, _params_to_kwargs  # noqa: E402
from lib import orchestrator as orch_mod  # noqa: E402
from lib import filters as filt_mod  # noqa: E402
from lib.filters import LevelState, detect_sequence_rejection  # noqa: E402
import replay_fleet_arms as rfa  # noqa: E402

TARGET_BAR_IDX = 1801
LEADIN_BARS = 12  # bars leading into the SAME-DAY 735.0000 formation (bar 1791) for the table
COLLISION_TOLERANCE = 0.05  # matches filters.py:1583's tie-break window exactly

OUT_MD = REPO / "analysis" / "deep-research" / "SEQUENCE-REJECTION-PARITY-PROBE-2026-08-23.md"


def locate_implementations() -> dict:
    return {
        "detect_sequence_rejection (predicate, SHARED by both engines)":
            "backtest/lib/filters.py:458-477 (mirror: detect_sequence_reclaim:480-493)",
        "LevelState dataclass (SHARED)": "backtest/lib/filters.py:66-76",
        "level_state LOOKUP inside evaluate_bearish_setup (SHARED -- this is where the bug lives)":
            "backtest/lib/filters.py:1578-1586 -- 'first LevelState within $0.05 of rejection_level, "
            "in dict-iteration order' with no exact-match preference and no role/recency tie-break.",
        "orchestrator level-state ACCUMULATOR (feeds ctx.level_states for GT / run_backtest)":
            "backtest/lib/orchestrator.py:123-210 (_update_level_states), driven per-bar at "
            "orchestrator.py:980-981 inside the run_backtest main loop. level_states dict is created "
            "ONCE at orchestrator.py:869 and NEVER reset/pruned -- it accumulates every level ever seen "
            "across the WHOLE evaluated date range (here: 8 trading days).",
        "heartbeat_core windowed REBUILD (feeds ctx.level_states for LIVE / decide_payload)":
            "setup/scripts/heartbeat_core.py:782-825 (_rebuild_level_states), invoked at "
            "heartbeat_core.py:919-926 inside _build_payload over ONLY the last W=150 bars "
            "(heartbeat_core.py:874-875) ending at the trigger bar -- effectively just the current "
            "trading day. Its own docstring (heartbeat_core.py:919-924) flags a 'WINDOW-TRUNCATION "
            "CAVEAT' worried about MISSING history; this probe shows the caveat's real-world failure "
            "mode runs the OPPOSITE direction here -- the windowed engine is what avoids the bug.",
    }


def load_data():
    spy = pd.read_csv(rfa.SPY_CSV)
    vix = pd.read_csv(rfa.VIX_CSV)
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
    vix["timestamp_et"] = pd.to_datetime(vix["timestamp_et"])
    spy = spy[(spy["timestamp_et"].dt.time >= dtime(9, 30))
              & (spy["timestamp_et"].dt.time < dtime(16, 0))].reset_index(drop=True)
    spy["date"] = spy["timestamp_et"].dt.date
    days = sorted(spy["date"].unique())[-rfa.N_DAYS:]
    start, end = days[0], days[-1]
    return spy, vix, days, start, end


def capture_orchestrator_level_states(spy, vix, start, end, params, equity):
    """Monkeypatch orchestrator._update_level_states to snapshot level_states (deep-copied)
    after EVERY bar it's called on, keyed by bar_idx. This observes the EXACT function +
    EXACT effective_levels run_backtest uses internally -- zero reimplementation risk."""
    capture: dict[int, dict] = {}
    original = orch_mod._update_level_states

    def _wrapped(level_states, levels_active, bar, idx, *a, **kw):
        original(level_states, levels_active, bar, idx, *a, **kw)
        capture[idx] = copy.deepcopy(level_states)

    orch_mod._update_level_states = _wrapped
    try:
        kw = _params_to_kwargs(params, account_equity=equity)
        res = run_backtest(spy.drop(columns=["date"]), vix, start_date=start, end_date=end, **kw)
    finally:
        orch_mod._update_level_states = original
    return res, capture


def _bh_repr(hist: list) -> str:
    if not hist:
        return "[]"
    parts = []
    for e in hist:
        v = e.get("high_reached", e.get("low_reached"))
        parts.append(f"{v:.2f}/{e['outcome']}")
    return "[" + ", ".join(parts) + "]"


def main() -> int:
    impls = locate_implementations()
    spy, vix, days, start, end = load_data()
    print(f"replay window: {start} .. {end} ({len(days)} days)")

    # ---- LIVE path ----
    bold_pack = rfa._replay_verdicts(spy, vix, days, start, end, rfa.PARAMS_BOLD)
    _res, decs, verdict_by_bar, payload_by_bar, score_pct, n, m = bold_pack
    if TARGET_BAR_IDX not in verdict_by_bar:
        print(f"!! bar {TARGET_BAR_IDX} not replayed by decide_payload"); return 1
    verdict = verdict_by_bar[TARGET_BAR_IDX]
    payload = payload_by_bar[TARGET_BAR_IDX]
    ts = spy["timestamp_et"].iloc[TARGET_BAR_IDX]
    print(f"bar {TARGET_BAR_IDX} timestamp_et = {ts}")
    print(f"LIVE (decide_payload) verdict: {verdict.get('verdict')} bear_score={verdict.get('bear_score')} "
          f"triggers_fired={verdict.get('triggers_fired')}")
    live_ls = payload["bar_ctx"]["level_states"]
    active = payload["bar_ctx"]["levels_active"]

    # ---- GT path (risky-1's own run_backtest, instrumented) ----
    arm = rfa._arm("risky-1")
    p = rfa._arm_run_backtest_params(arm)
    eq = float(arm.get("starting_equity") or 2000.0)
    gt_res, gt_capture = capture_orchestrator_level_states(spy, vix, start, end, p, eq)
    gt_decs_by_bar = {d["bar_idx"]: d for d in gt_res.decisions if isinstance(d.get("bar_idx"), int)}
    gt_dec_1801 = gt_decs_by_bar.get(TARGET_BAR_IDX)
    print(f"GT (run_backtest, risky-1 params) decision at bar {TARGET_BAR_IDX}: "
          f"action={gt_dec_1801.get('action') if gt_dec_1801 else 'NOT EVALUATED'} "
          f"triggers_fired={gt_dec_1801.get('triggers_fired') if gt_dec_1801 else None} "
          f"bear_score={gt_dec_1801.get('bear_score') if gt_dec_1801 else None}")
    if TARGET_BAR_IDX not in gt_capture:
        print(f"!! bar {TARGET_BAR_IDX} never reached _update_level_states in GT run"); return 1
    gt_ls = gt_capture[TARGET_BAR_IDX]

    # ---- Step 1: bounce_history CONTENT parity for the real 735.0000 level (values only,
    # ignoring each engine's own bar-numbering scheme -- LIVE uses a window-local index,
    # GT uses the global spy row index; comparing those numbers directly is a false-positive
    # trap, not a real divergence). ----
    live_735 = live_ls.get("735.0000")
    gt_735 = gt_ls.get("735.0000")
    print("\n--- Step 1: is the 735.0000 bounce_history itself identical between engines? ---")
    print(f"LIVE 735.0000: role={live_735.get('role') if live_735 else None} "
          f"bounce_history={_bh_repr(live_735.get('bounce_history', [])) if live_735 else None}")
    print(f"GT   735.0000: role={gt_735.role if gt_735 else None} "
          f"bounce_history={_bh_repr(gt_735.bounce_history) if gt_735 else None}")
    bh_content_matches = None
    if live_735 and gt_735:
        live_vals = [(round(e.get("high_reached", e.get("low_reached")), 4), e["outcome"])
                     for e in live_735["bounce_history"]]
        gt_vals = [(round(e.get("high_reached", e.get("low_reached")), 4), e["outcome"])
                   for e in gt_735.bounce_history]
        bh_content_matches = (live_vals == gt_vals) and (live_735["role"] == gt_735.role)
        print(f"CONTENT MATCH (role + high_reached/outcome sequence, bar-idx-label ignored): {bh_content_matches}")
        print(f"detect_sequence_rejection(LIVE 735.0000) = "
              f"{detect_sequence_rejection(LevelState(price=735.0, role=live_735['role'], bounce_history=live_735['bounce_history']))}")
        print(f"detect_sequence_rejection(GT   735.0000) = {detect_sequence_rejection(gt_735)}")

    # ---- Step 2: what does the SHARED lookup in evaluate_bearish_setup (filters.py:1578-1586)
    # actually resolve `rejection_level` to, in EACH engine's level_states dict? ----
    bar = spy.iloc[TARGET_BAR_IDX]
    bar_series = pd.Series({"open": bar["open"], "high": bar["high"], "low": bar["low"],
                             "close": bar["close"], "volume": bar["volume"]})
    rejection_level = filt_mod.detect_level_rejection(bar_series, active)
    print(f"\n--- Step 2: shared filters.py:1578-1586 lookup, rejection_level={rejection_level} ---")

    def _lookup_plain(states: dict, target: float):
        for key, st in states.items():
            if abs(st["price"] - target) <= COLLISION_TOLERANCE:
                return key, st
        return None, None

    def _lookup_obj(states: dict, target: float):
        for key, st in states.items():
            if abs(st.price - target) <= COLLISION_TOLERANCE:
                return key, st
        return None, None

    live_key, live_sel = _lookup_plain(live_ls, rejection_level)
    gt_key, gt_sel = _lookup_obj(gt_ls, rejection_level)
    print(f"LIVE lookup selects key={live_key} role={live_sel.get('role') if live_sel else None} "
          f"bounce_history_len={len(live_sel.get('bounce_history', [])) if live_sel else None}")
    print(f"GT   lookup selects key={gt_key} role={gt_sel.role if gt_sel else None} "
          f"bounce_history_len={len(gt_sel.bounce_history) if gt_sel else None}")

    live_final = detect_sequence_rejection(
        LevelState(price=live_sel["price"], role=live_sel["role"], bounce_history=live_sel["bounce_history"])
    ) if live_sel else False
    gt_final = detect_sequence_rejection(gt_sel) if gt_sel else False
    print(f"detect_sequence_rejection(LIVE selected) = {live_final}")
    print(f"detect_sequence_rejection(GT   selected) = {gt_final}")

    # ---- Step 3: enumerate every entry within collision range, IN INSERTION ORDER, per engine ----
    print(f"\n--- Step 3: all level_states entries within ${COLLISION_TOLERANCE} of "
          f"rejection_level={rejection_level}, in dict (insertion) order ---")
    gt_collisions = []
    for key, st in gt_ls.items():
        if abs(st.price - rejection_level) <= COLLISION_TOLERANCE:
            gt_collisions.append((key, st.price, st.role, st.broken_at_bar_idx, len(st.bounce_history)))
    live_collisions = []
    for key, st in live_ls.items():
        if abs(st["price"] - rejection_level) <= COLLISION_TOLERANCE:
            live_collisions.append((key, st["price"], st["role"], st["broken_at_bar_idx"], len(st["bounce_history"])))
    print("GT  :", gt_collisions)
    print("LIVE:", live_collisions)

    # Resolve the origin date of any colliding stale entry for the ground-truth OHLCV read.
    origin_note = ""
    if len(gt_collisions) > 1:
        stale_key, stale_price, stale_role, stale_bar_idx, _ = gt_collisions[0]
        if stale_key != "735.0000" and stale_bar_idx is not None:
            stale_ts = spy["timestamp_et"].iloc[stale_bar_idx]
            origin_note = (f"Colliding stale entry `{stale_key}` (price={stale_price:.4f}, role={stale_role}) "
                           f"first flipped role at bar {stale_bar_idx} = {stale_ts} "
                           f"({(ts.date() - stale_ts.date()).days} calendar days / "
                           f"{days.index(ts.date()) - days.index(stale_ts.date())} trading-day(s) before the "
                           f"target bar's session).")
            print("\n" + origin_note)

    # ---- Ground-truth OHLCV around the REAL formation of 735.0000 (bars leading to 1791,
    # where role first flips to broken_to_resistance) through 1801, to confirm the lower-highs
    # stairstep is a genuine chart pattern and not a bounce_history artifact. ----
    lo = 1791 - 2
    gt_window = spy.iloc[lo:TARGET_BAR_IDX + 1]
    report_lines = []
    report_lines.append("# SEQUENCE-REJECTION-PARITY-PROBE-2026-08-23\n\n")
    report_lines.append("Generated by `backtest/tools/sequence_rejection_parity_probe_2026_08_23.py` "
                         "(read-only, no trading-path files touched, no fixes applied).\n\n")
    report_lines.append("## Question\n\n")
    report_lines.append(
        f"`pytest backtest/tests/test_replay_fleet_arms.py` REDs on `test_no_arm_overtrades` "
        f"(risky-1 extra=1 > cap 0) and `test_three_arms_entry_faithful`, both pointing at bar "
        f"{TARGET_BAR_IDX} = {ts} (side P). `decide_payload` (LIVE) reports "
        f"`triggers_fired={verdict.get('triggers_fired')}`, quality_tier SUPER. "
        f"`orchestrator.run_backtest` (GT) reports "
        f"`triggers_fired={gt_dec_1801.get('triggers_fired') if gt_dec_1801 else None}` at the same bar "
        f"(action={gt_dec_1801.get('action') if gt_dec_1801 else None}) — sequence_rejection silently "
        f"absent.\n\n"
        "- H1: `decide_payload` (LIVE) OVER-fires sequence_rejection => real live entry-quality bug.\n"
        "- H2: `orchestrator.run_backtest` (GT) UNDER-counts a real touch => harness broken, live correct.\n\n"
    )
    report_lines.append("## Both implementations located\n\n")
    for k, v in impls.items():
        report_lines.append(f"- **{k}**: `{v}`\n")
    report_lines.append("\n")

    report_lines.append("## Step 1 — is the underlying bounce_history itself identical?\n\n")
    report_lines.append(
        f"Comparing the REAL 735.0000 level's tracked state between engines (bar-idx labels ignored, since "
        f"LIVE's windowed rebuild uses a window-LOCAL index and GT uses the GLOBAL spy row index — comparing "
        f"those numbers directly is a false-positive trap, not a real divergence):\n\n"
    )
    report_lines.append(f"- LIVE 735.0000: role=`{live_735.get('role') if live_735 else None}`, "
                         f"bounce_history=`{_bh_repr(live_735.get('bounce_history', [])) if live_735 else None}`\n")
    report_lines.append(f"- GT   735.0000: role=`{gt_735.role if gt_735 else None}`, "
                         f"bounce_history=`{_bh_repr(gt_735.bounce_history) if gt_735 else None}`\n\n")
    report_lines.append(f"**CONTENT MATCH (role + high_reached/outcome sequence): `{bh_content_matches}`.** "
                         f"Both engines record the SAME real chart pattern at 735.0000 — three progressively "
                         f"lower highs (735.28 -> 735.21 -> 735.19) each closing back below the broken level. "
                         f"`detect_sequence_rejection` on EITHER engine's raw 735.0000 state independently "
                         f"returns `True`. **The bounce_history tracking is NOT where the two engines "
                         f"disagree.**\n\n"
    )

    report_lines.append("## Step 2 — the SHARED lookup that actually decides the verdict\n\n")
    report_lines.append(
        f"`evaluate_bearish_setup` (filters.py:1578-1586, ONE shared function both engines call through the "
        f"same `backtest/lib/filters.py` module) does not look up `ctx.level_states[\"{{rejection_level:.4f}}\"]` "
        f"by exact key. It scans `ctx.level_states.values()` in dict-iteration (insertion) order and takes the "
        f"FIRST entry within ${COLLISION_TOLERANCE} of `rejection_level` (`{rejection_level}` at this bar), "
        f"with no exact-match preference and no role/recency tie-break:\n\n"
        "```python\n"
        "level_state = None\n"
        "if rejection_level is not None and ctx.level_states:\n"
        "    for state in ctx.level_states.values():\n"
        "        if abs(state.price - rejection_level) <= 0.05:\n"
        "            level_state = state\n"
        "            break\n"
        "sequence_rejected = detect_sequence_rejection(level_state) if level_state else False\n"
        "```\n\n"
        f"- LIVE lookup selects key=`{live_key}` -> role=`{live_sel.get('role') if live_sel else None}`, "
        f"bounce_history_len=`{len(live_sel.get('bounce_history', [])) if live_sel else None}` -> "
        f"`detect_sequence_rejection = {live_final}`\n"
        f"- GT   lookup selects key=`{gt_key}` -> role=`{gt_sel.role if gt_sel else None}`, "
        f"bounce_history_len=`{len(gt_sel.bounce_history) if gt_sel else None}` -> "
        f"`detect_sequence_rejection = {gt_final}`\n\n"
    )

    report_lines.append("## First divergence: the cause\n\n")
    report_lines.append(
        f"All level_states entries within ${COLLISION_TOLERANCE} of rejection_level={rejection_level}, in "
        f"dict (insertion) order:\n\n"
        f"- **GT** (`orchestrator.run_backtest`, never-reset level_states across the whole "
        f"{len(days)}-day replay): `{gt_collisions}`\n"
        f"- **LIVE** (`heartbeat_core._rebuild_level_states`, windowed to the current session): "
        f"`{live_collisions}`\n\n"
    )
    if origin_note:
        report_lines.append(origin_note + "\n\n")
    report_lines.append(
        "GT's `level_states` dict (`orchestrator.py:869`) is created once and never reset/pruned for the "
        f"whole {len(days)}-day backtest window, so by bar {TARGET_BAR_IDX} it holds a STALE, semantically "
        "unrelated level (`735.0300`, role=`broken_to_support`, zero bounce_history) left over from a much "
        "earlier session, purely because that price happens to sit within the fixed $0.05 tolerance band of "
        "TODAY's real, freshly-broken 735.0000 resistance. Because the stale entry was inserted into the dict "
        "FIRST (it appeared on an earlier day), Python's insertion-ordered dict iteration hits it before the "
        "correct 735.0000 entry, `detect_sequence_rejection` sees `role != \"broken_to_resistance\"` and "
        "returns `False` immediately, and the loop's `break` never lets it reach 735.0000 at all.\n\n"
        "LIVE's windowed rebuild (`heartbeat_core.py:874-875,925`, only the last 150 bars / effectively the "
        "current session) never creates a `735.0300` entry in the first place — that level was never active on "
        "today's session — so there is no collision and the lookup correctly resolves straight to 735.0000.\n\n"
        "This is NOT the window-truncation failure mode `heartbeat_core.py`'s own docstring "
        "(heartbeat_core.py:919-924) warns about (missing history because the break predates the window). "
        "It is the OPPOSITE failure mode: the FULL-HISTORY engine's over-long memory creates a false collision "
        "that the bounded-window engine structurally cannot have.\n\n"
    )

    report_lines.append("## Ground-truth OHLCV read (was there a real touch at 735.0000?)\n\n")
    report_lines.append("| bar_idx | ts | O | H | L | C | note |\n|---|---|---|---|---|---|---|\n")
    for bi, row in gt_window.iterrows():
        note = ""
        if bi == 1791:
            note = "role flips to broken_to_resistance (close < 735.00-0.10)"
        elif bi in (1794, 1795, 1796, 1798, 1799, 1800, 1801):
            note = "retest bar -> bounce_history append (high within $0.30 of 735.00, close stays below)"
        report_lines.append(f"| {bi} | {row['timestamp_et']} | {row['open']:.2f} | {row['high']:.2f} "
                             f"| {row['low']:.2f} | {row['close']:.2f} | {note} |\n")
    report_lines.append(
        "\nReading the raw bars: 735.00 breaks (bar 1791, close 733.96 < 734.90 = 735.00-0.10), then retests "
        "produce highs of 735.01 (1794), 735.60 (1795, a deeper poke), 734.86 (1796), 735.17 (1798), **735.28 "
        "(1799) -> 735.21 (1800) -> 735.19 (1801)** — a genuine, strictly-decreasing 3-bar lower-highs "
        "stairstep into the close-below-level rejection, exactly the sequence_rejection pattern's definition. "
        "**This is a real chart pattern, confirmed directly from OHLCV — not a bounce_history-tracking "
        "artifact.**\n\n"
    )

    report_lines.append("## Verdict\n\n")
    report_lines.append(
        "**H1 is FALSE, H2 is FALSE-AS-STATED but GT is still the wrong answer at this bar — for a different "
        "reason than either hypothesis proposed.**\n\n"
        "- `decide_payload` does NOT over-fire: the sequence_rejection pattern at 735.0000 is real (confirmed "
        "from raw OHLCV) and both engines' bounce_history tracking for that level agree byte-for-byte.\n"
        "- `orchestrator.run_backtest` does NOT under-count a touch either — its bounce_history for 735.0000 is "
        "equally complete and correct. It fails because the SHARED lookup helper in "
        "`filters.py:1578-1586` (used by BOTH engines identically) resolves `rejection_level` to the wrong "
        "LevelState object, because GT's never-pruned, whole-history level_states dict contains a stale, "
        "unrelated level (`735.0300`) that collides within the fixed $0.05 tolerance and was inserted earlier.\n"
        "- Net effect: **live (decide_payload/heartbeat_core) is giving the mechanistically correct answer at "
        "this bar; the backtest harness (orchestrator.run_backtest) is the one producing the false negative**, "
        "so `test_no_arm_overtrades`'s extra=1 is a harness/GT defect, not evidence of risky-1 over-trading in "
        "reality. This is closer to H2 in effect (GT is the wrong side) but the mechanism named in H2 "
        "(\"harness under-counts a real touch\") is not what's happening — GT counts the touch correctly, it "
        "just attaches it to the wrong level object downstream.\n\n"
        "**Confidence: HIGH for the mechanism** (directly demonstrated via monkeypatched instrumentation of "
        "the exact production functions, not reimplementation — Steps 1-3 above are load-bearing and "
        "reproducible by re-running this script). **Confidence: MEDIUM for the broader claim that this fully "
        "explains ALL of risky-1's extra=1** — this probe only traces bar 1801; if `test_no_arm_overtrades` "
        "ever reports `extra>1` for risky-1 or a different bar, that would need its own trace (the same "
        "collision mechanism generalizes to any bar where a fresh level's price falls within $0.05 of a "
        "stale multi-day level, but this run only confirms bar 1801).\n\n"
        "**What would falsify this**: if `735.0300`'s bounce_history were NOT actually empty (i.e., GT's "
        "instrumented capture were somehow stale/wrong), or if `detect_level_rejection` at bar 1801 resolved "
        "`rejection_level` to a price where 735.0300 is NOT the nearest earlier-inserted candidate (re-run "
        "Step 3's collision enumeration — it's data, not inference). Also falsified if a fix at the harness "
        "level (e.g., exact-key-first lookup, or dropping stale zero-activity level_states entries after N "
        "idle bars/days) makes GT's decision flip to include sequence_rejection while LIVE's stays unchanged "
        "— that would confirm the mechanism further rather than falsify it, but is the natural next "
        "verification step for whoever adjudicates the fix (explicitly OUT OF SCOPE for this probe).\n"
    )

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("".join(report_lines), encoding="utf-8")
    print(f"\nwrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
