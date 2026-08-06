"""LENS 2 entry-improvement variant scorer -- EOD 2026-08-05.

Runs the cells frozen in analysis/recommendations/entry-improvement-variants-prereg-2026-08-05.json
(committed b9cd7a6e BEFORE this file existed) over the LIVE-ENGINE-REAL-FILLS-v1 population.

Every feature is causal: computed from bars whose CLOSE time is <= the entry timestamp.
No option pricing here -- P&L is the arm's own realised broker fills.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import pickle
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "crypto"))

from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.market_structure import analyze_structure  # noqa: E402

ET = dt.timezone(dt.timedelta(hours=-4))
SCRATCH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")


# ---------------------------------------------------------------- load context
def load_ctx():
    ctx = pickle.load(open(SCRATCH / "ctx.pkl", "rb"))
    events = json.load(open(SCRATCH / "events.json"))["events"]
    for e in events:
        e["entry_dt"] = dt.datetime.fromisoformat(e["entry_ts"]).replace(tzinfo=ET)
    return ctx, events


def closed_bars_before(bars, cutoff, minutes):
    """Bars whose CLOSE time (open + minutes) is <= cutoff. Fully causal."""
    out = []
    for b in bars:
        if b["t"] + dt.timedelta(minutes=minutes) <= cutoff:
            out.append(b)
        else:
            break
    return out


def rth(bars):
    return [b for b in bars if dt.time(9, 30) <= b["t"].time() < dt.time(16, 0)]


# ---------------------------------------------------------------- features
def build_features(ctx, events):
    m1, m5, prior_ext, lvl = ctx["m1"], ctx["m5"], ctx["prior_ext"], ctx["lvl"]
    for e in events:
        d, cutoff = e["date"], e["entry_dt"]
        r1 = rth(m1.get(d, []))
        r5 = rth(m5.get(d, []))
        c1 = closed_bars_before(r1, cutoff, 1)
        c5 = closed_bars_before(r5, cutoff, 5)
        e["n_closed_1m"] = len(c1)
        e["n_closed_5m"] = len(c5)
        e["spot"] = c1[-1]["c"] if c1 else None

        # -- V-a: structure over CLOSED 5m bars
        e["struct_kind"] = e["struct_dir"] = None
        e["struct_bars_ago"] = None
        if len(c5) >= 8:
            bars = [Bar(open_time=b["t"], open=b["o"], high=b["h"], low=b["l"],
                        close=b["c"], volume=b["v"], granularity_seconds=300,
                        source="alpaca_sip") for b in c5]
            try:
                rd = analyze_structure(bars, window=3)
                if rd.last_event is not None:
                    ev = rd.last_event
                    e["struct_kind"] = ev.kind
                    e["struct_dir"] = "up" if getattr(ev, "direction", None) in ("up", "bullish") \
                        else ("down" if getattr(ev, "direction", None) in ("down", "bearish") else None)
                    if e["struct_dir"] is None:
                        # derive from the trend the event left behind
                        e["struct_dir"] = "up" if rd.trend == "uptrend" else (
                            "down" if rd.trend == "downtrend" else None)
                    e["struct_bars_ago"] = len(bars) - 1 - ev.break_index
                e["struct_trend"] = rd.trend
            except Exception as exc:  # noqa: BLE001
                e["struct_err"] = repr(exc)[:120]

        # -- V-b: levels
        e["levels_engine"] = None
        for ts, la in lvl.get(d, []):
            if ts <= cutoff.strftime("%H:%M:%S"):
                e["levels_engine"] = la
            else:
                break
        e["levels_proxy"] = mechanical_levels(d, cutoff, m1, prior_ext)

        # -- V-c / V-c'
        pe = prior_ext.get(d)
        e["prior_high"] = pe["ph"] if pe else None
        e["prior_low"] = pe["pl"] if pe else None
        if c1:
            hi = max(c1, key=lambda b: b["h"])
            lo = min(c1, key=lambda b: b["l"])
            e["sess_high"] = hi["h"]
            e["sess_high_age_min"] = (cutoff - hi["t"]).total_seconds() / 60.0
            e["sess_low"] = lo["l"]
            e["sess_low_age_min"] = (cutoff - lo["t"]).total_seconds() / 60.0
        else:
            e["sess_high"] = e["sess_low"] = None
            e["sess_high_age_min"] = e["sess_low_age_min"] = None

        # -- V-d
        e["last5_dir"] = None
        e["last5_third"] = None
        if c5:
            b = c5[-1]
            e["last5_dir"] = "up" if b["c"] > b["o"] else ("down" if b["c"] < b["o"] else "flat")
            rng = b["h"] - b["l"]
            if rng > 0:
                pos = (b["c"] - b["l"]) / rng
                e["last5_third"] = "top" if pos >= 2 / 3 else ("bottom" if pos <= 1 / 3 else "mid")
    return events


def mechanical_levels(day, cutoff, m1, prior_ext):
    """Causal proxy level set (violin defn v1 sources minus level_memory):
    prior-day high/low/close, premarket high/low, session high/low so far,
    session swing highs/lows so far (5-bar pivots on closed 1m bars)."""
    out = []
    pe = prior_ext.get(day)
    if pe:
        out += [pe["ph"], pe["pl"]]
        prev_rth = rth(m1.get(pe["pdate"], []))
        if prev_rth:
            out.append(prev_rth[-1]["c"])
    pm = [b for b in m1.get(day, []) if dt.time(4, 0) <= b["t"].time() < dt.time(9, 30)]
    if pm:
        out += [max(b["h"] for b in pm), min(b["l"] for b in pm)]
    c1 = closed_bars_before(rth(m1.get(day, [])), cutoff, 1)
    if c1:
        out += [max(b["h"] for b in c1), min(b["l"] for b in c1)]
        w = 5
        for i in range(w, len(c1) - w):
            if c1[i]["h"] == max(x["h"] for x in c1[i - w:i + w + 1]):
                out.append(c1[i]["h"])
            if c1[i]["l"] == min(x["l"] for x in c1[i - w:i + w + 1]):
                out.append(c1[i]["l"])
    return sorted({round(x, 2) for x in out if x})


# ---------------------------------------------------------------- variants
def blocked_by(e, cell):
    """True = this cell BLOCKS the entry. None = ABSTAIN (insufficient data)."""
    cid = cell["id"]
    long_ = e["side"] == "C"
    want = "up" if long_ else "down"

    if cid.startswith("V-a"):
        if e["n_closed_5m"] < 8:
            return None
        if e.get("struct_kind") is None or e.get("struct_dir") != want:
            return True
        cap = cell.get("max_bars_since_event")
        if cap is not None and (e.get("struct_bars_ago") is None or e["struct_bars_ago"] > cap):
            return True
        return False

    if cid.startswith("V-b"):
        levels = e["levels_engine"] if cell["src"] == "engine" else e["levels_proxy"]
        if not levels or e["spot"] is None:
            return None
        band = cell["band_usd"]
        for L in levels:
            if long_ and L <= e["spot"] <= L + band:
                return False
            if (not long_) and L - band <= e["spot"] <= L:
                return False
        return True

    if cid.startswith("V-c") and not cid.startswith("V-cp"):
        n = cell["n_usd"]
        if e["spot"] is None:
            return None
        if long_:
            if e["prior_high"] is None:
                return None
            return e["prior_high"] - n <= e["spot"] <= e["prior_high"]
        if e["prior_low"] is None:
            return None
        return e["prior_low"] <= e["spot"] <= e["prior_low"] + n

    if cid.startswith("V-cp"):
        n, k = cell["n_usd"], cell["k_min"]
        if e["spot"] is None:
            return None
        if long_:
            if e["sess_high"] is None:
                return None
            return (e["sess_high"] - n <= e["spot"] <= e["sess_high"]
                    and e["sess_high_age_min"] >= k)
        if e["sess_low"] is None:
            return None
        return (e["sess_low"] <= e["spot"] <= e["sess_low"] + n
                and e["sess_low_age_min"] >= k)

    if cid == "V-d1":
        if e["last5_dir"] is None:
            return None
        return e["last5_dir"] != ("up" if long_ else "down")
    if cid == "V-d2":
        if e["last5_dir"] is None or e["last5_third"] is None:
            return None
        ok = e["last5_dir"] == ("up" if long_ else "down") and \
            e["last5_third"] == ("top" if long_ else "bottom")
        return not ok
    raise ValueError(cid)


CELLS = (
    [{"id": "V-a1", "max_bars_since_event": None},
     {"id": "V-a2", "max_bars_since_event": 6},
     {"id": "V-a3", "max_bars_since_event": 3}]
    + [{"id": f"V-b{i}", "band_usd": b, "src": s}
       for i, b in ((1, 0.15), (2, 0.25), (3, 0.40)) for s in ("engine", "proxy")]
    + [{"id": "V-c1", "n_usd": 0.25}, {"id": "V-c2", "n_usd": 0.50}, {"id": "V-c3", "n_usd": 1.00}]
    + [{"id": "V-cp1", "n_usd": 0.50, "k_min": 10},
       {"id": "V-cp2", "n_usd": 1.00, "k_min": 10},
       {"id": "V-cp3", "n_usd": 1.00, "k_min": 20}]
    + [{"id": "V-d1"}, {"id": "V-d2"}]
)


def score(events):
    days = sorted({e["date"] for e in events})
    half = days[: len(days) // 2]
    rows = []
    for cell in CELLS:
        cid = cell["id"] + ("/" + cell["src"] if "src" in cell else "")
        blocked, kept, abstain = [], [], []
        for e in events:
            v = blocked_by(e, cell)
            (blocked if v is True else (abstain if v is None else kept)).append(e)
        # abstain counts as kept for P&L
        bl = sum(e["pnl"] for e in blocked)
        row = {
            "cell": cid,
            "n_blocked": len(blocked), "n_kept": len(kept) + len(abstain), "n_abstain": len(abstain),
            "delta_full": round(-bl, 2),
            "delta_ex_0804": round(-sum(e["pnl"] for e in blocked if e["date"] != "2026-08-04"), 2),
            "delta_0805": round(-sum(e["pnl"] for e in blocked if e["date"] == "2026-08-05"), 2),
            "delta_ex_0805": round(-sum(e["pnl"] for e in blocked if e["date"] != "2026-08-05"), 2),
            "delta_0804": round(-sum(e["pnl"] for e in blocked if e["date"] == "2026-08-04"), 2),
            "blocked_winner_$": round(sum(e["pnl"] for e in blocked if e["pnl"] > 0), 2),
            "blocked_loser_$": round(-sum(e["pnl"] for e in blocked if e["pnl"] < 0), 2),
            "delta_h1": round(-sum(e["pnl"] for e in blocked if e["date"] in half), 2),
            "delta_h2": round(-sum(e["pnl"] for e in blocked if e["date"] not in half), 2),
        }
        # days flipped positive -> negative
        by_day_actual = collections.defaultdict(float)
        by_day_new = collections.defaultdict(float)
        bset = {id(e) for e in blocked}
        for e in events:
            by_day_actual[e["date"]] += e["pnl"]
            if id(e) not in bset:
                by_day_new[e["date"]] += e["pnl"]
        row["days_flipped_pos_to_neg"] = sum(
            1 for d in days if by_day_actual[d] > 0 and by_day_new[d] < 0)
        g = {
            "G1": row["delta_full"] > 0,
            "G2": row["blocked_winner_$"] < row["blocked_loser_$"],
            "G3": row["delta_0805"] > 0,
            "G4": row["delta_h1"] >= 0 and row["delta_h2"] >= 0,
            "G5": row["n_blocked"] >= 5,
            "G6": row["delta_0804"] >= -250,
        }
        row["gates"] = "".join(k[1] if v else "-" for k, v in g.items())
        row["gates_pass"] = sum(g.values())
        row["verdict"] = ("SHIP_CANDIDATE" if all(g.values())
                          else ("REJECT" if not (g["G1"] and g["G2"]) else "WATCH"))
        rows.append(row)
    return rows, days


def main():
    ctx, events = load_ctx()
    events = build_features(ctx, events)
    rows, days = score(events)
    hdr = ["cell", "n_blocked", "n_abstain", "delta_full", "delta_ex_0804", "delta_0805",
           "delta_ex_0805", "delta_0804", "blocked_winner_$", "blocked_loser_$",
           "delta_h1", "delta_h2", "days_flipped_pos_to_neg", "gates", "verdict"]
    print(" | ".join(f"{h:>12}" if h != "cell" else f"{h:<14}" for h in hdr))
    for r in rows:
        print(" | ".join((f"{r[h]:<14}" if h == "cell" else f"{str(r[h]):>12}") for h in hdr))
    out = {"population_days": days, "n_events": len(events),
           "actual_net_pnl": round(sum(e["pnl"] for e in events), 2), "rows": rows}
    json.dump(out, open(SCRATCH / "variant_rows.json", "w"), indent=1)
    json.dump([{k: v for k, v in e.items() if k != "entry_dt"} for e in events],
              open(SCRATCH / "events_feat.json", "w"), default=str)
    print("\nwrote variant_rows.json + events_feat.json")


if __name__ == "__main__":
    main()
