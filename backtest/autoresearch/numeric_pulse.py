"""numeric_pulse -- every-1-min pure-Python pattern detector pass.

Per markdown/specs/2-MIN-CADENCE-ARCHITECTURE.md Option 1: J asked for chart reads every
2 min instead of 6 min. Vision-LLM at 2-min would be over-budget; pure-Python
numeric detection is FREE and can fire every 1 min.

This script:
  1. Fetches the latest closed 5m SPY bar via yfinance (zero cost).
  2. Runs all 6 chart_patterns detectors + is_contra_trend filter against the
     trailing ~78 bars (one RTH day).
  3. Writes every fire (regardless of hits) to automation/state/numeric-pulse.jsonl
     for forensics + grading.
  4. If any high-conviction hit fires (confidence >= 0.65, contra-trend, close
     to a named level), writes to automation/state/numeric-alert.jsonl.
  5. Heartbeat's Step 2.5 (queued) will read the alert ledger.

Cost: $0 (pure Python, no LLM in loop).

CLI:
    python backtest/autoresearch/numeric_pulse.py
    python backtest/autoresearch/numeric_pulse.py --silent      # no stdout
    python backtest/autoresearch/numeric_pulse.py --probe-only  # don't write, just print
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# crypto.lib is a normal package; safe to import directly (avoids broken
# spec_from_file_location dataclass(slots=True) interaction).
from crypto.lib.chart_patterns import (  # noqa: E402
    Bar,
    PatternHit,
    disambiguate_by_regime,
    is_contra_trend,
    double_bottom_detector,
    double_top_detector,
    failed_breakdown_wick,
    rejection_at_level,
    momentum_acceleration,
    inside_bar_consolidation,
    head_and_shoulders_detector,
)


ET_TZ = timezone(timedelta(hours=-4))  # EDT in May/June; toggled by season elsewhere
MIN_CONF_HIGH = 0.65
LEVEL_PROXIMITY_DOLLARS = 0.50  # within $0.50 of a named ★+ level

# Event-driven heartbeat trigger (per markdown/specs/2-MIN-CADENCE-ARCHITECTURE.md)
HEARTBEAT_COOLDOWN_SEC = 60  # don't fire ad-hoc heartbeat more than 1x per 60s
TRIGGER_STATE_FILE = PROJECT_ROOT / "automation" / "state" / "alert-trigger-state.json"
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _is_rth_now() -> bool:
    """True iff current ET clock is in [09:30, 16:00) on a weekday."""
    now_et = datetime.now(ET_TZ)
    if now_et.weekday() >= 5:
        return False
    return dtime(9, 30) <= now_et.time() < dtime(16, 0)


def _fetch_today_bars() -> list[Bar]:
    """Pull today's 5m SPY RTH bars from yfinance. Returns empty list on failure."""
    try:
        import yfinance as yf
    except ImportError:
        return []

    try:
        df = yf.download("SPY", interval="5m", period="2d",
                         auto_adjust=False, progress=False, threads=False)
    except Exception:
        return []
    if df is None or df.empty:
        return []

    # Flatten MultiIndex if yfinance returns one (it does for single-ticker)
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

    bars: list[Bar] = []
    for ts, row in df.iterrows():
        # ts may be tz-aware UTC or naive depending on yfinance version
        if ts.tzinfo is None:
            ts_utc = ts.replace(tzinfo=timezone.utc)
        else:
            ts_utc = ts.astimezone(timezone.utc)
        et = ts_utc.astimezone(ET_TZ)
        # Only RTH bars
        if not (dtime(9, 30) <= et.time() < dtime(16, 0)):
            continue
        # Volume=0 sentinel for in-progress bar (yfinance pattern, L33)
        try:
            vol = float(row["Volume"])
        except (KeyError, TypeError):
            vol = 0.0
        if vol == 0.0:
            continue  # skip the live in-progress bar
        bars.append(Bar(
            open_time=ts_utc,
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            volume=vol,
            granularity_seconds=300,
            source="yfinance",
        ))
    return bars


def _load_key_levels() -> list[dict]:
    """Load today's key levels (if available) to score level proximity."""
    today = datetime.now(ET_TZ).date()
    paths = [
        PROJECT_ROOT / "automation" / "state" / "key-levels.json",
        PROJECT_ROOT / "automation" / "state" / f"key-levels-{today.isoformat()}.json",
    ]
    for p in paths:
        if p.exists():
            try:
                data = json.loads(p.read_text())
                if isinstance(data, dict) and "levels" in data:
                    return [lvl for lvl in data["levels"] if isinstance(lvl, dict)]
                if isinstance(data, list):
                    return [lvl for lvl in data if isinstance(lvl, dict)]
            except (json.JSONDecodeError, OSError):
                continue
    return []


def _level_proximity(price: float, levels: list[dict]) -> dict | None:
    """Find the nearest level within $LEVEL_PROXIMITY_DOLLARS."""
    best: tuple[float, dict] | None = None
    for lvl in levels:
        lvl_price = lvl.get("price") or lvl.get("level_price")
        if lvl_price is None:
            continue
        try:
            d = abs(float(lvl_price) - price)
        except (TypeError, ValueError):
            continue
        if d <= LEVEL_PROXIMITY_DOLLARS and (best is None or d < best[0]):
            best = (d, lvl)
    if best is None:
        return None
    return {"distance_dollars": round(best[0], 3), "level": best[1]}


def _trigger_heartbeat_if_alert(alerts: list[dict]) -> dict:
    """If we have a high-conviction alert AND cooldown has elapsed, fire an
    ad-hoc heartbeat tick (Safe + Bold). Cooldown prevents back-to-back fires.

    Per OP-25 ENGINE-BENEFIT AUTONOMY: this is wrapper-layer infrastructure
    (just spawns existing run-heartbeat.ps1) — it does NOT modify heartbeat.md
    trading doctrine. The heartbeat scores per its existing 11-filter rubric;
    extra invocations are just additional sample points within the same rules.

    Returns: dict with `fired` (bool), `reason`, `cooldown_remaining_sec`.
    """
    if not alerts:
        return {"fired": False, "reason": "no_alerts"}

    now = datetime.now(timezone.utc)
    state = {}
    if TRIGGER_STATE_FILE.exists():
        try:
            state = json.loads(TRIGGER_STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            state = {}

    last_fire_iso = state.get("last_fire_utc")
    if last_fire_iso:
        try:
            last_fire = datetime.fromisoformat(last_fire_iso)
            elapsed = (now - last_fire).total_seconds()
            if elapsed < HEARTBEAT_COOLDOWN_SEC:
                return {"fired": False, "reason": "cooldown",
                        "cooldown_remaining_sec": round(HEARTBEAT_COOLDOWN_SEC - elapsed, 1)}
        except ValueError:
            pass  # bad state, fire anyway

    # Find heartbeat wrappers
    safe_wrapper = PROJECT_ROOT / "setup" / "scripts" / "run-heartbeat.ps1"
    bold_wrapper = PROJECT_ROOT / "setup" / "scripts" / "run-heartbeat-aggressive.ps1"

    pythonw = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
    run_ps1_hidden = PROJECT_ROOT / "setup" / "scripts" / "run_ps1_hidden.py"

    fired_for = []
    if not pythonw.exists() or not run_ps1_hidden.exists():
        return {"fired": False, "reason": f"missing pythonw or run_ps1_hidden: {pythonw} {run_ps1_hidden}"}

    import subprocess
    for label, wrapper in (("safe", safe_wrapper), ("bold", bold_wrapper)):
        if not wrapper.exists():
            continue
        try:
            subprocess.Popen(
                [str(pythonw), str(run_ps1_hidden), str(wrapper)],
                creationflags=CREATE_NO_WINDOW,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            fired_for.append(label)
        except Exception as e:
            return {"fired": False, "reason": f"spawn failed for {label}: {e}"}

    # Persist state
    state["last_fire_utc"] = now.isoformat()
    state["last_fire_alerts"] = [{"pattern": a["pattern"], "bias": a["bias"],
                                   "key_price": a["key_price"]} for a in alerts[:5]]
    state["fired_for"] = fired_for
    TRIGGER_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRIGGER_STATE_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    return {"fired": True, "reason": "alert_with_cooldown_elapsed", "fired_for": fired_for}


def run_pulse(probe_only: bool = False) -> dict:
    """One numeric pulse pass."""
    fire_at = datetime.now(timezone.utc)
    in_rth = _is_rth_now()
    if not in_rth:
        return {"fire_at_utc": fire_at.isoformat(), "rth": False,
                "skipped": "outside_rth", "hits": [], "alerts": []}

    bars = _fetch_today_bars()
    if len(bars) < 20:
        return {"fire_at_utc": fire_at.isoformat(), "rth": True,
                "skipped": f"insufficient_bars({len(bars)})", "hits": [], "alerts": []}

    levels = _load_key_levels()
    bar_idx = len(bars) - 1
    latest_close = bars[-1].close

    detectors = (
        ("double_bottom", lambda bs: double_bottom_detector(bs, lookback=20)),
        ("double_top", lambda bs: double_top_detector(bs, lookback=20)),
        ("failed_breakdown_wick", lambda bs: failed_breakdown_wick(bs, lookback_for_support=10)),
        ("rejection_at_level_bearish", lambda bs: rejection_at_level(bs, lookback_for_resistance=10)),
        ("momentum_acceleration", lambda bs: momentum_acceleration(bs, lookback=10)),
        ("inside_bar_consolidation", lambda bs: inside_bar_consolidation(bs, min_consecutive_inside=2)),
        ("head_and_shoulders_top", lambda bs: head_and_shoulders_detector(bs, lookback=30)),
    )
    raw_hits: list[PatternHit] = []
    for det_name, det_fn in detectors:
        hit = det_fn(bars)
        if hit is None:
            continue
        if hit.bar_index != bar_idx:
            continue
        raw_hits.append(hit)

    # Disambiguate if conflicting
    winner = disambiguate_by_regime(raw_hits, bars, sma_lookback=20) if raw_hits else None

    hit_summaries = []
    alerts = []
    for h in raw_hits:
        ct = is_contra_trend(h, bars, sma_lookback=20)
        proximity = _level_proximity(h.key_price or latest_close, levels)
        info = {
            "pattern": h.pattern,
            "bias": h.bias,
            "confidence": h.confidence,
            "key_price": h.key_price,
            "contra_trend": ct,
            "level_proximate": proximity is not None,
            "level_distance": (proximity["distance_dollars"] if proximity else None),
            "level_name": (proximity["level"].get("name") if proximity else None),
        }
        hit_summaries.append(info)
        # ALERT criteria: high-conviction + contra-trend + level-proximate
        if h.confidence >= MIN_CONF_HIGH and ct is True and proximity is not None:
            alerts.append({
                "fire_at_utc": fire_at.isoformat(),
                "pattern": h.pattern,
                "bias": h.bias,
                "confidence": h.confidence,
                "key_price": h.key_price,
                "spy_close": latest_close,
                "level_distance_dollars": proximity["distance_dollars"],
                "level_name": proximity["level"].get("name"),
            })

    result = {
        "fire_at_utc": fire_at.isoformat(),
        "rth": True,
        "bar_count": len(bars),
        "latest_bar_time_utc": bars[-1].open_time.isoformat(),
        "latest_close": latest_close,
        "raw_hits_count": len(raw_hits),
        "hits": hit_summaries,
        "disambiguated_winner": (
            {"pattern": winner.pattern, "bias": winner.bias, "confidence": winner.confidence}
            if winner else None
        ),
        "alerts": alerts,
    }

    if probe_only:
        return result

    # Persist
    state_dir = PROJECT_ROOT / "automation" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    pulse_ledger = state_dir / "numeric-pulse.jsonl"
    alert_ledger = state_dir / "numeric-alert.jsonl"
    with pulse_ledger.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result, default=str) + "\n")
    if alerts:
        with alert_ledger.open("a", encoding="utf-8") as f:
            for a in alerts:
                f.write(json.dumps(a, default=str) + "\n")

    # Event-driven heartbeat trigger (cooldown-gated). Spawns ad-hoc heartbeat
    # tick if alerts present + cooldown elapsed. Heartbeat applies its own
    # rubric — this is just attention, not override.
    trigger_result = _trigger_heartbeat_if_alert(alerts)
    result["trigger"] = trigger_result

    # PARALLEL: pure-Python fast-path executor (OBSERVER MODE).
    # Per markdown/specs/2-MIN-CADENCE-ARCHITECTURE.md + J's <30s directive.
    # Runs in-process so we can share the VIX fetch (saves ~1.1s).
    # Decisions written to fast-path-decisions.jsonl. Does NOT place orders
    # until --mode live + sentinel file (J ratification).
    fast_path_result = _trigger_fast_path_if_alert(alerts, bars)
    result["fast_path"] = fast_path_result

    return result


def _trigger_fast_path_if_alert(alerts: list[dict], bars: list[Bar]) -> dict:
    """Invoke the pure-Python fast_path_executor for each fresh alert.

    Runs IN-PROCESS (not subprocess) so we can share VIX + bar caches.
    Returns summary dict for logging. NEVER places orders in observer mode.
    """
    if not alerts:
        return {"fired": False, "reason": "no_alerts"}

    # Import here to keep numeric_pulse startup-fast on no-alert ticks
    try:
        import importlib.util as _il
        import sys as _sys
        spec = _il.spec_from_file_location(
            "fpe_inproc",
            PROJECT_ROOT / "setup" / "scripts" / "fast_path_executor.py",
        )
        fpe = _il.module_from_spec(spec)
        _sys.modules["fpe_inproc"] = fpe
        spec.loader.exec_module(fpe)
    except Exception as e:
        return {"fired": False, "reason": f"fpe import failed: {e}"}

    # Pre-fetch VIX once (saves 1.1s vs each account fetching its own)
    started = time.monotonic()
    vix_data = fpe._fetch_vix_quick()
    vix_ms = int((time.monotonic() - started) * 1000)

    # Evaluate latest alert against both accounts
    latest = alerts[-1]  # most recent
    decisions = []
    for acct in ("safe", "bold"):
        try:
            d = fpe.evaluate_alert(acct, latest, vix_data=vix_data)
            fpe._persist_decision(d)
            decisions.append({
                "account": acct,
                "decision": d.decision,
                "reason": d.reason,
                "elapsed_ms": d.elapsed_ms,
                "strike": d.proposed_strike,
                "qty": d.proposed_qty,
            })
        except Exception as e:
            decisions.append({"account": acct, "error": str(e)})

    return {
        "fired": True,
        "vix_fetch_ms": vix_ms,
        "decisions": decisions,
    }


def main() -> int:
    import time as _time
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--probe-only", action="store_true", help="Don't persist; just print")
    parser.add_argument("--cycles", type=int, default=2,
                        help="How many pulses per invocation (default 2 = 30s cadence with cron every 1m)")
    parser.add_argument("--interval-sec", type=int, default=30,
                        help="Seconds between cycles within one invocation (default 30)")
    args = parser.parse_args()

    last_result: dict | None = None
    for cycle_n in range(max(1, args.cycles)):
        if cycle_n > 0:
            _time.sleep(args.interval_sec)
        # Check market still open before continuing the loop
        if cycle_n > 0 and not _is_rth_now():
            break
        result = run_pulse(probe_only=args.probe_only)
        last_result = result

        if not args.silent:
            tag = f"[{cycle_n + 1}/{args.cycles}]"
            if result.get("skipped"):
                print(f"PULSE {tag} skipped: {result['skipped']}")
            else:
                print(f"PULSE {tag} @ {result['fire_at_utc']}  bars={result['bar_count']}  "
                      f"close={result['latest_close']}  hits={result['raw_hits_count']}  "
                      f"alerts={len(result['alerts'])}")
                for h in result["hits"]:
                    print(f"    {h['pattern']:35s} {h['bias']:7s} conf={h['confidence']}  "
                          f"contra={h['contra_trend']}  lvl={h['level_name']}")
                for a in result["alerts"]:
                    print(f"    !! ALERT {a['pattern']} @ ${a['spy_close']:.2f} "
                          f"vs level {a['level_name']} (${a['level_distance_dollars']:.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
