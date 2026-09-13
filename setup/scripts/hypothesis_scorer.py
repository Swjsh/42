#!/usr/bin/env python
"""hypothesis_scorer.py -- the deterministic verdict engine that closes the Station idea loop
(GOAL-GAMMA-STATION-2026-09-13 item (12), Slice 2 of the approved plan
`dapper-cuddling-peacock.md`).

THE GAP THIS CLOSES: the Station loop (station_loop.py) proposes idea-cards every ~30 minutes,
J can click Test on one, and its status flips to "testing" -- and then NOTHING happens. No
consumer ever turns "testing" into "supported"/"refuted". This module is that consumer: pure
Python over rows that already exist (analysis/autopsies/*.jsonl, written nightly by
trade_autopsy.py, which already replays every closed fill through the live exit core with real
1-min OPRA bars). NO LLM. NO new replayer. NO new scheduled task.

FOUR SPEC TYPES a card's `test_spec` can name (see automation/prompts/station.md for the
model-facing description):
  size_cap           {cap, strategy?, arm?}      -- linear-fill qty cap counterfactual
  exit_shape         {shape, strategy?, arm?}    -- reads an existing counterfactuals.* column
  metric_correlation {x, y?, group_by?, strategy?, arm?, method?} -- Pearson/Spearman + a
                                                     dedicated permutation p-value
  time_stop_minutes  {minutes, strategy?}        -- ALWAYS spec_error today; autopsy rows carry
                                                     no per-fill time series, and wiring one
                                                     needs a kwarg on exit_shape_parity_study.
                                                     replay_position() (backtest/tools/, outside
                                                     this build's ownership) -- day 2.

PRE/POST-REGISTRATION (checkpoint_packet.py's ~line-834 convention, reused here): every verdict
reports TWO windows -- rows strictly BEFORE the card's own `ts_et` (in-sample/exploratory, the
model could have seen them) and rows strictly AFTER (post-registration/confirmatory). A verdict
only ever flips to "supported"/"refuted" once post-registration n >= min_n (default 10, i.e.
config key `scorer_min_n` on the Station's config.json, read by station_loop.py); short of that
it stays "pending" with both windows shown honestly -- never a guess dressed as a verdict.

WHY NOT entry_quality_ledger.perm_p(): that function's signature (events/blocked_ids/eligible/
delta_obs/rng) is a within-day block-vs-keep permutation specific to the admissibility
battery's binary "did we block this trade" framing -- it needs `date_et`/`pnl` keys and a
selection-of-a-subset structure that none of the four spec types above actually have (size_cap
and exit_shape apply a deterministic transform to EVERY matched row, not a subset selection;
metric_correlation is a continuous x/y relationship). Force-adapting it would have been exactly
the invented-API risk the judgment guards forbid. bh_qvalues() IS generic (a dict of p-values ->
BH-adjusted q-values) and is imported and used for real, batched across every metric_correlation
card scored together in one --all-testing run (see rescore_board).

OUTPUTS: analysis/recommendations/station-verdicts.jsonl (append-only, one row per scored
card per fire: card_id, spec, result), verdict fields written back onto the card in
automation/state/station/ideas-board.json, and -- only when a card carries a `mechanism_ref` and
its verdict lands as supported/refuted -- one row folded into
automation/state/hypotheses-settled.json's existing `settled` list (trade_autopsy.py's own
detector already reads that file and will stop re-emitting a mechanism Station just settled).

Never touches the trading path. Never calls a model. Fail-open throughout: one bad card can
never crash a whole rescore (mirrors checkpoint_packet.py's score_row fail-open dispatcher).

CLI:
    python setup/scripts/hypothesis_scorer.py --card <id> [--dry-run]
        [--spec-type TYPE --spec-param KEY=VALUE ...]
    python setup/scripts/hypothesis_scorer.py --all-testing [--dry-run]
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parents[2]
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from et_clock import et_now  # noqa: E402
import station_board  # noqa: E402 -- read_json_or_none/atomic_write_text/append_jsonl/load_board

AUTOPSY_DIR = REPO / "analysis" / "autopsies"
IDEAS_BOARD_PATH = REPO / "automation" / "state" / "station" / "ideas-board.json"
VERDICTS_LEDGER_PATH = REPO / "analysis" / "recommendations" / "station-verdicts.jsonl"
SETTLED_HYP_PATH = REPO / "automation" / "state" / "hypotheses-settled.json"

DEFAULT_MIN_N = 10
MAX_FIRES_WITHOUT_SPEC = 3   # station.md's pending-note path gets this many fires before spec_error
KNOWN_SPEC_TYPES = ("size_cap", "exit_shape", "metric_correlation", "time_stop_minutes")

# trade_autopsy.DIAGNOSTIC_COUNTERFACTUALS, duplicated as a small stable literal (not imported --
# see module docstring on why this file avoids a trade_autopsy.py dependency): hold_to_time is a
# near-stopless, unbounded-upside ORACLE probe that wins on trend days by construction and must
# never read as a shippable exit_shape verdict, only a diagnostic one.
_DIAGNOSTIC_SHAPES = frozenset({"hold_to_time"})

_CORR_PERM_DRAWS = 4000
_CORR_PERM_SEED = 20260913
_CORR_P_THRESHOLD = 0.10   # matches entry_quality_ledger.BH_Q_BAR's convention for this tool family


# --------------------------------------------------------------------------- #
# Time: pre/post-registration split
# --------------------------------------------------------------------------- #

def _parse_card_cutoff_et(ts_et: str) -> Optional[datetime]:
    """Card ts_et is always written as 'YYYY-MM-DD HH:MM:SS ET' (station_board.merge_new_cards).
    None on any other shape -- never guessed."""
    s = (ts_et or "").strip()
    if s.endswith("ET"):
        s = s[:-2].strip()
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _row_et_datetime(row: dict) -> Optional[datetime]:
    """A row's own ET instant: prefer entry_ts_utc (precise, converted via et_clock's
    DST-aware offset -- never a hardcoded -4/-5), falling back to its ET calendar `date` at
    midnight when entry_ts_utc is missing/malformed. None when neither is usable."""
    ts_utc = row.get("entry_ts_utc")
    if ts_utc:
        try:
            dt_utc = datetime.fromisoformat(str(ts_utc).replace("Z", "+00:00"))
            offset_h = _et_offset_hours_cached(dt_utc)
            return (dt_utc + timedelta(hours=offset_h)).replace(tzinfo=None)
        except (ValueError, TypeError):
            pass
    d = row.get("date")
    if d:
        try:
            return datetime.strptime(str(d), "%Y-%m-%d")
        except ValueError:
            return None
    return None


def _et_offset_hours_cached(dt_utc: datetime) -> int:
    from et_clock import et_offset_hours
    return et_offset_hours(dt_utc)


def _split_pre_post(rows: list, cutoff: datetime) -> tuple:
    """(pre_rows, post_rows) -- strictly before / strictly after `cutoff`. A row with no
    resolvable timestamp is excluded from BOTH windows (never guessed into either)."""
    pre, post = [], []
    for r in rows:
        rdt = _row_et_datetime(r)
        if rdt is None:
            continue
        if rdt < cutoff:
            pre.append(r)
        elif rdt > cutoff:
            post.append(r)
    return pre, post


def _split_pre_post_pairs(pairs: list, cutoff: datetime) -> tuple:
    """Same split as _split_pre_post but over (row, value) tuples (size_cap/exit_shape's
    per-row delta already computed before the split)."""
    pre, post = [], []
    for r, v in pairs:
        rdt = _row_et_datetime(r)
        if rdt is None:
            continue
        if rdt < cutoff:
            pre.append((r, v))
        elif rdt > cutoff:
            post.append((r, v))
    return pre, post


# --------------------------------------------------------------------------- #
# Small pure helpers
# --------------------------------------------------------------------------- #

def _matches_filters(row: dict, *, strategy: Optional[str] = None, arm: Optional[str] = None) -> bool:
    """strategy: case-insensitive substring match (strategy names are long, e.g.
    BULLISH_RECLAIM_RIDE_THE_RIBBON, and a card may reference a shorter phrase).
    arm: exact case-insensitive match (arm tokens are short and must not partially collide,
    e.g. 'safe-2' vs a hypothetical 'safe-2x')."""
    if strategy and strategy.lower() not in str(row.get("strategy") or "").lower():
        return False
    if arm and str(row.get("arm") or "").lower() != str(arm).lower():
        return False
    return True


def _qty_arm_confound_note(rows: list, cap: float) -> Optional[str]:
    """size_cap's own confound check (station_facts.gather_autopsy_aggregates does the same
    check book-wide for the facts block; this is the per-card, per-filter version so a
    --card dry-run surfaces it directly in `detail`/`assumptions` without needing the facts
    block at all)."""
    above = {r.get("arm") for r in rows
             if isinstance(r.get("qty"), (int, float)) and r["qty"] > cap and r.get("arm")}
    at_or_below = {r.get("arm") for r in rows
                   if isinstance(r.get("qty"), (int, float)) and r["qty"] <= cap and r.get("arm")}
    if above and at_or_below and above.isdisjoint(at_or_below):
        return (f"CONFOUND: every fill with qty > {cap:g} belongs to arm(s) {sorted(above)} and "
                f"every fill with qty <= {cap:g} belongs to a disjoint arm(s) {sorted(at_or_below)} "
                "-- this counterfactual cannot separate a SIZE effect from an ARM/strategy-tier effect.")
    return None


def _verdict_from_effect(n_post: int, min_n: int, effect_post: Optional[float],
                         effect_pre: Optional[float], *, positive_means: str) -> tuple:
    """Shared supported/refuted/pending logic for size_cap and exit_shape (both are a sum of
    a deterministic per-row delta -- 'positive = the counterfactual beat what actually
    happened')."""
    if n_post < min_n:
        return "pending", (f"n_post={n_post} < min_n={min_n} -- not enough post-registration "
                           f"fills yet to confirm or kill this. In-sample (pre, exploratory) "
                           f"effect=${effect_pre if effect_pre is not None else 'n/a'}, post so "
                           f"far=${effect_post if effect_post is not None else 'n/a'}. Positive "
                           f"means {positive_means}.")
    if effect_post is not None and effect_post > 0:
        return "supported", (f"post-registration n={n_post}, effect=${effect_post:+.2f} "
                             f"(positive = {positive_means}). In-sample (exploratory) effect was "
                             f"${effect_pre if effect_pre is not None else 'n/a'}.")
    shown = effect_post if effect_post is not None else 0.0
    return "refuted", (f"post-registration n={n_post}, effect=${shown:+.2f} did not confirm the "
                       f"hypothesis (positive would mean {positive_means}). In-sample "
                       f"(exploratory) effect was ${effect_pre if effect_pre is not None else 'n/a'}.")


# --------------------------------------------------------------------------- #
# Correlation primitives (stdlib only -- no scipy/numpy in this repo's runtime)
# --------------------------------------------------------------------------- #

def _pearson(xs: list, ys: list) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs)
    dy = sum((y - my) ** 2 for y in ys)
    if dx <= 0 or dy <= 0:
        return None
    return num / (dx * dy) ** 0.5


def _rank(values: list) -> list:
    """Average ranks (1-based), ties split evenly -- the standard Spearman convention."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def _spearman(xs: list, ys: list) -> Optional[float]:
    if len(xs) < 2:
        return None
    return _pearson(_rank(xs), _rank(ys))


def _perm_p_correlation(xs: list, ys: list, observed: float, corr_fn: Callable, rng: random.Random) -> float:
    """Two-sided permutation p-value for a correlation statistic: shuffle y against a fixed
    x order `_CORR_PERM_DRAWS` times and report the fraction of shuffles whose |r| >= |observed|.
    A DEDICATED correlation-shuffle test -- see module docstring for why entry_quality_ledger.
    perm_p() was not force-adapted here."""
    if len(xs) < 3 or observed is None:
        return 1.0
    shuffled = list(ys)
    hits = 0
    abs_obs = abs(observed)
    for _ in range(_CORR_PERM_DRAWS):
        rng.shuffle(shuffled)
        r = corr_fn(xs, shuffled)
        if r is not None and abs(r) >= abs_obs - 1e-12:
            hits += 1
    return hits / _CORR_PERM_DRAWS


# --------------------------------------------------------------------------- #
# Spec handlers -- each returns {verdict, n_pre, n_post, effect_pre, effect_post, detail,
# assumptions} (score_card merges this over a common base and stamps scored_at_et).
# --------------------------------------------------------------------------- #

def _score_size_cap(params: dict, rows: list, cutoff: datetime, min_n: int) -> dict:
    cap = params.get("cap")
    if not isinstance(cap, (int, float)) or isinstance(cap, bool) or cap <= 0:
        return {"verdict": "spec_error", "n_pre": 0, "n_post": 0, "effect_pre": None,
                "effect_post": None, "assumptions": [],
                "detail": f"size_cap requires a positive numeric 'cap', got {cap!r}"}
    cap = float(cap)
    matched = [r for r in rows if _matches_filters(r, strategy=params.get("strategy"), arm=params.get("arm"))]

    pairs, skipped = [], 0
    for r in matched:
        qty, actual = r.get("qty"), r.get("actual_pnl")
        if (not isinstance(qty, (int, float)) or isinstance(qty, bool) or qty <= 0
                or not isinstance(actual, (int, float)) or isinstance(actual, bool)):
            skipped += 1
            continue
        cf_pnl = actual * min(qty, cap) / qty
        pairs.append((r, round(cf_pnl - actual, 2)))

    pre, post = _split_pre_post_pairs(pairs, cutoff)
    effect_pre = round(sum(d for _, d in pre), 2) if pre else None
    effect_post = round(sum(d for _, d in post), 2) if post else None

    assumptions = [
        "linear-fill assumption: counterfactual pnl = actual_pnl * min(qty, cap) / qty (scales "
        "P&L proportionally with a smaller fill; ignores any spread/liquidity difference a "
        "smaller order might actually have gotten).",
        f"{len(matched)} row(s) matched the strategy/arm filter; {skipped} skipped "
        "(missing/non-positive qty or non-numeric actual_pnl).",
    ]
    confound = _qty_arm_confound_note(matched, cap)
    if confound:
        assumptions.append(confound)

    verdict, detail = _verdict_from_effect(
        len(post), min_n, effect_post, effect_pre,
        positive_means="capping at this qty would have reduced the net loss / grown the net gain")
    return {"verdict": verdict, "n_pre": len(pre), "n_post": len(post),
            "effect_pre": effect_pre, "effect_post": effect_post,
            "detail": detail, "assumptions": assumptions}


def _score_exit_shape(params: dict, rows: list, cutoff: datetime, min_n: int) -> dict:
    shape = params.get("shape")
    if not isinstance(shape, str) or not shape:
        return {"verdict": "spec_error", "n_pre": 0, "n_post": 0, "effect_pre": None,
                "effect_post": None, "assumptions": [],
                "detail": "exit_shape requires a string 'shape' naming a recorded counterfactual column"}
    matched = [r for r in rows if _matches_filters(r, strategy=params.get("strategy"), arm=params.get("arm"))]
    known_shapes = sorted({k for r in matched for k in (r.get("counterfactuals") or {})})

    pairs = []
    for r in matched:
        cf = (r.get("counterfactuals") or {}).get(shape)
        actual = r.get("actual_pnl")
        if cf is None or not isinstance(actual, (int, float)) or isinstance(actual, bool):
            continue
        pairs.append((r, round(cf - actual, 2)))

    if not pairs:
        return {"verdict": "spec_error", "n_pre": 0, "n_post": 0, "effect_pre": None,
                "effect_post": None, "assumptions": [],
                "detail": (f"shape {shape!r} not present on any of {len(matched)} matched row(s) "
                          f"-- known shapes in this data: {known_shapes or 'none'}")}

    pre, post = _split_pre_post_pairs(pairs, cutoff)
    effect_pre = round(sum(d for _, d in pre), 2) if pre else None
    effect_post = round(sum(d for _, d in post), 2) if post else None

    assumptions = [f"{len(pairs)} of {len(matched)} matched row(s) carried a '{shape}' counterfactual."]
    if shape in _DIAGNOSTIC_SHAPES:
        assumptions.append(
            f"'{shape}' is an ORACLE/diagnostic-only counterfactual in trade_autopsy.py "
            "(near-stopless, unbounded upside -- wins on trend days by construction). A "
            "'supported' verdict here is a diagnostic finding about theta-ride, never a "
            "shippable exit shape on its own.")

    verdict, detail = _verdict_from_effect(
        len(post), min_n, effect_post, effect_pre,
        positive_means=f"the '{shape}' shape would have beaten the shipped exit")
    return {"verdict": verdict, "n_pre": len(pre), "n_post": len(post),
            "effect_pre": effect_pre, "effect_post": effect_post,
            "detail": detail, "assumptions": assumptions}


def _score_metric_correlation(params: dict, rows: list, cutoff: datetime, min_n: int) -> dict:
    x_field = params.get("x")
    y_field = params.get("y") or "actual_pnl"
    method = str(params.get("method") or "pearson").lower()
    if not isinstance(x_field, str) or not x_field:
        return {"verdict": "spec_error", "n_pre": 0, "n_post": 0, "effect_pre": None,
                "effect_post": None, "assumptions": [],
                "detail": "metric_correlation requires a string 'x' field name"}
    if method not in ("pearson", "spearman"):
        return {"verdict": "spec_error", "n_pre": 0, "n_post": 0, "effect_pre": None,
                "effect_post": None, "assumptions": [],
                "detail": f"metric_correlation.method must be 'pearson' or 'spearman', got {method!r}"}

    matched = [r for r in rows if _matches_filters(r, strategy=params.get("strategy"), arm=params.get("arm"))]
    usable = [r for r in matched
              if isinstance(r.get(x_field), (int, float)) and not isinstance(r.get(x_field), bool)
              and isinstance(r.get(y_field), (int, float)) and not isinstance(r.get(y_field), bool)]
    if len(usable) < 4:
        return {"verdict": "spec_error", "n_pre": 0, "n_post": 0, "effect_pre": None,
                "effect_post": None, "assumptions": [],
                "detail": (f"only {len(usable)} row(s) carry numeric '{x_field}' and '{y_field}' "
                          "after filters -- too few to correlate (need >= 4 total, top-level "
                          "fields only, no dot-path traversal)")}

    pre_rows, post_rows = _split_pre_post(usable, cutoff)
    corr_fn = _spearman if method == "spearman" else _pearson
    effect_pre = corr_fn([r[x_field] for r in pre_rows], [r[y_field] for r in pre_rows]) if len(pre_rows) >= 3 else None
    effect_post = corr_fn([r[x_field] for r in post_rows], [r[y_field] for r in post_rows]) if len(post_rows) >= 3 else None
    if effect_pre is not None:
        effect_pre = round(effect_pre, 4)
    if effect_post is not None:
        effect_post = round(effect_post, 4)

    p_post = None
    if effect_post is not None:
        p_post = _perm_p_correlation([r[x_field] for r in post_rows], [r[y_field] for r in post_rows],
                                     effect_post, corr_fn, random.Random(_CORR_PERM_SEED))

    assumptions = [f"{method} correlation of {x_field!r} vs {y_field!r} over {len(usable)} usable "
                  f"row(s) (numeric on both fields, after strategy/arm filters)."]
    group_by = params.get("group_by")
    if group_by:
        groups = collections.defaultdict(list)
        for r in usable:
            groups[str(r.get(group_by))].append(r)
        per_group = {g: round(corr_fn([r[x_field] for r in rs], [r[y_field] for r in rs]), 3)
                    for g, rs in groups.items() if len(rs) >= 3
                    and corr_fn([r[x_field] for r in rs], [r[y_field] for r in rs]) is not None}
        if len(groups) > 1:
            assumptions.append(f"grouped by {group_by!r}: {per_group} -- correlation-vs-causation "
                              "caveat: a group_by value that itself correlates with x is a confound "
                              "this reports but does not adjudicate on its own (see station_facts."
                              "gather_autopsy_aggregates's confound flag for the qty/arm case).")

    if p_post is not None:
        assumptions.append(f"permutation p-value = {_CORR_PERM_DRAWS} label-shuffles of the "
                          "post-registration window only (a dedicated correlation-shuffle test, "
                          "not entry_quality_ledger.perm_p() -- see module docstring); a BH "
                          "q-value (entry_quality_ledger.bh_qvalues) is attached only when "
                          "--all-testing scores multiple metric_correlation cards together.")

    n_pre, n_post = len(pre_rows), len(post_rows)
    if n_post < min_n or effect_post is None:
        verdict = "pending"
        detail = (f"n_post={n_post} < min_n={min_n} (or too few post rows to correlate) -- "
                 f"in-sample (pre) {method} r={effect_pre}, post so far r={effect_post}.")
    else:
        sign_pre = None if effect_pre is None else (1 if effect_pre > 0 else (-1 if effect_pre < 0 else 0))
        sign_post = 1 if effect_post > 0 else (-1 if effect_post < 0 else 0)
        significant = p_post is not None and p_post <= _CORR_P_THRESHOLD
        sign_consistent = sign_pre is None or sign_pre == 0 or sign_pre == sign_post
        if significant and sign_consistent and sign_post != 0:
            verdict = "supported"
        else:
            verdict = "refuted"
        detail = (f"post-registration n={n_post}, {method} r={effect_post:+.3f}, perm "
                 f"p={p_post:.4f} (threshold {_CORR_P_THRESHOLD}); in-sample r={effect_pre}; "
                 f"sign_consistent={sign_consistent}.")

    return {"verdict": verdict, "n_pre": n_pre, "n_post": n_post, "effect_pre": effect_pre,
            "effect_post": effect_post, "detail": detail, "assumptions": assumptions,
            "p_value": p_post}


def _score_time_stop_minutes(params: dict, rows: list, cutoff: datetime, min_n: int) -> dict:
    minutes = params.get("minutes")
    return {
        "verdict": "spec_error", "n_pre": 0, "n_post": 0, "effect_pre": None, "effect_post": None,
        "assumptions": [
            "analysis/autopsies/*.jsonl rows carry only the fixed COUNTERFACTUALS shapes "
            "(wide_stop_-50 / no_stop_ride / hold_to_time) plus entry/exit summary fields -- no "
            "per-fill intraday time series survives into the autopsy row.",
        ],
        "detail": (f"time_stop_minutes (minutes={minutes!r}) needs a time_stop_et kwarg on "
                  "exit_shape_parity_study.replay_position() to replay a fixed-duration exit -- "
                  "that function lives in backtest/tools/, outside this build's ownership "
                  "(GOAL-GAMMA-STATION item 12). Deferred to day 2 per the approved plan; this "
                  "is the honest 'not yet expressible' answer, not a bug."),
    }


_SPEC_HANDLERS: dict = {
    "size_cap": _score_size_cap,
    "exit_shape": _score_exit_shape,
    "metric_correlation": _score_metric_correlation,
    "time_stop_minutes": _score_time_stop_minutes,
}


def _valid_spec_shape(spec) -> bool:
    return (isinstance(spec, dict) and spec.get("type") in KNOWN_SPEC_TYPES
            and isinstance(spec.get("params"), dict))


# --------------------------------------------------------------------------- #
# score_card -- the per-card dispatcher (never raises)
# --------------------------------------------------------------------------- #

def score_card(card: dict, rows: list, *, now_et: datetime, min_n: int = DEFAULT_MIN_N) -> dict:
    """Scores ONE card against `rows` (already-loaded analysis/autopsies/*.jsonl rows -- see
    load_autopsy_rows). Never raises: any internal failure degrades to a 'spec_error' verdict
    (mirrors checkpoint_packet.py's score_row fail-open dispatcher) so one bad card can never
    crash a whole --all-testing rescore."""
    scored_at = now_et.strftime("%Y-%m-%d %H:%M:%S ET")
    base = {"n_pre": 0, "n_post": 0, "effect_pre": None, "effect_post": None,
            "assumptions": [], "scored_at_et": scored_at, "detail": ""}

    spec = card.get("test_spec")
    if not _valid_spec_shape(spec):
        return {**base, "verdict": "spec_error",
               "detail": "card carries no valid test_spec {type, params}"}

    cutoff = _parse_card_cutoff_et(str(card.get("ts_et", "")))
    if cutoff is None:
        return {**base, "verdict": "spec_error",
               "detail": f"card ts_et {card.get('ts_et')!r} is not parseable as "
                         "'YYYY-MM-DD HH:MM:SS ET'"}

    handler = _SPEC_HANDLERS.get(spec["type"])
    if handler is None:   # unreachable given _valid_spec_shape's check; kept for defense in depth
        return {**base, "verdict": "spec_error", "detail": f"no handler registered for {spec['type']!r}"}

    try:
        result = handler(spec["params"], rows, cutoff, min_n)
    except Exception as exc:  # noqa: BLE001 -- one bad card must never crash a batch rescore
        return {**base, "verdict": "spec_error",
               "detail": f"scorer raised {exc.__class__.__name__}: {exc}"}

    out = dict(base)
    out.update(result)
    out["scored_at_et"] = scored_at
    return out


# --------------------------------------------------------------------------- #
# I/O: autopsy rows
# --------------------------------------------------------------------------- #

def load_autopsy_rows(root: Path = AUTOPSY_DIR) -> list:
    """Every row in analysis/autopsies/*.jsonl (SPY engine autopsies only -- the twin's
    mechanism-only rows live in analysis/autopsies/twin/, a subdirectory this non-recursive
    glob does not descend into, exactly like trade_autopsy.load_recent_rows()). Malformed
    lines are skipped and counted, never raised -- fail-open, matches this whole tool family."""
    rows: list = []
    n_files = n_bad_lines = 0
    if root.exists():
        for f in sorted(root.glob("*.jsonl")):
            n_files += 1
            try:
                text = f.read_text(encoding="utf-8-sig")
            except OSError as exc:
                print(f"[hypothesis_scorer] WARN unreadable {f}: {exc}", file=sys.stderr)
                continue
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    n_bad_lines += 1
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    print(f"[hypothesis_scorer] loaded {len(rows)} row(s) from {n_files} file(s) under {root} "
          f"({n_bad_lines} malformed line(s) skipped)", file=sys.stderr)
    return rows


# --------------------------------------------------------------------------- #
# hypotheses-settled.json -- Station's own writer (trade_autopsy.py's detector is the other,
# older writer; both share the same file/schema, never the same code path)
# --------------------------------------------------------------------------- #

def _load_settled_doc(path: Path) -> dict:
    doc = station_board.read_json_or_none(path)
    if not isinstance(doc, dict) or not isinstance(doc.get("settled"), list):
        return {
            "schema_version": 1,
            "purpose": ("Autopsy hypothesis mechanisms with a FILED verdict. trade_autopsy.py's "
                       "detector reads this and stops re-emitting them; Station cards land here "
                       "too via hypothesis_scorer.settle_mechanism() once a card's post-"
                       "registration verdict lands with a mechanism_ref."),
            "how_to_unsettle": ("Delete the row (re-opens immediately), or set/advance "
                                "`revisit_after` (YYYY-MM-DD) to re-open on a stated date."),
            "settled": [],
        }
    return doc


def settle_mechanism(mechanism_ref: str, verdict: str, card: dict, detail: str, *,
                     path: Path = SETTLED_HYP_PATH, today: Optional[str] = None) -> None:
    """Appends (or updates in place) one settled-mechanism row for a Station card whose
    verdict just landed as supported/refuted with a mechanism_ref. Only additive fields beyond
    the file's existing schema -- trade_autopsy.load_settled_mechanisms()/is_settled() only
    read `mechanism`/`revisit_after` off each row, so this is a safe extension, never a
    breaking rewrite of the shape that reader depends on."""
    today = today or et_now().strftime("%Y-%m-%d")
    doc = _load_settled_doc(path)
    settled = doc["settled"]
    existing = next((r for r in settled if r.get("mechanism") == mechanism_ref), None)
    ids = list(existing.get("card_ids_seen", [])) if existing else []
    cid = card.get("id")
    if cid and cid not in ids:
        ids.append(cid)
    row = {
        "mechanism": mechanism_ref,
        "source": "station",
        "card_ids_seen": ids,
        "settled_on": today,
        "verdict": f"STATION_{verdict.upper()}",
        "verdict_detail": detail,
        "evidence": f"analysis/recommendations/station-verdicts.jsonl (card_id={cid})",
        "revisit_after": (existing or {}).get("revisit_after"),
    }
    if existing:
        settled[settled.index(existing)] = row
    else:
        settled.append(row)
    doc["settled"] = settled
    station_board.atomic_write_text(path, json.dumps(doc, indent=2, ensure_ascii=False))


# --------------------------------------------------------------------------- #
# rescore_board -- the orchestrator (station_board.score_testing_cards delegates here;
# trade_autopsy.py's nightly re-score calls this directly)
# --------------------------------------------------------------------------- #

def _apply_result_to_card(card: dict, result: dict) -> None:
    card["verdict"] = result["verdict"]
    card["verdict_n_pre"] = result["n_pre"]
    card["verdict_n_post"] = result["n_post"]
    card["verdict_ts"] = result["scored_at_et"]
    if result["verdict"] == "spec_error":
        card["spec_error"] = result["detail"]
    else:
        card.pop("spec_error", None)
        card.pop("spec_missing_fires", None)
    if result["verdict"] in ("supported", "refuted"):
        card["status"] = result["verdict"]


def rescore_board(*, board_path: Optional[Path] = None, autopsy_dir: Optional[Path] = None,
                  verdicts_path: Optional[Path] = None, settled_path: Optional[Path] = None,
                  min_n: int = DEFAULT_MIN_N, now_et: Optional[datetime] = None,
                  dry_run: bool = False,
                  max_fires_without_spec: int = MAX_FIRES_WITHOUT_SPEC) -> dict:
    """Scores every 'testing' card on the board. Cheap no-op (zero file writes, one read) when
    there are no testing cards -- the common case, deliberately kept fast so callers can invoke
    this on EVERY Station fire (yielded or not, per the approved plan: 'scoring needs no
    model') without it ever becoming a real cost. dry_run=True computes and returns everything
    but never writes the board/ledger/settled files (used by the CLI's --all-testing --dry-run
    and by tests)."""
    board_path = board_path or IDEAS_BOARD_PATH
    autopsy_dir = autopsy_dir or AUTOPSY_DIR
    verdicts_path = verdicts_path or VERDICTS_LEDGER_PATH
    settled_path = settled_path or SETTLED_HYP_PATH
    now = now_et or et_now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S ET")

    board = station_board.load_board(board_path)
    testing_idxs = [i for i, c in enumerate(board) if isinstance(c, dict) and c.get("status") == "testing"]
    summary = {"testing_cards": len(testing_idxs), "scored": 0, "pending_missing_spec": 0,
              "spec_error": 0, "supported": 0, "refuted": 0, "pending": 0,
              "ledger_rows_written": 0, "dry_run": dry_run}
    if not testing_idxs:
        return summary   # no board/ledger touched at all -- see docstring

    rows = load_autopsy_rows(autopsy_dir)
    ledger_rows: list = []
    correlation_ps: dict = {}
    correlation_row_idx: dict = {}

    for i in testing_idxs:
        card = dict(board[i])
        spec = card.get("test_spec")
        if not _valid_spec_shape(spec):
            n = int(card.get("spec_missing_fires", 0) or 0) + 1
            card["spec_missing_fires"] = n
            summary["pending_missing_spec"] += 1
            if n >= max_fires_without_spec:
                card["spec_error"] = f"no test_spec supplied after {n} fire(s)"
                summary["spec_error"] += 1
            board[i] = card
            continue

        result = score_card(card, rows, now_et=now, min_n=min_n)
        summary["scored"] += 1
        summary[result["verdict"]] = summary.get(result["verdict"], 0) + 1
        _apply_result_to_card(card, result)
        board[i] = card

        ledger_row = {"ts_et": now_str, "card_id": card.get("id"), "spec": spec, "result": result}
        ledger_rows.append(ledger_row)
        if spec.get("type") == "metric_correlation" and result.get("p_value") is not None:
            correlation_ps[card.get("id")] = result["p_value"]
            correlation_row_idx[card.get("id")] = (len(ledger_rows) - 1, i)

        if result["verdict"] in ("supported", "refuted") and not dry_run:
            mech_ref = card.get("mechanism_ref")
            if mech_ref:
                settle_mechanism(mech_ref, result["verdict"], card, result["detail"],
                                 path=settled_path, today=now.strftime("%Y-%m-%d"))

    if len(correlation_ps) > 1:
        from entry_quality_ledger import bh_qvalues   # generic BH correction -- see module docstring
        qs = bh_qvalues(correlation_ps)
        for cid, q in qs.items():
            li, bi = correlation_row_idx[cid]
            ledger_rows[li]["result"]["bh_q"] = q
            board[bi]["verdict_bh_q"] = q

    if not dry_run:
        station_board.write_ideas_board(board_path, board)
        if ledger_rows:
            station_board.append_jsonl(verdicts_path, ledger_rows)
            summary["ledger_rows_written"] = len(ledger_rows)

    return summary


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _coerce_scalar(v: str):
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    return v


def _parse_spec_params(pairs: list) -> dict:
    out = {}
    for p in pairs:
        if "=" not in p:
            raise SystemExit(f"--spec-param must be KEY=VALUE, got {p!r}")
        k, v = p.split("=", 1)
        out[k] = _coerce_scalar(v)
    return out


def main(argv: Optional[list] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(
        description="Score Station idea-board cards against real autopsy data (deterministic, no LLM).")
    ap.add_argument("--card", help="score exactly this card id from ideas-board.json")
    ap.add_argument("--all-testing", action="store_true", help="score every 'testing' card and write results")
    ap.add_argument("--dry-run", action="store_true", help="print result(s) only; never write board/ledger/settled files")
    ap.add_argument("--spec-type", choices=KNOWN_SPEC_TYPES,
                    help="with --card: run this spec type ad hoc (always preview-only, never persisted)")
    ap.add_argument("--spec-param", action="append", default=[], metavar="KEY=VALUE",
                    help="with --spec-type: one test_spec.params entry (repeatable)")
    ap.add_argument("--min-n", type=int, default=DEFAULT_MIN_N)
    ap.add_argument("--board", default=None, help="override ideas-board.json path (tests/manual runs)")
    ap.add_argument("--autopsy-dir", default=None, help="override the autopsies directory (tests/manual runs)")
    args = ap.parse_args(argv)

    board_path = Path(args.board) if args.board else IDEAS_BOARD_PATH
    autopsy_dir = Path(args.autopsy_dir) if args.autopsy_dir else AUTOPSY_DIR

    if args.card:
        board = station_board.load_board(board_path)
        card = next((c for c in board if isinstance(c, dict) and c.get("id") == args.card), None)
        if card is None:
            print(f"[hypothesis_scorer] no card with id {args.card!r} on {board_path}", file=sys.stderr)
            return 1
        if args.spec_type:
            card = {**card, "test_spec": {"type": args.spec_type, "params": _parse_spec_params(args.spec_param)}}
            args.dry_run = True   # ad-hoc CLI overrides always preview -- never silently persisted
            print(f"[hypothesis_scorer] ad-hoc override test_spec={card['test_spec']!r} "
                 "(preview only -- the card's stored test_spec on disk is unchanged)", file=sys.stderr)
        elif not _valid_spec_shape(card.get("test_spec")):
            print(f"[hypothesis_scorer] card {args.card!r} carries no test_spec -- pass "
                 "--spec-type/--spec-param to score it ad hoc, or wait for the model to supply "
                 "one via the pending-notes path.", file=sys.stderr)

        rows = load_autopsy_rows(autopsy_dir)
        result = score_card(card, rows, now_et=et_now(), min_n=args.min_n)
        print(json.dumps(result, indent=2, default=str))

        if not args.dry_run:
            summary = rescore_board(board_path=board_path, autopsy_dir=autopsy_dir, min_n=args.min_n)
            print(f"[hypothesis_scorer] board rescore: {json.dumps(summary)}", file=sys.stderr)
        return 0

    if args.all_testing:
        summary = rescore_board(board_path=board_path, autopsy_dir=autopsy_dir,
                                min_n=args.min_n, dry_run=args.dry_run)
        print(json.dumps(summary, indent=2))
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
