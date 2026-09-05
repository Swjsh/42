"""Guard for the 2026-09-05 tickers-lane sizing review
(analysis/deep-research/2026-09-05-tickers-sizing-risk-review.md).

WHY THIS EXISTS: that review found TWO stale doc-string fields in
automation/state/tickers/params.json#risk (_cap_note said "5% of equity" / a $100K-account
example, _kill_doc said "~$1,000 on $100K paper") that survived a 2026-09-04 03:5x ET
equity correction which updated only their sibling field (_per_trade_risk_cap_doc). The
fix touched documentation ONLY -- zero numeric/behavioral keys changed. This test pins
both halves of that fact so it can't silently drift back:

1. The 4 real risk numbers (per_trade_risk_cap_pct, daily_loss_kill_switch_pct,
   min_contracts, max_contracts) stay exactly what the review verified against real
   broker fills -- a future editor touching a doc string must not accidentally also
   change a number (or vice versa) without this test making them look at it.
2. The corrected doc strings actually say the $5,000-equity numbers, not the stale
   $100K-paper numbers -- so a revert/merge that resurrects the stale text is caught
   immediately instead of waiting for the next person to notice by hand (C7: a doc bug
   that only a human proofread would catch again is not a guard).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

PARAMS_PATH = REPO / "automation" / "state" / "tickers" / "params.json"


def _load_risk_block() -> dict:
    with PARAMS_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    return data["risk"]


def test_params_json_still_parses():
    # A doc-string-only edit must never break JSON validity.
    risk = _load_risk_block()
    assert isinstance(risk, dict)


def test_risk_numbers_unchanged_by_the_doc_fix():
    risk = _load_risk_block()
    assert risk["per_trade_risk_cap_pct"] == 0.3
    assert risk["daily_loss_kill_switch_pct"] == 0.01
    assert risk["min_contracts"] == 3
    assert risk["max_contracts"] == 3


def test_cap_note_no_longer_states_the_stale_5pct_100k_figure():
    risk = _load_risk_block()
    cap_note = risk["_cap_note"]
    assert "STALE" in cap_note, "_cap_note should flag its own prior staleness for traceability"
    assert "30% of equity" in cap_note or "0.30" in cap_note
    # The stale figure must not appear as the CURRENT claim (only inside the "used to say" note).
    assert "on a $100K paper account 5% = $5,000 covers" not in cap_note


def test_kill_doc_states_the_real_5k_dollar_figure_not_the_stale_100k_one():
    risk = _load_risk_block()
    kill_doc = risk["_kill_doc"]
    assert "$50" in kill_doc, "_kill_doc must state 1% of the REAL $5,000 accounts (~$50)"
    assert "$5,000" in kill_doc
    # The stale figure may still be QUOTED for traceability (mirrors _cap_note's "STALE"
    # pattern), but only inside the "this field used to say..." clause, never as the
    # CURRENT leading claim -- the doc must open with the corrected 1%/$50/$5,000 framing.
    assert kill_doc.startswith("1% of equity (~$50")


def test_review_doc_exists_and_is_linked_from_params():
    review = REPO / "analysis" / "deep-research" / "2026-09-05-tickers-sizing-risk-review.md"
    assert review.exists(), "the sizing review this guard protects must actually exist on disk"
    risk = _load_risk_block()
    assert "2026-09-05-tickers-sizing-risk-review.md" in risk["_kill_doc"]
