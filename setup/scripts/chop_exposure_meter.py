"""chop_exposure_meter.py -- THE CHOP EXPOSURE METER: "did we trade chop today?"
as a glance, not a question. MEASUREMENT ONLY -- never blocks, never touches params,
never places or cancels anything.

Contract frozen in analysis/recommendations/chop-defense-prereg-2026-08-06.json
(commit 5737488a, BEFORE this file existed). Nightly line reports, for today's
real engine entries (fills-ledger.jsonl, attribution=='engine', SPY options):

  n_entries        real broker-fill positions opened today
  ord>=4           entries at wave ordinal >= 4 on the same (arm, contract) --
                   the entries CAP-3 would have blocked (its forward-clock recorder)
  against V-d1     last fully-CLOSED 5m bar before entry disagrees with the trade
                   side (flat counts as disagree -- identical semantics to
                   lever_entry_count_2026_08_06.c6_block)
  zero-structure   entries before ANY completed BOS/CHoCH on the day's closed 5m
                   RTH bars (crypto.lib.market_structure walk, window=2, per-day).
                   CONTEXT, NOT AN ALARM: the admissibility battery showed blocking
                   these costs Tuesday -$2,091 -- early gap entries are always
                   zero-structure. The meter measures exposure; it does not judge.
  rr<0.70          entries where realized intraday range at entry < 0.70x the
                   20-day median at the same time-of-day cutoff (B-RR-070, the one
                   fresh cell that cleared all 8 gates on BOTH populations --
                   post-battery ADDITIVE measurement column, disclosed in the
                   CHOP-DEFENSE report; PREREG forward clock, not a lever)
  consec-loss runs max consecutive-loser run per arm (CONSEC4's recorder) and per
                   (arm, contract) (family-A context)
  fleet realized   pooled realized intraday P&L path across ALL arms: day total,
                   intraday floor + time, and would a -$600 REALIZED breaker have
                   latched (BRK600's forward-evidence recorder -- the surface the
                   live equity-based daily_loss_guard.py does NOT have)

Artifacts: automation/state/chop-exposure-{date}.json + chop-exposure-last.json
(the -last snapshot is what firm_brief renders, same pattern as prospector/twin).

FAIL-OPEN per prereg: if the 5m bar fetch fails, bar-dependent columns render n/a
with bars_degraded=true; ledger-derived columns still report. Errors are LOUD in
the artifact (C7: silent success is failure), never raised past main().

CLI: backtest/.venv/Scripts/python.exe setup/scripts/chop_exposure_meter.py
     [--date YYYY-MM-DD] [--no-write]
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3) -- same block as firm_brief.py ===
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "chop-meter.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "chop-meter.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import argparse
import datetime as dt
import json
import statistics
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "setup" / "scripts", REPO / "backtest" / "tools",
           REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from et_clock import et_now  # noqa: E402

STATE = REPO / "automation" / "state"
LEDGER = STATE / "fills-ledger.jsonl"

STRUCT_WINDOW = 2         # frozen (prereg): DEFAULT_WINDOW fractal, per-day, 5m RTH
RR_THRESHOLD = 0.70       # frozen: B-RR-070, the only 8/8-gate fresh cell
RR_PRIOR_DAYS = 20
RR_MIN_PRIOR_DAYS = 15
BRK_THRESHOLD = -600.0    # frozen (prereg): BRK600, realized basis, latching
ORD_ALARM = 4             # frozen: CAP-3 recorder counts ordinal >= 4
FETCH_CAL_DAYS = 70       # calendar lookback for the single 5Min request (~48 tds)


# ---------------------------------------------------------------------------
# ledger -> positions (reuse the book's one authority; LOUD on failure, C7)
# ---------------------------------------------------------------------------

def _load_positions(day: str, ledger_path: Path) -> "tuple[list[dict], str | None]":
    """Engine option positions ENTERED on `day`, chronological. Reuses
    exit_shape_parity_study.reconstruct_positions -- the same authority the
    admissibility battery and every KEEP-LOSSES lane used. Returns (positions,
    error). Positions carry entry_dt/exit legs in ET."""
    try:
        from exit_shape_parity_study import reconstruct_positions
    except Exception as exc:  # noqa: BLE001 -- report LOUD, never silently empty
        return [], f"reconstruct_positions import failed: {exc}"
    fills = []
    try:
        for ln in ledger_path.read_text(encoding="utf-8", errors="replace").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if (r.get("attribution") == "engine" and r.get("is_option")
                    and not r.get("is_crypto")):
                fills.append(r)
    except OSError as exc:
        return [], f"fills ledger unreadable: {exc}"
    if not fills:
        return [], None
    ts_et = {(f["arm"], f["symbol"], f["ts_utc"]): f.get("ts_et", "") for f in fills}
    pos = [p for p in reconstruct_positions(fills) if p["exit_fills"]]

    def _parse(s: str) -> "dt.datetime | None":
        try:
            return dt.datetime.fromisoformat(s).replace(tzinfo=None)
        except (TypeError, ValueError):
            return None

    out = []
    for p in pos:
        if p.get("date_et") != day:
            continue
        p["entry_ts_et"] = ts_et.get((p["arm"], p["symbol"], p["entry_ts_utc"]), "")
        p["entry_dt"] = _parse(p["entry_ts_et"])
        p["pnl"] = round(p["actual_exit_pnl"], 2)
        p["side"] = "C" if "C00" in p["symbol"] else "P"
        p["exit_legs"] = []
        for ef in p["exit_fills"]:
            ts = _parse(ef.get("ts_et", ""))
            if ts is not None:
                p["exit_legs"].append(
                    {"t": ts,
                     "pnl": round((ef["price"] - p["entry_price"]) * ef["qty"] * 100, 2)})
        out.append(p)
    out.sort(key=lambda p: (p["entry_ts_et"], p["arm"]))
    wave: dict = defaultdict(int)
    for p in out:
        wave[(p["arm"], p["symbol"])] += 1
        p["wave_ordinal"] = wave[(p["arm"], p["symbol"])]
    return out, None


# ---------------------------------------------------------------------------
# 5m bars (single SIP request, probed live creds -- L234: never a hardcoded arm)
# ---------------------------------------------------------------------------

def _probe_live_creds() -> "dict | None":
    try:
        import fleet_broker as fb
        creds_all = fb.load_creds()
        for arm in sorted(creds_all):
            c = creds_all[arm]
            acct = fb.get_account(c)
            if isinstance(acct, dict) and acct and not acct.get("_error"):
                return c
    except Exception:  # noqa: BLE001 -- caller reports bars_degraded, never crashes
        return None
    return None


def fetch_5m_window(day: str, *, now_utc: "dt.datetime | None" = None) -> "dict | None":
    """{et_date: [{t,o,h,l,c}, ...]} for [day - FETCH_CAL_DAYS, day], 5Min SIP,
    end clamped to now-16min (Alpaca Basic SIP delay). None on any failure."""
    creds = _probe_live_creds()
    if creds is None:
        return None
    now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
    start = (dt.date.fromisoformat(day) - dt.timedelta(days=FETCH_CAL_DAYS)).isoformat()
    end_dt = min(dt.datetime.fromisoformat(f"{day}T23:59:00+00:00"),
                 now_utc - dt.timedelta(minutes=16))
    base_url = ("https://data.alpaca.markets/v2/stocks/SPY/bars"
                f"?timeframe=5Min&start={start}T08:00:00Z"
                f"&end={end_dt:%Y-%m-%dT%H:%M:%SZ}"
                "&limit=10000&feed=sip&adjustment=raw")
    bars: list = []
    page_token = None
    for _page in range(12):          # the API pages regardless of `limit` -- follow it
        url = base_url + (f"&page_token={page_token}" if page_token else "")
        req = urllib.request.Request(url, headers={
            "APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]})
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                ConnectionError, ValueError, OSError):
            return None
        bars.extend(data.get("bars") or [])
        page_token = data.get("next_page_token")
        if not page_token:
            break
    else:
        return None                  # never-ending pagination -> refuse a partial tape
    if not bars:
        return None
    # runtime ET offset from the DST-aware clock -- never a hardcoded -4 (TZ scar)
    off_h = round((et_now() - dt.datetime.now(dt.timezone.utc).replace(tzinfo=None))
                  .total_seconds() / 3600.0)
    out: dict = defaultdict(list)
    for b in bars:
        try:
            ts = dt.datetime.fromisoformat(str(b["t"]).replace("Z", "+00:00")) \
                + dt.timedelta(hours=off_h)
            ts = ts.replace(tzinfo=None)
            out[ts.date().isoformat()].append(
                {"t": ts, "o": float(b["o"]), "h": float(b["h"]),
                 "l": float(b["l"]), "c": float(b["c"])})
        except (KeyError, TypeError, ValueError):
            continue
    for d in out:
        out[d].sort(key=lambda x: x["t"])
    return dict(out)


# ---------------------------------------------------------------------------
# features (definitions MUST stay parity with the admissibility battery --
# guard: test_chop_exposure_meter.py::test_structure_parity_with_battery)
# ---------------------------------------------------------------------------

def day_structure_events(bars5: list[dict]) -> list[dict]:
    """BOS/CHoCH events for one day's 5m bars; break_close_et = when knowable.
    Same walk as chop_admissibility_2026_08_06.day_structure_events."""
    from crypto.lib.bar import Bar
    from crypto.lib.market_structure import walk_structure
    from crypto.lib.trendlines import find_swing_points
    rth = [b for b in bars5 if dt.time(9, 30) <= b["t"].time() < dt.time(16, 0)]
    if len(rth) < 2 * STRUCT_WINDOW + 1:
        return []
    utc = dt.timezone.utc
    bars = [Bar(open_time=b["t"].replace(tzinfo=utc), open=b["o"], high=b["h"],
                low=b["l"], close=b["c"], volume=0.0, granularity_seconds=300,
                source="spy5m") for b in rth]
    swings = find_swing_points(bars, window=STRUCT_WINDOW, inclusive_right=True)
    _trend, events = walk_structure(bars, swings, STRUCT_WINDOW)
    return [{"kind": e.kind, "direction": e.direction,
             "break_close_et": rth[e.break_index]["t"] + dt.timedelta(minutes=5)}
            for e in events]


def last_closed_5m_dir(bars5: list[dict], cut: dt.datetime) -> "str | None":
    """Direction of the last FULLY CLOSED 5m RTH bar before `cut` (c6 semantics)."""
    closed = [b for b in bars5
              if dt.time(9, 30) <= b["t"].time() < dt.time(16, 0)
              and b["t"] + dt.timedelta(minutes=5) <= cut]
    if not closed:
        return None
    b = closed[-1]
    return "up" if b["c"] > b["o"] else ("down" if b["c"] < b["o"] else "flat")


def _cutoff_range(bars5: list[dict], cutoff_t: dt.time) -> "float | None":
    xs = [b for b in bars5
          if dt.time(9, 30) <= b["t"].time() < dt.time(16, 0)
          and (b["t"] + dt.timedelta(minutes=5)).time() <= cutoff_t]
    if not xs:
        return None
    return max(b["h"] for b in xs) - min(b["l"] for b in xs)


def rr_at_entry(m5: dict, day: str, cut: dt.datetime) -> "float | None":
    """Realized-range ratio vs the prior-20-trading-day median at the same
    time-of-day cutoff. None = ABSTAIN (insufficient history / no closed bar)."""
    if day not in m5:
        return None
    today_rng = _cutoff_range(m5[day], cut.time())
    if today_rng is None:
        return None
    priors = [x for x in sorted(m5) if x < day][-RR_PRIOR_DAYS:]
    if len(priors) < RR_MIN_PRIOR_DAYS:
        return None
    vals = [r for x in priors if (r := _cutoff_range(m5[x], cut.time())) is not None]
    if len(vals) < RR_MIN_PRIOR_DAYS:
        return None
    med = statistics.median(vals)
    return round(today_rng / med, 4) if med > 0 else None


# ---------------------------------------------------------------------------
# the meter
# ---------------------------------------------------------------------------

def compute_meter(day: "str | None" = None, *, ledger_path: "Path | None" = None,
                  bars_by_day: "dict | None" = None, fetch: bool = True,
                  now: "dt.datetime | None" = None) -> dict:
    """All inputs injectable for tests. Never raises: errors land in the artifact."""
    now = now or et_now()
    day = day or now.strftime("%Y-%m-%d")
    positions, err = _load_positions(day, ledger_path or LEDGER)

    m5 = bars_by_day
    if m5 is None and fetch:
        m5 = fetch_5m_window(day)
    bars_degraded = m5 is None or day not in (m5 or {})

    events = day_structure_events(m5[day]) if not bars_degraded else []

    per_entry = []
    n_ord4 = n_vd1 = n_zero_struct = n_rr = 0
    vd1_known = struct_known = rr_known = 0
    for p in positions:
        cut = p["entry_dt"]
        row = {"arm": p["arm"], "t": p["entry_ts_et"][11:19], "sym": p["symbol"],
               "side": p["side"], "ord": p["wave_ordinal"], "pnl": p["pnl"],
               "against_vd1": None, "zero_structure": None, "rr": None}
        if p["wave_ordinal"] >= ORD_ALARM:
            n_ord4 += 1
        if not bars_degraded and cut is not None:
            d5 = last_closed_5m_dir(m5[day], cut)
            if d5 is not None:
                vd1_known += 1
                row["against_vd1"] = d5 != ("up" if p["side"] == "C" else "down")
                n_vd1 += int(row["against_vd1"])
            done = [e for e in events if e["break_close_et"] <= cut]
            struct_known += 1
            row["zero_structure"] = not done
            n_zero_struct += int(row["zero_structure"])
            rr = rr_at_entry(m5, day, cut)
            if rr is not None:
                rr_known += 1
                row["rr"] = rr
                n_rr += int(rr < RR_THRESHOLD)
        per_entry.append(row)

    # consecutive-loser runs (exit-ordered) + fleet pooled realized path
    exits = []
    for p in positions:
        for leg in p["exit_legs"]:
            exits.append({"t": leg["t"], "pnl": leg["pnl"], "arm": p["arm"],
                          "sym": p["symbol"], "pos_id": id(p)})
    exits.sort(key=lambda e: e["t"])

    # per-position outcome order (position-level, at its LAST exit leg)
    pos_close = sorted(
        ((max(leg["t"] for leg in p["exit_legs"]), p) for p in positions if p["exit_legs"]),
        key=lambda x: x[0])
    run_arm: dict = defaultdict(int)
    max_run_arm: dict = defaultdict(int)
    run_ct: dict = defaultdict(int)
    max_run_ct = 0
    for _t, p in pos_close:
        ka, kc = p["arm"], (p["arm"], p["symbol"])
        if p["pnl"] < 0:
            run_arm[ka] += 1
            run_ct[kc] += 1
            max_run_arm[ka] = max(max_run_arm[ka], run_arm[ka])
            max_run_ct = max(max_run_ct, run_ct[kc])
        else:
            run_arm[ka] = 0
            run_ct[kc] = 0

    cum = 0.0
    floor = 0.0
    floor_t = None
    latch_t = None
    for e in exits:
        cum += e["pnl"]
        if cum < floor:
            floor = cum
            floor_t = e["t"]
        if latch_t is None and cum <= BRK_THRESHOLD:
            latch_t = e["t"]
    day_total = round(sum(p["pnl"] for p in positions), 2)

    out = {
        "date": day,
        "generated_at_et": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "meter_version": 1,
        "prereg": "analysis/recommendations/chop-defense-prereg-2026-08-06.json @ 5737488a",
        "n_entries": len(positions),
        "n_ord4plus": n_ord4,
        "n_against_vd1": (n_vd1 if not bars_degraded else None),
        "n_zero_structure": (n_zero_struct if not bars_degraded else None),
        "n_rr_below_070": (n_rr if not bars_degraded else None),
        "coverage": {"vd1_known": vd1_known, "struct_known": struct_known,
                     "rr_known": rr_known},
        "bars_degraded": bars_degraded,
        "max_consec_loss_per_arm": dict(max_run_arm),
        "max_consec_loss_same_contract": max_run_ct,
        "fleet_realized": {
            "day_total": day_total,
            "intraday_floor": round(floor, 2),
            "floor_time_et": floor_t.strftime("%H:%M:%S") if floor_t else None,
            "would_trip_600": latch_t is not None,
            "latch_time_et": latch_t.strftime("%H:%M:%S") if latch_t else None,
        },
        "per_entry": per_entry,
        "error": err,
    }
    return out


def render_line(m: dict) -> str:
    """The one nightly line (also what firm_brief renders from -last.json)."""
    if m.get("error"):
        return f"CHOP METER {m['date']}: ERROR -- {m['error']}"
    if m["n_entries"] == 0:
        return f"CHOP METER {m['date']}: no engine entries."
    def _n(v):  # noqa: E306
        return "n/a" if v is None else str(v)
    fr = m["fleet_realized"]
    trip = (f"YES @ {fr['latch_time_et']}" if fr["would_trip_600"] else "no")
    runs = m.get("max_consec_loss_per_arm") or {}
    worst_run = max(runs.values(), default=0)
    line = (f"CHOP METER {m['date']}: {m['n_entries']} entries | ord>={ORD_ALARM}: "
            f"{m['n_ord4plus']} | against V-d1: {_n(m['n_against_vd1'])} | "
            f"zero-structure: {_n(m['n_zero_structure'])} | rr<{RR_THRESHOLD:.2f}: "
            f"{_n(m['n_rr_below_070'])} | worst consec-loss run: {worst_run} "
            f"(contract {m['max_consec_loss_same_contract']}) | fleet realized: "
            f"day {fr['day_total']:+.0f}, floor {fr['intraday_floor']:+.0f}"
            + (f" @ {fr['floor_time_et']}" if fr["floor_time_et"] else "")
            + f", BRK600 would-trip: {trip}")
    if m.get("bars_degraded"):
        line += " | WARN bars n/a (fetch failed) -- V-d1/structure/rr not measured"
    return line


def write_artifacts(m: dict, state_dir: "Path | None" = None) -> "list[Path]":
    state_dir = state_dir or STATE
    out = []
    for name in (f"chop-exposure-{m['date']}.json", "chop-exposure-last.json"):
        p = state_dir / name
        try:
            p.write_text(json.dumps(m, indent=1, default=str), encoding="utf-8")
            out.append(p)
        except OSError as exc:
            print(f"[chop-meter] WARN artifact write failed {p}: {exc}", file=sys.stderr)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Chop exposure meter (measurement only)")
    ap.add_argument("--date", default=None)
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()
    m = compute_meter(args.date)
    print(render_line(m))
    if not args.no_write:
        for p in write_artifacts(m):
            print(f"[chop-meter] wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
