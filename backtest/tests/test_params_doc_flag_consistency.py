"""Guard: params doc/flag consistency (G15, 2026-07-07 Fable gap-audit).

A `_*_doc` field claiming DORMANT / enabled=false while its actual flag is True is the C7
doc-drift foot-gun -- the engine trades the setup LIVE while its own doc says it is inert
(exactly what was found tonight: vwap_continuation was enabled=true + exec-armed, yet both its
docs said 'DORMANT: enabled=false'). This pins the vwap_continuation doc set so a future revert
that re-staleifies a doc re-REDs. Extend _CHECKS as new flags gain docs.

Run: cd backtest && python -m pytest tests/test_params_doc_flag_consistency.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PARAMS = REPO / "automation" / "state" / "params.json"

# (flag_key, doc_key, phrase-that-is-STALE-when-the-flag-is-True)
_CHECKS = [
    ("j_vwap_cont_enabled", "_j_vwap_cont_doc", "DORMANT: enabled=false"),
    ("j_vwap_cont_strike_override_enabled", "_j_vwap_cont_strike_override_doc",
     "DORMANT: j_vwap_cont_strike_override_enabled=false"),
]


def test_no_dormant_doc_on_live_flag():
    d = json.loads(PARAMS.read_text(encoding="utf-8"))
    stale = []
    for flag, doc, dormant in _CHECKS:
        if d.get(flag) is True and dormant in (d.get(doc) or ""):
            stale.append(f"{flag}=True but {doc} still says '{dormant}'")
    assert not stale, (
        "params doc/flag DRIFT (C7 -- a doc says dormant while the flag is LIVE):\n"
        + "\n".join(stale)
        + "\nFix the doc to describe the live-armed state (keep the revert instruction)."
    )
