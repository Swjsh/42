"""backtest.lib.patterns — chart patterns as a GRAMMAR over existing primitives.

One registry (registry.py, 11 seeded rules), one composition engine (grammar.py +
combinators.py + predicates.py), one C27 pre-screen consumer
(backtest/tools/pattern_prescreen.py). NOT 30 bespoke per-pattern detector files.

Full design + primitive-inventory citations + handoff-to-battery spec:
markdown/research/PATTERN-GRAMMAR.md.

NO WIRING: this package is not imported by the live engine, setup_dispatch.py, or any
watcher. It is research/prescreen-only until a rule clears the pipeline described in
PATTERN-GRAMMAR.md sec 3.
"""
from __future__ import annotations

from .combinators import Predicate, all_of, any_of, negate, then_break, within_n_bars_after
from .context import (
    LEVEL_ROLE_VALUES,
    LevelLike,
    PatternContext,
    level_matches_role,
    levels_from_key_levels_json,
    levels_from_level_memory,
)
from .grammar import (
    RULE_DIRECTIONS,
    RULE_TIERS,
    VALID_TIMEFRAMES,
    GrammarHit,
    PatternRule,
    evaluate_rule,
    evaluate_rule_over_range,
)
from .registry import REGISTRY, REGISTRY_BY_NAME

__all__ = [
    "Predicate",
    "all_of",
    "any_of",
    "negate",
    "then_break",
    "within_n_bars_after",
    "LEVEL_ROLE_VALUES",
    "LevelLike",
    "PatternContext",
    "level_matches_role",
    "levels_from_key_levels_json",
    "levels_from_level_memory",
    "RULE_DIRECTIONS",
    "RULE_TIERS",
    "VALID_TIMEFRAMES",
    "GrammarHit",
    "PatternRule",
    "evaluate_rule",
    "evaluate_rule_over_range",
    "REGISTRY",
    "REGISTRY_BY_NAME",
]
