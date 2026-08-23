"""test_gate_expiry_naive_red_guard_2026_08_23.py -- OP-25 guard for the naive-mean-only
costing_verdict defect that produced TWO false alarms in one weekend (structure_veto_enabled,
require_bearish_fill_bar -- both cleared gate_expiry_check.py's old n>=floor+mean>0 bar but
FAILED a full G-battery's drop-top3 + BH-FDR + bootstrap-null checks: see
analysis/recommendations/gate-revalidation-structure_veto-2026-08-23-extended.json and
gate-revalidation-bearish_fill_bar-2026-08-23-extended.json). Per OP-25 (same mistake twice =
system failure, encode the correction as a guard, not a memory), this file pins the fix.

Pins three things, through the REAL production call path where practical (evaluate_gate_pnl ->
costing_verdict -> check_gate), no real OPRA data required:
  (a) a synthetic refused cohort whose positive mean is carried ONLY by 3 outlier winners must
      NOT produce an actionable overall=="RED" (must downgrade to NAIVE_RED_CONCENTRATED,
      labeled "battery required" -- not actionable), and that verdict must never trip
      compute_newly_red/flag_status_md's STATUS.md "## Known broken" alarm;
  (b) a genuinely broad positive cohort (edge survives dropping its top 3 winners) still
      produces an actionable RED -- proves the concentration term doesn't neuter every RED;
  (c) a --gate <id> single-gate run's write path (main()'s merge_gate_results) MERGES into the
      existing gate-registry-status.json, preserving every OTHER gate's row -- the second bug
      this same weekend's battery run disclosed: a filtered run used to truncate the status
      file down to just the one gate checked, destroying the other ~22 gates' history.

HOW THESE WERE PROVEN TO RED PRE-FIX (actually run this session, not asserted from memory):
  `git stash push -- backtest/autoresearch/gate_expiry_check.py` (reverting ONLY the source fix
  to its last-committed, pre-fix state -- this test file stayed in place, untracked), then
  `pytest backtest/tests/test_gate_expiry_naive_red_guard_2026_08_23.py -v` produced
  "5 failed in 1.22s", every one for a different, correct reason:
    - test_concentration_carried_cohort_is_not_actionable_red: KeyError: 'drop_top3' --
      pre-fix evaluate_gate_pnl never computed a drop_top3 field at all, so this test's own
      assertion on it (let alone the verdict check) can't even be reached.
    - test_naive_red_concentrated_never_maps_to_overall_red: check_gate's pre-fix overall-
      mapping has no NAIVE_RED_CONCENTRATED branch, so result["overall"] came back "GREEN"
      (fell through to the final `else` branch) instead of "NAIVE_RED_CONCENTRATED" --
      assertion failure, not a crash.
    - test_broad_positive_cohort_still_red: KeyError: 'drop_top3' -- same root cause as the
      first test; a broad cohort was already correctly RED under the pure naive mean check, but
      this test also pins that drop_top3 gets computed and reported, which pre-fix code never
      did.
    - test_gate_filtered_run_merges_preserves_other_gates_status_rows /
      test_gate_filtered_run_writes_merged_status_to_disk: AttributeError: module
      'autoresearch.gate_expiry_check' has no attribute 'merge_gate_results' -- the function
      did not exist pre-fix; the truncation bug had no merge step to test against.
  `git stash pop` restored the fix immediately afterward (confirmed via `git status` / `git
  stash list` showing the stash consumed and gate_expiry_check.py modified again). See the
  session report for the exact commands run.
"""
from __future__ import annotations

import datetime as dt
import json

import pandas as pd

from autoresearch import gate_expiry_check as gec


class _FakeSoundReplayModule:
    """Minimal stand-in for the lazily-imported backtest/tools/gate_revalidation_ab.py.
    Deliberately self-contained (not imported from test_gate_expiry_check.py) so this guard
    file has no cross-test-file coupling. `drop_top_n` mirrors the real module's semantics
    EXACTLY (only drops actual winners, pnl > 0) -- if this fake drifted from the real
    behavior, these tests would pass for the wrong reason."""

    def __init__(self, pnl_by_ts: dict[str, float]):
        self._pnl_by_ts = pnl_by_ts
        self.replay_calls: list[dict] = []

    def account_config(self):
        return {
            "safe": {"qty": 3, "structure_stop_enabled": True, "time_stop_et": dt.time(15, 40)},
            "bold": {"qty": 5, "structure_stop_enabled": True, "time_stop_et": dt.time(15, 40)},
        }

    def build_ribbon_lookup(self, spy):
        return "FAKE_RIBBON_LOOKUP"

    def drop_top_n(self, pnls: list[float], n_drop: int = 3) -> tuple[float, int]:
        if not pnls:
            return 0.0, 0
        winners = sorted([p for p in pnls if p > 0], reverse=True)
        k = min(n_drop, len(winners))
        dropped_sum = sum(winners[:k])
        return round(sum(pnls) - dropped_sum, 2), k

    def replay_row(self, row, *, spy, spy_ts, spy_by_date, ribbon_lookup, cfg):
        self.replay_calls.append({"row": row})
        ts = row["ts_et"]
        return {"status": "ok", "date": ts[:10], "pnl": self._pnl_by_ts[ts], "ts_et": ts}


def _tiny_spy_df():
    return pd.DataFrame({
        "date": [dt.date(2026, 7, 31)],
        "close": [450.0],
        "timestamp_et": pd.to_datetime(["2026-07-31 09:30:00"]),
    })


def _write_core_decisions(path, ts_list: list[str], skip_action: str) -> None:
    with path.open("w", encoding="utf-8") as f:
        for i, ts in enumerate(ts_list):
            row = {
                "ts_et": ts, "account": "safe", "verdict": skip_action, "armed": True,
                "side": "C" if i % 2 == 0 else "P",
            }
            f.write(json.dumps(row) + "\n")


def _spaced_timestamps(n: int, day: str = "2026-07-31", start_hour: int = 9,
                        start_minute: int = 35, gap_minutes: int = 20) -> list[str]:
    """n timestamps on the same trading day, gap_minutes apart -- wider than
    EVENT_CLUSTER_GAP_MINUTES (15) so cluster_events treats each as its own tradeable event
    (one row per event, matching the pnl_by_ts mapping 1:1)."""
    base = dt.datetime.fromisoformat(f"{day}T{start_hour:02d}:{start_minute:02d}:00")
    return [(base + dt.timedelta(minutes=gap_minutes * i)).isoformat() for i in range(n)]


_GATE = {
    "id": "_test_naive_red_guard_gate",
    "category": "core_gate_order",
    "skip_action": "SKIP_NAIVE_RED_GUARD_TEST",
    "accounts_armed": {"safe": True, "bold": False},
    "last_revalidated": "2026-01-01",
    "revalidation_interval_days": 21,
}


def _run_evaluate_gate_pnl(tmp_path, monkeypatch, pnls: list[float], floor: int = 10):
    gec._REPLAY_CTX_CACHE.clear()
    ts_list = _spaced_timestamps(len(pnls))
    pnl_by_ts = dict(zip(ts_list, pnls))
    fake_grab = _FakeSoundReplayModule(pnl_by_ts)
    monkeypatch.setattr(gec, "_sound_replay_module", lambda: fake_grab)

    core_decisions = tmp_path / "core-decisions.jsonl"
    _write_core_decisions(core_decisions, ts_list, _GATE["skip_action"])
    monkeypatch.setattr(gec, "CORE_DECISIONS", core_decisions)

    spy = _tiny_spy_df()
    result = gec.evaluate_gate_pnl(
        _GATE, spy, None, pd.Series(dtype="datetime64[ns]"),
        dt.date(2026, 7, 1), dt.date(2026, 7, 31), floor=floor,
    )
    return result, fake_grab


# ─────────────────────────────────────────────────────────────────────────────
# (a) concentration-carried cohort must NOT emit an actionable RED
# ─────────────────────────────────────────────────────────────────────────────

def test_concentration_carried_cohort_is_not_actionable_red(tmp_path, monkeypatch):
    """10 trades: 7 losers @ -$50 (-$350) + 3 winners @ +$150 (+$450) = net +$100 total, mean
    +$10/tr -- positive, n=10 >= floor=10. The OLD naive check (n>=floor AND mean>0) called
    this a bare actionable RED. drop_top_n only drops winners: removing the 3 winners leaves
    the 7 losers, -$350 -- NEGATIVE, fails drop-top3. Must downgrade to
    NAIVE_RED_CONCENTRATED."""
    pnls = [-50.0] * 7 + [150.0] * 3
    result, fake_grab = _run_evaluate_gate_pnl(tmp_path, monkeypatch, pnls, floor=10)

    assert len(fake_grab.replay_calls) == 10, "all 10 synthetic events must have been replayed"
    assert result["combined"]["n"] == 10
    assert result["combined"]["exp_per_trade"] == 10.0
    assert result["combined"]["drop_top3"] == -350.0
    assert result["combined"]["n_dropped_for_drop_top3"] == 3
    assert result["verdict"] == "NAIVE_RED_CONCENTRATED"
    assert result["verdict"] != "RED"
    assert "battery" in result["reason"].lower()
    assert "NAIVE-RED" in result["reason"]


def test_naive_red_concentrated_never_maps_to_overall_red(monkeypatch):
    """Direct pin on check_gate's overall-mapping branch: a NAIVE_RED_CONCENTRATED pnl_check
    verdict must map to overall == "NAIVE_RED_CONCENTRATED", NEVER "RED" -- this is the exact
    field compute_newly_red/flag_status_md key off (r["overall"] == "RED") to decide whether to
    write a fresh line under STATUS.md's "## Known broken" -- the actual surface that produced
    this weekend's two false alarms ("STATUS.md GATE-EXPIRY RED 2026-08-22T23:01:45")."""
    def _fake_naive_red(gate, spy, ribbon, spy_ts, recent_start, recent_end, floor):
        return {
            "combined": {"n": 15, "exp_per_trade": 7.43, "drop_top3": -588.0,
                         "n_dropped_for_drop_top3": 3},
            "verdict": "NAIVE_RED_CONCENTRATED",
            "reason": "NAIVE-RED (battery required): ...",
        }
    monkeypatch.setattr(gec, "evaluate_gate_pnl", _fake_naive_red)

    result = gec.check_gate(
        _GATE, spy=None, ribbon=None, spy_ts=None,
        recent_start=dt.date(2026, 7, 1), recent_end=dt.date(2026, 7, 31),
        floor=10, today=dt.date(2026, 7, 31),
    )
    assert result["overall"] == "NAIVE_RED_CONCENTRATED"
    assert result["overall"] != "RED"

    # ... and it must never trip the STATUS.md alarm:
    new_red = gec.compute_newly_red({_GATE["id"]: result}, prior_gates={})
    assert new_red == [], "a NAIVE_RED_CONCENTRATED gate must never be treated as newly-RED"


# ─────────────────────────────────────────────────────────────────────────────
# (b) a genuinely broad positive cohort still produces an actionable RED
# ─────────────────────────────────────────────────────────────────────────────

def test_broad_positive_cohort_still_red(tmp_path, monkeypatch):
    """10 trades: 6 winners @ +$80 (+$480) + 4 losers @ -$40 (-$160) = net +$320, mean
    +$32/tr, n=10 >= floor=10. Dropping the top 3 winners removes 3x$80=$240, leaving
    $320-$240=$80 -- still POSITIVE, survives drop-top3 (the remaining winner(s) + losers still
    net positive). This is a genuinely broad edge, not 3-trade-carried, and must still read
    RED -- proves the concentration term doesn't neuter every RED, only concentration-carried
    ones."""
    pnls = [80.0] * 6 + [-40.0] * 4
    result, fake_grab = _run_evaluate_gate_pnl(tmp_path, monkeypatch, pnls, floor=10)

    assert len(fake_grab.replay_calls) == 10
    assert result["combined"]["n"] == 10
    assert result["combined"]["exp_per_trade"] == 32.0
    assert result["combined"]["drop_top3"] == 80.0
    assert result["combined"]["n_dropped_for_drop_top3"] == 3
    assert result["verdict"] == "RED"
    assert "COSTING" in result["reason"]
    assert "G-battery" in result["reason"], "a survives-drop-top3 RED must still note the battery is the ratifying instrument"


# ─────────────────────────────────────────────────────────────────────────────
# (c) --gate filtered run must MERGE into gate-registry-status.json, never truncate it
# ─────────────────────────────────────────────────────────────────────────────

def test_gate_filtered_run_merges_preserves_other_gates_status_rows():
    """THE TRUNCATION BUG (disclosed by this weekend's G-battery run): a `--gate <id>` debug
    run only recomputes ONE gate, but pre-fix main() wrote that single-gate `results` dict as
    the ENTIRE "gates" object in gate-registry-status.json, wiping the other ~22 gates' rows.
    Pins merge_gate_results (main()'s own merge step) directly."""
    prior_gates = {
        "gate_a": {"id": "gate_a", "overall": "GREEN", "pnl_check": {"verdict": "GREEN"}},
        "gate_b": {"id": "gate_b", "overall": "RED", "pnl_check": {"verdict": "RED"}},
        "gate_c": {"id": "gate_c", "overall": "STALE_UNVERIFIED"},
        "_test_naive_red_guard_gate": {"id": "_test_naive_red_guard_gate", "overall": "RED"},
    }
    # simulate `--gate _test_naive_red_guard_gate`: only ONE gate recomputed this pass, and its
    # verdict changed (RED -> NAIVE_RED_CONCENTRATED, e.g. after this fix landed).
    results = {
        "_test_naive_red_guard_gate": {
            "id": "_test_naive_red_guard_gate", "overall": "NAIVE_RED_CONCENTRATED",
        },
    }

    merged = gec.merge_gate_results(results, prior_gates)

    assert set(merged.keys()) == {"gate_a", "gate_b", "gate_c", "_test_naive_red_guard_gate"}, (
        "the other 3 gates' rows must survive a single-gate run untouched"
    )
    assert merged["gate_a"] == prior_gates["gate_a"]
    assert merged["gate_b"] == prior_gates["gate_b"]
    assert merged["gate_c"] == prior_gates["gate_c"]
    assert merged["_test_naive_red_guard_gate"]["overall"] == "NAIVE_RED_CONCENTRATED", (
        "the filtered gate's own row must reflect THIS run's fresh result, not the stale prior one"
    )


def test_gate_filtered_run_writes_merged_status_to_disk(tmp_path, monkeypatch):
    """End-to-end through the actual gate-registry-status.json write path a --gate run uses:
    a pre-existing status file with 3 gates on disk, a single-gate `results`, confirm the file
    written back to disk still contains every gate -- not just the one this run touched. This
    is the literal on-disk reproduction of the bug (as opposed to the in-memory dict proof
    above)."""
    status_path = tmp_path / "gate-registry-status.json"
    prior = {
        "checker": "gate-expiry instrument (J directive 2026-07-31)",
        "gates": {
            "gate_a": {"id": "gate_a", "overall": "GREEN"},
            "gate_b": {"id": "gate_b", "overall": "RED"},
            "gate_c": {"id": "gate_c", "overall": "YELLOW"},
        },
    }
    status_path.write_text(json.dumps(prior), encoding="utf-8")
    monkeypatch.setattr(gec, "OUT_JSON", status_path)

    prior_gates = json.loads(status_path.read_text(encoding="utf-8"))["gates"]
    results = {"gate_b": {"id": "gate_b", "overall": "GREEN"}}  # simulates `--gate gate_b`
    merged = gec.merge_gate_results(results, prior_gates)
    summary = {"checker": prior["checker"], "gates": merged}
    gec.OUT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    written = json.loads(status_path.read_text(encoding="utf-8"))
    assert set(written["gates"].keys()) == {"gate_a", "gate_b", "gate_c"}, (
        "gate_a and gate_c must NOT be wiped by a gate_b-only run"
    )
    assert written["gates"]["gate_a"]["overall"] == "GREEN"   # untouched
    assert written["gates"]["gate_c"]["overall"] == "YELLOW"  # untouched
    assert written["gates"]["gate_b"]["overall"] == "GREEN"   # updated by this filtered run
