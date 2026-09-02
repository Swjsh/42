"""daily_loss_guard -- mechanical Rule-5 daily-loss kill switch (post-tick).

WHY THIS EXISTS (2026-06-21 readiness audit, finding C2/P0-3): the heartbeat only
ever READ circuit_breaker.tripped as a skip/entry gate -- NOTHING computed cumulative
intraday P&L and SET tripped=true at -30% (Safe) / -50% (Bold). So Rule 5's daily-loss
kill switch was effectively unenforced for unattended running: a runaway loss day would
keep trading past the limit. This guard closes that hole deterministically: it runs
post-tick (wired into run-heartbeat*.ps1 right after atomic_bracket_guard), hits the
Alpaca REST account endpoint directly (NOT dependent on the LLM), and flips the breaker
when the day's loss breaches the per-account limit. The next heartbeat tick then reads
tripped=true at gate G5 and halts the account; Gamma_HealthBeacon RED-pings J.

FAIL-SAFE BY DESIGN (never produce a false halt):
  * If the Alpaca equity fetch fails -> do NOTHING to tripped (report error, exit 0).
  * If start-of-day equity is missing/<=0 -> do NOTHING (cannot compute).
  * If the breaker's session date != today ET (premarket hasn't armed today's SoD) ->
    do NOTHING to tripped (stale SoD -> meaningless comparison); report a warning.
  * If already tripped -> idempotent (refresh equity fields, never un-trip).
  * Only a CONFIRMED breach (fresh SoD + successfully fetched equity + loss>=limit)
    trips. Catastrophe is one-sided: we only ever HALT trading, never enable it.

Reuses setup/scripts/alpaca_keys.py (live creds from gitignored .mcp.json) so the keys
can never drift from what the engine trades with (same fix as the bracket/ghost guards).

CLI:
    python setup/scripts/daily_loss_guard.py --account safe
    python setup/scripts/daily_loss_guard.py --account bold
    python setup/scripts/daily_loss_guard.py --account safe --dry-run   # report, never write tripped
    python setup/scripts/daily_loss_guard.py --account safe --silent     # JSON only
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from alpaca_keys import keys_for  # noqa: E402
from et_clock import ET_TZ  # noqa: E402 — DST-aware ET (TZ-SYSTEMIC fix: was timezone(timedelta(hours=-4)))
ALPACA_BASE = "https://paper-api.alpaca.markets/v2"

# Audit-trail log directory. Module-level (not inlined at the write sites) so tests can
# redirect it to a tempdir -- inlined paths once let every TRIPPED/REARMED test case
# append fake rows into the REAL automation/state/daily-loss-guard-{date}.jsonl
# (see test_daily_loss_guard.py's no-pollution guard, 2026-07-09).
LOG_DIR = PROJECT_ROOT / "automation" / "state"

# Per-account breaker schema mapping. The two breaker files use DIVERGENT field names
# (the C9 symmetry trap, documented in each file's _schema_note) -- so we map explicitly.
ACCOUNTS: dict[str, dict[str, Any]] = {
    "safe": {
        "breaker": PROJECT_ROOT / "automation" / "state" / "circuit-breaker.json",
        "sod_field": "starting_equity_today",
        "cur_field": "current_equity",
        "limit_field": "daily_loss_limit_pct",
        "limit_default": 0.30,
        "loss_pct_field": "max_drawdown_today_pct",
        "loss_dollars_field": "max_drawdown_today_dollars",
        "limit_dollars_field": "daily_loss_limit_dollars",  # display-only $ threshold, kept in sync on rearm
        "tripped_at_field": "tripped_at",
        "tripped_reason_field": "tripped_reason",
        "date_field": "last_reset",  # ISO datetime
    },
    "bold": {
        "breaker": PROJECT_ROOT / "automation" / "state" / "aggressive" / "circuit-breaker.json",
        "sod_field": "equity_start_of_day",
        "cur_field": "equity_current",
        "limit_field": "daily_loss_kill_switch_pct",
        "limit_default": 0.50,
        "loss_pct_field": "loss_pct",
        "loss_dollars_field": None,
        "limit_dollars_field": None,  # bold schema has no equivalent display field
        "tripped_at_field": "tripped_at_et",
        "tripped_reason_field": "trip_reason",
        "date_field": "session_id",  # date string
    },
}


def _fetch_equity(account: str) -> float:
    """GET /v2/account -> float(equity). Raises on any failure (caller fails safe)."""
    key, secret = keys_for(account)
    req = urllib.request.Request(
        f"{ALPACA_BASE}/account",
        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return float(data["equity"])


def _date_str(raw: Any) -> str | None:
    """Extract a YYYY-MM-DD date from an ISO datetime or a bare date string."""
    if not raw or not isinstance(raw, str):
        return None
    return raw[:10]


def _write_atomic(path: Path, obj: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    tmp.replace(path)


def rearm(account: str, dry_run: bool) -> dict:
    """Deterministic, LLM-independent premarket re-arm (2026-07-09 root-cause fix).

    WHY THIS EXISTS: the ONLY writer of a fresh starting_equity_today/equity_start_of_day
    used to be the premarket LLM persona (automation/prompts/premarket.md, invoked via
    claude --print). 2026-07-09: both premarket attempts failed instantly with "API Error:
    Unable to connect to API (ConnectionRefused)" because ~/.claude/settings.json now routes
    EVERY claude session through a local claude-code-router gateway (127.0.0.1:3456,
    apiKeyHelper) that had died overnight with no auto-restart (confirmed: no listener on
    3456-3459, PID from its own service.json long dead). The LLM never ran a single step, so
    both breaker files kept 2026-07-08's start-of-day equity while the engine traded
    2026-07-09 -- the daily-loss kill switch was silently anchored to the WRONG baseline.
    engine_health.py's killswitch_* check only asks "tripped?", not "armed on TODAY's
    equity?", so nothing surfaced it (see check_breaker_rearm in engine_health.py).

    This function decouples the SAFETY-CRITICAL re-arm from that fragile, optional,
    multi-tool-call LLM dependency: it fetches live equity via the same direct Alpaca REST
    path `run()` already uses (un-blockable by claude/CCR outages -- the "never-blind"
    pattern already used by sight_beacon.py), and idempotently resets the breaker to a fresh
    session ONLY when its stamped date != today ET. Wired into run-premarket.ps1 as an
    early, LLM-independent step so a dead CCR gateway (or a claude budget/timeout/rate-limit
    failure, or any other reason the LLM step doesn't complete) can no longer leave the kill
    switch anchored to a stale day. The LLM's own premarket step still runs afterward and
    will simply see an already-armed-today breaker (idempotent, no conflict).

    FAIL-SAFE BY DESIGN (mirrors run()'s contract):
      * Already armed today (date_field == today ET) -> no-op, never re-fetch/re-write.
        Never touches an in-progress trading day's current_equity/loss tracking.
      * Alpaca equity fetch fails -> do NOTHING (never invent/guess a value).
      * Missing breaker file -> do NOTHING (report, let a human create it from scratch --
        this function only RE-arms an existing file, never originates one).
      * Never mutates day_trades_used_5d / PDT fields -- out of scope for this guard;
        touching them without a reliable source would be a new, unrelated risk.
    """
    cfg = ACCOUNTS[account]
    breaker_path: Path = cfg["breaker"]
    now_et = datetime.now(timezone.utc).astimezone(ET_TZ)
    today = now_et.strftime("%Y-%m-%d")

    if not breaker_path.exists():
        return {"account": account, "ok": False, "action": "skip", "reason": "no_breaker_file"}

    breaker = json.loads(breaker_path.read_text(encoding="utf-8"))
    bdate = _date_str(breaker.get(cfg["date_field"]))

    if bdate == today:
        return {"account": account, "ok": True, "action": "already_armed_today", "date": today}

    try:
        equity = _fetch_equity(account)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
            ConnectionError, KeyError, ValueError, FileNotFoundError) as e:
        return {"account": account, "ok": False, "action": "skip",
                "reason": f"equity_fetch_failed: {e}", "warn": True}

    limit_pct = float(breaker.get(cfg["limit_field"], cfg["limit_default"]))
    prior_date = bdate  # for the audit trail / result payload
    # W2 (2026-09-01 kill-switch wiring fix): this used to unconditionally set tripped=False
    # every time a new day crossed -- the exact bug the W2 audit named ("daily_loss_guard.
    # rearm() unconditionally re-arms each premarket"), which meant an unresolved
    # eod_flatten.py escalation (partial-fill, physical-assignment risk) got silently
    # cleared by the very next premarket tick. escalation_unresolved is set only by
    # eod_flatten.py's _escalate_inner and cleared only by a human resolving the position.
    escalation_unresolved = bool(breaker.get("escalation_unresolved"))

    breaker[cfg["sod_field"]] = round(equity, 2)
    breaker[cfg["cur_field"]] = round(equity, 2)
    if escalation_unresolved:
        # Refuse to clear tripped/reason/at -- equity still refreshes so run()'s
        # stale-SoD guard doesn't itself misfire, but the halt persists untouched.
        action_label = "REARM_REFUSED_UNRESOLVED_ESCALATION"
    else:
        breaker["tripped"] = False
        breaker[cfg["tripped_at_field"]] = None
        breaker[cfg["tripped_reason_field"]] = None
        action_label = "REARMED"
    if cfg.get("loss_pct_field"):
        breaker[cfg["loss_pct_field"]] = 0.0
    if cfg.get("loss_dollars_field"):
        breaker[cfg["loss_dollars_field"]] = 0.0
    if cfg.get("limit_dollars_field"):
        breaker[cfg["limit_dollars_field"]] = round(equity * limit_pct, 2)
    if account == "safe":
        breaker[cfg["date_field"]] = now_et.isoformat(timespec="seconds")
    else:
        breaker[cfg["date_field"]] = today
    if escalation_unresolved:
        breaker["_note"] = (
            f"REARM_REFUSED_UNRESOLVED_ESCALATION {today}: equity refreshed to "
            f"${equity:.2f} (Alpaca REST) but tripped/{cfg['tripped_reason_field']} left "
            f"untouched because escalation_unresolved=true (set by eod_flatten.py's "
            f"partial-fill escalation). Resolve the open position manually, then clear "
            f"escalation_unresolved in this file before a future rearm can restore trading."
        )
    else:
        breaker["_note"] = (
            f"Re-armed {today} premarket (DETERMINISTIC fallback -- daily_loss_guard.rearm; "
            f"prior stamped date was {prior_date}). equity=${equity:.2f} confirmed live "
            f"(Alpaca REST, un-blockable by claude/CCR outages). Kill switch: "
            f"-{limit_pct:.0%} = -${round(equity * limit_pct, 2)}/day. day_trades_used_5d "
            f"left untouched (out of this guard's scope)."
        )

    result: dict[str, Any] = {
        "account": account, "ok": True, "action": action_label,
        "date": today, "prior_date": prior_date, "equity": round(equity, 2),
        "limit_pct": limit_pct, "escalation_unresolved": escalation_unresolved,
    }
    if dry_run:
        result["action"] = "WOULD_REARM" if action_label == "REARMED" else action_label
        return result

    _write_atomic(breaker_path, breaker)
    log = LOG_DIR / f"daily-loss-guard-{today}.jsonl"
    try:
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts_et": now_et.isoformat(), **result}) + "\n")
    except OSError:
        pass
    return result


def run(account: str, dry_run: bool) -> dict:
    cfg = ACCOUNTS[account]
    breaker_path: Path = cfg["breaker"]
    now_et = datetime.now(timezone.utc).astimezone(ET_TZ)
    today = now_et.strftime("%Y-%m-%d")

    if not breaker_path.exists():
        return {"account": account, "ok": False, "action": "skip", "reason": "no_breaker_file"}

    breaker = json.loads(breaker_path.read_text(encoding="utf-8"))

    sod = breaker.get(cfg["sod_field"])
    try:
        sod = float(sod)
    except (TypeError, ValueError):
        sod = 0.0
    if sod <= 0:
        return {"account": account, "ok": False, "action": "skip", "reason": "no_start_of_day_equity"}

    # Stale-SoD guard: if premarket has not armed today's SoD, do NOT trip (the
    # comparison would be meaningless). This is the single most important false-halt guard.
    bdate = _date_str(breaker.get(cfg["date_field"]))
    if bdate != today:
        return {"account": account, "ok": True, "action": "skip_stale_sod",
                "reason": f"breaker date {bdate} != today {today} (premarket not armed)",
                "warn": True}

    # Fetch live equity. Any failure -> fail safe (never trip on an error).
    try:
        equity = _fetch_equity(account)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
            ConnectionError, KeyError, ValueError, FileNotFoundError) as e:
        return {"account": account, "ok": False, "action": "skip",
                "reason": f"equity_fetch_failed: {e}", "warn": True}

    loss_dollars = sod - equity
    loss_pct = loss_dollars / sod if sod > 0 else 0.0
    limit = float(breaker.get(cfg["limit_field"], cfg["limit_default"]))

    # Refresh observability fields regardless of trip (so HealthBeacon/EOD see truth).
    breaker[cfg["cur_field"]] = round(equity, 2)
    if cfg.get("loss_pct_field") in breaker or cfg.get("loss_pct_field"):
        breaker[cfg["loss_pct_field"]] = round(max(loss_pct, 0.0), 4)
    if cfg.get("loss_dollars_field"):
        breaker[cfg["loss_dollars_field"]] = round(max(loss_dollars, 0.0), 2)

    already = bool(breaker.get("tripped"))
    breach = loss_pct >= limit

    result: dict[str, Any] = {
        "account": account, "ok": True, "sod": round(sod, 2), "equity": round(equity, 2),
        "loss_pct": round(loss_pct, 4), "limit_pct": limit, "already_tripped": already,
    }

    if already:
        result["action"] = "already_tripped"
        if not dry_run:
            _write_atomic(breaker_path, breaker)
        return result

    if breach and not dry_run:
        breaker["tripped"] = True
        breaker[cfg["tripped_at_field"]] = now_et.strftime("%Y-%m-%dT%H:%M:%S%z")
        breaker[cfg["tripped_reason_field"]] = (
            f"daily_loss_{loss_pct:.1%}_>=_{limit:.0%}_limit (daily_loss_guard)"
        )
        result["action"] = "TRIPPED"
    elif breach and dry_run:
        result["action"] = "WOULD_TRIP"
    else:
        result["action"] = "ok_within_limit"
        if not dry_run:
            _write_atomic(breaker_path, breaker)

    if result["action"] == "TRIPPED":
        _write_atomic(breaker_path, breaker)
        # Audit trail (fail-loud signal flows via the breaker -> HealthBeacon -> Discord).
        log = LOG_DIR / f"daily-loss-guard-{today}.jsonl"
        try:
            with log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts_et": now_et.isoformat(), **result}) + "\n")
        except OSError:
            pass

    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Mechanical Rule-5 daily-loss kill switch.")
    ap.add_argument("--account", choices=["safe", "bold"], required=True)
    ap.add_argument("--dry-run", action="store_true", help="report only, never write tripped/rearm")
    ap.add_argument("--silent", action="store_true", help="JSON only")
    ap.add_argument("--rearm", action="store_true",
                     help="deterministic premarket re-arm (idempotent; no-ops if already "
                          "armed today) instead of the intraday trip check")
    args = ap.parse_args()
    try:
        if args.rearm:
            result = rearm(args.account, args.dry_run)
        else:
            result = run(args.account, args.dry_run)
    except Exception as e:  # never crash the parent heartbeat/premarket wrapper
        result = {"account": args.account, "ok": False, "action": "error", "reason": str(e)}
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
