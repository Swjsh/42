"""j_drawn_lines_score.py -- nightly TOUCH/BREAK scoring of J's own drawn trend lines
(TRENDLINE-J-DRAWN-LINES-LEDGER, 2026-09-03, queue HIGH).

Reads `analysis/recommendations/j-drawn-lines-ledger.jsonl` (`kind: "line"` rows, written
by `j_drawn_lines_capture.py`) and scores each `rising`-shaped line against cached SPY 1m
bars (`backtest/data/spy_sip_cache`), never re-fetched. Full rule:
analysis/recommendations/prereg-trendline-j-drawn-lines-2026-09-03.md section 3 -- this
module implements it, does not restate it.

NO LOOK-AHEAD (the load-bearing rule): a line is scored only from the first cached session
strictly AFTER its `first_seen_date_et`. A line captured tonight is scored starting
tomorrow -- never against the bars that led to it being drawn/captured in the first place.

WHY REAL-TIME LINE VALUE, NOT BAR-INDEX (unlike the T5 sibling
`trendline_human_anchor_shadow.py`): a drawn trend line persists across many calendar days
(TradingView renders it as a real-time ray, not a within-session structure), so this module
evaluates `line(t) = a_price + rate*(t - a_time)` continuously across every forward session,
not per-session bar indices.

SHADOW ONLY, FOREVER: no broker call, no import of filters.py/trendline_detector.py, never
wired to any live or paper trigger. This instrument's own decision rule caps out at
"proceeds to a real ratification pass," itself a separate, later, explicitly-authorized
step this file does not perform -- and even that is gated to not read a verdict before
2026-10-30.

COST: $0. Pure Python stdlib, reads only cached JSON.

Outputs:
  analysis/recommendations/j-drawn-lines-ledger.jsonl    appends `kind: "event"` rows
  analysis/recommendations/j-drawn-lines-summary.json    per-timeframe aggregate + decision
"""
from __future__ import annotations

import datetime as dt
import json
import random
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

CACHE_DIR = REPO / "backtest" / "data" / "spy_sip_cache"
OUT_DIR = REPO / "analysis" / "recommendations"
LEDGER = OUT_DIR / "j-drawn-lines-ledger.jsonl"
SUMMARY = OUT_DIR / "j-drawn-lines-summary.json"
PREREG_REL = "analysis/recommendations/prereg-trendline-j-drawn-lines-2026-09-03.md"

IN_SAMPLE_CUTOFF = "2026-09-03"
HARD_DATE_GATE = "2026-10-30"

TOL = 0.20                          # 5m tolerance, prereg section 3 (matches T5 5m tol)
HORIZON_BARS = {15: 3, 30: 6, 60: 12}
HORIZONS = (15, 30, 60)
B_BOOT = 1000
SEED = 20260903
BAR_MIN_LINES_FORWARD = 20
BAR_MIN_SESSIONS_FORWARD = 15
FALSIFIER_TOP3_CONCENTRATION = 0.60


# ------------------------------------------------------------------------------------------
# ledger I/O
# ------------------------------------------------------------------------------------------
def _read_ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _stamp_now_et() -> str:
    try:
        from et_clock import et_now  # noqa: PLC0415
        return et_now().isoformat()
    except Exception:  # noqa: BLE001
        return dt.datetime.now(dt.timezone.utc).isoformat()


def _scored_event_keys(rows: list[dict]) -> set[tuple[str, str]]:
    """(entity_id, event_type-uniqueness key) already scored -- touches keyed by bar time,
    breaks are at most one per line so keyed by entity_id alone."""
    keys = set()
    for r in rows:
        if r.get("kind") != "event":
            continue
        if r["event_type"] == "break":
            keys.add((r["entity_id"], "break"))
        else:
            keys.add((r["entity_id"], f"touch:{r['bar_t']}"))
    return keys


# ------------------------------------------------------------------------------------------
# bars -- 5m_premkt convention (full day from 04:00 ET), identical aggregation to the T5
# sibling (verified there against cached 5m file, 146/148 exact match)
# ------------------------------------------------------------------------------------------
def list_sessions() -> list[str]:
    dates = []
    for f in sorted(CACHE_DIR.glob("spy_1m_*.json")):
        d = f.stem.replace("spy_1m_", "")
        if (CACHE_DIR / f"spy_5m_{d}.json").exists():
            dates.append(d)
    return dates


def load_bars(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["bars"]


def parse_t(t: str) -> dt.datetime:
    return dt.datetime.fromisoformat(t)


def to_5m_premkt(bars_5m: list[dict]) -> list[dict]:
    out = []
    for b in bars_5m:
        ts = parse_t(b["t"])
        out.append({"t_dt": ts, "t_unix": int(ts.timestamp()), "o": b["o"], "h": b["h"],
                    "l": b["l"], "c": b["c"], "v": b.get("v", 0.0)})
    out.sort(key=lambda x: x["t_unix"])
    return out


def _session_bars_cache() -> dict[str, list[dict]]:
    cache: dict[str, list[dict]] = {}
    for date in list_sessions():
        try:
            bars_5m = load_bars(CACHE_DIR / f"spy_5m_{date}.json")
        except (OSError, json.JSONDecodeError, KeyError):
            continue
        cache[date] = to_5m_premkt(bars_5m)
    return cache


# ------------------------------------------------------------------------------------------
# per-line scoring -- real-time-based line value, no look-ahead
# ------------------------------------------------------------------------------------------
def line_value(a_time: int, a_price: float, b_time: int, b_price: float, t: int) -> float:
    rate = (b_price - a_price) / (b_time - a_time)
    return a_price + rate * (t - a_time)


def _outcome(bd: list[dict], j: int, horizon: int) -> dict | None:
    n = len(bd)
    N = HORIZON_BARS[horizon]
    if j + N >= n:
        return None
    c0 = bd[j]["c"]
    cN = bd[j + N]["c"]
    window = bd[j + 1: j + N + 1]
    c2c = cN - c0
    mfe = max(b["h"] for b in window) - c0
    return {"c2c": c2c, "favorable": c2c > 0, "mfe": mfe}


def score_line(line_row: dict, bars_by_date: dict[str, list[dict]],
               already_scored: set[tuple[str, str]]) -> list[dict]:
    """Returns new `event` rows for one ledger `line` row. Scoring starts strictly after
    first_seen_date_et (no look-ahead) and stops at the line's first BREAK (or at
    anchor2.time if extend_right is False)."""
    if line_row.get("line_shape") != "rising":
        return []

    eid = line_row["entity_id"]
    a = line_row["anchor1"]
    b = line_row["anchor2"]
    a_time, a_price = a["time"], a["price"]
    b_time, b_price = b["time"], b["price"]
    if b_time == a_time:
        return []

    start_date = line_row["first_seen_date_et"]
    extend_right = bool(line_row.get("extend_right"))
    cap_unix = None if extend_right else b_time
    in_sample_cutoff = IN_SAMPLE_CUTOFF

    already_broken = (eid, "break") in already_scored
    rows: list[dict] = []

    for date in sorted(bars_by_date.keys()):
        if date <= start_date:
            continue  # no look-ahead: strictly after first_seen's calendar date
        bd = bars_by_date[date]
        in_sample = date <= in_sample_cutoff
        for j, bar in enumerate(bd):
            t = bar["t_unix"]
            if t < b_time:
                continue  # line only exists once B has been anchored
            if cap_unix is not None and t > cap_unix:
                break  # never project past anchor2 when extend_right is False
            if already_broken:
                break

            lv = line_value(a_time, a_price, b_time, b_price, t)
            close, low = bar["c"], bar["l"]

            if close < lv - TOL:
                outcomes = {str(h): _outcome(bd, j, h) for h in HORIZONS}
                rows.append({
                    "kind": "event", "entity_id": eid, "event_type": "break",
                    "in_sample": in_sample, "date_et": date,
                    "bar_idx": j, "bar_t": bar["t_dt"].isoformat(),
                    "close": close, "low": low, "line_value": round(lv, 4),
                    "outcomes": outcomes,
                })
                already_broken = True
                break
            if abs(low - lv) <= TOL and close > lv:
                key = (eid, f"touch:{bar['t_dt'].isoformat()}")
                if key in already_scored:
                    continue
                outcomes = {str(h): _outcome(bd, j, h) for h in HORIZONS}
                rows.append({
                    "kind": "event", "entity_id": eid, "event_type": "touch",
                    "in_sample": in_sample, "date_et": date,
                    "bar_idx": j, "bar_t": bar["t_dt"].isoformat(),
                    "close": close, "low": low, "line_value": round(lv, 4),
                    "outcomes": outcomes,
                })
        if already_broken:
            break

    return rows


# ------------------------------------------------------------------------------------------
# summary statistics -- session-clustered bootstrap CI + time-of-day baseline
# (identical methodology to trendline_human_anchor_shadow._clustered_bootstrap /
# _baseline_stats -- reimplemented standalone here per this instrument's own
# shadow-only-from-scratch discipline, not imported)
# ------------------------------------------------------------------------------------------
def _clustered_bootstrap(events_by_session: dict[str, list[dict]], rng: random.Random,
                          n_boot: int = B_BOOT) -> dict:
    sessions = list(events_by_session.keys())
    pooled = [e for v in events_by_session.values() for e in v]
    n = len(pooled)
    if n == 0 or not sessions:
        return {"n": 0, "n_sessions": 0, "rate": None, "rate_ci": None,
                "mean_move": None, "mean_move_ci": None}
    point_rate = sum(1 for e in pooled if e["favorable"]) / n
    point_mean = statistics.mean(e["c2c"] for e in pooled)

    agg = []
    for s in sessions:
        evs = events_by_session[s]
        agg.append((len(evs), sum(1 for e in evs if e["favorable"]), sum(e["c2c"] for e in evs)))
    n_sessions = len(sessions)

    rates, means = [], []
    randrange = rng.randrange
    for _ in range(n_boot):
        tot_n = tot_nf = 0
        tot_s = 0.0
        for _ in range(n_sessions):
            cn, cnf, cs = agg[randrange(n_sessions)]
            tot_n += cn
            tot_nf += cnf
            tot_s += cs
        if tot_n:
            rates.append(tot_nf / tot_n)
            means.append(tot_s / tot_n)
    rates.sort()
    means.sort()

    def pct(arr, p):
        if not arr:
            return None
        idx = min(len(arr) - 1, max(0, int(round(p * (len(arr) - 1)))))
        return arr[idx]

    return {"n": n, "n_sessions": len(events_by_session), "rate": point_rate,
            "rate_ci": [pct(rates, 0.025), pct(rates, 0.975)],
            "mean_move": point_mean, "mean_move_ci": [pct(means, 0.025), pct(means, 0.975)]}


def _build_hhmm_index(bars_by_date: dict[str, list[dict]]) -> dict[str, list[tuple[str, int]]]:
    idx: dict[str, list[tuple[str, int]]] = {}
    for date, bd in bars_by_date.items():
        for j, b in enumerate(bd):
            idx.setdefault(b["t_dt"].strftime("%H:%M"), []).append((date, j))
    return idx


def _baseline_stats(hhmm_index: dict[str, list[tuple[str, int]]],
                     bars_by_date: dict[str, list[dict]], event_bar_set: set[tuple[str, int]],
                     event_hhmm: set[str], horizon: int) -> dict:
    N = HORIZON_BARS[horizon]
    pooled = []
    for hhmm in event_hhmm:
        for date, j in hhmm_index.get(hhmm, ()):
            if (date, j) in event_bar_set:
                continue
            bd = bars_by_date[date]
            if j + N >= len(bd):
                continue
            c0 = bd[j]["c"]
            cN = bd[j + N]["c"]
            pooled.append(cN - c0)
    if not pooled:
        return {"n": 0, "rate": None, "mean_move": None}
    return {"n": len(pooled), "rate": sum(1 for x in pooled if x > 0) / len(pooled),
            "mean_move": statistics.mean(pooled)}


def _top3_concentration(events_by_line: dict[str, list[dict]]) -> float:
    counts = sorted((len(v) for v in events_by_line.values()), reverse=True)
    total = sum(counts)
    if total == 0:
        return 0.0
    return round(sum(counts[:3]) / total, 4)


def summarize(rows: list[dict], bars_by_date: dict[str, list[dict]]) -> dict:
    rng = random.Random(SEED)
    lines = [r for r in rows if r["kind"] == "line"]
    events = [r for r in rows if r["kind"] == "event"]

    hhmm_index = _build_hhmm_index(bars_by_date)
    event_bar_set = {(r["date_et"], r["bar_idx"]) for r in events}

    rising = [r for r in lines if r.get("line_shape") == "rising"]
    n_lines_total = len(lines)
    n_lines_rising = len(rising)
    n_lines_forward = sum(1 for r in rising if not r.get("in_sample"))
    n_lines_in_sample = sum(1 for r in rising if r.get("in_sample"))

    def per_type(etype: str, forward_only: bool) -> dict:
        sel = [r for r in events if r["event_type"] == etype
               and (not forward_only or not r["in_sample"])]
        by_h = {}
        for h in HORIZONS:
            by_session: dict[str, list[dict]] = {}
            hhmm: set[str] = set()
            for r in sel:
                oc = r["outcomes"].get(str(h))
                if oc is None:
                    continue
                by_session.setdefault(r["date_et"], []).append(oc)
                hhmm.add(r["bar_t"][11:16])
            stats = _clustered_bootstrap(by_session, rng)
            stats["baseline"] = _baseline_stats(hhmm_index, bars_by_date, event_bar_set, hhmm, h)
            by_h[str(h)] = stats
        by_line: dict[str, list[dict]] = {}
        for r in sel:
            by_line.setdefault(r["entity_id"], []).append(r)
        return {"by_horizon": by_h, "top3_concentration": _top3_concentration(by_line),
                "n_events": len(sel), "n_sessions": len({r["date_et"] for r in sel}),
                "n_lines": len(by_line)}

    timeframe_bucket = {
        "timeframe": "other",   # prereg section 0/1 -- no per-drawing timeframe signal recoverable yet
        "n_lines_total": n_lines_total, "n_lines_rising": n_lines_rising,
        "n_lines_non_rising_excluded": n_lines_total - n_lines_rising,
        "n_lines_in_sample": n_lines_in_sample, "n_lines_forward": n_lines_forward,
        "touch_all": per_type("touch", forward_only=False),
        "break_all": per_type("break", forward_only=False),
        "touch_forward": per_type("touch", forward_only=True),
        "break_forward": per_type("break", forward_only=True),
    }

    # decision rule (prereg section 4): TOUCH only, H=60, forward-only
    today = _stamp_now_et()[:10]
    date_gate_open = today >= HARD_DATE_GATE
    cell = timeframe_bucket["touch_forward"]
    h60 = cell["by_horizon"]["60"]
    n_sessions_forward = len({r["date_et"] for r in rows if r["kind"] == "line"
                               and r.get("line_shape") == "rising" and not r.get("in_sample")})
    # sessions for the bar = distinct forward dates contributing at least one scored event
    n_sessions_forward_events = cell["n_sessions"]
    n_ok = (n_lines_forward >= BAR_MIN_LINES_FORWARD
            and n_sessions_forward_events >= BAR_MIN_SESSIONS_FORWARD)
    baseline_rate = h60["baseline"]["rate"]
    rate_ci = h60.get("rate_ci")
    mean_ci = h60.get("mean_move_ci")
    rate_ok = (rate_ci is not None and rate_ci[0] is not None
               and baseline_rate is not None and rate_ci[0] > baseline_rate)
    mean_ok = mean_ci is not None and mean_ci[0] is not None and mean_ci[0] > 0
    falsified = (rate_ci is not None and rate_ci[0] is not None
                 and baseline_rate is not None and rate_ci[0] <= baseline_rate) \
        or (mean_ci is not None and mean_ci[0] is not None and mean_ci[0] <= 0) \
        or (cell["top3_concentration"] >= FALSIFIER_TOP3_CONCENTRATION)
    if not n_ok:
        status = "ACCRUING"
    elif not date_gate_open:
        status = "BAR_MET_DATE_GATED"
    elif rate_ok and mean_ok and cell["top3_concentration"] < FALSIFIER_TOP3_CONCENTRATION:
        status = "SUPPORTED_PROCEED_TO_RATIFICATION"
    elif falsified:
        status = "FALSIFIED"
    else:
        status = "BAR_MET_INCONCLUSIVE"

    decision = {
        "n_lines_forward": n_lines_forward, "n_sessions_forward_lines": n_sessions_forward,
        "n_sessions_forward_events": n_sessions_forward_events,
        "bar_met": n_ok, "date_gate_open": date_gate_open,
        "baseline_rate": baseline_rate, "rate_ci_lower": rate_ci[0] if rate_ci else None,
        "rate_clears_baseline": rate_ok,
        "mean_move_ci_lower": mean_ci[0] if mean_ci else None, "mean_move_positive": mean_ok,
        "top3_concentration": cell["top3_concentration"], "status": status,
    }

    return {
        "prereg": PREREG_REL, "generated_at_et": _stamp_now_et(),
        "in_sample_cutoff": IN_SAMPLE_CUTOFF, "hard_date_gate": HARD_DATE_GATE,
        "timeframes": {"other": timeframe_bucket}, "decision": decision,
    }


# ------------------------------------------------------------------------------------------
def run() -> dict:
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        existing = _read_ledger()
        line_rows = [r for r in existing if r.get("kind") == "line"]
        already_scored = _scored_event_keys(existing)

        bars_by_date = _session_bars_cache()

        appended: list[dict] = []
        for line_row in line_rows:
            appended.extend(score_line(line_row, bars_by_date, already_scored))
            for r in appended:
                if r.get("entity_id") == line_row["entity_id"] and r["event_type"] == "break":
                    already_scored.add((line_row["entity_id"], "break"))

        if appended:
            with LEDGER.open("a", encoding="utf-8") as fh:
                for r in appended:
                    fh.write(json.dumps(r) + "\n")

        all_rows = existing + appended
        summary = summarize(all_rows, bars_by_date)
        summary["new_events_this_run"] = len(appended)
        summary["n_lines_ledger"] = len(line_rows)
        SUMMARY.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        return summary
    except Exception as e:  # noqa: BLE001 -- descriptive side-product, never fatal
        return {"error": f"{type(e).__name__}: {e}"[:500], "prereg": PREREG_REL}


def main() -> int:
    out = run()
    print(json.dumps(out, indent=1)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
