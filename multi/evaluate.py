"""multi/evaluate.py -- the per-ticker evaluation system.

J's ask, verbatim: *"make sure we have a complex evaluation system for each ticker and its
prospective trade."* This is that system. For every name in the universe it answers, on one
readable card and in one JSON record:

    WHY THIS TICKER      liquidity, attention, context regime, structure, and the ZONE MAP
    WHY THIS TRADE       which level, which direction, which filters said yes, which said no
    WHAT IT WOULD COST   contract, premium, spread, size, dollar risk, stop, targets
    WHY NOT              when it is not a candidate, the NAMED reason -- never a silent HOLD

WHAT MAKES IT DIFFERENT FROM THE OLD SHADOW LEDGER. The lane's previous output was 178 opaque
HOLD rows; diagnosing any one of them took manual probing. Every field here is either a real
measured value or an explicit UNAVAILABLE with a reason. There is no third state, and in
particular there is no field that silently defaults to something plausible -- a fabricated
number on a trading surface is worse than a blank one, because a blank one gets investigated.

THE ZONE MAP IS THE CENTREPIECE, and that is a deliberate correction. The 2026-08-20 calibration
proved the production engine's edge lives in its LEVELS: the identical filter stack scores
58.23% at +10min reading curated levels (+4.89 sigma) and 49.06% reading the lane's home-made
ones (-1.63 sigma). Levels are not decoration around the signal; they ARE the signal's
information. So this card shows the tiered, sourced level map for every ticker -- shelves
(supply/demand bands where price actually spent time), pivots, PDH/PDL/PDC, intraday and
premarket extremes -- with distance from spot in both percent and ATR. That is the object J's
market philosophy has always described: *supply/demand zones, wait for the return to the zone,
structure shift at the zone.*

COMPOSED, NOT REBUILT. Every component here already existed and is called through its real
signature: reconstruct_levels_asof (levels), multi.lib.signal (scoring), multi.lib.filters via
core.name_blockers (named blockers), multi.lib.risk (admission), multi.lib.expiry /
multi.lib.sizing (contract + size), multi.lib.context (VIX, level states),
crypto.lib.market_structure (HH/HL/BOS/CHoCH), multi.core (bars, chain, quotes, liquidity).
Rebuilding any of them is how this lane lost a workpackage.

READ-ONLY BY CONSTRUCTION. This module computes and reports. It holds no order path -- pinned
by test_multi_evaluate.py, the same AST guard that protects core.py.

Run:  backtest/.venv/Scripts/python.exe -m multi.evaluate
      backtest/.venv/Scripts/python.exe -m multi.evaluate --symbols NVDA,QQQ --verbose
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from multi import core as mcore  # noqa: E402
from multi.lib import context as mctx  # noqa: E402
from multi.lib import creds as mcreds  # noqa: E402
from multi.lib import expiry as mexp  # noqa: E402
from multi.lib import risk as mrisk  # noqa: E402
from multi.lib import signal as msig  # noqa: E402
from multi.lib import sizing as msize  # noqa: E402
from backtest.lib.reconstruct_levels_asof import reconstruct_levels  # noqa: E402

try:
    from crypto.lib import market_structure as mstruct
except Exception:  # noqa: BLE001 -- structure is enrichment; its absence is reported, not fatal
    mstruct = None

OUT_DIR = REPO / "analysis" / "multi-lane" / "evaluations"
STATE_DIR = REPO / "automation" / "state" / "multi"
PARAMS = STATE_DIR / "params.json"
MULTI_DAY_TIERS = ("Carry", "Reference")

UNAVAILABLE = "UNAVAILABLE"


class Unavailable(dict):
    """An explicitly-absent value carrying WHY. Never silently falsy-equal to a real zero."""

    def __init__(self, reason: str):
        super().__init__(status=UNAVAILABLE, reason=reason)


def _atr(bars: pd.DataFrame, n: int = 14) -> Optional[float]:
    if bars is None or len(bars) < n + 1:
        return None
    h, l, c = bars["high"], bars["low"], bars["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    v = float(tr.tail(n).mean())
    return v if v > 0 else None


def _norm5m(df: pd.DataFrame) -> pd.DataFrame:
    out = df.reset_index()
    out.columns = [str(c).lower() for c in out.columns]
    tcol = next(c for c in out.columns if "time" in c or "date" in c)
    out = out.rename(columns={tcol: "timestamp_et"})
    out["timestamp_et"] = pd.to_datetime(out["timestamp_et"]).dt.tz_localize(None)
    return out[["timestamp_et", "open", "high", "low", "close", "volume"]]


def _norm_daily(df: pd.DataFrame) -> list[dict]:
    out = df.reset_index()
    out.columns = [str(c).lower() for c in out.columns]
    dcol = next(c for c in out.columns if "time" in c or "date" in c)
    return [{"date": pd.Timestamp(r[dcol]).strftime("%Y-%m-%d"), "o": float(r["open"]),
             "h": float(r["high"]), "l": float(r["low"]), "c": float(r["close"]),
             "v": float(r["volume"])} for _, r in out.iterrows()]


# --- the zone map --------------------------------------------------------------------------

def zone_map(symbol: str, bars5: pd.DataFrame, daily: list[dict], spot: float,
             atr: Optional[float], as_of: dt.datetime) -> dict:
    """The tiered, sourced level map -- the object the calibration proved carries the edge.

    Returns levels enriched with distance in percent AND in ATR. ATR-relative distance is the
    scale-invariant one: '$1.20 away' means something completely different on a $40 stock than
    on a $700 index, and a dollar band is precisely the portability defect found in the
    production compiler's own proximity filter.
    """
    try:
        res = reconstruct_levels(as_of_et=as_of, daily_bars=daily,
                                 five_min_df=_norm5m(bars5), spot=spot)
    except Exception as e:  # noqa: BLE001
        return {"status": UNAVAILABLE, "reason": f"level reconstruction raised {type(e).__name__}: {e}",
                "levels": [], "active": [], "multi_day": []}
    if not res.get("ok"):
        return {"status": UNAVAILABLE, "reason": res.get("error") or "reconstructor returned not-ok",
                "levels": [], "active": [], "multi_day": []}

    out, active, multi = [], [], []
    for lv in res.get("levels") or []:
        p = lv.get("price")
        if not isinstance(p, (int, float)):
            continue
        p = float(p)
        dist = p - spot
        rec = {
            "price": round(p, 2),
            "label": lv.get("label"),
            "tier": lv.get("tier"),
            "role": lv.get("role") or lv.get("type"),
            "source": lv.get("source"),
            "is_shelf": "SHELF" in str(lv.get("label") or ""),
            "distance_dollars": round(dist, 2),
            "distance_pct": round(100.0 * dist / spot, 3) if spot else None,
            "distance_atr": round(dist / atr, 2) if atr else None,
            "side": "above" if dist > 0 else "below",
        }
        out.append(rec)
        (multi if lv.get("tier") in MULTI_DAY_TIERS else active).append(p)
    out.sort(key=lambda r: abs(r["distance_dollars"]))
    return {
        "status": "OK", "n_levels": len(out),
        "n_shelves": sum(1 for r in out if r["is_shelf"]),
        "nearest": out[0] if out else None,
        "levels": out, "active": active, "multi_day": multi,
    }


def structure_read(bars5: pd.DataFrame) -> dict:
    """HH/HL/BOS/CHoCH -- 'structure shift at the zone', the second half of J's philosophy."""
    if mstruct is None:
        return {"status": UNAVAILABLE, "reason": "crypto.lib.market_structure not importable"}
    try:
        rows = bars5.tail(300)
        bars = [mstruct.Bar(open_time=t.to_pydatetime(), open=float(o), high=float(h),
                            low=float(l), close=float(cl), volume=float(v),
                            granularity_seconds=300, source="alpaca_5m")
                for t, o, h, l, cl, v in zip(rows.index, rows["open"], rows["high"],
                                             rows["low"], rows["close"], rows["volume"])]
        swings = mstruct.find_swing_points(bars, window=5)
        labeled = mstruct.label_swings(swings)
        trend = mstruct.classify_trend(labeled)
        ev = mstruct.detect_structure_break(bars, swings, trend)
        return {
            "status": "OK",
            "trend": getattr(trend, "value", str(trend)),
            "n_swings": len(labeled),
            "last_swings": [{"kind": s.kind, "label": s.label, "price": round(s.price, 2)}
                            for s in labeled[-4:]],
            "last_event": (None if ev is None else
                           {"kind": ev.kind, "direction": ev.direction,
                            "broken_price": round(ev.broken_price, 2)}),
        }
    except Exception as e:  # noqa: BLE001 -- enrichment: report the failure, never fake a trend
        return {"status": UNAVAILABLE, "reason": f"{type(e).__name__}: {e}"}


# --- the prospective trade ------------------------------------------------------------------

def prospective_trade(symbol: str, side: str, spot: float, params: dict, creds,
                      equity: Optional[float], open_positions: list) -> dict:
    """What the trade would concretely BE if the setup fired right now: contract, premium,
    spread, size, dollar risk, stop, targets. Every leg refuses rather than defaults."""
    right = "call" if side == "C" else "put"
    out: dict[str, Any] = {"side": side, "right": right}

    try:
        chain = mcore.fetch_chain(creds, symbol, right)
    except Exception as e:  # noqa: BLE001
        return {**out, "status": UNAVAILABLE, "reason": f"chain fetch failed: {type(e).__name__}: {e}"}
    if not chain:
        return {**out, "status": UNAVAILABLE, "reason": "option chain returned no contracts"}

    expiries = sorted({c.get("expiration_date") for c in chain if c.get("expiration_date")})
    esel = mexp.select_expiry(symbol=symbol, available_expiries=expiries, params=params)
    if not esel.ok:
        return {**out, "status": "BLOCKED", "reason": f"expiry: {esel.reason}"}
    out["expiry"] = esel.expiry
    out["dte"] = esel.dte

    at_exp = [c for c in chain if c.get("expiration_date") == esel.expiry]
    strikes = sorted({float(c["strike_price"]) for c in at_exp if c.get("strike_price")})
    ssel = msize.select_strike(symbol=symbol, spot=spot, side=side, available_strikes=strikes)
    if not ssel.ok:
        return {**out, "status": "BLOCKED", "reason": f"strike: {ssel.reason}"}
    out["strike"] = ssel.strike
    out["moneyness"] = msize.moneyness(strike=ssel.strike, spot=spot, side=side)

    occ = next((c.get("symbol") for c in at_exp
                if c.get("strike_price") and abs(float(c["strike_price"]) - ssel.strike) < 1e-6), None)
    if not occ:
        return {**out, "status": UNAVAILABLE, "reason": "no OCC symbol for the selected strike"}
    out["contract"] = occ

    quote, qerr = mcore.fetch_option_quote_checked(creds, occ)
    if qerr:
        # An API failure and an illiquid contract are DIFFERENT facts. Collapsing them into one
        # symptom cost this lane a full trading day (lesson: api-error-masqueraded-as-market-
        # condition-2026-08-20). They stay distinguishable here.
        return {**out, "status": UNAVAILABLE, "reason": f"quote ERROR (not illiquidity): {qerr}"}
    if not quote:
        return {**out, "status": "BLOCKED", "reason": "no two-sided quote (genuine market condition)"}

    ok, why, facts = mcore.liquidity_ok(quote, params)
    out["premium"] = facts.get("mid")
    out["spread_pct"] = facts.get("spread_pct")
    out["contract_volume"] = quote.get("volume")
    out["liquidity_ok"] = ok
    out["liquidity_note"] = why
    if not ok:
        return {**out, "status": "BLOCKED", "reason": f"liquidity: {why}"}

    if equity is None:
        return {**out, "status": "PARTIAL",
                "reason": "account equity unavailable -- contract priced, size NOT computed"}
    sz = msize.size_entry(symbol=symbol, equity=equity, premium=out["premium"],
                          params=params, open_positions=open_positions)
    out["contracts"] = sz.contracts
    out["sizing_code"] = sz.code
    out["sizing_note"] = sz.reason
    if not sz.allowed:
        return {**out, "status": "BLOCKED", "reason": f"sizing: {sz.reason}"}

    prem = float(out["premium"])
    cap = ((params.get("exits") or {}).get("catastrophe_cap_pct")
           or (params.get("exits") or {}).get("stop_loss_pct"))
    out["dollar_at_risk"] = round(prem * sz.contracts * 100.0, 2)
    out["pct_of_equity"] = round(100.0 * prem * sz.contracts * 100.0 / equity, 2) if equity else None
    out["catastrophe_cap_pct"] = cap
    out["max_loss_at_cap"] = (round(prem * sz.contracts * 100.0 * abs(float(cap)) / 100.0, 2)
                              if isinstance(cap, (int, float)) else Unavailable(
                                  "no catastrophe cap configured in params.exits"))
    out["status"] = "READY"
    return out


# --- the whole card ------------------------------------------------------------------------

def evaluate_symbol(symbol: str, *, params: dict, creds, bars5: pd.DataFrame,
                    bars_daily: pd.DataFrame, vix: mctx.VixContext,
                    htf: Optional[pd.DataFrame] = None, equity: Optional[float] = None,
                    open_positions: Optional[list] = None,
                    with_trade: bool = True) -> dict:
    """One ticker, fully evaluated. Never raises on a missing input: it reports it."""
    now = mcore.now_et()
    card: dict[str, Any] = {"symbol": symbol, "as_of_et": now.isoformat(timespec="seconds")}
    open_positions = open_positions or []

    if bars5 is None or bars5.empty:
        return {**card, "verdict": "EXCLUDED", "verdict_reason": "no 5-minute bars returned",
                "data_quality": {"bars_5m": UNAVAILABLE}}
    spot = float(bars5["close"].iloc[-1])
    atr = _atr(bars5)
    card["spot"] = round(spot, 2)
    card["atr14_5m"] = round(atr, 3) if atr else None

    # -- context
    card["context"] = {
        "vix": vix.now, "vix_5d_ma": vix.ma_5d, "vix_20d_ma": vix.ma_20d,
        "vix_degraded": vix.degraded, "vix_note": vix.reason,
        "htf_15m_bars": (len(htf) if htf is not None else None),
    }

    # -- attention
    att = mcore.attention_from_bars({symbol: bars5}).get(symbol) or {}
    card["attention"] = att or Unavailable("fewer bars than the relative-volume window needs")

    # -- structure + zones (the two halves of J's philosophy)
    card["structure"] = structure_read(bars5)
    daily = _norm_daily(bars_daily) if bars_daily is not None and not bars_daily.empty else []
    if not daily:
        card["zones"] = {"status": UNAVAILABLE, "reason": "no daily bars -> no shelves/pivots",
                         "levels": [], "active": [], "multi_day": []}
    else:
        card["zones"] = zone_map(symbol, bars5, daily, spot, atr,
                                 now.replace(tzinfo=None))

    # -- the signal
    zones = card["zones"]
    if zones.get("status") != "OK" or not zones.get("active"):
        card["setup"] = {"status": UNAVAILABLE,
                         "reason": f"no active levels ({zones.get('reason', 'none computed')}) "
                                   f"-- the trigger is level-tied, so it cannot be evaluated"}
        card["verdict"] = "BLOCKED"
        card["verdict_reason"] = "no usable zone map"
        return card

    try:
        sig = msig.build_signal(symbol, bars5, params=params,
                               candidate_levels=zones["active"],
                               candidate_multi_day_levels=zones["multi_day"],
                               htf_15m_bars=htf, **vix.as_kwargs())
    except (msig.SignalBuildError, ValueError) as e:
        card["setup"] = {"status": UNAVAILABLE, "reason": f"signal build failed: {e}"}
        card["verdict"] = "BLOCKED"
        card["verdict_reason"] = f"signal error: {e}"
        return card

    action = str(sig.get("action") or "HOLD").upper()
    bear, bull = (sig.get("bear") or {}), (sig.get("bull") or {})
    card["setup"] = {
        "status": "OK", "action": action,
        "bear": {"score": bear.get("score"),
                 "triggers": mcore.name_blockers(bear.get("triggers") or []),
                 "blockers": mcore.name_blockers(bear.get("blockers") or [])},
        "bull": {"score": bull.get("score"),
                 "triggers": mcore.name_blockers(bull.get("triggers") or []),
                 "blockers": mcore.name_blockers(bull.get("blockers") or [])},
        "level_tied_to": zones.get("nearest"),
    }

    if action not in ("ENTER_BULL", "ENTER_BEAR"):
        blocking = (card["setup"]["bull"]["blockers"] + card["setup"]["bear"]["blockers"])
        card["verdict"] = "WATCH"
        card["verdict_reason"] = ("no directional trigger; blocking filters: "
                                  + (", ".join(blocking[:4]) if blocking else "none recorded"))
        return card

    side = "C" if action == "ENTER_BULL" else "P"

    adm = mrisk.evaluate_admission(
        account=(params.get("account") or {}).get("account_number"), symbol=symbol,
        start_of_day_equity=equity, realized_pnl_today=0.0, kill_switch_tripped=False,
        open_positions=open_positions,
        # None = "no correlation matrix supplied", which the correlation gate treats as
        # unknown rather than as zero-correlation. This is a required keyword, not an optional
        # one; omitting it raised TypeError on the FIRST symbol that actually triggered -- a
        # crash no hand-test caught, because the hand-tested symbols all resolved to WATCH and
        # never reached this line.
        correlations=None,
        params=params)
    card["risk_admission"] = {"allowed": adm.allowed, "code": adm.code, "reason": adm.reason}
    if not adm.allowed:
        card["verdict"] = "BLOCKED"
        card["verdict_reason"] = f"risk admission: {adm.reason}"
        return card

    if not with_trade:
        card["verdict"] = "TRADE_CANDIDATE"
        card["verdict_reason"] = f"{action} with risk admitted (contract pricing skipped)"
        return card

    card["prospective_trade"] = prospective_trade(
        symbol, side, spot, params, creds, equity, open_positions)
    st = card["prospective_trade"].get("status")
    card["verdict"] = "TRADE_CANDIDATE" if st == "READY" else "BLOCKED"
    card["verdict_reason"] = (f"{action}, contract ready" if st == "READY"
                              else f"{action} but {card['prospective_trade'].get('reason')}")
    return card


# --- rendering -----------------------------------------------------------------------------

_MARK = {"TRADE_CANDIDATE": "*** TRADE CANDIDATE ***", "WATCH": "watch",
         "BLOCKED": "blocked", "EXCLUDED": "excluded"}


def render_card(c: dict, verbose: bool = False) -> str:
    L: list[str] = []
    W = 78
    L.append("-" * W)
    L.append(f"{c.get('symbol','?'):<6} {_MARK.get(c.get('verdict'), c.get('verdict','?')):<26}"
             f" spot {c.get('spot','?')}   ATR14(5m) {c.get('atr14_5m','?')}")
    L.append(f"       {c.get('verdict_reason','')}")

    z = c.get("zones") or {}
    if z.get("status") == "OK":
        L.append(f"  ZONES  {z['n_levels']} levels ({z['n_shelves']} supply/demand shelves)")
        for lv in (z.get("levels") or [])[: (12 if verbose else 5)]:
            datr = f"{lv['distance_atr']:+.2f} ATR" if lv.get("distance_atr") is not None else "  n/a  "
            L.append(f"         {lv['price']:>9.2f}  {str(lv['tier'] or '?'):<10}"
                     f"{str(lv['role'] or '?'):<11}{lv['distance_pct']:+7.2f}%  {datr:>10}"
                     f"  {'SHELF' if lv['is_shelf'] else ''}  {lv['label'] or ''}")
    else:
        L.append(f"  ZONES  {UNAVAILABLE}: {z.get('reason')}")

    s = c.get("structure") or {}
    if s.get("status") == "OK":
        ev = s.get("last_event")
        L.append(f"  STRUCT trend={s.get('trend')}  swings={s.get('n_swings')}  "
                 f"last_event={(ev['kind'] + ' ' + ev['direction'] + ' @' + str(ev['broken_price'])) if ev else 'none'}")
    else:
        L.append(f"  STRUCT {UNAVAILABLE}: {s.get('reason')}")

    a = c.get("attention") or {}
    if a.get("status") == UNAVAILABLE:
        L.append(f"  ATTN   {UNAVAILABLE}: {a.get('reason')}")
    else:
        L.append(f"  ATTN   rel_volume={a.get('rel_volume')}  " +
                 "  ".join(f"{k}={v}" for k, v in a.items() if k != "rel_volume"))

    ctx = c.get("context") or {}
    L.append(f"  CTX    VIX={ctx.get('vix')} (5d {ctx.get('vix_5d_ma')} / 20d {ctx.get('vix_20d_ma')})"
             + ("  [DEGRADED: " + str(ctx.get("vix_note")) + "]" if ctx.get("vix_degraded") else "")
             + f"  htf_15m_bars={ctx.get('htf_15m_bars')}")

    st = c.get("setup") or {}
    if st.get("status") == "OK":
        for sidename in ("bull", "bear"):
            d = st.get(sidename) or {}
            L.append(f"  {sidename.upper():<6} score={d.get('score')}  "
                     f"triggers={','.join(d.get('triggers') or []) or '-'}")
            L.append(f"         blockers={','.join(d.get('blockers') or []) or '-'}")
    else:
        L.append(f"  SETUP  {UNAVAILABLE}: {st.get('reason')}")

    t = c.get("prospective_trade")
    if t:
        if t.get("status") == "READY":
            L.append(f"  TRADE  {t.get('contract')}  {t.get('moneyness')} strike {t.get('strike')}"
                     f"  exp {t.get('expiry')} (DTE {t.get('dte')})")
            L.append(f"         premium ${t.get('premium')}  spread {t.get('spread_pct')}%"
                     f"  vol {t.get('contract_volume')}  qty {t.get('contracts')}")
            L.append(f"         at risk ${t.get('dollar_at_risk')} ({t.get('pct_of_equity')}% of equity)"
                     f"  cap {t.get('catastrophe_cap_pct')}%  max loss ${t.get('max_loss_at_cap')}")
        else:
            L.append(f"  TRADE  {t.get('status')}: {t.get('reason')}")
    return "\n".join(L)


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--symbols", type=str, default=None, help="default: the funnel watchlist")
    ap.add_argument("--all", action="store_true", help="evaluate the FULL universe, not the funnel")
    ap.add_argument("--top", type=int, default=8, help="how many names to price contracts for")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--no-trade", action="store_true", help="skip chain/quote calls entirely")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    params = json.loads(PARAMS.read_text(encoding="utf-8"))
    creds = mcreds.resolve(params)

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = mcore.universe_symbols(params)
        if not args.all:
            symbols = symbols[: max(args.top, 1)]

    print(f"[evaluate] {len(symbols)} symbols  as of {mcore.now_et().isoformat(timespec='seconds')}",
          flush=True)
    f5 = mcore.fetch_bars_batch(creds, symbols, "5Min", limit=600)
    fd = mcore.fetch_bars_batch(creds, symbols, "1Day", limit=200)
    f15 = mcore.fetch_bars_batch(creds, symbols, "15Min", limit=200)
    vix = mctx.fetch_vix()

    equity = None
    try:
        from multi.lib import broker as mb
        equity = float((mb.get_account(creds) or {}).get("equity") or 0.0) or None
    except Exception as e:  # noqa: BLE001 -- equity is for SIZING; absence is reported, not faked
        print(f"[evaluate] equity unavailable ({type(e).__name__}) -- sizing will be skipped",
              file=sys.stderr)

    cards = []
    for i, sym in enumerate(symbols):
        card = evaluate_symbol(
            sym, params=params, creds=creds, bars5=f5.get(sym), bars_daily=fd.get(sym),
            vix=vix, htf=f15.get(sym), equity=equity, open_positions=[],
            with_trade=(not args.no_trade) and i < args.top)
        cards.append(card)
        print(render_card(card, verbose=args.verbose), flush=True)

    rank = {"TRADE_CANDIDATE": 0, "WATCH": 1, "BLOCKED": 2, "EXCLUDED": 3}
    cards.sort(key=lambda c: rank.get(c.get("verdict"), 9))
    out = args.out or (OUT_DIR / f"evaluation-{mcore.now_et().strftime('%Y-%m-%d')}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "as_of_et": mcore.now_et().isoformat(timespec="seconds"),
        "lane_status": params.get("lane_status"),
        "n_evaluated": len(cards),
        "counts": {k: sum(1 for c in cards if c.get("verdict") == k) for k in rank},
        "cards": cards,
    }, indent=2, default=str), encoding="utf-8")

    print("\n" + "=" * 78)
    for k in rank:
        n = sum(1 for c in cards if c.get("verdict") == k)
        if n:
            names = ", ".join(c["symbol"] for c in cards if c.get("verdict") == k)
            print(f"  {k:<18} {n:>3}   {names}")
    ls = params.get("lane_status") or {}
    if str(ls.get("state") or "").startswith("STOPPED"):
        print(f"\n  NOTE: lane state is {ls.get('state')} -- these are EVALUATIONS, not "
              f"authorizations.\n        Entry requires a signal that passed a gate. See "
              f"{ls.get('verdict')}")
    print(f"[evaluate] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
