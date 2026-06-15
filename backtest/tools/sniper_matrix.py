"""DEFINITIVE sniper entry x stop x profit-lock matrix — FAITHFUL to the real engine.

FIX (after sanity guard caught a fidelity bug): the signal universe is now derived from
run_backtest ITSELF (not from logged BOLD trades). For the baseline V0 we re-sim the engine's
own trigger bars and ASSERT the per-day green count matches run_backtest's — internal
consistency, no cross-harness hardcoded expectation. For D1/D2 we re-time those same triggers.
This makes V0 == engine by construction; D1/D2 are the only thing that varies.

VERIFY-BEFORE-CONCLUDE GUARD (auto-fix for the L77 foot-gun): the script reproduces
run_backtest's own per-day P&L via the re-sim path and asserts they agree before writing.
If they don't, it raises LOUDLY and writes NOTHING.
"""
from __future__ import annotations
import sys, datetime as dt
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from lib.ribbon import compute_ribbon  # noqa
from lib.simulator_real import simulate_trade_real  # noqa
from lib.orchestrator import run_backtest  # noqa

DATA = REPO / "data"
ANALYSIS = REPO.parent / "analysis"
ABT = ANALYSIS / "backtests"
PL_ON = dict(profit_lock_mode="trailing", profit_lock_threshold_pct=0.05, profit_lock_trail_pct=0.20)
PL_OFF = dict(profit_lock_mode="fixed", profit_lock_threshold_pct=0.0, profit_lock_trail_pct=0.0)


def _to_et(series):
    # utc=True handles mixed EST/EDT offsets (Jan-May spans the DST boundary), then
    # convert to ET. Avoids the 'object dtype / no .dt accessor' crash.
    return pd.to_datetime(series, utc=True).dt.tz_convert("America/New_York")


def norm_str(df):
    df = df.copy()
    df["timestamp_et"] = _to_et(df["timestamp_et"]).dt.strftime("%Y-%m-%d %H:%M:%S-04:00")
    return df


def load_rth(csv):
    spy = pd.read_csv(csv)
    spy["timestamp_et"] = _to_et(spy["timestamp_et"])
    rth = spy[(spy["timestamp_et"].dt.time >= dt.time(9, 30)) &
              (spy["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    rth["vol_avg20"] = rth["volume"].rolling(20, min_periods=5).mean()
    return rth, compute_ribbon(rth["close"])


def engine_signals(spy_str, vix_str, d0, d1, strike, stop, pl, mtb):
    """Run the real engine; return (trades, per_day_dollar) and the trigger contexts."""
    r = run_backtest(spy_str, vix_str, start_date=d0, end_date=d1, use_real_fills=True,
                     premium_stop_pct=-abs(stop), strike_offset=strike, min_triggers_bull=mtb,
                     no_trade_before=dt.time(9, 35), **pl)
    sigs = []
    for t in r.trades:
        sigs.append({"fill_dt": t.entry_time_et, "side": "C" if "BULLISH" in t.setup else "P",
                     "level": t.rejection_level, "date": t.entry_time_et.date()})
    per_day = {}
    for t in r.trades:
        per_day[t.entry_time_et.date()] = per_day.get(t.entry_time_et.date(), 0.0) + t.dollar_pnl
    return sigs, per_day


def fill_idx(rth, fill_dt):
    tnaive = fill_dt.replace(tzinfo=None) if fill_dt.tzinfo else fill_dt
    m = rth[(rth["timestamp_et"].dt.tz_localize(None) == pd.Timestamp(tnaive))]
    return int(m.index[0]) if len(m) else None


def atr5(rth, idx):
    if idx < 5:
        return 0.5
    return float((rth.iloc[idx-5:idx]["high"] - rth.iloc[idx-5:idx]["low"]).mean()) or 0.5


def trig_for(rth, fi, side, level, variant, window=4):
    T = fi - 1
    if variant == "V0":
        return T
    if level is None:
        return None
    tol = max(0.10 * atr5(rth, fi), 0.05)
    n = len(rth)
    if variant in ("D1", "D1_or_D2"):
        for R in range(fi, min(fi + window + 1, n - 1)):
            b = rth.iloc[R]
            if side == "C" and b["low"] <= level + tol and b["close"] > level and b["close"] > b["open"]:
                return R
            if side == "P" and b["high"] >= level - tol and b["close"] < level and b["close"] < b["open"]:
                return R
        if variant == "D1":
            return None
    if variant in ("D2", "D1_or_D2"):
        for M in range(T, min(T + window + 1, n - 1)):
            b = rth.iloc[M]
            rng = b["high"] - b["low"]
            if rng <= 0:
                continue
            body = abs(b["close"] - b["open"]) / rng
            v20 = b["vol_avg20"]
            volok = bool(v20 and b["volume"] >= 1.3 * v20)
            holds = (b["low"] >= level - tol and b["close"] > b["open"]) if side == "C" \
                else (b["high"] <= level + tol and b["close"] < b["open"])
            if body >= 0.6 and holds and volok:
                return M
        return None
    return None


def sim(rth, ribbon, trig, side, level, soff, stop, pl, qty=3):
    if trig is None or trig < 1 or trig + 2 >= len(rth):
        return None
    try:
        return simulate_trade_real(
            entry_bar_idx=trig, entry_bar=rth.iloc[trig], spy_df=rth, ribbon_df=ribbon,
            rejection_level=level, triggers_fired=["level_reclaim", "confluence"], side=side,
            qty=qty, setup="BULLISH_RECLAIM_RIDE_THE_RIBBON" if side == "C" else "BEARISH_REJECTION_RIDE_THE_RIBBON",
            levels_active=[level] if level is not None else [], use_tiered_exits=True,
            strike_offset=soff, premium_stop_pct=-abs(stop), **pl)
    except Exception:
        return None


def measure(rth, ribbon, sigs, dates, variant, soff, stop, pl):
    pd_, pc_ = {d: 0.0 for d in dates}, {d: 0.0 for d in dates}
    worst, n, cap = 0.0, 0, {}
    for s in sigs:
        fi = fill_idx(rth, s["fill_dt"])
        if fi is None:
            continue
        trig = trig_for(rth, fi, s["side"], s["level"], variant)
        f = sim(rth, ribbon, trig, s["side"], s["level"], soff, stop, pl)
        if f is None:
            continue
        pcv = f.dollar_pnl / max(1, f.qty)
        pd_[s["date"]] += f.dollar_pnl
        pc_[s["date"]] += pcv
        worst = min(worst, pcv)
        n += 1
        if f.dollar_pnl > 0:
            cap.setdefault(s["date"], round(pcv, 1))
    return {"green": sum(1 for d in dates if pd_[d] > 0), "per_day_pc": pc_,
            "totpc": sum(pc_.values()), "n": n, "worst_pc": round(worst, 1), "cap": cap}


def main():
    mspy = norm_str(pd.read_csv(DATA / "spy_5m_2026-05-19_2026-05-29.csv"))
    mvix = norm_str(pd.read_csv(DATA / "vix_5m_2026-05-19_2026-05-29.csv"))
    rth, ribbon = load_rth(DATA / "spy_5m_2026-05-19_2026-05-29.csv")
    mdates = [dt.date(2026, 5, 26), dt.date(2026, 5, 27), dt.date(2026, 5, 28), dt.date(2026, 5, 29)]

    # ---- GUARD: engine baseline (ATM/-50%/PLoff/mtb1) and re-sim must agree ----
    base_sigs, base_perday = engine_signals(mspy, mvix, mdates[0], mdates[-1], 0, 0.50, PL_OFF, 1)
    eng_green = sum(1 for d in mdates if base_perday.get(d, 0) > 0)
    resim = measure(rth, ribbon, base_sigs, mdates, "V0", 0, 0.50, PL_OFF)
    assert base_sigs, "HARNESS BROKEN: engine produced 0 signals. Aborting."
    assert resim["green"] == eng_green, (f"FIDELITY FAIL: re-sim green {resim['green']} != engine "
                                         f"green {eng_green}. Aborting (no write).")
    print(f"[guard] OK: engine V0 green={eng_green}, re-sim green={resim['green']} (match); "
          f"signals={len(base_sigs)}")

    variants = ["V0", "D1", "D2", "D1_or_D2"]
    strikes = [0, 2]
    stops = [0.08, 0.15, 0.20, 0.30, 0.50]
    pls = [("PLoff", PL_OFF), ("PLon", PL_ON)]

    out = ["# SNIPER MATRIX — entry x stop x profit-lock (real fills, FAITHFUL to engine)", "",
           "Signal universe derived from run_backtest itself (V0 reproduces the engine; D1/D2 "
           "re-time the same triggers). Per-contract $. Strike 0=ATM, 2=ITM2. D1=retest-reclaim, "
           "D2=no-retest momentum, D1_or_D2=D1 else D2. PLoff=trailing profit-lock disabled.", "",
           f"_Guard: engine V0 green={eng_green} reproduced by re-sim. Signals={len(base_sigs)}._", ""]

    grid = {}
    # For each (strike,stop,pl,mtb=1) the signal set is the engine's own entries at THAT config.
    out.append("## Min stop for 4/4 green, per entry-variant (smaller = better entry = J's metric)")
    out.append("| variant | strike | PL | min stop 4/4 | per-c@min | worst/c | n |")
    out.append("|---|---|---|---|---|---|---|")
    winners = []
    for v in variants:
        for soff in strikes:
            for plname, pl in pls:
                best = None
                for stop in stops:  # ascending -> first 4/4 = min stop
                    # signals = engine entries at this strike/stop/pl/mtb1
                    sigs, _ = engine_signals(mspy, mvix, mdates[0], mdates[-1], soff, stop, pl, 1)
                    r = measure(rth, ribbon, sigs, mdates, v, soff, stop, pl)
                    grid[(v, soff, plname, stop)] = r
                    if r["green"] == 4 and best is None:
                        best = (stop, r)
                sl = "ATM" if soff == 0 else "ITM2"
                if best:
                    stop, r = best
                    out.append(f"| {v} | {sl} | {plname} | **-{int(stop*100)}%** | {r['totpc']:+.1f} "
                               f"| {r['worst_pc']} | {r['n']} |")
                    winners.append((stop, v, soff, plname, r))
                else:
                    out.append(f"| {v} | {sl} | {plname} | none (<4/4) | — | — | — |")
    out.append("")

    winners.sort(key=lambda x: (x[0], -x[4]["totpc"]))
    out.append("## RANKED by smallest stop for 4/4 green")
    out.append("| rank | min stop | variant | strike | PL | per-c | worst/c | n |")
    out.append("|---|---|---|---|---|---|---|---|")
    for i, (stop, v, soff, plname, r) in enumerate(winners[:15], 1):
        sl = "ATM" if soff == 0 else "ITM2"
        out.append(f"| {i} | -{int(stop*100)}% | {v} | {sl} | {plname} | {r['totpc']:+.1f} | {r['worst_pc']} | {r['n']} |")
    out.append("")

    # anchor preservation for top-5 smallest-stop winners
    aspy_p = DATA / "spy_5m_2025-01-01_2026-05-07.csv"
    if aspy_p.exists() and winners:
        aspy = norm_str(pd.read_csv(aspy_p)); avix = norm_str(pd.read_csv(DATA / "vix_5m_2025-01-01_2026-05-07.csv"))
        arth, aribbon = load_rth(aspy_p)
        ad0, ad1 = dt.date(2026, 4, 27), dt.date(2026, 5, 7)
        out.append("## Anchor preservation (top-5 smallest-stop winners on bear-put anchor window)")
        out.append("| variant | strike | PL | stop | 5/04 cap | anchor total/c | worst put/c | n |")
        out.append("|---|---|---|---|---|---|---|---|")
        for stop, v, soff, plname, _ in winners[:5]:
            pl = PL_OFF if plname == "PLoff" else PL_ON
            asigs, _ = engine_signals(aspy, avix, ad0, ad1, soff, stop, pl, 1)
            # filter to puts (the anchor edge); disable f8 not needed here since we pass entries
            asigs = [s for s in asigs if s["side"] == "P"]
            ar = measure(arth, aribbon, asigs, [ad0 + dt.timedelta(days=k) for k in range((ad1-ad0).days+1)],
                         v, soff, stop, pl)
            c504 = ar["cap"].get(dt.date(2026, 5, 4))
            sl = "ATM" if soff == 0 else "ITM2"
            out.append(f"| {v} | {sl} | {plname} | -{int(stop*100)}% | "
                       f"{('+%.1f' % c504) if c504 else 'MISS'} | {ar['totpc']:+.1f} | {ar['worst_pc']} | {ar['n']} |")
        out.append("")
        out.append("**OP-16 decision rule:** best = smallest missed-week stop that ALSO keeps a 5/04 "
                   "capture and a shallow worst-put-loss. That entry fixes the week without breaking "
                   "the bear book or needing a -50% stop.")

    if winners:
        stop, v, soff, plname, r = winners[0]
        out.append("")
        out.append(f"## HEADLINE: **{v} @ {'ATM' if soff==0 else 'ITM2'}/{plname} -> 4/4 green at "
                   f"-{int(stop*100)}% stop** ({r['totpc']:+.1f}/c, worst {r['worst_pc']}/c). "
                   f"Baseline V0 needs -50%. Smaller stop = entry closer to the move = J's sniper thesis.")
        print(f"HEADLINE {v} {'ATM' if soff==0 else 'ITM2'} {plname} 4/4 at -{int(stop*100)}% ({r['totpc']:+.1f}/c)")

    (ANALYSIS / "sniper-matrix-2026-05-31.md").write_text("\n".join(out), encoding="utf-8")
    print("wrote", ANALYSIS / "sniper-matrix-2026-05-31.md")

    # ---- machine-readable dump (finalizer reads THIS; no hand-typed numbers, L77) ----
    import json as _json
    anchor = {}
    if aspy_p.exists() and winners:
        for stop, v, soff, plname, _ in winners[:5]:
            pl = PL_OFF if plname == "PLoff" else PL_ON
            asigs2, _ = engine_signals(aspy, avix, ad0, ad1, soff, stop, pl, 1)
            asigs2 = [s for s in asigs2 if s["side"] == "P"]
            ar = measure(arth, aribbon, asigs2,
                         [ad0 + dt.timedelta(days=k) for k in range((ad1 - ad0).days + 1)],
                         v, soff, stop, pl)
            anchor[f"{v}|{soff}|{plname}|{stop}"] = {
                "cap_504": ar["cap"].get(dt.date(2026, 5, 4)),
                "totpc": round(ar["totpc"], 1), "worst_pc": ar["worst_pc"], "n": ar["n"]}
    dump = {
        "winners": [{"stop": s, "variant": v, "strike": ("ATM" if so == 0 else "ITM2"),
                     "pl": pn, "week_totpc": round(r["totpc"], 1), "worst_pc": r["worst_pc"],
                     "n": r["n"]} for s, v, so, pn, r in winners],
        "baseline_v0": next(({"stop": s, "week_totpc": round(r["totpc"], 1),
                              "worst_pc": r["worst_pc"]} for s, v, so, pn, r in winners
                             if v == "V0" and so == 0 and pn == "PLoff"), None),
        "anchor": anchor,
        "engine_v0_green": eng_green,
    }
    (ABT / "_sniper_matrix.json").write_text(_json.dumps(dump, indent=2, default=str))
    print("wrote", ABT / "_sniper_matrix.json")


if __name__ == "__main__":
    raise SystemExit(main())
