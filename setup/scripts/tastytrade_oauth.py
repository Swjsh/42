"""Tastytrade connection tester — run after setting TT_SECRET and TT_REFRESH.

The OAuth "Create Grant" flow happens in the browser (no redirect server needed):
  1. Log into my.tastytrade.com
  2. Settings -> API Access -> OAuth Applications -> your app -> Manage -> Create Grant
  3. Copy the refresh_token shown
  4. Set env vars:
       TT_SECRET=<client_secret from when you created the app>
       TT_REFRESH=<refresh_token from Create Grant>
  5. Run this script to verify the connection works

Usage:
  set TT_SECRET=43092f9e739c0a0cb64b94754aa7ed9edf988ebb
  set TT_REFRESH=<your-refresh-token>
  python setup/scripts/tastytrade_oauth.py
"""
import asyncio
import os
import sys

try:
    import tastytrade as tt
except ImportError:
    print("Run: pip install tastytrade")
    sys.exit(1)

CLIENT_SECRET = os.getenv("TT_SECRET",   "43092f9e739c0a0cb64b94754aa7ed9edf988ebb")
REFRESH_TOKEN = os.getenv("TT_REFRESH",  "")
SANDBOX       = os.getenv("TT_SANDBOX",  "true").lower() != "false"

ENV_FILE = os.path.join(os.path.dirname(__file__), "..", "..", ".env.tastytrade")


async def main():
    if not REFRESH_TOKEN:
        print("\nERROR: TT_REFRESH is not set.")
        print("  1. Log into my.tastytrade.com")
        print("  2. Settings -> API Access -> OAuth Applications -> your app -> Manage -> Create Grant")
        print("  3. Copy the refresh_token and set: set TT_REFRESH=<token>")
        sys.exit(1)

    env = "SANDBOX (cert)" if SANDBOX else "PRODUCTION"
    print(f"\nTastytrade connection test — {env}")
    print(f"  CLIENT_SECRET: {CLIENT_SECRET[:8]}...")
    print(f"  REFRESH_TOKEN: {REFRESH_TOKEN[:12]}...")

    try:
        session  = tt.Session(CLIENT_SECRET, REFRESH_TOKEN, is_test=SANDBOX)
        accounts = await tt.Account.get(session)
        print(f"\nConnected! Found {len(accounts)} account(s):")
        for a in accounts:
            bal = await a.get_balances(session)
            equity = float(getattr(bal, "net_liquidating_value", 0) or 0)
            print(f"  {a.account_number}  equity=${equity:,.2f}")

        # Save to .env.tastytrade (gitignored)
        with open(ENV_FILE, "w") as f:
            f.write(f"TT_SECRET={CLIENT_SECRET}\n")
            f.write(f"TT_REFRESH={REFRESH_TOKEN}\n")
            f.write(f"TT_SANDBOX={'true' if SANDBOX else 'false'}\n")
        print(f"\nSaved to {os.path.abspath(ENV_FILE)}")
        print("\nNext: flip WATCH_ONLY = False in backtest/futures/tastytrade_paper.py")

    except Exception as e:
        print(f"\nConnection FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
