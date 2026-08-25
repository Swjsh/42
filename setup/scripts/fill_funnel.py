"""fill_funnel.py -- the per-day FILL FUNNEL: ticks -> signals -> ENTER -> attempted
-> accepted -> filled -> exited, per account. Pure-ledger, $0, read-only.

THE INSTRUMENT THAT RETIRES "is it actually trading?" (OP-33e). 2026-07-01 ground
truth vs what the surfaces said: core-decisions had 766 rows / 10 ENTER_BEAR (all
PLACE_FAIL) and the fleet arms filled + exit-managed 4 ENTER_BULL at 11:22 -- yet
the EOD journal claimed "ENTER signals: 0" and loop-state said ticks_today=0.
Every number here is re-derived from the decision ledgers J can open himself:

  automation/state/core-decisions.jsonl          (heartbeat core: safe + bold)
  automation/state/fleet/<arm>/decisions.jsonl   (fleet arms; exit_pass rows carry
                                                  broker-truth fills + exit actions)

Funnel stage definitions (deterministic, no LLM):
  ticks      = rows for the day
  signals    = rows with a fired trigger OR a non-HOLD verdict/action
  enter      = verdict/action startswith ENTER
  attempted  = ENTER rows where a LIVE placement was actually tried
  accepted   = attempted rows whose broker response carries an order id
  filled     = distinct symbols with broker fill evidence (filled_qty>0 on the
               order, or an exit_pass row showing open_qty>0 at the broker)
  exited     = distinct filled symbols with a placed exit action (SELL_ALL/TP/...)

Verdict rules (shared by self_check + gamma_glance + guard tests):
  RED       any account with attempted>0 and accepted==0  (placement broken) --
            UNLESS every failed attempt carries bracket_err/oto_err, i.e. the
            retired bracket->oto->simple ladder produced it: the shipped
            _place_simple_entry code never emits those, so such a day is PROVABLY
            pre-fix history (DEGRADED "PLACEMENT PRE-FIX ARTIFACT", not a live RED).
  DEGRADED  any ENTER after the 15:00 ET entry ceiling; a pre-fix retired-ladder
            placement day; or (at/after EOD) a fill with no exit record
  GREEN     ENTER>0 and none of the above
  IDLE      no ENTER fired (not a fault by itself)

CLI:  backtest/.venv/Scripts/python.exe setup/scripts/fill_funnel.py [--date YYYY-MM-DD] [--write]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
sys.path.insert(0, str(REPO / "setup" / "scripts"))

try:
    from et_clock import et_now
except Exception:  # noqa: BLE001
    def et_now() -> dt.datetime:  # fail-open (rig is on Mountain; never Bash TZ)
        return dt.datetime.utcnow() - dt.timedelta(hours=4)
try:
    from arm_display import display_name_for_label
except Exception:  # noqa: BLE001
    def display_name_for_label(label): return label

ENTRY_CEILING_HHMM = "15:00"   # ENTER after this = DEGRADED (0DTE theta cliff)
EOD_HHMM = "16:00"             # after this, a fill with no exit record = DEGRADED

# FALSE-RED FIX (2026-07-07): a CORE ENTER row's exec dict is TRUTHY for every
# outcome -- including pure-skip statuses that NEVER call the broker (NOT_FLAT,
# SKIP_*). Counting those as `attempted` made a flat-veto day (already holding a
# position -> NOT_FLAT) read as attempted>0 & accepted==0 -> a false "PLACEMENT
# BROKEN" RED that reached gamma_glance + self_check while the broker was never
# touched. `attempted` now requires a status that is a REAL placement OUTCOME:
# the order was sent (PLACED / a broker reject in PLACE_FAIL) or it died at the
# last pre-broker sizing/pricing/risk gate that is genuinely PART of the placement
# attempt (NO_PREMIUM). A skip that bails BEFORE that (NOT_FLAT and
# every SKIP_*) is NOT a placement attempt. Anything unrecognized fails OPEN to
# "attempted" so a NEW real-fault status can never be silently swallowed.
#
# SECOND FALSE-RED FIX (2026-07-08): RISK_DENY_* was counted as `attempted`,
# so a PDT-jail day (13 ENTER, all correctly refused by the risk gate) read as
# attempted>0 & accepted==0 -> "PLACEMENT BROKEN" spam to Discord while Rule 7
# was doing its job. RISK_DENY_* is now its own funnel stage: `rule_blocked`,
# with its own informational flag -- disclosed, never RED (guard:
# test_fill_funnel_guard.py::test_risk_deny_is_rule_block_not_broken).
_CORE_ATTEMPT_STATUSES = frozenset({
    "PLACED", "PLACE_FAIL", "PLACING", "NO_PREMIUM",
})
# statuses that are provably a skip BEFORE any broker interaction -> never attempted
_CORE_SKIP_STATUSES = frozenset({
    "NOT_FLAT", "NO_CREDS", "EQUITY_FETCH_FAIL", "WOULD_PLACE",
})


def _core_is_rule_block(status: str) -> bool:
    """True iff the exec status is the risk gate REFUSING the entry (RISK_DENY_*:
    PDT, per-trade cap, kill switch...). That is rule ENFORCEMENT working, not a
    placement fault -- counted in its own `rule_blocked` stage."""
    return (status or "").upper().startswith("RISK_DENY")


# THIRD FALSE-RED FIX (2026-07-16, SIX-ACCOUNT-DAILY-HYPOTHESIS-REDESIGN.md §5 row 5):
# a fleet ENTER row's placement dict is mode="LIVE" for EVERY outcome of _place_live
# (fleet_live.py) -- including the entry-time floor/ceiling skips, which bail BEFORE
# any broker call (mirrors the CORE NOT_FLAT/SKIP_* false-RED fixed 2026-07-07 above).
# The fleet-path attempted check previously trusted mode=="LIVE" alone, so a correctly
# time-gated SKIP_EARLY_ENTRY/SKIP_LATE_ENTRY row was counted as `attempted` with
# `accepted`==0 -> a false "PLACEMENT BROKEN" RED even though the broker was never
# touched. `reason` now gates the same way `status` does on the core side.
_FLEET_SKIP_REASONS = frozenset({"SKIP_EARLY_ENTRY", "SKIP_LATE_ENTRY"})


def _fleet_is_attempt(ex: dict) -> bool:
    """True iff a FLEET placement dict (fleet_live.py's `_place_live` return value)
    represents a real placement OUTCOME. mode=="LIVE" alone is NOT sufficient -- the
    entry-ceiling/floor skips also return mode="LIVE", placed=False with reason
    SKIP_EARLY_ENTRY/SKIP_LATE_ENTRY, never calling the broker."""
    if str(ex.get("mode", "LIVE")).upper() != "LIVE":
        return False
    return str(ex.get("reason", "")).upper() not in _FLEET_SKIP_REASONS


def _core_is_attempt(status: str) -> bool:
    """True iff a CORE exec status represents a real placement OUTCOME (the broker
    was called OR the attempt died at the last in-placement gate). NOT_FLAT and
    every SKIP_* bail before the broker and are NOT attempts; RISK_DENY_* is a
    rule-block, not an attempt. Fail-OPEN: an unrecognized status counts as an
    attempt so a genuinely-broken new status still trips the RED (OP-33)."""
    s = (status or "").upper()
    if s in _CORE_ATTEMPT_STATUSES:
        return True
    if s in _CORE_SKIP_STATUSES or s.startswith("SKIP_") or _core_is_rule_block(s):
        return False
    return True  # unknown status -> fail open (never hide a possible real fault)


# ---------------------------------------------------------------------------
# WHY-THIS-ARM-DID-OR-DID-NOT-TRADE  (2026-08-06, EOD-2026-08-05-SILENT-ARMS)
# ---------------------------------------------------------------------------
# THE INSTRUMENT THAT RETIRES "why didn't arm X trade today?" (OP-33e -- a repeated
# question from J is a MISSING INSTRUMENT, not a query). The funnel above already
# proved WHETHER an arm traded; it never said WHY NOT, so every silent-arm day cost
# a manual ledger dig. Ground truth 2026-08-05: bold-2 and safe-3 took ZERO legs
# while three siblings took 29 off the same shared signal, and the two silences had
# COMPLETELY DIFFERENT causes -- bold-2 = free-model veto (13/16 ENTER verdicts)
# then PDT (3/16); safe-3 = its own accounts.json gate_override (30 refusals:
# min_triggers=2 + require_confluence_or_sequence) with the risk gate never even
# consulted. One-cause-fits-all reporting would have been wrong for both.
#
# STRICTLY ADDITIVE + FAIL-OPEN: writes only the per-account "why" key and renders
# extra lines. It never touches a funnel STAGE, never appends to `flags`, and never
# influences `verdict` -- self_check / gamma_glance / gamma_narrative / eod_fallback
# read those and must behave byte-identically (guard:
# test_silence_diagnosis_is_additive_stages_and_verdict_unchanged).

# Canonical terminal-cause taxonomy. Ordered MOST->LEAST informative: when a tick
# could map to several, the first match wins, so a real gate always beats "no setup".
_WHY_NO_SETUP = "NO_SETUP"                 # nothing fired -- the market, not the engine
_WHY_NO_FEED = "NO_LIVE_SIGNAL"            # shared-signal missing/stale this tick
_WHY_GATE = "ARM_GATE"                     # this arm's own accounts.json gate_override
_WHY_MODEL_VETO = "FREE_MODEL_VETO"        # the 2 free-model entry veto
_WHY_PDT = "RISK_DENY_PDT"                 # PDT rule (Rule 7)
_WHY_RISK = "RISK_DENY_OTHER"              # any other risk_gate deny
_WHY_NOT_FLAT = "NOT_FLAT"                 # already in a position (C11)
_WHY_KILLED = "KILL_SWITCH"                # daily-loss breaker tripped (Rule 5)
_WHY_SKIP = "ENTRY_GATE_SKIP"              # SKIP_* entry-gate refusals
_WHY_ERROR = "ERROR"                       # broker/feed error this tick
_WHY_TRADED = "TRADED"

_WHY_PROSE = {
    _WHY_NO_SETUP: "no qualifying setup fired",
    _WHY_NO_FEED: "no live shared signal",
    _WHY_GATE: "blocked by this arm's own gate_override",
    _WHY_MODEL_VETO: "vetoed by the free-model entry check",
    _WHY_PDT: "PDT rule blocked the day-trade (Rule 7)",
    _WHY_RISK: "refused by the risk gate",
    _WHY_NOT_FLAT: "already holding a position (not flat)",
    _WHY_KILLED: "daily-loss kill switch tripped (Rule 5)",
    _WHY_SKIP: "refused by an entry gate",
    _WHY_ERROR: "broker/feed error",
}


# DARK-ARM FIX (2026-08-25, REFUSED-CORE-ENTRY-SHOWS-REASON): a real 2026-08-25
# ground truth (5x bold ENTER_BULL, exec.status=SKIP_MIN_PREMIUM_FLOOR, premium
# 0.07-0.11 vs floor 0.30) folded into the generic ENTRY_GATE_SKIP bucket read as
# "dominant cause ENTRY_GATE_SKIP (11x): refused by an entry gate" -- a human
# cannot tell "correctly refused an 11-cent lottery ticket" from "the arm is
# dark". An exec.status SKIP_* is a POST-SCORING placement-stage refusal (the
# row passed scoring + every entry gate and reached _execute, then bailed at the
# LAST pre-broker check: SKIP_MIN_PREMIUM_FLOOR / SKIP_QUALITY_LOCK /
# SKIP_DUPLICATE_CLAIM) -- a DIFFERENT failure stage from the generic PRE-execute
# action-level entry-gate skips (SKIP_LATE_ENTRY/SKIP_EARLY_ENTRY/
# SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY/...), which never populate `exec` at all.
# It is now reported by its OWN exact status name so the funnel line reads as a
# decision, not an absence. Checked BEFORE the generic `action` scan because
# heartbeat_core.py mirrors the placement-stage status into `action` too (a real
# refusal carries the SAME string in both fields) -- scanning action first would
# re-swallow it into the generic bucket. Guard: test_fill_funnel_skip_reason_2026_08_25.py.
_PLACEMENT_SKIP_PROSE = ("passed scoring and every entry gate, then was refused at "
                         "the last pre-broker placement check")


def _cause_prose(cause: str) -> str:
    """Human prose for a `why` cause -- the fixed taxonomy's own text, or the
    generic placement-skip prose for a dynamic named exec-status SKIP_* cause."""
    return _WHY_PROSE.get(cause, _PLACEMENT_SKIP_PROSE)


def _why_core(row: dict) -> str:
    """Terminal cause for ONE core (heartbeat_core) tick. Fail-open -> NO_SETUP.
    See the DARK-ARM FIX comment above for the exec.status SKIP_* named-cause rule."""
    action = str(row.get("action") or "").upper()
    exec_status_raw = str((row.get("exec") or {}).get("status") or "")
    exec_status = exec_status_raw.upper()
    if exec_status.startswith("SKIP_"):
        return exec_status_raw
    for s in (action, exec_status):
        if not s:
            continue
        if s.startswith("PLACED") or s == "ACCEPTED":
            return _WHY_TRADED
        if s == "VETOED_BY_MODELS":
            return _WHY_MODEL_VETO
        if s == "RISK_DENY_PDT":
            return _WHY_PDT
        if s.startswith("RISK_DENY"):
            return _WHY_RISK
        if s == "NOT_FLAT":
            return _WHY_NOT_FLAT
        if s.startswith("SKIP_"):
            return _WHY_SKIP
        if s == "ERROR" or s.startswith("PLACE_FAIL"):
            return _WHY_ERROR
    return _WHY_NO_SETUP


# Fixed taxonomy constants -- anything `_why_core`/`_why_fleet` returns that is NOT
# in this set is a dynamic named exec-status SKIP_* cause (core only, see above).
_FIXED_WHY_CAUSES = frozenset({
    _WHY_NO_SETUP, _WHY_NO_FEED, _WHY_GATE, _WHY_MODEL_VETO, _WHY_PDT, _WHY_RISK,
    _WHY_NOT_FLAT, _WHY_KILLED, _WHY_SKIP, _WHY_ERROR, _WHY_TRADED,
})


def _skip_detail(ex: dict) -> str:
    """Discriminating numbers/text a CORE SKIP_* exec dict carries (e.g. premium vs
    the min_entry_premium floor) so a refusal renders as a decision, not a bare
    status name. Prefers the exec dict's OWN human 'reason'/'detail' string
    (SKIP_QUALITY_LOCK/SKIP_DUPLICATE_CLAIM carry one); falls back to generic
    key=value scalars (SKIP_MIN_PREMIUM_FLOOR's premium/min_entry_premium) --
    nested dicts/lists are excluded as noise, not signal. Fail-open -> ''."""
    for key in ("reason", "detail"):
        v = ex.get(key)
        if isinstance(v, str) and v:
            return v
    parts = []
    for k, v in ex.items():
        if k in ("status", "symbol", "broker") or v is None:
            continue
        if isinstance(v, (dict, list)):
            continue
        parts.append(f"{k}={v}")
    return ", ".join(parts)


def _why_fleet(row: dict) -> str:
    """Terminal cause for ONE fleet (fleet_live) tick. Fail-open -> NO_SETUP."""
    action = str(row.get("action") or "").upper()
    if action.startswith("ENTER"):
        return _WHY_TRADED
    if action == "ERROR":
        return _WHY_ERROR
    if row.get("killed"):
        return _WHY_KILLED
    code = str(row.get("risk_code") or "").upper()
    if code == "NOT_FLAT":
        return _WHY_NOT_FLAT
    if code.endswith("PDT"):
        return _WHY_PDT
    if code and code not in ("ALLOW", "NONE"):
        return _WHY_RISK
    reason = str(row.get("reason") or "").lower()
    if reason.startswith("gate:") or reason.startswith("gate "):
        return _WHY_GATE
    if "no live signal" in reason:
        return _WHY_NO_FEED
    if "risk_gate denied" in reason:
        return _WHY_RISK
    return _WHY_NO_SETUP


def _silence_diagnosis(rows: list[dict], kind: str, f: dict) -> dict:
    """Per-arm 'why did this arm trade / not trade today' one-liner + evidence counts.

    Counts EVERY tick by terminal cause, then reports the dominant BLOCKING cause
    among the ticks where a setup actually existed (i.e. excluding NO_SETUP /
    NO_LIVE_SIGNAL, which say 'the market gave us nothing', not 'the engine refused').
    That distinction is the whole point: a day with 384 NO_SETUP ticks is a quiet
    tape; a day with 30 ARM_GATE refusals is a configuration decision.

    Never raises -- any malformed row degrades to NO_SETUP for that tick alone.
    """
    counts: Counter = Counter()
    detail: dict[str, Counter] = {}
    for r in rows:
        try:
            cause = _why_core(r) if kind == "core" else _why_fleet(r)
        except Exception:  # noqa: BLE001 -- one bad row must never blind the instrument
            cause = _WHY_NO_SETUP
        counts[cause] += 1
        # a dynamic named exec-status SKIP_* cause (2026-08-25 fix, core only --
        # _why_fleet never returns one) gets its OWN discriminating-numbers detail
        # (premium vs floor, etc.) instead of the setup-pass `reason` text, which
        # narrates a DIFFERENT stage (scoring) and would misleadingly suggest the
        # row wasn't refused at all.
        named_skip = kind == "core" and cause not in _FIXED_WHY_CAUSES
        if named_skip:
            sd = _skip_detail(r.get("exec") or {})
            txt = (cause + (f" ({sd})" if sd else ""))[:90]
            detail.setdefault(cause, Counter())[txt] += 1
        elif cause in (_WHY_GATE, _WHY_RISK, _WHY_SKIP, _WHY_ERROR):
            txt = str(r.get("reason") or (r.get("exec") or {}).get("reason")
                      or r.get("action") or "")[:90]
            detail.setdefault(cause, Counter())[txt] += 1
    traded = bool(f.get("filled", 0) or f.get("extra_placed_total", 0)
                  or f.get("accepted", 0))
    blockers = [(c, n) for c, n in counts.most_common()
                if c not in (_WHY_TRADED, _WHY_NO_SETUP, _WHY_NO_FEED)]
    quiet = counts.get(_WHY_NO_SETUP, 0) + counts.get(_WHY_NO_FEED, 0)
    if traded:
        # Attribute fills to the pipeline that actually sent them. Saying
        # "N filled from M ENTER verdicts" when some fills came off extra_exec
        # invites the reader to credit the primary setup for a secondary
        # strategy's trade (2026-08-06 scar -- see filled_primary/filled_extra).
        n_pri = int(f.get("filled_primary", 0) or 0)
        n_ext = int(f.get("filled_extra", 0) or 0)
        n_una = int(f.get("filled_unattributed", 0) or 0)
        head = (f"TRADED -- {f.get('filled', 0)} filled / {f.get('exited', 0)} exited"
                f" ({n_pri} from {f.get('enter', 0)} primary ENTER verdicts")
        if n_ext:
            setups = ", ".join(f"{k} x{v}" for k, v in
                               sorted(f.get("extra_fill_setups", {}).items()))
            head += f"; {n_ext} from SECONDARY extra_exec [{setups}] -- NOT a primary ENTER"
        if n_una:
            head += f"; {n_una} UNATTRIBUTED (no placement row -- manual or lost)"
        head += ")"
        if blockers:
            head += (f"; also blocked {sum(n for _, n in blockers)}x ("
                     + ", ".join(f"{n}x {c}" for c, n in blockers[:3]) + ")")
        top = _WHY_TRADED
    elif not blockers:
        head = (f"DID NOT TRADE -- {_WHY_PROSE[_WHY_NO_SETUP]} on any of {len(rows)} ticks "
                f"(quiet tape, not an engine refusal)")
        top = _WHY_NO_SETUP
    else:
        top, n_top = blockers[0]
        extra = ", ".join(f"{n}x {c}" for c, n in blockers[1:3])
        head = (f"DID NOT TRADE -- dominant cause {top} ({n_top}x): {_cause_prose(top)}"
                + (f"; then {extra}" if extra else "")
                + f". {quiet} of {len(rows)} ticks had no setup at all.")
        ex = detail.get(top)
        if ex:
            head += " e.g. " + "; ".join(f'"{t}" x{n}' for t, n in ex.most_common(2))
    return {
        "traded": traded,
        "top_cause": top,
        "headline": head,
        "cause_counts": dict(counts),
        "blocking_ticks": sum(n for _, n in blockers),
        "quiet_ticks": quiet,
        "examples": {c: dict(v.most_common(3)) for c, v in detail.items()},
    }


# ---------------------------------------------------------------------------
# ledger readers
# ---------------------------------------------------------------------------

def _read_jsonl_day(path: Path, day: str) -> list[dict]:
    """JSONL rows whose ts_et starts with the day. Fail-open -> []."""
    rows: list[dict] = []
    try:
        for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
            ln = ln.strip()
            if not ln or day not in ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(o, dict) and str(o.get("ts_et", "")).startswith(day):
                rows.append(o)
    except OSError:
        pass
    return rows


def _hhmm(ts_et: str) -> str:
    """'2026-07-01T15:51:02' or '...T11:22:01.4-04:00' -> '15:51' / '11:22'."""
    return ts_et.split("T", 1)[1][:5] if "T" in ts_et else ""


def _fail_reason(broker: dict) -> str:
    """Verbatim broker rejection text (the PLACE_FAIL truth J needs to see)."""
    if not broker:
        return "no broker response recorded"
    msgs: list[str] = []
    if broker.get("_error"):
        msgs.append(str(broker["_error"]))
    for k in ("bracket_err", "oto_err", "simple_err"):
        e = broker.get(k)
        if isinstance(e, dict):
            body = e.get("_body") if isinstance(e.get("_body"), dict) else e
            m = (body or {}).get("message") or e.get("message")
            if m:
                msgs.append(f"{k}: {m}")
        elif e:
            msgs.append(f"{k}: {e}")
    return " | ".join(msgs) if msgs else "unknown (no error detail in ledger)"


# ---------------------------------------------------------------------------
# per-account funnel
# ---------------------------------------------------------------------------

def _acct_funnel(rows: list[dict], kind: str) -> dict:
    """Fold one account's day rows into funnel stages. kind: 'core' | 'fleet'."""
    f = {
        "ticks": len(rows), "signals": 0, "enter": 0, "rule_blocked": 0,
        "attempted": 0,
        "accepted": 0, "filled": 0, "exited": 0, "retired_ladder_fails": 0,
        "enter_events": [], "place_fail_reasons": [], "rule_block_reasons": [],
        "enters_after_ceiling": [], "open_fills_no_exit": [],
        "extra_setup_placed": {}, "extra_placed_total": 0,
        # FILL-PROVENANCE (2026-08-06): which PIPELINE produced each fill.
        "filled_primary": 0, "filled_extra": 0, "filled_unattributed": 0,
        "extra_fill_setups": {},
    }
    filled_syms: set[str] = set()
    exited_syms: set[str] = set()
    # symbol -> pipeline that sent the order ("primary" | setup name), so a fill
    # observed later via exit_pass broker-truth can be attributed to its origin.
    sym_origin: dict[str, str] = {}
    for r in rows:
        v = str((r.get("verdict") if kind == "core" else r.get("action")) or "")
        if r.get("triggers") or (v and v != "HOLD"):
            f["signals"] += 1
        # SECONDARY-SETUP VISIBILITY FIX (2026-07-22): core rows can carry an
        # `extra_exec` list -- non-primary setups (vwap_continuation,
        # bollinger_squeeze, vix_regime_dayside, gap_and_go...) scored + placed
        # on a path separate from the primary `verdict`/`exec` ENTER pipeline
        # this funnel otherwise tracks exclusively. Before this fix a day with
        # 0 primary ENTERs but several extra_exec PLACED orders read as IDLE/
        # "0 attempts, mystery 2 fills via exit_pass broker-truth" -- a C7
        # silent-success gap (ground truth 2026-07-22: core:safe showed
        # enter=0/attempted=0/accepted=0 while extra_exec fired 4 PLACED across
        # vwap_continuation + bollinger_squeeze). This does NOT change any
        # enter/attempted/accepted/rule_blocked stage (those stay scoped to the
        # primary pipeline, unchanged) -- it adds a SEPARATE, additive
        # attribution so secondary-setup activity is visible instead of silent.
        for ex in (r.get("extra_exec") or []):
            setup = str(ex.get("setup") or "?")
            action = str(ex.get("action") or "?")
            bucket = f["extra_setup_placed"].setdefault(setup, {})
            bucket[action] = bucket.get(action, 0) + 1
            if action == "PLACED":
                f["extra_placed_total"] += 1
                # remember WHICH secondary setup owns this symbol so its fill is
                # never silently read as a primary ENTER (2026-08-06 misattribution:
                # a bollinger_squeeze long was reported as a BULLISH_RECLAIM fire).
                esym = ((ex.get("exec") or {}).get("symbol")
                        or (ex.get("exec") or {}).get("sym"))
                if esym:
                    sym_origin.setdefault(str(esym), setup)
        # exit_pass rows carry broker-truth: open_qty>0 = we HOLD a fill;
        # a placed action (SELL_ALL / tp / stop) = the exit went to the broker.
        for ep in (r.get("exit_pass") or []):
            sym = ep.get("symbol")
            if not sym:
                continue
            try:
                if float(ep.get("open_qty") or 0) > 0:
                    filled_syms.add(sym)
            except (TypeError, ValueError):
                pass
            for a in (ep.get("actions") or []):
                if a.get("placed"):
                    exited_syms.add(sym)
        if not v.startswith("ENTER"):
            continue
        f["enter"] += 1
        ex = (r.get("exec") if kind == "core" else r.get("placement")) or {}
        broker = ex.get("broker") or {}
        rule_blocked = False
        if kind == "core":
            # only count a CORE ENTER as attempted when its exec status is a REAL
            # placement outcome -- NOT_FLAT / SKIP_* bail before the broker (they
            # were falsely counted, tripping a phantom PLACEMENT BROKEN RED);
            # RISK_DENY_* is rule enforcement -> its own stage, never an attempt.
            st = str(ex.get("status", ""))
            rule_blocked = bool(ex) and _core_is_rule_block(st)
            attempted = bool(ex) and _core_is_attempt(st)
        else:
            attempted = bool(ex) and _fleet_is_attempt(ex)
        accepted = bool(broker.get("id"))
        if rule_blocked:
            f["rule_blocked"] += 1
            f["rule_block_reasons"].append(str(ex.get("reason") or ex.get("status") or "risk gate deny"))
        if attempted:
            f["attempted"] += 1
        if accepted:
            f["accepted"] += 1
        elif attempted:
            f["place_fail_reasons"].append(_fail_reason(broker))
            # A rejection carrying bracket_err/oto_err was produced by the RETIRED
            # bracket->oto->simple ladder. The shipped _place_simple_entry path emits
            # only simple_err/_error (no order_class), so such an attempt is PROVABLY
            # pre-fix history, not a live fault -- and the code invariant is guarded
            # build-side (test_money_path_2026_07_01: AST test_no_place_bracket_call_*
            # + behavioral test_execute_first_and_only_order_call_is_simple_marketable),
            # so a regression re-adding the ladder REDs at build before it reaches here.
            if broker.get("bracket_err") or broker.get("oto_err"):
                f["retired_ladder_fails"] += 1
        # fill evidence on the entry order itself
        sym = ex.get("symbol") or broker.get("symbol")
        try:
            entry_filled = float(broker.get("filled_qty") or 0) > 0
        except (TypeError, ValueError):
            entry_filled = False
        if sym:
            sym_origin[str(sym)] = "primary"
        if sym and (entry_filled or broker.get("filled_at")):
            filled_syms.add(sym)
        hhmm = _hhmm(str(r.get("ts_et", "")))
        # DARK-ARM FIX (2026-08-25): a core ENTER whose exec.status is a named
        # placement-stage SKIP_* (SKIP_MIN_PREMIUM_FLOOR/SKIP_QUALITY_LOCK/
        # SKIP_DUPLICATE_CLAIM) is neither `attempted` nor `rule_blocked` (see the
        # comment above -- it bails BEFORE the broker, correctly), so it used to
        # fall through to the generic "NOT_ATTEMPTED" bucket here -- indistinguishable
        # from a truly dark/silent arm. Report the ACTUAL status by name instead, plus
        # the discriminating numbers it carries (premium vs floor, etc.), so the line
        # reads as a decision ("refused an 11-cent lottery ticket"), not an absence.
        # Fleet handling is untouched (kind == "core" only). Guard:
        # test_fill_funnel_skip_reason_2026_08_25.py.
        core_skip_status = None
        if kind == "core" and not (attempted or rule_blocked):
            st_raw = str(ex.get("status") or "")
            if st_raw.upper().startswith("SKIP_"):
                core_skip_status = st_raw
        ev = {
            "ts_et": r.get("ts_et"), "hhmm": hhmm, "verdict": v,
            "setup": r.get("setup") or r.get("setup_name"),
            "symbol": sym, "qty": ex.get("qty") or r.get("qty"),
            "status": ("ACCEPTED" if accepted
                       else (str(ex.get("status") or "PLACE_FAIL")
                             if (attempted or rule_blocked)
                             else (core_skip_status or "NOT_ATTEMPTED"))),
            "order_id": broker.get("id"),
            "reason": r.get("reason"),
            "skip_detail": _skip_detail(ex) if core_skip_status else None,
        }
        f["enter_events"].append(ev)
        # FALSE-CEILING-ALARM FIX (2026-07-20): a row whose `verdict` is ENTER_BEAR/
        # ENTER_BULL but was ALREADY correctly gated by heartbeat_core.py's own
        # _past_entry_ceiling check (core: rec["action"]="SKIP_LATE_ENTRY", never
        # reaching _execute -- no `exec` dict at all; fleet: fleet_live.py's
        # placement.reason="SKIP_LATE_ENTRY", placed=False, never reaching the broker)
        # is NOT a ceiling bypass -- it is the ceiling working. Flagging it as "ENTER
        # AFTER CEILING" was a producer/consumer mismatch: this funnel keys `v` off the
        # PRE-gate `verdict` field (line ~195), but the ceiling gate's verdict lives in
        # the POST-gate `action` (core) / `placement.reason` (fleet) field. 2026-07-20
        # ground truth: 6 core rows (5 safe + 1 bold) fired ENTER_BEAR 15:41-15:45 ET,
        # ALL correctly downgraded to action=SKIP_LATE_ENTRY with zero broker attempts
        # (attempted==0 above proves it) -- yet this line still spammed a false DEGRADED
        # "ENTER AFTER CEILING" to self_check/STATUS.md every 30 min. Only flag when the
        # gate did NOT catch it (a genuine bypass -- see test_real_day_enter_after_ceiling_
        # flagged's 2026-07-01 fixture: action="PLACE_FAIL", pre-dates this ceiling gate).
        # Guard: test_enter_after_ceiling_excludes_gated_skip_late_entry.
        gated_by_ceiling = (
            (kind == "core" and str(r.get("action") or "") == "SKIP_LATE_ENTRY")
            or (kind == "fleet" and str(ex.get("reason") or "").upper() == "SKIP_LATE_ENTRY")
        )
        if hhmm and hhmm > ENTRY_CEILING_HHMM and not gated_by_ceiling:
            f["enters_after_ceiling"].append(f"{hhmm} {v} {sym or '?'}")
    f["filled"] = len(filled_syms)
    f["exited"] = len(filled_syms & exited_syms)
    f["open_fills_no_exit"] = sorted(filled_syms - exited_syms)
    # FILL-PROVENANCE split (2026-08-06). `filled` counts distinct symbols the
    # broker confirms we held -- but the funnel's enter/attempted/accepted stages
    # are scoped to the PRIMARY pipeline only, so a secondary (extra_exec) fill
    # silently inflated `filled` above `accepted` and every downstream reader
    # attributed it to the primary setup. Ground truth 2026-08-06: core:safe read
    # "2 filled from 5 ENTER verdicts" when ENTER produced ONE fill (a bear put)
    # and the second was a bollinger_squeeze long off extra_exec -- which sent an
    # EOD reviewer chasing a BULLISH_RECLAIM/filter-5 story that never happened.
    for s in sorted(filled_syms):
        origin = sym_origin.get(s)
        if origin == "primary":
            f["filled_primary"] += 1
        elif origin:
            f["filled_extra"] += 1
            f["extra_fill_setups"][origin] = f["extra_fill_setups"].get(origin, 0) + 1
        else:
            # broker-truth fill with no placement row in this ledger (manual fill,
            # cross-day carry, or a lost row) -- disclosed, never silently bucketed.
            f["filled_unattributed"] += 1
    # WHY (2026-08-06): additive only -- computed AFTER every stage above is final, so
    # it can read them but can never change them. Fail-open to an absent key.
    try:
        f["why"] = _silence_diagnosis(rows, kind, f)
    except Exception:  # noqa: BLE001
        pass
    return f


# ---------------------------------------------------------------------------
# whole-day funnel + evaluation
# ---------------------------------------------------------------------------

_STAGES = ("ticks", "signals", "enter", "rule_blocked", "attempted", "accepted", "filled", "exited")


def compute_funnel(day: str | None = None, *, core_path: Path | None = None,
                   fleet_dir: Path | None = None, now: dt.datetime | None = None) -> dict:
    """Compute the per-day funnel. All inputs overridable for tests. Fail-open."""
    now = now or et_now()
    day = day or now.strftime("%Y-%m-%d")
    core_path = core_path or (STATE / "core-decisions.jsonl")
    fleet_dir = fleet_dir or (STATE / "fleet")

    accounts: dict[str, dict] = {}
    core_rows_all = _read_jsonl_day(core_path, day)
    # SYNTHETIC-ROW QUARANTINE (2026-08-06). Diagnostic / gym-harness / guard-test
    # invocations write into the SAME live core-decisions.jsonl as production ticks,
    # but carry armed=false AND core_tick_id=null (a real tick always stamps both).
    # Ground truth 2026-08-06: two such rows at 04:16:32 ET (spy pinned 751.0, vix
    # 16.0, spread 10) inflated safe's tick count and, worse, contributed a phantom
    # `bollinger_squeeze PLACED` with a null exec -- so the secondary-setup line read
    # "2 PLACED" when exactly ONE order reached the broker. Quarantined, not dropped:
    # the count is reported so a flood of them can never be silently swallowed (C7).
    def _is_synthetic(r: dict) -> bool:
        return r.get("armed") is False and r.get("core_tick_id") is None

    core_rows = [r for r in core_rows_all if not _is_synthetic(r)]
    n_synthetic = len(core_rows_all) - len(core_rows)
    for acct in sorted({str(r.get("account") or "core") for r in core_rows}):
        accounts[f"core:{acct}"] = _acct_funnel(
            [r for r in core_rows if str(r.get("account") or "core") == acct], "core")
    try:
        arm_files = sorted(fleet_dir.glob("*/decisions.jsonl"))
    except OSError:
        arm_files = []
    for p in arm_files:
        rows = _read_jsonl_day(p, day)
        if rows:
            accounts[f"fleet:{p.parent.name}"] = _acct_funnel(rows, "fleet")

    totals = {s: sum(a[s] for a in accounts.values()) for s in _STAGES}
    totals["extra_placed_total"] = sum(a.get("extra_placed_total", 0) for a in accounts.values())
    funnel = {
        "date": day,
        "generated_at_et": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "accounts": accounts,
        "totals": totals,
        "synthetic_core_rows_excluded": n_synthetic,
        "sources": {"core": str(core_path), "fleet": str(fleet_dir)},
    }
    funnel["flags"], funnel["verdict"] = _evaluate(funnel, now)
    return funnel


def _evaluate(funnel: dict, now: dt.datetime) -> tuple[list[str], str]:
    """Shared verdict rules -- see module docstring."""
    flags: list[str] = []
    red = False
    day = funnel["date"]
    at_eod = (now.strftime("%Y-%m-%d") > day) or (
        now.strftime("%Y-%m-%d") == day and now.strftime("%H:%M") >= EOD_HHMM)
    for name, a in funnel["accounts"].items():
        if a.get("rule_blocked", 0):
            reasons = Counter(a.get("rule_block_reasons", []))
            top = "; ".join(f"{n}x {r[:120]}" for r, n in reasons.most_common(2))
            flags.append(f"RULE-BLOCKED[{name}]: {a['rule_blocked']} ENTER refused by the risk "
                         f"gate (rule enforcement working, NOT a placement fault): {top}")
        if a["attempted"] > 0 and a["accepted"] == 0:
            reasons = Counter(a["place_fail_reasons"])
            top = "; ".join(f"{n}x {r[:120]}" for r, n in reasons.most_common(2))
            if a.get("retired_ladder_fails", 0) == a["attempted"]:
                # EVERY failed attempt used the retired bracket/oto ladder -> this day is
                # pre-fix history (current code is simple-first). DEGRADED, not a live RED:
                # surfaced for J's visibility but does not falsely flag placement dead.
                flags.append(f"PLACEMENT PRE-FIX ARTIFACT[{name}]: {a['attempted']} attempted via the "
                             f"retired bracket/oto ladder (current code is simple-first) -- stale pre-fix "
                             f"decisions, not a live fault. Reasons: {top}")
            else:
                red = True
                flags.append(f"PLACEMENT BROKEN[{name}]: {a['enter']} ENTER, "
                             f"{a['attempted']} attempted, 0 broker-accepted. Reasons: {top}")
        if a["enters_after_ceiling"]:
            flags.append(f"ENTER AFTER CEILING[{name}]: {len(a['enters_after_ceiling'])} ENTER "
                         f"after {ENTRY_CEILING_HHMM} ET: {a['enters_after_ceiling'][:3]}")
        if at_eod and a["open_fills_no_exit"]:
            flags.append(f"FILL WITHOUT EXIT AT EOD[{name}]: {a['open_fills_no_exit']} "
                         f"filled but no exit record in the ledger.")
    if red:
        return flags, "RED"
    if flags:
        return flags, "DEGRADED"
    # IDLE-MISCLASSIFICATION FIX (2026-07-22): verdict used to key off `enter`
    # alone -- blind to (a) broker-truth fills/exits seen only via exit_pass
    # (no primary ENTER row at all) and (b) extra_exec secondary-setup PLACED
    # orders (see the extra_setup_placed comment above). Ground truth 2026-07-22:
    # core:safe read enter=0/attempted=0/accepted=0 -> this line said IDLE, and
    # gamma-narrative.json/facts_digest propagated "the system stayed idle" to
    # J's narrative -- while the SAME day had 2 real broker-truth fills+exits
    # and 4 extra_exec PLACED orders (vwap_continuation/bollinger_squeeze).
    # "Real trading activity happened" now means enter>0 OR filled>0 OR an
    # extra-setup PLACED order fired; IDLE is reserved for a day with none of
    # the three (test_idle_day_is_not_a_fault pins the genuine-idle case).
    real_activity = (funnel["totals"]["enter"] > 0 or funnel["totals"]["filled"] > 0
                     or funnel["totals"].get("extra_placed_total", 0) > 0)
    return flags, ("GREEN" if real_activity else "IDLE")


# ---------------------------------------------------------------------------
# trades-CSV P&L (deterministic; feeds the EOD quant section)
# ---------------------------------------------------------------------------

def _trades_today(csv_path: Path, day: str, default_header: list[str] | None = None) -> list[dict]:
    """Today's rows from a trades CSV. Tolerates a headerless file (trades-aggressive)."""
    import csv as _csv
    out: list[dict] = []
    if not csv_path.exists():
        return out
    try:
        with open(csv_path, encoding="utf-8-sig", newline="") as fh:
            rdr = _csv.reader(fh)
            rows = [r for r in rdr if r]
    except OSError:
        return out
    if not rows:
        return out
    if rows[0] and rows[0][0].strip().lower() == "date":
        header, data = rows[0], rows[1:]
    else:
        header, data = (default_header or []), rows
    for r in data:
        if not r or not r[0].startswith(day):
            continue
        d = {header[i].strip(): r[i] for i in range(min(len(header), len(r)))} if header else {}
        d["_raw"] = r
        out.append(d)
    return out


_TRADES_HEADER = ["date", "time_entry", "time_exit", "setup", "contract", "dte", "strike",
                  "c_or_p", "qty", "entry_px", "exit_px", "premium_paid", "premium_received",
                  "dollar_pnl"]


def _pnl_statement_today(day: str, repo: Path) -> "dict | None":
    """T1 broker-truth per-day P&L (setup/scripts/broker_fills.py's pnl-statement.json), or
    None if that file doesn't exist yet or has no entry for this day."""
    path = repo / "automation" / "state" / "pnl-statement.json"
    if not path.exists():
        return None
    try:
        stmt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return stmt.get("per_day", {}).get(day) or None


def trades_pnl_today(day: str, repo: Path | None = None) -> dict:
    """P&L truth for the day. PRIMARY SOURCE (T2 rewire, HANDOFF-2026-07-09-TRUTH-AND-EXITS,
    ground rule 2): setup/scripts/broker_fills.py's automation/state/pnl-statement.json --
    Alpaca /account/activities/FILL, broker-truth. journal/trades.csv is used ONLY as a
    fallback when T1 has no entry for this day (e.g. Gamma_BrokerFills hasn't fired yet for
    a historical date) -- it is never the primary source, since it depends on a separate,
    less-reliable EOD reconciliation workflow."""
    repo = repo or REPO
    per_day = _pnl_statement_today(day, repo)
    if per_day:
        by_arm = []
        total = 0.0
        for arm, stats in sorted(per_day.items()):
            total += stats.get("realized_pnl", 0.0)
            by_arm.append({"arm": arm, "n_round_trips": stats.get("n_round_trips", 0),
                           "realized_pnl": stats.get("realized_pnl", 0.0),
                           "engine_pnl": stats.get("engine_pnl", 0.0),
                           "manual_pnl": stats.get("manual_pnl", 0.0)})
        return {"by_arm": by_arm, "total_pnl": round(total, 2),
                "source": "pnl-statement.json (T1, broker-truth)"}

    out = {"safe": [], "aggressive": [], "total_pnl": 0.0,
           "source": "journal/trades.csv (T1 fallback -- no pnl-statement.json entry for this day)"}
    for label, fname in (("safe", "trades.csv"), ("aggressive", "trades-aggressive.csv")):
        for t in _trades_today(repo / "journal" / fname, day, default_header=_TRADES_HEADER):
            pnl = 0.0
            try:
                pnl = float(t.get("dollar_pnl") or t["_raw"][13])
            except (KeyError, IndexError, TypeError, ValueError):
                pass
            out[label].append({
                "setup": t.get("setup") or (t["_raw"][3] if len(t["_raw"]) > 3 else "?"),
                "contract": t.get("contract") or (t["_raw"][4] if len(t["_raw"]) > 4 else "?"),
                "qty": t.get("qty") or (t["_raw"][8] if len(t["_raw"]) > 8 else "?"),
                "time_entry": t.get("time_entry") or (t["_raw"][1] if len(t["_raw"]) > 1 else "?"),
                "time_exit": t.get("time_exit") or (t["_raw"][2] if len(t["_raw"]) > 2 else "?"),
                "pnl": pnl,
            })
            out["total_pnl"] += pnl
    return out


# ---------------------------------------------------------------------------
# renderers + artifact
# ---------------------------------------------------------------------------

def _display_label(account_key: str) -> str:
    """account_key ('core:safe', 'fleet:safe-3', a raw arm id, ...) -> the SAME key with
    accounts.json's display_name appended when resolvable, e.g. 'fleet:safe-3' ->
    'fleet:safe-3 FLEET-TIGHT-S (OB0Q)'. The raw key is ALWAYS kept as the prefix -- nothing
    downstream keys off this rendered text (funnel['accounts']/funnel['flags'] keep the raw
    key), but keeping it makes correlating a report row with decisions.jsonl paths trivial.
    Fail-open -> the raw key unchanged when no display name is found (2026-07-17)."""
    resolved = display_name_for_label(account_key)
    return account_key if resolved == account_key else f"{account_key} {resolved}"


def render_text(funnel: dict) -> str:
    """One glanceable block (gamma_glance / CLI)."""
    t = funnel["totals"]
    out = [f"FUNNEL {funnel['date']}  [{funnel['verdict']}]  "
           f"ticks->sig->ENTER->ruleblk->attempt->accept->fill->exit"]
    for name, a in funnel["accounts"].items():
        out.append(f"  {_display_label(name):<34} {a['ticks']:>4} -> {a['signals']:>3} -> {a['enter']:>2} "
                   f"-> {a.get('rule_blocked', 0):>2} -> {a['attempted']:>2} -> {a['accepted']:>2} "
                   f"-> {a['filled']:>2} -> {a['exited']:>2}")
    out.append(f"  {'TOTAL':<14} {t['ticks']:>4} -> {t['signals']:>3} -> {t['enter']:>2} "
               f"-> {t.get('rule_blocked', 0):>2} -> {t['attempted']:>2} -> {t['accepted']:>2} "
               f"-> {t['filled']:>2} -> {t['exited']:>2}")
    if t.get("extra_placed_total", 0) > 0:
        parts = []
        for name, a in funnel["accounts"].items():
            for setup, actions in a.get("extra_setup_placed", {}).items():
                n = actions.get("PLACED", 0)
                if n:
                    parts.append(f"{setup}={n}PLACED[{name}]")
        out.append(f"  + secondary setups (extra_exec, outside the primary ENTER pipeline): "
                   f"{', '.join(parts)}")
    if funnel.get("synthetic_core_rows_excluded"):
        out.append(f"  + quarantined {funnel['synthetic_core_rows_excluded']} synthetic core "
                   f"row(s) (armed=false + core_tick_id=null: diagnostic/gym/guard writes "
                   f"into the LIVE ledger -- excluded from every stage above)")
    # WHY-EACH-ARM (2026-08-06): the standing answer to "why didn't arm X trade?"
    out.append("  why each arm did / did not trade:")
    for name, a in funnel["accounts"].items():
        why = a.get("why") or {}
        out.append(f"    {_display_label(name):<34} {why.get('headline', 'n/a')}")
    for fl in funnel["flags"]:
        out.append(f"  ! {fl}")
    return "\n".join(out)


def render_markdown(funnel: dict, repo: Path | None = None) -> str:
    """The deterministic QUANT section for the EOD digest/journal. Every number
    here is computed from the ledgers -- never LLM-generated (OP-33a)."""
    day = funnel["date"]
    t = funnel["totals"]
    pnl = trades_pnl_today(day, repo=repo)
    out = [
        "## Quantitative (deterministic -- computed from ledgers, not LLM)",
        "",
        f"Source ledgers: `core-decisions.jsonl` + `fleet/*/decisions.jsonl` + trades CSVs. "
        f"Generated {funnel['generated_at_et']} ET. Funnel verdict: **{funnel['verdict']}**.",
        "",
        "| account | ticks | signals | ENTER | rule-blocked | attempted | accepted | filled | exited |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, a in funnel["accounts"].items():
        out.append(f"| {_display_label(name)} | {a['ticks']} | {a['signals']} | {a['enter']} | "
                   f"{a.get('rule_blocked', 0)} | "
                   f"{a['attempted']} | {a['accepted']} | {a['filled']} | {a['exited']} |")
    out.append(f"| **TOTAL** | {t['ticks']} | {t['signals']} | {t['enter']} | "
               f"{t.get('rule_blocked', 0)} | "
               f"{t['attempted']} | {t['accepted']} | {t['filled']} | {t['exited']} |")
    # WHY-EACH-ARM (2026-08-06, EOD-2026-08-05-SILENT-ARMS): OP-33e standing answer to
    # "why did arm X not trade today" -- one row per arm, every day, no manual dig.
    out.append("")
    out.append("**Why each arm did / did not trade:**")
    out.append("")
    out.append("| account | traded | dominant cause | detail |")
    out.append("|---|---|---|---|")
    for name, a in funnel["accounts"].items():
        why = a.get("why") or {}
        out.append(f"| {_display_label(name)} | {'yes' if why.get('traded') else '**no**'} | "
                   f"`{why.get('top_cause', 'n/a')}` | {why.get('headline', 'n/a')} |")
    # ENTER events with times + verdicts
    events = [(name, ev) for name, a in funnel["accounts"].items() for ev in a["enter_events"]]
    out.append("")
    out.append(f"**ENTER events ({len(events)}):**")
    if events:
        for name, ev in sorted(events, key=lambda x: str(x[1].get("ts_et"))):
            out.append(f"- {ev['hhmm']} ET [{name}] {ev['verdict']} {ev.get('symbol') or '?'} "
                       f"x{ev.get('qty') or '?'} -> {ev['status']}"
                       + (f" (order {str(ev['order_id'])[:8]})" if ev.get("order_id") else "")
                       + (f" [{ev['skip_detail']}]" if ev.get("skip_detail") else "")
                       + (f" -- {ev['reason']}" if ev.get("reason") else ""))
    else:
        out.append("- none")
    # secondary-setup placements (extra_exec) -- outside the primary ENTER pipeline,
    # separately attributed here so they cannot silently under-report as IDLE (2026-07-22)
    out.append("")
    out.append(f"**Secondary-setup placements (extra_exec, {t.get('extra_placed_total', 0)} PLACED):**")
    extra_rows = []
    for name, a in funnel["accounts"].items():
        for setup, actions in a.get("extra_setup_placed", {}).items():
            extra_rows.append(f"- [{name}] {setup}: " + ", ".join(
                f"{cnt}x {act}" for act, cnt in sorted(actions.items())))
    out.extend(sorted(extra_rows) if extra_rows else ["- none"])
    # PLACE_FAIL reasons verbatim
    fails = Counter()
    for a in funnel["accounts"].values():
        for r in a["place_fail_reasons"]:
            fails[r] += 1
    out.append("")
    out.append("**PLACE_FAIL reasons (verbatim from broker):**")
    if fails:
        for r, n in fails.most_common():
            out.append(f"- {n}x {r}")
    else:
        out.append("- none")
    # flags
    out.append("")
    out.append("**Funnel flags:**")
    out.extend([f"- {fl}" for fl in funnel["flags"]] or ["- none"])
    # P&L -- broker-truth (T1) unless flagged as the CSV fallback
    out.append("")
    out.append(f"**P&L (source: {pnl.get('source', 'unknown')}):**")
    any_trade = False
    if "by_arm" in pnl:
        for r in pnl["by_arm"]:
            any_trade = True
            out.append(f"- [{_display_label(r['arm'])}] {r['n_round_trips']} round trip(s): "
                       f"{r['realized_pnl']:+.0f} (engine {r['engine_pnl']:+.0f} / "
                       f"manual {r['manual_pnl']:+.0f})")
    else:
        for label in ("safe", "aggressive"):
            for tr in pnl.get(label, []):
                any_trade = True
                out.append(f"- [{label}] {tr['setup']} {tr['contract']} x{tr['qty']} "
                           f"{tr['time_entry']}->{tr['time_exit']} ET: {tr['pnl']:+.0f}")
    if not any_trade:
        out.append("- no P&L rows for this day")
    out.append(f"- **Total recorded P&L: {pnl['total_pnl']:+.0f}**")
    out.append("")
    return "\n".join(out)


def write_artifact(funnel: dict, state_dir: Path | None = None) -> Path | None:
    """Persist the funnel JSON so J (and the dashboard) can glance at it. Fail-open."""
    state_dir = state_dir or STATE
    p = state_dir / f"fill-funnel-{funnel['date']}.json"
    try:
        p.write_text(json.dumps(funnel, indent=1), encoding="utf-8")
        return p
    except OSError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Per-day fill funnel from decision ledgers")
    ap.add_argument("--date", default=None, help="ET date YYYY-MM-DD (default today)")
    ap.add_argument("--write", action="store_true", help="also write automation/state/fill-funnel-{date}.json")
    ap.add_argument("--markdown", action="store_true", help="print the EOD quant markdown instead of the table")
    args = ap.parse_args()
    f = compute_funnel(args.date)
    print(render_markdown(f) if args.markdown else render_text(f))
    if args.write:
        p = write_artifact(f)
        print(f"[fill-funnel] wrote {p}" if p else "[fill-funnel] WARN artifact write failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
