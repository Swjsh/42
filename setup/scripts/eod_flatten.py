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
ACCOUNTS = ["safe-2", "bold-2"]
MAX_RETRIES = 3

LOG_DIR = _REPO / "automation" / "state" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Set GAMMA_EOD_DRY=1 to simulate without placing orders (weekend test / dry-run).
DRY = os.environ.get("GAMMA_EOD_DRY", "0") == "1"


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


def _flatten_account(arm: str, creds: dict[str, str], log: Path, jsonl: Path) -> dict:
    """Flatten one account.  Returns a result dict.  NEVER raises."""
    ts_start = _et_ts()
    result: dict = {"arm": arm, "ts": ts_start, "dry": DRY}

    try:
        # Step 1: check current positions
        positions = fleet_broker.open_spy_option_positions(creds)
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
            res = fleet_broker.close_all_spy_options(creds, live=True)
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
