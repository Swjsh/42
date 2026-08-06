#!/usr/bin/env python
"""entry_quality_ledger.py -- THE ENTRY QUALITY LEDGER (LANE 4, 2026-08-06).

PREREG: analysis/recommendations/entry-quality-admissibility-prereg-2026-08-06.json,
committed 6d6bf8c8 BEFORE this file existed (freeze order git-provable). Every
definition here is the frozen one; drift from the prereg is a bug.

WHAT THIS IS
------------
One standing builder that answers "which entries PAY and which BLEED?" over the
full live-fills population, with every factor computed AT ENTRY TIME ONLY (C6:
every bar consulted must have CLOSED at or before the entry fill timestamp --
no look-ahead, ever):

  population  LIVE-ENGINE-REAL-FILLS-v2: every engine-attributed option BUY fill
              in automation/state/fills-ledger.jsonl (one fill = one entry event);
              P&L = FIFO within (arm, symbol, date) over ALL fills regardless of
              attribution (exits are broker truth even when a manual/EOD-flatten
              sell closed an engine entry -- the v1 population silently dropped
              one such entry, disclosed in the prereg).
  factors     (a) 5m + 1m market structure (BOS/CHoCH presence/recency/agreement)
              (b) level-tied trigger vs bare confirmation (decision-ledger join)
              (c) signed distance to the nearest same-session extreme already in
                  the engine's own levels_active (core ledger, causal timeline)
              (d) last-closed-5m-bar agreement (the V-d1 factor)
              (e) time-of-day bucket   (f) VWAP side (causal RTH-anchored)
  MFE/MAE     joined from analysis/pain-ledger/mae-mfe.json (the ONE frozen
              entry+1 excursion implementation) -- never recomputed here (L251:
              two engines that "should" agree will silently disagree).

⛔ DESCRIPTIVE + SHADOW ONLY. This module never blocks an entry, never writes any
engine/params surface, and its admissibility battery (--battery) exists to score
FROZEN prereg cells -- nothing it outputs arms anything.

OUTPUTS
-------
  analysis/entry-quality/entry-quality-ledger.json     (events + crossings + meta)
  analysis/entry-quality/admissibility-battery.json    (--battery: cells/gates/BH)

COST: $0. Alpaca SIP stock bars (already-wired key via backtest/tools/_alpaca_creds)
with an on-disk per-day cache so nightly reruns fetch at most one new day.

Manual:
    python setup/scripts/entry_quality_ledger.py            # build ledger
    python setup/scripts/entry_quality_ledger.py --battery  # + frozen battery
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "crypto", REPO / "backtest" / "tools", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

ET = ZoneInfo("America/New_York")
FILLS_LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
PAIN_LEDGER = REPO / "analysis" / "pain-ledger" / "mae-mfe.json"
OUT_DIR = REPO / "analysis" / "entry-quality"
LEDGER_OUT = OUT_DIR / "entry-quality-ledger.json"
BATTERY_OUT = OUT_DIR / "admissibility-battery.json"
BAR_CACHE_DIR = REPO / "backtest" / "data" / "spy_sip_cache"
PREREG = "analysis/recommendations/entry-quality-admissibility-prereg-2026-08-06.json"

RTH_START, RTH_END = dt.time(9, 30), dt.time(16, 0)
QUORUM_5M, QUORUM_1M = 8, 20            # frozen (prereg): structure-blind thresholds
WINDOW_5M, WINDOW_1M = 3, 5             # frozen: analyze_structure fractal windows
LEVEL_MATCH_TOL = 0.25                  # frozen: levels_active <-> session-extreme match
PERM_DRAWS, PERM_SEED = 20_000, 20260806
BH_Q_BAR = 0.10
OCC_RE = re.compile(r"^SPY(\d{6})([CP])(\d{8})$")

TOD_BUCKETS = (("0930-0959", dt.time(9, 30), dt.time(10, 0)),
               ("1000-1059", dt.time(10, 0), dt.time(11, 0)),
               ("1100-1159", dt.time(11, 0), dt.time(12, 0)),
               ("1200-1329", dt.time(12, 0), dt.time(13, 30)),
               ("1330-1459", dt.time(13, 30), dt.time(15, 0)),
               ("1500-1555", dt.time(15, 0), dt.time(16, 0)))


# ---------- bars: Alpaca SIP with per-day disk cache ---------------------------------------

def _cache_path(tf: str, date_et: str) -> Path:
    return BAR_CACHE_DIR / f"spy_{tf}_{date_et}.json"


def _fetch_sip_range(tf: str, start_date: str, end_date: str, timeout: int = 60) -> list[dict]:
    """One paginated SIP fetch; bars returned as naive-ET dicts {t,o,h,l,c,v}."""
    from _alpaca_creds import resolve_alpaca_creds
    creds = resolve_alpaca_creds()
    timeframe = {"1m": "1Min", "5m": "5Min"}[tf]
    url = "https://data.alpaca.markets/v2/stocks/SPY/bars"
    params = {"timeframe": timeframe, "start": f"{start_date}T07:00:00Z",
              "end": f"{end_date}T23:59:00Z", "limit": 10000, "feed": "sip",
              "adjustment": "raw", "sort": "asc"}
    now_clamp = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=16)
    end_dt = dt.datetime.fromisoformat(f"{end_date}T23:59:00+00:00")
    if end_dt > now_clamp:                       # Basic-plan 15-min SIP delay -> 403
        params["end"] = now_clamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    raw, token = [], None
    while True:
        q = dict(params)
        if token:
            q["page_token"] = token
        req = urllib.request.Request(
            url + "?" + urllib.parse.urlencode(q),
            headers={"APCA-API-KEY-ID": creds.key, "APCA-API-SECRET-KEY": creds.secret})
        payload = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        raw.extend(payload.get("bars") or [])
        token = payload.get("next_page_token")
        if not token:
            break
        time.sleep(0.15)
    out = []
    for b in raw:
        ts = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(ET)
        if dt.time(4, 0) <= ts.time() < dt.time(20, 0):
            out.append({"t": ts.replace(tzinfo=None).isoformat(), "o": b["o"], "h": b["h"],
                        "l": b["l"], "c": b["c"], "v": b["v"]})
    return out


def load_bars(tf: str, dates: list[str]) -> dict[str, list[dict]]:
    """Per-day bars (naive-ET), disk-cached. Missing days fetched in ONE ranged call."""
    BAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out: dict[str, list[dict]] = {}
    missing = []
    for d in dates:
        p = _cache_path(tf, d)
        if p.exists():
            out[d] = json.loads(p.read_text(encoding="utf-8"))["bars"]
        else:
            missing.append(d)
    if missing:
        fetched = _fetch_sip_range(tf, min(missing), max(missing))
        by_day: dict[str, list[dict]] = collections.defaultdict(list)
        for b in fetched:
            by_day[b["t"][:10]].append(b)
        for d in missing:
            bars = by_day.get(d, [])
            _cache_path(tf, d).write_text(json.dumps({"bars": bars}), encoding="utf-8")
            out[d] = bars
    for d, bars in out.items():
        for b in bars:
            b["dt"] = dt.datetime.fromisoformat(b["t"])
    return out


def rth(bars: list[dict]) -> list[dict]:
    return [b for b in bars if RTH_START <= b["dt"].time() < RTH_END]


def closed_before(bars: list[dict], cutoff: dt.datetime, minutes: int) -> list[dict]:
    """Bars whose CLOSE (open + minutes) is <= cutoff. Fully causal (C6)."""
    out = []
    for b in bars:
        if b["dt"] + dt.timedelta(minutes=minutes) <= cutoff:
            out.append(b)
        else:
            break
    return out


# ---------- population: LIVE-ENGINE-REAL-FILLS-v2 ------------------------------------------

def build_population() -> tuple[list[dict], dict]:
    """Entry events (engine buy fills) with FIFO P&L over ALL-attribution fills."""
    seen, fills = set(), []
    with open(FILLS_LEDGER, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if not r.get("is_option") or r["activity_id"] in seen:
                continue
            seen.add(r["activity_id"])
            fills.append(r)
    fills.sort(key=lambda r: r["ts_utc"])
    groups: dict[tuple, list[dict]] = collections.defaultdict(list)
    for r in fills:
        groups[(r["arm"], r["symbol"], r["date_et"])].append(r)

    events, unmatched_sell, leftover = [], 0.0, 0.0
    for g in groups.values():
        buys = [dict(r, remaining=r["qty"], pnl=0.0, exit_qty=0.0, last_exit_ts_utc=None,
                     first_exit_ts_utc=None) for r in g if r["side"] == "buy"]
        pending, active = collections.deque(buys), collections.deque()
        for r in g:
            if r["side"] == "buy":
                active.append(pending.popleft())
                continue
            sq = r["qty"]
            while sq > 1e-9 and active:
                b = active[0]
                take = min(sq, b["remaining"])
                b["remaining"] -= take
                b["pnl"] += (r["price"] - b["price"]) * take * r.get("multiplier", 100)
                b["exit_qty"] += take
                b["last_exit_ts_utc"] = r["ts_utc"]
                if b["first_exit_ts_utc"] is None:
                    b["first_exit_ts_utc"] = r["ts_utc"]
                sq -= take
                if b["remaining"] <= 1e-9:
                    active.popleft()
            unmatched_sell += max(0.0, sq)
        for b in buys:
            leftover += b["remaining"]
            if b["remaining"] > 1e-9:            # expiry: cost of the unclosed remainder
                b["pnl"] -= b["price"] * b["remaining"] * b.get("multiplier", 100)
                b["expired_qty"] = b["remaining"]
        events.extend(buys)

    events = [e for e in events if e.get("attribution") == "engine"]
    n_manual = sum(1 for g in groups.values() for r in g
                   if r["side"] == "buy" and r.get("attribution") != "engine")
    for e in events:
        m = OCC_RE.match(e["symbol"])
        e["opt_side"] = m.group(2) if m else None
        e["entry_dt"] = dt.datetime.fromisoformat(e["ts_et"])
    events.sort(key=lambda e: e["ts_utc"])
    meta = {"n_events": len(events), "n_manual_buys_excluded": n_manual,
            "unmatched_sell_qty": round(unmatched_sell, 4),
            "open_leftover_qty": round(leftover, 4),
            "net_usd": round(sum(e["pnl"] for e in events), 2),
            "days": sorted({e["date_et"] for e in events})}
    return events, meta


# ---------- factor (a): market structure ---------------------------------------------------

def structure_read(closed: list[dict], tf_minutes: int, window: int):
    """(kind, direction, bars_ago, trend) of the LAST BOS/CHoCH over `closed` bars."""
    from crypto.lib.bar import Bar
    from crypto.lib.market_structure import analyze_structure
    bars = [Bar(open_time=b["dt"].replace(tzinfo=ET), open=b["o"], high=b["h"], low=b["l"],
                close=b["c"], volume=b["v"], granularity_seconds=tf_minutes * 60,
                source="alpaca_sip") for b in closed]
    rd = analyze_structure(bars, window=window)
    ev = rd.events[-1] if rd.events else None
    if ev is None:
        return None, None, None, rd.trend
    direction = "up" if ev.direction == "bullish" else "down"
    return ev.kind, direction, (len(bars) - 1 - ev.break_index), rd.trend


def structure_bucket(n_closed: int, quorum: int, kind, direction, want: str) -> str:
    if n_closed < quorum:
        return "BLIND"
    if kind is None:
        return "NO_EVENT"
    return "AGREES" if direction == want else "DISAGREES"


# ---------- factor (b): decision-ledger join ----------------------------------------------

def _row_trigger_level(row: dict) -> float | None:
    for k in ("trigger_level", "trigger_level_exact"):
        if row.get(k) is not None:
            return row[k]
    side = row.get("side")
    if side == "P" and row.get("bear_rejection_level_raw") is not None:
        return row["bear_rejection_level_raw"]
    if side == "C" and row.get("bull_reclaim_level_raw") is not None:
        return row["bull_reclaim_level_raw"]
    return None


def match_decision(arm_rows: list[dict], symbol: str, entry_dt: dt.datetime) -> dict | None:
    """The ENTER row for THIS entry event: placement/exec symbol match, nearest in time
    within [-180s, +60s] of the fill (a symbol-only match would bind every 776C re-entry
    to the first one). Falls back to None -> unattributed, disclosed."""
    best, best_gap = None, None
    for r in arm_rows:
        for key in ("placement", "exec"):
            blk = r.get(key)
            if not (isinstance(blk, dict) and blk.get("symbol") == symbol):
                continue
            try:
                ts = dt.datetime.fromisoformat(str(r.get("ts_et"))[:19])
            except ValueError:
                continue
            gap = (entry_dt - ts).total_seconds()
            if -60 <= gap <= 180 and (best_gap is None or abs(gap) < abs(best_gap)):
                best, best_gap = r, gap
    return best


# ---------- factor (c): levels_active timeline ---------------------------------------------

def load_levels_timeline() -> dict[str, list[tuple[str, list[float]]]]:
    out: dict[str, list[tuple[str, list[float]]]] = collections.defaultdict(list)
    with open(CORE_DECISIONS, encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            la = r.get("levels_active")
            ts = str(r.get("ts_et", ""))
            if la and len(ts) >= 19:
                out[ts[:10]].append((ts[:19], la))
    for d in out:
        out[d].sort()
    return dict(out)


def levels_at(timeline: dict, date_et: str, entry_dt: dt.datetime) -> list[float] | None:
    best = None
    for ts, la in timeline.get(date_et, []):
        if dt.datetime.fromisoformat(ts) <= entry_dt:
            best = la
        else:
            break
    return best


def extreme_distance(spot: float, opt_side: str, c1: list[dict],
                     levels: list[float] | None):
    """Signed distance to the nearest same-session extreme present in levels_active.
    +ve = extreme AHEAD of the trade (long buying toward the session high / short
    toward the session low). None = abstain (no levels / no extreme match)."""
    if not levels or not c1 or spot is None:
        return None, None
    if opt_side == "C":
        ext = max(b["h"] for b in c1)
        matches = [lv for lv in levels if abs(lv - ext) <= LEVEL_MATCH_TOL]
        if not matches:
            return None, None
        lv = min(matches, key=lambda x: abs(x - spot))
        return round(lv - spot, 4), lv
    ext = min(b["l"] for b in c1)
    matches = [lv for lv in levels if abs(lv - ext) <= LEVEL_MATCH_TOL]
    if not matches:
        return None, None
    lv = min(matches, key=lambda x: abs(x - spot))
    return round(spot - lv, 4), lv


# ---------- factors (d)/(e)/(f) -------------------------------------------------------------

def last5_direction(c5: list[dict]) -> str | None:
    if not c5:
        return None
    b = c5[-1]
    return "up" if b["c"] > b["o"] else ("down" if b["c"] < b["o"] else "flat")


def tod_bucket(t: dt.time) -> str:
    for name, lo, hi in TOD_BUCKETS:
        if lo <= t < hi:
            return name
    return "other"


def vwap_side(c1: list[dict], spot: float | None) -> str:
    if not c1 or spot is None:
        return "unknown"
    num = sum(((b["h"] + b["l"] + b["c"]) / 3.0) * b["v"] for b in c1)
    den = sum(b["v"] for b in c1)
    if den <= 0:
        return "unknown"
    return "above" if spot >= num / den else "below"


# ---------- MFE join ------------------------------------------------------------------------

def load_pain_index() -> dict[tuple, dict]:
    try:
        pain = json.loads(PAIN_LEDGER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    idx = {}
    for r in pain.get("trades", []):
        key = (r["arm"], r["symbol"], r["entry_ts_utc"][:16])
        idx[key] = r
    return idx


# ---------- feature assembly ----------------------------------------------------------------

def build_features(events: list[dict], m1: dict, m5: dict, timeline: dict,
                   pain_idx: dict) -> None:
    import winner_autopsy as wa
    arm_rows_cache: dict[tuple, list[dict]] = {}

    def arm_rows(arm: str, d: str) -> list[dict]:
        key = (arm, d)
        if key not in arm_rows_cache:
            try:
                arm_rows_cache[key] = wa.load_arm_rows(arm, d)
            except Exception:                     # noqa: BLE001 -- join is best-effort
                arm_rows_cache[key] = []
        return arm_rows_cache[key]

    for e in events:
        d, cutoff, want = e["date_et"], e["entry_dt"], ("up" if e["opt_side"] == "C" else "down")
        r1, r5 = rth(m1.get(d, [])), rth(m5.get(d, []))
        c1, c5 = closed_before(r1, cutoff, 1), closed_before(r5, cutoff, 5)
        e["n_closed_1m"], e["n_closed_5m"] = len(c1), len(c5)
        e["spot"] = c1[-1]["c"] if c1 else None

        # (a) structure, both timeframes
        for tag, closed, tf_min, window, quorum in (("s5", c5, 5, WINDOW_5M, QUORUM_5M),
                                                    ("s1", c1, 1, WINDOW_1M, QUORUM_1M)):
            kind = direction = ago = trend = None
            if len(closed) >= quorum:
                try:
                    kind, direction, ago, trend = structure_read(closed, tf_min, window)
                except Exception as exc:          # noqa: BLE001 -- disclosed, never guessed
                    e[f"{tag}_err"] = repr(exc)[:100]
            e[f"{tag}_kind"], e[f"{tag}_dir"], e[f"{tag}_bars_ago"] = kind, direction, ago
            e[f"{tag}_trend"] = trend
            e[f"{tag}_bucket"] = structure_bucket(len(closed), quorum, kind, direction, want)

        # (b) level-tied vs bare
        row = match_decision(arm_rows(e["arm"], d), e["symbol"], e["entry_dt"])
        if row is None:
            e["b_class"], e["setup"], e["trigger_level"] = "unattributed", None, None
        else:
            lvl = _row_trigger_level(row)
            e["b_class"] = "tied" if lvl is not None else "bare"
            e["setup"] = row.get("setup") or row.get("setup_name")
            e["trigger_level"] = lvl

        # (c) distance to owned session extreme
        dist, lv = extreme_distance(e["spot"], e["opt_side"], c1,
                                    levels_at(timeline, d, cutoff))
        e["c_extreme_dist"], e["c_extreme_level"] = dist, lv

        # (d)/(e)/(f)
        e["d_last5_dir"] = last5_direction(c5)
        e["d_agree"] = (None if e["d_last5_dir"] is None
                        else e["d_last5_dir"] == ("up" if e["opt_side"] == "C" else "down"))
        e["e_tod"] = tod_bucket(cutoff.time())
        e["f_vwap"] = vwap_side(c1, e["spot"])

        # MFE/MAE join (pain ledger = the one frozen excursion implementation)
        pr = pain_idx.get((e["arm"], e["symbol"], e["ts_utc"][:16]))
        e["mfe_pct"] = pr["mfe_pct"] if pr else None
        e["mae_pct"] = pr["mae_pct"] if pr else None
        e["mfe_join"] = "pain" if pr else "none"


# ---------- admissibility cells (frozen) ----------------------------------------------------

CELLS = ("R-PRES-5m", "R-S8-5m", "R-PRES-1m", "R-S40-1m", "V-d1-rescore")


def blocked_by(e: dict, cell: str):
    """True = BLOCK, False = keep, None = ABSTAIN. Definitions frozen in the prereg."""
    if cell == "R-PRES-5m":
        if e["n_closed_5m"] < QUORUM_5M:
            return None
        return e["s5_kind"] is None
    if cell == "R-S8-5m":
        if e["n_closed_5m"] < QUORUM_5M:
            return None
        return e["s5_kind"] is None or e["s5_bars_ago"] > 8
    if cell == "R-PRES-1m":
        if e["n_closed_1m"] < QUORUM_1M:
            return None
        return e["s1_kind"] is None
    if cell == "R-S40-1m":
        if e["n_closed_1m"] < QUORUM_1M:
            return None
        return e["s1_kind"] is None or e["s1_bars_ago"] > 40
    if cell == "V-d1-rescore":
        if e["d_last5_dir"] is None:
            return None
        return e["d_last5_dir"] != ("up" if e["opt_side"] == "C" else "down")
    raise ValueError(cell)


def perm_p(events: list[dict], blocked_ids: set, eligible: list[dict],
           delta_obs: float, rng: random.Random) -> float:
    """Within-day permutation (frozen): per-day block COUNT held fixed, blocked entries
    re-drawn among that day's ELIGIBLE (non-abstain) entries. One-sided."""
    by_day: dict[str, list[dict]] = collections.defaultdict(list)
    for e in eligible:
        by_day[e["date_et"]].append(e)
    k_by_day = {d: sum(1 for e in rows if id(e) in blocked_ids)
                for d, rows in by_day.items()}
    days = [(rows, k_by_day[d]) for d, rows in by_day.items() if k_by_day[d] > 0]
    if not days:
        return 1.0
    hits = 0
    for _ in range(PERM_DRAWS):
        delta = 0.0
        for rows, k in days:
            delta -= sum(e["pnl"] for e in rng.sample(rows, k))
        if delta >= delta_obs - 1e-9:
            hits += 1
    return hits / PERM_DRAWS


def bh_qvalues(ps: dict[str, float]) -> dict[str, float]:
    m = len(ps)
    order = sorted(ps, key=lambda k: ps[k])
    q, prev = {}, 1.0
    for rank_from_end, key in enumerate(reversed(order)):
        i = m - rank_from_end               # 1-based rank
        prev = min(prev, ps[key] * m / i)
        q[key] = round(prev, 4)
    return q


def run_battery(events: list[dict]) -> dict:
    rng = random.Random(PERM_SEED)
    days = sorted({e["date_et"] for e in events})
    half = set(days[: len(days) // 2])
    rows, ps = [], {}
    for cell in CELLS:
        verdicts = [(e, blocked_by(e, cell)) for e in events]
        blocked = [e for e, v in verdicts if v is True]
        eligible = [e for e, v in verdicts if v is not None]
        abstain_n = len(events) - len(eligible)
        bl_ids = {id(e) for e in blocked}
        by_day = collections.defaultdict(float)
        for e in blocked:
            by_day[e["date_et"]] -= e["pnl"]     # per-day delta contribution
        delta_days = sorted(by_day.items(), key=lambda kv: kv[1], reverse=True)
        delta_full = round(sum(by_day.values()), 2)
        drop1 = round(delta_full - (delta_days[0][1] if delta_days else 0.0), 2)
        drop2 = round(delta_full - sum(v for _, v in delta_days[:2]), 2)
        winner_usd = round(sum(e["pnl"] for e in blocked if e["pnl"] > 0), 2)
        loser_usd = round(-sum(e["pnl"] for e in blocked if e["pnl"] < 0), 2)
        p = perm_p(events, bl_ids, eligible, delta_full, rng)
        ps[cell] = p
        row = {
            "cell": cell, "n_blocked": len(blocked), "n_abstain": abstain_n,
            "delta_full": delta_full, "delta_drop_best_day": drop1,
            "delta_drop_top2": drop2,
            "blocked_winner_usd": winner_usd, "blocked_loser_usd": loser_usd,
            "blocked_wr_pct": round(100 * sum(1 for e in blocked if e["pnl"] > 0)
                                    / len(blocked), 1) if blocked else None,
            "delta_h1": round(-sum(e["pnl"] for e in blocked if e["date_et"] in half), 2),
            "delta_h2": round(-sum(e["pnl"] for e in blocked if e["date_et"] not in half), 2),
            "delta_2026_08_04": round(by_day.get("2026-08-04", 0.0), 2),
            "delta_2026_08_05": round(by_day.get("2026-08-05", 0.0), 2),
            "delta_2026_08_06": round(by_day.get("2026-08-06", 0.0), 2),
            "days_touched": len(delta_days),
            "days_negative": sum(1 for _, v in delta_days if v < 0),
            "worst_day_usd": round(min((v for _, v in delta_days), default=0.0), 2),
            "p_within_day": round(p, 4),
        }
        rows.append(row)
    qs = bh_qvalues(ps)
    for row in rows:
        row["bh_q"] = qs[row["cell"]]
        g = {"G1": row["delta_full"] > 0,
             "G2": row["blocked_winner_usd"] < row["blocked_loser_usd"],
             "G3": row["delta_drop_top2"] > 0,
             "G4": row["delta_h1"] >= 0 and row["delta_h2"] >= 0,
             "G5": row["n_blocked"] >= 8,
             "G6": row["worst_day_usd"] >= -250,
             "G7": row["bh_q"] <= BH_Q_BAR}
        row["gates"] = "".join(k[1] if v else "-" for k, v in g.items())
        if g["G1"] and g["G2"] and g["G3"] and g["G4"] and g["G5"] and g["G6"]:
            row["verdict"] = "FORWARD_SHADOW_CANDIDATE"
        elif g["G1"] and g["G2"]:
            row["verdict"] = "WATCH"
        else:
            row["verdict"] = "REJECT"
    return {"cells": rows, "perm_draws": PERM_DRAWS, "perm_seed": PERM_SEED,
            "bh_family_size": len(CELLS), "bh_q_bar": BH_Q_BAR}


# ---------- crossings (descriptive) ---------------------------------------------------------

def _cell_stats(rows: list[dict]) -> dict:
    n = len(rows)
    mfes = [r["mfe_pct"] for r in rows if r["mfe_pct"] is not None]
    return {"n": n,
            "pnl_usd": round(sum(r["pnl"] for r in rows), 2),
            "pnl_per_entry": round(sum(r["pnl"] for r in rows) / n, 2) if n else None,
            "wr_pct": round(100 * sum(1 for r in rows if r["pnl"] > 0) / n, 1) if n else None,
            "median_mfe_pct": round(sorted(mfes)[len(mfes) // 2], 4) if mfes else None,
            "n_mfe": len(mfes)}


def crossings(events: list[dict]) -> dict:
    out: dict = {}

    def cross(name: str, keyfn) -> None:
        buckets = collections.defaultdict(list)
        for e in events:
            buckets[str(keyfn(e))].append(e)
        out[name] = {k: _cell_stats(v) for k, v in sorted(buckets.items())}

    cross("a_structure_5m_bucket", lambda e: e["s5_bucket"])
    cross("a_structure_1m_bucket", lambda e: e["s1_bucket"])
    cross("a_structure_5m_within8", lambda e: (
        "BLIND" if e["n_closed_5m"] < QUORUM_5M else
        ("EVENT<=8bars" if e["s5_kind"] is not None and e["s5_bars_ago"] <= 8
         else "NO_RECENT_EVENT")))
    cross("b_trigger_class", lambda e: e["b_class"])
    cross("c_extreme_dist", lambda e: (
        "abstain" if e["c_extreme_dist"] is None else
        "beyond(<0)" if e["c_extreme_dist"] < 0 else
        "hug(0-0.5)" if e["c_extreme_dist"] <= 0.5 else
        "near(0.5-1.5)" if e["c_extreme_dist"] <= 1.5 else "far(>1.5)"))
    cross("d_last5_agreement", lambda e: e["d_agree"])
    cross("e_tod", lambda e: e["e_tod"])
    cross("f_vwap_side", lambda e: e["f_vwap"])
    cross("setup", lambda e: e.get("setup"))
    return out


# ---------- build + main --------------------------------------------------------------------

def build_ledger() -> dict:
    from et_clock import et_now
    events, pop_meta = build_population()
    dates = pop_meta["days"]
    m1, m5 = load_bars("1m", dates), load_bars("5m", dates)
    build_features(events, m1, m5, load_levels_timeline(), load_pain_index())

    clean = []
    for e in events:
        clean.append({k: v for k, v in e.items()
                      if k not in ("entry_dt", "remaining") and not k.startswith("_")})
    ledger = {
        "_meta": {
            "generated_at_et": et_now().isoformat(),
            "builder": "setup/scripts/entry_quality_ledger.py",
            "prereg": PREREG,
            "population_id": "LIVE-ENGINE-REAL-FILLS-v2",
            "shadow_only": "⛔ DESCRIPTIVE + SHADOW ONLY -- nothing here blocks a live entry.",
            "provenance": {
                "entries": "fills-ledger.jsonl attribution==engine option buys (1 fill = 1 event)",
                "pnl": "FIFO vs ALL-attribution exits (broker truth); expiry remainder = -cost",
                "bars": "Alpaca SIP 1m/5m via backtest/data/spy_sip_cache",
                "mfe": "analysis/pain-ledger/mae-mfe.json join (frozen entry+1 conventions)",
                "levels": "core-decisions.jsonl levels_active timeline (exists from 2026-07-28)",
            },
            "population": {**pop_meta,
                           "n_days": len(dates),
                           "n_mfe_joined": sum(1 for e in events if e["mfe_join"] == "pain"),
                           "n_unattributed_decision": sum(1 for e in events
                                                          if e["b_class"] == "unattributed")},
        },
        "crossings": crossings(events),
        "events": clean,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LEDGER_OUT.write_text(json.dumps(ledger, indent=1, default=str), encoding="utf-8")
    print(f"[entry-quality] {len(events)} events / {len(dates)} days "
          f"net ${pop_meta['net_usd']:.2f} -> {LEDGER_OUT.relative_to(REPO)}")
    return ledger


def main() -> int:
    ap = argparse.ArgumentParser(description="Entry quality ledger (descriptive+shadow only).")
    ap.add_argument("--battery", action="store_true",
                    help="also run the frozen admissibility battery")
    args = ap.parse_args()
    ledger = build_ledger()
    if args.battery:
        events = ledger["events"]
        for e in events:
            e["entry_dt"] = dt.datetime.fromisoformat(e["ts_et"])
        battery = run_battery(events)
        battery["_meta"] = {"prereg": PREREG, "generated_at_et": ledger["_meta"]["generated_at_et"],
                            "population_id": "LIVE-ENGINE-REAL-FILLS-v2",
                            "n_events": len(events)}
        BATTERY_OUT.write_text(json.dumps(battery, indent=1), encoding="utf-8")
        print(f"[entry-quality] battery -> {BATTERY_OUT.relative_to(REPO)}")
        for row in battery["cells"]:
            print(f"  {row['cell']:<14} n={row['n_blocked']:>3} d={row['delta_full']:>9} "
                  f"top2={row['delta_drop_top2']:>9} p={row['p_within_day']:.3f} "
                  f"q={row['bh_q']:.3f} {row['gates']} {row['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
