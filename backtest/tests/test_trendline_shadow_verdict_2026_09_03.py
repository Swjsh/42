"""Guard: trendline_shadow_verdict.py recomputes the shadow lane's verdict correctly and
appends (never overwrites) history, and obsidian_vault_sync.py's build_preregs_board renders
the latest verdict into what becomes SHADOW.md's "Trendline shadow" row.

Filed by overnight queue item TRENDLINE-SHADOW-VERDICT-RECOMPUTE (2026-08-29 Fable full
review): the 08-20 verdict (65 sessions, n=1332, +0.041 pts/trade, CI [-0.039, +0.124]) was
never saved as a reusable script and SHADOW.md never carried a row for this lane at all.

Run: backtest/.venv/Scripts/python.exe -m pytest tests/test_trendline_shadow_verdict_2026_09_03.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "lib"))

import trendline_shadow_verdict as V  # noqa: E402
import obsidian_vault_sync as ovs  # noqa: E402


def _synthetic_ledger(tmp_path) -> Path:
    """5 sessions, deterministic theo_points, enough to exercise every stat this module
    reports without depending on the live (and constantly growing) real ledger."""
    p = tmp_path / "shadow-ledger.jsonl"
    rows = []
    # session A: one big winner (drives concentration)
    rows.append({"date": "2026-01-05", "theo_points": 5.0})
    rows.append({"date": "2026-01-05", "theo_points": 1.0})
    # sessions B-E: small mixed results
    rows.append({"date": "2026-01-06", "theo_points": -0.5})
    rows.append({"date": "2026-01-07", "theo_points": 0.2})
    rows.append({"date": "2026-01-07", "theo_points": -0.3})
    rows.append({"date": "2026-01-08", "theo_points": 0.1})
    rows.append({"date": "2026-01-09", "theo_points": -0.2})
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


class TestComputeVerdict:
    def test_matches_baseline_whole_sample_stats(self, tmp_path):
        import trendline_shadow as T
        ledger = _synthetic_ledger(tmp_path)
        v = V.compute_verdict("2026-01-09", ledger)
        bl = T.baseline("2026-01-09", sessions=5, path=ledger)
        assert v["ok"] is True
        assert v["sessions_total"] == bl["sessions_total"] == 5
        assert v["n_trades"] == bl["all_trades"] == 7
        assert v["points_per_trade"] == bl["all_points_per_trade"]
        assert v["top3_session_share_of_profit"] == bl["top3_share_of_total"]

    def test_ci_is_session_clustered_not_trade_level(self, tmp_path):
        """The whole point of session-clustered: resampling by SESSION, not by trade. A
        trade-level bootstrap on this fixture (session A supplies 2 of 7 trades but 100%+ of
        the profit) would understate variance -- assert the CI is wide enough to reflect that
        one session dominates, i.e. it does NOT tightly hug the point estimate."""
        ledger = _synthetic_ledger(tmp_path)
        v = V.compute_verdict("2026-01-09", ledger)
        lo, hi = v["session_clustered_ci_95"]
        assert lo is not None and hi is not None
        assert lo < v["points_per_trade"] < hi
        # session A alone (6.0 pts / 2 trades = 3.0/trade) dominates -- the CI upper bound
        # should be able to reach well above the whole-sample mean when session A is
        # oversampled, which a trade-level bootstrap pooling 7 iid draws would smear away.
        assert hi > 1.0

    def test_deterministic_across_runs(self, tmp_path):
        ledger = _synthetic_ledger(tmp_path)
        v1 = V.compute_verdict("2026-01-09", ledger)
        v2 = V.compute_verdict("2026-01-09", ledger)
        assert v1["session_clustered_ci_95"] == v2["session_clustered_ci_95"]

    def test_ok_false_on_empty_ledger(self, tmp_path):
        empty = tmp_path / "empty.jsonl"
        empty.write_text("", encoding="utf-8")
        v = V.compute_verdict("2026-01-09", empty)
        assert v["ok"] is False


class TestHistoryIsAppendOnly:
    def test_main_appends_never_overwrites(self, tmp_path, monkeypatch):
        ledger = _synthetic_ledger(tmp_path)
        out = tmp_path / "shadow-verdict.json"
        rc = V.main(["--date", "2026-01-09", "--out", str(out)])
        assert rc == 0
        doc = json.loads(out.read_text(encoding="utf-8"))
        assert doc["history"][0]["date"] == "2026-08-20"  # original verdict always preserved
        assert doc["history"][-1]["date"] == "2026-01-09"
        assert doc["latest"]["date"] == "2026-01-09"
        n_before = len(doc["history"])

        # A second run for a LATER date appends a THIRD entry, not a replacement.
        rows = ledger.read_text(encoding="utf-8") + json.dumps(
            {"date": "2026-01-12", "theo_points": 0.4}) + "\n"
        ledger.write_text(rows, encoding="utf-8")
        rc2 = V.main(["--date", "2026-01-12", "--out", str(out)])
        assert rc2 == 0
        doc2 = json.loads(out.read_text(encoding="utf-8"))
        assert len(doc2["history"]) == n_before + 1
        assert doc2["history"][0]["date"] == "2026-08-20"  # still preserved

    def test_rerunning_the_same_date_replaces_that_entry_not_duplicates(self, tmp_path):
        ledger = _synthetic_ledger(tmp_path)
        out = tmp_path / "shadow-verdict.json"
        V.main(["--date", "2026-01-09", "--out", str(out)])
        V.main(["--date", "2026-01-09", "--out", str(out)])
        doc = json.loads(out.read_text(encoding="utf-8"))
        dates = [h["date"] for h in doc["history"]]
        assert dates.count("2026-01-09") == 1


class TestPromotionBarIsFrozen:
    def test_bar_has_all_four_criteria(self):
        bar = V.PROMOTION_BAR
        for key in ("ci_clears_zero", "concentration_resolved", "n_sessions_min", "no_new_knobs"):
            assert key in bar, f"promotion bar missing {key!r}"
        assert bar["n_sessions_min"] == 60


class TestVaultSyncRendersTheVerdict:
    def test_build_preregs_board_reads_the_verdict_file(self, tmp_path, monkeypatch):
        ledger = _synthetic_ledger(tmp_path)
        out = tmp_path / "shadow-verdict.json"
        V.main(["--date", "2026-01-09", "--out", str(out)])
        monkeypatch.setattr(ovs, "REPO", tmp_path)
        (tmp_path / "analysis" / "trendlines").mkdir(parents=True, exist_ok=True)
        (tmp_path / "analysis" / "trendlines" / "shadow-verdict.json").write_text(
            out.read_text(encoding="utf-8"), encoding="utf-8")
        text = ovs.build_preregs_board("TEST")
        assert "Trendline shadow" in text
        assert "2026-01-09" in text
        assert "NOT a green light" in text

    def test_missing_verdict_file_is_reported_not_silent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ovs, "REPO", tmp_path)
        text = ovs.build_preregs_board("TEST")
        assert "Trendline shadow" in text
        assert "no verdict recomputed yet" in text
