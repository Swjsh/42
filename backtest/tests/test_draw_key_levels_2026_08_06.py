"""Guards for the auto-draw key-levels producer (setup/scripts/draw_key_levels.py).

WHAT INCIDENT THESE PIN (2026-08-06): J opened his chart and saw a "PMH 732.62" line
with SPY at 770 -- levels from JUNE. Two mechanisms, both guarded here:

  * out-of-band June levels were still in key-levels.json `levels` with draw_needed=true
    (PRIOR_CLOSE_2026-06-26 @ 731.22, PML_2026-06-29 @ 734.52), so a naive drawer would
    faithfully redraw them  -> test_june_level_is_excluded_at_august_spot
  * prices already retired into `deprecated_levels` still had live chart drawings,
    because nothing ever subtracted                                -> test_deprecated_price_is_never_drawn

The safety guards matter more than the selection guards: this is the only automation in
the repo that can destroy J's hand-drawn chart work. They pin that the module cannot
call removeAllShapes, and that every line it draws is TAG-prefixed (the TAG is the
recovery path when the state file is lost).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "setup" / "scripts"))

import draw_key_levels as dkl  # noqa: E402


AUGUST_SPOT = 768.14  # live chart last price when the incident was reproduced


def _key_levels() -> dict:
    """Trimmed real shape of automation/state/key-levels.json on 2026-08-06."""
    return {
        "spot_at_compute": 769.0,
        "levels": [
            {"price": 731.22, "role": "support", "label": "PRIOR_CLOSE_2026-06-26", "draw_needed": True},
            {"price": 734.52, "role": "support", "label": "PML_2026-06-29", "draw_needed": True},
            {"price": 754.71, "role": "support", "label": "SHELF_753.91_755.51_2026-08-06"},
            {"price": 767.46, "role": "support", "label": "INTRADAY_RTH_LOW_2026-08-06"},
            {"price": 770.24, "role": "resistance", "label": "PRIOR_DAY_CLOSE_2026-08-06"},
            {"price": 776.85, "role": "resistance", "label": "PRIOR_DAY_HIGH_2026-08-06"},
        ],
        "deprecated_levels": [
            {"price": 732.62, "label": "PMH_2026-06-26 (Active resistance, expired)"},
            {"price": 728.5, "label": "PML_2026-06-26 (Active support, expired)"},
            {"price": 770.24, "label": "SENTINEL_deprecated_wins_over_active"},
        ],
    }


# ---------------------------------------------------------------- selection

def test_june_level_is_excluded_at_august_spot():
    """THE incident guard: a $35-away June level must not be drawn on an August chart."""
    picked = dkl.select_levels(_key_levels(), spot=AUGUST_SPOT, band=15.0)
    prices = {p["price"] for p in picked}
    assert 731.22 not in prices, "June PRIOR_CLOSE redrawn -- the 'PMH 732.62 at SPY 770' bug is back"
    assert 734.52 not in prices, "June PML redrawn -- out-of-band filter regressed"


def test_deprecated_price_is_never_drawn():
    """A price retired into deprecated_levels must not be drawn even if still in `levels`."""
    picked = dkl.select_levels(_key_levels(), spot=AUGUST_SPOT, band=15.0)
    assert 770.24 not in {p["price"] for p in picked}, "deprecated_levels must win over the active list"


def test_near_spot_levels_are_kept():
    picked = dkl.select_levels(_key_levels(), spot=AUGUST_SPOT, band=15.0)
    prices = {p["price"] for p in picked}
    assert 767.46 in prices
    assert 776.85 in prices


def test_band_is_symmetric_and_inclusive():
    kl = {"levels": [{"price": 753.14, "role": "support", "label": "LOW_EDGE"},
                     {"price": 783.14, "role": "resistance", "label": "HIGH_EDGE"},
                     {"price": 753.13, "role": "support", "label": "JUST_OUT_LOW"}]}
    prices = {p["price"] for p in dkl.select_levels(kl, spot=AUGUST_SPOT, band=15.0)}
    assert {753.14, 783.14} <= prices
    assert 753.13 not in prices


def test_max_levels_cap_keeps_the_closest():
    kl = {"levels": [{"price": AUGUST_SPOT + i * 0.1, "role": "support", "label": f"L{i}"} for i in range(1, 30)]}
    picked = dkl.select_levels(kl, spot=AUGUST_SPOT, band=15.0, max_levels=5)
    assert len(picked) == 5
    assert picked[0]["price"] == pytest.approx(AUGUST_SPOT + 0.1, abs=0.011)


def test_duplicate_prices_are_deduped():
    kl = {"levels": [{"price": 770.0, "role": "support", "label": "A"},
                     {"price": 770.0, "role": "resistance", "label": "B"}]}
    assert len(dkl.select_levels(kl, spot=AUGUST_SPOT, band=15.0)) == 1


def test_malformed_level_does_not_crash_selection():
    kl = {"levels": [{"role": "support", "label": "NO_PRICE"},
                     {"price": "not-a-number", "label": "BAD"},
                     {"price": 770.0, "role": "support", "label": "GOOD"}]}
    assert {p["price"] for p in dkl.select_levels(kl, spot=AUGUST_SPOT, band=15.0)} == {770.0}


# ---------------------------------------------------------------- labelling

def test_humanize_strips_trailing_iso_date():
    assert dkl.humanize_label("PRIOR_DAY_CLOSE_2026-08-06") == "PRIOR DAY CLOSE"
    assert dkl.humanize_label("MEMORY_RES_114") == "MEMORY RES 114"
    assert dkl.humanize_label("") == "LEVEL"


def test_humanize_keeps_numeric_tokens_that_are_not_dates():
    assert dkl.humanize_label("SHELF_753.91_755.51_2026-08-06") == "SHELF 753.91 755.51"


# ---------------------------------------------------------------- SAFETY

def test_every_drawn_line_is_tag_prefixed():
    """The TAG is how orphaned lines are recovered when the state file is lost."""
    for lv in dkl.select_levels(_key_levels(), spot=AUGUST_SPOT, band=15.0):
        assert dkl.line_text(lv).startswith(dkl.TAG)


def test_tag_value_is_pinned():
    """Changing TAG silently orphans every line drawn under the old marker."""
    assert dkl.TAG == "[G] "


def _executable_source(path: Path) -> str:
    """Module source with docstrings and comments removed.

    Docstrings must be stripped by AST rather than by a startswith() heuristic: these
    modules *document* why removeAllShapes is forbidden, and a naive text scan would
    fire on the warning instead of on a real call.
    """
    import ast

    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    doc_spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            doc_spans.append((first.lineno, first.end_lineno))

    lines = src.splitlines()
    keep = [
        ln for i, ln in enumerate(lines, start=1)
        if not any(lo <= i <= hi for lo, hi in doc_spans) and not ln.strip().startswith("#")
    ]
    return "\n".join(keep)


def test_module_never_calls_remove_all_shapes():
    """removeAllShapes/draw_clear take no scope argument -- they would wipe J's work."""
    for mod in ("draw_key_levels.py", "tv_cdp.py"):
        code = _executable_source(REPO_ROOT / "setup" / "scripts" / mod)
        assert "removeAllShapes" not in code, f"{mod} must never call removeAllShapes()"
        assert "removeAllStudies" not in code, f"{mod} must never call removeAllStudies()"


def test_legacy_sweep_only_targets_deprecated_prices():
    """The sweep's authorisation is key-levels.json having retired that exact price."""
    dep = dkl.deprecated_prices(_key_levels())
    assert dep == {732.62, 728.5, 770.24}
    assert 731.22 not in dep, "a merely-old ACTIVE level is not sweep-authorised"


def test_deprecated_prices_tolerates_junk():
    assert dkl.deprecated_prices({"deprecated_levels": [{"label": "no price"}, "a string", {"price": None}]}) == set()
    assert dkl.deprecated_prices({}) == set()


def test_support_and_resistance_get_different_colors():
    sup = dkl.overrides_for({"role": "support"})
    res = dkl.overrides_for({"role": "resistance"})
    assert sup["linecolor"] != res["linecolor"]
    assert sup["linestyle"] == 2, "dashed keeps engine lines visually distinct from J's solid work"
