"""eod_flatten.py -- pure-Python EOD flatten safety net for BOTH heartbeat accounts.

WHY THIS EXISTS (G7, 2026-06-27):
  Gamma_EodFlatten / Gamma_EodFlatten_Aggressive used to fire `claude --print` on
  eod-flatten.md -- the SAME fragile Max-pool/rate-limit substrate the heartbeat was
  migrated AWAY from.  If the Claude session starves at 15:55 ET, live 0DTE positions
  expire worthless.

  This script is the pure-Python replacement: no LLM, no MCP, no CDP.  It calls
  fleet_broker.close_all_spy_options() for safe-2 AND bold-2 via the same tested
  broker primitives heartbeat_core uses.  The LLM eod-flatten.md is demoted to a
  verbose-confirmation fallback (NOT the execution path).

FLOW:
  1. Load creds from secrets.json (fleet_broker.load_creds).
  2. For each account (safe-2, bold-2) -- INDEPENDENTLY (one error never blocks the other):
     a. Check open SPY option positions.  If flat -> log NOOP, continue.
     b. Retry-until-zero loop (3 attempts): market-sell all open SPY option qty.
     c. Verify flat after each attempt.
     d. Log result to automation/state/logs/eod-flatten-YYYY-MM-DD.log + .jsonl.
  3. Exit 0.  Fail-open per account -- a single broker error is logged, not raised.

SAFETY:
  * Uses `live=True` for the market-sell (production) -- set GAMMA_EOD_DRY=1 to force
    dry-run for testing (both accounts report NOOP/flat without placing any orders).
  * Timestamps from et_clock (NEVER naive datetime.now(tz=None) -- this rig is Mountain Time).
  * Idempotent: if already flat -> NOOP, nothing placed.
  * Expiry-agnostic: closes ANY open SPY option position (0DTE AND 1DTE alike).

CREDS:
  Loaded from automation/state/fleet/secrets.json via fleet_broker.load_creds().
  The 'safe-2' and 'bold-2' keys map to the Gamma-Safe-2 / Gamma-Risky-2 accounts.
  NEVER hardcoded.  If a key is missing from secrets.json, that account is logged as
  SKIP_NO_CREDS and the other account is still attempted.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import timezone, datetime
from pathlib import Path

# ---- path setup (mirrors heartbeat_core pattern) --------------------------------
_SCRIPTS = Path(__file__).resolve().parent
_REPO = _SCRIPTS.parents[1]
for _p in ("setup/scripts", "automation/state/fleet", "backtest/lib"):
    _pp = str(_REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

import fleet_broker  # noqa: E402 (from automation/state/fleet)
from et_clock import et_now  # noqa: E402 (from setup/scripts)

# ---- config ---------------------------------------------------------------------
# COVERAGE FIX (2026-08-18). This read ACCOUNTS = ["safe-2", "bold-2"] -- the two CORE arms
# only. The three fleet arms (safe-3, risky-1, risky-3) are separate real Alpaca accounts that
# take real 0DTE positions, and `fleet_eod.py` exists but is scheduled NOWHERE (verified against
# the live Task Scheduler, not the docs). So 3 of 5 active arms had NO deterministic EOD
# flatten at all.
#
# WHY THAT IS HARMLESS ON PAPER AND CATASTROPHIC LIVE: SPY options are PHYSICALLY settled. An
# unclosed ITM 0DTE contract is assigned 100 shares -- roughly $77,000 of stock per contract at
# current SPY -- against a ~$5,000 account. On paper that is a number in a ledger; live it is an
# account-ending margin call. This is exactly the class of gap that never shows up in paper
# results and only appears the first time real money is on the line.
#
# The roster is now DERIVED from the fleet registry (active + paper-account arms) intersected
# with the arms that actually have creds, so a new arm is covered the moment it is registered
# rather than the next time someone remembers to edit this list.
MAX_RETRIES = 3

# W2 KILL-SWITCH WIRING FIX (2026-09-01 audit): _escalate_inner used to write ONLY
# kill-switch-{arm}.json -- a file NOTHING on the live gate path reads. heartbeat_core.py's
# entry gate reads `cb.get('tripped')` off the account's OWN circuit-breaker.json (see that
# module's ~line 2604), so a 3x partial-fill escalation never actually halted the arm it was
# escalating. Only the two CORE arms (safe-2, bold-2) run through mcp_heartbeat/
# heartbeat_core.py and therefore have a circuit-breaker.json on the live gate path; the
# fleet arms (safe-3, risky-1, risky-3) halt through fleet_executor.py instead, which is
# FROZEN for the September config window and out of scope here -- they still get the
# kill-switch-{arm}.json file (unread today, but harmless and possibly wired up later).
CORE_BREAKER_MAP: dict[str, dict[str, str]] = {
    "safe-2": {
        "path": "automation/state/circuit-breaker.json",
        "reason_field": "tripped_reason",
        "at_field": "tripped_at",
    },
    "bold-2": {
        "path": "automation/state/aggressive/circuit-breaker.json",
        "reason_field": "trip_reason",
        "at_field": "tripped_at_et",
    },
}


def _active_arms() -> list[str]:
    """Active SPY arms from the fleet registry. Falls back to the two core arms if the
    registry is unreadable -- flattening SOMETHING beats flattening nothing."""
    try:
        reg = json.loads((_REPO / "automation" / "state" / "fleet" / "accounts.json")
                         .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["safe-2", "bold-2"]
    out = []
    for arm in reg.get("arms", []):
        acct = arm.get("account_number")
        if not isinstance(acct, str) or not acct.startswith("PA"):
            continue          # skips futures/sim arms -- not SPY options
        if str(arm.get("status") or "").lower() != "active":
            continue          # skips retired arms
        aid = arm.get("id") or arm.get("arm_id")
        if aid:
            out.append(str(aid))
    return out or ["safe-2", "bold-2"]


ACCOUNTS = _active_arms()

LOG_DIR = _REPO / "automation" / "state" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Set GAMMA_EOD_DRY=1 to simulate without placing orders (weekend test / dry-run).
DRY = os.environ.get("GAMMA_EOD_DRY", "0") == "1"

# Position-read retries before declaring the flat status UNKNOWN (2026-08-13). Sized against the
# measured incident: bold-2's /v2/positions timed out at 15s repeatedly, and a persistence probe
# showed 4/6 eventually succeeding with one recovery taking 24.0s. Three attempts with a short
# gap covers a recovering endpoint without stalling the 15:55 flatten window.
READ_ATTEMPTS = 3
READ_RETRY_S = 2.0


# ---- helpers --------------------------------------------------------------------

def _et_ts() -> str:
    return et_now().strftime("%Y-%m-%d %H:%M:%S ET")


def _log_path() -> tuple[Path, Path]:
    date_str = et_now().strftime("%Y-%m-%d")
    return (
        LOG_DIR / f"eod-flatten-{date_str}.log",
        LOG_DIR / f"eod-flatten-{date_str}.jsonl",
    )


def _log(log_path: Path, msg: str) -> None:
    ts = _et_ts()
    line = f"[{ts}] {msg}"
    print(line)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _append_jsonl(jsonl_path: Path, record: dict) -> None:
    with jsonl_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _escalate(arm: str, remaining: int, errors: list, log: Path) -> None:
    """Terminal flatten failure -> halt the arm and leave a signal a human will actually see.

    Fail-soft by design: escalation must never raise back into the flatten loop, because the
    OTHER arms still need their turn. Each step is independently guarded AND the whole body is
    wrapped -- a per-step guard is not enough, because `_log` itself writes to disk and can
    raise (caught by test_escalate_never_raises_even_when_everything_fails, which failed on the
    first cut of this function for exactly that reason: the kill-switch write was guarded, the
    log call reporting its failure was not).
    """
    try:
        _escalate_inner(arm, remaining, errors, log)
    except Exception:  # noqa: BLE001 -- last-resort: an escalation must never abort the sweep
        pass


def _escalate_inner(arm: str, remaining: int, errors: list, log: Path) -> None:
    """Body of _escalate. See that function for the fail-soft contract."""
    reason = (f"EOD_FLATTEN_PARTIAL_FILL: {remaining} contract(s) NOT closed for {arm} -- "
              f"MANUAL ACTION REQUIRED. SPY options settle PHYSICALLY; an unclosed ITM 0DTE "
              f"is assigned ~100 shares/contract. errors={errors[:3]}")
    # 1. Kill-switch file -- halts the arm so it cannot open more risk while unresolved.
    try:
        ks = _REPO / "automation" / "state" / f"kill-switch-{arm}.json"
        ks.write_text(json.dumps({
            "armed": True, "arm": arm, "reason": reason,
            "set_by": "eod_flatten.py", "set_at_et": _et_ts(),
            "clear_by": "resolve the open position manually, then delete this file",
        }, indent=2), encoding="utf-8")
        _log(log, f"EOD_FLATTEN_KILLSWITCH_WRITTEN arm={arm} path={ks.name}")
    except Exception as exc:  # noqa: BLE001
        _log(log, f"EOD_FLATTEN_KILLSWITCH_FAILED arm={arm} err={type(exc).__name__}: {exc}")
    # 1b. Trip the account's OWN circuit-breaker.json too -- see CORE_BREAKER_MAP docstring
    # above for why the kill-switch-{arm}.json file alone never actually halted anything.
    cb_cfg = CORE_BREAKER_MAP.get(arm)
    if cb_cfg:
        try:
            cb_path = _REPO / cb_cfg["path"]
            cb = json.loads(cb_path.read_text(encoding="utf-8")) if cb_path.exists() else {}
            cb["tripped"] = True
            cb[cb_cfg["reason_field"]] = f"EOD_FLATTEN_ESCALATION: {reason}"
            cb[cb_cfg["at_field"]] = _et_ts()
            cb["escalation_unresolved"] = True
            tmp = cb_path.with_suffix(cb_path.suffix + ".tmp")
            tmp.write_text(json.dumps(cb, indent=2), encoding="utf-8")
            tmp.replace(cb_path)
            _log(log, f"EOD_FLATTEN_CIRCUIT_BREAKER_TRIPPED arm={arm} path={cb_path.name}")
        except Exception as exc:  # noqa: BLE001
            _log(log, f"EOD_FLATTEN_CIRCUIT_BREAKER_FAILED arm={arm} err={type(exc).__name__}: {exc}")
    else:
        _log(log, f"EOD_FLATTEN_CIRCUIT_BREAKER_SKIPPED arm={arm} -- no core breaker mapping "
                   f"(fleet arm; halt path is fleet_executor.py, frozen/out of scope for W2)")
    # 2. STATUS.md "Known broken" -- the surface J's morning read already looks at.
    try:
        status = _REPO / "automation" / "overnight" / "STATUS.md"
        if status.exists():
            with status.open("a", encoding="utf-8") as fh:
                fh.write(
                    "\n- 🚨 **" + _et_ts() + " EOD FLATTEN FAILED - " + arm + "** - "
                    + str(remaining) + " contract(s) still open. Physical assignment risk. "
                    + reason + "\n"
                )
            _log(log, f"EOD_FLATTEN_STATUS_APPENDED arm={arm}")
    except Exception as exc:  # noqa: BLE001
        _log(log, f"EOD_FLATTEN_STATUS_FAILED arm={arm} err={type(exc).__name__}: {exc}")


def _flatten_account(arm: str, creds: dict[str, str], log: Path, jsonl: Path) -> dict:
    """Flatten one account.  Returns a result dict.  NEVER raises."""
    ts_start = _et_ts()
    result: dict = {"arm": arm, "ts": ts_start, "dry": DRY}

    try:
        # Step 1: check current positions.
        #
        # CHECKED READ (2026-08-13). This used open_spy_option_positions, which collapses ANY
        # read failure to [] -- so a broker timeout landed here as qty_total==0 and returned
        # "EOD_FLATTEN_NOOP -- already flat". On 2026-08-13 bold-2's /v2/positions hung for ~15
        # minutes while its other endpoints answered in 0.2s; had that window covered 15:55, a
        # live 0DTE contract would have EXPIRED while this logged that everything was fine.
        # A missed flatten on 0DTE is not a delayed exit, it is total loss.
        #
        # Retry a few times, then FAIL LOUD. An unreadable arm is reported as READ_FAILED, never
        # as NOOP -- "could not measure" must never render as "measured and fine" (C7).
        positions: list = []
        read_ok = False
        for _attempt in range(READ_ATTEMPTS):
            positions, read_ok = fleet_broker.open_spy_option_positions_checked(creds)
            if read_ok:
                break
            time.sleep(READ_RETRY_S)
        if not read_ok:
            msg = (f"EOD_FLATTEN_READ_FAILED arm={arm} -- positions query failed "
                   f"{READ_ATTEMPTS}x; CANNOT confirm flat. NOT reporting NOOP.")
            _log(log, msg)
            result.update({"outcome": "READ_FAILED", "closed": [], "remaining": None,
                           "errors": [f"positions query failed {READ_ATTEMPTS}x -- flat status UNKNOWN"]})
            _append_jsonl(jsonl, result)
            return result

        symbols = [str(p.get("symbol")) for p in positions]
        qty_total = sum(abs(int(float(p.get("qty", 0)))) for p in positions)

        if qty_total == 0:
            msg = f"EOD_FLATTEN_NOOP arm={arm} -- already flat (0 open SPY option positions)"
            _log(log, msg)
            result.update({"outcome": "NOOP", "closed": [], "errors": [], "remaining": 0})
            _append_jsonl(jsonl, result)
            return result

        _log(log, f"EOD_FLATTEN_START arm={arm} qty={qty_total} symbols={symbols} dry={DRY}")

        if DRY:
            msg = f"EOD_FLATTEN_DRY_RUN arm={arm} -- would close {qty_total} contracts: {symbols}"
            _log(log, msg)
            result.update({"outcome": "DRY_RUN", "would_close": symbols, "qty": qty_total})
            _append_jsonl(jsonl, result)
            return result

        # Step 2: retry-until-zero loop (mirrors eod-flatten.md partial-fill scar)
        all_closed: list[str] = []
        all_errors: list[str] = []
        final_remaining = qty_total

        for attempt in range(1, MAX_RETRIES + 1):
            # arm/reason are LOGGING-ONLY labels (default None; see close_all_spy_options'
            # docstring) that give the order-intent ledger the WHY this path never wrote.
            # They change nothing about the orders placed. 2026-08-19.
            res = fleet_broker.close_all_spy_options(
                creds, live=True, arm=arm,
                reason=(f"EOD_FLATTEN attempt {attempt}/{MAX_RETRIES} -- 15:55 ET forced "
                        f"close; SPY options settle PHYSICALLY and an unclosed ITM 0DTE is "
                        f"assigned ~100 shares/contract"))
            closed = res.get("closed", [])
            errors = res.get("errors", [])
            remaining = res.get("remaining", 0)

            all_closed.extend(closed)
            all_errors.extend(errors)
            final_remaining = remaining

            _log(log, (
                f"EOD_FLATTEN_ATTEMPT arm={arm} attempt={attempt}/{MAX_RETRIES} "
                f"closed={closed} errors={errors} remaining={remaining}"
            ))

            if remaining == 0:
                break

        outcome = "SUCCESS" if final_remaining == 0 else "PARTIAL_FILL_ESCALATION"
        _log(log, (
            f"EOD_FLATTEN_{outcome} arm={arm} "
            f"closed={all_closed} errors={all_errors} remaining={final_remaining}"
        ))
        # ESCALATION FIX (2026-08-18). This branch LOGGED "PARTIAL_FILL_ESCALATION" and did
        # nothing else. The actual escalation -- write a kill-switch, ping Discord -- lived
        # ONLY in automation/prompts/eod-flatten.md, which this module's own docstring
        # explicitly demotes to "a verbose-confirmation fallback (NOT the execution path)".
        # So on the path that actually runs, a 3x-failed flatten was a log line nobody reads,
        # while an ITM 0DTE walked into physical assignment. The word "ESCALATION" in an
        # outcome string is not an escalation.
        if final_remaining != 0:
            _escalate(arm, final_remaining, all_errors, log)

        result.update({
            "outcome": outcome,
            "closed": all_closed,
            "errors": all_errors,
            "remaining": final_remaining,
        })
        _append_jsonl(jsonl, result)
        return result

    except Exception as exc:
        msg = f"EOD_FLATTEN_ERROR arm={arm} exception={type(exc).__name__}: {exc}"
        _log(log, msg)
        result.update({"outcome": "ERROR", "error": str(exc)})
        try:
            _append_jsonl(jsonl, result)
        except Exception:
            pass
        return result


# ---- main -----------------------------------------------------------------------

def main() -> int:
    log_path, jsonl_path = _log_path()
    _log(log_path, f"EOD_FLATTEN_FIRE ts={_et_ts()} dry={DRY} accounts={ACCOUNTS}")

    # Load creds once (fail-open per account if missing)
    try:
        all_creds = fleet_broker.load_creds()
    except Exception as exc:
        _log(log_path, f"EOD_FLATTEN_CREDS_ERROR: {exc} -- cannot flatten any account")
        _append_jsonl(jsonl_path, {"outcome": "CREDS_ERROR", "error": str(exc), "ts": _et_ts()})
        return 1

    results = []
    for arm in ACCOUNTS:
        if arm not in all_creds:
            msg = f"EOD_FLATTEN_SKIP_NO_CREDS arm={arm} -- not found in secrets.json"
            _log(log_path, msg)
            rec = {"arm": arm, "outcome": "SKIP_NO_CREDS", "ts": _et_ts()}
            _append_jsonl(jsonl_path, rec)
            results.append(rec)
            continue

        result = _flatten_account(arm, all_creds[arm], log_path, jsonl_path)
        results.append(result)

    # Summary
    outcomes = [r.get("outcome", "UNKNOWN") for r in results]
    _log(log_path, f"EOD_FLATTEN_COMPLETE outcomes={outcomes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
