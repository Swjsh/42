#!/usr/bin/env python
"""intraday_position_tracker.py -- append-on-CHANGE tracker for open option positions.

J directive 2026-08-10 mid-session: "let's keep monitoring, and let's make sure we have a very
detailed after action report for tonight... make sure we are able to reproduce this."

WHY THIS EXISTS AND THE NIGHTLY DOES NOT COVER IT: winner_autopsy and the EOD pipeline run
AFTER the close and read the broker's realized fills. They can tell you a position closed at
X. They CANNOT tell you the intraday path -- what the high-water mark was, at what minute the
lock armed, how many cents short of TP1 it stalled, or how long it sat unprotected at +90%.
Those fields live in the exit-state ledger and are OVERWRITTEN as the position evolves and
discarded when it closes. Today the three 773C positions stalled 1-21 CENTS short of TP1 while
+81% to +97% unprotected; that fact is only knowable from a live capture. This closes that gap.

DESIGN -- deliberately boring:
  - Polls the broker + the exit-state ledger, writes a row ONLY when something changed
    (position qty, price bucket, HWM, tp1_filled, or lock state). A per-minute full dump would
    be 390 near-identical rows/day and nobody would read it.
  - Change-detection is on a rounded fingerprint so a 1-cent quote wiggle does not spam rows,
    but any qty / TP1 / lock transition ALWAYS writes -- those are the events that matter.
  - READ-ONLY. Places no orders, cancels nothing, edits no params. It cannot affect a trade.
  - Fail-open per arm: one bad key or a broker hiccup logs an error row and the loop continues.
  - $0, stdlib only, no LLM.

Output: analysis/deep-research/2026-08-10-live/position-track.jsonl (append-only)
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FLEET = REPO / "automation" / "state" / "fleet"
SECRETS = FLEET / "secrets.json"
SKIP = {"safe-1", "kalshi-1"}
POLL_SECONDS = 60


def _et_now() -> str:
    try:
        out = subprocess.run([sys.executable, str(REPO / "setup" / "scripts" / "et_clock.py")],
                             capture_output=True, text=True, timeout=30).stdout
        return out.splitlines()[0].strip()
    except Exception:  # noqa: BLE001
        return dt.datetime.now().isoformat(timespec="seconds") + " (LOCAL fallback)"


def _get(url: str, key: str, sec: str):
    req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key,
                                               "APCA-API-SECRET-KEY": sec})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


def _exit_state(arm: str) -> dict:
    p = FLEET / arm / "exit-state.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _fingerprint(arm: str, pos: list, st: dict) -> str:
    """What counts as 'changed'. qty / tp1_filled / lock_armed are ALWAYS significant;
    price and HWM are bucketed to 5c so quote noise does not generate rows."""
    parts = [arm]
    for p in sorted(pos, key=lambda x: x.get("symbol", "")):
        parts.append(f"{p['symbol']}:{p['qty']}:{round(float(p.get('current_price') or 0) / 0.05)}")
    for sym, s in sorted(st.items()):
        parts.append(f"{sym}:{s.get('tp1_filled')}:{s.get('profit_lock_armed')}:"
                     f"{round(float(s.get('hwm_premium') or 0) / 0.05)}:"
                     f"{round(float(s.get('runner_stop_premium') or 0) / 0.05)}")
    return "|".join(parts)


def main() -> int:
    out_dir = REPO / "analysis" / "deep-research" / "2026-08-10-live"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "position-track.jsonl"

    creds = json.loads(SECRETS.read_text(encoding="utf-8"))
    accts = creds.get("accounts") or creds
    arms = {a: c for a, c in accts.items()
            if isinstance(c, dict) and a not in SKIP and (c.get("key") or c.get("api_key"))}
    print(f"[tracker] watching {sorted(arms)} every {POLL_SECONDS}s -> {out}", flush=True)

    last: dict[str, str] = {}
    while True:
        stamp = _et_now()
        # Stop cleanly after the flatten window; nothing to track once all arms are flat.
        hhmm = stamp[11:16] if len(stamp) > 16 else ""
        for arm, c in arms.items():
            k = c.get("key") or c.get("api_key")
            s = c.get("secret") or c.get("api_secret")
            try:
                pos = _get("https://paper-api.alpaca.markets/v2/positions", k, s)
            except Exception as e:  # noqa: BLE001
                json.loads("{}") if False else None
                with out.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"ts_et": stamp, "arm": arm,
                                         "error": f"{type(e).__name__}: {e}"[:160]}) + "\n")
                continue
            st = _exit_state(arm)
            fp = _fingerprint(arm, pos, st)
            if last.get(arm) == fp:
                continue
            last[arm] = fp
            row = {"ts_et": stamp, "arm": arm, "n_positions": len(pos), "positions": [], "exit_state": {}}
            for p in pos:
                e = float(p["avg_entry_price"]); cur = float(p.get("current_price") or 0)
                row["positions"].append({
                    "symbol": p["symbol"], "qty": p["qty"], "avg_entry": e, "last": cur,
                    "pct_from_entry": round((cur / e - 1) * 100, 1) if e else None,
                    "unrealized_pl": float(p["unrealized_pl"]),
                })
            for sym, s in st.items():
                ep = float(s.get("entry_premium") or 0)
                hwm = float(s.get("hwm_premium") or 0)
                row["exit_state"][sym] = {
                    "entry_premium": ep, "hwm_premium": hwm,
                    "hwm_pct": round((hwm / ep - 1) * 100, 1) if ep else None,
                    "tp1_target": round(ep * (1 + float(s.get("tp1_premium_pct") or 0)), 4) if ep else None,
                    "tp1_filled": s.get("tp1_filled"),
                    "profit_lock_armed": s.get("profit_lock_armed"),
                    "runner_stop_premium": s.get("runner_stop_premium"),
                    "stop_mode": s.get("stop_mode"),
                }
            with out.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, default=str) + "\n")
            print(f"[tracker] {stamp[11:19]} {arm}: {len(pos)} pos "
                  + ", ".join(f"{p['symbol'][-9:]} q={p['qty']} {p['pct_from_entry']:+.0f}%"
                              for p in row["positions"]), flush=True)
        if hhmm and hhmm >= "16:00":
            print("[tracker] past 16:00 ET -- stopping", flush=True)
            return 0
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
