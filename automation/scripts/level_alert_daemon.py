"""Level Alert Daemon — local SPY price poller + level-cross notifier.

Runs every 30 seconds during RTH, polls SPY quote via yfinance (free, no API
cost), compares to named ★★+ levels in key-levels.json, writes alerts to
``automation/state/live-alerts.jsonl`` on any cross or close-touch.

Per CLAUDE.md OP 3 (cost-effectiveness): runs locally in pure Python, never
goes through Claude. Marginal cost ≈ $0/day. Per OP 22: this is the L2-L3
piece of the WATCHER_2.0 plan (real-time level monitoring without burning
tokens).

This is NOT a trade-placer. It is a NOTIFIER. The trade decision still goes
through the heartbeat ``Gamma_Heartbeat`` scheduled task. The daemon's job is
to UPGRADE the heartbeat's awareness — when a level interaction happens
between heartbeat ticks (3-min cycle), the daemon catches it within 30s.

Usage::

    pythonw.exe automation\\scripts\\level_alert_daemon.py
    pythonw.exe automation\\scripts\\level_alert_daemon.py --interval 30 --hours 6.5

Schedule via Windows Task Scheduler at 09:25 ET weekdays; exits at 16:05 ET.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
ALERTS_LOG = STATE_DIR / "live-alerts.jsonl"
KEY_LEVELS = STATE_DIR / "key-levels.json"

logger = logging.getLogger("level_alert_daemon")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

PROXIMITY_DOLLARS = 0.15
CROSS_HYSTERESIS = 0.05  # require this much beyond level before re-arming
MIN_STARS = 2  # only alert on ★★ and ★★★


def _load_levels() -> list[dict]:
    """Load ★★+ levels from key-levels.json."""
    if not KEY_LEVELS.exists():
        return []
    try:
        payload = json.loads(KEY_LEVELS.read_text(encoding="utf-8-sig"))
    except Exception:
        logger.exception("failed to read key-levels.json")
        return []
    out = []
    for lv in payload.get("levels") or []:
        if (lv.get("type") or "").lower() == "psychological":
            continue
        stars = 0
        try:
            stars = int((lv.get("strength") or {}).get("stars") or 0)
        except Exception:
            stars = 0
        if stars < MIN_STARS:
            continue
        try:
            price = float(lv.get("price"))
        except (TypeError, ValueError):
            continue
        out.append({
            "price": price,
            "type": lv.get("type") or "level",
            "tier": lv.get("tier") or "",
            "label": (lv.get("source") or lv.get("type") or "level")[:60],
            "stars": stars,
        })
    return out


def _fetch_spy_quote() -> Optional[float]:
    """Fetch latest SPY price via yfinance. Returns None if fetch fails.

    yfinance gives free intraday quotes during RTH with ~5 sec latency.
    """
    try:
        import yfinance as yf
        t = yf.Ticker("SPY")
        info = t.fast_info
        # fast_info.last_price is the most recent traded price
        price = info.last_price
        if price is None or price <= 0:
            return None
        return float(price)
    except Exception:
        logger.exception("yfinance fetch failed")
        return None


def _now_et() -> dt.datetime:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=-4)))


def _in_rth(now: dt.datetime) -> bool:
    rth_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    rth_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return rth_open <= now < rth_close


def _append_alert(event: dict) -> None:
    """Append a single event row to live-alerts.jsonl."""
    ALERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ALERTS_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=str) + "\n")


def _detect_crosses(
    last_price: Optional[float],
    cur_price: float,
    levels: list[dict],
    cross_state: dict[float, str],
) -> list[dict]:
    """Detect level crosses between last_price and cur_price.

    cross_state tracks the last-side per level ('above'/'below'/'init').
    Hysteresis prevents flicker when price oscillates within $0.05 of a level.

    Returns a list of cross-event dicts.
    """
    events = []
    for lv in levels:
        p = lv["price"]
        cur_side = "above" if cur_price > p + CROSS_HYSTERESIS else \
                   "below" if cur_price < p - CROSS_HYSTERESIS else None
        if cur_side is None:
            # In hysteresis band — emit a TOUCH alert (only if not already in band)
            prior = cross_state.get(p)
            if prior not in ("touch", "init", None):
                events.append({
                    "type": "touch",
                    "level_price": p,
                    "level_label": lv["label"],
                    "level_stars": lv["stars"],
                    "level_tier": lv["tier"],
                    "level_type": lv["type"],
                    "spy_price": cur_price,
                    "distance": round(cur_price - p, 4),
                    "prior_side": prior,
                })
                cross_state[p] = "touch"
            continue
        prior = cross_state.get(p)
        cross_state[p] = cur_side
        if prior is None or prior == "init":
            continue  # first observation, no cross
        if prior != cur_side and prior != "touch":
            events.append({
                "type": "cross",
                "level_price": p,
                "level_label": lv["label"],
                "level_stars": lv["stars"],
                "level_tier": lv["tier"],
                "level_type": lv["type"],
                "spy_price": cur_price,
                "from_side": prior,
                "to_side": cur_side,
                "distance": round(cur_price - p, 4),
            })
    return events


def run_daemon(interval_sec: int = 30, max_hours: float = 6.75) -> int:
    """Main loop. Exits after max_hours or at 16:05 ET.

    Returns the number of alert events written.
    """
    levels = _load_levels()
    if not levels:
        logger.warning("no ★★+ levels loaded — nothing to monitor")
        return 0

    logger.info("monitoring %d levels: %s", len(levels),
                ", ".join(f"{lv['price']:.2f}" for lv in levels))

    deadline = _now_et() + dt.timedelta(hours=max_hours)
    cross_state: dict[float, str] = {lv["price"]: "init" for lv in levels}
    last_price: Optional[float] = None
    events_written = 0

    while _now_et() < deadline:
        now = _now_et()
        if not _in_rth(now):
            logger.info("outside RTH — sleeping 60s")
            time.sleep(60)
            continue

        price = _fetch_spy_quote()
        if price is None:
            time.sleep(interval_sec)
            continue

        crosses = _detect_crosses(last_price, price, levels, cross_state)
        for c in crosses:
            event = {
                "ts": now.isoformat(),
                "source": "level_alert_daemon",
                **c,
            }
            _append_alert(event)
            events_written += 1
            logger.info(
                "ALERT: %s SPY=%.2f vs %.2f (%s) %s",
                c["type"].upper(), price, c["level_price"], c["level_label"],
                c.get("to_side") or c.get("prior_side") or "",
            )

        last_price = price
        time.sleep(interval_sec)

    logger.info("deadline reached — wrote %d alerts this session", events_written)
    return events_written


def main() -> int:
    parser = argparse.ArgumentParser(description="Level alert daemon")
    parser.add_argument("--interval", type=int, default=30,
                        help="poll interval in seconds (default 30)")
    parser.add_argument("--hours", type=float, default=6.75,
                        help="max runtime in hours (default 6.75 = open to close)")
    parser.add_argument("--once", action="store_true",
                        help="single tick — for testing")
    args = parser.parse_args()

    if args.once:
        levels = _load_levels()
        price = _fetch_spy_quote()
        print(f"levels={len(levels)} spy={price}")
        return 0

    return run_daemon(interval_sec=args.interval, max_hours=args.hours)


if __name__ == "__main__":
    sys.exit(0 if main() == 0 or main() > 0 else 1)
