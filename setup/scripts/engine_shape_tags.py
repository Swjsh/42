"""engine_shape_tags.py -- the ONE shared tuple of chart-drawing tag prefixes that mark a
TradingView shape as engine-drawn (2026-09-09, WS-B chart hygiene sweep, L251).

WHY THIS EXISTS: `chart_hygiene.py` needs to answer "is this shape ours or J's?" across
every engine producer at once. Before this file, that answer required importing (or
worse, re-typing) `draw_key_levels.TAG` ("[G] ") and `trendline_headless_draw.TAG`
("[GTL] ") separately, plus inventing a THIRD tag for WS-A's forthcoming engine-acting
layer ("[GE] ", ratified in the work order's tag taxonomy, F(1): `[GE]` = acts-on,
`[G]` = level context, `[GTL]` = shadow fitter, untagged = J). L251 (two producers, one
right) is exactly the failure mode a second independently-typed copy of a tag constant
invites -- so this module imports the two that already exist rather than copying their
string literals, and is the single place the still-unclaimed `[GE] ` tag is defined so
WS-A's author picks it up from here instead of re-deciding it.

NEUTRALITY: this file is new and touches nothing WS-A/C/D own. It is NOT
`automation/scripts/compute_trendlines.py`, `automation/scripts/read_chart_drawings.js`,
or `setup/scripts/j_drawn_lines_capture.py` (all three off-limits this session --
another agent is concurrently editing them) and it does not edit `draw_key_levels.py`'s
or `trendline_headless_draw.py`'s own TAG definitions, only reads them.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from draw_key_levels import TAG as LEVELS_TAG  # noqa: E402 -- "[G] ", imported not copied
from trendline_headless_draw import TAG as TRENDLINE_TAG  # noqa: E402 -- "[GTL] ", imported not copied

# Not yet claimed by any producer as of 2026-09-09 -- WS-A (engine-view read-out, work
# order §9.5 row A) is the intended author of shapes carrying this tag. Defined here,
# once, so WS-A and this hygiene sweep can never disagree on the string.
ENGINE_ACTING_TAG = "[GE] "

# Every prefix that means "an engine producer drew this, not J". Order does not matter --
# membership is a simple startswith() scan (see `is_engine_tagged` in chart_hygiene.py).
ENGINE_TAG_PREFIXES: tuple[str, ...] = (LEVELS_TAG, TRENDLINE_TAG, ENGINE_ACTING_TAG)
