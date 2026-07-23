"""grammar.py — PatternRule: the declarative unit of the pattern grammar, plus the
evaluation engine that turns a composed Predicate into a GrammarHit.

THE POINT (per markdown/research/PATTERN-GRAMMAR.md): chart patterns are a GRAMMAR over
the primitives the codebase already computes (market structure, levels, VWAP, volume,
compression, wicks, gaps) — not 30 bespoke per-pattern detector files. A PatternRule is
a name + a boolean composition of predicates.py's 15 domain predicates (glued with
combinators.py's all_of/any_of/negate/within_n_bars_after/then_break) + metadata
(tier, timeframes, direction, citation, disclosed thresholds). registry.py seeds 11 of
these; backtest/tools/pattern_prescreen.py runs every one of them over cached history.

C6 CONTRACT: `evaluate_rule(rule, ctx, t)` is C6-safe iff `rule.predicate` only reads
`ctx.bars[<=t]` (directly, or via `ctx.structure`/`ctx.vwap`/`ctx.bandwidth`/
`ctx.levels_for(t)`, all of which are themselves causal — see context.py). This module
adds no I/O of its own; it is pure dataclasses + pure functions, so purity/determinism
follow directly from predicates.py + combinators.py being pure. See
tests/test_pattern_grammar.py for the enforcement suite (C6 bite, determinism, schema).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .combinators import Predicate
from .context import PatternContext

RULE_DIRECTIONS: tuple[str, ...] = ("bullish", "bearish", "bidirectional")
RULE_TIERS: tuple[int, ...] = (1, 2)
VALID_TIMEFRAMES: tuple[str, ...] = ("5m", "15m", "30m")


@dataclass(frozen=True, slots=True)
class GrammarHit:
    """One firing of one PatternRule at one bar. `bias` is always resolved to a concrete
    "bullish"/"bearish" — never "bidirectional" (that is only a RULE-level declaration
    meaning "this rule can fire either way, decided per-instance" — see evaluate_rule)."""
    rule_name: str
    tier: int
    timeframe: str
    bar_index: int
    bias: str
    trigger_level: Optional[float]
    notes: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PatternRule:
    """A declarative pattern-grammar rule.

    name:        machine-readable, unique across the registry.
    tier:        1 (strong existing-primitive backing + clear intraday applicability
                 per TA-PATTERN-REFERENCE.md) | 2 (weaker applicability / more
                 speculative / higher-complexity geometry).
    timeframes:  which timeframe(s) this rule is INTENDED for (metadata; the prescreen
                 tool evaluates every rule on every cached timeframe regardless, to
                 let the data — not an assumption — decide where it's testable).
    direction:   "bullish" | "bearish" | "bidirectional". Bidirectional rules' predicate
                 MUST supply a resolved "bias" key in its evidence dict when it fires
                 (enforced at evaluation time, not construction time, since it's a
                 runtime contract on the predicate's return value).
    predicate:   the composed boolean predicate (see combinators.py).
    citation:    pointer(s) into TA-PATTERN-REFERENCE.md and/or the existing codebase
                 primitive this rule reuses or is modeled on. Never a fabricated stat.
    thresholds:  the OBJECTIVE, DISCLOSED numeric knobs this rule's composition used
                 (for audit — "no magic numbers" per repo coding style).
    description: one paragraph, human-readable.
    anchors:     OPTIONAL tuple of live-tape exhibit dicts this rule was built FROM or
                 is claimed to cover — the pre-ship + drift contract (filed
                 2026-07-23 from the self-audit gap "no reliable pre-ship validation
                 step that confirms a rule actually fires on the specific anchor bars
                 J identified", ENGULFING-AT-STRUCTURE-TRIGGER near-miss). Each dict:
                 {"date": "YYYY-MM-DD", "time_et": "HH:MM", "bias": "bullish"|"bearish",
                  "expected_fire": bool, "note": str}. `expected_fire` is the CURRENT,
                 HONEST state of whether the predicate actually fires at that bar — not
                 an aspiration. backtest/tools/pattern_anchor_verify.py re-checks every
                 declared anchor against the live predicate; test_pattern_anchor_verify.py
                 asserts actual == expected_fire for all of them, so registry.py can never
                 silently drift out of sync with the anchor exhibits it cites (either a
                 rule that was supposed to cover an anchor quietly stops firing on it, or
                 one honestly declared NOT to fire starts firing without anyone updating
                 the record). Empty tuple (default) = no anchor claim made; nothing to
                 verify — most rules (esp. the original 11 seed rules, which were built
                 from TA-PATTERN-REFERENCE.md citations, not specific live bars) leave
                 this empty by design.
    """
    name: str
    tier: int
    timeframes: tuple[str, ...]
    direction: str
    predicate: Predicate
    citation: str
    thresholds: dict
    description: str
    anchors: tuple[dict, ...] = ()

    def __post_init__(self) -> None:
        if self.tier not in RULE_TIERS:
            raise ValueError(f"{self.name}: tier must be one of {RULE_TIERS}, got {self.tier}")
        if self.direction not in RULE_DIRECTIONS:
            raise ValueError(f"{self.name}: direction must be one of {RULE_DIRECTIONS}, got {self.direction!r}")
        if not self.timeframes:
            raise ValueError(f"{self.name}: timeframes must be non-empty")
        if not set(self.timeframes).issubset(VALID_TIMEFRAMES):
            raise ValueError(f"{self.name}: timeframes must be a subset of {VALID_TIMEFRAMES}")
        if not callable(self.predicate):
            raise ValueError(f"{self.name}: predicate must be callable")
        if not self.thresholds:
            raise ValueError(f"{self.name}: thresholds must be a non-empty dict (objective, disclosed knobs)")
        if not self.citation:
            raise ValueError(f"{self.name}: citation must be non-empty")
        if not self.description:
            raise ValueError(f"{self.name}: description must be non-empty")
        for a in self.anchors:
            missing = {"date", "time_et", "bias", "expected_fire"} - set(a)
            if missing:
                raise ValueError(f"{self.name}: anchor {a!r} missing required keys {missing}")
            if a["bias"] not in ("bullish", "bearish"):
                raise ValueError(f"{self.name}: anchor bias must be bullish/bearish, got {a['bias']!r}")


def evaluate_rule(rule: PatternRule, ctx: PatternContext, t: int, *, timeframe: str) -> Optional[GrammarHit]:
    """Evaluate `rule` at bar t of `ctx`. Pure; deterministic; C6-safe as long as
    `rule.predicate` honors the contract documented in predicates.py's module docstring.
    """
    result = rule.predicate(ctx, t)
    if result is None:
        return None
    if rule.direction == "bidirectional":
        bias = result.get("bias")
        if bias not in ("bullish", "bearish"):
            raise ValueError(
                f"{rule.name}: bidirectional rule's predicate must return "
                f"bias='bullish'|'bearish' in its evidence dict at bar {t}; got {bias!r}"
            )
    else:
        bias = rule.direction
    notes = {k: v for k, v in result.items() if k not in ("bias", "trigger_level")}
    return GrammarHit(
        rule_name=rule.name, tier=rule.tier, timeframe=timeframe, bar_index=t, bias=bias,
        trigger_level=result.get("trigger_level"), notes=notes,
    )


def evaluate_rule_over_range(
    rule: PatternRule,
    ctx: PatternContext,
    *,
    timeframe: str,
    start: int = 0,
    end: Optional[int] = None,
) -> list[GrammarHit]:
    """Evaluate `rule` at every bar index in [start, end) (end defaults to len(ctx.bars)).
    Returns hits in bar order. This is the function backtest/tools/pattern_prescreen.py
    calls once per (rule, timeframe)."""
    hi = len(ctx.bars) if end is None else end
    hits: list[GrammarHit] = []
    for t in range(start, hi):
        hit = evaluate_rule(rule, ctx, t, timeframe=timeframe)
        if hit is not None:
            hits.append(hit)
    return hits
