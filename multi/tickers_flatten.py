"""multi/tickers_flatten.py -- EOD safety-net flatten for the TICKERS LANE (14:52 ET).

For each of the three arms with resolvable, pin-consistent credentials: closes every OPEN
equity-option position narrowed to that arm's OWN universe roots
(`multi/lib/broker.py::close_all_equity_options`, which is provably OCC-shape-safe -- see
`backtest/tests/test_multi_broker.py`'s crypto-safety proof) and never touches another arm's
contracts. `--shadow` previews without submitting (armed=False, nothing sent).

This is the SAFETY NET behind `multi/execute.py`'s own expiry-day flatten schedule
(`exits.flatten_schedule_et`, evaluated every 2 minutes inside core.tick()'s exit_eval rows):
a position execute.py's own logic somehow failed to close by its 14:50 hard backstop still
gets one more close attempt here at 14:52 ET, registered as a SEPARATE scheduled task
(`Gamma_TickersEodFlatten`) so a stall or crash in the 2-minute execute.py cadence cannot also
disable this backstop.

$ python multi/tickers_flatten.py [--shadow]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_SCRIPTS_DIR = REPO_ROOT / "setup" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from et_clock import et_now  # noqa: E402 -- the ONE clock on this rig

from multi.lib import broker as mb  # noqa: E402
from multi.lib import creds as mc  # noqa: E402

DEFAULT_PARAMS_PATH = REPO_ROOT / "automation" / "state" / "tickers" / "params.json"
STATE_DIR = REPO_ROOT / "automation" / "state" / "tickers"
ARM_NAMES = ("tickers-1", "tickers-2", "tickers-3")


def _load_pin(arm: str) -> Optional[str]:
    p = STATE_DIR / arm / "account.json"
    if not p.exists():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    num = doc.get("account_number")
    return str(num) if num else None


def flatten_one(lane_params: dict, arm: str, *, shadow: bool, ts: str) -> tuple[bool, str]:
    """(ok, one-line report). ok=False on any error for THIS arm -- never raises, and never
    prevents the caller from moving on to the next arm."""
    cfg = (lane_params.get("arms") or {}).get(arm)
    if not isinstance(cfg, dict):
        return True, f"[{ts}] {arm}: SKIP -- arms.{arm} missing from params"

    universe = [str(s).upper() for s in (cfg.get("universe") or [])]
    pinned = _load_pin(arm)
    arm_params = {**lane_params, "account": {"key_source": cfg.get("key_source"), "account_number": pinned or ""}}
    try:
        creds = mc.resolve(arm_params)
        mc.verify_account(creds)
    except mc.CredError as e:
        return True, f"[{ts}] {arm}: NO_CREDS/SKIP -- {e}"
    except Exception as e:  # noqa: BLE001 -- network/parse failure resolving/verifying
        return True, f"[{ts}] {arm}: SKIP -- verify failed {type(e).__name__}: {e}"

    try:
        res = mb.close_all_equity_options(creds, allowed_roots=universe, armed=not shadow, params=arm_params)
    except Exception as e:  # noqa: BLE001 -- one arm's flatten failure must never block the others
        return False, f"[{ts}] {arm}: FLATTEN_ERROR -- {type(e).__name__}: {e}"

    if shadow or res.get("_shadow"):
        return True, f"[{ts}] {arm}: SHADOW would_close={res.get('would_close')}"
    closed, errors = res.get("closed") or [], res.get("errors") or []
    line = f"[{ts}] {arm}: closed={closed} errors={errors}"
    return (not errors), line


def flatten_all(params_path: Path = DEFAULT_PARAMS_PATH, *, shadow: bool = False) -> int:
    try:
        lane_params = mc.load_params(params_path)
    except mc.CredError as e:
        print(f"[tickers-flatten] ABORT: cannot load {params_path}: {e}", file=sys.stderr)
        return 1

    ts = et_now().isoformat(timespec="seconds")
    any_error = False
    for arm in ARM_NAMES:
        try:
            ok, line = flatten_one(lane_params, arm, shadow=shadow, ts=ts)
        except Exception as e:  # noqa: BLE001 -- outer safety net: an arm must never take the process down
            ok, line = False, f"[{ts}] {arm}: UNCAUGHT -- {type(e).__name__}: {e}"
        print(line, file=sys.stderr if not ok else sys.stdout)
        any_error = any_error or not ok
    return 1 if any_error else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--shadow", action="store_true", help="preview only -- armed=False, nothing sent")
    ap.add_argument("--params", default=str(DEFAULT_PARAMS_PATH))
    args = ap.parse_args(argv)
    return flatten_all(Path(args.params), shadow=args.shadow)


if __name__ == "__main__":
    raise SystemExit(main())
