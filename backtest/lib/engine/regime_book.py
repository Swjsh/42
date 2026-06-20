"""regime_book — the Regime-Aware Multi-Setup Book scaffold (DESIGN, propose-only).

Spec: ``markdown/research/REGIME-AWARE-BOOK.md``. This is the LEAN skeleton of the architecture
that ends the **one-setup fragility** by routing each bar to the setup(s) that have
edge in the *current regime*, instead of always trading the single
``BEARISH_REJECTION_RIDE_THE_RIBBON`` edge regardless of market state.

WHAT THIS IS (three layers, see the design doc)
-----------------------------------------------
1. :func:`classify_regime` — a PURE, $0, look-ahead-safe classifier that maps the
   market state to ONE coarse :class:`Regime` tag (bull_trend / bear_trend /
   range_pin / high_vol / neutral) from signals we ALREADY compute every bar:
   VIX level + VIX character, the 5m/15m ribbon stack (trend vs range), and range
   compression vs the 20-bar baseline. It accepts an OPTIONAL dealer-gamma hint
   from :mod:`lib.engine.gex_regime` (live-only corroborator; absent in backtests).
2. :data:`REGIME_SETUP_MAP` — the routing table as **DATA** (a dict), not logic:
   ``regime -> tuple[SetupSlot, ...]``. Adding/promoting/retiring a setup is a data
   edit, never an engine change. :func:`select_setups` reads it.
3. (existing engine) — each selected setup is still scored/gated by its OWN
   ``engine.score`` / ``engine.gates`` checks. The regime layer decides only WHICH
   setup is *eligible*; it never relaxes a gate, invents a trigger, or sizes a trade.

PROPOSE-ONLY (Rule 9) — NOT WIRED LIVE
--------------------------------------
* No heartbeat / params / order path imports this module. It is scaffolding.
* The ENTIRE seed :data:`REGIME_SETUP_MAP` is ``WATCH_ONLY`` (no setup has cleared
  the full real-★★★ + anchor-no-regression promotion bar yet — even the two
  DSR-PASS data-discovered survivors are proxy-STRIKE real-fills, not promoted), so
  :func:`select_setups` returns an **empty roster for every regime today**. The book
  is wired-up but INERT — the propose-only posture made structural. A setup becomes
  selectable only when promoted to ``REGIME_ACTIVE`` (a one-line data edit, after it
  meets the bar in ``§6`` of the design doc).

HONEST PROVENANCE
-----------------
The seed map's numbers come from TWO scorecards, both carried verbatim per slot so
the map is self-documenting and the promotion gate is checkable in code:

* ``analysis/recommendations/fleet-standalone-regime.json`` (the corrected, UNBIASED
  standalone real-fills eval) — on **proxy ★★ levels**, mostly DSR-WEAK, some
  low-power. Candidates worth a real-★★★ re-test, NOT ready-to-trade setups.
* ``analysis/recommendations/infinite-ammo-discovery.json`` (a first-principles
  DISCOVERY eval NOT gated on J anchors) — two survivors, ``VWAP_TREND_PULLBACK``
  (H4) and ``GAP_AND_GO`` (H2b), that cleared standalone real-fills + OOS
  sign-stable + **DSR PASS** + drop-top-5 robustness, both directions positive.
  These are the first DATA-DISCOVERED (not anchor-derived) candidates in the book —
  stronger statistically than the fleet rows, but still proxy-STRIKE real-fills on
  the wider population (L58), so WATCH_ONLY like everything else.

They are all *candidates*, not ready-to-trade setups.

PURITY
------
Like ``risk_gate.check_order`` / ``engine.score.score_bar``: no I/O, no MCP, no clock,
no mutation. All records are frozen dataclasses; every function reads its inputs and
returns a NEW value. ``classify_regime`` reads a tiny structural ``RegimeSignals``
view (built from a ``filters.BarContext`` via :func:`signals_from_bar_context`, or
directly in tests) so it is decoupled from the full BarContext shape and trivially
testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence

__all__ = [
    "Regime",
    "PromotionStatus",
    "Evidence",
    "SetupSlot",
    "RegimeSignals",
    "REGIME_PRECEDENCE",
    "REGIME_SETUP_MAP",
    "classify_regime",
    "select_setups",
    "signals_from_bar_context",
    # thresholds (exported so tests pin them and callers can read, not redefine)
    "VIX_HIGH_VOL_FLOOR",
    "VIX_LOW_CEIL",
    "RANGE_COMPRESSION_RATIO",
    "VIX_DEADBAND",
]

# ── classifier thresholds (lean, from the weekend proxy definition) ────────────
# Mirror fleet-standalone-regime.json#regime_proxy_definition so the live tag and
# the research that justified it use the SAME cut points (no silent drift, C14).
VIX_HIGH_VOL_FLOOR = 19.0   # VIX >= this => high_vol regime (HIGH bucket).
VIX_LOW_CEIL = 16.0         # VIX < this => "low" (pin/bullish-reclaim regimes need it).
RANGE_COMPRESSION_RATIO = 0.85  # today_range / trailing_median_range < this => compressed.
VIX_DEADBAND = 0.05         # matches filters.VIX_RISING_DEADBAND (character deadband).


class Regime(str, Enum):
    """The coarse 5-way market-state tag (see design doc §3.2).

    ``str`` mixin so a Regime is JSON-friendly and compares equal to its value
    (``Regime.BULL_TREND == "bull_trend"``) for cheap logging/scorecards.
    """

    BULL_TREND = "bull_trend"
    BEAR_TREND = "bear_trend"
    RANGE_PIN = "range_pin"
    HIGH_VOL = "high_vol"
    NEUTRAL = "neutral"


class PromotionStatus(str, Enum):
    """A setup's lifecycle state within the book (see design doc §6).

    * ``WATCH_ONLY``   — in the framework, EXCLUDED from live selection (default).
    * ``REGIME_ACTIVE`` — cleared the promotion bar; eligible in its regime.
    * ``RETIRED``      — revoked/regressed; kept as a record, never selected.
    """

    WATCH_ONLY = "WATCH_ONLY"
    REGIME_ACTIVE = "REGIME_ACTIVE"
    RETIRED = "RETIRED"


@dataclass(frozen=True)
class Evidence:
    """Provenance for a setup slot — carried verbatim from its scorecard.

    Pure data. Makes :data:`REGIME_SETUP_MAP` self-documenting (the *why* and *how
    strong* live next to the slot) and lets the promotion gate be checked in code
    against the slot's own numbers. ``source`` names the scorecard the figures came
    from so a reader can trace them.
    """

    exp: float                       # in-regime real-fills expectancy ($/trade)
    wr: float                        # win rate (%)
    n: int                           # sample size in the regime
    dsr_verdict: str = "UNKNOWN"     # "PASS" | "WEAK" | "FAIL" | "UNKNOWN"
    oos_sign_stable: Optional[bool] = None
    low_power: bool = False          # True when n is too small to over-read (C24)
    on_real_levels: bool = False     # False => proxy ★★ levels (L58 caveat applies)
    source: str = ""                 # scorecard path the numbers came from


@dataclass(frozen=True)
class SetupSlot:
    """One setup's participation in one regime (a single cell of the book).

    Pure data describing HOW a setup participates — never a position. ``sizing_tier``
    is an ADVISORY hint to the existing sizer; ``risk_gate.check_order`` + the sizer
    remain the sole authority on actual size and the per-account caps.
    """

    setup: str
    status: PromotionStatus = PromotionStatus.WATCH_ONLY
    sizing_tier: str = "base"        # "base" | "elite" | "half" — advisory only
    evidence: Optional[Evidence] = None
    note: str = ""

    def is_live_eligible(self) -> bool:
        """True iff this slot may be considered for a live decision (REGIME_ACTIVE)."""
        return self.status is PromotionStatus.REGIME_ACTIVE


@dataclass(frozen=True)
class RegimeSignals:
    """The minimal, structural view :func:`classify_regime` reads (decoupled input).

    Built from a ``filters.BarContext`` via :func:`signals_from_bar_context`, or
    directly in tests. Keeping the classifier's input to this tiny record (rather
    than the full BarContext) is what makes it pure and trivially testable.

    Attributes
    ----------
    vix_now / vix_prior:
        Current and prior-bar VIX (character via the deadband comparison).
    ribbon_stack:
        5m ribbon stack: ``"BULL" | "BEAR" | "MIXED" | "WARMUP" | None``.
    htf_stack:
        15m ribbon stack (same domain) — corroborator, may be ``None``.
    range_ratio:
        ``current_bar_range / trailing_median(20) range``. ``None`` when the
        baseline is unavailable (warmup) => "not compressed" is assumed.
    gex_hint:
        Optional dealer-gamma regime string from ``gex_regime`` (``"long_gamma_pin"``
        / ``"short_gamma_trend"`` / ``"flat"``). LIVE-ONLY corroborator; ``None`` in
        every backtest (no historical chain OI). The classifier NEVER requires it.
    """

    vix_now: float
    vix_prior: float
    ribbon_stack: Optional[str]
    htf_stack: Optional[str] = None
    range_ratio: Optional[float] = None
    gex_hint: Optional[str] = None

    # ── derived character helpers (kept here so the classifier stays flat) ──
    def vix_rising(self) -> bool:
        return self.vix_now > self.vix_prior + VIX_DEADBAND

    def vix_falling(self) -> bool:
        return self.vix_now < self.vix_prior - VIX_DEADBAND

    def is_compressed(self) -> bool:
        return self.range_ratio is not None and self.range_ratio < RANGE_COMPRESSION_RATIO

    def is_low_vix(self) -> bool:
        return self.vix_now < VIX_LOW_CEIL


# ── precedence: checked top-to-bottom; FIRST match wins (declared, auditable) ──
# high_vol first: an elevated-fear day is high_vol whatever the stack says (C23 —
# tier labels conflate VIX populations; high-vol is its own bucket). Then the two
# trends, then the pin, else neutral. The order IS the spec; it lives here, not in
# nested if/elif, so it is testable and never silently reordered.
REGIME_PRECEDENCE: tuple[Regime, ...] = (
    Regime.HIGH_VOL,
    Regime.BEAR_TREND,
    Regime.BULL_TREND,
    Regime.RANGE_PIN,
    Regime.NEUTRAL,
)


def _matches(regime: Regime, s: RegimeSignals) -> bool:
    """Predicate for ONE regime against the signals (pure, no precedence here).

    Precedence is applied by :func:`classify_regime` walking ``REGIME_PRECEDENCE``;
    each predicate only answers "do MY conditions hold?" in isolation. ``NEUTRAL``
    is the always-true fallback (it is last in precedence).
    """
    stack = (s.ribbon_stack or "").upper()

    if regime is Regime.HIGH_VOL:
        # Elevated fear dominates, regardless of stack. GEX short-gamma corroborates.
        return s.vix_now >= VIX_HIGH_VOL_FLOOR

    if regime is Regime.BEAR_TREND:
        # Down-stack with stable/rising fear (NOT a VIX-falling relief bounce).
        if stack != "BEAR":
            return False
        if s.vix_falling():
            return False
        return True

    if regime is Regime.BULL_TREND:
        # Up-stack, fear not rising, not pinned/compressed.
        if stack != "BULL":
            return False
        if s.vix_rising():
            return False
        if s.is_compressed():
            return False
        return True

    if regime is Regime.RANGE_PIN:
        # Chop + compression + low VIX. LIVE: GEX long_gamma_pin reinforces.
        if stack != "MIXED":
            return False
        if not s.is_compressed():
            return False
        if not s.is_low_vix():
            return False
        return True

    if regime is Regime.NEUTRAL:
        return True  # always-true fallback (last in precedence)

    return False


def classify_regime(signals: RegimeSignals) -> Regime:
    """Map the market state to ONE :class:`Regime` (pure, $0, look-ahead-safe).

    Walks :data:`REGIME_PRECEDENCE` and returns the FIRST regime whose predicate
    holds. ``NEUTRAL`` is guaranteed to match last, so a value is always returned.

    The optional ``signals.gex_hint`` (dealer-gamma, live-only) is used as a
    *corroborator* that can only ever REINFORCE the VIX/ribbon/compression read,
    never override it: a ``short_gamma_trend`` hint nudges a borderline MIXED-stack
    high-vol-ish tape toward ``high_vol``; a ``long_gamma_pin`` hint nudges a
    borderline compressed tape toward ``range_pin``. Because the hint is absent in
    every backtest, the classifier is fully backtestable on the base signals alone.

    Args:
        signals: the :class:`RegimeSignals` view (from a BarContext or a test).

    Returns:
        The classified :class:`Regime`.
    """
    base = _apply_precedence(signals)
    return _apply_gex_corroboration(base, signals)


def _apply_precedence(s: RegimeSignals) -> Regime:
    """Return the first regime in precedence whose predicate matches ``s``."""
    for regime in REGIME_PRECEDENCE:
        if _matches(regime, s):
            return regime
    return Regime.NEUTRAL  # unreachable (NEUTRAL is in precedence) — belt-and-suspenders


def _apply_gex_corroboration(base: Regime, s: RegimeSignals) -> Regime:
    """Apply the LIVE-only dealer-gamma corroborator (reinforce-only, never override).

    Only acts on a ``NEUTRAL`` base read (the ambiguous case) and only nudges it to a
    regime the GEX literature supports: ``long_gamma_pin`` + low VIX -> ``range_pin``;
    ``short_gamma_trend`` + high VIX -> ``high_vol``. Anything else (or no hint) leaves
    the base read untouched. This keeps GEX strictly additive and never able to flip a
    clean VIX/ribbon classification.
    """
    if s.gex_hint is None or base is not Regime.NEUTRAL:
        return base
    hint = s.gex_hint.strip().lower()
    if hint == "long_gamma_pin" and s.is_low_vix():
        return Regime.RANGE_PIN
    if hint == "short_gamma_trend" and s.vix_now >= VIX_HIGH_VOL_FLOOR:
        return Regime.HIGH_VOL
    return base


def select_setups(
    regime: Regime,
    *,
    include_watch: bool = False,
    book: Optional[dict] = None,
) -> tuple[SetupSlot, ...]:
    """Return the setup slots routed to ``regime`` (DATA-driven, from the map).

    SAFETY PROPERTY (the propose-only contract, made structural): by default this
    returns ONLY ``REGIME_ACTIVE`` slots. ``WATCH_ONLY`` slots are EXCLUDED from the
    live-eligible set; ``RETIRED`` slots are NEVER returned. Because the entire seed
    :data:`REGIME_SETUP_MAP` is ``WATCH_ONLY`` today, ``select_setups(regime)`` with
    defaults returns ``()`` for EVERY regime — the book is wired-up but inert.

    Args:
        regime: the classified market state.
        include_watch: when True, also include ``WATCH_ONLY`` slots (for research /
            shadow-mode / reporting ONLY — never for a live decision). ``RETIRED``
            remain excluded even then.
        book: override the map (tests inject a synthetic book); defaults to
            :data:`REGIME_SETUP_MAP`.

    Returns:
        A tuple of :class:`SetupSlot` (possibly empty). New tuple — never the
        internal map's object — so callers cannot mutate the book.
    """
    the_book = REGIME_SETUP_MAP if book is None else book
    slots = the_book.get(regime, ())
    out: list[SetupSlot] = []
    for slot in slots:
        if slot.status is PromotionStatus.RETIRED:
            continue
        if slot.status is PromotionStatus.WATCH_ONLY and not include_watch:
            continue
        out.append(slot)
    return tuple(out)


def signals_from_bar_context(ctx, *, gex_hint: Optional[str] = None) -> RegimeSignals:
    """Adapt a ``filters.BarContext`` into the :class:`RegimeSignals` view.

    The ONLY place that knows the BarContext shape, so the classifier stays pure and
    decoupled. Computes ``range_ratio`` from the trigger bar's range vs the context's
    20-bar range baseline (``range_baseline_20``) — the same look-ahead-safe
    compression proxy the weekend research used (the baseline is prior-bars-only).

    Args:
        ctx: a ``filters.BarContext`` (duck-typed — only the fields below are read).
        gex_hint: optional live dealer-gamma regime string (``None`` in backtests).

    Returns:
        A :class:`RegimeSignals`.
    """
    ribbon_stack = None
    ribbon_now = getattr(ctx, "ribbon_now", None)
    if ribbon_now is not None:
        ribbon_stack = getattr(ribbon_now, "stack", None)

    range_ratio = None
    baseline = float(getattr(ctx, "range_baseline_20", 0.0) or 0.0)
    bar = getattr(ctx, "bar", None)
    if bar is not None and baseline > 0:
        try:
            rng = float(bar["high"]) - float(bar["low"])
            range_ratio = rng / baseline
        except (KeyError, TypeError, ValueError):
            range_ratio = None

    return RegimeSignals(
        vix_now=float(getattr(ctx, "vix_now", 0.0) or 0.0),
        vix_prior=float(getattr(ctx, "vix_prior", 0.0) or 0.0),
        ribbon_stack=ribbon_stack,
        htf_stack=getattr(ctx, "htf_15m_stack", None),
        range_ratio=range_ratio,
        gex_hint=gex_hint,
    )


# ─────────────────────────────────────────────────────────────────────────────
# THE BOOK (DATA) — the seed regime->setup routing table.
#
# PROVISIONAL + ENTIRELY WATCH_ONLY. Numbers from TWO scorecards (see HONEST
# PROVENANCE in the module docstring): the unbiased standalone fleet eval (_FLEET,
# proxy ★★ levels, mostly DSR-WEAK) AND the first-principles discovery eval
# (_DISCOVERY) whose two survivors — VWAP_TREND_PULLBACK (H4) and GAP_AND_GO (H2b) —
# are DSR-PASS, OOS sign-stable, both-direction-positive, but still proxy-STRIKE
# real-fills. All candidates worth a real-★★★ re-test, NOT ready to trade.
# select_setups(regime) returns () for every regime until a slot is promoted to
# REGIME_ACTIVE (a one-line edit here, after it meets the design-doc §6 bar). Each
# slot carries its Evidence verbatim so the map is self-documenting.
#
# range_pin is DELIBERATELY EMPTY: the bounce family REVIVED in-regime but on n=2-11
# (low_power) and only under the mean-reversion exit, not the engine default — wiring
# it now would be the exact over-fit this architecture exists to prevent. It is a
# named target for the next real-fills re-test, recorded in the design doc.
# ─────────────────────────────────────────────────────────────────────────────
_FLEET = "analysis/recommendations/fleet-standalone-regime.json"
# Second provenance source: the infinite-ammo first-principles DISCOVERY eval
# (NOT gated on J anchors). Two survivors cleared standalone real-fills + OOS
# sign-stable + DSR PASS + drop-top-5 robustness — the first DATA-DISCOVERED
# (not anchor-derived) candidates in the book. Still proxy-strike real-fills on
# the wider population, hence WATCH_ONLY like everything else (L58 caveat). Each
# slot below records the ATM tier (the disclosed default; ITM1 was modestly
# better — noted per slot) so the map does not overstate the edge.
_DISCOVERY = "analysis/recommendations/infinite-ammo-discovery.json"

REGIME_SETUP_MAP: dict[Regime, tuple[SetupSlot, ...]] = {
    Regime.BEAR_TREND: (
        SetupSlot(
            setup="BEARISH_REJECTION_RIDE_THE_RIBBON",
            status=PromotionStatus.WATCH_ONLY,  # the confirmed edge — but re-confirm on real ★★★
            sizing_tier="base",
            evidence=Evidence(
                exp=0.0, wr=0.0, n=0, dsr_verdict="UNKNOWN",
                on_real_levels=False,
                source="J anchors (OP-16) + proxy fleet eval",
            ),
            note="The only setup with J's real winners. Bar to promote = re-confirm "
                 "on real ★★★ + the accruing live archive (anchor-no-regression).",
        ),
        SetupSlot(
            setup="NAMED_LEVEL_SECOND_TEST",
            status=PromotionStatus.WATCH_ONLY,
            sizing_tier="base",
            evidence=Evidence(
                exp=8.65, wr=63.2, n=144, dsr_verdict="WEAK",
                oos_sign_stable=False, low_power=False,
                on_real_levels=False, source=_FLEET,
            ),
            note="Long, in bear_trend. DSR WEAK on proxy levels.",
        ),
        SetupSlot(
            setup="VWAP_TREND_PULLBACK",
            status=PromotionStatus.WATCH_ONLY,
            sizing_tier="base",
            evidence=Evidence(
                exp=45.88, wr=42.4, n=92, dsr_verdict="PASS",
                oos_sign_stable=True, low_power=False,
                on_real_levels=False, source=_DISCOVERY,
            ),
            note="H4 — pullback to session VWAP in the trend direction (here the "
                 "bear/put side). Data-discovered survivor: standalone real-fills "
                 "PASS, OOS sign-stable, DSR PASS, robust to drop-top-5, both "
                 "directions positive. ATM exp shown; ITM1 +$63/trade. Proxy levels. "
                 "2026-06-19: LIVE detector built + parity-verified "
                 "(lib/watchers/vwap_trend_pullback_watcher.py); ratify scorecard "
                 "analysis/recommendations/vwap-trend-pullback-LIVE.json (causality "
                 "PASS, WF median 1.679, sub-window stable). Stays WATCH_ONLY here: "
                 "execution gated on heartbeat wiring (propose-only) + OP-21 live wins; "
                 "regime-sensitive (bled 2025-Q2/Q3, 7 positive OOS months since). "
                 "2026-06-19 regime-gate research (docs/VWAP-TREND-PULLBACK-REGIME-GATE-"
                 "2026-06-19.md): NO clean causal gate kills the bimodality on the LIVE "
                 "chart-stop-only exit; ALSO the scorecard's +$45.88 used premium_stop=-0.08 "
                 "while the live watcher trades chart-stop-only (+$14/t, WF 0.239). Keep "
                 "dormant; fix the exit config before a 2nd-edge claim.",
        ),
        SetupSlot(
            setup="GAP_AND_GO",
            status=PromotionStatus.WATCH_ONLY,
            sizing_tier="base",
            evidence=Evidence(
                exp=35.24, wr=42.9, n=84, dsr_verdict="PASS",
                oos_sign_stable=True, low_power=False,
                on_real_levels=False, source=_DISCOVERY,
            ),
            note="H2b — opening-gap continuation after a confirming first bar (bear/put "
                 "side). Data-discovered survivor: 5/6 quarters positive, OOS sign-stable, "
                 "DSR PASS, both directions positive. ATM exp shown; ITM1 +$40/trade. "
                 "Proxy levels.",
        ),
    ),
    Regime.BULL_TREND: (
        SetupSlot(
            setup="DOUBLE_BOTTOM_MORNING_LOW_VOL",
            status=PromotionStatus.WATCH_ONLY,
            sizing_tier="base",
            evidence=Evidence(
                exp=20.61, wr=66.7, n=24, dsr_verdict="WEAK",
                oos_sign_stable=True, low_power=False,
                on_real_levels=False, source=_FLEET,
            ),
            note="Best standalone exp; DSR WEAK on proxy levels.",
        ),
        SetupSlot(
            setup="DOUBLE_BOTTOM_BASE_QUIET",
            status=PromotionStatus.WATCH_ONLY,
            sizing_tier="base",
            evidence=Evidence(
                exp=9.95, wr=58.3, n=24, dsr_verdict="WEAK",
                oos_sign_stable=False, low_power=False,
                on_real_levels=False, source=_FLEET,
            ),
            note="OOS sign UNSTABLE standalone — needs a real-level re-test.",
        ),
        SetupSlot(
            setup="BULLISH_RECLAIM_RIDE_THE_RIBBON",
            status=PromotionStatus.WATCH_ONLY,
            sizing_tier="base",
            evidence=Evidence(
                exp=10.33, wr=54.9, n=82, dsr_verdict="WEAK",
                oos_sign_stable=False, low_power=False,
                on_real_levels=False,
                source="analysis/recommendations/bullish-reclaim-standalone.json",
            ),
            note="Positive slice is low-VIX (14-16) only; needs a low-VIX-or-falling "
                 "gate + J's own logged bullish winners before promotion.",
        ),
        SetupSlot(
            setup="VWAP_TREND_PULLBACK",
            status=PromotionStatus.WATCH_ONLY,
            sizing_tier="base",
            evidence=Evidence(
                exp=45.88, wr=42.4, n=92, dsr_verdict="PASS",
                oos_sign_stable=True, low_power=False,
                on_real_levels=False, source=_DISCOVERY,
            ),
            note="H4 — pullback to session VWAP in the trend direction (here the "
                 "bull/call side). Data-discovered survivor: standalone real-fills "
                 "PASS, OOS sign-stable, DSR PASS, robust to drop-top-5, both "
                 "directions positive. ATM exp shown (both-side blend); ITM1 "
                 "+$63/trade. Proxy levels. 2026-06-19 regime-gate research: NO clean "
                 "causal gate (markdown/research/VWAP-TREND-PULLBACK-REGIME-GATE-2026-06-19.md); "
                 "exit-config caveat (scorecard -0.08 vs live chart-stop-only +$14/t). "
                 "Stays dormant.",
        ),
        SetupSlot(
            setup="GAP_AND_GO",
            status=PromotionStatus.WATCH_ONLY,
            sizing_tier="base",
            evidence=Evidence(
                exp=35.24, wr=42.9, n=84, dsr_verdict="PASS",
                oos_sign_stable=True, low_power=False,
                on_real_levels=False, source=_DISCOVERY,
            ),
            note="H2b — opening-gap continuation after a confirming first bar (bull/call "
                 "side). Data-discovered survivor: 5/6 quarters positive, OOS sign-stable, "
                 "DSR PASS, both directions positive. ATM exp shown (both-side blend); "
                 "ITM1 +$40/trade. Proxy levels.",
        ),
    ),
    Regime.HIGH_VOL: (
        SetupSlot(
            setup="NAMED_LEVEL_SECOND_TEST",
            status=PromotionStatus.WATCH_ONLY,
            sizing_tier="base",
            evidence=Evidence(
                exp=22.26, wr=66.7, n=144, dsr_verdict="WEAK",
                oos_sign_stable=False, low_power=False,
                on_real_levels=False, source=_FLEET,
            ),
            note="Strongest in-regime cell of the fleet; DSR WEAK on proxy levels.",
        ),
        SetupSlot(
            setup="DOUBLE_BOTTOM_MORNING_LOW_VOL",
            status=PromotionStatus.WATCH_ONLY,
            sizing_tier="base",
            evidence=Evidence(
                exp=80.88, wr=80.0, n=5, dsr_verdict="WEAK",
                oos_sign_stable=None, low_power=True,
                on_real_levels=False, source=_FLEET,
            ),
            note="low_power (n=5) — do NOT over-read (C24). Re-test on real levels.",
        ),
    ),
    Regime.RANGE_PIN: (),   # intentionally empty — see header note (bounce family low_power)
    Regime.NEUTRAL: (),     # no edge-aligned setup => abstain (correct, not a gap)
}
