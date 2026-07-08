"""Guard: F1 ribbon-momentum gate stays DISABLED (V0, engine-vision build 2026-07-08).

The gate was judged harmful (params doc, L107: WF=-1.308, "gate was removing profitable trades")
and MEANT to be disabled — but setting it to 0 left a RESIDUAL gate, because the gate code guards
on `min_ribbon_momentum_cents is not None` (so 0 ARMS it, blocking entries on a CONTRACTING
ribbon; fired 29x SKIP_RIBBON_MOMENTUM_GATE live). The V0 A/B
(analysis/recommendations/ribbon-momentum-gate-probe-2026-07-08.json) confirmed that residual
gate removed a NET +$585 cohort (n=14, survives realistic slippage) — J's big-down-day-put edge.
Disabled by setting the param to null. This guard pins that decision: a future 0 or positive
value re-arms the harmful gate. REVOKE = a POSITIVE threshold + OOS first (then update this test).
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_f1_gate_disabled_in_live_params():
    p = json.loads((REPO / "automation" / "state" / "params.json").read_text(encoding="utf-8"))
    v = p.get("min_ribbon_momentum_cents")
    assert v is None, (
        f"F1 RIBBON-MOMENTUM GATE re-armed: min_ribbon_momentum_cents={v!r} (must be null/None). "
        f"0 does NOT disable it — the gate code checks `is not None`, so 0 leaves a residual gate "
        f"blocking entries on a contracting ribbon. V0 A/B showed that removes a +$585 cohort. "
        f"To intentionally re-arm: set a POSITIVE threshold, run OOS first, and update this guard."
    )
