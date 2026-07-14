"""level_memory_producer.py — write multi-day MEMORY levels to a SHADOW key (V1, 2026-07-08).

The live engine had NO multi-day level memory (verified 2026-07-08: key-levels.json = today's
intraday + curated levels only). J reads multi-day structure naturally ("bounced off 739.50 like
last Thursday"; "rejected the bottom of those 746 candles"). This runs the existing memory engine
(backtest/lib/watchers/level_memory.py) over recent SPY 5m history and writes the memory-weighted
levels (touches + role-flips + candle-bottom CLUSTERS) to automation/state/key-levels-memory.json
— a SHADOW feed the engine / dashboard / self-check can SEE and G5's emit_reject_alert can ping on
— WITHOUT changing what the live engine trades. Roles are STRUCTURAL (level_memory's own
support/resistance from pivot type), deduped by price -> no contradictory-role bug.

The entry-wire (merging these into the live key-levels.json that filter-10 trades off) is A/B-gated
and NEEDS-REVIEW — this producer is the safe, visible half. Read-only market data; no orders.

Run: python setup/scripts/level_memory_producer.py   (schedulable every N min).
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, 2026-07-14 popup-storm fix) =====
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# can allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout
# write. Redirect stdio to log files BEFORE any other import gets a chance to write.
# Root-caused live 2026-07-14 (J: "stop the fkin popus on my screen") via the
# re-armed window-leak-detector.py: this exact script, launched wscript->
# run_exe_hidden.vbs->backtest-venv-pythonw with NO relay layer, was caught flashing
# a WindowsTerminal window on a real Start-ScheduledTask fire within 45s.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "level-memory-producer.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "level-memory-producer.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
from lib.watchers import level_memory as LM  # noqa: E402

SHADOW = REPO / "automation" / "state" / "key-levels-memory.json"
MIN_MEMORY = 20.0       # only well-tested levels (raised from 3: 3 gave 43 levels = S/R everywhere)
STRONG_MEMORY = 60.0    # >= this => tier "Active" (else "Reference")
LOOKBACK_DAYS = 10      # multi-day memory horizon
DEDUP_EPS = 0.60        # collapse levels within $0.60 into ONE zone (J reads zones, not pivots)
TOP_N = 12              # cap the map at the strongest N zones (readable; not a wall of levels)

# V1c reject-alert: ping J when the latest bar REJECTS a strong memory level (like 746.7).
OUTBOX = REPO / "automation" / "state" / "discord-outbox.jsonl"
PING_STATE = REPO / "automation" / "state" / "level-memory-ping-state.json"
PING_MIN_MEMORY = 40.0  # only ping STRONG levels (the 746.7 zone is 151) -- not every pivot
PING_DEDUP_MIN = 30     # don't re-ping the same level within 30 min (no spam)


def _load_spy() -> "pd.DataFrame | None":
    """Recent SPY 5m OHLCV as timestamp_et/open/high/low/close/volume. yfinance (off the hot
    path); None on failure so the producer fails open (writes nothing rather than garbage)."""
    try:
        import yfinance as yf
        d = yf.download("SPY", period="1mo", interval="5m", progress=False)
    except Exception:
        return None
    if d is None or not len(d):
        return None
    d = d.reset_index()
    tcol = d.columns[0]

    def col(name):
        v = d[name]
        return v.values.ravel() if hasattr(v, "values") else v

    try:
        return pd.DataFrame({
            "timestamp_et": pd.to_datetime(d[tcol]),
            "open": col("Open"), "high": col("High"), "low": col("Low"),
            "close": col("Close"), "volume": col("Volume"),
        })
    except Exception:
        return None


def select_levels(raw) -> list[dict]:
    """PURE: filter (>= MIN_MEMORY) + dedup-into-zones (DEDUP_EPS, strongest wins) + cap (TOP_N)
    + map to the key-levels schema. Broker/network-free -> unit-testable on synthetic Levels.
    Each output carries ONE structural role per price (level_memory's own support/resistance),
    so no contradictory-role bug can arise (one polarity per price, deduped)."""
    keep = [lv for lv in raw if lv.memory_score >= MIN_MEMORY]
    keep.sort(key=lambda lv: -lv.memory_score)     # strongest first, so the zone winner is strongest
    out: list[dict] = []
    for lv in keep:
        if any(abs(lv.price - o["price"]) <= DEDUP_EPS for o in out):
            continue  # a stronger already-kept level owns this price zone
        out.append({
            "price": round(float(lv.price), 2),
            "type": lv.role, "role": lv.role,
            "label": f"MEMORY_{lv.role[:3].upper()}_{lv.memory_score:.0f}",
            "memory_score": round(float(lv.memory_score), 2),
            "touches": int(lv.touches), "role_flips": int(lv.role_flips),
            "tier": "Active" if lv.memory_score >= STRONG_MEMORY else "Reference",
            "source": "level_memory",
        })
    out = out[:TOP_N]                              # cap (readable map, not a wall of levels)
    out.sort(key=lambda o: -o["price"])            # price-ordered for display/consumers
    return out


def apply_role_flip(
    levels: list[dict],
    raw,
    df: pd.DataFrame,
    up_to_idx: int,
    *,
    sustain_bars: int = LM.ROLE_FLIP_SUSTAIN_BARS,
    memory_threshold: float = LM.ROLE_FLIP_MEMORY_THRESHOLD,
) -> list[dict]:
    """PURE (T7, 2026-07-09): tag each selected level with sustained-role-flip confirmation
    (see backtest/lib/watchers/level_memory.py::detect_role_flip for the gate + why). Adds
    `flipped_at` (ISO ET string, or None) + `provenance` (str, or None) to every dict; overrides
    `role`/`type` to the level's PRIOR role if its most recent causal flip hasn't sustained for
    `sustain_bars` bars yet (so a single-bar whipsaw never reaches the shadow file as a "flip").
    Matches raw Level objects to selected dicts by rounded price (same key select_levels uses).
    SHADOW-ONLY -- this list feeds key-levels-memory.json ONLY, never key-levels.json."""
    by_price = {round(float(lv.price), 2): lv for lv in raw}
    out: list[dict] = []
    for d in levels:
        lv = by_price.get(d["price"])
        if lv is None:  # shouldn't happen (dict prices come from raw) but fail safe, not blind
            out.append({**d, "flipped_at": None, "provenance": None})
            continue
        role, flipped_at, provenance = LM.detect_role_flip(
            lv, df, up_to_idx, sustain_bars=sustain_bars, memory_threshold=memory_threshold,
        )
        nd = dict(d)
        nd["role"] = role
        nd["type"] = role
        if role != d["role"]:  # keep the human-readable label in sync with the corrected role
            nd["label"] = f"MEMORY_{role[:3].upper()}_{d['memory_score']:.0f}"
        nd["flipped_at"] = flipped_at
        nd["provenance"] = provenance
        out.append(nd)
    return out


def build_levels(df: pd.DataFrame) -> list[dict]:
    """Memory levels at the latest bar (causal): select_levels() then apply_role_flip() (T7)."""
    lm = LM.LevelMemory(df)
    up_to = len(lm.df) - 1
    raw = lm.levels_at(up_to, lookback_days=LOOKBACK_DAYS)
    return apply_role_flip(select_levels(raw), raw, lm.df, up_to)


# --- V2 gap-fill: prior RTH close (the gap-fill magnet) + gap status ------------------------
PRIOR_CLOSE_FILE = REPO / "automation" / "state" / "prior-rth-close.json"


def prior_rth_close(df: pd.DataFrame) -> "float | None":
    """PURE: the prior trading day's last RTH (<=16:00 ET) close from timestamped 5m bars.
    This is the value gap_and_go needs (today-bias.json stopped carrying it -> gap_and_go was
    100% SKIP_NO_FEED, F22/F25) AND the gap-fill magnet ('gaps always get filled'). None if the
    frame lacks a prior day. Testable without a network."""
    try:
        d = df.copy()
        d["timestamp_et"] = pd.to_datetime(d["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
        d["_date"] = d["timestamp_et"].dt.date
        d["_t"] = d["timestamp_et"].dt.strftime("%H:%M")
        today = d["_date"].iloc[-1]
        prior_days = sorted(set(x for x in d["_date"] if x < today))
        if not prior_days:
            return None
        pday = prior_days[-1]
        rth = d[(d["_date"] == pday) & (d["_t"] <= "16:00")]
        if rth.empty:
            return None
        return round(float(rth["close"].iloc[-1]), 2)
    except Exception:
        return None


def dedup_ok(state: dict, key: str, now: dt.datetime, dedup_min: int = PING_DEDUP_MIN) -> bool:
    """PURE: True if this level hasn't been pinged within dedup_min minutes. Testable."""
    last = state.get(key)
    if not last:
        return True
    try:
        return (now - dt.datetime.fromisoformat(last)).total_seconds() >= dedup_min * 60
    except (TypeError, ValueError):
        return True


def _ping_rejection(lm, last_idx: int) -> "str | None":
    """If the latest bar REJECTED a strong memory level (>= PING_MIN_MEMORY) and it wasn't pinged
    within PING_DEDUP_MIN, queue a Discord ping (delivered `content` schema). Notify-only,
    fail-open -- never raises into the producer. Returns the pinged message or None."""
    try:
        snap = lm.snapshot(last_idx, lookback_days=LOOKBACK_DAYS)
        msg = LM.format_reject_alert(snap, min_memory=PING_MIN_MEMORY)
        if not msg:
            return None
        now = dt.datetime.now(dt.timezone.utc)
        state = {}
        if PING_STATE.exists():
            try:
                state = json.loads(PING_STATE.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                state = {}
        key = f"{round(float(snap.interaction.level.price), 2)}"
        if not dedup_ok(state, key, now):
            return None  # pinged recently, skip (no spam)
        row = {"content": f"[LEVEL-MEMORY] {msg}", "source": "level_memory_producer",
               "queued_at": now.isoformat()}
        with OUTBOX.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        state[key] = now.isoformat()
        PING_STATE.write_text(json.dumps(state), encoding="utf-8")
        return msg
    except Exception:  # noqa: BLE001 -- the ping must never break the producer
        return None


def main() -> int:
    df = _load_spy()
    if df is None or len(df) < 50:
        print("[level_memory_producer] SPY load failed -> wrote nothing (fail-open)")
        return 0
    lm = LM.LevelMemory(df)
    last = len(lm.df) - 1
    raw_levels = lm.levels_at(last, lookback_days=LOOKBACK_DAYS)
    levels = apply_role_flip(select_levels(raw_levels), raw_levels, lm.df, last)  # T7
    spot = round(float(df["close"].iloc[-1]), 2)
    # V2 gap-fill: write the prior RTH close (gap-fill magnet) so gap_and_go stops SKIP_NO_FEED.
    pc = prior_rth_close(df)
    if pc is not None:
        gap = round(spot - pc, 2)
        PRIOR_CLOSE_FILE.write_text(json.dumps({
            "date": str(pd.Timestamp.now(tz="America/New_York").date()),
            "prior_rth_close": pc, "spot": spot, "gap_pts": gap,
            "gap_direction": ("up" if gap > 0 else "down" if gap < 0 else "flat"),
            "note": ("prior RTH close = gap-fill magnet (gaps get filled). Consumed by "
                     "setup_dispatch._get_prior_rth_close (V2 F22/F25 fix).")}, indent=2),
            encoding="utf-8")
    payload = {"generated_at_et": str(pd.Timestamp.now(tz="America/New_York").replace(microsecond=0)),
               "spot": spot, "lookback_days": LOOKBACK_DAYS, "min_memory": MIN_MEMORY,
               "count": len(levels), "levels": levels,
               "note": ("SHADOW multi-day memory levels (V1 + T7 sustained-role-flip tagging "
                        "2026-07-09). NOT yet fed to entries (A/B/NEEDS-REVIEW).")}
    SHADOW.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[level_memory_producer] spot {spot} -> {len(levels)} memory levels (>= {MIN_MEMORY}):")
    for lv in levels:
        flip_tag = f"  FLIPPED@{lv['flipped_at']}" if lv.get("flipped_at") else ""
        print(f"   {lv['price']:8.2f}  {lv['role']:10s}  mem {lv['memory_score']:5.1f}  "
              f"touches {lv['touches']}  flips {lv['role_flips']}  [{lv['tier']}]{flip_tag}")
    pinged = _ping_rejection(lm, last)   # V1c: ping J on a strong-memory-level rejection
    if pinged:
        print(f"[level_memory_producer] >>> PINGED J (memory-level rejection): {pinged}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
