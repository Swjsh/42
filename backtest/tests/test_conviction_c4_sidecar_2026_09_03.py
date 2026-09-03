"""Guard suite for setup/scripts/conviction_c4_sidecar.py -- F4 CONVICTION C4 POLARITY
SIDECAR + FLEET COVERAGE (2026-09-03, descends from range-extreme-dead.md / H2).

Pins the mechanics that would matter if broken:
  1. THRESHOLD ARITHMETIC. Live polarity mirrors conviction.py's own rule exactly (boundary
     inclusive both directions); continuation polarity is its mirror image.
  2. RE-DERIVED TOTAL, NOT RE-INVOKED score_conviction(). The sidecar's core-row scoring
     reads STORED components and re-derives `total` (total_live - orig_C4 + flipped_C4).
     Equivalence between "sum stored components via conviction._SCORING_KEYS" and the row's
     own stored `total` is proven directly against >=20 REAL post-fix ledger rows -- this is
     what licenses treating that re-derivation as a faithful stand-in for a fresh
     score_conviction() call (which would need level_records/level_states this ledger row
     does not retain).
  3. COVERAGE LABELS NEVER BLUR. Core rows get real floor-based `would_block_*`; fleet rows
     (no floor -- no C1/C2/C3/C5/C6/C7 at a PLACED row) get ONLY `would_block_*_c4proxy`.
     The two must never be readable under the same key.
  4. NO LOOK-AHEAD ON THE TAPE PREFIX. range_position_from_tape must use only bars at or
     before the trigger time, matching heartbeat_core.py's `win.iloc[:trig_idx+1]`
     convention.
  5. IDEMPOTENT. Re-running against the same fixtures must never duplicate a ledger row.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import conviction as cv  # noqa: E402  -- frozen, read-only
import conviction_c4_sidecar as sc  # noqa: E402


# ---------------------------------------------------------------------------------
# 1. C4 threshold arithmetic -- both polarities, boundary-inclusive
# ---------------------------------------------------------------------------------
def test_live_polarity_matches_conviction_py_exactly():
    # conviction.py: call scores when pos <= 0.30 (inclusive); put when pos >= 0.70 (incl.)
    assert sc.c4_live_score("C", 0.30) == 1
    assert sc.c4_live_score("C", 0.301) == 0
    assert sc.c4_live_score("P", 0.70) == 1
    assert sc.c4_live_score("P", 0.699) == 0
    assert sc.LIVE_CALL_MAX_POS == cv.RANGE_EXTREME_PCT
    assert sc.LIVE_PUT_MIN_POS == pytest.approx(1.0 - cv.RANGE_EXTREME_PCT)


def test_continuation_polarity_is_the_mirror_image():
    # continuation: call rewards pos >= 0.70, put rewards pos <= 0.30 -- the OPPOSITE side
    assert sc.c4_continuation_score("C", 0.70) == 1
    assert sc.c4_continuation_score("C", 0.699) == 0
    assert sc.c4_continuation_score("P", 0.30) == 1
    assert sc.c4_continuation_score("P", 0.301) == 0
    assert sc.CONTINUATION_CALL_MIN_POS == sc.LIVE_PUT_MIN_POS
    assert sc.CONTINUATION_PUT_MAX_POS == sc.LIVE_CALL_MAX_POS


def test_mid_range_scores_zero_under_both_polarities():
    # pos=0.50 is nobody's extreme under either polarity
    assert sc.c4_live_score("C", 0.50) == 0
    assert sc.c4_continuation_score("C", 0.50) == 0
    assert sc.c4_live_score("P", 0.50) == 0
    assert sc.c4_continuation_score("P", 0.50) == 0


def test_score_none_on_missing_pos_or_bad_side():
    assert sc.c4_live_score("C", None) is None
    assert sc.c4_continuation_score("X", 0.1) is None


# ---------------------------------------------------------------------------------
# 2. score_core_row -- re-derive total from stored components
# ---------------------------------------------------------------------------------
def _core_row(total=5, floor=5, would_block=False, side="C", pos=0.81, range_extreme=0,
              degraded=None):
    return {
        "account": "bold", "ts_et": "2026-08-27T09:47:05", "side": side,
        "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
        "conviction": {
            "total": total, "floor_effective": floor, "would_block": would_block, "k": 0,
            "components": {"named_level": 2, "multi_day_memory": 1, "fresh_test": 0,
                           "range_extreme": range_extreme, "structure_agreement": 0,
                           "elite_trigger": 1, "zone_stack": 0, "range_position": pos},
            "degraded_components": degraded or [],
        },
    }


def test_score_core_row_flips_c4_and_rederives_total():
    # call at pos=0.81: live C4=0 (needs <=0.30), continuation C4=1 (needs >=0.70).
    # total_live=4 (0+1+0+0+0+1+0+2... use the helper's fixed sum: named2+mem1+elite1=4),
    # floor=5 -> blocked live. total_continuation = 4 - 0 + 1 = 5 -> NOT blocked (5 !< 5).
    row = _core_row(total=4, floor=5, would_block=True, side="C", pos=0.81, range_extreme=0)
    out = sc.score_core_row(row)
    assert out["not_applicable"] is False
    assert out["c4_live"] == 0
    assert out["c4_continuation"] == 1
    assert out["c4_flip"] is True
    assert out["total_continuation"] == 5
    assert out["would_block_continuation"] is False
    assert out["would_block_flip"] is True  # was blocked live, now allowed continuation


def test_score_core_row_no_flip_when_still_below_floor():
    # pos=0.81, call, total_live=3, floor=6 -> total_continuation=4, still < 6 -> still blocked
    row = _core_row(total=3, floor=6, would_block=True, side="C", pos=0.81, range_extreme=0)
    out = sc.score_core_row(row)
    assert out["would_block_continuation"] is True
    assert out["would_block_flip"] is False


def test_score_core_row_degraded_range_extreme_is_not_applicable():
    row = _core_row(degraded=["range_extreme"])
    out = sc.score_core_row(row)
    assert out["not_applicable"] is True
    assert out["c4_continuation"] is None
    assert out["would_block_continuation"] is None


def test_score_core_row_missing_range_position_is_not_applicable():
    row = _core_row()
    row["conviction"]["components"]["range_position"] = None
    out = sc.score_core_row(row)
    assert out["not_applicable"] is True


# ---------------------------------------------------------------------------------
# 3. equivalence proof: re-deriving `total` from STORED components must byte-match the
# row's own stored `total`, on >=20 REAL post-fix core-decisions.jsonl rows -- this licenses
# score_core_row's "re-derive, don't re-invoke score_conviction()" design.
# ---------------------------------------------------------------------------------
def test_stored_components_sum_matches_stored_total_on_20_real_rows():
    core_path = REPO / "automation" / "state" / "core-decisions.jsonl"
    if not core_path.exists():
        pytest.skip("core-decisions.jsonl not present in this environment")
    checked = 0
    with core_path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if checked >= 20:
                break
            if "conviction" not in line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            c = row.get("conviction")
            if not isinstance(c, dict) or c.get("total") is None:
                continue
            comp = c.get("components") or {}
            resummed = sum(int(comp.get(k) or 0) for k in cv._SCORING_KEYS)
            assert resummed == c["total"], (row.get("ts_et"), comp, c["total"])
            checked += 1
    assert checked >= 20, f"only found {checked} real conviction rows to check -- need >=20"


# ---------------------------------------------------------------------------------
# 4. fleet SPY-tape scoring -- no look-ahead, coverage=c4_component_only
# ---------------------------------------------------------------------------------
@pytest.fixture
def _fake_tape(tmp_path, monkeypatch):
    sip_dir = tmp_path / "spy_sip_cache"
    sip_dir.mkdir()
    bars = []
    # 09:30 -> 09:34, a clean up-move: low never below 700, high climbs to 710 by 09:34
    prices = [(700.0, 701.0), (701.0, 704.0), (704.0, 707.0), (707.0, 710.0), (709.5, 709.8)]
    for i, (lo, hi) in enumerate(prices):
        bars.append({"t": f"2026-09-03T09:3{i}:00", "o": lo, "h": hi, "l": lo, "c": hi})
    (sip_dir / "spy_1m_2026-09-03.json").write_text(json.dumps({"bars": bars}), encoding="utf-8")
    monkeypatch.setattr(sc, "SIP_1M_DIR", sip_dir)
    sc._SPY_1M_CACHE.clear()
    yield sip_dir
    sc._SPY_1M_CACHE.clear()


def test_range_position_from_tape_excludes_forming_bar_no_lookahead(_fake_tape):
    # bars: 09:30(lo700,hi701,c701) 09:31(lo701,hi704,c704) 09:32(lo704,hi707,c707)
    #       09:33(lo707,hi710,c710) 09:34(lo709.5,hi709.8,c709.8) -- START-OF-BAR timestamps.
    #
    # A trigger at 09:32:30 fires 30s INTO the 09:32:00-09:33:00 bar -- that bar is still
    # forming and must NOT be visible. Only bars whose start is strictly before the tick's
    # OWN minute floor (09:32:00) may be used: 09:30 and 09:31 only. hi=704 (09:31), lo=700
    # (09:30), close=704 (09:31's own close) -- the forming 09:32 bar's close (707) must
    # never leak in as `close`, and its high (707) must never leak in as `hi`.
    pos, close, reason = sc.range_position_from_tape("2026-09-03", "09:32:30")
    assert reason is None
    assert close == 704.0
    assert pos == pytest.approx(1.0)  # (704-700)/(704-700)

    # once the clock actually reaches 09:33:00, the 09:32 bar HAS closed (t=09:32:00 < floor
    # 09:33:00) and becomes visible -- proves the window grows with the tick's minute floor
    # rather than being a fixed lookback, while still excluding the NOW-forming 09:33 bar.
    pos2, close2, reason2 = sc.range_position_from_tape("2026-09-03", "09:33:00")
    assert reason2 is None
    assert close2 == 707.0  # 09:32 bar's close, now fully closed
    assert pos2 == pytest.approx(1.0)  # (707-700)/(707-700)


def test_range_position_from_tape_mutating_forming_or_future_bar_is_inert(_fake_tape):
    """A bar dated AT OR AFTER the tick's own minute floor must be structurally unreachable --
    not just absent from this fixture's particular values. Mutate the 09:32 (forming-at-tick)
    and 09:33/09:34 (future) bars to extreme values that WOULD blow up hi/lo/close if they
    leaked in, and prove the result is byte-identical to the unmutated read."""
    pos1, close1, reason1 = sc.range_position_from_tape("2026-09-03", "09:32:30")
    assert reason1 is None

    tape_path = _fake_tape / "spy_1m_2026-09-03.json"
    payload = json.loads(tape_path.read_text(encoding="utf-8"))
    for b in payload["bars"]:
        if b["t"][11:16] >= "09:32":  # the forming bar (09:32) and every bar after it
            b["h"] = 99999.0
            b["l"] = -99999.0
            b["c"] = 99999.0
    tape_path.write_text(json.dumps(payload), encoding="utf-8")
    sc._SPY_1M_CACHE.clear()  # force a fresh read of the mutated file

    pos2, close2, reason2 = sc.range_position_from_tape("2026-09-03", "09:32:30")
    assert reason2 is None
    assert close2 == close1
    assert pos2 == pytest.approx(pos1)


def test_range_position_from_tape_missing_date_is_labeled_not_fabricated(_fake_tape):
    pos, close, reason = sc.range_position_from_tape("2026-09-04", "10:00:00")
    assert pos is None and close is None
    assert reason == "no_cached_spy_tape_for_date"


def test_score_fleet_row_end_to_end(_fake_tape):
    row = {"ts_et": "2026-09-03T09:32:30.123456-04:00", "side": "C",
           "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON"}
    out = sc.score_fleet_row(row, "risky-1")
    assert out["coverage"] == "c4_component_only"
    assert out["not_applicable"] is False
    assert out["range_position"] == pytest.approx(1.0)
    # pos=1.0: live (call wants <=0.30) MISSES -> c4proxy blocked; continuation (call wants
    # >=0.70) HITS -> c4proxy allowed
    assert out["c4_live"] == 0
    assert out["c4_continuation"] == 1
    assert out["would_block_live_c4proxy"] is True
    assert out["would_block_continuation_c4proxy"] is False
    assert "would_block_live" not in out  # coverage labels never blur (see docstring #3)


def test_hhmmss_handles_naive_and_offset_aware():
    assert sc._hhmmss("2026-09-03T11:09:04") == "11:09:04"
    assert sc._hhmmss("2026-06-29T14:49:03.456152-04:00") == "14:49:03"
    assert sc._hhmmss(None) is None
    assert sc._hhmmss("not-a-timestamp") is None


# ---------------------------------------------------------------------------------
# 5. bootstrap CI shape + top-3 concentration
# ---------------------------------------------------------------------------------
def test_bootstrap_ci_none_below_two_days():
    rows = [{"date": "2026-09-03", "real_pnl": 10.0}]
    assert sc._bootstrap_day_clustered_mean(rows) is None


def test_bootstrap_ci_shape_with_two_or_more_days():
    rows = ([{"date": "2026-09-03", "real_pnl": 50.0} for _ in range(4)]
            + [{"date": "2026-09-04", "real_pnl": -40.0} for _ in range(4)])
    ci = sc._bootstrap_day_clustered_mean(rows, n_boot=200)
    assert ci is not None
    assert ci["n_days_clustered"] == 2
    assert ci["ci_lower_2.5"] <= ci["ci_upper_97.5"]


def test_top3_concentration_share_all_zero_when_no_pnl():
    assert sc._top3_concentration_share([{"real_pnl": 0.0}, {"real_pnl": 0.0}]) == 0.0


# ---------------------------------------------------------------------------------
# 6. run() end-to-end, idempotent, over tiny fixtures for BOTH populations
# ---------------------------------------------------------------------------------
@pytest.fixture
def _wired_fixtures(tmp_path, monkeypatch):
    core_path = tmp_path / "core-decisions.jsonl"
    fleet_dir = tmp_path / "fleet"
    sip_dir = tmp_path / "spy_sip_cache"
    out_dir = tmp_path / "out"
    fleet_dir.mkdir()
    sip_dir.mkdir()

    core_row = _core_row(total=4, floor=5, would_block=True, side="C", pos=0.81,
                          range_extreme=0)
    core_row["ts_et"] = "2026-08-27T09:47:05"
    core_path.write_text(json.dumps(core_row) + "\n", encoding="utf-8")

    for arm in sc.FLEET_ARMS:
        arm_dir = fleet_dir / arm
        arm_dir.mkdir()
        placed = {"ts_et": "2026-08-27T09:48:05.470782-04:00", "side": "C",
                  "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
                  "placement": {"placed": True}}
        not_placed = {"ts_et": "2026-08-27T09:49:05.000000-04:00", "side": "C",
                      "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
                      "placement": {"placed": False}}
        (arm_dir / "decisions.jsonl").write_text(
            json.dumps(not_placed) + "\n" + json.dumps(placed) + "\n", encoding="utf-8")

    bars = [{"t": "2026-08-27T09:30:00", "o": 700, "h": 701, "l": 699, "c": 700.5},
            {"t": "2026-08-27T09:47:00", "o": 700, "h": 712, "l": 699, "c": 711.0},
            {"t": "2026-08-27T09:48:00", "o": 711, "h": 715, "l": 710, "c": 714.0}]
    (sip_dir / "spy_1m_2026-08-27.json").write_text(json.dumps({"bars": bars}), encoding="utf-8")

    monkeypatch.setattr(sc, "CORE_DECISIONS", core_path)
    monkeypatch.setattr(sc, "FLEET_DIR", fleet_dir)
    monkeypatch.setattr(sc, "SIP_1M_DIR", sip_dir)
    monkeypatch.setattr(sc, "OUT_DIR", out_dir)
    monkeypatch.setattr(sc, "LEDGER", out_dir / "ledger.jsonl")
    monkeypatch.setattr(sc, "SUMMARY", out_dir / "summary.json")
    # attach_outcomes imports fills_fifo lazily inside the function -- no real fills ledger
    # in this fixture, so patch it to a no-op join (0 joined, additive-safe per its own
    # contract) rather than letting it silently hit the REAL fills-ledger.jsonl on disk.
    monkeypatch.setattr(sc, "attach_outcomes", lambda rows: 0)
    sc._SPY_1M_CACHE.clear()
    yield out_dir
    sc._SPY_1M_CACHE.clear()


def test_run_writes_one_core_row_and_four_fleet_rows(_wired_fixtures):
    out = sc.run()
    assert "error" not in out, out
    assert out["_meta"]["new_rows_this_run"] == 5   # 1 core + 4 fleet (1 PLACED each)
    rows = sc._read_ledger()
    assert len(rows) == 5
    arms = sorted(r["arm"] for r in rows)
    assert arms == sorted(["core"] + list(sc.FLEET_ARMS))


def test_run_skips_unplaced_fleet_rows(_wired_fixtures):
    sc.run()
    rows = sc._read_ledger()
    fleet_rows = [r for r in rows if r["arm"] != "core"]
    assert all(r["ts_et"].startswith("2026-08-27T09:48:05") for r in fleet_rows), (
        "the placement.placed=False row must never be scored")


def test_run_is_idempotent_on_a_second_fire(_wired_fixtures):
    sc.run()
    out2 = sc.run()
    assert out2["_meta"]["new_rows_this_run"] == 0
    rows = sc._read_ledger()
    assert len(rows) == 5, "re-running must never duplicate a ledger row"


def test_run_summary_has_expected_top_level_shape(_wired_fixtures):
    out = sc.run()
    for key in ("by_arm", "core_outcome_join", "fleet_c4proxy_outcome_join", "big_winner_days",
                "big_days_check", "bar", "decision_rule", "status"):
        assert key in out, key
    assert "core" in out["by_arm"]
    for arm in sc.FLEET_ARMS:
        assert arm in out["by_arm"]
        assert out["by_arm"][arm]["coverage"] == "c4_component_only"
    assert out["by_arm"]["core"]["coverage"] == "full_conviction"


# ---------------------------------------------------------------------------------
# 7. decision-rule contradiction fix: PRIMARY statistic is core-only, no pooled cell exists,
# fleet stays disclosure-only and never gates bar_met (prereg section 9, 2026-09-03 fix)
# ---------------------------------------------------------------------------------
def test_summary_has_no_pooled_outcome_cell(_wired_fixtures):
    out = sc.run()
    assert "book_outcome_join" not in out, (
        "a pooled core+fleet outcome-join cell must never exist -- it would let fleet "
        "C4-proxy rows (no real floor/would_block) move the core-only decision statistic "
        "(prereg section 5/7 contradiction, fixed 2026-09-03)")
    assert "core_outcome_join" in out
    assert "fleet_c4proxy_outcome_join" in out


def test_bar_met_never_gated_by_fleet_coverage(_wired_fixtures):
    # the fixture provides only 1 core row and 1 placed row per fleet arm (4 total) -- far
    # below either the 60-row core bar or the (now non-gating) 60-row fleet disclosure
    # threshold. bar_met must be False here (core rows too few), and the reason must be
    # core-only: "min_fleet_rows_scored" no longer appears in the decision-gating `bar` block
    # as a key that could make bar_met True or False -- it is disclosure-only.
    out = sc.run()
    assert out["bar"]["bar_met"] is False
    assert out["bar"]["core_rows_scored"] == 1
    assert "min_fleet_rows" not in out["bar"]  # only the _disclosure_only variant may appear
    assert out["bar"]["min_fleet_rows_disclosure_only"] == sc.BAR_MIN_FLEET_ROWS
    assert out["bar"]["fleet_rows_scored_disclosure_only"] == 4
