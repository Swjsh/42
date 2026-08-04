"""violin_metric.py — THE VIOLIN TEST: how much of what the tape respected did the engine
actually have in its hand at that moment?

J's week directive (2026-08-03, verbatim): "playing these key levels like a violin". The
honest version of that claim is a NUMBER, measured the same way every night:

    coverage = respected levels the engine had ACTIVE at the moment of the touch
               / all levels the tape respected that session          (per source family)

plus the LATENCY (minutes from the tape first respecting a level to that level first
appearing in the engine's levels_active). Today's known case: 749.33 (final premarket low)
respected 09:25-09:29, in levels_active 09:44:03 — 15 minutes late (root cause: the
delayed-SIP frame, fixed same night via the IEX tail in refresh_levels_intraday.py; this
metric exists so that class of gap TRENDS instead of being rediscovered by embarrassment).

MEASUREMENT DEFINITION v1-2026-08-03 (FROZEN — a metric that moves its own goalposts
cannot trend; changes bump defn_version and START A NEW HISTORY SEGMENT):
  * Tape: SIP 5m bars 04:00-16:00 ET for the session (pulled after-hours, so the plan
    tier's 15-min SIP recency delay is irrelevant here).
  * Level universe, per source family — derived EX-POST and INDEPENDENT of the engine
    wherever the tape alone defines the level (else coverage would be trivially high):
      - premarket_high / premarket_low: final extremes of the 04:00-09:29 bars.
      - prior_day_high / prior_day_low / prior_day_close: D-1 RTH (09:30-15:55) extremes.
      - intraday_rth_high / intraday_rth_low: the RUNNING prior extreme at each RTH bar.
      - intraday_swing_high / intraday_swing_low: 3-bar pivots (the refresher's own
        _swing_levels shape), active once CONFIRMED (pivot bar +1).
      - file layers (daily_context_shelf / level_memory / curated): taken from the day's
        key-levels-history snapshots (these need multi-week state no tape replay owns —
        for them the metric measures presence-at-touch, not independent discovery).
    Universe entries within $0.10 collapse, tape-derived source wins (no double count).
  * RESPECT episode (support): bar.low <= L + TOL and bar.close > L, and within the next
    REACT_BARS bars max(high) >= L + REACT.   (resistance = mirror)
    TOL = $0.15 (the ratified ZONE_WIDTH_MIN floor), REACT = $0.50, REACT_BARS = 2.
    Episodes at the same level+side within DEDUP_BARS(=3) bars collapse to one.
  * COVERED: some levels_active price within MATCH_EPS ($0.10 = ROLE_EPSILON) of L on the
    last engine tick at-or-before the episode bar's close. Premarket episodes (the engine
    does not tick before 09:30) are COVERED iff the level is active by 09:36 ET — the
    window-open moment the 09:35 entry gate makes actionable.
  * LATENCY (min): episode bar close -> first engine tick whose levels_active matches L.
    Covered-in-advance = 0. Never matched = MISS (latency null, counted uncovered).
  * Trendlines are SLOPED — a static-price coverage test would be dishonest; they are
    reported as a separate visibility line from the engine's own watch surface, never in
    the coverage denominator.

OUTPUTS
  * automation/state/violin-metric.json          — latest run, all sessions computed.
  * analysis/violin/violin-history.jsonl         — one row per session, upserted by date
    (re-runs replace, never duplicate), the TREND surface.
  * stdout table (goes to the task log).

Nightly: Gamma_ViolinMetric 17:35 ET weekdays -> `violin_metric.py --last 1 --write`.
$0, pure read + REST bars, no LLM, no orders, fail-open, always exits 0 under --nightly.
Guard: backtest/tests/test_violin_metric_2026_08_03.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1].parent
STATE = REPO / "automation" / "state"
SNAP_DIR = STATE / "key-levels-history"
LEDGER = STATE / "core-decisions.jsonl"
ARCHIVE_DIR = REPO / "automation" / "archive" / "ledgers"
OUT_LATEST = STATE / "violin-metric.json"
HISTORY = REPO / "analysis" / "violin" / "violin-history.jsonl"
TRENDLINE_WATCH = STATE / "trendline-watch.json"

sys.path.insert(0, str(REPO / "setup" / "scripts"))
from et_clock import et_now  # noqa: E402

# pythonw stdio redirect (C8/L41 pattern, mirrors premarket_readiness.py) — a scheduled
# pythonw spawn has no console; without this the nightly violin table would vanish (C7).
import os as _os  # noqa: E402
if sys.platform == "win32" and _os.path.basename(sys.executable).lower() == "pythonw.exe":
    _logs = STATE / "logs"
    _logs.mkdir(parents=True, exist_ok=True)
    _stamp = et_now().strftime("%Y-%m-%d")
    sys.stdout = open(_logs / f"violin-metric-{_stamp}.stdout.log", "a", buffering=1, encoding="utf-8")
    sys.stderr = open(_logs / f"violin-metric-{_stamp}.stderr.log", "a", buffering=1, encoding="utf-8")

DEFN_VERSION = "v1-2026-08-03"
TOL = 0.15          # ZONE_WIDTH_MIN — the ratified zone floor (J doctrine: levels are zones)
REACT = 0.50        # $ move away from the level that upgrades a touch to a RESPECT
REACT_BARS = 2      # bars allowed for the reaction
DEDUP_BARS = 3      # episodes at same level+side within this many bars collapse
MATCH_EPS = 0.10    # ROLE_EPSILON — same "same level" tolerance the refresher uses
PREMARKET_COVERED_BY = "09:36"  # premarket respects are covered iff active on a tick within
                                # this minute or earlier (engine ticks land at :36:0x — the
                                # first actionable tick after the 09:35 entry-window open)

TAPE_SOURCES = ("premarket_high", "premarket_low", "prior_day_high", "prior_day_low",
                "prior_day_close", "intraday_rth_high", "intraday_rth_low",
                "intraday_swing_high", "intraday_swing_low")


# ---------------------------------------------------------------------------------------
# Bars + ledger IO
# ---------------------------------------------------------------------------------------

def fetch_frame(days_back: int = 12) -> pd.DataFrame:
    """SIP 5m frame via the refresher's own REST helper (shared code, shared creds path)."""
    import refresh_levels_intraday as rli
    return rli._fetch_bars_rest(feed="sip", days_back=days_back, limit=5000)


def session_dates(df: pd.DataFrame) -> list[str]:
    return sorted(d for d in df["date"].unique()
                  if len(df[(df["date"] == d) & (df["hm"] >= "09:30") & (df["hm"] <= "15:55")]) > 0)


def _iter_ledger_lines(date: str):
    """Yield raw lines that may hold `date` rows — current ledger first, then any archived
    copies (Gamma_LedgerArchive) so pruned/rotated days still measure."""
    if LEDGER.exists():
        with LEDGER.open(encoding="utf-8", errors="replace") as f:
            yield from f
    if ARCHIVE_DIR.exists():
        for day_dir in sorted(ARCHIVE_DIR.iterdir(), reverse=True):
            p = day_dir / "core-decisions.jsonl"
            if p.exists() and day_dir.name >= date:
                with p.open(encoding="utf-8", errors="replace") as f:
                    yield from f


def load_engine_timeline(date: str) -> list[tuple[str, list[float]]]:
    """[(ts_et, levels_active)] for the session, one row per tick (first account seen wins
    per timestamp — safe/bold read the same file, rows are duplicated per account)."""
    seen: dict[str, list[float]] = {}
    needle = f'"{date}T'
    for line in _iter_ledger_lines(date):
        if needle not in line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = str(r.get("ts_et") or "")
        if not ts.startswith(date):
            continue
        la = r.get("levels_active")
        if la is None:
            la = (r.get("bar_ctx") or {}).get("levels_active")
        if la is None or ts in seen:
            continue
        try:
            seen[ts] = [round(float(x), 2) for x in la]
        except (TypeError, ValueError):
            continue
    return sorted(seen.items())


def load_snapshot_levels(date: str) -> list[dict]:
    """File-layer universe from the day's key-levels-history snapshots (union by price)."""
    out: dict[float, dict] = {}
    day_dir = SNAP_DIR / date
    if not day_dir.exists():
        return []
    for snap in sorted(day_dir.glob("[0-9]*.json")):
        if snap.name.endswith("-memory.json"):
            continue
        try:
            kl = json.loads(snap.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for lv in kl.get("levels") or []:
            try:
                price = round(float(lv.get("price")), 2)
            except (TypeError, ValueError):
                continue
            if str(lv.get("tier", "")).lower() == "expired":
                continue
            src = str(lv.get("source") or "unknown")
            role = str(lv.get("role") or lv.get("type") or "")
            if price not in out:
                out[price] = {"price": price, "source": src, "role": role,
                              "first_snapshot": snap.stem}
    return list(out.values())


# ---------------------------------------------------------------------------------------
# Universe construction (tape-derived, ex-post, engine-independent)
# ---------------------------------------------------------------------------------------

def build_universe(df: pd.DataFrame, date: str) -> list[dict]:
    """Static levels: premarket/prior-day extremes + snapshot file layers. Running/swing
    families are handled dynamically inside scan_respects (their level moves per bar)."""
    uni: list[dict] = []
    day = df[df["date"] == date]
    pre = day[day["hm"] < "09:30"]
    if len(pre):
        uni.append({"price": round(float(pre["high"].max()), 2), "source": "premarket_high",
                    "role": "resistance"})
        uni.append({"price": round(float(pre["low"].min()), 2), "source": "premarket_low",
                    "role": "support"})
    dates = sorted(df["date"].unique())
    prior = [d for d in dates if d < date]
    if prior:
        pd_rth = df[(df["date"] == prior[-1]) & (df["hm"] >= "09:30") & (df["hm"] <= "15:55")]
        if len(pd_rth):
            uni.append({"price": round(float(pd_rth["high"].max()), 2),
                        "source": "prior_day_high", "role": "resistance"})
            uni.append({"price": round(float(pd_rth["low"].min()), 2),
                        "source": "prior_day_low", "role": "support"})
            uni.append({"price": round(float(pd_rth["close"].iloc[-1]), 2),
                        "source": "prior_day_close", "role": "either"})
    # file layers, deduped against tape-derived (tape source wins within MATCH_EPS)
    for lv in load_snapshot_levels(date):
        if any(abs(lv["price"] - u["price"]) <= MATCH_EPS for u in uni):
            continue
        uni.append(lv)
    return uni


# ---------------------------------------------------------------------------------------
# Respect scanning
# ---------------------------------------------------------------------------------------

def _reacted(bars: pd.DataFrame, i: int, level: float, side: str) -> bool:
    nxt = bars.iloc[i + 1: i + 1 + REACT_BARS]
    if len(nxt) == 0:
        return False
    if side == "support":
        return float(nxt["high"].max()) >= level + REACT
    return float(nxt["low"].min()) <= level - REACT


def _test_bar(bars: pd.DataFrame, i: int, level: float, side: str) -> bool:
    b = bars.iloc[i]
    if side == "support":
        return float(b["low"]) <= level + TOL and float(b["close"]) > level \
            and _reacted(bars, i, level, side)
    return float(b["high"]) >= level - TOL and float(b["close"]) < level \
        and _reacted(bars, i, level, side)


def scan_respects(df: pd.DataFrame, date: str, universe: list[dict]) -> list[dict]:
    """All respect episodes for the session: static universe levels tested on premarket+RTH
    bars; running RTH extremes and confirmed 3-bar swings tested dynamically."""
    day = df[df["date"] == date].reset_index(drop=True)
    scan = day[day["hm"] <= "15:55"].reset_index(drop=True)
    rth_mask = scan["hm"] >= "09:30"
    episodes: list[dict] = []

    def _emit(i: int, level: float, side: str, source: str) -> None:
        hm = str(scan.iloc[i]["hm"])
        for ep in episodes:
            if (ep["source"] == source and abs(ep["price"] - level) <= MATCH_EPS
                    and ep["side"] == side and i - ep["bar_i"] <= DEDUP_BARS):
                return  # same episode continuing
        episodes.append({"date": date, "hm": hm, "bar_i": i, "price": round(level, 2),
                         "side": side, "source": source,
                         "premarket": hm < "09:30"})

    # static universe levels — a level is only testable while it EXISTS: premarket extremes
    # exist from the bar after they print; prior-day + file layers exist all session.
    for u in universe:
        level, src = u["price"], u["source"]
        sides = ("support", "resistance") if u.get("role") in ("either", "", None) \
            else (("support",) if u["role"] == "support" else ("resistance",))
        if src in ("premarket_high", "premarket_low"):
            pre_bars = scan[scan["hm"] < "09:30"]
            if src == "premarket_high":
                ext_i = int(pre_bars["high"].idxmax()) if len(pre_bars) else -1
            else:
                ext_i = int(pre_bars["low"].idxmin()) if len(pre_bars) else -1
            start_i = ext_i + 1
        else:
            start_i = 0
        for side in sides:
            for i in range(max(start_i, 0), len(scan)):
                if _test_bar(scan, i, level, side):
                    _emit(i, level, side, src)

    # running RTH extremes (the level at bar i is the PRIOR bars' extreme)
    rth = scan[rth_mask].reset_index()  # keep original index in 'index'
    for i in range(1, len(rth)):
        prior_high = float(rth.iloc[:i]["high"].max())
        prior_low = float(rth.iloc[:i]["low"].min())
        gi = int(rth.iloc[i]["index"])
        if _test_bar(scan, gi, prior_high, "resistance"):
            _emit(gi, prior_high, "resistance", "intraday_rth_high")
        if _test_bar(scan, gi, prior_low, "support"):
            _emit(gi, prior_low, "support", "intraday_rth_low")

    # confirmed 3-bar swings (refresher's _swing_levels shape), active from pivot+1
    highs, lows = rth["high"].tolist(), rth["low"].tolist()
    for j in range(2, len(rth) - 1):
        if highs[j] >= highs[j - 1] and highs[j] >= highs[j + 1] and highs[j] > highs[j - 2]:
            level = round(highs[j], 2)
            for i in range(j + 2, len(rth)):
                gi = int(rth.iloc[i]["index"])
                if float(rth.iloc[i]["close"]) > level + TOL:
                    break  # swing high invalidated
                if _test_bar(scan, gi, level, "resistance"):
                    _emit(gi, level, "resistance", "intraday_swing_high")
        if lows[j] <= lows[j - 1] and lows[j] <= lows[j + 1] and lows[j] < lows[j - 2]:
            level = round(lows[j], 2)
            for i in range(j + 2, len(rth)):
                gi = int(rth.iloc[i]["index"])
                if float(rth.iloc[i]["close"]) < level - TOL:
                    break
                if _test_bar(scan, gi, level, "support"):
                    _emit(gi, level, "support", "intraday_swing_low")
    return episodes


# ---------------------------------------------------------------------------------------
# Coverage against the engine timeline
# ---------------------------------------------------------------------------------------

def _bar_close_ts(date: str, hm: str) -> str:
    h, m = int(hm[:2]), int(hm[3:])
    m += 5
    if m >= 60:
        m -= 60
        h += 1
    return f"{date}T{h:02d}:{m:02d}:00"


def grade_episodes(episodes: list[dict], timeline: list[tuple[str, list[float]]]) -> None:
    """Mutates each episode with covered_at_touch / first_active_ts / latency_min."""
    for ep in episodes:
        L = ep["price"]
        date = ep["date"]
        touch_ts = _bar_close_ts(date, ep["hm"])
        deadline = f"{date}T{PREMARKET_COVERED_BY}:59" if ep["premarket"] else touch_ts
        first_ts = None
        for ts, levels in timeline:
            if any(abs(x - L) <= MATCH_EPS for x in levels):
                first_ts = ts
                break
        ep["first_active_ts"] = first_ts
        ep["covered_at_touch"] = bool(first_ts is not None and first_ts <= deadline)
        if first_ts is None:
            ep["latency_min"] = None
        else:
            try:
                t0 = datetime.strptime(touch_ts, "%Y-%m-%dT%H:%M:%S")
                t1 = datetime.strptime(first_ts[:19], "%Y-%m-%dT%H:%M:%S")
                ep["latency_min"] = max(0.0, round((t1 - t0).total_seconds() / 60.0, 1))
            except ValueError:
                ep["latency_min"] = None


def summarize(date: str, episodes: list[dict], timeline_len: int) -> dict:
    per_source: dict[str, dict] = {}
    for ep in episodes:
        s = per_source.setdefault(ep["source"], {"respected": 0, "covered": 0,
                                                 "latencies": [], "misses": []})
        s["respected"] += 1
        if ep["covered_at_touch"]:
            s["covered"] += 1
        if ep["latency_min"] is not None:
            s["latencies"].append(ep["latency_min"])
        if not ep["covered_at_touch"]:
            s["misses"].append({"price": ep["price"], "hm": ep["hm"], "side": ep["side"],
                                "first_active_ts": ep["first_active_ts"],
                                "latency_min": ep["latency_min"]})
    for s in per_source.values():
        lat = sorted(s.pop("latencies"))
        s["median_latency_min"] = lat[len(lat) // 2] if lat else None
        s["coverage_pct"] = round(100.0 * s["covered"] / s["respected"], 1) if s["respected"] else None
    total = sum(s["respected"] for s in per_source.values())
    covered = sum(s["covered"] for s in per_source.values())
    return {"date": date, "defn_version": DEFN_VERSION,
            "engine_ticks_seen": timeline_len,
            "respected_total": total, "covered_total": covered,
            "coverage_pct": round(100.0 * covered / total, 1) if total else None,
            "per_source": per_source}


def trendline_note() -> str:
    try:
        w = json.loads(TRENDLINE_WATCH.read_text(encoding="utf-8"))
        act = w.get("active_lines") or []
        resp = sum(int(x.get("respect_count") or 0) for x in (w.get("all_lines") or act))
        return (f"trendlines (sloped, excluded from coverage math): {len(act)} active, "
                f"{resp} engine-counted respects, state {w.get('live_state_date_et')}")
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return "trendlines: watch surface unreadable"


# ---------------------------------------------------------------------------------------
# Persistence + CLI
# ---------------------------------------------------------------------------------------

def upsert_history(rows: list[dict]) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    old: dict[str, dict] = {}
    if HISTORY.exists():
        for line in HISTORY.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                old[str(r.get("date"))] = r
            except json.JSONDecodeError:
                continue
    for r in rows:
        slim = {k: v for k, v in r.items() if k != "per_source"}
        slim["per_source_coverage"] = {s: v["coverage_pct"] for s, v in r["per_source"].items()}
        slim["computed_at_et"] = et_now().strftime("%Y-%m-%dT%H:%M:%S")
        old[str(r["date"])] = slim
    lines = [json.dumps(old[d], sort_keys=True) for d in sorted(old)]
    tmp = HISTORY.with_suffix(".jsonl.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(HISTORY)


def run(dates: list[str], write: bool, df: pd.DataFrame | None = None) -> dict:
    df = fetch_frame() if df is None else df
    if df is None or len(df) == 0:
        return {"ok": False, "error": "no bars"}
    results = []
    for date in dates:
        uni = build_universe(df, date)
        eps = scan_respects(df, date, uni)
        timeline = load_engine_timeline(date)
        grade_episodes(eps, timeline)
        results.append(summarize(date, eps, len(timeline)))
    out = {"ok": True, "computed_at_et": et_now().strftime("%Y-%m-%dT%H:%M:%S"),
           "defn_version": DEFN_VERSION, "sessions": results,
           "trendline_note": trendline_note()}
    if write:
        OUT_LATEST.parent.mkdir(parents=True, exist_ok=True)
        tmp = OUT_LATEST.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(out, indent=1), encoding="utf-8")
        tmp.replace(OUT_LATEST)
        upsert_history(results)
    return out


def _table(out: dict) -> str:
    lines = [f"VIOLIN METRIC {out.get('defn_version')} @ {out.get('computed_at_et')}"]
    for s in out.get("sessions", []):
        lines.append(f"  {s['date']}: coverage {s['coverage_pct']}% "
                     f"({s['covered_total']}/{s['respected_total']} respects covered; "
                     f"{s['engine_ticks_seen']} engine ticks)")
        for src, v in sorted(s["per_source"].items()):
            med = v["median_latency_min"]
            lines.append(f"    {src:22s} {v['covered']}/{v['respected']:>2} covered "
                         f"({v['coverage_pct']}%), median latency "
                         f"{'-' if med is None else str(med) + 'm'}")
    lines.append("  " + out.get("trendline_note", ""))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", nargs="*", default=None)
    ap.add_argument("--last", type=int, default=1)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--nightly", action="store_true",
                    help="task mode: --last 1 --write, always exit 0")
    args = ap.parse_args()
    try:
        df = fetch_frame()
        if args.dates:
            dates = args.dates
        else:
            n = 1 if args.nightly else args.last
            dates = session_dates(df)[-n:]
        out = run(dates, write=args.write or args.nightly, df=df)
        print(_table(out) if out.get("ok") else json.dumps(out))
        return 0 if (out.get("ok") or args.nightly) else 1
    except Exception as exc:  # noqa: BLE001 — nightly must be loud in the log, never crash the chain
        print(f"[violin_metric] FAILED: {type(exc).__name__}: {exc}")
        return 0 if args.nightly else 1


if __name__ == "__main__":
    sys.exit(main())
