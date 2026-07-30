"""build_shared_signal -- derive shared-signal.json from the heartbeat's decisions.jsonl.

The fleet's "one perception" is the SAFE heartbeat's per-tick read. Rather than burden
the token-tight production heartbeat prompt with another write, this pure-Python step
(run by the fleet wrapper right after the heartbeat) reads the latest production decision
row for today and maps it into the shared-signal contract the fleet executor consumes.

FAITHFULNESS NOTE (v1): decisions.jsonl carries action + bear/bull scores + spy + vix +
ribbon + setup + trigger, but NOT confidence/confluence/est_premium. So:
  * production_action, scores, spot, vix, ribbon are faithful.
  * bear.passed/bull.passed are derived from the production ACTION (the 3 fleet arms are
    all MORE selective than production -- stricter gate / direction-lock / different
    instrument -- so deriving "passed" from production's choice is correct: an arm can
    only filter production's signal further, never enter when production held).
  * confidence/confluence are omitted -> safe-3's A+ gate runs conservative (holds more).
  * est_premium is omitted -> the fleet runner fetches the REAL option mid per arm.
The faithfulness upgrade (heartbeat emits confidence/confluence/est_premium natively) is
the pre-LIVE step; for WATCH this derivation is honest and zero-risk to production.

Writes automation/state/fleet/shared-signal.json. Idempotent, fail-safe (writes a
HOLD/no-signal stub rather than crashing if decisions.jsonl is empty/unreadable).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

FLEET_DIR = Path(__file__).resolve().parent
REPO_ROOT = FLEET_DIR.parents[2]
sys.path.insert(0, str(REPO_ROOT / "setup" / "scripts"))
from et_clock import ET_TZ as ET  # DST-aware ET (TZ-SYSTEMIC fix: was timezone(timedelta(hours=-4)))
DECISIONS = REPO_ROOT / "automation" / "state" / "decisions.jsonl"
KEY_LEVELS = REPO_ROOT / "automation" / "state" / "key-levels.json"
# CORE ledger (the deterministic heartbeat_core brain): one row per account per tick
# (account in {"safe","bold"}). This is the LIVE producer source as of the 2026-06-25
# fleet-wiring redirect; the old DECISIONS LLM ledger is DEAD and kept only behind
# USE_CORE_LEDGER=False for a byte-identical revert.
CORE_DECISIONS = REPO_ROOT / "automation" / "state" / "core-decisions.jsonl"
BEACON = REPO_ROOT / "automation" / "state" / "sight-beacon.json"
OUT = FLEET_DIR / "shared-signal.json"

_ENTERS = {"ENTER_BEAR", "ENTER_BULL"}

# --- PRODUCER REDIRECT flag (REVERSIBLE) -------------------------------------
# DEFAULT ON (2026-06-25 fleet-wiring): the producer reads the DETERMINISTIC
# core-decisions.jsonl (heartbeat_core's verdicts) instead of the DEAD LLM
# decisions.jsonl. This is what lets the 3 ARM-READY fleet arms (safe-1, safe-3,
# risky-1) trade off the same brain that safe-2/bold-2 use. Set USE_CORE_LEDGER=False
# (or pass use_core=False to build()) for a BYTE-IDENTICAL revert to the v1 dead-ledger
# read — the one documented rollback for this change. Independent of SCORING_PEAK_LIVE
# (which is the separate dual-perception flag).
USE_CORE_LEDGER = True


def _fresh_beacon(now: datetime, max_age_s: int = 180) -> dict | None:
    """The NEVER-BLIND beacon (sight_beacon.py — direct Alpaca REST + yfinance, no MCP/CDP).
    Returns its fresh market read so the fleet still SEES the ribbon/price when the
    heartbeat's decisions.jsonl is stale/blind. None if the beacon is missing/stale/not-ok."""
    if not BEACON.exists():
        return None
    try:
        b = json.loads(BEACON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not b.get("ok"):
        return None
    try:
        bt = datetime.strptime((b.get("ts_et") or "")[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=ET)
    except (ValueError, TypeError):
        return None
    if (now - bt).total_seconds() > max_age_s:
        return None
    return b


def _decision_is_blind(row: dict | None, today: str, now: datetime, stale_min: int = 6) -> bool:
    """A decision that cannot inform the fleet: missing, blind ribbon, or >stale_min old."""
    if row is None:
        return True
    if row.get("ribbon_stack") in (None, "None", "UNKNOWN", ""):
        return True
    try:
        rt = datetime.strptime(f"{today} {row.get('time_et')}", "%Y-%m-%d %H:%M").replace(tzinfo=ET)
        if (now - rt).total_seconds() > stale_min * 60:
            return True
    except (ValueError, TypeError):
        pass
    return False


# --- CORE-LEDGER row mapping (the 2026-06-25 producer redirect) --------------
# core-decisions.jsonl schema (one row per account per tick):
#   ts_et, account ("safe"|"bold"), spy, ribbon, spread_cents, vix, htf_15m,
#   verdict, side, setup, bear_score, bull_score, triggers, action
# Map it into the SAME internal row shape the rest of build() already consumes
# (the keys build()'s row-mapping reads): action/spy->spot/ribbon_stack/
# ribbon_spread_cents/bear_score/bull_score/triggers_fired/setup_name/time_et.
# The ENTRY DECISION is taken from `verdict` (ENTER_BEAR/ENTER_BULL/HOLD/SKIP_*),
# NOT `action` — in the live ledger `action` can carry a downstream EXECUTION
# outcome (e.g. PLACE_FAIL) while `verdict` stays the brain's decision, and the
# validated replay_fleet_arms harness keys off the verdict. We surface the
# verdict-as-action so derive-passed (startswith ENTER_*) is faithful to the brain.
# 2026-07-02 entry-floor fix: brain-level TIME-GATE skips must not fan out as ENTER.
# Unlike PLACE_FAIL (execution noise — arms may succeed where the core's broker call
# failed), these mean the entry was never actionable at this wall-clock time.
_TIME_GATE_SKIPS = frozenset({"SKIP_EARLY_ENTRY", "SKIP_STALE_TRIGGER", "SKIP_LATE_ENTRY"})


def _map_core_row(row: dict) -> dict:
    verdict = row.get("verdict")
    if row.get("action") in _TIME_GATE_SKIPS:
        verdict = "HOLD"
    trig = row.get("triggers") or []
    if not isinstance(trig, list):
        trig = [trig] if trig else []
    ts = row.get("ts_et") or ""
    return {
        "action": verdict,                                  # verdict drives production_action + passed
        "spy": row.get("spy"),                              # -> spot
        "vix": row.get("vix"),
        "vix_dir": None,                                    # core ledger carries no vix_dir
        "ribbon_stack": row.get("ribbon"),                  # -> ribbon_stack
        "ribbon_spread_cents": row.get("spread_cents"),     # -> ribbon_spread_cents
        "htf_15m_stack": row.get("htf_15m"),
        "bear_score": row.get("bear_score", 0),
        "bull_score": row.get("bull_score", 0),
        "triggers_fired": list(trig),                       # full fired list (not single trigger+flag)
        "setup_name": row.get("setup"),
        "side": row.get("side"),
        "time_et": ts[11:16] if len(ts) >= 16 else None,    # "HH:MM" from ISO ts_et
        "tick_id": None,                                    # core ledger has no tick_id
        "date": ts[:10] if len(ts) >= 10 else None,
        "_core": True,
        # LEVEL PROVENANCE (G12, 2026-07-09 night): passthrough of heartbeat_core's
        # core-decisions.jsonl "trigger_level_exact" (ground truth from the winning side's
        # fired level-tied trigger). Absent on any row written before this build -> None,
        # the exact same "no exact level available" contract as a TRENDLINE-tier entry.
        "trigger_level_exact": row.get("trigger_level_exact"),
    }


def _latest_today_core(today: str, account: str) -> dict | None:
    """Latest core-decisions.jsonl row for `today` and `account` ("safe"|"bold"),
    mapped to build()'s internal row shape. File is append-order; last match wins."""
    if not CORE_DECISIONS.exists():
        return None
    latest = None
    try:
        for line in CORE_DECISIONS.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("account") != account:
                continue
            ts = row.get("ts_et") or ""
            if ts[:10] != today:
                continue
            latest = row  # append-order; last today+account row wins
    except OSError:
        return None
    return _map_core_row(latest) if latest is not None else None


def _latest_today_decision(today: str, account: str = "safe") -> dict | None:
    """Latest decision row for `today`. When USE_CORE_LEDGER (default) reads the
    DETERMINISTIC core-decisions.jsonl filtered by `account` ("safe"|"bold"); else
    falls back to the DEAD LLM decisions.jsonl (the byte-identical-v1 revert path).
    The `account` arg is honored only on the core path (the old ledger is safe-only)."""
    if USE_CORE_LEDGER:
        return _latest_today_core(today, account)
    if not DECISIONS.exists():
        return None
    latest = None
    try:
        for line in DECISIONS.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("date") != today:
                continue
            # production rows carry "action"; skip shadow-only rows (would_have_action)
            if row.get("action") is None and row.get("would_have_action") is not None:
                continue
            latest = row  # file is append-order; last today-row wins
    except OSError:
        return None
    return latest


# --- LIVE producer flip flag (DEFAULT OFF -- the WATCH-safe invariant) ---------
# build()'s DEFAULT output is byte-identical to v1: passed derives ONLY from the
# production action off the SAFE ledger, so EVERY arm stays inert/no-looser-than-
# production (passed=false on a gated HOLD). Setting SCORING_PEAK_LIVE=True (or
# passing scoring_peak=True) is the documented, reversible LIVE FLIP: build() then
# ALSO emits dual-perception signal['safe'] + signal['bold'] blocks where the bold
# block uses passed_scoring_peak off the BOLD ledger, so the loose arms (bold-loose/
# safe-loose) can take the A+ signals the tight gates blocked. Flipping this is a
# SEPARATE after-close step, NOT done by wiring accounts.json. Revert = flag off ->
# byte-identical v1 rollback.
SCORING_PEAK_LIVE = True  # flipped 2026-06-25 (J directive): all paper fleet arms live for the DATA; loose arms (safe-1/risky-3) consume scoring-peak passes. Revert = set False (byte-identical v1 rollback).


# --- FIX2: multi-strategy emit (DEFAULT ON, reversible) ----------------------
# The producer emits signal["strategies"]: every registered strategy evaluated
# INDEPENDENTLY per tick, so plan_all sees the FULL set (not just the single ribbon
# verdict the core ledger carries). ribbon_ride is re-keyed from the core row's bear/bull
# blocks; vwap_continuation is run via fleet_market.vwap_strategy_block (un-blockable REST
# bar fetch + the detector). Set EMIT_STRATEGIES=False (or pass emit_strategies=False) for a
# byte-identical revert to the pre-FIX2 signal (no strategies[] key). RUN_VWAP gates JUST the
# network detector pass (tests pass RUN_VWAP=False to stay offline + deterministic); the
# ribbon strategy is always derived from the in-hand row.
EMIT_STRATEGIES = True
RUN_VWAP = True  # network VWAP detector pass; tests disable to stay offline


# --- STRUCTURE-STOP trigger_level derivation (2026-07-09, flag-gated feature; this part is
# pure data plumbing and always runs -- emitting an extra JSON field is harmless whether or
# not params.structure_stop_enabled is set, since only exit_manager.ExitState.from_entry
# ACTS on stop_mode=="structure", never build_shared_signal). Mirrors heartbeat_core.py's
# own _read_levels/_level_expired (independent copy deliberately: build_shared_signal.py and
# heartbeat_core.py are separate entry-point scripts, not a shared library, so duplicating
# ~15 lines here is safer than adding a cross-directory import dependency to a live per-tick
# producer). None on ANY failure -- callers must treat a missing trigger_level as 'stay in
# premium-stop mode', never guess or block on it.
def _active_level_prices(now: datetime) -> list[float]:
    """Unexpired key-levels.json prices as of `now`'s ET date. [] on any read/parse failure."""
    try:
        kl = json.loads(KEY_LEVELS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    levels = kl.get("levels") or kl.get("key_levels") or []
    today = now.strftime("%Y-%m-%d")
    out: list[float] = []
    for lv in levels:
        if not isinstance(lv, dict):
            continue
        exp = str(lv.get("expires_at") or "")[:10]
        if exp and exp < today:
            continue  # expired -- fail-open (skip, never guess a stale level is still active)
        p = lv.get("price")
        if isinstance(p, (int, float)) and not isinstance(p, bool):
            out.append(float(p))
    return out


def _nearest_level(prices: list[float], spot, side: str, max_distance: float = 2.0):
    """Nearest of `prices` to `spot`, DIRECTIONALLY filtered by `side`, within max_distance.

    side="P" (bear/rejection) only considers levels AT/ABOVE spot (the resistance a
    rejection setup just bounced off); side="C" (bull/reclaim) only considers levels
    AT/BELOW spot (the support a reclaim setup just broke above) -- a correctness guard
    against picking a level on the WRONG side of spot (which would make the structure-stop
    check true at/near entry, a same-tick false exit). Mirrors
    exit_manager.nearest_active_level (kept independent -- see module note above)."""
    if spot is None or not prices or side not in ("P", "C"):
        return None
    try:
        spot_f = float(spot)
    except (TypeError, ValueError):
        return None
    best, best_dist = None, None
    for p in prices:
        if side == "P" and p < spot_f:
            continue
        if side == "C" and p > spot_f:
            continue
        dist = abs(p - spot_f)
        if dist <= max_distance and (best_dist is None or dist < best_dist):
            best, best_dist = round(p, 2), dist
    return best


def _ribbon_strategy_entries(bear: dict, bull: dict, spot, now: datetime | None = None) -> list[dict]:
    """ribbon_ride strategy-set entries re-keyed from the core row's passed side-blocks.
    One entry per passed side. Pure restructuring of data build() already mapped, PLUS a
    best-effort trigger_level (STRUCTURE-STOP, 2026-07-09) read from key-levels.json --
    the ONE per-tick file read this function performs; `now` defaults to the current ET
    time when omitted (existing callers that don't pass it keep working)."""
    now = now or datetime.now(timezone.utc).astimezone(ET)
    levels = _active_level_prices(now)
    out: list[dict] = []
    for side, blk in (("P", bear), ("C", bull)):
        if blk.get("passed") is not True:
            continue
        trigs = list(blk.get("triggers_fired") or [])
        elite = bool(blk.get("confluence")) or any("sequence" in str(t).lower() for t in trigs)
        # LEVEL PROVENANCE (G12, 2026-07-09 night): trigger_level_exact rides the side-block
        # (bear/bull dict already carries it, see build()/comment above) -- pure passthrough,
        # None-safe. trigger_level (the _nearest_level proximity heuristic) is UNCHANGED and
        # stays the fallback source; fleet_executor.py prefers _exact when present.
        _tl_exact = blk.get("trigger_level_exact")
        out.append({
            "name": "ribbon_ride",
            "side": side,
            "setup": blk.get("setup_name")
            or ("BEARISH_REJECTION_RIDE_THE_RIBBON" if side == "P"
                else "BULLISH_RECLAIM_RIDE_THE_RIBBON"),
            "triggers": trigs,
            "quality": "ELITE" if elite else "BASE",
            "est_premium": None,
            "spot": spot,
            "trigger_level": _nearest_level(levels, spot, side),
            "trigger_level_exact": (float(_tl_exact) if _tl_exact is not None else None),
        })
    return out


def _strategies_block(bear: dict, bull: dict, spot, now: datetime,
                      run_vwap: bool) -> list[dict]:
    """The FIX2 strategies[] set: every registered strategy evaluated independently this tick.

    ribbon_ride from the (already-mapped) side-blocks; vwap_continuation from the live
    detector pass (fleet_market). vwap is fail-safe: any import/fetch/detector miss simply
    omits it (never blocks the ribbon entries). run_vwap=False skips the network pass entirely
    (tests / offline) -- the ribbon entries still emit."""
    entries = _ribbon_strategy_entries(bear, bull, spot, now)
    if run_vwap:
        try:
            import fleet_market  # local; lazy heavy deps inside
            vwap_entry = fleet_market.vwap_strategy_block(now)
            if vwap_entry is not None:
                entries.append(vwap_entry)
        except Exception:
            pass  # producer must never crash on the VWAP pass — omit + continue
    return entries


def _has_confluence(triggers) -> bool:
    """A 'confluence' or 'multi_day_confluence' trigger fired (the ELITE flag fleet_executor
    ._is_elite reads as block['confluence'] is True — it does NOT read 'confluence' as a
    trigger NAME). Without this flag, require_confluence_or_sequence arms (risky-1/safe-3)
    silently HOLD setups their own backtest TOOK (risky-1 0/4 -> 4/4 once modeled)."""
    return any("confluence" in str(t).lower() for t in (triggers or []))


def _row_trigger_args(row: dict) -> tuple[list, object, bool]:
    """Normalize a mapped row's trigger info to (full_list, first_trigger, fired_bool).

    Core rows carry the full `triggers_fired` list; the legacy dead ledger carries a
    single `trigger` + `trigger_fired_this_tick` flag. Support both so the scoring-peak
    derivation is faithful on either source."""
    trigs = row.get("triggers_fired")
    if isinstance(trigs, list) and trigs:
        return list(trigs), trigs[0], True
    trigger = row.get("trigger")
    fired = bool(row.get("trigger_fired_this_tick"))
    if trigger and fired:
        return [trigger], trigger, True
    return [], trigger, fired


def _bold_passed_blocks_from_row(row: "dict | None") -> dict:
    """Pure row->blocks mapping extracted from _bold_passed_blocks (2026-07-20 DOJO-FLEET-
    HISTORICAL-SIGNAL split): identical logic, but takes an ALREADY-FETCHED row instead of
    reading disk. This is what lets a replay caller (DOJO's engine_step.py) supply a
    historical bold-account row without touching _latest_today_decision at all."""
    if row is None:
        return {"bull": {"passed": False, "score": 0, "triggers_fired": [], "confluence": False},
                "bear": {"passed": False, "score": 0, "triggers_fired": [], "confluence": False}}
    action = row.get("action")
    trigs, trig0, fired = _row_trigger_args(row)
    has_conf = _has_confluence(trigs)
    bull_peak = _score_peak_check("bull", action, row.get("bull_score", 0), trig0, fired)
    bear_peak = _score_peak_check("bear", action, row.get("bear_score", 0), trig0, fired)
    hard_skip = action in _HARD_SKIP_VERDICTS
    bull_p = bull_peak and not hard_skip
    bear_p = bear_peak and not hard_skip
    setup = row.get("setup_name")
    # LEVEL PROVENANCE (G12, 2026-07-09 night): same win-gated passthrough as build()'s
    # top-level bear/bull blocks (see comment there) -- sourced from the BOLD row itself,
    # since _latest_today_decision(..., account="bold") already routed _map_core_row here.
    _tl_exact = row.get("trigger_level_exact")
    # GATE-TIERS-IMPLEMENT (2026-07-23): "score_peak_passed"/"hard_skip_action" ride ALONGSIDE
    # the unchanged "passed" so fleet_executor._effective_passed() can rescue a hard-skip-only
    # block for an arm whose gate_params.hard_skip_verdicts opts out. triggers_fired/setup_name/
    # confluence/trigger_level_exact are now gated on the PEAK check (a superset of "passed" --
    # true whenever passed is true, plus the hard-skip-only cases) so a rescued arm has real
    # data to act on; an arm that does NOT opt out still reads "passed" and never sees this.
    return {
        "bull": {"passed": bull_p, "score": row.get("bull_score", 0),
                 "score_peak_passed": bull_peak,
                 "hard_skip_action": action if (hard_skip and bull_peak) else None,
                 "triggers_fired": trigs if bull_peak else [],
                 "setup_name": setup if bull_peak else None,
                 "confluence": bool(bull_peak and has_conf),
                 "trigger_level_exact": (_tl_exact if bull_peak else None)},
        "bear": {"passed": bear_p, "score": row.get("bear_score", 0),
                 "score_peak_passed": bear_peak,
                 "hard_skip_action": action if (hard_skip and bear_peak) else None,
                 "triggers_fired": trigs if bear_peak else [],
                 "setup_name": setup if bear_peak else None,
                 "confluence": bool(bear_peak and has_conf),
                 "trigger_level_exact": (_tl_exact if bear_peak else None)},
    }


def _bold_passed_blocks(today: str, now: datetime) -> dict:
    """Scoring-peak passed blocks derived off the BOLD perception (the 'bold' core row).

    Returns {'bull': {...}, 'bear': {...}} mirroring build()'s side-block shape. Used
    only by the flagged dual-perception build(); resolves the perception-source confound
    (safe arms judged on the SAFE row, bold arms on the BOLD row). Under USE_CORE_LEDGER
    the bold row is the account=="bold" core-decisions row; on the revert path it falls
    back to the dead BOLD_DECISIONS LLM ledger. Thin disk-read wrapper over
    _bold_passed_blocks_from_row (the pure mapping) -- unchanged behavior, just factored."""
    if USE_CORE_LEDGER:
        row = _latest_today_decision(today, account="bold")
    else:
        global DECISIONS
        _safe, DECISIONS = DECISIONS, BOLD_DECISIONS
        try:
            row = _latest_today_decision(today)
        finally:
            DECISIONS = _safe
    return _bold_passed_blocks_from_row(row)


def build(now: datetime | None = None, scoring_peak: bool | None = None,
          emit_strategies: bool | None = None, run_vwap: bool | None = None,
          probe_cohort: bool | None = None) -> dict:
    """Write shared-signal.json. DEFAULT (scoring_peak False/None and SCORING_PEAK_LIVE
    False) is byte-identical to v1. When scoring_peak is True (or the module flag is set)
    the signal ALSO carries dual-perception 'safe'/'bold' blocks for the loose arms.

    FIX2: when emit_strategies (or EMIT_STRATEGIES) is set, the signal ALSO carries a
    `strategies[]` set -- every registered strategy evaluated independently this tick (so
    plan_all sees the full set, not just the ribbon verdict). run_vwap gates JUST the
    network VWAP detector pass (tests pass run_vwap=False to stay offline).

    PROBE ARM (2026-07-10): when probe_cohort (or module flag PROBE_COHORT_LIVE) is set,
    the signal ALSO carries a 'probe' block (_probe_passed_blocks) -- the maximally-
    permissive cohort-block-bypass perception consumed ONLY by fleet_executor.py's
    probe-arm path. Pure additive data; inert for every other reader/arm."""
    now = now or datetime.now(timezone.utc).astimezone(ET)
    today = now.strftime("%Y-%m-%d")
    use_peak = SCORING_PEAK_LIVE if scoring_peak is None else bool(scoring_peak)
    do_strats = EMIT_STRATEGIES if emit_strategies is None else bool(emit_strategies)
    do_vwap = RUN_VWAP if run_vwap is None else bool(run_vwap)
    do_probe = PROBE_COHORT_LIVE if probe_cohort is None else bool(probe_cohort)
    row = _latest_today_decision(today)

    # NEVER-BLIND fallback (2026-06-25): if the heartbeat ledger is missing/stale/blind,
    # derive the live market read from the sight beacon (direct REST, no MCP/CDP) so the
    # fleet still SEES the ribbon/price. No scored setup comes from the beacon, so
    # production_action stays HOLD (conservative — sees but won't false-enter without a trigger).
    if _decision_is_blind(row, today, now):
        beacon = _fresh_beacon(now)
        if beacon is not None:
            sig = {
                "_doc": "Derived from sight-beacon.json (NEVER-BLIND fallback) — the heartbeat "
                        "decisions.jsonl was stale/blind. ribbon/price are live via direct REST; "
                        "no scored setup so production_action=HOLD.",
                "tick_id": None, "date": today, "time_et": now.strftime("%H:%M"),
                "spot": beacon.get("spy"), "vix": None, "vix_dir": None,
                "ribbon_stack": beacon.get("ribbon_stack"),
                "ribbon_spread_cents": beacon.get("spread_cents"),
                "htf_15m_stack": None, "production_action": "HOLD",
                "bear": {"passed": False, "score": 0, "triggers_fired": [], "setup_name": None},
                "bull": {"passed": False, "score": 0, "triggers_fired": [], "setup_name": None},
                "written_at": now.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "beacon_ts_et": beacon.get("ts_et"), "data_source": beacon.get("data_source"),
                "source": "derived-from-beacon-NEVER-BLIND",
            }
            if use_peak:
                sig["safe"] = {"bull": {"passed": False, "score": 0}, "bear": {"passed": False, "score": 0}}
                sig["bold"] = {"bull": {"passed": False, "score": 0}, "bear": {"passed": False, "score": 0}}
                sig["scoring_peak_live"] = True
            if do_strats:
                sig["strategies"] = []  # blind/beacon fallback: no scored setup -> empty set
            if do_probe:
                sig["probe"] = {"bull": dict(_PROBE_EMPTY), "bear": dict(_PROBE_EMPTY)}
            OUT.write_text(json.dumps(sig, indent=2), encoding="utf-8")
            return sig
        # beacon also unavailable -> fall through to the original no-decision / stale-row path

    if row is None:
        sig = {
            "_doc": "Derived from decisions.jsonl by build_shared_signal.py (no today row yet).",
            "tick_id": None, "date": today, "time_et": now.strftime("%H:%M"),
            "spot": None, "production_action": "HOLD",
            "bear": {"passed": False, "score": 0}, "bull": {"passed": False, "score": 0},
            "written_at": now.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "source": "derived-no-decision",
        }
        if use_peak:
            sig["safe"] = {"bull": {"passed": False, "score": 0}, "bear": {"passed": False, "score": 0}}
            sig["bold"] = {"bull": {"passed": False, "score": 0}, "bear": {"passed": False, "score": 0}}
            sig["scoring_peak_live"] = True
        if do_strats:
            sig["strategies"] = []  # no today row -> no scored setup -> empty set
        if do_probe:
            sig["probe"] = {"bull": dict(_PROBE_EMPTY), "bear": dict(_PROBE_EMPTY)}
        OUT.write_text(json.dumps(sig, indent=2), encoding="utf-8")
        return sig

    action = row.get("action")
    triggers, _trig0, _fired = _row_trigger_args(row)
    has_conf = _has_confluence(triggers)
    setup = row.get("setup_name")

    bear_pass = action == "ENTER_BEAR"
    bull_pass = action == "ENTER_BULL"
    # LEVEL PROVENANCE (G12, 2026-07-09 night): row.get("trigger_level_exact") is a single
    # value keyed to whichever side WON the tick (mirrors triggers_fired/setup_name's own
    # win-gated emission below) -- None on the losing side or a HOLD/SKIP tick.
    _tl_exact = row.get("trigger_level_exact")
    bear = {"passed": bear_pass, "score": row.get("bear_score", 0),
            "triggers_fired": triggers if bear_pass else [],
            "setup_name": setup if bear_pass else None,
            # CONFLUENCE FLAG (load-bearing): fleet_executor._is_elite treats a block ELITE
            # only if block['confluence'] is True OR a sequence_* trigger is present — it does
            # NOT read "confluence" as a trigger NAME. So emit the boolean here whenever a
            # confluence/multi_day_confluence trigger fired for this side.
            "confluence": bool(bear_pass and has_conf),
            "trigger_level_exact": (_tl_exact if bear_pass else None)}
    bull = {"passed": bull_pass, "score": row.get("bull_score", 0),
            "triggers_fired": triggers if bull_pass else [],
            "setup_name": setup if bull_pass else None,
            "confluence": bool(bull_pass and has_conf),
            "trigger_level_exact": (_tl_exact if bull_pass else None)}

    _ledger = "core-decisions.jsonl" if USE_CORE_LEDGER else "decisions.jsonl"
    sig = {
        "_doc": f"Derived from {_ledger} by build_shared_signal.py. "
                "confidence/est_premium omitted -> safe-3 conservative; confluence flag "
                "emitted for ELITE parity; fleet runner fetches real option mid for premium.",
        "tick_id": row.get("tick_id"),
        "date": today,
        "time_et": row.get("time_et") or now.strftime("%H:%M"),
        "spot": row.get("spy"),
        "vix": row.get("vix"),
        "vix_dir": row.get("vix_dir"),
        "ribbon_stack": row.get("ribbon_stack"),
        "ribbon_spread_cents": row.get("ribbon_spread_cents"),
        "htf_15m_stack": row.get("htf_15m_stack"),
        "production_action": action,
        "bear": bear,
        "bull": bull,
        "written_at": now.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": f"derived-from-{'core' if USE_CORE_LEDGER else 'decisions'}-v1",
    }
    if use_peak:
        # Dual perception: safe arms read signal['safe'] (the SAFE core row, production-faithful);
        # bold/loose arms read signal['bold'] (the BOLD core row, scoring-peak). Top-level bear/bull
        # stay production-faithful for backward-compat (controls + un-routed consumers).
        sig["safe"] = {"bull": dict(bull), "bear": dict(bear)}
        sig["bold"] = _bold_passed_blocks(today, now)
        sig["scoring_peak_live"] = True
        sig["source"] = f"derived-from-{'core' if USE_CORE_LEDGER else 'decisions'}-v2-dualperception"
    if do_strats:
        # FIX2: every registered strategy, evaluated independently this tick. When the
        # dual-perception 'bold' block passed a side the top-level (production-faithful) one
        # did not, derive the ribbon entries from the LOOSER perception so the loose arms see
        # the scoring-peak setup (top-level bear/bull stay production-faithful for the controls).
        s_bear, s_bull = bear, bull
        if use_peak:
            bold = sig.get("bold") or {}
            if (bold.get("bear") or {}).get("passed") or (bold.get("bull") or {}).get("passed"):
                s_bear, s_bull = bold.get("bear") or bear, bold.get("bull") or bull
        sig["strategies"] = _strategies_block(s_bear, s_bull, row.get("spy"), now, do_vwap)
    if do_probe:
        sig["probe"] = _probe_passed_blocks(today, now)
    # SCORE LADDER (2026-07-27): additive block, same inertness contract as 'probe' -- every
    # reader that doesn't know the key ignores it; only arms with gate_override.
    # score_ladder_floor consume it (fleet_executor._ladder_plan). Fail-closed producer:
    # absent raw fields (all rows before 2026-07-28) -> available=False.
    sig["ladder"] = _ladder_block(today)
    OUT.write_text(json.dumps(sig, indent=2), encoding="utf-8")
    return sig


# --- Scoring-peak derivation (2026-06-24 KEYSTONE fix, SHADOW until after-close deploy) ---
# BUG found by workflow w2dnmn1pr verify phase: build() above derives passed ONLY from
# production action=='ENTER_*' off the SAFE ledger. So a gated-but-perfect setup (production
# HOLDs because a gate vetoed it) emits passed=false, and NO fleet arm can ever be LOOSER
# than production -- the inverse of the 3-bold-looseness-tier goal. This shadow path derives
# passed from the SCORING PEAK + a fired entry-trigger off the BOLD ledger, so the looser
# bold arms can SEE the A+ signals the tight gates blocked. WATCH-ONLY: writes a shadow file,
# NOT wired into the live build()/__main__ -- live behavior is byte-identical until the
# after-close deploy + safety review (the fleet runs fleet_live --live).
BOLD_DECISIONS = REPO_ROOT / "automation" / "state" / "aggressive" / "decisions.jsonl"
SHADOW_OUT = FLEET_DIR / "shared-signal-bold-shadow.json"
BULL_PEAK_THRESHOLD = 9   # bull_score is /11; 9+ with a fired trigger = A+ reclaim/breakout
BEAR_PEAK_THRESHOLD = 8   # bear_score is /10
ENTRY_TRIGGERS = frozenset({
    "level_reclaim", "ribbon_flip", "sequence_reclaim", "multi_day_confluence",
    "confluence", "level_rejection", "sequence_rejection",
})


# Hard gates that override scoring peak — the fill bar being counter-directional is trade
# quality (computable at signal time), NOT a conservative production gate, so no loose arm
# should bypass it via high score. Added 2026-06-28 (C14 fix: require_bearish_fill_bar).
_HARD_SKIP_VERDICTS = frozenset({"SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY"})

# SIGHT FAILURES (2026-07-30, SKIP_NO_LEVELS) — categorically NOT gates, and therefore not
# something ANY arm may trade through, however loose its tier.
#
# Every other verdict in this file describes a JUDGMENT the brain made about a setup it could
# see. SKIP_NO_LEVELS describes the brain being UNABLE TO SEE: on 2026-07-30 key-levels.json
# went 19.8h without a refresh, levels_active was [] on 386 of 386 rows, and the engine fell
# through to trendline-only entries (-$1,830 / WR .19 / n=124) — 11 ENTER_BEAR verdicts at
# SPY 734.885, the LOW OF THE DAY, before SPY rallied 6.7 points into the close.
#
# WHY NOT _HARD_SKIP_VERDICTS: that set is explicitly per-arm-overridable via accounts.json
# gate_params.hard_skip_verdicts, and risky-3 ships with `[]` (inherits NO global hard skip).
# Routing blindness through it would leave risky-3 entering blind trades off this exact
# ledger row — the bypass this repair exists to close. A sight failure is checked INSIDE
# _score_peak_check, ahead of the score/trigger math, so it suppresses `passed` AND
# `score_peak_passed` together and fleet_executor._effective_passed has nothing left to
# rescue for any tier.
#
# The score math is what makes this necessary rather than belt-and-suspenders: today's blind
# rows carry bear_score 8 (== BEAR_PEAK_THRESHOLD) with triggers [ribbon_flip,
# trendline_rejection], and trig0 "ribbon_flip" IS in ENTRY_TRIGGERS — so a loose arm would
# have scored these as "passed on quality alone" despite the brain having refused them.
#
# ZERO BEHAVIOR CHANGE ON HISTORY: "SKIP_NO_LEVELS" is a verdict string that did not exist
# before 2026-07-30, so no historical row carries it and every replay
# (replay_fleet_arms/DOJO) is byte-identical. Guard: test_blind_no_levels_2026_07_30.py.
_SIGHT_FAILURE_VERDICTS = frozenset({"SKIP_NO_LEVELS"})


def _score_peak_check(side: str, action, score, trigger, fired) -> bool:
    """The score/trigger half of passed_scoring_peak, WITHOUT the hard-skip filter --
    'would this side have passed on quality alone'. Exposed separately (GATE-TIERS-
    IMPLEMENT, 2026-07-23) so a per-arm gate_params.hard_skip_verdicts override can
    rescue a setup that only the GLOBAL _HARD_SKIP_VERDICTS blocked (audit rank #3,
    markdown/audits/GATE-PROVENANCE-AUDIT-2026-07-02.md section 4: 'require_bearish_
    fill_bar ... not inherited via _HARD_SKIP' for RISKY-tier arms).

    SIGHT-FAILURE GUARD (2026-07-30): a blind tick has no computable quality, so the question
    this function asks is unanswerable and the only honest return is False -- for every tier,
    including the arms that opt out of _HARD_SKIP_VERDICTS. See _SIGHT_FAILURE_VERDICTS."""
    if action in _SIGHT_FAILURE_VERDICTS:
        return False
    enter = "ENTER_BULL" if side == "bull" else "ENTER_BEAR"
    peak = BULL_PEAK_THRESHOLD if side == "bull" else BEAR_PEAK_THRESHOLD
    trig_ok = bool(fired) and (trigger in ENTRY_TRIGGERS)
    return (action == enter) or (int(score or 0) >= peak and trig_ok)


def passed_scoring_peak(side: str, action, score, trigger, fired) -> bool:
    """Looser-than-production 'passed': production ENTERED this side, OR the score hit the
    peak threshold WITH a real entry-trigger fired (the quality gate that stops pure-score
    over-emission). This is what lets a loose arm take a setup production's gates blocked.
    Hard gates in _HARD_SKIP_VERDICTS always return False regardless of score.

    UNCHANGED signature/behavior (byte-identical) -- this is now a thin wrapper over
    _score_peak_check + the global hard-skip filter; per-arm overrides are consumed at
    fleet_executor.py's _effective_passed(), not here."""
    if action in _HARD_SKIP_VERDICTS:
        return False
    return _score_peak_check(side, action, score, trigger, fired)


# --- PROBE ARM cohort-bypass block (2026-07-10 ship, NARROWED same session) ---------------
# J directive 2026-07-10: "6 arms and nothing took a trade... why isn't 1 arm set to take
# riskier trades?" First cut of this mechanism was a broad "bypass any cohort/tier gate
# except a hard-safety exclude-list" blocklist. SAME SESSION, `markdown/audits/GATE-
# PROVENANCE-SWEEP-2026-07-10.md` (commit 54d5840) landed a rigorous, pre-registered,
# hash-pinned, 19/19-test-covered per-gate audit that changed the answer for the two gates
# that actually blocked bull setups on 07-10:
#   - block_elite_bull: RELAUNCHED its SS-B revalidation (a study a PC reboot killed
#     2026-07-09) under the FROZEN pre-registration `block-elite-bull-ssb-preregistration.
#     json`. VERDICT: KEEP. n=28, OLD(CONTROL) total -$560.00 -> SS-B total -$3,873.60 --
#     the SAME structure-stop exit shape this probe arm's own ribbon_ride entries use makes
#     an already-negative cohort ~6.9x WORSE (`analysis/recommendations/block-elite-bull-
#     ssb-revalidation.json`). Probing a cohort JUST hash-pin-proven to be a loser under the
#     EXACT exit shape probe would trade it with is not "gathering evidence" -- it is
#     re-spending real paper capital on a question that already has a rigorous answer.
#     NOT bypassed.
#   - block_bull_1100_1200: VERDICT REVALIDATE. Provenance is thin (IS n=11 WR=9.1%, OOS
#     n=1) and pre-dates SS-B (ratified the same day chart-stop-primary shipped, so its own
#     evidence likely straddles the exit-shape transition) -- and 07-10 was the first
#     genuinely-live block of a SUPER-tier (not just ELITE) signal since ratification. This
#     is exactly the shape of gate a min-size forward probe SHOULD revalidate: real signal,
#     thin/stale evidence, no fresh answer yet. Bypassed.
#   - block_bull_ribbon_flip: independently reconfirmed (3rd time across 3 separate audits
#     this repo has now run) ABSENT from both params.json files. Never armed, no bypass
#     needed or built for it.
# So the bypass set is NARROW and EXPLICIT (an allowlist, not a blocklist): ONLY
# SKIP_BULL_1100_1200, PLUS the always-required "a real named ENTRY_TRIGGERS-member trigger
# fired" floor (never trades on triggers=[], regardless of verdict). Every other SKIP_*
# verdict -- block_elite_bull's SKIP_ELITE_BULL_LEVEL_RECLAIM/SKIP_ELITE_BEAR_*, the time-
# gate skips, structure-veto, data-integrity, one-position, and anything not explicitly
# named -- is NOT bypassed. min_entry_premium / kill-switch / PDT / entry-time floor-ceiling
# are enforced DOWNSTREAM (fleet_executor.finalize / fleet_live._place_live, untouched by
# this block) so they apply to a probe-sourced plan exactly like any other.
# Consumed ONLY by fleet_executor.py's probe-arm path (accounts.json top-level "probe_arm"
# block); every other reader ignores the new 'probe' signal key, so this addition is inert
# for every other arm regardless of PROBE_COHORT_LIVE.
PROBE_ALLOWED_VERDICTS = frozenset({"SKIP_BULL_1100_1200"})

# LEDGER-SOURCE FIX (2026-07-11, found in code review before dispatch, confirmed here):
# every verdict on PROBE_ALLOWED_VERDICTS maps (via PROBE_COHORT_GATE_KEYS below) to a
# params.json gate key. block_bull_1100_1200 is a SAFE-ONLY gate -- confirmed absent from
# automation/state/aggressive/params.json (grep, both files) and present in heartbeat_core.
# GATE_KEYS (setup/scripts/heartbeat_core.py:125-133), which each account's engine reads
# from ITS OWN params file. Bold's engine has no such key to read, so it can never emit
# action=="SKIP_BULL_1100_1200" -- confirmed against 4,342 real bold core-decisions.jsonl
# rows: 0 BULL_1100_1200 hits, ever. _probe_passed_blocks() below read account="bold" at
# ship (a copy-paste of _bold_passed_blocks' read, never re-derived for the probe's actual
# allowlist scope) -- so the ONE cohort this arm exists to probe could structurally never be
# read off the ledger it consulted. Dead on arrival, silently, from ship (2026-07-10) until
# this fix. Reads PROBE_LEDGER_ACCOUNT instead now. If the allowlist ever grows a bold-side
# (or mixed) cohort, PROBE_LEDGER_ACCOUNT/the read logic must be revisited by hand -- the
# drift guard (test_probe_arm.py::test_probe_allowlist_gates_present_on_read_account_params)
# fails loudly if a future addition's gate isn't a key in the read account's params file.
PROBE_LEDGER_ACCOUNT = "safe"
PROBE_COHORT_GATE_KEYS = {"SKIP_BULL_1100_1200": "block_bull_1100_1200"}

# DEFAULT ON (2026-07-10 ship): build()'s emitted 'probe' block is pure additive data --
# harmless whether or not any arm's accounts.json probe_arm.enabled reads it (same "extra
# JSON field, only a flagged consumer ACTS on it" philosophy as the trigger_level plumbing
# above). Set PROBE_COHORT_LIVE=False (or build(probe_cohort=False)) for a byte-identical
# producer-side revert -- belt-and-suspenders alongside accounts.json's probe_arm.enabled
# (the primary, consumer-side kill switch fleet_executor.py actually checks).
PROBE_COHORT_LIVE = True

_PROBE_EMPTY = {"passed": False, "score": 0, "triggers_fired": [], "setup_name": None,
                "blocked_verdict": None, "trigger_level_exact": None}


def passed_probe_cohort(action, trigger, fired) -> bool:
    """NARROW ALLOWLIST (see module comment): True only when `action` is one of the
    explicitly gate-provenance-reviewed, REVALIDATE-verdicted verdicts in
    PROBE_ALLOWED_VERDICTS (today: SKIP_BULL_1100_1200 only) AND a real named
    ENTRY_TRIGGERS-member trigger actually fired. Everything else -- including a bare
    "HOLD" (which action collapses to even for the excluded _TIME_GATE_SKIPS verdicts, see
    _map_core_row) and every cohort/tier gate NOT on the allowlist (block_elite_bull
    included) -- returns False. The allowlist model makes this automatic: there is no
    exclude-list to keep in sync as new gates are added or re-verdicted, only an explicit
    list of what's IN."""
    if action not in PROBE_ALLOWED_VERDICTS:
        return False
    return bool(fired) and (trigger in ENTRY_TRIGGERS)


def _probe_passed_blocks(today: str, now: datetime) -> dict:
    """Raw cohort-block-bypass blocks off the PROBE_LEDGER_ACCOUNT ledger ("safe" -- FIXED
    2026-07-11, was hardcoded "bold" at ship. Every verdict on PROBE_ALLOWED_VERDICTS maps to
    a SAFE-only params.json gate (see the PROBE_COHORT_GATE_KEYS module comment above); the
    bold ledger this function used to read structurally has zero rows carrying any of those
    verdicts, so the probe arm could never fire. Full evidence in the module comment above
    PROBE_ALLOWED_VERDICTS). blocked_verdict carries the ORIGINAL core verdict for THIS tick
    so the probe arm can tag its entry reason with exactly which gate it bypassed (e.g.
    SKIP_BULL_1100_1200 -> reason 'PROBE_ARM cohort=bull_1100_1200'). Side discrimination uses
    the ledger's OWN `side` field (row['side'], 'C'|'P') rather than a score-based inference
    (passed_scoring_peak's implicit protection: the LOSING side's raw score is usually too low
    to matter) -- explicit is correct here since this function does not consult score at all."""
    if USE_CORE_LEDGER:
        row = _latest_today_decision(today, account=PROBE_LEDGER_ACCOUNT)
    elif PROBE_LEDGER_ACCOUNT == "bold":
        global DECISIONS
        _safe_decisions, DECISIONS = DECISIONS, BOLD_DECISIONS
        try:
            row = _latest_today_decision(today)
        finally:
            DECISIONS = _safe_decisions
    else:
        row = _latest_today_decision(today)
    return _probe_passed_blocks_from_row(row)


def _probe_passed_blocks_from_row(row: "dict | None") -> dict:
    """Pure row->blocks mapping extracted from _probe_passed_blocks (2026-07-20 DOJO-FLEET-
    HISTORICAL-SIGNAL split): identical logic, takes an ALREADY-FETCHED row. Lets a replay
    caller supply a historical probe-ledger row without touching disk."""
    if row is None:
        return {"bull": dict(_PROBE_EMPTY), "bear": dict(_PROBE_EMPTY)}
    action = row.get("action")
    trigs, trig0, fired = _row_trigger_args(row)
    setup = row.get("setup_name")
    row_side = row.get("side")
    ok = passed_probe_cohort(action, trig0, fired)
    bull_p = bool(ok and row_side == "C")
    bear_p = bool(ok and row_side == "P")
    _tl_exact = row.get("trigger_level_exact")
    return {
        "bull": {"passed": bull_p, "score": row.get("bull_score", 0),
                 "triggers_fired": trigs if bull_p else [],
                 "setup_name": setup if bull_p else None,
                 "blocked_verdict": (action if bull_p else None),
                 "trigger_level_exact": (_tl_exact if bull_p else None)},
        "bear": {"passed": bear_p, "score": row.get("bear_score", 0),
                 "triggers_fired": trigs if bear_p else [],
                 "setup_name": setup if bear_p else None,
                 "blocked_verdict": (action if bear_p else None),
                 "trigger_level_exact": (_tl_exact if bear_p else None)},
    }


# --- SCORE LADDER (2026-07-27, J directive after the 09:40 bear_score-9 miss) -------------
# The probe lane above rescues GATE-blocked ticks (verdict on PROBE_ALLOWED_VERDICTS). This
# lane rescues SCORING-failed ticks -- the 2026-07-27 class: bear_score 9/10, raw detections
# level_rejection+confluence @744.9, refused because filter 5 (ribbon stack, STRUCTURAL,
# unforgivable) left passed=False and _derive_routing emitted a bare HOLD. J's standing arm
# design ("the riskiest arm can hop in at a seven out of ten") -- each arm applies its OWN
# score floor (gate_override.score_ladder_floor in accounts.json) to this block downstream in
# fleet_executor._ladder_plan; this producer only reports what the engine SAW.
#
# HARD REQUIREMENTS (all fail-closed -- absent data means NO block, never a guess):
#   * verdict must be a plain scoring HOLD ("no setup passed scoring") -- gate-skip verdicts
#     stay probe's turf, ENTER ticks stay the normal path's;
#   * a RAW LEVEL-TIED trigger must have fired (bear_triggers_raw, from decide_payload as of
#     3ced7457 -- rows before 2026-07-28 lack the field and correctly produce no block);
#   * the raw detection's own level must exist (bear_rejection_level_raw) -- it is the ladder
#     entry's chart-stop anchor; no level, no trade.
LADDER_LEVEL_TIED = frozenset({"level_rejection", "fhh_level_rejection", "confluence",
                                "sequence_rejection"})
_LADDER_EMPTY = {"available": False, "score": 0, "triggers_raw": [], "level": None,
                 "blockers": [], "reason": None}


def _ladder_block_from_row(row: "dict | None") -> dict:
    """Pure row -> ladder block (bear side only for v1 -- bull stays out until its own
    pre-registered evidence exists; the 2026-07-27 10:06 bull-9 fired mid-fade and would
    have lost, so bull needs the study first, not a mirror-image flip)."""
    out = {"bear": dict(_LADDER_EMPTY)}
    if row is None:
        return out
    verdict = str(row.get("verdict") or "")
    reason = str(row.get("reason") or "")
    if verdict != "HOLD" or "no setup passed scoring" not in reason:
        return out
    raw = [t for t in (row.get("bear_triggers_raw") or []) if isinstance(t, str)]
    level = row.get("bear_rejection_level_raw")
    score = row.get("bear_score") or 0
    if not any(t in LADDER_LEVEL_TIED for t in raw):
        return out
    if not isinstance(level, (int, float)):
        return out
    out["bear"] = {"available": True, "score": int(score), "triggers_raw": raw,
                   "level": float(level),
                   "blockers": list(row.get("bear_blockers") or []),
                   "reason": f"score {score} blocked (blockers {row.get('bear_blockers')})"}
    return out


def _ladder_block(today: str) -> dict:
    row = _latest_today_decision(today, account=PROBE_LEDGER_ACCOUNT) if USE_CORE_LEDGER \
        else _latest_today_decision(today)
    return _ladder_block_from_row(row)


def build_from_rows(row: "dict | None", now: datetime, *, bold_row: "dict | None" = None,
                     probe_row: "dict | None" = None, scoring_peak: bool | None = None,
                     emit_strategies: bool | None = None, run_vwap: bool | None = None,
                     probe_cohort: bool | None = None, write: bool = False) -> dict:
    """Replay-aware sibling of build() (2026-07-20 DOJO-FLEET-HISTORICAL-SIGNAL). Produces the
    IDENTICAL shared-signal shape build() writes, but fed an ALREADY-MAPPED row (the exact shape
    _map_core_row/a DojoDecision->row mapping produces) instead of reading today's on-disk
    core-decisions.jsonl. This is what lets the DOJO replay room (setup/scripts/dojo/
    engine_step.py) drive the 3 fleet exit-diversity arms (safe-3/risky-1/risky-3) off a
    HISTORICAL bar's engine decision, using the SAME signal-construction logic as the live
    producer (bear/bull block shape, _bold_passed_blocks_from_row, _probe_passed_blocks_from_row,
    _strategies_block) -- so there is exactly one implementation of "what a core row means as a
    fleet signal", no separate replay re-derivation to drift out of sync.

    BLAST-RADIUS DISCIPLINE (this module is a shared PRODUCTION module the live fleet_rest
    executor consumes every tick): this function is PURELY ADDITIVE -- build(), _latest_today_
    decision, _decision_is_blind, and every existing disk-reading code path are UNTOUCHED. write
    defaults to False and this function NEVER calls OUT.write_text unless write=True is passed
    explicitly, so a replay session can never clobber the live automation/state/fleet/
    shared-signal.json (guarded: test_build_from_rows_replay.py::test_build_from_rows_never_
    writes_by_default).

    `row is None` (no engine decision this bar, e.g. before 2 RTH bars exist) returns the same
    'no-decision' HOLD stub shape build() returns for that case, so a fleet-arm consumer sees a
    structurally identical signal regardless of live/replay source."""
    today = now.strftime("%Y-%m-%d")
    use_peak = SCORING_PEAK_LIVE if scoring_peak is None else bool(scoring_peak)
    do_strats = EMIT_STRATEGIES if emit_strategies is None else bool(emit_strategies)
    do_vwap = RUN_VWAP if run_vwap is None else bool(run_vwap)
    do_probe = PROBE_COHORT_LIVE if probe_cohort is None else bool(probe_cohort)

    if row is None:
        sig = {
            "_doc": "Derived from build_from_rows() (replay/DOJO path) -- no engine decision "
                    "for this bar.",
            "tick_id": None, "date": today, "time_et": now.strftime("%H:%M"),
            "spot": None, "production_action": "HOLD",
            "bear": {"passed": False, "score": 0}, "bull": {"passed": False, "score": 0},
            "written_at": now.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "source": "derived-no-decision-replay",
        }
        if use_peak:
            sig["safe"] = {"bull": {"passed": False, "score": 0}, "bear": {"passed": False, "score": 0}}
            sig["bold"] = {"bull": {"passed": False, "score": 0}, "bear": {"passed": False, "score": 0}}
            sig["scoring_peak_live"] = True
        if do_strats:
            sig["strategies"] = []
        if do_probe:
            sig["probe"] = {"bull": dict(_PROBE_EMPTY), "bear": dict(_PROBE_EMPTY)}
        if write:
            OUT.write_text(json.dumps(sig, indent=2), encoding="utf-8")
        return sig

    action = row.get("action")
    triggers, _trig0, _fired = _row_trigger_args(row)
    has_conf = _has_confluence(triggers)
    setup = row.get("setup_name")

    bear_pass = action == "ENTER_BEAR"
    bull_pass = action == "ENTER_BULL"
    _tl_exact = row.get("trigger_level_exact")
    bear = {"passed": bear_pass, "score": row.get("bear_score", 0),
            "triggers_fired": triggers if bear_pass else [],
            "setup_name": setup if bear_pass else None,
            "confluence": bool(bear_pass and has_conf),
            "trigger_level_exact": (_tl_exact if bear_pass else None)}
    bull = {"passed": bull_pass, "score": row.get("bull_score", 0),
            "triggers_fired": triggers if bull_pass else [],
            "setup_name": setup if bull_pass else None,
            "confluence": bool(bull_pass and has_conf),
            "trigger_level_exact": (_tl_exact if bull_pass else None)}

    sig = {
        "_doc": "Derived from build_from_rows() (replay/DOJO path) -- same shape as the live "
                "producer's build(), fed a historical row instead of a disk read.",
        "tick_id": row.get("tick_id"),
        "date": row.get("date") or today,
        "time_et": row.get("time_et") or now.strftime("%H:%M"),
        "spot": row.get("spy"),
        "vix": row.get("vix"),
        "vix_dir": row.get("vix_dir"),
        "ribbon_stack": row.get("ribbon_stack"),
        "ribbon_spread_cents": row.get("ribbon_spread_cents"),
        "htf_15m_stack": row.get("htf_15m_stack"),
        "production_action": action,
        "bear": bear,
        "bull": bull,
        "written_at": now.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": "derived-from-row-replay",
    }
    if use_peak:
        sig["safe"] = {"bull": dict(bull), "bear": dict(bear)}
        sig["bold"] = _bold_passed_blocks_from_row(bold_row)
        sig["scoring_peak_live"] = True
        sig["source"] = "derived-from-row-replay-dualperception"
    if do_strats:
        s_bear, s_bull = bear, bull
        if use_peak:
            bold = sig.get("bold") or {}
            if (bold.get("bear") or {}).get("passed") or (bold.get("bull") or {}).get("passed"):
                s_bear, s_bull = bold.get("bear") or bear, bold.get("bull") or bull
        sig["strategies"] = _strategies_block(s_bear, s_bull, row.get("spy"), now, do_vwap)
    if do_probe:
        sig["probe"] = _probe_passed_blocks_from_row(probe_row)
    if write:
        OUT.write_text(json.dumps(sig, indent=2), encoding="utf-8")
    return sig


def build_shadow(now: datetime | None = None) -> dict:
    """SHADOW signal off the BOLD ledger using scoring-peak 'passed'. Read-only proof; the
    live fleet does NOT consume SHADOW_OUT. Mirrors build()'s shape for an apples-to-apples diff."""
    now = now or datetime.now(timezone.utc).astimezone(ET)
    today = now.strftime("%Y-%m-%d")
    # reuse _latest_today_decision against the BOLD ledger
    global DECISIONS
    _safe_decisions, DECISIONS = DECISIONS, BOLD_DECISIONS
    try:
        row = _latest_today_decision(today)
    finally:
        DECISIONS = _safe_decisions
    if row is None:
        sig = {"_doc": "SHADOW (scoring-peak, BOLD ledger) -- no today row.", "date": today,
               "bull": {"passed": False, "score": 0}, "bear": {"passed": False, "score": 0},
               "source": "shadow-no-decision"}
        SHADOW_OUT.write_text(json.dumps(sig, indent=2), encoding="utf-8")
        return sig
    action, trigger = row.get("action"), row.get("trigger")
    fired = bool(row.get("trigger_fired_this_tick"))
    triggers = [trigger] if (trigger and fired) else []
    bull_p = passed_scoring_peak("bull", action, row.get("bull_score", 0), trigger, fired)
    bear_p = passed_scoring_peak("bear", action, row.get("bear_score", 0), trigger, fired)
    sig = {
        "_doc": "SHADOW (scoring-peak derivation, BOLD ledger) -- proves looser-than-production "
                "passes. WATCH-only; not consumed by the live fleet until after-close deploy.",
        "tick_id": row.get("tick_id"), "date": today,
        "time_et": row.get("time_et", now.strftime("%H:%M")), "spot": row.get("spy"),
        "vix": row.get("vix"), "ribbon_stack": row.get("ribbon_stack"),
        "production_action": action, "setup_name": row.get("setup_name"),
        "bull": {"passed": bull_p, "score": row.get("bull_score", 0),
                 "triggers_fired": triggers if bull_p else []},
        "bear": {"passed": bear_p, "score": row.get("bear_score", 0),
                 "triggers_fired": triggers if bear_p else []},
        "written_at": now.strftime("%Y-%m-%dT%H:%M:%S%z"), "source": "shadow-scoring-peak-bold-v1",
    }
    SHADOW_OUT.write_text(json.dumps(sig, indent=2), encoding="utf-8")
    return sig


if __name__ == "__main__":
    s = build()
    print(json.dumps({"production_action": s.get("production_action"),
                      "tick_id": s.get("tick_id"), "spot": s.get("spot"),
                      "source": s.get("source"), "written_at": s.get("written_at")}))
