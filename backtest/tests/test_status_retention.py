"""Graduated guard for L181: STATUS.md retention consolidation must be correct,
verbatim, idempotent, and fail-open.

L181 (re-violated 2026-06-24): STATUS.md grew past the Read cap with no retention
mechanism, so a fire trusted a stale breadcrumb and re-did solved work. The
2026-06-22 fix was a manual one-off that regrew. This pins the reusable tool
`setup/scripts/status_retention.py` so the consolidation is a tested operation,
never another bespoke manual effort.
"""
import datetime as dt
import importlib.util
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(REPO_ROOT, "setup", "scripts", "status_retention.py")


def _load():
    spec = importlib.util.spec_from_file_location("status_retention", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sr = _load()


def _make_status(n_entries: int, body_kb: float = 1.0) -> str:
    """Newest-first STATUS.md with n entries, each ~body_kb KB of body."""
    filler = "x" * int(body_kb * 1024)
    out = []
    for i in range(n_entries):  # i=0 is newest
        out.append(f"## [2026-06-{24 - i % 20:02d} {i:02d}:00 ET] conductor: entry {i}\n")
        out.append(f"> body for entry {i} {filler}\n\n---\n\n")
    return "".join(out)


def test_split_entries_no_preamble():
    text = _make_status(3)
    preamble, entries = sr.split_entries(text)
    assert preamble == ""
    assert len(entries) == 3
    assert entries[0].startswith("## [2026-06-24 00:00 ET]")  # newest first


def test_split_entries_preserves_preamble():
    text = "# header\nsome preamble\n\n" + _make_status(2)
    preamble, entries = sr.split_entries(text)
    assert "preamble" in preamble
    assert len(entries) == 2


def test_keeps_newest_and_rolls_rest():
    text = _make_status(30, body_kb=2.0)  # ~60KB+
    plan = sr.plan_consolidation(text, max_keep_bytes=20_000, min_keep=4)
    assert plan["n_kept"] >= 4
    assert plan["n_rolled"] > 0
    assert plan["n_kept"] + plan["n_rolled"] == 30
    # newest entry retained, oldest rolled
    assert "entry 0" in plan["kept_text"]
    assert "entry 29" not in plan["kept_text"]
    assert any("entry 29" in e for e in plan["rolled_entries"])


def test_min_keep_floor_respected():
    text = _make_status(20, body_kb=5.0)  # each entry alone exceeds a tiny budget
    plan = sr.plan_consolidation(text, max_keep_bytes=1, min_keep=6)
    assert plan["n_kept"] == 6  # floor honored even though over budget


def test_idempotent_noop_when_within_budget():
    text = _make_status(5, body_kb=0.5)
    plan = sr.plan_consolidation(text, max_keep_bytes=10_000_000, min_keep=4)
    assert plan["n_rolled"] == 0
    assert plan["kept_text"] == text


def test_verbatim_nothing_lost(tmp_path):
    status = tmp_path / "STATUS.md"
    text = _make_status(25, body_kb=2.0)
    status.write_text(text, encoding="utf-8")
    res = sr.apply_consolidation(str(status), max_keep_bytes=15_000, min_keep=4,
                                 today=dt.date(2026, 6, 24))
    assert res["changed"]
    kept = status.read_text(encoding="utf-8")
    archive = (tmp_path / "STATUS-archive-2026-06.md").read_text(encoding="utf-8")
    # Every original entry survives in kept ∪ archive (verbatim, nothing deleted).
    for i in range(25):
        marker = f"conductor: entry {i}\n"
        assert (marker in kept) or (marker in archive), f"entry {i} lost"
    assert "rolled off 2026-06-24" in archive


def test_apply_is_idempotent_second_run(tmp_path):
    status = tmp_path / "STATUS.md"
    status.write_text(_make_status(25, body_kb=2.0), encoding="utf-8")
    sr.apply_consolidation(str(status), max_keep_bytes=15_000, min_keep=4,
                           today=dt.date(2026, 6, 24))
    after_first = status.read_text(encoding="utf-8")
    res2 = sr.apply_consolidation(str(status), max_keep_bytes=15_000, min_keep=4,
                                  today=dt.date(2026, 6, 24))
    assert res2["changed"] is False  # already within budget
    assert status.read_text(encoding="utf-8") == after_first


def test_new_roll_inserted_at_top_of_archive(tmp_path):
    status = tmp_path / "STATUS.md"
    archive = tmp_path / "STATUS-archive-2026-06.md"
    archive.write_text(sr._archive_header(dt.date(2026, 6, 20))
                       + "\n<!-- rolled off 2026-06-20 ... -->\n\nOLD ROLL\n", encoding="utf-8")
    status.write_text(_make_status(25, body_kb=2.0), encoding="utf-8")
    sr.apply_consolidation(str(status), max_keep_bytes=15_000, min_keep=4,
                           today=dt.date(2026, 6, 24))
    arc = archive.read_text(encoding="utf-8")
    # newest roll (06-24) must appear before the older roll (06-20)
    assert arc.index("rolled off 2026-06-24") < arc.index("rolled off 2026-06-20")
    assert "OLD ROLL" in arc  # prior archive preserved


def test_fail_open_on_missing_file():
    rc = sr.main(["--status-path", "/nonexistent/STATUS.md"])
    assert rc == 0  # noop, never raises


def test_check_mode_exit_codes(tmp_path):
    status = tmp_path / "STATUS.md"
    status.write_text(_make_status(30, body_kb=2.0), encoding="utf-8")
    over = sr.main(["--status-path", str(status), "--check", "--max-keep-bytes", "10000"])
    assert over == 2
    within = sr.main(["--status-path", str(status), "--check",
                      "--max-keep-bytes", "100000000"])
    assert within == 0


def test_retention_is_autowired_into_conductor_wrapper():
    """L181 last-mile (2026-06-24): the durable guard is useless if it requires a
    fire to NOTICE + run it -- STATUS.md regrew past budget within hours of both
    manual trims. The conductor wrapper must invoke the tool every after-hours wake
    so consolidation is self-executing. This pins the autowire so it cannot silently
    regress (a deleted call = the foot-gun returns)."""
    wrapper = os.path.join(REPO_ROOT, "setup", "scripts", "run-conductor.ps1")
    assert os.path.exists(wrapper), wrapper
    with open(wrapper, encoding="utf-8") as fh:
        src = fh.read()
    assert "status_retention.py" in src, \
        "conductor wrapper no longer invokes status_retention.py -- L181 autowire regressed"
    # Must be guarded fail-open (try/catch) so a retention hiccup never blocks the
    # fire. The actual invocation is the LAST mention (earlier ones are the comment).
    idx = src.rindex("status_retention.py")
    assert "try {" in src[:idx], "retention call must be wrapped fail-open (rail 2)"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
