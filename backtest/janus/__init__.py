"""JANUS — two-window regime detector.

Maintains a "recent" rolling window (e.g. last 10 trading days) and a
"baseline" window (e.g. last 60 trading days). When the recent window's
performance diverges sharply from baseline, JANUS emits a regime signal
that downstream consumers (heartbeat threshold tuning, dashboard) can react
to.

Adapted from ATLAS's JANUS meta-weighting layer
(https://github.com/chrisworsey55/atlas-gic/blob/main/src/janus.py)
which weighted multiple agent cohorts. Our adaptation: only one "cohort"
(Gamma's filter set) but two time windows of its outputs.

Three regime states:
    NOVEL_REGIME       — recent significantly worse than baseline. Tighten
                         thresholds, raise min_triggers, or pause auto-entry.
    HISTORICAL_REGIME  — recent significantly better than baseline. Conditions
                         match historical patterns; no adjustment.
    MIXED              — within deadband. Default; no signal.
"""

from . import detector

__all__ = ["detector"]
