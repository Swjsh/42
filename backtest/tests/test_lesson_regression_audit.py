"""Tests for the lesson-regression audit -- the parser + idempotent recording. The slow
guard run itself is stubbed (run_guards seam), so these are fast and deterministic."""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "setup" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import lesson_regression_audit as L  # noqa: E402


def test_parse_failures_extracts_lesson_ids():
    out = (
        "....F..\n"
        "FAILED backtest/tests/test_l173_supersede.py::test_direction\n"
        "FAILED backtest/tests/test_graduated_guards.py::test_l99_realfills\n"
        "FAILED backtest/tests/test_graduated_guards.py::test_no_lesson_token\n"
        "2 failed, 5 passed\n"
    )
    fails = L.parse_failures(out)
    lessons = [f["lesson"] for f in fails]
    assert lessons == ["L173", "L99", "test_no_lesson_token"]


def test_parse_failures_empty_when_green():
    assert L.parse_failures("5 passed in 1s\n") == []


def test_record_is_idempotent_per_day(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "STATE", tmp_path)
    monkeypatch.setattr(L, "REG_LOG", tmp_path / "lesson-regressions.jsonl")
    fail = {"lesson": "L173", "test": "x::y"}
    assert L._record(fail) is True    # first time -> logged
    assert L._record(fail) is False   # same lesson+day -> not re-logged
    assert (tmp_path / "lesson-regressions.jsonl").read_text(encoding="utf-8").count("L173") == 1


def test_file_queue_item_idempotent_and_anchored(tmp_path, monkeypatch):
    q = tmp_path / "queue.md"
    q.write_text("# header\n\n## Active backlog\n\n- [ ] EXISTING (LOW) :: x :: status:pending\n", encoding="utf-8")
    monkeypatch.setattr(L, "QUEUE", q)
    fail = {"lesson": "L173", "test": "test_l173.py::test_x"}
    assert L._file_queue_item(fail) is True
    text = q.read_text(encoding="utf-8")
    assert "LESSON-REGRESSION-L173" in text
    # inserted right under the Active backlog header (seen first)
    assert text.index("LESSON-REGRESSION-L173") < text.index("EXISTING")
    assert L._file_queue_item(fail) is False  # already present -> not duplicated
    assert text.count("LESSON-REGRESSION-L173") == 1


def test_main_green_returns_zero(monkeypatch):
    monkeypatch.setattr(L, "run_guards", lambda: (0, "10 passed in 2s"))
    monkeypatch.setattr(sys, "argv", ["lesson_regression_audit.py", "--dry-run"])
    assert L.main() == 0


def test_main_regression_returns_one(monkeypatch):
    monkeypatch.setattr(L, "run_guards", lambda: (1, "FAILED t/test_l173.py::test_x\n1 failed"))
    monkeypatch.setattr(sys, "argv", ["lesson_regression_audit.py", "--dry-run"])
    assert L.main() == 1
