#!/usr/bin/env python
"""lever_entry_count_2026_08_06.py -- LEVER 4: STOP THE BLEED AT THE SOURCE.

Pre-registration: analysis/recommendations/lever-entry-count-prereg-2026-08-06.json
(commit bf8dec8d, frozen BEFORE this file existed -- provable with
`git merge-base --is-ancestor bf8dec8d <this file's commit>`).

J's ask (2026-08-06, after the close): keep the LOSSES small so the wins can stack.
Wednesday 2026-08-05 lost -$1,935.00 (SPY options only) / -$1,943.66 (all-in) the day after
Tuesday made +$3,624.00 / +$3,617.19. THIS lane asks exactly one question: does capping or
qualifying ENTRIES cap a Wednesday-shaped day WITHOUT costing Tuesday or Thursday?

Seven pre-registered cell families:
  C1 wave cap        -- at most N positions per (arm, date, symbol)              N in 1..5
  C2 day cap         -- at most N positions per (arm, date) total                N in 3..6
  C3 once/day SCOPED -- at most 1 vwap_continuation position per (arm, date)     DEFECT FIX
  C4 once/day ALL    -- at most 1 position per (arm, date, setup)                contrast
  C5 time cooldown   -- GRAVEYARD comparator, reported, never recommended        M in 5..30
  C6 V-d1            -- last CLOSED 5m bar must agree with the trade direction
  C7 session-high    -- refuse a long within X of a session high that is ALSO in levels_active

COUNTERFACTUAL SEMANTICS (per prereg): a blocked position contributes $0. Nothing is
re-priced, nothing is re-walked, no exit model is invoked. Removing a real broker fill from
the book is arithmetic on broker truth -- the only counterfactual this lane is entitled to.

Run: backtest/.venv/Scripts/python.exe backtest/tools/lever_entry_count_2026_08_06.py
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import random
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "setup" / "scripts",
           REPO / "automation" / "state" / "fleet", REPO / "backtest"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import exit_shape_parity_study as esp  # noqa: E402
import fleet_broker as fb  # noqa: E402

LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
CORE_DEC = REPO / "automation" / "state" / "core-decisions.jsonl"
FLEET_DEC = REPO / "automation" / "state" / "fleet" / "*" / "decisions.jsonl"
BARS_5M = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-08-06.csv"
REPLAY = REPO / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
OUT_JSON = REPO / "analysis" / "deep-research" / "LEVER-ENTRY-COUNT-2026-08-06.json"
CACHE_1M = Path(os.environ.get("LEVER4_CACHE", REPO / "analysis" / "deep-research")) / "_lever4_spy1m.json"

TUE, WED, THU = "2026-08-04", "2026-08-05", "2026-08-06"
VWAP = "VWAP_CONTINUATION"
SEED = 20260806
N_PERM = 20000
LEVEL_MATCH_TOL = 0.05          # prereg: |level - session extreme| <= 5 cents
PARENT_STUDY_N_CELLS = 17       # prereg: multiplicity correction base


# ════════════════════════════════════════════════════════════ population A: the book
def _parse_et(s: str) -> "dt.datetime | None":
    try:
        return dt.datetime.fromisoformat(s).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _decision_index() -> list[dict]:
    """Every ENTER decision the engine logged, from BOTH lanes, as
    {arm, dt, setup, side, symbol}. Used only to label a real fill with the setup that
    produced it -- never as a P&L source."""
    out: list[dict] = []
    for pth in glob.glob(str(FLEET_DEC)):
        arm = os.path.basename(os.path.dirname(pth))
        for line in Path(pth).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(r.get("action", "")).startswith("ENTER"):
                out.append({"arm": arm, "dt": _parse_et(r.get("ts_et", "")),
                            "setup": r.get("setup_name"), "side": r.get("side"),
                            "symbol": None})
    core_arm = {"safe": "safe-2", "bold": "bold-2"}
    for line in CORE_DEC.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        arm = core_arm.get(r.get("account"))
        if not arm:
            continue
        when = _parse_et(r.get("ts_et", ""))
        if str(r.get("verdict", "")).startswith("ENTER"):
            out.append({"arm": arm, "dt": when, "setup": r.get("setup"),
                        "side": r.get("side"), "symbol": None})
        # core EXTRA-SETUP placements carry the exact symbol -- the highest-fidelity label
        for ex in (r.get("extra_exec") or []):
            if not isinstance(ex, dict) or ex.get("action") != "PLACED":
                continue
            sym = ((ex.get("exec") or {}).get("symbol"))
            out.append({"arm": arm, "dt": when, "setup": ex.get("setup"),
                        "side": (ex.get("exec") or {}).get("side"), "symbol": sym})
    return [d for d in out if d["dt"] is not None]


def load_book() -> list[dict]:
    """Population A. Real broker fills -> canonical positions -> setup-labelled, ordinal-
    stamped. Sorted by entry time."""
    fills = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("attribution") == "engine" and r.get("is_option") and not r.get("is_crypto"):
            fills.append(r)
    ts_et = {(f["arm"], f["symbol"], f["ts_utc"]): f["ts_et"] for f in fills}
    pos = [p for p in esp.reconstruct_positions(fills) if p["exit_fills"]]
    for p in pos:
        p["entry_ts_et"] = ts_et.get((p["arm"], p["symbol"], p["entry_ts_utc"]), "")
        p["entry_dt"] = _parse_et(p["entry_ts_et"])
        p["exit_ts_et"] = max(ef["ts_et"] for ef in p["exit_fills"])
        p["exit_dt"] = _parse_et(p["exit_ts_et"])
        p["pnl"] = round(p["actual_exit_pnl"], 2)
        p["side"] = "C" if "C00" in p["symbol"] else "P"
    pos.sort(key=lambda p: (p["entry_ts_utc"], p["arm"]))

    dec = _decision_index()
    for p in pos:
        best = None
        for d in dec:
            if d["arm"] != p["arm"]:
                continue
            if d["symbol"] is not None:
                if d["symbol"] != p["symbol"]:
                    continue
            elif d["side"] != p["side"]:
                continue
            gap = (p["entry_dt"] - d["dt"]).total_seconds()
            if -5.0 <= gap <= 300.0 and (best is None or gap < best[0]):
                best = (gap, d)
        p["setup"] = (best[1]["setup"] if best else None)
        p["setup_matched"] = best is not None

    wave: dict = defaultdict(int)
    day: dict = defaultdict(int)
    setup_seq: dict = defaultdict(int)
    for p in pos:
        wave[(p["arm"], p["symbol"], p["date_et"])] += 1
        p["wave_ordinal"] = wave[(p["arm"], p["symbol"], p["date_et"])]
        day[(p["arm"], p["date_et"])] += 1
        p["day_ordinal"] = day[(p["arm"], p["date_et"])]
        setup_seq[(p["arm"], p["date_et"], p["setup"])] += 1
        p["setup_ordinal"] = setup_seq[(p["arm"], p["date_et"], p["setup"])]
    for p in pos:
        p["wave_n"] = wave[(p["arm"], p["symbol"], p["date_et"])]
    return pos


# ════════════════════════════════════════════════════════════ population B: the replay
def load_replay() -> "tuple[list[dict], dict]":
    d = json.loads(REPLAY.read_text(encoding="utf-8"))
    trades = []
    for t in d["trades"]:
        trades.append({**t, "pnl": round(float(t["dollar_pnl"]), 2),
                       "date_et": t["date"], "arm": "replay",
                       "entry_dt": _parse_et(t["entry_time_et"])})
    trades.sort(key=lambda t: (t["date_et"], t["entry_time_et"]))
    return trades, d


# ════════════════════════════════════════════════════════════ scoring
def day_totals(rows: list[dict]) -> dict:
    d: dict = defaultdict(float)
    for r in rows:
        d[r["date_et"]] += r["pnl"]
    return {k: round(v, 2) for k, v in d.items()}


def score(base_days: dict, blocked: list[dict], all_rows: list[dict], label: str,
          *, n_abstain: int = 0, coverage_days: "list[str] | None" = None) -> dict:
    """Every counterfactual in this lane is 'delete these positions'. One scorer, one
    definition, applied identically to every cell so no cell gets a bespoke metric."""
    bset = {id(b) for b in blocked}
    kept = [r for r in all_rows if id(r) not in bset]
    cf = day_totals(kept)
    days = sorted(set(base_days) | set(cf))
    deltas = {d: round(cf.get(d, 0.0) - base_days.get(d, 0.0), 2) for d in days}
    harmed = {d: v for d, v in deltas.items() if v < -0.005}
    helped = {d: v for d, v in deltas.items() if v > 0.005}
    win_blocked = round(sum(b["pnl"] for b in blocked if b["pnl"] > 0), 2)
    los_blocked = round(-sum(b["pnl"] for b in blocked if b["pnl"] < 0), 2)
    tot = round(sum(deltas.values()), 2)
    return {
        "cell": label,
        "n_blocked": len(blocked),
        "n_abstain": n_abstain,
        "coverage_days": len(coverage_days) if coverage_days is not None else len(base_days),
        "delta_total": tot,
        "delta_tue_2026_08_04": deltas.get(TUE, 0.0),
        "delta_wed_2026_08_05": deltas.get(WED, 0.0),
        "delta_thu_2026_08_06": deltas.get(THU, 0.0),
        "delta_ex_wed": round(sum(v for d, v in deltas.items() if d != WED), 2),
        "delta_ex_week": round(sum(v for d, v in deltas.items()
                                   if d not in (TUE, WED, THU)), 2),
        "wed_after": cf.get(WED, 0.0),
        "book_after": round(sum(cf.values()), 2),
        "blocked_winner_usd": win_blocked,
        "blocked_loser_usd": los_blocked,
        "blocked_win_rate_pct": (round(100.0 * sum(1 for b in blocked if b["pnl"] > 0)
                                       / len(blocked), 1) if blocked else None),
        "n_days_harmed": len(harmed),
        "n_days_helped": len(helped),
        "worst_harmed_day": (min(harmed.items(), key=lambda kv: kv[1]) if harmed else None),
        "harmed_days": dict(sorted(harmed.items(), key=lambda kv: kv[1])[:6]),
        "share_of_benefit_from_wed_pct": (round(100.0 * deltas.get(WED, 0.0) / tot, 1)
                                          if tot > 0 else None),
        "blocked_week_detail": [
            {"arm": b.get("arm"), "date": b["date_et"],
             "t": (b.get("entry_ts_et") or b.get("entry_time_et", ""))[11:19],
             "sym": b.get("symbol"), "setup": b.get("setup"),
             "wave_ord": b.get("wave_ordinal"), "pnl": b["pnl"]}
            for b in blocked if b["date_et"] in (TUE, WED, THU)],
    }


def gates(row: dict, *, is_defect_fix: bool, popB: "str | float") -> dict:
    g = {
        "G1_tuesday_hard": row["delta_tue_2026_08_04"] >= -100.0,
        "G2_thursday": row["delta_thu_2026_08_06"] >= -100.0,
        "G3_wednesday": row["delta_wed_2026_08_05"] > 0.0,
        "G4_population": row["delta_total"] > 0.0,
        "G5_not_only_wed": row["delta_ex_wed"] >= 0.0,
        "G6_does_no_harm": row["n_days_harmed"] == 0,
        "G7_frequency": row["n_blocked"] >= 5,
        "G8_populationB": (popB == "NO_OP" or (isinstance(popB, (int, float)) and popB >= 0)),
    }
    row["gates"] = "".join(k.split("_")[0][1] if v else "-" for k, v in g.items())
    row["gates_pass"] = sum(g.values())
    row["gate_detail"] = g
    row["popB"] = popB
    if not (g["G1_tuesday_hard"] and g["G2_thursday"]):
        row["verdict"] = "REJECT"
    elif not g["G3_wednesday"]:
        row["verdict"] = "NULL"
    elif all(g.values()) and is_defect_fix:
        row["verdict"] = "SHIP"
    elif all(g.values()):
        row["verdict"] = "PREREG"
    elif g["G4_population"] and g["G6_does_no_harm"]:
        row["verdict"] = "PREREG"
    else:
        row["verdict"] = "SHADOW"
    return row


# ════════════════════════════════════════════════════════════ C1 / C2 / C3 / C4 / C5
def cap_by_key(rows: list[dict], keyfn, n: int) -> list[dict]:
    seq: dict = defaultdict(int)
    blocked = []
    for p in sorted(rows, key=lambda q: (q["date_et"], q.get("entry_ts_utc") or
                                         q.get("entry_time_et", ""))):
        k = keyfn(p)
        seq[k] += 1
        if seq[k] > n:
            blocked.append(p)
    return blocked


def once_per_day_setup(rows: list[dict], only_setup: "str | None") -> list[dict]:
    seq: dict = defaultdict(int)
    blocked = []
    for p in sorted(rows, key=lambda q: (q["date_et"], q["entry_ts_utc"])):
        if only_setup is not None and p.get("setup") != only_setup:
            continue
        if p.get("setup") is None:
            continue           # unlabelled -> ABSTAIN, never block on a guess
        k = (p["arm"], p["date_et"], p["setup"])
        seq[k] += 1
        if seq[k] > 1:
            blocked.append(p)
    return blocked


def time_cooldown(rows: list[dict], minutes: int) -> list[dict]:
    """GRAVEYARD COMPARATOR. After a position in setup S closes for arm A, block any new S
    entry for `minutes`. Chained causally: a blocked entry never happened, so it can never
    itself start a cooldown."""
    last_close: dict = {}
    blocked = []
    for p in sorted(rows, key=lambda q: (q["date_et"], q["entry_ts_utc"])):
        if p.get("setup") is None:
            continue
        k = (p["arm"], p["date_et"], p["setup"])
        prev = last_close.get(k)
        if prev is not None and p["entry_dt"] is not None and \
                (p["entry_dt"] - prev).total_seconds() < minutes * 60:
            blocked.append(p)
            continue
        if p["exit_dt"] is not None:
            last_close[k] = p["exit_dt"]
    return blocked


# ════════════════════════════════════════════════════════════ bars
def load_5m(path: "Path | None" = None) -> dict:
    import csv
    out: dict = defaultdict(list)
    with (path or BARS_5M).open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            ts = _parse_et(str(r["timestamp_et"]).replace(" ", "T")[:19])
            if ts is None:
                continue
            out[ts.date().isoformat()].append(
                {"t": ts, "o": float(r["open"]), "h": float(r["high"]),
                 "l": float(r["low"]), "c": float(r["close"])})
    for d in out:
        out[d].sort(key=lambda b: b["t"])
    return dict(out)


def fetch_1m(dates: list[str]) -> dict:
    """SPY 1-min SIP bars for the given ET dates. Cached on disk so a rerun costs nothing."""
    cache: dict = {}
    if CACHE_1M.exists():
        try:
            cache = json.loads(CACHE_1M.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cache = {}
    need = [d for d in dates if d not in cache]
    if need:
        # L234: never hardcode / never take the FIRST key -- a retired arm's key 401s and a
        # fail-open fetcher would report the 401 as "no data". Probe for a LIVE key.
        creds = esp._live_data_creds()  # noqa: SLF001 -- the repo's one probed-creds helper
        if creds is None:
            raise RuntimeError("no LIVE broker creds for the 1m SIP fetch")
        _ = fb
        # Alpaca Basic delays SIP by 15 min: any window reaching into the last 15 minutes
        # 403s. Clamp the end bound (same rule as backtest/tools/alpaca_bars.py#SIP_DELAY).
        now_clamp = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=16)
        for d in need:
            end_dt = dt.datetime.fromisoformat(f"{d}T21:00:00+00:00")
            if end_dt > now_clamp:
                end_dt = now_clamp
                print(f"  [1m] clamping {d} end to {end_dt:%H:%MZ} (SIP 15-min delay)")
            url = ("https://data.alpaca.markets/v2/stocks/SPY/bars"
                   f"?timeframe=1Min&start={d}T08:00:00Z"
                   f"&end={end_dt:%Y-%m-%dT%H:%M:%SZ}"
                   "&limit=10000&feed=sip&adjustment=raw")
            req = urllib.request.Request(url, headers={
                "APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]})
            try:
                with urllib.request.urlopen(req, timeout=40) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                    ConnectionError, ValueError) as exc:
                raise RuntimeError(f"1m SIP fetch failed for {d}: {exc}") from exc
            bars = data.get("bars") or []
            if not bars:
                raise RuntimeError(f"1m SIP fetch returned ZERO bars for {d} -- refusing to "
                                   "proceed on an empty tape (L241: never let a silent empty "
                                   "fetch look like 'no signal')")
            cache[d] = [{"t": b["t"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]}
                        for b in bars]
            print(f"  [1m] {d}: {len(bars)} bars")
            CACHE_1M.parent.mkdir(parents=True, exist_ok=True)
            CACHE_1M.write_text(json.dumps(cache), encoding="utf-8")
    out: dict = {}
    for d in dates:
        rows = []
        for b in cache[d]:
            ts = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00")) \
                - dt.timedelta(hours=4)          # EDT; every book date is in EDT months
            rows.append({"t": ts.replace(tzinfo=None), "o": b["o"], "h": b["h"],
                         "l": b["l"], "c": b["c"]})
        rows.sort(key=lambda b: b["t"])
        out[d] = rows
    return out


def levels_by_day() -> dict:
    """{date: [(ts_et, [levels...]), ...]} from the engine's OWN core-decisions log. Only
    populated from 2026-07-28 -- the coverage limit is reported, never hidden."""
    out: dict = defaultdict(list)
    for line in CORE_DEC.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        la = r.get("levels_active")
        if not la:
            continue
        ts = _parse_et(r.get("ts_et", ""))
        if ts is None:
            continue
        out[ts.date().isoformat()].append((ts, [float(x) for x in la]))
    for d in out:
        out[d].sort(key=lambda kv: kv[0])
    return dict(out)


# ════════════════════════════════════════════════════════════ C6 / C7 features
def annotate_features(book: list[dict], m5: dict, m1: dict, lvl: dict) -> None:
    for p in book:
        d, cut = p["date_et"], p["entry_dt"]
        # --- C6: last FULLY CLOSED 5m bar strictly before the fill (close = open+5m)
        closed5 = [b for b in m5.get(d, [])
                   if dt.time(9, 30) <= b["t"].time() < dt.time(16, 0)
                   and b["t"] + dt.timedelta(minutes=5) <= cut]
        p["last5_dir"] = None
        p["trigger_bar_et"] = None
        if closed5:
            b = closed5[-1]
            p["last5_dir"] = "up" if b["c"] > b["o"] else ("down" if b["c"] < b["o"] else "flat")
            p["trigger_bar_et"] = b["t"].isoformat()
        # --- C7: session extreme so far on CLOSED 1m bars + spot
        closed1 = [b for b in m1.get(d, [])
                   if dt.time(9, 30) <= b["t"].time() < dt.time(16, 0)
                   and b["t"] + dt.timedelta(minutes=1) <= cut]
        p["spot"] = closed1[-1]["c"] if closed1 else None
        p["sess_high"] = max((b["h"] for b in closed1), default=None)
        p["sess_low"] = min((b["l"] for b in closed1), default=None)
        rows = lvl.get(d, [])
        act = None
        for ts, ls in rows:
            if ts <= cut:
                act = ls
            else:
                break
        p["levels_active"] = act
        p["sess_high_in_levels"] = (
            act is not None and p["sess_high"] is not None
            and any(abs(L - p["sess_high"]) <= LEVEL_MATCH_TOL for L in act))
        p["sess_low_in_levels"] = (
            act is not None and p["sess_low"] is not None
            and any(abs(L - p["sess_low"]) <= LEVEL_MATCH_TOL for L in act))


def c6_block(p: dict) -> "bool | None":
    if p["last5_dir"] is None:
        return None
    return p["last5_dir"] != ("up" if p["side"] == "C" else "down")


def c7_block(p: dict, x: float) -> "bool | None":
    if p["levels_active"] is None or p["spot"] is None:
        return None
    if p["side"] == "C":
        if not p["sess_high_in_levels"]:
            return False
        return p["sess_high"] - x <= p["spot"] <= p["sess_high"]
    if not p["sess_low_in_levels"]:
        return False
    return p["sess_low"] <= p["spot"] <= p["sess_low"] + x


def apply_predicate(rows: list[dict], pred) -> "tuple[list[dict], int]":
    blocked, abstain = [], 0
    for p in rows:
        v = pred(p)
        if v is None:
            abstain += 1
        elif v:
            blocked.append(p)
    return blocked, abstain


# ════════════════════════════════════════════════════════════ discrimination
def within_day_permutation(rows: list[dict], blocked: list[dict], seed: int = SEED,
                           draws: int = N_PERM) -> "float | None":
    """Hold each day's number of blocked positions FIXED, randomise WHICH positions inside
    that day are blocked. Tests 'did the rule pick the bad ENTRY' rather than 'did the rule
    sit out a bad DAY'. One-sided: P(random delta >= observed)."""
    if not blocked:
        return None
    by_day: dict = defaultdict(list)
    for p in rows:
        by_day[p["date_et"]].append(p["pnl"])
    k_by_day: dict = defaultdict(int)
    for b in blocked:
        k_by_day[b["date_et"]] += 1
    obs = -sum(b["pnl"] for b in blocked)
    rng = random.Random(seed)
    ge = 0
    for _ in range(draws):
        tot = 0.0
        for d, k in k_by_day.items():
            pool = by_day[d]
            tot += -sum(rng.sample(pool, k))
        if tot >= obs - 1e-9:
            ge += 1
    return round((ge + 1) / (draws + 1), 4)


def bh_adjust(pvals: dict) -> dict:
    """Benjamini-Hochberg adjusted q-values over the pre-registered 17-cell base."""
    items = [(k, v) for k, v in pvals.items() if v is not None]
    items.sort(key=lambda kv: kv[1])
    m = max(PARENT_STUDY_N_CELLS, len(items))
    out, prev = {}, 1.0
    for i in range(len(items) - 1, -1, -1):
        k, p = items[i]
        q = min(prev, p * m / (i + 1))
        out[k] = round(q, 4)
        prev = q
    return out


# ════════════════════════════════════════════════════════════ Wednesday tick exhibit
def wednesday_tick_exhibit(_m5: dict) -> dict:
    """Which guard fires WHEN on Wednesday's real tape. Behavioural only -- never P&L.

    Four regimes on the same bar sequence:
      LIVE_TODAY  -- fresh process every tick (module global resets)  == today's defect
      C3          -- once-per-day-per-setup, PERSISTED                == the defect fix
      C1_N3       -- cap 3 entries per contract
      C5_10MIN    -- per-setup 10-minute time cooldown (graveyard comparator)
    """
    import importlib

    import pandas as pd
    sys.path.insert(0, str(REPO / "backtest"))
    from lib.filters import BarContext  # noqa: PLC0415

    # Read the pinned 5m CSV DIRECTLY -- the watcher's session VWAP needs real VOLUME, and
    # load_5m() drops it. (Caught by a zero-fire run: a volume-less frame makes VWAP
    # degenerate and the detector never triggers. Silent-success trap, C7.)
    frame = pd.read_csv(BARS_5M)
    frame = frame[frame["timestamp_et"].astype(str).str.startswith(WED)].copy()
    frame["timestamp_et"] = pd.to_datetime(frame["timestamp_et"])
    tt = frame["timestamp_et"].dt.time
    frame = frame[(tt >= dt.time(9, 30)) & (tt < dt.time(16, 0))].reset_index(drop=True)
    assert len(frame) > 50, f"Wednesday 5m frame is {len(frame)} bars -- refusing to run"
    assert float(frame["volume"].sum()) > 0, "Wednesday 5m frame has ZERO volume"

    def ctx(i: int) -> "BarContext":
        sub = frame.iloc[: i + 1]
        last = sub.iloc[-1]
        return BarContext(bar_idx=i, timestamp_et=last["timestamp_et"].to_pydatetime(),
                          bar=last, prior_bars=sub, ribbon_now=None, ribbon_history=[],
                          vix_now=17.4, vix_prior=17.4, vol_baseline_20=0.0,
                          range_baseline_20=0.0, levels_active=[], multi_day_levels=[],
                          htf_15m_stack=None)

    def raw_fires(fresh_process: bool) -> list[str]:
        import lib.watchers.vwap_continuation_watcher as w  # noqa: PLC0415
        importlib.reload(w)
        fires = []
        for i in range(len(frame)):
            if fresh_process:
                importlib.reload(w)
            if w.detect_vwap_continuation_setup(ctx(i)) is not None:
                fires.append(frame.iloc[i]["timestamp_et"].strftime("%H:%M"))
        return fires

    live = raw_fires(True)
    same_proc = raw_fires(False)
    return {
        "_what_this_is": ("the vwap_continuation watcher run bar-by-bar over 2026-08-05's "
                          "real 5m RTH tape. CLOSED-BAR fires only; the live producer also "
                          "reads the in-progress bar, which is why the ledger shows 5 real "
                          "entries where a closed-bar replay shows fewer. Behavioural "
                          "exhibit, never a P&L source."),
        "LIVE_TODAY_fresh_process_each_tick": live,
        "C3_once_per_day_persisted": same_proc,
        "defect_confirmed": len(live) > len(same_proc),
        "actual_ledger_entries_per_risky_arm": 5,
        "regime_semantics_on_wednesday": {
            "LIVE_TODAY": "5 real fills per risky arm, 09:58/10:06/10:10/10:14/10:18",
            "C3_once_per_day_scoped": "1 fill per risky arm (09:58); 4 blocked",
            "C1_N3_cap_per_contract": "3 fills per risky arm (09:58/10:06/10:10); 2 blocked",
            "C5_10min_time_cooldown": ("the 5 entries are 4-8 min apart AND each closes "
                                       "before the next opens, so a 10-min post-CLOSE "
                                       "cooldown blocks a different, smaller subset -- "
                                       "reported for contrast only, family is GRAVEYARDED"),
        },
        "three_guards_are_not_the_same_guard": {
            "once_per_day_per_SETUP": "keys on (arm, date, setup). Blocks a 2nd vwap entry "
                                      "even on a DIFFERENT contract (Tuesday's 10:35 C765).",
            "cap_N_per_CONTRACT": "keys on (arm, date, symbol). Never blocks a move to a new "
                                  "strike, however many times you rotate.",
            "per_setup_TIME_cooldown": "keys on elapsed minutes. Blocks a fast re-entry and "
                                       "ALLOWS a slow one -- the opposite selectivity, and "
                                       "the reason it is graveyarded.",
        },
    }


# ════════════════════════════════════════════════════════════ main
def main() -> int:
    print("[lever4] loading populations ...")
    book = load_book()
    base = day_totals(book)
    dates = sorted(base)
    print(f"[lever4] BOOK: {len(book)} positions, {len(dates)} ET dates, "
          f"net {round(sum(base.values()), 2)}")
    replay, replay_meta = load_replay()
    rbase = day_totals(replay)
    print(f"[lever4] REPLAY: {len(replay)} trades, {len(rbase)} traded days, "
          f"net {round(sum(rbase.values()), 2)}")

    m5 = load_5m()
    m1 = fetch_1m(dates)
    lvl = levels_by_day()
    annotate_features(book, m5, m1, lvl)

    res: dict = {
        "_doc": __doc__.strip().splitlines()[0],
        "artifact": "LEVER-ENTRY-COUNT-2026-08-06",
        "lens": "LEVER 4 -- entry COUNT and entry ADMISSIBILITY",
        "prereg": {"path": "analysis/recommendations/lever-entry-count-prereg-2026-08-06.json",
                   "commit": "bf8dec8d", "frozen_before_runner": True},
        "populations": {
            "A_book": {"n_positions": len(book), "n_dates": len(dates),
                       "window": [dates[0], dates[-1]],
                       "net_usd": round(sum(base.values()), 2),
                       "day_totals": base,
                       "setup_label_coverage": {
                           "labelled": sum(1 for p in book if p["setup"]),
                           "unlabelled_ABSTAIN": sum(1 for p in book if not p["setup"])}},
            "B_replay": {"n_trades": len(replay), "n_traded_days": len(rbase),
                         "n_calendar_rth_days":
                             replay_meta["window"]["n_calendar_rth_days"],
                         "net_usd": round(sum(rbase.values()), 2)},
        },
        "cells": {},
    }

    # ---- Population B structural check: is it 1-entry-per-day by construction?
    per_day = defaultdict(int)
    for t in replay:
        per_day[t["date_et"]] += 1
    maxpd = max(per_day.values())
    same_contract = defaultdict(int)
    for t in replay:
        same_contract[(t["date_et"], t["symbol"])] += 1
    res["populationB_structure"] = {
        "max_trades_per_day": maxpd,
        "n_days_with_more_than_1": sum(1 for v in per_day.values() if v > 1),
        "max_trades_per_day_per_contract": max(same_contract.values()),
        "count_cap_is_a_NO_OP_on_B": max(same_contract.values()) <= 3 and maxpd <= 3,
    }

    def popB_for_cap(keyfn, n: int) -> "str | float":
        bl = cap_by_key(replay, keyfn, n)
        if not bl:
            return "NO_OP"
        return round(-sum(b["pnl"] for b in bl), 2)

    rows = []

    # ---- C1 wave cap
    for n in (1, 2, 3, 4, 5):
        bl = cap_by_key(book, lambda p: (p["arm"], p["symbol"], p["date_et"]), n)
        r = score(base, bl, book, f"C1-WAVE-CAP N={n}")
        gates(r, is_defect_fix=False,
              popB=popB_for_cap(lambda t: (t["date_et"], t["symbol"]), n))
        r["p_within_day"] = within_day_permutation(book, bl)
        rows.append(r)

    # ---- C2 day cap
    for n in (3, 4, 5, 6):
        bl = cap_by_key(book, lambda p: (p["arm"], p["date_et"]), n)
        r = score(base, bl, book, f"C2-DAY-CAP N={n}")
        gates(r, is_defect_fix=False, popB=popB_for_cap(lambda t: (t["date_et"],), n))
        r["p_within_day"] = within_day_permutation(book, bl)
        rows.append(r)

    # ---- C3 once-per-day SCOPED (the defect fix)
    bl = once_per_day_setup(book, VWAP)
    r = score(base, bl, book, "C3-ONCE-PER-DAY-SCOPED (vwap_continuation only)",
              n_abstain=sum(1 for p in book if p["setup"] is None))
    gates(r, is_defect_fix=True, popB="NO_OP")
    r["p_within_day"] = within_day_permutation(book, bl)
    r["blocked_detail"] = [{"arm": b["arm"], "date": b["date_et"],
                            "t": b["entry_ts_et"][11:19], "sym": b["symbol"],
                            "setup_ordinal": b["setup_ordinal"], "pnl": b["pnl"]}
                           for b in bl]
    rows.append(r)

    # ---- C4 once-per-day ALL setups
    bl = once_per_day_setup(book, None)
    r = score(base, bl, book, "C4-ONCE-PER-DAY-ALL-SETUPS",
              n_abstain=sum(1 for p in book if p["setup"] is None))
    gates(r, is_defect_fix=False, popB="NO_OP")
    r["p_within_day"] = within_day_permutation(book, bl)
    rows.append(r)

    # ---- C3b SAME-BAR COOLDOWN (fleet<->core PARITY). POST-HOC, disclosed.
    claimed: set = set()
    bl = []
    for p in sorted(book, key=lambda q: (q["date_et"], q["entry_ts_utc"])):
        if p.get("setup") is None or p.get("trigger_bar_et") is None:
            continue                                    # ABSTAIN, never block on a guess
        k = (p["arm"], p["date_et"], p["setup"], p["trigger_bar_et"])
        if k in claimed:
            bl.append(p)
        else:
            claimed.add(k)
    r = score(base, bl, book, "C3b-SAME-BAR-COOLDOWN (fleet<->core parity) [POST-HOC]",
              n_abstain=sum(1 for p in book
                            if p["setup"] is None or p["trigger_bar_et"] is None))
    gates(r, is_defect_fix=False, popB="NO_OP")
    r["p_within_day"] = within_day_permutation(book, bl)
    r["DISCLOSURE"] = (
        "POST-HOC -- NOT in the frozen prereg. Added after the pre-registered C3 failed the "
        "Tuesday hard gate, because the failure exposed that once-per-day is not the only "
        "way to close the fleet/core parity gap. It is the NARROWEST possible parity fix: "
        "it ports the CORE lane's already-shipped exit_actuator.same_bar_cooldown_active "
        "guard (2026-07-20, EXTRA-SIGNAL-CHURN-COOLDOWN) to the fleet lane verbatim. It has "
        "NO tunable knob -- the trigger bar must simply ADVANCE. Because it is post-hoc its "
        "verdict is CAPPED at PREREG in this lane no matter what the dollars say.")
    r["mechanism"] = (
        "Blocks a repeat entry by the same arm in the same setup on the SAME last-closed 5m "
        "trigger bar. On 2026-08-05 that is exactly ONE of the five 776C entries per arm "
        "(10:14, whose trigger bar 10:05 was already claimed by the 10:10 entry). On "
        "2026-08-04 it is exactly ONE (risky-3 09:54, trigger bar 09:45 already claimed by "
        "09:50) -- and it PRESERVES the 09:57 +$524 rescue, whose 09:50 trigger bar is new.")
    if r["verdict"] == "SHIP":
        r["verdict"] = "PREREG"
    rows.append(r)

    # ---- C5 time cooldown (GRAVEYARD comparator)
    for m in (5, 10, 15, 30):
        bl = time_cooldown(book, m)
        r = score(base, bl, book, f"C5-TIME-COOLDOWN {m}min [GRAVEYARDED FAMILY]")
        gates(r, is_defect_fix=False, popB="NO_OP")
        r["verdict"] = "GRAVEYARD_COLLISION"
        r["p_within_day"] = within_day_permutation(book, bl)
        rows.append(r)

    # ---- Population B feature annotation (pinned lineage that produced the replay)
    b5 = load_5m(REPO / "backtest" / "data" / "spy_5m_2025-01-01_2026-07-22.csv")
    for t in replay:
        d, cut = t["date_et"], t["entry_dt"]
        closed5 = [b for b in b5.get(d, [])
                   if dt.time(9, 30) <= b["t"].time() < dt.time(16, 0)
                   and b["t"] + dt.timedelta(minutes=5) <= cut]
        t["last5_dir"] = None
        if closed5:
            b = closed5[-1]
            t["last5_dir"] = "up" if b["c"] > b["o"] else ("down" if b["c"] < b["o"] else "flat")
        # session extreme so far, on CLOSED 5m bars (B has no 1m lineage and no
        # levels_active -- this is the labelled PROXY, never the C7 rule itself)
        t["spot"] = closed5[-1]["c"] if closed5 else None
        t["sess_high"] = max((b["h"] for b in closed5), default=None)
        t["sess_low"] = min((b["l"] for b in closed5), default=None)

    def popB_predicate(pred) -> "str | float":
        bl_, ab_ = apply_predicate(replay, pred)
        if not bl_:
            return "NO_OP"
        return round(-sum(x["pnl"] for x in bl_), 2)

    # ---- C6 V-d1
    bl, ab = apply_predicate(book, c6_block)
    r = score(base, bl, book, "C6-VD1 last closed 5m bar agrees", n_abstain=ab)
    blB, abB = apply_predicate(replay, c6_block)
    rB = score(rbase, blB, replay, "C6-VD1 on POPULATION B", n_abstain=abB)
    gates(r, is_defect_fix=False, popB=rB["delta_total"])
    r["populationB_detail"] = {
        "n_trades": len(replay), "n_blocked": rB["n_blocked"], "n_abstain": abB,
        "delta_total_usd": rB["delta_total"],
        "n_days_harmed": rB["n_days_harmed"], "n_days_helped": rB["n_days_helped"],
        "blocked_winner_usd": rB["blocked_winner_usd"],
        "blocked_loser_usd": rB["blocked_loser_usd"],
        "blocked_win_rate_pct": rB["blocked_win_rate_pct"],
        "p_within_day": within_day_permutation(replay, blB),
        "lineage": "backtest/data/spy_5m_2025-01-01_2026-07-22.csv (the pinned 5m lineage "
                   "that produced the replay itself)",
    }
    r["p_within_day"] = within_day_permutation(book, bl)
    r["forward_2026_08_06_first_shadow_session"] = {
        "n_blocked": sum(1 for b in bl if b["date_et"] == THU),
        "delta_usd": round(-sum(b["pnl"] for b in bl if b["date_et"] == THU), 2),
        "note": ("2026-08-06 is session 1 of the 10-session shadow window frozen in "
                 "analysis/recommendations/entry-structure-forward-prereg-2026-08-06.json. "
                 "Reported SEPARATELY; it is one session and settles nothing."),
    }
    r["in_sample_25day_ex_thursday"] = {
        "n_blocked": sum(1 for b in bl if b["date_et"] != THU),
        "delta_usd": round(-sum(b["pnl"] for b in bl if b["date_et"] != THU), 2),
    }
    rows.append(r)

    # ---- C7 session-high-in-levels_active
    cov = sorted(set(lvl) & set(dates))

    def c7_proxy(t: dict, x: float) -> "bool | None":
        """POPULATION-B PROXY ONLY. Population B has no levels_active log, so the
        'is the extreme on the engine's own level list' conjunct CANNOT be evaluated. This
        drops that conjunct and tests raw session-extreme proximity on CLOSED 5m bars. It is
        a STRICTLY LOOSER rule than C7 and is labelled as a proxy everywhere it appears."""
        if t["spot"] is None:
            return None
        if t.get("side") == "C":
            return t["sess_high"] - x <= t["spot"] <= t["sess_high"]
        return t["sess_low"] <= t["spot"] <= t["sess_low"] + x

    for x in (0.25, 0.50, 0.75, 1.00):
        bl, ab = apply_predicate(book, lambda p, x=x: c7_block(p, x))
        r = score(base, bl, book, f"C7-SESSION-HIGH-IN-LEVELS X=${x:.2f}",
                  n_abstain=ab, coverage_days=cov)
        blB, abB = apply_predicate(replay, lambda t, x=x: c7_proxy(t, x))
        rB = score(rbase, blB, replay, f"C7-PROXY on B X=${x:.2f}", n_abstain=abB)
        gates(r, is_defect_fix=False, popB="PROXY_ONLY")
        r["gate_detail"]["G8_populationB"] = False
        r["p_within_day"] = within_day_permutation(book, bl)
        r["levels_coverage_dates"] = cov
        r["levels_coverage_disclosure"] = (
            f"levels_active is only logged from {cov[0] if cov else 'n/a'}; "
            f"{ab} of {len(book)} positions ABSTAIN. No C7 cell may be called SHIP.")
        r["populationB_PROXY_no_levels_conjunct"] = {
            "n_blocked": rB["n_blocked"], "delta_total_usd": rB["delta_total"],
            "n_days_harmed": rB["n_days_harmed"], "n_days_helped": rB["n_days_helped"],
            "blocked_win_rate_pct": rB["blocked_win_rate_pct"],
            "LABEL": "PROXY -- levels_active conjunct DROPPED (B has no such log). Strictly "
                     "looser than C7. Never a validation of C7, only of the family.",
        }
        r["wednesday_blocked_share_of_day_positions"] = round(
            100.0 * sum(1 for b in bl if b["date_et"] == WED)
            / max(1, sum(1 for p in book if p["date_et"] == WED)), 1)
        rows.append(r)

    # ---- COMBINATION (POST-HOC, disclosed): the two cells that clear the Tuesday hard gate
    bl_cap = cap_by_key(book, lambda p: (p["arm"], p["symbol"], p["date_et"]), 3)
    bl_vd1, ab_vd1 = apply_predicate(book, c6_block)
    union = {id(x): x for x in (bl_cap + bl_vd1)}.values()
    r = score(base, list(union), book, "COMB-CAP3+VD1 [POST-HOC, disclosed]",
              n_abstain=ab_vd1)
    gates(r, is_defect_fix=False, popB="NOT_JOINTLY_MEASURABLE_ON_B")
    r["gate_detail"]["G8_populationB"] = False
    r["p_within_day"] = within_day_permutation(book, list(union))
    r["DISCLOSURE"] = ("POST-HOC union of the only two pre-registered cells that clear the "
                       "Tuesday hard gate. NOT pre-registered as a combination. Reported so "
                       "the ceiling of this lane is visible; it cannot ship off this run.")
    rows.append(r)

    res["cells"] = rows

    # ---- multiplicity correction over every cell measured here + the parent 17
    praw = {r["cell"]: r.get("p_within_day") for r in rows}
    q = bh_adjust(praw)
    for r in rows:
        p = r.get("p_within_day")
        r["p_bonferroni_x17"] = (round(min(1.0, p * PARENT_STUDY_N_CELLS), 4)
                                 if p is not None else None)
        r["q_benjamini_hochberg"] = q.get(r["cell"])

    # ---- ordinal decomposition, broker truth
    def ordinal_table(rows_in: list[dict], field: str) -> dict:
        agg: dict = defaultdict(lambda: {"n": 0, "pnl": 0.0, "wins": 0})
        for p in rows_in:
            k = min(p[field], 5)
            agg[k]["n"] += 1
            agg[k]["pnl"] += p["pnl"]
            agg[k]["wins"] += 1 if p["pnl"] > 0 else 0
        return {("5+" if k == 5 else str(k)):
                {"n": v["n"], "pnl": round(v["pnl"], 2),
                 "win_rate_pct": round(100.0 * v["wins"] / v["n"], 1)}
                for k, v in sorted(agg.items())}

    res["ordinal_decomposition_broker_truth"] = {
        "per_contract_wave_ordinal": ordinal_table(book, "wave_ordinal"),
        "per_arm_day_ordinal": ordinal_table(book, "day_ordinal"),
        "per_setup_ordinal_labelled_only":
            ordinal_table([p for p in book if p["setup"]], "setup_ordinal"),
    }

    # ---- vwap_continuation family, the setup whose contract is being restored
    vw = [p for p in book if p["setup"] == VWAP]
    res["vwap_continuation_family"] = {
        "n_positions": len(vw),
        "dates": sorted({p["date_et"] for p in vw}),
        "net_usd": round(sum(p["pnl"] for p in vw), 2),
        "first_entry_of_day_only": {
            "n": sum(1 for p in vw if p["setup_ordinal"] == 1),
            "pnl": round(sum(p["pnl"] for p in vw if p["setup_ordinal"] == 1), 2)},
        "entries_2_plus": {
            "n": sum(1 for p in vw if p["setup_ordinal"] > 1),
            "pnl": round(sum(p["pnl"] for p in vw if p["setup_ordinal"] > 1), 2)},
        "per_position": [{"arm": p["arm"], "date": p["date_et"],
                          "t": p["entry_ts_et"][11:19], "sym": p["symbol"],
                          "ord": p["setup_ordinal"], "qty": int(p["entry_qty"]),
                          "pnl": p["pnl"]} for p in vw],
    }

    # ---- Tuesday hard-gate exhibit (which positions any count cap would clip)
    tue = [p for p in book if p["date_et"] == TUE]
    res["tuesday_hard_gate_exhibit"] = {
        "day_total": base.get(TUE),
        "money_from_2nd_plus_wave_entries":
            round(sum(p["pnl"] for p in tue if p["wave_ordinal"] >= 2), 2),
        "money_from_2nd_plus_setup_entries":
            round(sum(p["pnl"] for p in tue if p["setup"] and p["setup_ordinal"] >= 2), 2),
        "positions": [{"arm": p["arm"], "t": p["entry_ts_et"][11:19], "sym": p["symbol"],
                       "setup": p["setup"], "wave_ord": p["wave_ordinal"],
                       "day_ord": p["day_ordinal"], "setup_ord": p["setup_ordinal"],
                       "pnl": p["pnl"]} for p in tue],
    }

    res["wednesday_tick_exhibit"] = wednesday_tick_exhibit(m5)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")

    hdr = ["cell", "n_blocked", "delta_total", "delta_tue_2026_08_04",
           "delta_wed_2026_08_05", "delta_thu_2026_08_06", "delta_ex_wed",
           "n_days_harmed", "p_within_day", "gates", "verdict"]
    print()
    print(" | ".join(f"{h:<38}" if h == "cell" else f"{h:>10}" for h in hdr))
    for r in rows:
        print(" | ".join((f"{r['cell']:<38}" if h == "cell" else f"{str(r.get(h)):>10}")
                         for h in hdr))
    print(f"\nwrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
