"""Mine J's real Webull options trade history (2021-2023) -> reconstructed
round-trip trades, P&L, and style analytics.

This is the highest-value ground truth Project Gamma has: J's ACTUAL fills,
not anchors hand-copied into trades.csv. It parses the three Webull export
CSVs, reconstructs round-trip trades per option symbol via FIFO matching
(handling partial fills, scaling in/out, and same-day re-entries), then
computes the style analytics that tell us *what worked for J*.

Scope note
----------
The raw export contains 114 underliers (TSLA, QQQ, AMD, ...). Project Gamma
trades SPY 0DTE; SPX (SPXW), XSP and SPY are the same underlying price action
(SPX ~= 10x SPY), so the **SPX/SPY family** is the primary analysis subject.
Every trade is still parsed and the non-family universe is summarised
separately so nothing is hidden.

Outputs (written by --write):
  analysis/webull-j-trades/j_roundtrips.csv   -- every reconstructed round-trip
  analysis/webull-j-trades/j_roundtrips.json  -- same, structured + top winners
  analysis/webull-j-trades/j_style_stats.json -- aggregate style analytics
  analysis/webull-j-trades/winner_candles.json -- (optional) SPY candle context

Pure stdlib + pandas. py_compile clean. $0 cost.

Usage:
    python -m autoresearch.webull_history_miner            # analyse + print
    python -m autoresearch.webull_history_miner --write     # + write outputs
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import statistics
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent  # .../42
WEBULL_DIR = REPO / "docs" / "WeBull History"
OUT_DIR = REPO / "analysis" / "webull-j-trades"

# SPX/SPY family = same underlying price action (SPX ~= 10x SPY). Primary subject.
SPX_FAMILY = frozenset({"SPXW", "SPX", "SPY", "XSP"})

# OCC-style symbol: TICKER + YYMMDD + C|P + strike*1000 (8 zero-padded digits)
_SYMBOL_RE = re.compile(r"^([A-Z]+?)(\d{6})([CP])(\d{8})$")
# Avg Price / Price fields sometimes carry a leading '@'
_NUM_RE = re.compile(r"[-+]?\d*\.?\d+")


# --------------------------------------------------------------------------- #
# Parsing primitives
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ParsedSymbol:
    underlier: str
    expiry: dt.date
    right: str          # "C" or "P"
    strike: float
    is_spx_family: bool


def parse_symbol(symbol: str) -> Optional[ParsedSymbol]:
    """Parse an OCC-style option symbol. Returns None if it doesn't match."""
    m = _SYMBOL_RE.match(str(symbol).strip())
    if not m:
        return None
    under, ymd, right, strike_raw = m.groups()
    try:
        expiry = dt.datetime.strptime(ymd, "%y%m%d").date()
    except ValueError:
        return None
    strike = int(strike_raw) / 1000.0
    return ParsedSymbol(
        underlier=under,
        expiry=expiry,
        right=right,
        strike=strike,
        is_spx_family=under in SPX_FAMILY,
    )


def parse_price(raw: Any) -> Optional[float]:
    """Parse '@1.55', '1.55', '0.020' -> float. None if blank/unparseable."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return None
    m = _NUM_RE.search(s)
    return float(m.group(0)) if m else None


def parse_filled_time(raw: Any) -> Optional[dt.datetime]:
    """Parse '10/03/2023 12:36:56 EDT' -> naive ET datetime.

    Webull stamps the local market timezone (EST/EDT) explicitly; both are
    Eastern, so we strip the suffix and treat the clock time as naive ET
    (matching the engine's `entry_time_et` convention, lesson C6/L161).
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return None
    # Drop trailing timezone token (EST/EDT/...).
    parts = s.rsplit(" ", 1)
    if len(parts) == 2 and parts[1].isalpha():
        s = parts[0]
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------- #
# Fill loading
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Fill:
    symbol: str
    side: str               # "Buy" / "Sell"
    qty: int
    price: float
    filled_time: dt.datetime
    parsed: ParsedSymbol


def load_fills(webull_dir: Path = WEBULL_DIR) -> list[Fill]:
    """Load all Status==Filled rows across every year, parse + validate."""
    csvs = sorted(webull_dir.glob("*/Webull_Orders_Records_Options.csv"))
    if not csvs:
        raise FileNotFoundError(f"no Webull CSVs under {webull_dir}")
    frames = [pd.read_csv(p) for p in csvs]
    df = pd.concat(frames, ignore_index=True)
    # DATA-QUALITY: the yearly exports overlap heavily — the "2023" file
    # actually carries 1,574 rows of 2022 data, so the raw concat contains
    # ~1,890 exact-duplicate fills. Drop them before reconstruction or every
    # overlapping trade is double-counted (lesson C7 / dedupe-by-key).
    n_before = len(df)
    df = df.drop_duplicates()
    n_dropped = n_before - len(df)
    if n_dropped:
        print(f"[load_fills] dropped {n_dropped} exact-duplicate rows "
              f"(yearly exports overlap)")
    df = df[df["Status"] == "Filled"].copy()

    fills: list[Fill] = []
    skipped = 0
    for _, row in df.iterrows():
        parsed = parse_symbol(row["Symbol"])
        ft = parse_filled_time(row.get("Filled Time"))
        # Prefer Avg Price (actual execution), fall back to Price.
        px = parse_price(row.get("Avg Price"))
        if px is None:
            px = parse_price(row.get("Price"))
        # Filled qty: the "Filled" column is the executed quantity.
        try:
            qty = int(float(row.get("Filled")))
        except (TypeError, ValueError):
            qty = 0
        if parsed is None or ft is None or px is None or qty <= 0:
            skipped += 1
            continue
        side = str(row["Side"]).strip()
        if side not in ("Buy", "Sell"):
            skipped += 1
            continue
        fills.append(
            Fill(symbol=str(row["Symbol"]).strip(), side=side, qty=qty,
                 price=px, filled_time=ft, parsed=parsed)
        )
    fills.sort(key=lambda f: f.filled_time)
    if skipped:
        print(f"[load_fills] skipped {skipped} unparseable/blank filled rows")
    return fills


# --------------------------------------------------------------------------- #
# Round-trip reconstruction (FIFO)
# --------------------------------------------------------------------------- #
@dataclass
class RoundTrip:
    symbol: str
    underlier: str
    right: str                       # C / P
    bias: str                        # bull (call) / bear (put)
    strike: float
    expiry: dt.date
    is_spx_family: bool
    qty: int                         # matched contracts
    entry_time: dt.datetime
    exit_time: dt.datetime
    entry_px: float                  # qty-weighted avg buy price for this match
    exit_px: float                   # qty-weighted avg sell price for this match
    pnl: float                       # $ = (exit_px - entry_px) * qty * 100
    hold_minutes: float
    is_0dte: bool
    status: str = "closed"           # closed | unclosed | expired_worthless
    n_entry_fills: int = 1           # scaling-in fills consumed
    n_exit_fills: int = 1            # scaling-out fills consumed

    @property
    def is_win(self) -> bool:
        return self.pnl > 0

    def entry_date(self) -> dt.date:
        return self.entry_time.date()

    def entry_hhmm(self) -> str:
        return self.entry_time.strftime("%H:%M")

    def exit_hhmm(self) -> str:
        return self.exit_time.strftime("%H:%M")


@dataclass
class _Lot:
    """An open long lot awaiting a matching sell (FIFO)."""
    qty: int
    price: float
    time: dt.datetime
    n_fills: int = 1


def reconstruct_round_trips(fills: list[Fill]) -> tuple[list[RoundTrip], list[dict]]:
    """FIFO-match Buy fills to Sell fills per symbol.

    J trades long options (buys to open, sells to close). We treat Buys as
    opening long lots and Sells as closing them FIFO. A Sell with no
    preceding Buy (rare data artefact) is logged as an anomaly, not a trade.
    Leftover Buys at end = unclosed (held to expiry); if 0DTE we mark them
    expired_worthless (-100% premium) and still book the loss.

    Returns (round_trips, anomalies).
    """
    by_symbol: dict[str, list[Fill]] = {}
    for f in fills:
        by_symbol.setdefault(f.symbol, []).append(f)

    trips: list[RoundTrip] = []
    anomalies: list[dict] = []

    for symbol, sym_fills in by_symbol.items():
        sym_fills.sort(key=lambda f: f.filled_time)
        open_lots: deque[_Lot] = deque()
        p = sym_fills[0].parsed

        for f in sym_fills:
            if f.side == "Buy":
                open_lots.append(_Lot(qty=f.qty, price=f.price, time=f.filled_time))
                continue
            # Sell: consume open lots FIFO.
            remaining = f.qty
            if not open_lots:
                anomalies.append({
                    "symbol": symbol, "type": "sell_without_open",
                    "qty": f.qty, "price": f.price,
                    "time": f.filled_time.isoformat(),
                })
                continue
            # Accumulate the matched legs into ONE round-trip per sell fill,
            # weighting entry price across however many lots it spans.
            matched_qty = 0
            entry_cost = 0.0
            first_entry_time = None
            n_entry_fills = 0
            while remaining > 0 and open_lots:
                lot = open_lots[0]
                take = min(remaining, lot.qty)
                matched_qty += take
                entry_cost += take * lot.price
                n_entry_fills += 1
                if first_entry_time is None:
                    first_entry_time = lot.time
                lot.qty -= take
                remaining -= take
                if lot.qty == 0:
                    open_lots.popleft()
            if matched_qty == 0:
                continue
            entry_px = entry_cost / matched_qty
            exit_px = f.price
            pnl = (exit_px - entry_px) * matched_qty * 100.0
            hold = (f.filled_time - first_entry_time).total_seconds() / 60.0
            trips.append(RoundTrip(
                symbol=symbol, underlier=p.underlier, right=p.right,
                bias="bull" if p.right == "C" else "bear",
                strike=p.strike, expiry=p.expiry, is_spx_family=p.is_spx_family,
                qty=matched_qty, entry_time=first_entry_time, exit_time=f.filled_time,
                entry_px=entry_px, exit_px=exit_px, pnl=pnl, hold_minutes=hold,
                is_0dte=(p.expiry == f.filled_time.date()),
                status="closed", n_entry_fills=n_entry_fills, n_exit_fills=1,
            ))
            if remaining > 0:
                anomalies.append({
                    "symbol": symbol, "type": "sell_overflow",
                    "unmatched_qty": remaining, "time": f.filled_time.isoformat(),
                })

        # Leftover open lots: unclosed / expired worthless.
        for lot in open_lots:
            is_0dte = p.expiry == lot.time.date()
            if is_0dte:
                # 0DTE held to expiry with no sell record -> expired worthless.
                pnl = -lot.price * lot.qty * 100.0
                status = "expired_worthless"
                exit_px = 0.0
                exit_time = lot.time.replace(hour=16, minute=0, second=0)
            else:
                # Longer-dated, no sell in dataset -> can't value. Mark unclosed.
                pnl = 0.0
                status = "unclosed"
                exit_px = lot.price
                exit_time = lot.time
            trips.append(RoundTrip(
                symbol=symbol, underlier=p.underlier, right=p.right,
                bias="bull" if p.right == "C" else "bear",
                strike=p.strike, expiry=p.expiry, is_spx_family=p.is_spx_family,
                qty=lot.qty, entry_time=lot.time, exit_time=exit_time,
                entry_px=lot.price, exit_px=exit_px, pnl=pnl,
                hold_minutes=(exit_time - lot.time).total_seconds() / 60.0,
                is_0dte=is_0dte, status=status,
                n_entry_fills=1, n_exit_fills=0,
            ))

    trips.sort(key=lambda t: t.entry_time)
    return trips, anomalies


# --------------------------------------------------------------------------- #
# Style analytics (Step 2)
# --------------------------------------------------------------------------- #
def _safe_mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return float(statistics.mean(xs)) if xs else 0.0


def _safe_median(xs: Iterable[float]) -> float:
    xs = list(xs)
    return float(statistics.median(xs)) if xs else 0.0


def _bucket_hour(d: dt.datetime) -> str:
    """30-min entry bucket label, e.g. '09:30', '10:00'."""
    minute = 0 if d.minute < 30 else 30
    return f"{d.hour:02d}:{minute:02d}"


def _wr(trips: list[RoundTrip]) -> dict[str, Any]:
    """Win-rate / expectancy block for a set of *closed* trips."""
    closed = [t for t in trips if t.status in ("closed", "expired_worthless")]
    n = len(closed)
    wins = [t for t in closed if t.is_win]
    losses = [t for t in closed if not t.is_win]
    total_pnl = sum(t.pnl for t in closed)
    avg_win = _safe_mean(t.pnl for t in wins)
    avg_loss = _safe_mean(t.pnl for t in losses)
    wr = len(wins) / n if n else 0.0
    expectancy = total_pnl / n if n else 0.0
    profit_factor = (
        sum(t.pnl for t in wins) / abs(sum(t.pnl for t in losses))
        if losses and sum(t.pnl for t in losses) != 0 else float("inf")
    )
    return {
        "n": n, "wins": len(wins), "losses": len(losses),
        "win_rate": round(wr, 4),
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "expectancy_per_trade": round(expectancy, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else None,
    }


def _dist(label_fn, trips: list[RoundTrip]) -> dict[str, dict[str, Any]]:
    """Group closed trips by a label fn -> per-group WR block, sorted by key."""
    groups: dict[str, list[RoundTrip]] = {}
    for t in trips:
        if t.status not in ("closed", "expired_worthless"):
            continue
        groups.setdefault(label_fn(t), []).append(t)
    return {k: _wr(v) for k, v in sorted(groups.items())}


def compute_style_stats(trips: list[RoundTrip]) -> dict[str, Any]:
    """Full Step-2 style breakdown, primary subject = SPX/SPY family."""
    fam = [t for t in trips if t.is_spx_family]
    non_fam = [t for t in trips if not t.is_spx_family]
    fam_closed = [t for t in fam if t.status in ("closed", "expired_worthless")]

    stats: dict[str, Any] = {}
    stats["overall_spx_family"] = _wr(fam)
    stats["overall_all_underliers"] = _wr(trips)
    stats["non_family_summary"] = _wr(non_fam)

    # By year (family).
    stats["by_year"] = _dist(lambda t: str(t.entry_date().year), fam)

    # Call vs put (directional bias) — family.
    stats["call_vs_put"] = _dist(lambda t: t.bias, fam)

    # 0DTE vs longer-dated — family.
    stats["dte_split"] = _dist(lambda t: "0DTE" if t.is_0dte else "longer_dated", fam)

    # Entry time-of-day distribution — winners vs losers (family).
    win_times = _dist(_bucket_hour_label, [t for t in fam_closed if t.is_win])
    loss_times = _dist(_bucket_hour_label, [t for t in fam_closed if not t.is_win])
    stats["entry_time_of_day"] = {
        "winners": {k: v["n"] for k, v in win_times.items()},
        "losers": {k: v["n"] for k, v in loss_times.items()},
        "per_bucket_wr": _dist(_bucket_hour_label, fam_closed),
    }

    # Hold duration — winners vs losers (family, closed only).
    win_holds = [t.hold_minutes for t in fam_closed if t.is_win]
    loss_holds = [t.hold_minutes for t in fam_closed if not t.is_win]
    stats["hold_minutes"] = {
        "winners": {
            "mean": round(_safe_mean(win_holds), 1),
            "median": round(_safe_median(win_holds), 1),
            "n": len(win_holds),
        },
        "losers": {
            "mean": round(_safe_mean(loss_holds), 1),
            "median": round(_safe_median(loss_holds), 1),
            "n": len(loss_holds),
        },
    }

    # Day-of-week (family).
    stats["day_of_week"] = _dist(
        lambda t: f"{t.entry_date().weekday()}_{t.entry_date().strftime('%a')}", fam
    )

    # Scaling behaviour: trades whose entry consumed multiple fills (scaled in)
    # vs single-fill entries (family).
    stats["scaling"] = {
        "scaled_in": _wr([t for t in fam if t.n_entry_fills > 1]),
        "single_entry": _wr([t for t in fam if t.n_entry_fills == 1]),
        "by_size": _dist(_size_bucket_label, fam),
    }

    # Top 10 winners / losers (family, closed).
    closed_sorted = sorted(fam_closed, key=lambda t: t.pnl)
    stats["top_10_losers"] = [_trip_detail(t) for t in closed_sorted[:10]]
    stats["top_10_winners"] = [_trip_detail(t) for t in reversed(closed_sorted[-10:])]

    # Data-quality footnote.
    stats["data_quality"] = {
        "total_round_trips_all": len(trips),
        "spx_family_round_trips": len(fam),
        "spx_family_closed": len(fam_closed),
        "unclosed_or_expired": len([t for t in trips if t.status != "closed"]),
    }
    return stats


def _bucket_hour_label(t: RoundTrip) -> str:
    return _bucket_hour(t.entry_time)


def _size_bucket_label(t: RoundTrip) -> str:
    if t.qty <= 2:
        return "1-2"
    if t.qty <= 5:
        return "3-5"
    if t.qty <= 10:
        return "6-10"
    return "11+"


def _trip_detail(t: RoundTrip) -> dict[str, Any]:
    return {
        "date": t.entry_date().isoformat(),
        "symbol": t.symbol,
        "underlier": t.underlier,
        "bias": t.bias,
        "right": t.right,
        "strike": t.strike,
        "expiry": t.expiry.isoformat(),
        "is_0dte": t.is_0dte,
        "qty": t.qty,
        "entry_time": t.entry_hhmm(),
        "exit_time": t.exit_hhmm(),
        "hold_min": round(t.hold_minutes, 1),
        "entry_px": round(t.entry_px, 3),
        "exit_px": round(t.exit_px, 3),
        "pnl": round(t.pnl, 2),
        "result": "WIN" if t.is_win else "LOSS",
        "status": t.status,
    }


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
_CSV_COLS = [
    "date", "symbol", "underlier", "is_spx_family", "bias", "right", "strike",
    "expiry", "is_0dte", "qty", "entry_time", "exit_time", "hold_min",
    "entry_px", "exit_px", "pnl", "result", "status", "n_entry_fills",
]


def round_trips_to_rows(trips: list[RoundTrip]) -> list[dict[str, Any]]:
    rows = []
    for t in trips:
        rows.append({
            "date": t.entry_date().isoformat(),
            "symbol": t.symbol,
            "underlier": t.underlier,
            "is_spx_family": t.is_spx_family,
            "bias": t.bias,
            "right": t.right,
            "strike": t.strike,
            "expiry": t.expiry.isoformat(),
            "is_0dte": t.is_0dte,
            "qty": t.qty,
            "entry_time": t.entry_time.strftime("%Y-%m-%d %H:%M:%S"),
            "exit_time": t.exit_time.strftime("%Y-%m-%d %H:%M:%S"),
            "hold_min": round(t.hold_minutes, 1),
            "entry_px": round(t.entry_px, 3),
            "exit_px": round(t.exit_px, 3),
            "pnl": round(t.pnl, 2),
            "result": "WIN" if t.is_win else "LOSS",
            "status": t.status,
            "n_entry_fills": t.n_entry_fills,
        })
    return rows


def write_outputs(trips: list[RoundTrip], stats: dict[str, Any],
                  anomalies: list[dict], out_dir: Path = OUT_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    rows = round_trips_to_rows(trips)
    df = pd.DataFrame(rows, columns=_CSV_COLS)
    csv_path = out_dir / "j_roundtrips.csv"
    df.to_csv(csv_path, index=False)
    written.append(csv_path)

    json_path = out_dir / "j_roundtrips.json"
    json_path.write_text(json.dumps({
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "n_round_trips": len(trips),
        "anomalies": anomalies,
        "round_trips": rows,
    }, indent=2), encoding="utf-8")
    written.append(json_path)

    stats_path = out_dir / "j_style_stats.json"
    stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    written.append(stats_path)

    return written


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print_summary(stats: dict[str, Any]) -> None:
    o = stats["overall_spx_family"]
    print("=" * 78)
    print("J'S WEBULL OPTIONS HISTORY — SPX/SPY FAMILY (primary subject)")
    print("=" * 78)
    print(f"  round-trips: {o['n']}   WR: {o['win_rate']:.1%}   "
          f"total P&L: ${o['total_pnl']:,.0f}")
    print(f"  avg win: ${o['avg_win']:,.0f}   avg loss: ${o['avg_loss']:,.0f}   "
          f"expectancy/trade: ${o['expectancy_per_trade']:,.0f}   "
          f"PF: {o['profit_factor']}")
    print()
    print("  BY YEAR:")
    for yr, b in stats["by_year"].items():
        print(f"    {yr}: n={b['n']:>4}  WR={b['win_rate']:.1%}  "
              f"P&L=${b['total_pnl']:>9,.0f}  exp=${b['expectancy_per_trade']:>6,.0f}")
    print()
    print("  CALL vs PUT:")
    for k, b in stats["call_vs_put"].items():
        print(f"    {k:<5}: n={b['n']:>4}  WR={b['win_rate']:.1%}  "
              f"P&L=${b['total_pnl']:>9,.0f}  exp=${b['expectancy_per_trade']:>6,.0f}")
    print()
    print("  0DTE vs LONGER:")
    for k, b in stats["dte_split"].items():
        print(f"    {k:<12}: n={b['n']:>4}  WR={b['win_rate']:.1%}  "
              f"P&L=${b['total_pnl']:>9,.0f}  exp=${b['expectancy_per_trade']:>6,.0f}")
    print()
    print("  HOLD MINUTES (winners vs losers):")
    h = stats["hold_minutes"]
    print(f"    winners: mean={h['winners']['mean']}  median={h['winners']['median']}  n={h['winners']['n']}")
    print(f"    losers : mean={h['losers']['mean']}  median={h['losers']['median']}  n={h['losers']['n']}")
    print()
    print("  ENTRY TIME-OF-DAY WR (closed family):")
    for k, b in stats["entry_time_of_day"]["per_bucket_wr"].items():
        print(f"    {k}: n={b['n']:>4}  WR={b['win_rate']:.1%}  exp=${b['expectancy_per_trade']:>6,.0f}")
    print()
    print("  TOP 5 WINNERS:")
    for d in stats["top_10_winners"][:5]:
        print(f"    {d['date']} {d['symbol']:<20} {d['bias']:<4} 0DTE={str(d['is_0dte']):<5} "
              f"x{d['qty']:<3} {d['entry_time']}->{d['exit_time']} "
              f"${d['entry_px']}->${d['exit_px']}  pnl=${d['pnl']:>8,.0f}")
    print()
    print("  TOP 5 LOSERS:")
    for d in stats["top_10_losers"][:5]:
        print(f"    {d['date']} {d['symbol']:<20} {d['bias']:<4} 0DTE={str(d['is_0dte']):<5} "
              f"x{d['qty']:<3} {d['entry_time']}->{d['exit_time']} "
              f"${d['entry_px']}->${d['exit_px']}  pnl=${d['pnl']:>8,.0f}")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="write outputs to analysis/")
    args = ap.parse_args(argv)

    fills = load_fills()
    print(f"[main] loaded {len(fills)} filled fills")
    trips, anomalies = reconstruct_round_trips(fills)
    print(f"[main] reconstructed {len(trips)} round-trips "
          f"({len(anomalies)} anomalies)")
    stats = compute_style_stats(trips)
    _print_summary(stats)

    if args.write:
        written = write_outputs(trips, stats, anomalies)
        print()
        print("[main] wrote:")
        for p in written:
            print(f"  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
