"""multi/tickers_verify.py -- resolves + verifies all three TICKERS LANE paper accounts.

Run this AFTER pasting `automation/state/tickers/secrets.json` (copy from
`secrets.json.example`). For each arm (tickers-1/2/3): resolves credentials via
`multi/lib/creds.py` (refuses anything but a paper base_url), reads /v2/account, prints
account_number / equity / buying_power / options_approved_level / status with the key
masked to its first 4 characters, and pins `automation/state/tickers/<arm>/account.json` --
the same pin `multi/execute.py` refuses to trade past if a later key resolves to a
different account. Exits non-zero if ANY arm fails, so this is the one command that gates
"are we ready to trade tomorrow".

$ python multi/tickers_verify.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_SCRIPTS_DIR = REPO_ROOT / "setup" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from et_clock import et_now  # noqa: E402 -- the ONE clock on this rig

from multi.lib import creds as mc  # noqa: E402

DEFAULT_PARAMS_PATH = REPO_ROOT / "automation" / "state" / "tickers" / "params.json"
STATE_DIR = REPO_ROOT / "automation" / "state" / "tickers"
ARM_NAMES = ("tickers-1", "tickers-2", "tickers-3")


def _write_pin(arm: str, account_number: str, equity, pinned_at_et: str) -> None:
    p = STATE_DIR / arm / "account.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "account_number": account_number, "equity_at_pin": equity,
        "pinned_at_et": pinned_at_et,
    }, indent=2), encoding="utf-8")


def verify_one(lane_params: dict, arm: str) -> tuple[bool, str]:
    """(ok, one-line report) for a single arm. Never raises -- every failure mode is
    reported as ok=False with the reason in the report line."""
    cfg = (lane_params.get("arms") or {}).get(arm)
    if not isinstance(cfg, dict):
        return False, f"{arm}: FAIL -- arms.{arm} missing from params.json"

    arm_params = {**lane_params, "account": {"key_source": cfg.get("key_source"), "account_number": ""}}
    try:
        creds = mc.resolve(arm_params)
        acct = mc.verify_account(creds)
    except mc.CredError as e:
        return False, f"{arm}: FAIL -- {e}"
    except Exception as e:  # noqa: BLE001 -- network/parse failure, report and continue
        return False, f"{arm}: FAIL -- {type(e).__name__}: {e}"

    account_number = str(acct.get("account_number") or "")
    _write_pin(arm, account_number, acct.get("equity"), et_now().isoformat(timespec="seconds"))
    line = (f"{arm}: OK key={mc.masked(creds.key)} account={account_number} "
            f"equity={acct.get('equity')} buying_power={acct.get('buying_power')} "
            f"options_approved_level={acct.get('options_approved_level')} "
            f"status={acct.get('status')}")
    return True, line


def verify_all(params_path: Path = DEFAULT_PARAMS_PATH) -> int:
    try:
        lane_params = mc.load_params(params_path)
    except mc.CredError as e:
        print(f"FAIL: cannot load {params_path}: {e}")
        return 1

    all_ok = True
    for arm in ARM_NAMES:
        ok, line = verify_one(lane_params, arm)
        print(line)
        all_ok = all_ok and ok
    print("ALL ARMS VERIFIED -- ready to trade" if all_ok else "ONE OR MORE ARMS FAILED -- see above")
    return 0 if all_ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--params", default=str(DEFAULT_PARAMS_PATH))
    args = ap.parse_args(argv)
    return verify_all(Path(args.params))


if __name__ == "__main__":
    raise SystemExit(main())
