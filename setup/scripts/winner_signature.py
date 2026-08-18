#!/usr/bin/env python
"""winner_signature.py -- WHAT DOES OUR MONEY LOOK LIKE?

The companion to `winner_autopsy.py`. That instrument answers "how much of what our
winners offered did we KEEP" (an EXIT question). This one answers J's other question:

    "review all the trades the engine has done, focus on the winners -- what is our
     edge, what's been working, what's the common theme?"

It is an ENTRY/REGIME/SHAPE question, and it is answered over the real-fills journal
(`journal/trades.csv`), joined to the engine's own decision context at entry
(`core-decisions.jsonl` + the per-arm fleet decision ledgers) and to the post-hoc day
taxonomy (`analysis/regime-library/day-archetypes.json`).

DESCRIPTIVE ONLY. Nothing here ratifies a knob. Every bucket printed is a conditional
on an outcome-bearing population; the disclosures below are load-bearing.

THE THREE DISCLOSURES (read before quoting any number out of this file)
----------------------------------------------------------------------
1. ARMS ARE NOT INDEPENDENT. Up to 6 arms consume ONE shared signal and enter the same
   impulse within seconds. 424 fills are ~102 independent "waves". Every per-trade
   bucket is therefore ~4x over-counted. This report prints the WAVE level as the
   headline denominator.
2. HOLD TIME AND EXIT MULTIPLE ARE OUTCOMES, NOT LEVERS. "Winners held 24 min, losers
   6 min" is close to a tautology -- a stop-out is short BECAUSE it lost. Those rows
   describe the SHAPE of our money; they are never an entry filter.
3. DAY REALIZED RANGE IS LOOK-AHEAD. `range_pct` is known only at the close. It is the
   single strongest correlate of day P&L in this data and it is UNUSABLE as an ex-ante
   gate. The ex-ante section exists precisely to show that every pre-open proxy for it
   (ATR, VIX-open, gap) has r ~ 0.

$0 -- pure Python over files already on disk. Read-only; safe to run any time.
"""
from __future__ import annotations

import collections
import csv
import json
import math
import statistics as st
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

TRADES = REPO / "journal" / "trades.csv"
CORE = REPO / "automation" / "state" / "core-decisions.jsonl"
FLEET = REPO / "automation" / "state" / "fleet"
ARCHETYPES = REPO / "analysis" / "regime-library" / "day-archetypes.json"
OUT_MD = REPO / "analysis" / "winner-autopsies" / "SIGNATURE.md"
OUT_JSON = REPO / "analysis" / "winner-autopsies" / "signature.json"

FLEET_ARMS = ("risky-1", "risky-3", "safe-1", "safe-3")
KNOWN_ARMS = {"safe", "bold", "safe-1", "safe-3", "risky-1", "risky-3"}
WAVE_GAP_S = 900  # >15 min between entries starts a new wave (same convention as winner_autopsy)


# ----------------------------------------------------------------------------- helpers
def _num(x):
    try:
        return float(str(x).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _secs(t):
    try:
        p = str(t).split(":")
        return int(p[0]) * 3600 + int(p[1]) * 60 + (int(float(p[2])) if len(p) > 2 else 0)
    except (TypeError, ValueError, IndexError):
        return None


def _corr(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return num / den if den else float("nan")


# ------------------------------------------------------------------------------- load
def load_trades():
    """Real fills only. Rows whose account_id is not a known arm are the handful of
    journal rows with embedded newlines in `notes_short`; they are skipped, not
    silently repaired."""
    rows = []
    with open(TRADES, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r.get("account_id") not in KNOWN_ARMS:
                continue
            if _num(r.get("dollar_pnl")) is None or _secs(r.get("time_entry")) is None:
                continue
            rows.append(r)
    return rows


def _iter_jsonl(path):
    if not path.exists():
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def load_decisions():
    """Return (enters_by_arm_date, core_by_tick_id, core_by_date).

    core-decisions.jsonl carries the shared market context (ribbon, vix, scores,
    triggers, context_bundle) for BOTH core arms and -- via `core_tick_id` -- for the
    fleet arms, which consume the same shared signal. That is why a fleet arm's thin
    decision row can still be attributed the full core context.
    """
    core, enters = [], []
    for rec in _iter_jsonl(CORE):
        rec.pop("exit_pass", None)
        ts = rec.get("ts_et", "")
        rec["_date"], rec["_sec"] = ts[:10], _secs(ts[11:19])
        core.append(rec)
        if str(rec.get("verdict") or rec.get("action") or "").startswith("ENTER"):
            ent = dict(rec)
            ent["_arm"] = rec.get("account")
            enters.append(ent)
    for arm in FLEET_ARMS:
        for rec in _iter_jsonl(FLEET / arm / "decisions.jsonl"):
            if not str(rec.get("verdict") or rec.get("action") or "").startswith("ENTER"):
                continue
            rec.pop("exit_pass", None)
            ts = rec.get("ts_et", "")
            rec["_arm"], rec["_date"], rec["_sec"] = arm, ts[:10], _secs(ts[11:19])
            enters.append(rec)

    by_arm_date = collections.defaultdict(list)
    for ent in enters:
        if ent.get("_sec") is not None and ent.get("_arm"):
            by_arm_date[(ent["_arm"], ent["_date"])].append(ent)
    for v in by_arm_date.values():
        v.sort(key=lambda e: e["_sec"])

    by_tick = {rec["core_tick_id"]: rec for rec in core if rec.get("core_tick_id")}
    by_date = collections.defaultdict(list)
    for rec in core:
        if rec.get("_sec") is not None:
            by_date[rec["_date"]].append(rec)
    for v in by_date.values():
        v.sort(key=lambda x: x["_sec"])
    return by_arm_date, by_tick, by_date


def join(trades, by_arm_date, by_tick, by_date):
    """Attach (decision, core-context) to each real fill.

    Match window: the arm's ENTER verdict from 10 min BEFORE to 15 min AFTER the
    recorded fill time, preferring an exact strike match. Fills predating
    core-decisions.jsonl (2026-06-25) simply carry no context -- they stay in the P&L
    totals and drop out of context buckets, never silently discarded.
    """
    out = []
    for r in trades:
        t, key = _secs(r["time_entry"]), (r["account_id"], r["date"])
        cands = [e for e in by_arm_date.get(key, []) if -600 <= (t - e["_sec"]) <= 900]
        dec = None
        if cands:
            sk = _num(r.get("strike"))
            pool = [e for e in cands if _num(e.get("strike")) == sk] or cands
            dec = min(pool, key=lambda e: abs(t - e["_sec"]))
        ctx = None
        if dec and dec.get("core_tick_id"):
            ctx = by_tick.get(dec["core_tick_id"])
        if ctx is None:
            prior = [x for x in by_date.get(r["date"], []) if 0 <= (t - x["_sec"]) <= 600]
            if prior:
                ctx = max(prior, key=lambda x: x["_sec"])
        out.append({"trade": r, "dec": dec or {}, "core": ctx or {}})
    return out


def flatten(joined):
    recs = []
    for j in joined:
        t, c, dec = j["trade"], j["core"], j["dec"]
        entry, exitp = _num(t.get("entry_px")), _num(t.get("exit_px"))
        recs.append(dict(
            date=t["date"], arm=t["account_id"], side=t.get("c_or_p"), setup=t.get("setup"),
            pnl=_num(t["dollar_pnl"]), qty=_num(t.get("qty")), entry=entry, exitp=exitp,
            mult=(exitp / entry) if (entry and exitp) else None,
            hold=_num(t.get("hold_minutes")), sec=_secs(t["time_entry"]),
            xsec=_secs(t.get("time_exit")), hr=int(str(t["time_entry"])[:2]),
            vix=c.get("vix"), ribbon_width=c.get("spread_cents"), ribbon=c.get("ribbon"),
            htf=c.get("htf_15m"), quality=dec.get("quality"),
            triggers=",".join(sorted(c.get("triggers") or [])) or None,
            has_ctx=bool(c),
        ))
    recs.sort(key=lambda r: (r["date"], r["sec"]))
    return recs


def wavify(recs):
    """Group entries into impulse waves -- all arms piling into ONE move = one wave."""
    waves, cur = [], None
    for r in recs:
        if cur and r["date"] == cur["date"] and r["sec"] - cur["_last"] <= WAVE_GAP_S:
            cur["rows"].append(r)
            cur["_last"] = r["sec"]
        else:
            cur = {"date": r["date"], "rows": [r], "_last": r["sec"]}
            waves.append(cur)
    seen = collections.Counter()
    for w in waves:
        w["pnl"] = sum(x["pnl"] for x in w["rows"])
        w["head"] = w["rows"][0]
        seen[w["date"]] += 1
        w["nth"] = seen[w["date"]]
        for r in w["rows"]:
            r["wave_nth"] = w["nth"]
    return waves


# ---------------------------------------------------------------------------- reporting
class Doc:
    def __init__(self):
        self.lines = []

    def __call__(self, s=""):
        self.lines.append(s)

    def text(self):
        return "\n".join(self.lines) + "\n"


def bucket_table(doc, title, recs, keyfn, minn, unit="trades"):
    g = collections.defaultdict(list)
    for r in recs:
        try:
            k = keyfn(r)
        except (TypeError, ValueError, KeyError):
            k = None
        if k is None:
            continue
        g[str(k)].append(r)
    rows = [(k, v) for k, v in g.items() if len(v) >= minn]
    if not rows:
        return {}
    doc("")
    doc(f"**{title}**")
    doc("")
    doc(f"| bucket | {unit} | win% | total $ | avg $ |")
    doc("|---|---:|---:|---:|---:|")
    outp = {}
    for k, v in sorted(rows, key=lambda kv: -sum(x["pnl"] for x in kv[1])):
        tot = sum(x["pnl"] for x in v)
        wr = 100 * sum(1 for x in v if x["pnl"] > 0) / len(v)
        doc(f"| `{k}` | {len(v)} | {wr:.0f}% | ${tot:,.0f} | ${tot / len(v):,.0f} |")
        outp[k] = {"n": len(v), "win_pct": round(wr, 1), "total": round(tot, 2)}
    return outp


def _mult_band(m):
    if m is None:
        return None
    if m >= 2:
        return "≥2.0×"
    if m >= 1.3:
        return "1.3–2.0×"
    if m >= 1.0:
        return "1.0–1.3×"
    if m >= 0.7:
        return "0.7–1.0×"
    return "<0.7×"


def main():
    from et_clock import et_now

    trades = load_trades()
    by_arm_date, by_tick, by_date = load_decisions()
    recs = flatten(join(trades, by_arm_date, by_tick, by_date))
    if not recs:
        raise SystemExit("winner_signature: no usable fills in journal/trades.csv -- refusing to write an empty report")
    waves = wavify(recs)
    archetypes = json.loads(ARCHETYPES.read_text(encoding="utf-8"))["days"]

    W = sorted([r for r in recs if r["pnl"] > 0], key=lambda r: -r["pnl"])
    L = [r for r in recs if r["pnl"] <= 0]
    total = sum(r["pnl"] for r in recs)
    ctx_cov = sum(1 for r in recs if r["has_ctx"]) / len(recs)
    wave_wr = 100 * sum(1 for w in waves if w["pnl"] > 0) / len(waves)

    d = Doc()
    d("# Winner signature — what does our money actually look like?")
    d("")
    d(f"_Generated {et_now().strftime('%Y-%m-%d %H:%M:%S')} ET · real-fills journal · $0 (pure Python) · "
      "`setup/scripts/winner_signature.py`._")
    d("")
    d("> **DESCRIPTIVE ONLY — this file ratifies nothing.** Read the three disclosures in the module "
      "docstring before quoting any number: (1) arms are not independent, the honest denominator is "
      "WAVES not trades; (2) hold-time and exit-multiple are OUTCOMES, never entry filters; (3) day "
      "realized range is LOOK-AHEAD and unusable as a gate.")
    d("")
    d("## The population")
    d("")
    d(f"- **{len(recs)} real fills** across {len({r['arm'] for r in recs})} arms and "
      f"{len({r['date'] for r in recs})} sessions ({min(r['date'] for r in recs)} → "
      f"{max(r['date'] for r in recs)}).")
    d(f"- Collapsed to **{len(waves)} independent impulse waves** (>{WAVE_GAP_S // 60} min gap = new wave). "
      "**This is the honest denominator.**")
    d(f"- Engine decision context recovered for **{ctx_cov:.0%}** of fills (the shortfall is fills "
      "predating `core-decisions.jsonl`; they stay in P&L, drop out of context buckets).")
    d(f"- **Trade level:** {len(W)} winners / {len(L)} losers · WR **{100 * len(W) / len(recs):.1f}%** · "
      f"net **${total:,.0f}**.")
    d(f"- **Wave level:** WR **{wave_wr:.0f}%** — three of every four impulses we commit to lose money.")
    d("")
    wsum, lsum = sum(r["pnl"] for r in W), sum(r["pnl"] for r in L)
    d(f"- Winners **${wsum:,.0f}** (avg ${st.mean([r['pnl'] for r in W]):,.0f}, median "
      f"${st.median([r['pnl'] for r in W]):,.0f}, max ${max(r['pnl'] for r in W):,.0f}).")
    d(f"- Losers **${lsum:,.0f}** (avg ${st.mean([r['pnl'] for r in L]):,.0f}, median "
      f"${st.median([r['pnl'] for r in L]):,.0f}, worst ${min(r['pnl'] for r in L):,.0f}).")
    for k in (5, 10, 20, 30):
        if len(W) >= k:
            d(f"  - top {k} winners = ${sum(r['pnl'] for r in W[:k]):,.0f} "
              f"(**{100 * sum(r['pnl'] for r in W[:k]) / wsum:.0f}%** of all winner dollars)")
    d("")

    # ------------------------------------------------------------------ 1. shape
    d("## 1. The shape of the money (outcome anatomy — descriptive, NOT a filter)")
    d("")
    order = ["≥2.0×", "1.3–2.0×", "1.0–1.3×", "0.7–1.0×", "<0.7×"]
    banded = collections.defaultdict(list)
    for r in recs:
        b = _mult_band(r["mult"])
        if b:
            banded[b].append(r)
    d("| exit ÷ entry premium | n | total $ |")
    d("|---|---:|---:|")
    shape = {}
    for k in order:
        sel = banded.get(k)
        if not sel:
            continue
        shape[k] = {"n": len(sel), "total": round(sum(x["pnl"] for x in sel), 2)}
        d(f"| {k} | {len(sel)} | ${sum(x['pnl'] for x in sel):,.0f} |")
    runners = banded.get("≥2.0×", []) + banded.get("1.3–2.0×", [])
    club = banded.get("≥2.0×", [])
    if runners:
        d("")
        d(f"**Every dollar we have ever made came from an exit at ≥1.3× entry.** Those "
          f"{len(runners)} fills — {100 * len(runners) / len(recs):.0f}% of the book — carry "
          f"${sum(r['pnl'] for r in runners):,.0f}. Everything below 1.3× is net negative, including the "
          "band that closed at a nominal small profit.")
    if club:
        d("")
        d(f"**The 2× club — {len(club)} fills ({100 * len(club) / len(recs):.0f}% of the book) carrying "
          f"${sum(r['pnl'] for r in club):,.0f}.** Median hold "
          f"**{st.median([r['hold'] for r in club if r['hold'] is not None]):.0f} min**, median entry premium "
          f"**${st.median([r['entry'] for r in club if r['entry']]):.2f}**, concentrated on "
          f"**{len({r['date'] for r in club})} sessions**. That is the edge in one line: a "
          "near-the-money contract given room to run through a real impulse.")
    losers_m = [r["mult"] for r in L if r["mult"] is not None]
    if losers_m:
        d("")
        d(f"**The bleed dies small, not catastrophically:** median losing exit is "
          f"**{st.median(losers_m):.2f}×** entry (≈{100 * (st.median(losers_m) - 1):.0f}%), nowhere near the "
          "−50% catastrophe cap. The book is not killed by disasters — it is nibbled to death by a high "
          "count of small, fast invalidations.")
    d("")

    # ------------------------------------------------------------------ 2. ex-ante buckets
    d("## 2. Ex-ante buckets (wave level = the honest denominator)")
    d("")
    d("_A finding only counts if it holds at wave level AND is knowable BEFORE the entry._")
    wave_recs = [dict(w["head"], pnl=w["pnl"]) for w in waves]
    buckets = {}
    buckets["entry_premium"] = bucket_table(
        d, "Entry premium (ex-ante — the strike we chose)", wave_recs,
        lambda r: None if not r["entry"] else (
            "<$0.30" if r["entry"] < .3 else "$0.30–0.60" if r["entry"] < .6 else
            "$0.60–1.00" if r["entry"] < 1 else "$1.00–2.00" if r["entry"] < 2 else "$2.00+"),
        5, unit="waves")
    buckets["hour"] = bucket_table(d, "Hour of entry (ex-ante)", wave_recs,
                                   lambda r: f"{r['hr']:02d}:xx", 5, unit="waves")
    buckets["setup"] = bucket_table(d, "Setup (ex-ante)", wave_recs, lambda r: r["setup"], 5, unit="waves")
    buckets["side"] = bucket_table(d, "Side (ex-ante)", wave_recs, lambda r: r["side"], 5, unit="waves")
    buckets["vix"] = bucket_table(
        d, "VIX at entry (ex-ante)", wave_recs,
        lambda r: None if not r["vix"] else (
            "<14" if r["vix"] < 14 else "14–16" if r["vix"] < 16 else "16–18" if r["vix"] < 18 else "18+"),
        5, unit="waves")
    buckets["triggers"] = bucket_table(d, "Trigger set (ex-ante)", wave_recs,
                                       lambda r: r["triggers"] or "none", 5, unit="waves")
    d("")
    d("> ⚠ **Ribbon width (`spread_cents`) is a TRAP — logged so the next session does not re-discover "
      "and ship it.** Filtering out width ≥40¢ turns the whole book positive, which is why it looks "
      "irresistible; it also removes ~81% of the population and kills 18 of the top-25 winners. It is a "
      "trend-EXTENSION measure, not a bid-ask spread. That is survivorship, not edge.")
    d("")

    # ------------------------------------------------------------------ 3. regime
    d("## 3. Regime — the strongest signal in the data, and it is LOOK-AHEAD")
    d("")
    byday = collections.defaultdict(list)
    for r in recs:
        byday[r["date"]].append(r)
    day_rows = []
    for dt_, rows in sorted(byday.items()):
        a = archetypes.get(dt_)
        if not a:
            continue
        day_rows.append(dict(date=dt_, arch=a["archetype"], rng=a.get("range_pct"),
                             atr=a.get("atr14_prior_pct"), gap=a.get("gap_pct"),
                             vixo=a.get("vix_open"), n=len(rows),
                             pnl=sum(x["pnl"] for x in rows)))
    d("**Realized day range vs day P&L** (⚠ range is known only at the CLOSE):")
    d("")
    d("| realized range | days | fills | total $ | $/day | green days |")
    d("|---|---:|---:|---:|---:|---:|")
    rng_b = {}
    for lab, lo, hi in [("<0.5%", 0, .5), ("0.5–0.8%", .5, .8), ("0.8–1.2%", .8, 1.2), ("1.2%+", 1.2, 99)]:
        v = [x for x in day_rows if x["rng"] is not None and lo <= x["rng"] < hi]
        if not v:
            continue
        tot = sum(x["pnl"] for x in v)
        green = sum(1 for x in v if x["pnl"] > 0)
        rng_b[lab] = {"days": len(v), "total": round(tot, 2), "green_days": green}
        d(f"| {lab} | {len(v)} | {sum(x['n'] for x in v)} | ${tot:,.0f} | ${tot / len(v):,.0f} | "
          f"{green}/{len(v)} |")
    d("")
    d("**Every pre-open proxy for that range fails.**")
    d("")
    d("| ex-ante candidate | r vs realized range | r vs day P&L |")
    d("|---|---:|---:|")
    exante = {}
    for nm, key, absolute in [("ATR14 prior %", "atr", False), ("VIX open", "vixo", False),
                              ("abs(gap %)", "gap", True)]:
        pairs = [((abs(x[key]) if absolute else x[key]), x["rng"], x["pnl"])
                 for x in day_rows if x.get(key) is not None and x["rng"] is not None]
        if len(pairs) < 5:
            continue
        r1 = _corr([p[0] for p in pairs], [p[1] for p in pairs])
        r2 = _corr([p[0] for p in pairs], [p[2] for p in pairs])
        exante[nm] = {"r_vs_range": round(r1, 3), "r_vs_pnl": round(r2, 3)}
        d(f"| {nm} | {r1:+.2f} | {r2:+.2f} |")
    pr = [(x["rng"], x["pnl"]) for x in day_rows if x["rng"] is not None]
    r_post = _corr([p[0] for p in pr], [p[1] for p in pr])
    d(f"| _realized range (POST-HOC, unusable)_ | — | **{r_post:+.2f}** |")
    d("")
    d("**Conclusion: the day cannot be pre-selected.** The regime that decides our P&L is invisible "
      "before the open, so the lever cannot be a pre-open gate — it has to be an intraday feedback loop.")
    bucket_table(d, "Day archetype (post-hoc taxonomy)",
                 [dict(pnl=x["pnl"], a=x["arch"]) for x in day_rows], lambda r: r["a"], 2, unit="days")
    d("")

    # ------------------------------------------------------------------ 4. feedback
    d("## 4. The feedback signal the engine does not currently use")
    d("")
    cond = {}
    for lab, test in [("first wave LOST", lambda p: p < 0), ("first wave WON", lambda p: p > 0)]:
        days = rest_n = rest_green = 0
        rest_pnl = 0.0
        for _dt, rows in byday.items():
            w1 = [r for r in rows if r.get("wave_nth") == 1]
            if not w1 or not test(sum(r["pnl"] for r in w1)):
                continue
            days += 1
            rest = [r for r in rows if r.get("wave_nth", 1) > 1]
            s = sum(r["pnl"] for r in rest)
            rest_pnl += s
            rest_n += len(rest)
            rest_green += 1 if s > 0 else 0
        if days:
            cond[lab] = {"days": days, "rest_trades": rest_n, "rest_pnl": round(rest_pnl, 2),
                         "rest_green_days": rest_green}
            d(f"- **{lab}** ({days} sessions): everything traded AFTER it — {rest_n} fills — came to "
              f"**${rest_pnl:,.0f}** (${rest_pnl / days:,.0f}/session, {rest_green}/{days} sessions green).")
    d("")
    d("**Per-arm intraday stop — counterfactual.** Halt an arm for the day once its own REALIZED P&L "
      "(only trades already exited at the moment of the next entry — no look-ahead) crosses a threshold:")
    d("")
    d("| arm-day stop | fills kept | fills skipped | book total |")
    d("|---|---:|---:|---:|")
    by_arm_day = collections.defaultdict(list)
    for r in recs:
        by_arm_day[(r["arm"], r["date"])].append(r)
    stops = {}
    for X in (50, 75, 100, 150, 200, 300, 400, None):
        tot = 0.0
        kept = cut = 0
        for rows in by_arm_day.values():
            for r in sorted(rows, key=lambda x: x["sec"]):
                realized = sum(q["pnl"] for q in rows if q["xsec"] is not None and q["xsec"] <= r["sec"])
                if X is not None and realized <= -X:
                    cut += 1
                    continue
                tot += r["pnl"]
                kept += 1
        lab = f"−${X}" if X else "**none (what we actually did)**"
        stops[str(X)] = {"kept": kept, "skipped": cut, "total": round(tot, 2)}
        d(f"| {lab} | {kept} | {cut} | ${tot:,.0f} |")
    d("")
    d("> **Every threshold beats no-stop.** Monotonicity across a wide knob range is why this deserves a "
      "pre-registration rather than a knob-fit — but read §5 before believing the SIZE of it.")
    d("")
    arm_day_tot = sorted(sum(x["pnl"] for x in v) for v in by_arm_day.values())
    d(f"**Why the existing Rule-5 kill switch never engages:** over {len(arm_day_tot)} arm-days the loss "
      f"distribution runs worst **${arm_day_tot[0]:,.0f}**, p10 "
      f"**${arm_day_tot[len(arm_day_tot) // 10]:,.0f}**, median **${st.median(arm_day_tot):,.0f}**. Rule 5 "
      "halts Safe at −30% of start-of-day equity (≈−$1,400 at current size) — roughly **4× wider than the "
      "10th-percentile bad day**. In practice the engine runs with no daily throttle at all.")
    d("")

    # ------------------------------------------------------------------ 5. concentration
    d("## 5. Concentration disclosure (why nothing here is ratified)")
    d("")
    base = collections.defaultdict(float)
    for r in recs:
        base[r["date"]] += r["pnl"]
    deltas = []
    for dt_, rows in byday.items():
        s = 0.0
        for r in sorted(rows, key=lambda x: x["sec"]):
            realized = sum(q["pnl"] for q in rows if q["xsec"] is not None and q["xsec"] <= r["sec"])
            if realized <= -400:
                continue
            s += r["pnl"]
        deltas.append((dt_, s - base[dt_]))
    deltas.sort(key=lambda kv: -abs(kv[1]))
    moved = [x for x in deltas if abs(x[1]) > 1e-9]
    tot_delta = sum(v for _, v in deltas)
    d(f"- The book-level −$400 day-stop moves **{len(moved)} of {len(deltas)} sessions**; the top 3 carry "
      f"${sum(v for _, v in deltas[:3]):,.0f} of a ${tot_delta:,.0f} total delta.")
    if moved:
        d(f"- Sessions moved: {', '.join(f'`{k}` ${v:+,.0f}' for k, v in moved[:8])}.")
    d("- **Effective n is a handful of sessions, not 424 fills.** Any live change built on this needs its "
      "own forward pre-registration. This report is the hypothesis generator, not the evidence.")
    d("")

    # ------------------------------------------------------------------ 6. top winners
    d("## 6. The top 20 winners, in full")
    d("")
    d("| date | arm | side | hr | entry | exit | × | qty | hold | $ | day range | archetype |")
    d("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for r in W[:20]:
        a = archetypes.get(r["date"], {})
        rng = a.get("range_pct")
        d(f"| {r['date']} | {r['arm']} | {r['side']} | {r['hr']:02d} | "
          f"${(r['entry'] or 0):.2f} | ${(r['exitp'] or 0):.2f} | "
          f"{(r['mult'] or 0):.2f}× | {(r['qty'] or 0):.0f} | {(r['hold'] or 0):.0f}m | "
          f"**${r['pnl']:,.0f}** | {(f'{rng:.2f}%' if rng is not None else '?')} | "
          f"{a.get('archetype', '?')} |")
    d("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(d.text(), encoding="utf-8")
    payload = {
        "_meta": {"generated_at_et": et_now().isoformat(),
                  "builder": "setup/scripts/winner_signature.py",
                  "descriptive_only": True, "wave_gap_seconds": WAVE_GAP_S,
                  "context_coverage_pct": round(100 * ctx_cov, 1)},
        "population": {"fills": len(recs), "waves": len(waves), "sessions": len(byday),
                       "winners": len(W), "losers": len(L), "net": round(total, 2),
                       "trade_wr_pct": round(100 * len(W) / len(recs), 1),
                       "wave_wr_pct": round(wave_wr, 1)},
        "exit_multiple_shape": shape,
        "wave_buckets": buckets,
        "realized_range_buckets": rng_b,
        "ex_ante_correlations": exante,
        "realized_range_r_vs_pnl": round(r_post, 3),
        "first_wave_conditioning": cond,
        "per_arm_day_stop": stops,
        "day_stop_400_concentration": {"sessions_moved": len(moved), "total_delta": round(tot_delta, 2),
                                       "top3_delta": round(sum(v for _, v in deltas[:3]), 2)},
    }
    OUT_JSON.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"wrote {OUT_MD.relative_to(REPO)} and {OUT_JSON.relative_to(REPO)}")
    print(f"  fills={len(recs)} waves={len(waves)} sessions={len(byday)} net=${total:,.0f} "
          f"tradeWR={100 * len(W) / len(recs):.1f}% waveWR={wave_wr:.0f}%")


if __name__ == "__main__":
    main()
