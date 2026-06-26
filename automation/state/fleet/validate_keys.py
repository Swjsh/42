"""Validate fleet Alpaca paper keys against the live broker.

Reads creds from the gitignored secrets.json (never from argv), hits the
read-only /v2/account endpoint for each, prints account#/status/equity only
(never the secret). Pure stdlib. Source of truth = broker (lesson C11).
"""
import json
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(HERE, "secrets.json"), encoding="utf-8") as fh:
    accounts = json.load(fh)["accounts"]

print(f"{'arm':9} {'account#':14} {'status':9} {'equity':>11} {'cash':>11} {'created':10}")
print("-" * 70)
for name, c in accounts.items():
    req = urllib.request.Request(
        c["base_url"].rstrip("/") + "/v2/account",
        headers={
            "APCA-API-KEY-ID": c["key"],
            "APCA-API-SECRET-KEY": c["secret"],
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            d = json.load(resp)
        print(f"{name:9} {d.get('account_number',''):14} {d.get('status',''):9} "
              f"{d.get('equity',''):>11} {d.get('cash',''):>11} {d.get('created_at','')[:10]:10}")
    except Exception as e:  # noqa: BLE001 - report any auth/network failure inline
        print(f"{name:9} {'ERROR':14} {str(e)[:55]}")
