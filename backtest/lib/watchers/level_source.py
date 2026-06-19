"""Shared named-level loader for level-keyed watchers.

────────────────────────────────────────────────────────────────────────────────
WHY THIS MODULE EXISTS (the 2026-06-18 schema-mismatch fix)
────────────────────────────────────────────────────────────────────────────────
Live `automation/state/key-levels.json` (schema_version 3) describes each level
with a `tier` field ("Active" | "Carry" | "Reference"), a `type`
("support" | "resistance" | "psychological" | "transition"), and a `role`. It does
NOT carry the `strength.stars` object that strategy/key-levels-protocol.md §6
*planned* (added to the protocol doc 2026-05-08 v3) but which never actually
shipped into the J-curated state file — `summary.by_stars` in the live file is
{3star:0, 2star:0, 1star:0}.

Four watchers filtered levels on `entry.get("strength",{}).get("stars",0) >= 2`:
  floor_hold_bounce_watcher, close_ceiling_fade_watcher,
  named_level_second_test_watcher, stairstep_continuation_watcher.
Because `strength.stars` is always absent, that gate was ALWAYS False → every
watcher saw an empty level list → they fired on NOTHING live. After they were
wired into the production unified watcher layer, that wiring was inert.

THE FIX — derive stars from `tier` when `strength.stars` is absent.

Tier→stars mapping (justified against the codebase's OWN existing convention,
not invented here):
  - backtest/lib/sniper_detector.py lines 74-75 pair tier="Active" with star=2
    and tier="Carry" with star=3.
  - backtest/lib/level_strength.py#filter_by_distance treats ("Carry","Reference")
    as the deep-context anchor tiers that survive distance filtering — i.e. the
    high-importance set.
  - backtest/lib/watchers/shotgun_scalper_detector.py + missed_setups_scanner.py
    emit Active/Reference structural levels with stars=2.
So:  Active→2, Carry→3, Reference→2, Major→3, default→2.

Because key-levels.json contains only J-curated named levels (protocol gate:
"a level does not exist until it passes this protocol"), every structural named
level is meant to clear a >=2 gate by design. Active=2 vs the task-suggested
Active=3 makes NO behavioural difference under a >=2 threshold — both clear it —
so we adopt the codebase-consistent value.

THE LOAD-BEARING EXCLUSION — psychological / round-number levels are capped at ★
(protocol §6: "Round-number levels (is_round_number: true) capped at ★ unless
confluent"; protocol §5: round numbers go under type `psychological` and §1 of the
live file: ROUND_750 "Engine does not score as trigger source"). They must NOT
leak into a support/resistance set. We therefore force stars=1 for
type=="psychological" OR is_round_number==true, so they never clear min_stars>=2.
This is the rule that keeps the live 750.0 ROUND level out of the watcher sets.

The function is a drop-in replacement for the four watchers' bespoke
`_load_*_levels` helpers: same encoding (utf-8-sig), same path anchoring
(parents[3] → repo root → automation/state/key-levels.json), same per-calendar-day
cache, same graceful-empty-on-error behaviour.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

# Path from this file: backtest/lib/watchers/ → parents[3] = repo root → automation/state
_KEY_LEVELS_PATH: Path = (
    Path(__file__).resolve().parents[3] / "automation" / "state" / "key-levels.json"
)

# Tier → stars mapping (see module docstring for the codebase-evidence justification).
_TIER_STARS: dict[str, int] = {
    "Active": 2,
    "Carry": 3,
    "Reference": 2,
    "Major": 3,
}
_DEFAULT_TIER_STARS: int = 2

# Types that are awareness-only and must never clear a >=2 structural gate.
_NON_STRUCTURAL_TYPES: frozenset[str] = frozenset({"psychological"})


# ── Per-calendar-day cache ────────────────────────────────────────────────────
# Keyed by (today_str, roles_key, types_key, min_stars) so different watchers with
# different role/type filters do not stomp on one another's cached result.
_cache: dict[tuple, list[float]] = {}
_cache_date: Optional[str] = None


def level_stars(entry: dict) -> int:
    """Return the effective star rating for one key-levels.json level entry.

    Precedence:
      1. `strength.stars` if present and > 0 (forward-compatible — if the planned
         strength object ever ships, it wins).
      2. else tier→stars via _TIER_STARS (default _DEFAULT_TIER_STARS).
    Then CAP at 1 for psychological / round-number levels (protocol §6).
    """
    raw = ((entry.get("strength") or {}).get("stars")) or 0
    if raw and raw > 0:
        stars = int(raw)
    else:
        tier = entry.get("tier") or ""
        stars = _TIER_STARS.get(tier, _DEFAULT_TIER_STARS)

    lvl_type = (entry.get("type") or "").lower()
    is_round = bool(entry.get("is_round_number", False))
    if lvl_type in _NON_STRUCTURAL_TYPES or is_round:
        return min(stars, 1)
    return stars


def _read_levels() -> list[dict]:
    """Read the raw `levels` list from key-levels.json. [] on any error."""
    try:
        data = json.loads(_KEY_LEVELS_PATH.read_text(encoding="utf-8-sig"))
        levels = data.get("levels", [])
        return levels if isinstance(levels, list) else []
    except Exception:
        # File missing, corrupt JSON, unexpected schema — caller gets [] and the
        # watcher returns None gracefully; the next bar re-attempts the load.
        return []


def load_named_levels(
    today_str: str,
    *,
    roles: Optional[frozenset[str]] = None,
    types: Optional[frozenset[str]] = None,
    min_stars: int = 2,
) -> list[float]:
    """Load named-level PRICES from key-levels.json matching the given filters.

    A level qualifies if:
        price > 0
        AND effective stars (level_stars()) >= min_stars
        AND (its `role` is in `roles`  OR  its `type` is in `types`)
    where an empty/None `roles` (resp. `types`) means "do not match on role"
    (resp. type). At least one of roles/types should be provided; if BOTH are
    None the result is empty (nothing to match on).

    Results are cached per calendar day (key-levels.json changes daily but is
    stable within a session). Returns sorted unique prices.

    Mirrors the encoding (utf-8-sig), path anchoring, and graceful-empty error
    behaviour of the four watchers' original bespoke loaders.
    """
    global _cache_date, _cache

    if _cache_date != today_str:
        _cache = {}
        _cache_date = today_str

    roles = roles or frozenset()
    types = types or frozenset()
    # Normalise types to lowercase for case-insensitive matching.
    types_lc = frozenset(t.lower() for t in types)

    cache_key = (today_str, tuple(sorted(roles)), tuple(sorted(types_lc)), min_stars)
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    out: list[float] = []
    for entry in _read_levels():
        price = entry.get("price", 0.0)
        if not price or price <= 0:
            continue
        if level_stars(entry) < min_stars:
            continue
        role = entry.get("role") or ""
        lvl_type = (entry.get("type") or "").lower()
        if (role in roles) or (lvl_type in types_lc):
            out.append(float(price))

    result = sorted(set(out))
    _cache[cache_key] = result
    return result


def reset_cache() -> None:
    """Clear the per-day cache. Used by tests/gym validators to force a reload."""
    global _cache, _cache_date
    _cache = {}
    _cache_date = None
