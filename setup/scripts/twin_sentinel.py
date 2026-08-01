"""twin_sentinel.py -- the deterministic RED/GREEN/YELLOW judge for the CRYPTO TWIN
(markdown/planning/TWIN-PROGRAM.md). Pure Python, $0, no LLM on this path.

WHY THIS EXISTS: B1/B2 are building the twin's SEE/DECIDE/ACT loop + scenario
scheduler + gauntlet (crypto_twin_core.py / crypto_twin_health.py /
crypto_twin_scenarios.py / twin_gauntlet.py / trade_autopsy.py / firm_brief.py --
this module NEVER edits any of those). Nobody is watching the watcher: if the twin
silently stops ticking, breaks its breaker, or loses its account, that's invisible
until someone happens to glance at a JSON file. This is the standing instrument that
retires that gap (OP-33e: "a repeated question is a missing instrument").

READ-ONLY CONSUMER CONTRACT -- this module reads, and NEVER writes, any of:
  * automation/state/twin-health.json           (TOP-LEVEL glance file, written by
    crypto_twin_health.py -- account_status, breaker_tripped, last_action, last_error)
  * automation/state/crypto-twin/decisions.jsonl (every tick, written by crypto_twin_core.py)
  * automation/state/crypto-twin/soak-log.jsonl  (hourly rollup, written by crypto_twin_health.py
    -- consumed by twin_review.py for cheap daily-shape context, NOT by evaluate() below;
    decisions.jsonl is the finer-grained, more authoritative source for the deterministic rules)
  * automation/state/crypto-twin/incidents.jsonl (NOT SHIPPED by any crew as of this
    build -- schema undefined upstream. See count_incidents_today()'s docstring for the
    schema-tolerant contract this module assumes so it keeps working whatever shape
    eventually lands. Currently always reads 0/0 -- fail-open, not a bug.)
  * automation/state/crypto-twin/path-coverage.json (SHIPPED mid-build by B1c,
    2026-07-11 -- schema CONFIRMED against the real producer, not guessed: see
    parse_path_coverage()'s docstring. Also the source of a SECOND, independently-
    re-derived incident signal -- per-branch status=="INCIDENT" -- combined with the
    incidents.jsonl scan above via max() in evaluate()'s RULE 3, since B1 wired the
    exact same derivation into twin-health.json's own `incidents_today` field
    concurrently with this build; re-deriving it here from the SAME raw file keeps
    this sentinel a genuinely separate judge instead of trusting B1's number back.)

Every reader below is fail-open: a missing/corrupt/absent file NEVER raises and NEVER
manufactures a false RED -- it degrades to "can't evaluate this rule" (recorded in
`notes`, not `reasons`) per the task's own instruction ("tolerate absence fail-open").
The one deliberate exception is TICK_GAP: an ENTIRELY missing/empty decisions.jsonl
IS itself a genuine freshness problem (the twin has never ticked, or its ledger is
gone) -- OP-25/C7 "silent success is failure" means that must read RED, not silently
skip. See evaluate()'s RULE 1 for the exact reasoning.

VERDICT RULES (RED wins over YELLOW wins over GREEN):
  RED    TICK_GAP          last tick age > TICK_GAP_RED_MINUTES (20), or no tick ever
  YELLOW LOW_UPTIME         today's UTC-day tick count < LOW_UPTIME_YELLOW_RATIO (70%)
                            of expected-for-cadence, once >= LOW_UPTIME_MIN_EXPECTED
                            ticks (~1h) have had a chance to accrue. NOTE: the task spec
                            asks for uptime% to be COMPUTED (tick count vs expected) but
                            names an explicit threshold only for the 4 other rules below --
                            this threshold/rule is this module's own derived judgment call,
                            documented here so it is auditable, not silently invented.
  RED    INCIDENT_SPIKE    >= INCIDENT_SPIKE_RED_COUNT (3) incidents today (UTC day),
                            max() of incidents.jsonl's scan + path-coverage.json's own
                            per-branch status=="INCIDENT" count (see docstring above)
  YELLOW COVERAGE_LAG      path-coverage.json present + dated today + < 50% branches
                            status=="GREEN", evaluated ONLY once now_utc >= 18:00 UTC
                            (spec-given threshold + cutoff hour)
  RED    BREAKER_TRIPPED   twin-health.json reports breaker_tripped == true
  RED    ACCOUNT_REGRESSION account_status was LIVE on the PRIOR sentinel run and is
                            something else now (this module persists the prior value in
                            its own twin-sentinel.json -- twin-health.json only ever
                            holds the LATEST snapshot, no history)

All "today" framing is the UTC calendar day throughout (matches the twin's own
UTC-day session/breaker anchoring -- see crypto_twin_core.TwinConfig's
daily_loss_kill_switch_pct comment: "UTC-day anchored"), NOT the ET day the rest of
this repo usually reasons in.

ESCALATION (on a NEW transition into RED): appends ONE row to automation/overnight/
queue.md under a "## Twin escalations" section (created once, row inserted at the
END of that section specifically -- never at end-of-file, so a later-appended
unrelated section elsewhere in queue.md can never swallow a future escalation row
into the wrong section) + ONE Discord outbox ping (reusing the exact
_load_user_mention()/outbox-line pattern already used by ccr_keepalive.py /
trade_today_watcher.py -- never rebuilt). De-duped PER EPISODE via bookkeeping
persisted in twin-sentinel.json's own `escalation` block (queue_row_written_this_episode
/ ping_sent_this_episode), reset the moment the verdict leaves RED -- mirrors
ccr_keepalive.py's ping_sent_this_episode reset-on-recovery shape, except the
transition itself is the trigger here (the spec says "on a NEW transition into RED",
not "after N consecutive fires" -- there is no strike-counter in this module).
A write failure on either side effect is logged into `notes` and simply retried on
the NEXT RED fire (the per-episode flag only flips True on confirmed success), so a
transient IO error self-heals instead of silently eating the one escalation.

SCHEDULING: registered as Gamma_TwinSentinel (every 15 min, 24/7). This same
entrypoint also triggers the nightly free-LLM review (see run_sentinel()) once per
UTC day after 23:30 UTC -- ONE task does both jobs (see install-twin-sentinel.ps1).

Exits 0 always. This must never be the thing that breaks a scheduled fire.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (matches ccr_keepalive.py / kitchen_seeder.py) ==============
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "twin-sentinel.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "twin-sentinel.stderr.log", "a", buffering=1, encoding="utf-8")
# ==========================================================================================

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in _sys.path:
    _sys.path.insert(0, str(SCRIPTS))

from et_clock import et_now  # noqa: E402

STATE = REPO / "automation" / "state"
TWIN_DIR = STATE / "crypto-twin"

DECISIONS_PATH = TWIN_DIR / "decisions.jsonl"
HEALTH_PATH = STATE / "twin-health.json"                 # top-level, per crypto_twin_health.py
SOAK_LOG_PATH = TWIN_DIR / "soak-log.jsonl"               # read by twin_review.py, not evaluate()
INCIDENTS_PATH = TWIN_DIR / "incidents.jsonl"             # schema undefined upstream (fail-open)
COVERAGE_PATH = TWIN_DIR / "path-coverage.json"           # schema undefined upstream (fail-open)
SENTINEL_PATH = STATE / "twin-sentinel.json"

QUEUE_MD = REPO / "automation" / "overnight" / "queue.md"
OUTBOX = STATE / "discord-outbox.jsonl"
DISCORD_CFG = STATE / ".discord-config.json"

TWIN_ESCALATIONS_HEADER = "## Twin escalations"

# ── Thresholds (see module docstring VERDICT RULES for provenance of each) ───────────────
# CADENCE-TUNE (2026-08-01, J latency drill): Gamma_CryptoTwin's own tick cadence went
# 5min -> 1min (see install-crypto-twin.ps1 + SCHEDULED-TASKS.md for the full rationale --
# real 1-min-BTC adverse-excursion data showed 5min cadence exposes ~2-2.6x the blind-spot
# risk of 1min between looks, and exit management already reads LIVE quotes every tick so
# the tighter cadence genuinely shortens reaction time, not just visibility). Both
# CADENCE_MINUTES and LOW_UPTIME_MIN_EXPECTED are updated TOGETHER so the ">=1h of expected
# ticks" invariant LOW_UPTIME_MIN_EXPECTED's own comment promises stays true at the new
# cadence -- these two constants are mathematically coupled (expected_ticks =
# minutes_elapsed // CADENCE_MINUTES; the "~1h" gate is LOW_UPTIME_MIN_EXPECTED *
# CADENCE_MINUTES minutes), so changing one without the other would silently break that
# promise (LOW_UPTIME_MIN_EXPECTED=12 at a 1-min cadence would only wait 12 real minutes,
# not 1 hour, causing premature LOW_UPTIME judgments in the first hour of every UTC day).
CADENCE_MINUTES = 1                    # the TWIN's own tick cadence (Gamma_CryptoTwin), NOT
                                        # this sentinel's 15-min fire cadence
TICK_GAP_RED_MINUTES = 20              # spec-given, unchanged by the cadence tune (absolute
                                        # staleness trip-wire, not cadence-derived)
INCIDENT_SPIKE_RED_COUNT = 3           # spec-given
COVERAGE_LAG_YELLOW_RATIO = 0.5        # spec-given ("<half branches green")
COVERAGE_LAG_HOUR_UTC = 18             # spec-given ("by 18:00 UTC")
LOW_UPTIME_YELLOW_RATIO = 0.70         # derived judgment call -- see docstring
LOW_UPTIME_MIN_EXPECTED = 60           # >=1h of expected ticks before judging uptime (avoids
                                        # false YELLOW in the first few minutes of a UTC day) --
                                        # 60 * CADENCE_MINUTES(1) = 60min, same "~1h" invariant
                                        # the old 12 * 5min = 60min value encoded pre-cadence-tune
REVIEW_TRIGGER_HOUR_UTC = 23           # spec-given ("after 23:30 UTC")
REVIEW_TRIGGER_MINUTE_UTC = 30

RED_CODES = {"TICK_GAP", "INCIDENT_SPIKE", "BREAKER_TRIPPED", "ACCOUNT_REGRESSION"}
YELLOW_CODES = {"LOW_UPTIME", "COVERAGE_LAG"}


# ══════════════════════════════════════════════════════════════════════════════════════
# Fail-open readers -- deliberately NOT imported from crypto_twin_health.py / _core.py:
# this sentinel must keep working even if B1/B2's own files are mid-edit, broken, or
# import something heavy (exit_manager/risk_gate/crypto.lib.*) this lightweight 15-min
# judge has no need to pull in (fable-blast-radius: don't couple to a concurrently-
# edited surface when a 15-line local reader does the same job standalone).
# ══════════════════════════════════════════════════════════════════════════════════════
def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _parse_iso(s) -> Optional[datetime]:
    if not isinstance(s, str) or not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # every ts_utc in this repo's writers already
                                               # carries an offset; naive fallback assumes UTC
    return dt.astimezone(timezone.utc)


# ══════════════════════════════════════════════════════════════════════════════════════
# RULE 1+2 data: tick freshness + UTC-day uptime (from decisions.jsonl, oldest-first
# on disk -- every writer in this repo appends in that order)
# ══════════════════════════════════════════════════════════════════════════════════════
def evaluate_tick_freshness(rows: list[dict], now_utc: datetime) -> dict:
    last_dt: Optional[datetime] = None
    for row in reversed(rows):
        dt_ = _parse_iso(row.get("ts_utc")) or _parse_iso(row.get("ts_et"))
        if dt_:
            last_dt = dt_
            break
    tick_age_minutes = None
    if last_dt is not None:
        tick_age_minutes = (now_utc - last_dt).total_seconds() / 60.0

    today_utc_str = now_utc.strftime("%Y-%m-%d")
    ticks_today = 0
    for row in rows:
        d = row.get("session_date_utc")
        if not d:
            dt_ = _parse_iso(row.get("ts_utc"))
            d = dt_.strftime("%Y-%m-%d") if dt_ else None
        if d == today_utc_str:
            ticks_today += 1

    minutes_elapsed = now_utc.hour * 60 + now_utc.minute
    expected_ticks = max(0, minutes_elapsed // CADENCE_MINUTES)
    uptime_pct = None
    if expected_ticks > 0:
        uptime_pct = round(min(100.0, 100.0 * ticks_today / expected_ticks), 1)

    return {
        "last_tick_utc": last_dt.isoformat() if last_dt else None,
        "tick_age_minutes": round(tick_age_minutes, 2) if tick_age_minutes is not None else None,
        "ticks_today_utc": ticks_today,
        "expected_ticks_utc": expected_ticks,
        "uptime_pct": uptime_pct,
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# RULE 3 data: incident count today -- SCHEMA-TOLERANT (incidents.jsonl not yet shipped
# by any crew as of this build; see module docstring)
# ══════════════════════════════════════════════════════════════════════════════════════
def count_incidents_today(rows: list[dict], today_utc_str: str) -> "tuple[int, int]":
    """Returns (matched_today, undated). Scans every string value in each row (one
    level deep) for a 'YYYY-MM-DD...' date prefix -- schema-agnostic on purpose, since
    no producer has defined incidents.jsonl's real field names yet. A row with NO
    recognizable date anywhere is NOT counted toward today (fail-open: ambiguous data
    must never manufacture a RED) but IS tallied separately as `undated` so it stays
    visible (surfaced in `notes`) rather than silently vanishing (OP-25/C7)."""
    today_n = 0
    undated = 0
    for row in rows:
        matched = False
        found_date = False
        for v in row.values():
            if isinstance(v, str) and len(v) >= 10 and v[:4].isdigit() and v[4:5] == "-" and v[5:7].isdigit():
                found_date = True
                if v[:10] == today_utc_str:
                    matched = True
        if matched:
            today_n += 1
        elif not found_date:
            undated += 1
    return today_n, undated


# ══════════════════════════════════════════════════════════════════════════════════════
# RULE 4 data: path coverage -- CONFIRMED schema (2026-07-11, B1c ship, verified against
# the REAL producer -- crypto_twin_scenarios.py's BRANCH_REGISTRY/_mark_exercise_result
# + crypto_twin_health.py's summarize_path_coverage(), not guessed):
#   {"date_utc": "YYYY-MM-DD",
#    "branches": {"<BRANCH_NAME>": {"tier": "LIVE"|"SIM",
#                                    "status": "PENDING"|"IN_PROGRESS"|"NOT_YET_COVERED"
#                                              |"GREEN"|"INCIDENT",
#                                    "count_today": int, "last_exercised_utc": iso|null,
#                                    "last_result": ...|null}, ...}}
# "green" = status=="GREEN" exactly; "incident" = status=="INCIDENT" exactly (closed
# enum, confirmed via grep of the real producer's literal string constants). A defensive
# summary-ints fallback (total_branches/green_branches) is kept in case a future shape
# ever emits pre-aggregated counts instead of a branches map -- not observed in the real
# producer as of this build.
# ══════════════════════════════════════════════════════════════════════════════════════
_GREEN_STATUS = "GREEN"
_INCIDENT_STATUS = "INCIDENT"


def parse_path_coverage(data: Optional[dict], today_utc_str: str) -> Optional[dict]:
    """Returns {"total", "green", "incidents", "date_utc"} or None if absent/
    unparseable/stale (dated to a different UTC day -- a stale file must never accuse
    TODAY of lagging) /unrecognized shape. `incidents` here is derived the SAME way
    crypto_twin_health.summarize_path_coverage() derives twin-health.json's own
    `incidents_today` -- re-derived independently from the SAME raw file rather than
    read back off twin-health.json, so this sentinel stays a genuinely separate judge
    (not dependent on B1's own derivation code being bug-free)."""
    if not data:
        return None
    date_utc = data.get("date_utc")
    if date_utc and date_utc != today_utc_str:
        return None

    branches = data.get("branches")
    if isinstance(branches, dict) and branches:
        total = len(branches)
        green = 0
        incidents = 0
        for rec in branches.values():
            status = str((rec or {}).get("status", "")) if isinstance(rec, dict) else str(rec)
            if status == _GREEN_STATUS:
                green += 1
            elif status == _INCIDENT_STATUS:
                incidents += 1
        return {"total": total, "green": green, "incidents": incidents, "date_utc": date_utc}

    # Defensive fallback only -- not the real producer's shape (see docstring above).
    total = data.get("total_branches")
    green = data.get("green_branches")
    if isinstance(total, int) and isinstance(green, int) and total > 0:
        return {"total": total, "green": green, "incidents": None, "date_utc": date_utc}

    return None


# ══════════════════════════════════════════════════════════════════════════════════════
# RULE 5+6 data: breaker + account_status, from twin-health.json (already computed by
# crypto_twin_health.py -- reused, not re-derived, to stay DRY and avoid a second,
# possibly-divergent creds/broker lookup)
# ══════════════════════════════════════════════════════════════════════════════════════
def read_health_facts(health_path: Path = HEALTH_PATH) -> dict:
    data = _read_json(health_path)
    if not data:
        return {"health_readable": False, "account_status": None, "breaker_tripped": None,
                "last_action": None, "last_error": None}
    return {
        "health_readable": True,
        "account_status": data.get("account_status"),
        "breaker_tripped": data.get("breaker_tripped"),
        "last_action": data.get("last_action"),
        "last_error": data.get("last_error"),
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# The deterministic core -- pure, fully injectable, no side effects
# ══════════════════════════════════════════════════════════════════════════════════════
def evaluate(
    *,
    now_utc: Optional[datetime] = None,
    now_et: Optional[datetime] = None,
    prior_sentinel: Optional[dict] = None,
    decisions_path: Path = DECISIONS_PATH,
    health_path: Path = HEALTH_PATH,
    incidents_path: Path = INCIDENTS_PATH,
    coverage_path: Path = COVERAGE_PATH,
) -> dict:
    now_utc = now_utc or datetime.now(timezone.utc)
    now_et = now_et or et_now()
    today_utc_str = now_utc.strftime("%Y-%m-%d")

    rows = _read_jsonl(decisions_path)
    freshness = evaluate_tick_freshness(rows, now_utc)

    incidents_rows = _read_jsonl(incidents_path)
    incidents_from_jsonl, incidents_undated = count_incidents_today(incidents_rows, today_utc_str)

    coverage_raw = _read_json(coverage_path)
    coverage = parse_path_coverage(coverage_raw, today_utc_str)
    incidents_from_coverage = coverage["incidents"] if (coverage and coverage.get("incidents") is not None) else 0
    # Two independent signals, same underlying concept ("something is wrong today") --
    # take the WORSE (max), never sum: incidents.jsonl (if/when B2 ships it -- the file
    # this task was originally spec'd against) and path-coverage.json's own per-branch
    # status=="INCIDENT" count (confirmed live 2026-07-11, B1c) are different-shaped
    # views of overlapping reality, not necessarily additive events.
    incidents_today = max(incidents_from_jsonl, incidents_from_coverage)

    health = read_health_facts(health_path)

    reasons: list[str] = []
    notes: list[str] = []

    # RULE 1: TICK_GAP (RED)
    if freshness["tick_age_minutes"] is None:
        reasons.append(f"TICK_GAP: no ticks recorded yet in {decisions_path.name}")
    elif freshness["tick_age_minutes"] > TICK_GAP_RED_MINUTES:
        reasons.append(
            f"TICK_GAP: last tick {freshness['tick_age_minutes']:.1f} min ago "
            f"(threshold {TICK_GAP_RED_MINUTES} min)"
        )

    # RULE 2: LOW_UPTIME (YELLOW, derived threshold -- see module docstring)
    if (freshness["expected_ticks_utc"] >= LOW_UPTIME_MIN_EXPECTED
            and freshness["uptime_pct"] is not None
            and freshness["uptime_pct"] < LOW_UPTIME_YELLOW_RATIO * 100):
        reasons.append(
            f"LOW_UPTIME: {freshness['ticks_today_utc']}/{freshness['expected_ticks_utc']} "
            f"ticks today ({freshness['uptime_pct']:.1f}%, threshold "
            f"{LOW_UPTIME_YELLOW_RATIO * 100:.0f}%)"
        )

    # RULE 3: INCIDENT_SPIKE (RED)
    if incidents_today >= INCIDENT_SPIKE_RED_COUNT:
        reasons.append(
            f"INCIDENT_SPIKE: {incidents_today} incidents today (threshold {INCIDENT_SPIKE_RED_COUNT})"
        )
    if not incidents_path.exists():
        notes.append("incidents.jsonl not present -- incident count treated as 0 (fail-open)")
    elif incidents_undated:
        notes.append(
            f"{incidents_undated} incidents.jsonl row(s) had no recognizable date -- "
            "excluded from today's count"
        )

    # RULE 4: COVERAGE_LAG (YELLOW) -- only evaluated after 18:00 UTC, only if coverage
    # data is present, dated today, and parseable
    if coverage is None:
        if coverage_path.exists():
            notes.append(
                "path-coverage.json present but unreadable/stale/unrecognized shape -- "
                "coverage check skipped"
            )
        else:
            notes.append(
                "path-coverage.json not present yet (B1 may not have shipped it) -- "
                "coverage check skipped"
            )
    else:
        ratio = (coverage["green"] / coverage["total"]) if coverage["total"] else None
        if ratio is not None and now_utc.hour >= COVERAGE_LAG_HOUR_UTC and ratio < COVERAGE_LAG_YELLOW_RATIO:
            reasons.append(
                f"COVERAGE_LAG: {coverage['green']}/{coverage['total']} branches green "
                f"({ratio * 100:.0f}%, threshold {COVERAGE_LAG_YELLOW_RATIO * 100:.0f}% by "
                f"{COVERAGE_LAG_HOUR_UTC:02d}:00 UTC)"
            )

    # RULE 5: BREAKER_TRIPPED (RED)
    if health["breaker_tripped"] is True:
        reasons.append("BREAKER_TRIPPED: twin-health.json reports breaker_tripped=true")
    if not health["health_readable"]:
        notes.append(
            "twin-health.json unreadable/missing -- breaker + account_status checks skipped"
        )

    # RULE 6: ACCOUNT_REGRESSION (RED) -- LIVE -> anything else, vs the PRIOR sentinel run
    # (twin-sentinel.json is the only place this module keeps history; twin-health.json
    # only ever holds the latest snapshot)
    prior_account_status = None
    if isinstance(prior_sentinel, dict):
        prior_account_status = (prior_sentinel.get("facts") or {}).get("account_status")
    current_account_status = health["account_status"]
    if (prior_account_status == "LIVE"
            and current_account_status is not None
            and current_account_status != "LIVE"):
        reasons.append(f"ACCOUNT_REGRESSION: account_status LIVE -> {current_account_status}")

    has_red = any(r.split(":", 1)[0] in RED_CODES for r in reasons)
    has_yellow = any(r.split(":", 1)[0] in YELLOW_CODES for r in reasons)
    verdict = "RED" if has_red else ("YELLOW" if has_yellow else "GREEN")

    facts = {
        **freshness,
        "incidents_today": incidents_today,
        "incidents_from_jsonl": incidents_from_jsonl,
        "incidents_from_coverage": incidents_from_coverage,
        "incidents_undated": incidents_undated,
        "coverage": coverage,
        "breaker_tripped": health["breaker_tripped"],
        "account_status": current_account_status,
        "last_action": health["last_action"],
        "last_error": health["last_error"],
    }

    return {
        "verdict": verdict,
        "reasons": reasons,
        "notes": notes,
        "facts": facts,
        "checked_at_et": now_et.isoformat(),
        "checked_at_utc": now_utc.isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# Escalation side effects -- queue.md row + Discord ping, de-duped per RED episode
# ══════════════════════════════════════════════════════════════════════════════════════
def _load_user_mention(cfg_path: Path = DISCORD_CFG) -> str:
    """Verbatim shared pattern (ccr_keepalive.py / trade_today_watcher.py) -- fail-open
    to '' on any missing/malformed config, never blocks the ping itself."""
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
        uid = cfg.get("user_id")
        return f"<@{uid}> " if uid else ""
    except Exception:  # noqa: BLE001
        return ""


def _send_discord_ping(msg: str, *, outbox_path: Path = OUTBOX, cfg_path: Path = DISCORD_CFG) -> None:
    mention = _load_user_mention(cfg_path)
    outbox_path.parent.mkdir(parents=True, exist_ok=True)
    with outbox_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "content": mention + msg,
            "source": "twin_sentinel",
            "queued_at": datetime.now(timezone.utc).isoformat(),
        }) + "\n")


def _ensure_twin_escalations_section(lines: list[str]) -> "tuple[list[str], int]":
    """Returns (possibly-extended lines, index of the header line). Creates the
    section ONCE at end-of-file if absent."""
    for i, ln in enumerate(lines):
        if ln.strip() == TWIN_ESCALATIONS_HEADER:
            return lines, i
    if lines and not lines[-1].endswith("\n"):
        lines = lines[:-1] + [lines[-1] + "\n"]
    lines = lines + ["\n", TWIN_ESCALATIONS_HEADER + "\n", "\n"]
    return lines, len(lines) - 2  # index of the header line just appended


def _append_queue_row(reasons: list[str], *, today_et: str, queue_path: Path = QUEUE_MD) -> None:
    """Appends ONE row to the '## Twin escalations' section (created once). The row is
    inserted at the END of THAT section specifically (before the next '## ' heading, or
    EOF if this is the last section) -- never blindly at end-of-file, so a later,
    unrelated section appended elsewhere in queue.md can never swallow a future
    escalation row into the wrong place."""
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    text = queue_path.read_text(encoding="utf-8") if queue_path.exists() else ""
    lines = text.splitlines(keepends=True)
    lines, header_idx = _ensure_twin_escalations_section(lines)

    reason_codes = "+".join(r.split(":", 1)[0] for r in reasons) if reasons else "UNSPECIFIED"
    detail = "; ".join(reasons) if reasons else "unspecified reason"
    row_id = f"TWIN-ESCALATION-{today_et.replace('-', '')}-{int(time.time())}"
    row = (
        f"- [ ] {row_id} {today_et} {reason_codes} ({detail}) :: "
        f"dispatch a Sonnet investigation :: status:pending\n"
    )

    end_idx = len(lines)
    for j in range(header_idx + 1, len(lines)):
        if lines[j].startswith("## "):
            end_idx = j
            break
    lines.insert(end_idx, row)
    queue_path.write_text("".join(lines), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════════════════
# Orchestration -- loads prior state, evaluates, escalates on new-RED, triggers the
# nightly review, writes twin-sentinel.json
# ══════════════════════════════════════════════════════════════════════════════════════
def run_sentinel(
    *,
    now_utc: Optional[datetime] = None,
    now_et: Optional[datetime] = None,
    sentinel_path: Path = SENTINEL_PATH,
    queue_path: Path = QUEUE_MD,
    outbox_path: Path = OUTBOX,
    cfg_path: Path = DISCORD_CFG,
    run_review: bool = True,
    decisions_path: Path = DECISIONS_PATH,
    health_path: Path = HEALTH_PATH,
    incidents_path: Path = INCIDENTS_PATH,
    coverage_path: Path = COVERAGE_PATH,
) -> dict:
    now_utc = now_utc or datetime.now(timezone.utc)
    now_et = now_et or et_now()
    today_utc_str = now_utc.strftime("%Y-%m-%d")
    today_et_str = now_et.strftime("%Y-%m-%d")

    prior = _read_json(sentinel_path)
    prior_escalation = (prior or {}).get("escalation") or {}
    prior_queue_written = bool(prior_escalation.get("queue_row_written_this_episode"))
    prior_ping_sent = bool(prior_escalation.get("ping_sent_this_episode"))

    result = evaluate(
        now_utc=now_utc, now_et=now_et, prior_sentinel=prior,
        decisions_path=decisions_path, health_path=health_path,
        incidents_path=incidents_path, coverage_path=coverage_path,
    )

    if result["verdict"] == "RED":
        queue_row_written = prior_queue_written
        if not prior_queue_written:
            try:
                _append_queue_row(result["reasons"], today_et=today_et_str, queue_path=queue_path)
                queue_row_written = True
            except OSError as exc:
                result["notes"].append(f"queue.md escalation append FAILED: {exc}")

        ping_sent = prior_ping_sent
        if not prior_ping_sent:
            try:
                summary = "; ".join(result["reasons"])[:300]
                _send_discord_ping(f"TWIN SENTINEL RED: {summary}", outbox_path=outbox_path, cfg_path=cfg_path)
                ping_sent = True
            except OSError as exc:
                result["notes"].append(f"discord escalation ping FAILED: {exc}")
    else:
        queue_row_written = False
        ping_sent = False

    result["escalation"] = {
        "episode_active": result["verdict"] == "RED",
        "queue_row_written_this_episode": queue_row_written,
        "ping_sent_this_episode": ping_sent,
    }

    # Carry the prior review note forward unless a fresh review runs below.
    result["last_review_note"] = (prior or {}).get("last_review_note")

    review_ran = False
    if run_review and (now_utc.hour, now_utc.minute) >= (REVIEW_TRIGGER_HOUR_UTC, REVIEW_TRIGGER_MINUTE_UTC):
        already_done = isinstance(result["last_review_note"], dict) and \
            result["last_review_note"].get("date_utc") == today_utc_str
        if not already_done:
            try:
                import twin_review  # lazy import -- only paid when a review is actually due
                review_result = twin_review.run_review(now_utc=now_utc, now_et=now_et)
                result["last_review_note"] = {
                    "date_utc": today_utc_str,
                    "mode": review_result.get("mode"),
                    "summary": review_result.get("summary_line", ""),
                    "assessment": review_result.get("assessment"),
                    "confidence": review_result.get("confidence"),
                    "report_path": review_result.get("report_path"),
                    "sidecar_path": review_result.get("sidecar_path"),
                }
                review_ran = True
            except Exception as exc:  # noqa: BLE001 -- a review failure must never break sentinel
                result["notes"].append(f"nightly review FAILED: {type(exc).__name__}: {exc}")

    result["review_ran_this_fire"] = review_ran

    try:
        sentinel_path.parent.mkdir(parents=True, exist_ok=True)
        sentinel_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    except OSError as exc:
        result["notes"].append(f"twin-sentinel.json write FAILED: {exc}")

    return result


# ══════════════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════════════
def main(argv: Optional[list] = None) -> int:
    result = run_sentinel()
    print(json.dumps({
        "verdict": result["verdict"],
        "reasons": result["reasons"],
        "notes": result["notes"],
        "checked_at_et": result["checked_at_et"],
        "escalation": result["escalation"],
        "review_ran_this_fire": result["review_ran_this_fire"],
        "last_review_note": result["last_review_note"],
    }, indent=2))
    return 0  # fail-open -- this task must never be the reason a scheduled fire shows non-zero


def _main_safe(argv: Optional[list] = None) -> int:
    try:
        return main(argv)
    except Exception as exc:  # noqa: BLE001
        try:
            _log_dir2 = STATE / "logs"
            _log_dir2.mkdir(parents=True, exist_ok=True)
            with (_log_dir2 / "twin-sentinel-fatal.log").open("a", encoding="utf-8") as fh:
                fh.write(f"{datetime.now(timezone.utc).isoformat()} FATAL {type(exc).__name__}: {exc}\n")
        except OSError:
            pass
        print(json.dumps({"verdict": "RED", "reasons": [f"SENTINEL_CRASH: {type(exc).__name__}: {exc}"],
                          "fatal": True}))
        return 0


if __name__ == "__main__":
    raise SystemExit(_main_safe())
