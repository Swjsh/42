"""SHOTGUN_SCALPER watcher — WATCH-ONLY observation pump.

Reads today's RTH bars, key levels, and the current ribbon/VIX snapshot,
calls `shotgun_scalper_detector.detect()`, and on a fired signal appends a
row to `automation/state/watcher-observations.jsonl`.

Per CLAUDE.md OP 21 (Watch-First Promotion Path), the watcher is strictly
observation-only. It does NOT place orders, does NOT mutate position state,
and does NOT call Alpaca.

**OP-21 STATUS: WATCH_FRAGILE — TBR HIGH-VOL ISOLATION PENDING (2026-05-24)**

16-month graded evidence via `shotgun_grader.py` (single-exit doctrine):
  - N=1723 deduped observations  WR=61.2%  Expectancy: -$1.63/obs
  - Tier breakdown:
      TRENDLINE_BREAK_RETEST: N=828   P&L=-$362.45  exp=-$0.44/obs
      LEVEL_REJECT_LIVE:      N=793   P&L=-$2,168   exp=-$2.73/obs
      OPEN_REJECTION:         N=102   P&L=-$276.51  exp=-$2.71/obs

**2026-05-24 VOLUME FILTER DISCOVERY:**
  Splitting TRENDLINE_BREAK_RETEST by bar volume relative to 20-bar avg:
      TBR vol >= 1.5x:  N=144  P&L=+$442.50  exp=+$3.07/obs  ← POSITIVE
      TBR vol <  1.5x:  N=684  P&L=-$804.95  exp=-$1.18/obs  ← NOISE

  The entire negative-expectancy result comes from low-vol TBR + LRL + OR.
  High-vol TBR is genuinely positive at +$3.07/obs (N=144, 16 months).

  Fix deployed: `shotgun_scalper_detector.TBR_VOL_CONFIRM_MULT=1.5` — low-vol
  TBR signals now emit with `confidence="low"` so downstream can filter.
  Next step: walk-forward + real-fills on TBR-vol-confirmed only.

NO PROMOTION PATH for full SHOTGUN under current exit knobs.
TBR-HIGH-VOL is a CANDIDATE for standalone watcher promotion if WF/RF pass.

NOTE: Do NOT grade shotgun observations with `watcher_grader.py` — that
applies the TP1+runner 50/50 split which is wrong for single-exit doctrine.
Use `shotgun_grader.py` exclusively. `watcher_grader.py` now skips
shotgun_scalper rows automatically.

The watcher mirrors the structure of `orb_watcher.py` /
`bullish_watcher.py` / `sniper_watcher.py` so it can be wired into
`watcher_live.py` / `runner.py` once registered.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from . import shotgun_scalper_detector as _detector  # local package import

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = REPO_ROOT / "automation" / "state"
OBS_LOG = STATE_DIR / "watcher-observations.jsonl"
KEY_LEVELS = STATE_DIR / "key-levels.json"

STRATEGY_NAME = "shotgun_scalper"
PROMOTION_STATUS = "WATCH_ONLY"


def _load_levels(path: Optional[Path] = None) -> list[dict]:
    """Load named levels from key-levels.json, returning a price/label list."""
    target = path or KEY_LEVELS
    if not target.exists():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8-sig"))
    except Exception:
        logger.exception("failed to read %s", target)
        return []
    raw = payload.get("levels") or []
    out: list[dict] = []
    for lv in raw:
        try:
            price = float(lv.get("price"))
        except (TypeError, ValueError):
            continue
        out.append(
            {
                "price": price,
                "label": lv.get("source") or lv.get("type") or "level",
                "tier": lv.get("tier"),
                "type": lv.get("type"),
                "stars": ((lv.get("strength") or {}).get("stars")),
            }
        )
    return out


def _resolve_today_bar_idx(today_bars: pd.DataFrame) -> int:
    """Return index of most recent closed bar."""
    if today_bars is None or today_bars.empty:
        return -1
    return len(today_bars) - 1


def detect_shotgun_scalper(
    today_bars: pd.DataFrame,
    today_bar_idx: Optional[int] = None,
    levels: Optional[list[dict]] = None,
    ribbon: Optional[dict] = None,
    vix: Optional[float] = None,
    htf_15m_stack: Optional[str] = None,
) -> Optional[dict]:
    """Thin wrapper over the detector. Returns the trigger dict or None.

    Args:
        today_bars: 5m bars for today (time/open/high/low/close/volume).
        today_bar_idx: optional explicit index of the current closed bar.
            Defaults to the last row.
        levels: explicit level list; if None, loaded from key-levels.json.
        ribbon: ribbon snapshot dict. Defaults to a neutral placeholder.
        vix: VIX print. Defaults to 17.0 (placeholder).
        htf_15m_stack: HTF 15m ribbon stack tag.
    """
    if today_bars is None or today_bars.empty:
        return None

    idx = today_bar_idx if today_bar_idx is not None else _resolve_today_bar_idx(today_bars)
    if idx < 0:
        return None

    lv = levels if levels is not None else _load_levels()
    rb = ribbon or {
        "fast": float("nan"),
        "pivot": float("nan"),
        "slow": float("nan"),
        "spread_cents": 0.0,
        "stack": "NEUTRAL",
    }
    v = vix if vix is not None else 17.0

    return _detector.detect(
        today_bars=today_bars,
        today_bar_idx=idx,
        levels=lv,
        ribbon=rb,
        vix=v,
        htf_15m_stack=htf_15m_stack,
    )


def _bar_snapshot(bar: pd.Series) -> dict:
    """Capture OHLC + volume for the current bar."""
    return {
        "open": float(bar["open"]),
        "high": float(bar["high"]),
        "low": float(bar["low"]),
        "close": float(bar["close"]),
        "volume": int(bar["volume"]) if "volume" in bar else 0,
    }


def log_observation(
    trigger: dict,
    bar: pd.Series,
    obs_log: Optional[Path] = None,
) -> dict:
    """Append a watcher observation to the JSONL log.

    Returns the observation row that was written.
    """
    target = obs_log or OBS_LOG
    target.parent.mkdir(parents=True, exist_ok=True)
    ts = bar.get("time") if bar.get("time") is not None else bar.get("timestamp_et")
    ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
    row = {
        "observed_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "bar_timestamp_et": ts_iso,
        "strategy": STRATEGY_NAME,
        "watcher_name": "shotgun_scalper_watcher",
        "setup_name": trigger["name"],
        "tier": trigger["tier"],
        "direction": trigger["direction"],
        "trigger_bar_time": trigger["trigger_bar_time"],
        "rejection_high": trigger["rejection_high"],
        "rejection_low": trigger["rejection_low"],
        "target_level": trigger["target_level"],
        "target_label": trigger["target_label"],
        "stop_chart": trigger["stop_chart"],
        "confidence": trigger["confidence"],
        "vol_ratio": trigger["vol_ratio"],
        "reasoning": trigger["reasoning"],
        "bar_ohlcv": _bar_snapshot(bar),
        "promotion_status": PROMOTION_STATUS,
        "would_be_outcome": None,
        "would_be_pnl_dollars": None,
    }
    with target.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")
    return row


def run_once(
    today_bars: pd.DataFrame,
    levels: Optional[list[dict]] = None,
    ribbon: Optional[dict] = None,
    vix: Optional[float] = None,
    htf_15m_stack: Optional[str] = None,
    obs_log: Optional[Path] = None,
) -> Optional[dict]:
    """One-shot live invocation: detect + log + return the observation row.

    Returns None if nothing fired, else the logged observation dict.
    """
    trigger = detect_shotgun_scalper(
        today_bars=today_bars,
        levels=levels,
        ribbon=ribbon,
        vix=vix,
        htf_15m_stack=htf_15m_stack,
    )
    if trigger is None:
        return None
    cur = today_bars.iloc[-1]
    return log_observation(trigger, cur, obs_log=obs_log)


def detect_shotgun_scalper_setup(
    bar: pd.Series,
    day_bars: pd.DataFrame,
    bar_idx_in_day: int,
    ribbon_state_dict: Optional[dict] = None,
    vix_now: Optional[float] = None,
):
    """Runner.py-compatible adapter that returns a WatcherSignal or None.

    Bridges the standard `run_all_watchers` call signature
    (bar, day_bars, bar_idx_in_day, ...) into the detector's typed inputs
    (today_bars, today_bar_idx, levels, ribbon, vix, htf_15m_stack).

    Levels are loaded fresh from key-levels.json on each call (cheap — sub-ms).
    """
    from . import WatcherSignal

    if day_bars is None or day_bars.empty or bar_idx_in_day < 0:
        return None

    levels = _load_levels()

    rb = ribbon_state_dict or {
        "fast": float("nan"),
        "pivot": float("nan"),
        "slow": float("nan"),
        "spread_cents": 0.0,
        "stack": "NEUTRAL",
    }
    if "spread_cents" not in rb and {"fast", "slow"}.issubset(rb.keys()):
        try:
            rb["spread_cents"] = round((float(rb["slow"]) - float(rb["fast"])) * 100, 1)
        except Exception:
            rb["spread_cents"] = 0.0
    if "stack" not in rb and {"fast", "pivot", "slow"}.issubset(rb.keys()):
        try:
            f, p, s = float(rb["fast"]), float(rb["pivot"]), float(rb["slow"])
            rb["stack"] = "BULL" if f > p > s else "BEAR" if f < p < s else "MIXED"
        except Exception:
            rb["stack"] = "NEUTRAL"

    v = vix_now if vix_now is not None else 17.0

    try:
        trigger = _detector.detect(
            today_bars=day_bars,
            today_bar_idx=bar_idx_in_day,
            levels=levels,
            ribbon=rb,
            vix=float(v),
            htf_15m_stack=None,
            auto_derive_intraday_levels=True,  # historical replay needs richer levels
        )
    except Exception:
        logger.exception("shotgun_scalper_detector raised")
        return None

    if trigger is None:
        return None

    direction = "short" if trigger.get("direction", "").lower() in ("put", "short", "bearish") else "long"
    entry_px = float(bar.get("close", trigger.get("rejection_low") or 0.0))
    target_px = float(trigger.get("target_level") or entry_px)
    stop_px = float(trigger.get("stop_chart") or entry_px)
    tier = trigger.get("tier")
    setup_name = trigger.get("name") or f"SHOTGUN_SCALPER_TIER_{tier}"

    return WatcherSignal(
        watcher_name="shotgun_scalper_watcher",
        setup_name=setup_name,
        direction=direction,
        entry_price=entry_px,
        stop_price=stop_px,
        tp1_price=target_px,
        runner_price=None,  # SHOTGUN doctrine: single exit, NO runner
        confidence=trigger.get("confidence", "medium"),
        reason=trigger.get("reasoning", "shotgun_scalper trigger"),
        triggers_fired=[setup_name],
        metadata={
            "tier": tier,
            "rejection_high": trigger.get("rejection_high"),
            "rejection_low": trigger.get("rejection_low"),
            "target_level": trigger.get("target_level"),
            "target_label": trigger.get("target_label"),
            "vol_ratio": trigger.get("vol_ratio"),
            "promotion_status": PROMOTION_STATUS,
        },
    )


__all__ = [
    "STRATEGY_NAME",
    "PROMOTION_STATUS",
    "detect_shotgun_scalper",
    "detect_shotgun_scalper_setup",
    "run_once",
    "log_observation",
]
