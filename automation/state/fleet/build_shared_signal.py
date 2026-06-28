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
def _map_core_row(row: dict) -> dict:
    verdict = row.get("verdict")
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


def _ribbon_strategy_entries(bear: dict, bull: dict, spot) -> list[dict]:
    """ribbon_ride strategy-set entries re-keyed from the core row's passed side-blocks.
    One entry per passed side. No I/O — pure restructuring of data build() already mapped."""
    out: list[dict] = []
    for side, blk in (("P", bear), ("C", bull)):
        if blk.get("passed") is not True:
            continue
        trigs = list(blk.get("triggers_fired") or [])
        elite = bool(blk.get("confluence")) or any("sequence" in str(t).lower() for t in trigs)
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
        })
    return out


def _strategies_block(bear: dict, bull: dict, spot, now: datetime,
                      run_vwap: bool) -> list[dict]:
    """The FIX2 strategies[] set: every registered strategy evaluated independently this tick.

    ribbon_ride from the (already-mapped) side-blocks; vwap_continuation from the live
    detector pass (fleet_market). vwap is fail-safe: any import/fetch/detector miss simply
    omits it (never blocks the ribbon entries). run_vwap=False skips the network pass entirely
    (tests / offline) -- the ribbon entries still emit."""
    entries = _ribbon_strategy_entries(bear, bull, spot)
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


def _bold_passed_blocks(today: str, now: datetime) -> dict:
    """Scoring-peak passed blocks derived off the BOLD perception (the 'bold' core row).

    Returns {'bull': {...}, 'bear': {...}} mirroring build()'s side-block shape. Used
    only by the flagged dual-perception build(); resolves the perception-source confound
    (safe arms judged on the SAFE row, bold arms on the BOLD row). Under USE_CORE_LEDGER
    the bold row is the account=="bold" core-decisions row; on the revert path it falls
    back to the dead BOLD_DECISIONS LLM ledger."""
    if USE_CORE_LEDGER:
        row = _latest_today_decision(today, account="bold")
    else:
        global DECISIONS
        _safe, DECISIONS = DECISIONS, BOLD_DECISIONS
        try:
            row = _latest_today_decision(today)
        finally:
            DECISIONS = _safe
    if row is None:
        return {"bull": {"passed": False, "score": 0, "triggers_fired": [], "confluence": False},
                "bear": {"passed": False, "score": 0, "triggers_fired": [], "confluence": False}}
    action = row.get("action")
    trigs, trig0, fired = _row_trigger_args(row)
    has_conf = _has_confluence(trigs)
    bull_p = passed_scoring_peak("bull", action, row.get("bull_score", 0), trig0, fired)
    bear_p = passed_scoring_peak("bear", action, row.get("bear_score", 0), trig0, fired)
    setup = row.get("setup_name")
    return {
        "bull": {"passed": bull_p, "score": row.get("bull_score", 0),
                 "triggers_fired": trigs if bull_p else [],
                 "setup_name": setup if bull_p else None,
                 "confluence": bool(bull_p and has_conf)},
        "bear": {"passed": bear_p, "score": row.get("bear_score", 0),
                 "triggers_fired": trigs if bear_p else [],
                 "setup_name": setup if bear_p else None,
                 "confluence": bool(bear_p and has_conf)},
    }


def build(now: datetime | None = None, scoring_peak: bool | None = None,
          emit_strategies: bool | None = None, run_vwap: bool | None = None) -> dict:
    """Write shared-signal.json. DEFAULT (scoring_peak False/None and SCORING_PEAK_LIVE
    False) is byte-identical to v1. When scoring_peak is True (or the module flag is set)
    the signal ALSO carries dual-perception 'safe'/'bold' blocks for the loose arms.

    FIX2: when emit_strategies (or EMIT_STRATEGIES) is set, the signal ALSO carries a
    `strategies[]` set -- every registered strategy evaluated independently this tick (so
    plan_all sees the full set, not just the ribbon verdict). run_vwap gates JUST the
    network VWAP detector pass (tests pass run_vwap=False to stay offline)."""
    now = now or datetime.now(timezone.utc).astimezone(ET)
    today = now.strftime("%Y-%m-%d")
    use_peak = SCORING_PEAK_LIVE if scoring_peak is None else bool(scoring_peak)
    do_strats = EMIT_STRATEGIES if emit_strategies is None else bool(emit_strategies)
    do_vwap = RUN_VWAP if run_vwap is None else bool(run_vwap)
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
        OUT.write_text(json.dumps(sig, indent=2), encoding="utf-8")
        return sig

    action = row.get("action")
    triggers, _trig0, _fired = _row_trigger_args(row)
    has_conf = _has_confluence(triggers)
    setup = row.get("setup_name")

    bear_pass = action == "ENTER_BEAR"
    bull_pass = action == "ENTER_BULL"
    bear = {"passed": bear_pass, "score": row.get("bear_score", 0),
            "triggers_fired": triggers if bear_pass else [],
            "setup_name": setup if bear_pass else None,
            # CONFLUENCE FLAG (load-bearing): fleet_executor._is_elite treats a block ELITE
            # only if block['confluence'] is True OR a sequence_* trigger is present — it does
            # NOT read "confluence" as a trigger NAME. So emit the boolean here whenever a
            # confluence/multi_day_confluence trigger fired for this side.
            "confluence": bool(bear_pass and has_conf)}
    bull = {"passed": bull_pass, "score": row.get("bull_score", 0),
            "triggers_fired": triggers if bull_pass else [],
            "setup_name": setup if bull_pass else None,
            "confluence": bool(bull_pass and has_conf)}

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


def passed_scoring_peak(side: str, action, score, trigger, fired) -> bool:
    """Looser-than-production 'passed': production ENTERED this side, OR the score hit the
    peak threshold WITH a real entry-trigger fired (the quality gate that stops pure-score
    over-emission). This is what lets a loose arm take a setup production's gates blocked.
    Hard gates in _HARD_SKIP_VERDICTS always return False regardless of score."""
    if action in _HARD_SKIP_VERDICTS:
        return False
    enter = "ENTER_BULL" if side == "bull" else "ENTER_BEAR"
    peak = BULL_PEAK_THRESHOLD if side == "bull" else BEAR_PEAK_THRESHOLD
    trig_ok = bool(fired) and (trigger in ENTRY_TRIGGERS)
    return (action == enter) or (int(score or 0) >= peak and trig_ok)


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
