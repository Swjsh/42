"""THE FUNNEL — how the lane picks what to trade out of ~72 names without drowning in noise.

J's question, 2026-08-19: *"how does it kinda pick what it's gonna trade? How does it filter out
the noise of seventy different names?"*

THE ANSWER IS A FUNNEL WITH A HARD CAP AT EVERY STAGE, and the cap is the point. The SPY engine
never had this problem — it watches ONE name, so "what do I look at" was never a question. With
72 names it is the whole question, and getting it wrong has two distinct failure modes this shop
has already paid for:

  * TOO LOOSE -> 72 signals a day, no attention anywhere, and the account tries to hold ten
    correlated positions. This is the "shotgun, not sniper" failure J named in 2026-07-09.
  * TOO TIGHT -> stack enough AND-gates and NOTHING ever passes. That is L199: "6 arms, 700
    signals, 0 trades." The v1 weekly lane died of a related disease.

So the funnel narrows by RANKING, not by adding gates. Each stage keeps the best N rather than
filtering on a threshold that might match nothing. A ranked cut always yields something to look
at; a threshold cut can silently yield zero.

    STAGE 0  UNIVERSE          ~72 names        params.universe (static membership list)
    STAGE 1  LIQUIDITY         keep ~top 40     tradeable at all, measured LIVE not from a list
    STAGE 2  ATTENTION         keep top 15      where is anything actually happening today
    STAGE 3  SETUP             keep top 5       which of those have a chart setup worth scoring
    STAGE 4  ADMISSION         keep <= 3        risk/correlation/sector caps decide the final set

Only stage 4's survivors are scored by the full engine and considered for entry. Stages 1-3 are
CHEAP (bars + scanner reads); the expensive per-symbol work happens on 5 names, not 72.

WHY ATTENTION (stage 2) IS RANKED ON RELATIVE VOLUME, NOT % MOVE:
relative volume normalizes against each name's OWN baseline, so a 9.8x reading is comparable
across NVDA and a $18 stock. Raw % change is not — a 5% day means something completely different
for SOFI than for JNJ. Measured 2026-08-19: the scanner stack put MRNA at 9.8x RVOL and all four
scanners fired on it, on the day its $120 call ran open-to-high +1,121%.

WHAT THIS FUNNEL DOES NOT DO: it does not predict. Every field is a backward-looking measured
fact. Ranking by attention says "something is happening here," never "this will continue." The
entry decision remains the engine's, and the engine's blockers still veto.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]

# Stage caps. Deliberately CONSTANTS, not params: these bound ATTENTION, which is a property of
# the operator (and of a $9.6K account), not a strategy knob to be optimized. Widening them is a
# doctrine decision, not a tuning pass.
KEEP_AFTER_LIQUIDITY = 40
KEEP_AFTER_ATTENTION = 15
KEEP_AFTER_SETUP = 5


class WatchlistError(RuntimeError):
    """Fail loud: an empty watchlist must be distinguishable from a broken funnel."""


@dataclass
class Candidate:
    symbol: str
    stage: str = "universe"
    # Stage-1 liquidity facts (measured live)
    spread_pct: Optional[float] = None
    open_interest: Optional[int] = None
    tradeable: Optional[bool] = None
    # Stage-2 attention facts
    rel_volume: Optional[float] = None
    pct_change: Optional[float] = None
    dollar_volume: Optional[float] = None
    scanner_hits: int = 0
    news_headline: Optional[str] = None
    news_class: Optional[str] = None
    attention_score: Optional[float] = None
    # Stage-3 setup facts
    setup_score: Optional[int] = None
    setup_side: Optional[str] = None
    # Provenance
    reasons: list[str] = field(default_factory=list)

    def as_row(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d["reasons"] = list(self.reasons)
        return d


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return f if f == f else None  # NaN check
    except (TypeError, ValueError):
        return None


def stage1_liquidity(cands: Sequence[Candidate], keep: int = KEEP_AFTER_LIQUIDITY
                     ) -> list[Candidate]:
    """Keep the names that are TRADEABLE AT ALL, ranked tightest-spread first.

    Measured live rather than inherited from a static screen: a name that is untradeable on a
    normal day can be deeply liquid on a catalyst day (MRNA: 1 contract Monday, 30,314
    Wednesday). Names with no measurement yet are kept but ranked last -- absence of data is
    not evidence of illiquidity, and dropping them here would silently shrink the universe.
    """
    scored, unmeasured = [], []
    for c in cands:
        if c.tradeable is False:
            c.reasons.append("stage1: failed live liquidity gate")
            continue
        s = _num(c.spread_pct)
        (scored if s is not None else unmeasured).append(c)
    scored.sort(key=lambda c: _num(c.spread_pct) or 999.0)
    out = (scored + unmeasured)[:keep]
    for c in out:
        c.stage = "liquidity"
    return out


def attention_score(c: Candidate) -> float:
    """Rank 'where is something actually happening', normalized per name.

    RELATIVE VOLUME dominates deliberately (see module docstring): it is the only field here
    that is comparable across a $18 stock and a $700 ETF. Absolute % change is a secondary
    tiebreak and scanner corroboration a small bonus -- four scanners agreeing is weak evidence
    on its own, but it is not nothing.
    """
    rv = _num(c.rel_volume) or 1.0
    pct = abs(_num(c.pct_change) or 0.0)
    hits = min(int(c.scanner_hits or 0), 4)
    # rel-volume is the signal; cap its contribution so one absurd print cannot dominate.
    rv_term = min(rv, 20.0) * 1.0
    pct_term = min(pct, 25.0) * 0.20
    hit_term = hits * 0.5
    return round(rv_term + pct_term + hit_term, 4)


def stage2_attention(cands: Sequence[Candidate], keep: int = KEEP_AFTER_ATTENTION
                     ) -> list[Candidate]:
    """Keep the top-N by attention. RANKED, never thresholded -- a threshold can match nothing
    on a quiet day, and a quiet day should still produce a watchlist to look at."""
    for c in cands:
        c.attention_score = attention_score(c)
    ranked = sorted(cands, key=lambda c: c.attention_score or 0.0, reverse=True)
    out = list(ranked[:keep])
    for c in out:
        c.stage = "attention"
        if (_num(c.rel_volume) or 0) >= 3.0:
            c.reasons.append(f"stage2: rel_volume {c.rel_volume:.1f}x")
    return out


def stage3_setup(cands: Sequence[Candidate], keep: int = KEEP_AFTER_SETUP) -> list[Candidate]:
    """Keep the top-N by the engine's own setup score. Names with no score yet rank last."""
    ranked = sorted(cands, key=lambda c: (c.setup_score if c.setup_score is not None else -1),
                    reverse=True)
    out = list(ranked[:keep])
    for c in out:
        c.stage = "setup"
    return out


def build_watchlist(
    universe: Sequence[str],
    *,
    liquidity: Optional[dict[str, dict]] = None,
    attention: Optional[dict[str, dict]] = None,
    setups: Optional[dict[str, dict]] = None,
) -> tuple[list[Candidate], dict[str, int]]:
    """Run the funnel. Returns (survivors, stage_counts).

    Each input maps symbol -> measured facts; any may be None (that stage then passes through
    unmeasured, ranked last rather than dropped). The stage_counts dict IS the participation
    cascade for the funnel: it makes 'why is the watchlist empty' answerable in one read.
    """
    if not universe:
        raise WatchlistError("empty universe handed to the funnel — refusing to build nothing")

    cands = [Candidate(symbol=s.upper()) for s in dict.fromkeys(u.upper() for u in universe)]
    counts = {"universe": len(cands)}

    for c in cands:
        f = (liquidity or {}).get(c.symbol) or {}
        c.spread_pct = _num(f.get("spread_pct"))
        c.open_interest = f.get("open_interest")
        c.tradeable = f.get("tradeable")
    cands = stage1_liquidity(cands)
    counts["liquidity"] = len(cands)

    for c in cands:
        a = (attention or {}).get(c.symbol) or {}
        c.rel_volume = _num(a.get("rel_volume"))
        c.pct_change = _num(a.get("pct_change"))
        c.dollar_volume = _num(a.get("dollar_volume"))
        c.scanner_hits = int(a.get("scanner_hits") or 0)
        c.news_headline = a.get("headline")
        c.news_class = a.get("news_class")
    cands = stage2_attention(cands)
    counts["attention"] = len(cands)

    for c in cands:
        s = (setups or {}).get(c.symbol) or {}
        c.setup_score = s.get("score")
        c.setup_side = s.get("side")
    cands = stage3_setup(cands)
    counts["setup"] = len(cands)

    return cands, counts


def write_watchlist(cands: Sequence[Candidate], counts: dict[str, int], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "stage_counts": counts,
        "caps": {"liquidity": KEEP_AFTER_LIQUIDITY, "attention": KEEP_AFTER_ATTENTION,
                 "setup": KEEP_AFTER_SETUP},
        "_reading": (
            "stage_counts IS the funnel's participation cascade. If 'setup' is 0 on many "
            "consecutive sessions the funnel is too tight (L199); if the engine is entering "
            "many correlated names it is too loose. Both are visible here in one read."
        ),
        "candidates": [c.as_row() for c in cands],
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
