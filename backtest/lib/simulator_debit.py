"""Multi-leg OPRA-fills simulator for 0DTE SPY DEBIT verticals.

THE INVERSION OF THE INVERSION
    simulator_credit.py SELLS premium (net_credit > 0, theta = income). A DEBIT
    vertical is the mirror image: we BUY the near strike + SELL a further-OTM strike
    on the SAME side -> net DEBIT paid at entry. Max gain = (width - debit); max loss
    = the debit. The short leg CAPS the upside but cuts cost, theta, vega, and whipsaw.

WHY A SEPARATE THIN MODULE (not just calling simulate_credit_trade)
    The credit sim's intraday engine -- per-leg OPRA fills, the bar-by-bar open_pnl
    walk (qty_sign * (mark - entry_fill)), the intrabar-worst MTM flag, the
    STOP-before-PT conflict rule -- is SIGN-AGNOSTIC and already correct for ANY
    signed-qty leg combo, debit included. The ONLY credit-specific pieces are:
      (a) the net_credit <= 0 -> SKIP guard (credit sim REJECTS a debit; here it is
          the EXPECTED, REQUIRED sign);
      (b) PT/STOP expressed as a fraction of the *credit collected* -- for a debit we
          express them as a fraction of the *debit paid* (the cost basis / max loss);
      (c) expiry intrinsic settled as "keep credit, owe net intrinsic" -- for a debit
          it is "pay debit, collect net intrinsic".
    So we reuse the credit sim's loader + Leg + helpers BYTE-FOR-BYTE and re-walk with
    the three debit-correct substitutions. simulator_real.py is NOT touched.

LEG FILL MODEL (identical conventions to simulator_credit / simulator_real)
    LONG leg  (buy-to-open):  pay ASK ~ bar.open + entry_slippage; sell-to-close at
        BID ~ exit_bar.close - exit_slippage.
    SHORT leg (sell-to-open): receive BID ~ bar.open - entry_slippage; buy-to-close at
        ASK ~ exit_bar.close + exit_slippage.
    net_debit (per 1-lot, $) = sum_legs( qty_sign * entry_fill ) * 100
        = long_ask - short_bid  for a BUY-near/SELL-far vertical. MUST be POSITIVE for a
        debit structure; a day pricing to a CREDIT is SKIPPED + logged (data/band artifact
        -- the geometry inverted, same defensive posture as the credit sim).

INTRADAY MTM (bar-by-bar, entry+1 .. EOD) -- IDENTICAL math to the credit sim
    open_pnl(t) = sum_legs[ qty_sign * (mark(t) - entry_fill) ] * 100
        LONG (+1): profits as mark RISES above entry. SHORT (-1): profits as mark FALLS.
    For a debit call spread this is correctly bounded in [-debit, width-debit] at expiry.

EXITS (management grid -- fractions of the DEBIT PAID, not a credit)
    1. Profit target: open_pnl >= pt_frac * net_debit$ -> close ALL. (e.g. pt_frac=1.0
       = +100% of debit; the edge's own tp1/runner % map onto this if desired.)
    2. Stop:          open_pnl <= -stop_frac * net_debit$ -> close ALL. stop_frac in (0,1].
       stop_frac=0.50 = lose half the debit; stop_frac=1.0 = let it ride to total loss /
       EOD. None = EOD-only (no premium stop -- the chart-stop-only analogue).
    3. EOD/settlement: 15:50 ET hard, mark-to-close DEFAULT; expiry_intrinsic via settler.
    4. Same-bar conflict: STOP before PT (conservative, mirrors the credit sim).

VALIDATION ANCHORS (see test_simulator_debit.py)
    * Fully-ITM debit call spread (both legs deep ITM at EOD) -> ~ +(width - debit)*100.
    * Fully-OTM (both legs expire worthless) -> ~ -debit*100.
    * Per-leg prices are REAL cache bar values; entry strictly AFTER the decision bar.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Literal, Optional

import pandas as pd

from .option_pricing_real import (
    OptionBar,
    bar_at_or_after,
    quote_at_index,
)
# Reuse the credit sim's leg loader + normalizer BYTE-FOR-BYTE (it reuses
# simulator_real's loader in turn). load_contract_bars is referenced through the
# credit module so the same monkeypatch point works in tests.
from . import simulator_credit as _sc
from .multileg_structures import Leg
from .simulator import TIME_STOP_ET

DEFAULT_ENTRY_SLIPPAGE = _sc.DEFAULT_ENTRY_SLIPPAGE
DEFAULT_EXIT_SLIPPAGE = _sc.DEFAULT_EXIT_SLIPPAGE
DEFAULT_COMMISSION = _sc.DEFAULT_COMMISSION

ExitReasonStr = Literal["PT", "STOP", "EOD", "EXPIRY", "SKIP", "NO_DATA"]
SettleMode = Literal["eod_close_mark", "expiry_intrinsic"]


# ──────────────────────────────────────────────────────────────────────────
# Debit-vertical leg builder (the inverse of build_legs' PCS/CCS)
# ──────────────────────────────────────────────────────────────────────────
def build_debit_vertical(spot: float, side: str, *, near_offset: int = 0,
                         width: int = 1) -> list[Leg]:
    """Legs for a 0DTE SPY DEBIT vertical (directional, defined-risk).

    A debit CALL spread (bullish):  BUY near call (long, +1) + SELL further-OTM call
        (short, -1). long_call = atm + near_offset ; short_call = long_call + width.
    A debit PUT spread (bearish):   BUY near put  (long, +1) + SELL further-OTM put
        (short, -1). long_put  = atm - near_offset ; short_put  = long_put - width.

    Args:
        spot:        underlying SPY price at the entry decision.
        side:        'C' bullish call spread / 'P' bearish put spread.
        near_offset: $ distance of the LONG (near) strike from ATM, in the OTM
                     direction. 0 = ATM long leg (richest, most directional). Negative
                     => ITM long leg (deltas higher, costs more, deeper-money). Mirrors
                     the edge's strike_offset sense (negative = ITM) for the LONG leg.
        width:       $ distance the SHORT (far) leg is FURTHER OTM than the long. >= 1.
                     This is the spread width; max gain = (width - debit).

    Returns legs ordered [LONG (near), SHORT (far)]. The net entry is a DEBIT
    (long_ask - short_bid > 0 for a well-formed near/far vertical).
    """
    if width < 1:
        raise ValueError(f"width must be >= 1, got {width}")
    s = side.upper()
    if s not in ("C", "P"):
        raise ValueError(f"side must be C or P, got {side}")
    atm = int(round(spot))
    if s == "C":
        long_k = atm + near_offset
        short_k = long_k + width
    else:
        long_k = atm - near_offset
        short_k = long_k - width
    return [Leg(long_k, s, +1), Leg(short_k, s, -1)]


@dataclass
class LegFill:
    """Per-leg entry/exit record (real cache prices, never synthesized)."""
    strike: int
    side: str
    qty_sign: int
    entry_fill: float
    exit_fill: Optional[float] = None
    entry_bar_open: float = 0.0
    exit_bar_close: Optional[float] = None


@dataclass
class DebitFill:
    """One multi-leg debit-vertical trade result."""
    date: str
    structure: str
    entry_time_et: Optional[dt.datetime] = None
    legs: list[LegFill] = field(default_factory=list)
    net_debit: float = 0.0             # $ per 1-lot (POSITIVE = paid)
    max_loss_defined: float = 0.0      # $ per 1-lot = net_debit (the most you can lose)
    max_gain_defined: float = 0.0      # $ per 1-lot = (width - debit_per_share)*100
    width: int = 0
    contracts: int = 1
    entry_spot: float = 0.0
    exit_reason: ExitReasonStr = "EOD"
    exit_time_et: Optional[dt.datetime] = None
    realized_pnl: float = 0.0          # $ net of slippage + commission, all contracts
    max_favorable: float = 0.0         # best open_pnl over path ($, 1-lot)
    max_adverse: float = 0.0           # worst open_pnl over path ($, 1-lot, bar.close basis)
    intrabar_worst_mtm: float = 0.0    # worst open_pnl using leg intrabar extremes ($, 1-lot)
    realized_pct_otm: float = 0.0      # LONG (near) strike %OTM at entry
    skipped: bool = False
    skip_reason: str = ""
    commission_total: float = 0.0
    intrabar_stop_would_hit: bool = False


def _load_leg_df(date: dt.date, leg: Leg) -> Optional[pd.DataFrame]:
    """Load a leg's OPRA bars (tz-naive). None if not cached (caller SKIPS).

    Reuses simulator_credit.option_symbol + load_contract_bars (the same loader
    simulator_real uses), so the test monkeypatch point (sc.load_contract_bars) and
    the in-RAM contract cache are shared -- zero drift (C9/C14).
    """
    sym = _sc.option_symbol(date, leg.strike, leg.side)
    df = _sc.load_contract_bars(sym)
    if df is None or df.empty:
        return None
    df = df.copy()
    if df["timestamp_et"].dt.tz is not None:
        df["timestamp_et"] = df["timestamp_et"].dt.tz_localize(None)
    return df


def simulate_debit_trade(
    date: dt.date,
    legs: list[Leg],
    entry_time_et: dt.datetime,
    spot: float,
    width: int,
    structure_name: str = "DEBIT_VERTICAL",
    *,
    contracts: int = 1,
    pt_frac: Optional[float] = 1.0,    # close at +100% of debit (open_pnl >= +debit$)
    stop_frac: Optional[float] = 0.50,  # close at -50% of debit; None = EOD-only (no stop)
    settle_mode: SettleMode = "eod_close_mark",
    entry_slippage: float = DEFAULT_ENTRY_SLIPPAGE,
    exit_slippage: float = DEFAULT_EXIT_SLIPPAGE,
    commission_per_contract: float = DEFAULT_COMMISSION,
    time_stop_et: dt.time = TIME_STOP_ET,
) -> DebitFill:
    """Combine per-leg OPRA 5m fills into a DEBIT-vertical P&L path.

    Returns a DebitFill. On any unpriceable day (missing leg CSV / no entry bar /
    structure prices to a CREDIT) returns a SKIPPED DebitFill (never raises). NO
    look-ahead: every exit decision uses bars whose timestamp <= the current walk bar,
    and entry fills strictly on the bar AFTER the decision time. The intraday open_pnl
    math is byte-identical to the credit sim (sign-agnostic).
    """
    date_str = date.strftime("%Y-%m-%d")
    entry_time_et = _sc._normalize_naive(entry_time_et)
    fill = DebitFill(date=date_str, structure=structure_name, width=width,
                     contracts=contracts, entry_spot=spot,
                     entry_time_et=entry_time_et)

    # 1) Load every leg; SKIP if any missing (band/liquidity artifact).
    leg_dfs: list[pd.DataFrame] = []
    for leg in legs:
        ldf = _load_leg_df(date, leg)
        if ldf is None:
            fill.skipped = True
            fill.skip_reason = f"missing_cache:{leg.side}{leg.strike}"
            return fill
        leg_dfs.append(ldf)

    # 2) Entry on the NEXT 5m bar at/after the decision (NO look-ahead).
    next_bar_start = entry_time_et + dt.timedelta(minutes=5)
    entry_bars: list[OptionBar] = []
    for ldf in leg_dfs:
        eb = bar_at_or_after(ldf, next_bar_start)
        if eb is None or eb.open <= 0:
            fill.skipped = True
            fill.skip_reason = "no_entry_bar"
            return fill
        entry_bars.append(eb)

    actual_entry_ts = max(eb.timestamp_et for eb in entry_bars)
    assert actual_entry_ts > entry_time_et, (
        f"look-ahead: entry {actual_entry_ts} <= decision {entry_time_et}")
    fill.entry_time_et = actual_entry_ts

    # 3) Per-leg entry fills: long pays ASK (open + slip), short receives BID (open - slip).
    net_debit = 0.0
    long_pct_otms: list[float] = []
    for leg, eb in zip(legs, entry_bars):
        if leg.qty_sign == +1:   # long / buy-to-open
            entry_fill = eb.open + entry_slippage
        else:                    # short / sell-to-open
            entry_fill = max(0.01, eb.open - entry_slippage)
        fill.legs.append(LegFill(
            strike=leg.strike, side=leg.side, qty_sign=leg.qty_sign,
            entry_fill=entry_fill, entry_bar_open=eb.open))
        # net_debit = sum( qty_sign * entry_fill ) * 100 ; long(+1)->+price, short(-1)->-price
        net_debit += leg.qty_sign * entry_fill
        if leg.qty_sign == +1:
            long_pct_otms.append(abs(leg.strike - spot) / spot * 100.0 if spot else 0.0)
    net_debit *= 100.0
    fill.net_debit = net_debit
    fill.realized_pct_otm = sum(long_pct_otms) / len(long_pct_otms) if long_pct_otms else 0.0

    # A debit structure MUST price to a positive debit; a credit = data/band artifact -> SKIP.
    if net_debit <= 0:
        fill.skipped = True
        fill.skip_reason = f"non_debit:{net_debit:.2f}"
        return fill

    debit_per_share = net_debit / 100.0
    fill.max_loss_defined = net_debit * contracts
    fill.max_gain_defined = max(0.0, (width - debit_per_share)) * 100.0 * contracts

    # 4) Per-leg index aligned to the entry bar, then walk bar-by-bar.
    leg_entry_idx: list[int] = []
    for ldf, eb in zip(leg_dfs, entry_bars):
        idx = None
        for k in range(len(ldf)):
            if ldf.iloc[k]["timestamp_et"] == eb.timestamp_et:
                idx = k
                break
        if idx is None:
            fill.skipped = True
            fill.skip_reason = "entry_idx_align_fail"
            return fill
        leg_entry_idx.append(idx)

    # PT/STOP as fractions of the DEBIT PAID (cost basis = max loss).
    pt_target = (pt_frac * net_debit) if pt_frac is not None else None  # open_pnl >= +pt*debit
    stop_target = (-stop_frac * net_debit) if stop_frac is not None else None

    def _open_pnl(marks: list[float]) -> float:
        """open_pnl ($, 1-lot). LONG profits as mark rises; SHORT as it falls.
        Per-share leg pnl = qty_sign * (mark - entry). IDENTICAL to the credit sim."""
        pnl = 0.0
        for leg, lf, m in zip(legs, fill.legs, marks):
            pnl += leg.qty_sign * (m - lf.entry_fill)
        return pnl * 100.0

    def _open_pnl_intrabar_worst(highs: list[float], lows: list[float]) -> float:
        """Worst open_pnl using each leg's ADVERSE intrabar extreme.
        LONG adverse = bar.low (it lost value); SHORT adverse = bar.high (premium spiked
        against us). Same qty_sign*(mark-entry) convention as the credit sim."""
        pnl = 0.0
        for leg, lf, h, l in zip(legs, fill.legs, highs, lows):
            adverse_mark = l if leg.qty_sign == +1 else h
            pnl += leg.qty_sign * (adverse_mark - lf.entry_fill)
        return pnl * 100.0

    n = len(leg_dfs)
    offset = 1  # start at entry+1 (min-hold one bar)
    fill.max_favorable = 0.0
    fill.max_adverse = 0.0
    fill.intrabar_worst_mtm = 0.0
    exit_marks: Optional[list[float]] = None

    while True:
        idxs = [leg_entry_idx[j] + offset for j in range(n)]
        if any(idxs[j] >= len(leg_dfs[j]) for j in range(n)):
            break  # ran out of bars -> EOD settle below
        bars = [quote_at_index(leg_dfs[j], idxs[j]) for j in range(n)]
        if any(b is None for b in bars):
            break
        bar_ts = max(b.timestamp_et for b in bars)
        bar_time = bar_ts.time()

        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]

        opnl = _open_pnl(closes)
        opnl_worst = _open_pnl_intrabar_worst(highs, lows)
        if opnl > fill.max_favorable:
            fill.max_favorable = opnl
        if opnl < fill.max_adverse:
            fill.max_adverse = opnl
        if opnl_worst < fill.intrabar_worst_mtm:
            fill.intrabar_worst_mtm = opnl_worst

        time_stop_now = bar_time >= time_stop_et

        # --- EXITS (conservative: STOP before PT) ---
        if stop_target is not None and opnl <= stop_target:
            fill.exit_reason = "STOP"
            fill.exit_time_et = bar_ts
            exit_marks = closes
            break
        if stop_target is not None and opnl > stop_target and opnl_worst <= stop_target:
            fill.intrabar_stop_would_hit = True
        if pt_target is not None and opnl >= pt_target:
            fill.exit_reason = "PT"
            fill.exit_time_et = bar_ts
            exit_marks = closes
            break
        if time_stop_now:
            fill.exit_reason = "EOD"
            fill.exit_time_et = bar_ts
            exit_marks = closes
            break

        offset += 1

    # 5) EOD / settlement if no intraday exit fired.
    if exit_marks is None:
        last_bars: list[OptionBar] = []
        for j in range(n):
            last_idx = len(leg_dfs[j]) - 1
            last_bars.append(quote_at_index(leg_dfs[j], last_idx))
        fill.exit_time_et = max(b.timestamp_et for b in last_bars)
        exit_marks = [b.close for b in last_bars]
        fill.exit_reason = "EOD"

    # 6) Exit fills: long sells-to-close at BID (close - slip), short buys at ASK (close + slip).
    realized_per_lot = 0.0
    for leg, lf, m in zip(legs, fill.legs, exit_marks):
        if leg.qty_sign == +1:
            exit_fill = max(0.01, m - exit_slippage)   # sell-to-close hits the bid
        else:
            exit_fill = m + exit_slippage              # buy-to-close pays the ask
        lf.exit_fill = exit_fill
        lf.exit_bar_close = m
        # pnl = qty_sign*(exit - entry). Long(+1): exit>entry -> +; short(-1): exit<entry -> +.
        realized_per_lot += leg.qty_sign * (exit_fill - lf.entry_fill)
    realized_per_lot *= 100.0

    # 7) Commission: per leg per side, both open + close.
    n_legs = len(legs)
    fill.commission_total = commission_per_contract * n_legs * 2 * contracts
    fill.realized_pnl = realized_per_lot * contracts - fill.commission_total
    return fill


def settle_expiry_intrinsic(legs: list[Leg], net_debit: float, spot_close: float,
                            contracts: int = 1,
                            commission_per_contract: float = DEFAULT_COMMISSION) -> float:
    """True 0DTE EXPIRY settlement P&L ($) for a DEBIT vertical given the SPY close.

    Intrinsic: put = max(0, K - S); call = max(0, S - K). We PAID net_debit and COLLECT
    the net intrinsic of the combination at expiry. For a long(+1)/short(-1) vertical the
    net intrinsic collected = sum( qty_sign * intrinsic ): long collects its intrinsic,
    short owes its intrinsic. P&L per lot = net_intrinsic_collected - net_debit. Bounded
    in [-net_debit, (width - debit)*100]. No exit slippage (cash-settled); commission on
    the OPEN only (expired legs aren't traded to close).
    """
    net_intrinsic = 0.0
    for leg in legs:
        if leg.side == "P":
            intr = max(0.0, leg.strike - spot_close)
        else:
            intr = max(0.0, spot_close - leg.strike)
        net_intrinsic += leg.qty_sign * intr * 100.0
    per_lot = net_intrinsic - net_debit
    commission = commission_per_contract * len(legs) * contracts  # open only
    return per_lot * contracts - commission
