#!/usr/bin/env python3
"""Install Kalshi credentials WITHOUT anyone pasting key material into a chat or a file.

WHY THIS EXISTS: on 2026-08-09 a private key was pasted into a chat transcript and had to be
rotated. The fix is not "be careful" -- it is removing the step where a human handles key
material at all. You download the .pem from Kalshi, point this at it, and it does the rest.

    python automation/kalshi/setup_credentials.py --pem ~/Downloads/kalshi-key.pem --key-id <UUID>

What it does:
  * validates the PEM actually parses as an RSA private key (fail fast, clear message)
  * MOVES it to automation/state/fleet/kalshi-1.pem (gitignored) with 0600 where supported
  * MERGES a kalshi-1 block into the gitignored secrets.json -- never clobbers the other arms
  * backs the secrets file up first
  * verifies against the live API by reading the account balance
  * NEVER prints, logs, or echoes key material

Nothing here touches a tracked file. Run it locally; it needs no network except the final check.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parents[1]

SECRETS = REPO / "automation" / "state" / "fleet" / "secrets.json"
DEST_PEM = REPO / "automation" / "state" / "fleet" / "kalshi-1.pem"

# Kalshi's own recommended hosts (docs: getting_started/api_environments).
# Credentials are NOT shared across environments -- a demo key only works on demo.
PROD = "https://external-api.kalshi.com/trade-api/v2"
DEMO = "https://external-api.demo.kalshi.co/trade-api/v2"


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Install Kalshi credentials safely")
    ap.add_argument("--pem", required=True, help="path to the .pem downloaded from Kalshi")
    ap.add_argument("--key-id", required=True, help="the API Key ID (UUID) shown in Kalshi")
    ap.add_argument("--arm", default="kalshi-1")
    ap.add_argument("--demo", action="store_true", help="install against the DEMO environment")
    ap.add_argument("--keep-original", action="store_true",
                    help="copy instead of move (default is MOVE, so no stray copy is left)")
    args = ap.parse_args()

    src = Path(os.path.expanduser(args.pem)).resolve()
    if not src.exists():
        die(f"pem not found: {src}")

    # --- validate BEFORE touching anything -------------------------------
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        key = serialization.load_pem_private_key(src.read_bytes(), password=None)
    except ImportError:
        die("`cryptography` is not importable. Run with the venv on PYTHONPATH:\n"
            "  PYTHONPATH=backtest/.venv/Lib/site-packages python automation/kalshi/setup_credentials.py ...")
    except Exception as e:  # noqa: BLE001 - never echo key material in the message
        die(f"that file is not a readable unencrypted PEM private key ({type(e).__name__})")
    if not isinstance(key, rsa.RSAPrivateKey):
        die("key is not RSA -- Kalshi requires an RSA key")
    print(f"[ok] PEM parses as a {key.key_size}-bit RSA private key")

    if len(args.key_id) < 8:
        die("--key-id does not look like a Kalshi API Key ID")

    # --- install the key file --------------------------------------------
    DEST_PEM.parent.mkdir(parents=True, exist_ok=True)
    if args.keep_original:
        shutil.copy2(src, DEST_PEM)
        print(f"[ok] copied key -> {DEST_PEM.relative_to(REPO)}")
    else:
        shutil.move(str(src), str(DEST_PEM))
        print(f"[ok] MOVED key -> {DEST_PEM.relative_to(REPO)} (no copy left at the source)")
    try:
        os.chmod(DEST_PEM, 0o600)
    except OSError:
        pass  # Windows ACLs differ; the gitignore is the load-bearing protection here

    # --- merge into secrets.json, never clobber --------------------------
    if SECRETS.exists():
        backup = SECRETS.with_suffix(f".json.bak-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(SECRETS, backup)
        print(f"[ok] backed up secrets -> {backup.name}")
        try:
            blob = json.loads(SECRETS.read_text())
        except json.JSONDecodeError as e:
            die(f"existing secrets.json is not valid JSON, refusing to touch it: {e}")
    else:
        blob = {"_doc": "GITIGNORED credential store. Never commit."}

    accounts = blob.setdefault("accounts", {})
    existing = set(accounts)
    accounts[args.arm] = {
        "key": args.key_id,
        "secret_path": str(DEST_PEM.relative_to(REPO)).replace("\\", "/"),
        "base_url": DEMO if args.demo else PROD,
        "label": args.arm.upper(),
    }
    SECRETS.write_text(json.dumps(blob, indent=1))
    preserved = sorted(existing - {args.arm})
    print(f"[ok] wrote accounts.{args.arm} (preserved {len(preserved)} existing arms: "
          f"{', '.join(preserved) if preserved else 'none'})")

    # --- verify against the live API -------------------------------------
    print("[..] verifying against Kalshi ...")
    try:
        from kalshi_client import KalshiClient, load_credentials, KalshiError
        creds = load_credentials(args.arm)
        if not creds:
            die("credentials did not load back -- check the secrets file")
        client = KalshiClient(creds)
        bal = client.balance()
        cents = bal.get("balance")
        if isinstance(cents, (int, float)):
            print(f"[OK] AUTHENTICATED. balance = ${cents / 100:.2f}")
        else:
            print(f"[OK] AUTHENTICATED. balance payload = {bal}")
    except Exception as e:  # noqa: BLE001
        print(f"[!!] credentials installed but the live check FAILED: {e}", file=sys.stderr)
        print("     Common causes: key belongs to the other environment (demo vs prod),\n"
              "     the key was revoked, or the machine clock is skewed (signing uses ms time).",
              file=sys.stderr)
        return 1

    print("\nDone. Nothing was committed; both the .pem and secrets.json are gitignored.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
