"""futures_trader_runner.py -- the scheduled entry point for the autonomous futures lane.

Fired by Gamma_FuturesTrader (see install-futures-trader.ps1). One invocation = one
see -> decide -> act tick against the configured broker backend, plus a liveness beacon
written on EVERY fire including no-ops.

FAIL-OPEN, ALWAYS EXIT 0. A scheduled task that exits non-zero on a quiet market trains
everyone to ignore its exit code (C7: audit outputs, not exit codes). This runner's
CONTRACT is that it always writes state -- the monitor reads that state, not this
process's return value. A genuine failure surfaces as a stale heartbeat plus a row in
the failure log, which is a signal that cannot be mistaken for silence.

BACKEND is `fillsim` unless FUTURES_BROKER says otherwise. `fillsim` touches no external
account and no credentials; it is safe to run unattended, which is the entire reason the
lane can start before the venue question is settled.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "setup/scripts"):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

LOG_DIR = REPO / "automation" / "state" / "logs"
STATE_DIR = REPO / "automation" / "state" / "futures" / "trader"
FAILURE_LOG = STATE_DIR / "runner-failures.jsonl"


def _log(msg: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y-%m-%d")
        with (LOG_DIR / f"futures-trader-{stamp}.log").open("a", encoding="utf-8") as fh:
            fh.write(f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}\n")
    except Exception:  # noqa: BLE001
        pass


def _record_failure(stage: str, err: BaseException) -> None:
    """A failure must leave a mark. Silence is the only true failure (OP-25)."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with FAILURE_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "at": dt.datetime.now().isoformat(timespec="seconds"),
                "stage": stage,
                "error": f"{type(err).__name__}: {err}",
                "traceback": traceback.format_exc()[-2000:],
            }) + "\n")
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    instrument = os.environ.get("FUTURES_INSTRUMENT", "MES")
    backend = os.environ.get("FUTURES_BROKER", "fillsim")
    try:
        from futures import futures_trader_core as core  # noqa: PLC0415

        rec = core.run_tick(instrument, backend=backend)
        _log(f"tick {instrument}/{backend}: {rec.get('action')} -- {rec.get('reason')} "
             f"(feed={rec.get('freshness')}, signals={rec.get('n_signals')})")
    except Exception as e:  # noqa: BLE001 -- fail open, but never fail SILENT
        _log(f"TICK FAILED: {type(e).__name__}: {e}")
        _record_failure("run_tick", e)
        # Still stamp the beacon so the monitor can tell "ran and failed" from "never ran".
        try:
            from futures.futures_trader_core import _write_heartbeat  # noqa: PLC0415
            from futures.futures_session import et_now  # noqa: PLC0415

            _write_heartbeat(et_now(), "ERROR", {"error": f"{type(e).__name__}: {e}"})
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
