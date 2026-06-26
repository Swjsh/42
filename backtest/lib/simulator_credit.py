"""Multi-leg OPRA-fills simulator for 0DTE SPY CREDIT structures.

THE INVERSION (vs simulator_real.py): we SELL premium. Theta is income; the short
legs PROFIT as their premium falls. Every short leg is paired with a long wing
(defined risk — NO naked legs ever). Built ALONGSIDE simulator_real.py — that file
is NOT edited; we reuse its OPRA loader + fill conventions byte-for-byte.

Reused verbatim from option_pricing_real (the same loader simulator_real uses):
    option_symbol, load_contract_bars, bar_at_or_after, quote_at_index, OptionBar.

Fill conventions mirror simulator_real:
    - Entry on the NEXT 5m bar at/after the entry decision (NO look-ahead).
    - $0.02/leg default slippage. SELLERS pay the half-spread on BOTH open and close;
      BUYERS (wings) pay it both ways too. Modeled per-leg below.
    - tz-naive normalization; min-hold = one bar.
    - Conservative same-bar conflict: STOP before PT.

LEG FILL MODEL
    SHORT leg (sell-to-open): receive BID ~ bar.open - entry_slippage; buy-to-close
        at ASK ~ exit_bar.close + exit_slippage.
    LONG leg (buy-to-open, the wing): pay ASK ~ bar.open + entry_slippage; sell-to-close
        at BID ~ exit_bar.close - exit_slippage.
    entry_fill[leg] = the price we transacted at on open (signed handling below).
    net_credit (per 1-lot, $) = sum_legs( -qty_sign * entry_fill ) * 100.
        PCS: (short_put_bid - long_put_ask) * 100. Must be POSITIVE for a credit
        structure; a day pricing to a DEBIT is SKIPPED + logged (data/band artifact).

INTRADAY MTM (bar-by-bar, entry+1 .. EOD)
    open_pnl(t) = sum_legs[ qty_sign * (entry_fill - current_mark) ] * 100
        (short leg profits as premium falls -> qty_sign=-1 * (entry-mark): when mark<entry
         this is positive). Equivalent to credit + position_value(t).
    bar.close used for MTM/exit decisions. We ALSO compute an intrabar-WORST MTM from
    leg highs/lows (short legs' adverse extreme = bar.high; long legs' adverse = bar.low)
    to FLAG whether a tighter stop would have been hit — bar.close-only understates stop
    hits (the classic premium-seller backtest trap). Both are reported.

EXITS (management grid)
    1. Profit target: open_pnl >= pt_frac * net_credit$ -> close ALL.
    2. Stop: open_pnl <= -stop_mult * net_credit$ -> close ALL. (EOD-only variant via
       stop_mult=None.)
    3. EOD/settlement: 15:50 ET hard (mirror TIME_STOP_ET) mark-to-close DEFAULT;
       or expiry_intrinsic mode (intrinsic at day's SPY close).
    4. Same-bar conflict: STOP before PT.

COSTS
    commission_per_contract (default $0.65; Alpaca paper = $0 — report both). A 4-leg
    IC pays 8 contract-commissions round-trip + 8 spread-crossings. Materially erodes a
    thin credit; in the headline number.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Literal, Optional

import pandas as pd

from .option_pricing_real import (
    OptionBar,
    bar_at_or_after,
    load_contract_bars,
    option_symbol,
    quote_at_index,
)
from .multileg_structures import Leg, max_loss_per_contract
from .simulator import TIME_STOP_ET  # reuse the canonical 15:50 ET hard stop

DEFAULT_ENTRY_SLIPPAGE = 0.02  # byte-for-byte same default as simulator_real
DEFAULT_EXIT_SLIPPAGE = 0.02
DEFAULT_COMMISSION = 0.65      # per contract per side; Alpaca paper = 0.0 (knob)

ExitReasonStr = Literal["PT", "STOP", "EOD", "EXPIRY", "SKIP", "NO_DATA"]
SettleMode = Literal["eod_close_mark", "expiry_intrinsic"]


@dataclass
class LegFill:
    """Per-leg entry/exit record (real cache prices, never synthesized)."""
    strike: int
    side: str
    qty_sign: int           # -1 short / +1 long
    entry_fill: float       # price transacted on OPEN (short=bid, long=ask)
    exit_fill: Optional[float] = None  # price transacted on CLOSE
    entry_bar_open: float = 0.0        # raw cache bar.open (pre-slippage) — provenance
    exit_bar_close: Optional[float] = None


@dataclass
class CreditFill:
    """One multi-leg credit trade result."""
    date: str
    structure: str
    entry_time_et: Optional[dt.datetime] = None
    legs: list[LegFill] = field(default_factory=list)
    net_credit: float = 0.0            # $ per 1-lot (positive for credit)
    max_loss_defined: float = 0.0      # $ per 1-lot (the kill-switch gate number)
    wing_width: int = 0
    contracts: int = 1
    entry_spot: float = 0.0
    exit_reason: ExitReasonStr = "EOD"
    exit_time_et: Optional[dt.datetime] = None
    realized_pnl: float = 0.0          # $ net of slippage + commission, all contracts
    max_favorable: float = 0.0         # best open_pnl over path ($, 1-lot)
    max_adverse: float = 0.0           # worst open_pnl over path ($, 1-lot, bar.close basis)
    intrabar_worst_mtm: float = 0.0    # worst open_pnl using leg intrabar extremes ($, 1-lot)
    realized_pct_otm: float = 0.0      # short-strike %OTM at entry (avg of short legs)
    skipped: bool = False
    skip_reason: str = ""
    commission_total: float = 0.0
    # diagnostic: would a tighter (intrabar) stop have hit when bar.close didn't?
    intrabar_stop_would_hit: bool = False


def _normalize_naive(ts) -> dt.datetime:
    if hasattr(ts, "tz_localize"):
        if ts.tz is not None:
            ts = ts.tz_localize(None)
        return ts.to_pydatetime()
    if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
        return ts.replace(tzinfo=None)
    return ts


def _load_leg_df(date: dt.date, leg: Leg) -> Optional[pd.DataFrame]:
    """Load a leg's OPRA bars (tz-naive). None if not cached (caller SKIPS)."""
    sym = option_symbol(date, leg.strike, leg.side)
    df = load_contract_bars(sym)
    if df is None or df.empty:
        return None
    df = df.copy()
    if df["timestamp_et"].dt.tz is not None:
        df["timestamp_et"] = df["timestamp_et"].dt.tz_localize(None)
    return df


def simulate_credit_trade(
    date: dt.date,
    legs: list[Leg],
    entry_time_et: dt.datetime,
    spot: float,
    wing_width: int,
    structure_name: str = "IC",
    *,
    contracts: int = 1,
    pt_frac: float = 0.50,           # close at +50% of max profit (credit)
    stop_mult: Optional[float] = 2.0,  # close at -200% of credit; None = EOD-only (no stop)
    settle_mode: SettleMode = "eod_close_mark",
    entry_slippage: float = DEFAULT_ENTRY_SLIPPAGE,
    exit_slippage: float = DEFAULT_EXIT_SLIPPAGE,
    commission_per_contract: float = DEFAULT_COMMISSION,
    time_stop_et: dt.time = TIME_STOP_ET,
) -> CreditFill:
    """Combine per-leg OPRA 5m fills into a credit-structure P&L path.

    Returns a CreditFill. On any unpriceable day (missing leg CSV / no entry bar /
    structure prices to a DEBIT) returns a SKIPPED CreditFill (never raises) so the
    runner can tally skip-rate. NO look-ahead: every exit decision uses bars whose
    timestamp <= the current walk bar, and entry fills strictly on the bar AFTER the
    decision time.
    """
    date_str = date.strftime("%Y-%m-%d")
    entry_time_et = _normalize_naive(entry_time_et)
    fill = CreditFill(date=date_str, structure=structure_name, wing_width=wing_width,
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

    # 2) Entry on the NEXT 5m bar at/after the decision (NO look-ahead) — same rule as
    #    simulator_real: decision at entry_time fires at bar CLOSE, fill on next bar open.
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
    # Causality assert: entry bar strictly AFTER the decision time.
    assert actual_entry_ts > entry_time_et, (
        f"look-ahead: entry {actual_entry_ts} <= decision {entry_time_et}")
    fill.entry_time_et = actual_entry_ts

    # 3) Per-leg entry fills: short receives BID (open - slip), long pays ASK (open + slip).
    net_credit = 0.0
    short_pct_otms: list[float] = []
    for leg, eb in zip(legs, entry_bars):
        if leg.qty_sign == -1:  # short / sell-to-open
            entry_fill = max(0.01, eb.open - entry_slippage)
        else:                   # long / buy-to-open (wing)
            entry_fill = eb.open + entry_slippage
        fill.legs.append(LegFill(
            strike=leg.strike, side=leg.side, qty_sign=leg.qty_sign,
            entry_fill=entry_fill, entry_bar_open=eb.open))
        # net_credit = sum( -qty_sign * entry_fill ) * 100 ; short(-1)->+price, long(+1)->-price
        net_credit += (-leg.qty_sign) * entry_fill
        if leg.qty_sign == -1:
            short_pct_otms.append(abs(leg.strike - spot) / spot * 100.0 if spot else 0.0)
    net_credit *= 100.0
    fill.net_credit = net_credit
    fill.realized_pct_otm = sum(short_pct_otms) / len(short_pct_otms) if short_pct_otms else 0.0

    # A credit structure MUST price to a positive credit; debit = data/band artifact -> SKIP.
    if net_credit <= 0:
        fill.skipped = True
        fill.skip_reason = f"non_credit:{net_credit:.2f}"
        return fill

    credit_per_share = net_credit / 100.0
    fill.max_loss_defined = max_loss_per_contract(wing_width, credit_per_share) * contracts

    # 4) Build per-leg index aligned to the entry bar, then walk bar-by-bar.
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

    pt_target = pt_frac * net_credit               # close ALL when open_pnl >= this
    stop_target = (-stop_mult * net_credit) if stop_mult is not None else None

    def _open_pnl_close(marks: list[float]) -> float:
        """open_pnl ($, 1-lot) at bar.close.

        A SHORT leg profits as its premium falls below the entry fill, a LONG leg
        profits as its premium rises. Per-share leg pnl = -qty_sign * (mark - entry)
        = -qty_sign*mark + qty_sign*entry. For a short (-1): +(entry - mark) -> profit
        when mark < entry. For a long (+1): (mark - entry) -> profit when mark > entry.
        """
        pnl = 0.0
        for leg, lf, m in zip(legs, fill.legs, marks):
            pnl += leg.qty_sign * (m - lf.entry_fill)
        return pnl * 100.0

    def _open_pnl_intrabar_worst(highs: list[float], lows: list[float]) -> float:
        """Worst open_pnl using each leg's ADVERSE intrabar extreme.
        Short leg adverse = bar.high (premium spiked up against us); long wing adverse
        = bar.low (wing lost value). Same -qty_sign*(mark-entry) sign convention."""
        pnl = 0.0
        for leg, lf, h, l in zip(legs, fill.legs, highs, lows):
            adverse_mark = h if leg.qty_sign == -1 else l
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
            break  # ran out of bars on some leg -> EOD settle below
        bars = [quote_at_index(leg_dfs[j], idxs[j]) for j in range(n)]
        if any(b is None for b in bars):
            break
        bar_ts = max(b.timestamp_et for b in bars)
        bar_time = bar_ts.time()

        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]

        opnl = _open_pnl_close(closes)
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
        # flag: intrabar-worst would have hit the stop even though bar.close didn't
        if stop_target is not None and opnl > stop_target and opnl_worst <= stop_target:
            fill.intrabar_stop_would_hit = True
        if opnl >= pt_target:
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
        # mark each leg to its FINAL cached bar.close (manage-and-close default) OR
        # expiry intrinsic at the day's last SPY-proxy = use option's own final close
        # for eod_close_mark; for expiry_intrinsic compute intrinsic vs spot-at-close.
        last_bars: list[OptionBar] = []
        for j in range(n):
            last_idx = len(leg_dfs[j]) - 1
            last_bars.append(quote_at_index(leg_dfs[j], last_idx))
        fill.exit_time_et = max(b.timestamp_et for b in last_bars)
        if settle_mode == "expiry_intrinsic":
            # Intrinsic at expiry needs the underlying close. We approximate underlying
            # close from ATM behavior is unreliable; the runner passes spot_close via a
            # thin wrapper. Here, with no underlying, fall back to final bar.close mark
            # (documented divergence) — runner-level expiry uses settle_expiry().
            exit_marks = [b.close for b in last_bars]
            fill.exit_reason = "EOD"
        else:
            exit_marks = [b.close for b in last_bars]
            fill.exit_reason = "EOD"

    # 6) Exit fills: short buys-to-close at ASK (close + slip), long sells at BID (close - slip).
    realized_per_lot = 0.0
    for leg, lf, m in zip(legs, fill.legs, exit_marks):
        if leg.qty_sign == -1:
            exit_fill = m + exit_slippage          # buy-to-close pays the ask
        else:
            exit_fill = max(0.01, m - exit_slippage)  # sell-to-close hits the bid
        lf.exit_fill = exit_fill
        lf.exit_bar_close = m
        # Same sign convention as open_pnl: pnl = qty_sign*(exit - entry).
        # Short(-1): exit<entry -> +; long(+1): exit>entry -> +.
        realized_per_lot += leg.qty_sign * (exit_fill - lf.entry_fill)
    realized_per_lot *= 100.0

    # 7) Commission: per leg per side, both open + close.
    n_legs = len(legs)
    fill.commission_total = commission_per_contract * n_legs * 2 * contracts
    fill.realized_pnl = realized_per_lot * contracts - fill.commission_total
    return fill


def settle_expiry_intrinsic(legs: list[Leg], net_credit: float, spot_close: float,
                            contracts: int = 1,
                            commission_per_contract: float = DEFAULT_COMMISSION) -> float:
    """True 0DTE EXPIRY settlement P&L ($) given the day's SPY close.

    Intrinsic: put = max(0, K - S); call = max(0, S - K). We keep the credit, pay out
    the net intrinsic owed on the combination. No exit slippage (cash-settled at
    expiry); commission still charged on the OPEN only (expired legs aren't traded to
    close). For contrast/robustness vs the manage-and-close default.
    """
    intrinsic_owed = 0.0
    for leg in legs:
        if leg.side == "P":
            intr = max(0.0, leg.strike - spot_close)
        else:
            intr = max(0.0, spot_close - leg.strike)
        # short leg: we OWE intrinsic (negative); long wing: we COLLECT intrinsic (positive)
        intrinsic_owed += (-leg.qty_sign) * intr * 100.0
    # we keep net_credit, settle net intrinsic: pnl = credit - intrinsic_owed... but
    # intrinsic_owed as built is (short owed - long collected); subtract it.
    per_lot = net_credit - intrinsic_owed
    commission = commission_per_contract * len(legs) * contracts  # open only
    return per_lot * contracts - commission
