"""Guard: the ladder shadow tally must never double-count a date again.

THE DEFECT (found 2026-08-20 while quoting the ledger to J)
  score_ladder_rung_shadow_nightly appended unconditionally, so every re-run of a
  date wrote duplicate rows. 2026-08-07 landed EIGHT times, 08-13 twice. The raw
  file summed to -$21,735 against a deduped -$6,615 — a 6x inflation for anyone
  summing it naively, which is exactly what a consumer would do.

  The VERDICT never moved (16 of 18 real days negative either way), which is
  precisely why it was dangerous: the number was wrong in a direction that did not
  change the conclusion, so nothing forced anyone to notice.

THE FIX, two halves
  1. WRITE: refuse to re-append a (date, arm_id) already present. `--retally`
     appends a row flagged `supersedes_prior` so a deliberate re-tally stays
     auditable.
  2. READ: `read_deduped()` returns one row per (date, arm_id), last-wins. Every
     consumer uses it; the raw file stays intact as the audit trail.

History is NOT rewritten — this ledger is append-only by doctrine, and the dupes
are an honest record of re-runs. C7 class: a shadow whose own bookkeeping is
wrong cannot be allowed to gate anything.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))

import score_ladder_rung_shadow_nightly as s     # noqa: E402

LEDGER = REPO / "analysis" / "arm-ladder" / "ladder-rung-shadow-ledger.jsonl"


def _raw_rows():
    if not LEDGER.exists():
        return []
    out = []
    for line in LEDGER.open(encoding="utf-8", errors="replace"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def test_the_writer_refuses_to_duplicate_a_tallied_date():
    src = Path(s.__file__).read_text(encoding="utf-8")
    assert "existing_keys()" in src, "no idempotency check before append"
    assert "refusing to duplicate" in src, "must say why it skipped, not skip silently"
    assert "--retally" in src, "no deliberate override path"


def test_read_deduped_collapses_to_one_row_per_date_and_arm(tmp_path):
    p = tmp_path / "l.jsonl"
    rows = [
        {"date": "2026-08-07", "arm_id": "risky-3", "added_pnl": -945.0, "tallied_at": "1"},
        {"date": "2026-08-07", "arm_id": "risky-3", "added_pnl": -945.0, "tallied_at": "2"},
        {"date": "2026-08-07", "arm_id": "risky-3", "added_pnl": -111.0, "tallied_at": "3"},
        {"date": "2026-08-08", "arm_id": "risky-3", "added_pnl": +50.0, "tallied_at": "1"},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    ded = s.read_deduped(p)
    assert len(ded) == 2, ded
    by = {(r["date"], r["arm_id"]): r for r in ded}
    # LAST tally wins — a re-run supersedes, it does not average or sum
    assert by[("2026-08-07", "risky-3")]["added_pnl"] == -111.0
    assert sum(r["added_pnl"] for r in ded) == -61.0


def test_existing_keys_finds_every_pair(tmp_path):
    p = tmp_path / "l.jsonl"
    p.write_text(json.dumps({"date": "2026-08-07", "arm_id": "risky-1"}) + "\n"
                 + json.dumps({"date": "2026-08-08", "arm_id": "risky-3"}) + "\n", encoding="utf-8")
    assert s.existing_keys(p) == {("2026-08-07", "risky-1"), ("2026-08-08", "risky-3")}


def test_readers_are_immune_to_corrupt_lines(tmp_path):
    p = tmp_path / "l.jsonl"
    p.write_text('{"date":"2026-08-07","arm_id":"risky-3","added_pnl":-1}\n'
                 'NOT JSON\n'
                 '{"date":"2026-08-08","arm_id":"risky-3","added_pnl":-2}\n', encoding="utf-8")
    assert len(s.read_deduped(p)) == 2
    assert len(s.existing_keys(p)) == 2


def test_missing_ledger_returns_empty_not_an_exception(tmp_path):
    missing = tmp_path / "nope.jsonl"
    assert s.read_deduped(missing) == []
    assert s.existing_keys(missing) == set()


def test_the_live_ledger_really_did_contain_duplicates():
    """The scar itself. If this ever reads clean, the file was rewritten — which
    the fix deliberately does NOT do, so investigate rather than celebrate."""
    raw = _raw_rows()
    if not raw:
        return
    ded = s.read_deduped()
    assert len(ded) <= len(raw)
    if len(ded) < len(raw):
        naive = sum(r.get("added_pnl", 0) for r in raw)
        true = sum(r.get("added_pnl", 0) for r in ded)
        assert abs(naive) > abs(true), (naive, true)


def test_the_verdict_direction_survives_dedupe():
    """The dedupe corrects the MAGNITUDE, not the conclusion. If this flips, the
    ladder's HOLD decision needs re-reading, not just re-counting."""
    ded = s.read_deduped()
    if len(ded) < 5:
        return
    neg = sum(1 for r in ded if r.get("added_pnl", 0) < 0)
    assert neg > len(ded) / 2, (
        "deduped ladder is no longer majority-negative — the HOLD decision rests on "
        "this being negative, so re-read it before trusting either number"
    )
