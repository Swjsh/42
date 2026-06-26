"""chart_read -- the Chart Master's one-shot structured chart read.

Fuses the three TA layers a human reads in the first two seconds, into ONE
structured object + a plain-English line in J's language:

    1. MARKET STRUCTURE  (crypto.lib.market_structure) -- trend from swings,
       HH/HL/LH/LL sequence, BOS / CHoCH.  (The layer the engine was missing.)
    2. CHART PATTERNS    (crypto.lib.chart_patterns)   -- double bottom/top, H&S,
       rejection/failed-break, momentum, inside-bar.
    3. LEVEL PROXIMITY   (automation/state/key-levels.json) -- nearest named level.

CONNECTIVITY / "NO WRITING TO THIN AIR" GUARD (mandate constraint #2):
    NEVER computes a confident read on an empty/stale feed. Missing/empty/degraded
    bars -> flag automation/overnight/STATUS.md "Known broken" + exit non-zero.
    The guard is HARDENED: time parsing, row building, and the whole analysis are
    wrapped so a malformed feed (e.g. epoch-ms timestamps) FAILS LOUD instead of
    crashing past the guard with a bare traceback.

Inputs:
    --bars-json PATH   LIVE: bars pulled from the TradingView MCP (data_get_ohlcv).
                       JSON list of {time/timestamp, open, high, low, close, volume}
                       or {"bars":[...]}. Pass --drop-last-bar to discard the
                       in-progress bar in-module (don't hand-filter in prose).
    --csv PATH --date  BACKTEST/GYM: a SPY 5m CSV (timestamp_et,open,...,volume).

Pure Python, $0, no LLM, no orders. Reads only; writes one analysis JSON.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from crypto.lib import chart_patterns as cp
from crypto.lib.bar import Bar
from crypto.lib.confluence import compute_confluence
from crypto.lib.market_structure import analyze_structure, signal_tier

_PATTERN_DETECTORS = (
    "double_bottom_detector",
    "double_top_detector",
    "head_and_shoulders_detector",
    "failed_breakdown_wick",
    "rejection_at_level",
    "momentum_acceleration",
    "inside_bar_consolidation",
)

MIN_BARS_FOR_STRUCTURE = 10
_HIGH_DROP_RATIO = 0.25  # >25% of rows unusable -> flag the feed as suspect


def _et_date(dt: datetime) -> str:
    """ISO date in US/Eastern (SPY's session calendar). Falls back to the dt's own
    tz if zoneinfo/tzdata is unavailable, never to a wrong-by-a-day UTC roll."""
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    except Exception:
        return dt.date().isoformat()


def _flag_broken(status_path: Path, msg: str) -> None:
    """Append a RED line to STATUS.md 'Known broken' -- fail loud, but IDEMPOTENT:
    if an identical message already sits in the section, refresh its timestamp
    instead of spamming a new line every run on a persistently-dark feed."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    new_line = f"- [chart-read] {ts} RED: {msg}"
    try:
        anchor = "## Known broken"
        if status_path.exists():
            text = status_path.read_text(encoding="utf-8")
            # dedupe: drop any prior chart-read line with the same msg body
            kept = [ln for ln in text.splitlines()
                    if not (ln.startswith("- [chart-read]") and ln.rstrip().endswith(f"RED: {msg}"))]
            text = "\n".join(kept)
            if anchor in text:
                idx = text.index(anchor) + len(anchor)
                text = text[:idx] + "\n" + new_line + text[idx:] if not text[idx:].startswith("\n") \
                    else text[:idx] + "\n" + new_line + text[idx:]
            else:
                text = text.rstrip() + f"\n\n{anchor}\n{new_line}\n"
            status_path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        else:
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(f"{anchor}\n{new_line}\n", encoding="utf-8")
    except Exception as e:  # the flag itself must never crash the guard
        print(f"  (could not write STATUS flag: {e})", file=sys.stderr)


def _parse_time(raw) -> datetime:
    """Parse epoch (s/ms/us) or ISO string to tz-aware UTC. Raises on unparseable."""
    if isinstance(raw, bool):
        raise ValueError("bool is not a timestamp")
    if isinstance(raw, (int, float)):
        v = float(raw)
        while abs(v) > 1e11:  # epoch ms -> s, then us -> s if still huge
            v /= 1000.0
        return datetime.fromtimestamp(v, tz=timezone.utc)
    if isinstance(raw, str) and raw.strip():
        dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    raise ValueError(f"unparseable time: {raw!r}")


def _to_bars(rows: list[dict], tf_seconds: int, source: str) -> tuple[list[Bar], int]:
    """Build Bars; returns (bars, dropped_count). Bad time -> anchor to prior bar
    + tf (never epoch-0). Malformed OHLC -> dropped (counted, not silent)."""
    bars: list[Bar] = []
    dropped = 0
    last_t: datetime | None = None
    for r in rows:
        traw = r.get("time", r.get("timestamp", r.get("timestamp_et", r.get("datetime"))))
        try:
            o, h, l, c = float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])
        except (KeyError, TypeError, ValueError):
            dropped += 1
            continue
        v = float(r.get("volume", 0) or 0)
        if h < l:
            h, l = l, h
        try:
            t = _parse_time(traw)
        except Exception:
            t = (last_t + timedelta(seconds=tf_seconds)) if last_t else datetime.now(timezone.utc)
        last_t = t
        try:
            bars.append(Bar(open_time=t, open=o, high=h, low=l, close=c, volume=v,
                            granularity_seconds=tf_seconds, source=source))
        except Exception:
            dropped += 1
    # enforce chronology + de-dup timestamps (concatenated MCP pulls can be out of order)
    bars.sort(key=lambda b: b.open_time)
    deduped: list[Bar] = []
    seen: set[datetime] = set()
    for b in bars:
        if b.open_time in seen:
            dropped += 1
            continue
        seen.add(b.open_time)
        deduped.append(b)
    return deduped, dropped


def _load_csv_date(csv_path: Path, date_str: str) -> list[dict]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        return [row for row in csv.DictReader(f) if row.get("timestamp_et", "").startswith(date_str)]


def scan_csv_range(csv_path: Path, start_date: str, end_date: str, window: int = 2) -> dict:
    """Audit market-structure across REAL SPY history (the coverage the detector
    lacked -- it had only BTC + fixtures). Reports trend distribution, BOS/CHoCH
    density, and crashes over a date range. Permanent, re-runnable SPY coverage.
    """
    import collections
    by_date: dict[str, list[dict]] = collections.defaultdict(list)
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d = row.get("timestamp_et", "")[:10]
            if start_date <= d <= end_date:
                by_date[d].append(row)
    dist: collections.Counter = collections.Counter()
    crashes = 0
    events = 0
    days = 0
    for d in sorted(by_date):
        bars, _ = _to_bars(by_date[d], 300, "csv")
        if not bars:
            continue
        days += 1
        try:
            r = analyze_structure(bars, window=window)
            dist[r.trend] += 1
            events += r.notes["n_events"]
        except Exception:
            crashes += 1
    return {
        "days": days,
        "trend_distribution": dict(dist),
        "total_events": events,
        "events_per_day": round(events / days, 1) if days else 0,
        "indecisive_days": dist.get("unknown", 0) + dist.get("range", 0),
        "crashes": crashes,
        "window": window,
    }


def _hit_to_dict(hit) -> dict:
    return {
        "pattern": hit.pattern,
        "bias": hit.bias,
        "confidence": round(hit.confidence, 3),
        "key_price": round(hit.key_price, 2),
        "bar_index": hit.bar_index,
    }


def _scan_patterns(bars: list[Bar]) -> tuple[list[dict], list[str]]:
    hits: list[dict] = []
    errors: list[str] = []
    for name in _PATTERN_DETECTORS:
        fn = getattr(cp, name, None)
        if fn is None:
            errors.append(f"{name}: missing")
            continue
        try:
            hit = fn(bars)
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}")
            continue
        if hit is not None:
            hits.append(_hit_to_dict(hit))
    return hits, errors


def _load_levels(key_levels_path: Path | None) -> list | None:
    if not key_levels_path:
        return None
    try:
        data = json.loads(key_levels_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data.get("levels", data) if isinstance(data, dict) else data


def _nearest_level(levels: list | None, price: float) -> dict | None:
    if not isinstance(levels, list):
        return None
    best = None
    for lv in levels:
        try:
            lp = float(lv.get("price"))
        except (TypeError, ValueError, AttributeError):
            continue
        dist = abs(lp - price)
        if best is None or dist < best["distance"]:
            best = {
                "name": lv.get("name") or lv.get("label") or lv.get("type", "level"),
                "price": round(lp, 2),
                "tier": lv.get("tier"),
                "distance": round(dist, 2),
                "side": "above" if lp > price else "below",
            }
    return best


def _summary_line(read: dict) -> str:
    parts = [f"{read['symbol']} {read['trend'].upper()}"]
    seq = read.get("recent_label_sequence") or []
    if seq:
        parts.append("(" + " ".join(seq[-4:]) + ")")
    ev = read.get("last_event")
    if ev:
        ago = read.get("last_event_bars_ago")
        ago_s = f" {ago}b ago" if ago is not None else ""
        parts.append(f"last event {ev['direction']} {ev['kind']} @ {ev['broken_price']}{ago_s}")
    pats = read.get("patterns") or []
    if pats:
        top = max(pats, key=lambda p: p["confidence"])
        parts.append(f"pattern {top['pattern']} ({top['bias']}, conf {top['confidence']})")
    nl = read.get("nearest_level")
    if nl:
        parts.append(f"nearest {nl['name']} {nl['price']} ({nl['distance']} {nl['side']})")
    return " | ".join(parts)


def build_read(bars: list[Bar], *, symbol: str, mode: str, key_levels_path: Path | None,
               window: int, dropped_rows: int = 0, session_date_override: str | None = None) -> dict:
    ms = analyze_structure(bars, window=window)
    last = bars[-1]
    ev = ms.last_event
    patterns, pattern_errors = _scan_patterns(bars)
    levels = _load_levels(key_levels_path)
    read = {
        "symbol": symbol,
        "mode": mode,
        "asof_utc": last.close_time.isoformat(),
        "session_date_et": session_date_override or _et_date(last.close_time),
        "n_bars": len(bars),
        "dropped_rows": dropped_rows,
        "last_close": round(last.close, 2),
        "trend": ms.trend,
        "trend_basis": ms.trend_basis,
        "recent_label_sequence": ms.notes.get("recent_label_sequence", []),
        "last_swing_high": round(ms.last_swing_high, 2) if ms.last_swing_high is not None else None,
        "last_swing_low": round(ms.last_swing_low, 2) if ms.last_swing_low is not None else None,
        "last_event": ({
            "kind": ev.kind, "direction": ev.direction, "broken_price": round(ev.broken_price, 2),
        } if ev else None),
        "last_event_bars_ago": ms.notes.get("last_event_bars_ago"),
        "bars_since_last_swing": ms.notes.get("bars_since_last_swing"),
        "structure_confidence": ms.confidence,
        "structure_confidence_tier": signal_tier(ms.confidence),
        "patterns": patterns,
        "pattern_errors": pattern_errors,
        "nearest_level": _nearest_level(levels, last.close),
        "low_data": len(bars) < MIN_BARS_FOR_STRUCTURE,
    }
    # the confluence synthesis -- the "wizard read" (awareness, not a trigger)
    conf = compute_confluence(bars, levels=levels, window=window)
    read["confluence"] = {
        "bias": conf.bias,
        "conviction": conf.conviction,
        "confirming": list(conf.confirming),
        "conflicting": list(conf.conflicting),
        "invalidation": conf.invalidation,
        "scenario": conf.scenario,
    }
    read["structure_summary"] = _summary_line(read)
    read["summary"] = conf.scenario
    return read


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["morning", "intraday", "backtest"], default="intraday")
    p.add_argument("--bars-json", type=Path, default=None, help="LIVE bars from TV MCP")
    p.add_argument("--csv", type=Path, default=None, help="SPY 5m CSV (backtest/gym)")
    p.add_argument("--date", default=None, help="YYYY-MM-DD (with --csv)")
    p.add_argument("--symbol", default="SPY")
    p.add_argument("--tf-seconds", type=int, default=300)
    p.add_argument("--window", type=int, default=2, help="swing strictness (2=5m default)")
    p.add_argument("--drop-last-bar", action="store_true",
                   help="discard the final (in-progress) bar -- closed-bar discipline, in-module")
    p.add_argument("--key-levels", type=Path, default=_REPO_ROOT / "automation/state/key-levels.json")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--status", type=Path, default=_REPO_ROOT / "automation/overnight/STATUS.md")
    p.add_argument("--print-only", action="store_true")
    p.add_argument("--scan", action="store_true", help="audit structure across a SPY date range")
    p.add_argument("--scan-end", default=None, help="end date for --scan (with --csv + --date as start)")
    args = p.parse_args(argv)

    # ---- SPY-history audit mode ----
    if args.scan:
        if not (args.csv and args.date and args.scan_end):
            print("ERROR: --scan needs --csv, --date (start), --scan-end", file=sys.stderr)
            return 2
        rep = scan_csv_range(args.csv, args.date, args.scan_end, window=args.window)
        print(json.dumps(rep, indent=2))
        return 0 if rep["crashes"] == 0 else 2

    # ---- load rows ----
    rows: list[dict] = []
    if args.bars_json:
        try:
            raw = json.loads(args.bars_json.read_text(encoding="utf-8"))
            rows = raw.get("bars", raw) if isinstance(raw, dict) else raw
        except Exception as e:
            _flag_broken(args.status, f"bars-json unreadable: {e}")
            print(f"RED: bars-json unreadable ({e}) -- flagged, no read written.")
            return 2
    elif args.csv and args.date:
        if not args.csv.exists():
            _flag_broken(args.status, f"csv not found: {args.csv}")
            print(f"RED: csv not found {args.csv}")
            return 2
        rows = _load_csv_date(args.csv, args.date)
        if not rows:
            print(f"RED: no rows for {args.date} in {args.csv.name} (wrong date or column?) -- no read.")
            return 2
    else:
        print("ERROR: provide --bars-json OR (--csv AND --date)", file=sys.stderr)
        return 2

    source = "tv" if args.bars_json else "csv"
    bars, dropped = _to_bars(rows, args.tf_seconds, source)
    if args.drop_last_bar and bars:
        bars = bars[:-1]

    # ---- THIN-AIR GUARD ----
    if not bars:
        _flag_broken(args.status, f"{args.symbol} {args.mode}: 0 usable bars (feed dark/empty)")
        print(f"RED: 0 usable bars for {args.symbol} {args.mode} -- flagged STATUS, no read written.")
        return 2
    if rows and dropped / max(len(rows), 1) > _HIGH_DROP_RATIO:
        _flag_broken(args.status, f"{args.symbol} {args.mode}: {dropped}/{len(rows)} rows unusable (feed suspect)")

    # ---- analyze (hardened: any failure here fails LOUD, not a bare traceback) ----
    try:
        kl_path = None if args.mode == "backtest" else args.key_levels
        read = build_read(bars, symbol=args.symbol, mode=args.mode, key_levels_path=kl_path,
                          window=args.window, dropped_rows=dropped,
                          session_date_override=args.date if source == "csv" else None)
    except Exception as e:
        _flag_broken(args.status, f"{args.symbol} {args.mode}: analysis crashed: {type(e).__name__}: {e}")
        print(f"RED: analysis crashed ({type(e).__name__}) -- flagged STATUS, no read written.")
        return 2

    if read["low_data"]:
        _flag_broken(args.status, f"{args.symbol} {args.mode}: only {len(bars)} bars "
                     f"(< {MIN_BARS_FOR_STRUCTURE}) -- structure read degraded")

    # ---- output ----
    print(read["summary"])
    if not args.print_only:
        out = args.out or (_REPO_ROOT / f"analysis/chart-read-{read['session_date_et']}.json")
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(read, indent=2, default=str), encoding="utf-8")
            print(f"  -> {out.relative_to(_REPO_ROOT)}")
        except Exception as e:
            _flag_broken(args.status, f"cannot write read to {out}: {e}")
            print(f"RED: cannot write read ({e}) -- flagged STATUS.")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
