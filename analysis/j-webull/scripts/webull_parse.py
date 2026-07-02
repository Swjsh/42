"""Fresh-eyes WeBull order parser + flat-to-flat round-trip reconstructor.

Independent re-derivation (2026-07-01). Does NOT import the 2026-06-19 miner
(backtest/autoresearch/webull_history_miner.py) — conclusions are re-derived
from raw CSV per J's directive.

Unit of analysis: a POSITION EPISODE = flat -> flat per option symbol (FIFO).
This differs from the prior miner (one round-trip per SELL fill); episodes make
n_adds / scale-in / max_qty first-class, which is what the trait analysis needs.
Reconciliation counts vs the prior 667 are reported by the caller.
"""
from __future__ import annotations

import re
from datetime import datetime, date
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
RAW_DIR = REPO / "docs" / "WeBull History"
YEARS = (2021, 2022, 2023)

OCC_RE = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")
FAMILY = {"SPY", "SPX", "SPXW", "XSP"}
# SPY-equivalent spot multiplier for moneyness (SPX ~= 10 x SPY, XSP = SPX/10 ~= SPY)
SPOT_RATIO = {"SPY": 1.0, "SPX": 10.0, "SPXW": 10.0, "XSP": 1.0}


def load_fills() -> tuple[pd.DataFrame, dict]:
    """Load, dedup cross-file, keep filled rows, parse contract + timestamps."""
    frames = []
    for y in YEARS:
        f = RAW_DIR / str(y) / "Webull_Orders_Records_Options.csv"
        df = pd.read_csv(f)
        df["src_file"] = y
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)
    n_raw = len(raw)

    data_cols = [c for c in raw.columns if c != "src_file"]
    deduped = raw.drop_duplicates(subset=data_cols, keep="first")
    n_dupes = n_raw - len(deduped)

    fills = deduped[(deduped["Status"] == "Filled") & (deduped["Filled"] > 0)].copy()
    n_filled = len(fills)

    parsed = fills["Symbol"].str.extract(OCC_RE)
    parsed.columns = ["underlying", "exp_raw", "right", "strike_raw"]
    bad = parsed["underlying"].isna().sum()
    fills = pd.concat([fills, parsed], axis=1).dropna(subset=["underlying"])
    fills["expiry"] = pd.to_datetime(fills["exp_raw"], format="%y%m%d").dt.date
    fills["strike"] = fills["strike_raw"].astype(int) / 1000.0
    fills["qty"] = fills["Filled"].astype(int)
    fills["px"] = pd.to_numeric(fills["Avg Price"], errors="coerce")

    # "12/31/2021 10:50:57 EST" -> naive ET (label already tells us it's ET local)
    ts = fills["Filled Time"].str.replace(r" E[SD]T$", "", regex=True)
    fills["ts_et"] = pd.to_datetime(ts, format="%m/%d/%Y %H:%M:%S")
    fills = fills.dropna(subset=["px", "ts_et"])
    fills["is_family"] = fills["underlying"].isin(FAMILY)
    fills = fills.sort_values(["ts_et"], kind="stable").reset_index(drop=True)

    meta = {
        "raw_rows": n_raw,
        "cross_file_exact_dupes_dropped": n_dupes,
        "filled_rows_after_dedup": n_filled,
        "unparseable_symbols": int(bad),
        "fills_used": len(fills),
    }
    return fills, meta


def build_episodes(fills: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """FIFO flat->flat episodes per option symbol. Returns (episodes, anomalies)."""
    episodes, anomalies = [], []
    for sym, g in fills.groupby("Symbol", sort=False):
        g = g.sort_values("ts_et", kind="stable")
        first = g.iloc[0]
        lots: list[list] = []  # [qty_remaining, px]
        cur = None

        def open_episode(row):
            return {
                "symbol": sym,
                "underlying": first["underlying"],
                "right": first["right"],
                "strike": first["strike"],
                "expiry": first["expiry"],
                "is_family": bool(first["is_family"]),
                "entry_ts_et": row["ts_et"],
                "exit_ts_et": None,
                "buy_qty": 0,
                "sell_qty": 0,
                "buy_cost": 0.0,
                "sell_proceeds": 0.0,
                "n_buy_fills": 0,
                "n_sell_fills": 0,
                "max_open_qty": 0,
                "first_fill_px": float(row["px"]),
            }

        for _, row in g.iterrows():
            if row["Side"] == "Buy":
                if cur is None:
                    cur = open_episode(row)
                cur["buy_qty"] += row["qty"]
                cur["buy_cost"] += row["qty"] * row["px"]
                cur["n_buy_fills"] += 1
                lots.append([row["qty"], row["px"]])
                open_qty = sum(l[0] for l in lots)
                cur["max_open_qty"] = max(cur["max_open_qty"], open_qty)
            else:  # Sell
                if cur is None or not lots:
                    anomalies.append(
                        {"symbol": sym, "ts": str(row["ts_et"]), "why": "sell_without_open",
                         "qty": int(row["qty"]), "px": float(row["px"])}
                    )
                    continue
                need = row["qty"]
                open_qty = sum(l[0] for l in lots)
                if need > open_qty:
                    anomalies.append(
                        {"symbol": sym, "ts": str(row["ts_et"]), "why": "sell_overflow_clipped",
                         "qty": int(need), "open": int(open_qty)}
                    )
                    need = open_qty
                cur["sell_qty"] += need
                cur["sell_proceeds"] += need * row["px"]
                cur["n_sell_fills"] += 1
                while need > 0 and lots:
                    take = min(need, lots[0][0])
                    lots[0][0] -= take
                    need -= take
                    if lots[0][0] == 0:
                        lots.pop(0)
                if not lots:  # flat -> close episode
                    cur["exit_ts_et"] = row["ts_et"]
                    episodes.append(cur)
                    cur = None

        if cur is not None:  # leftover open lots at end of data
            rem_qty = sum(l[0] for l in lots)
            rem_cost = sum(l[0] * l[1] for l in lots)
            entry_d = cur["entry_ts_et"].date()
            if cur["expiry"] <= entry_d + pd.Timedelta(days=0):
                # 0DTE (expiry == entry date): expired worthless, full premium loss
                cur["exit_ts_et"] = pd.Timestamp.combine(cur["expiry"], datetime.min.time().replace(hour=16))
                cur["expired_worthless_qty"] = rem_qty
                episodes.append(cur)
            else:
                cur["unclosed"] = True
                cur["unclosed_qty"] = rem_qty
                cur["unclosed_cost"] = rem_cost
                episodes.append(cur)

    ep = pd.DataFrame(episodes)
    ep["unclosed"] = ep.get("unclosed", pd.Series(False, index=ep.index)).fillna(False)
    ep["closed"] = ~ep["unclosed"]
    ep["pnl"] = (ep["sell_proceeds"] - ep["buy_cost"]) * 100.0
    ep.loc[ep["unclosed"], "pnl"] = float("nan")
    ep["qty"] = ep["max_open_qty"]
    ep["n_adds"] = (ep["n_buy_fills"] - 1).clip(lower=0)
    ep["scaled_in"] = ep["n_buy_fills"] > 1
    ep["entry_px"] = ep["buy_cost"] / ep["buy_qty"]
    ep["exit_px"] = (ep["sell_proceeds"] / ep["sell_qty"]).where(ep["sell_qty"] > 0, 0.0)
    ep["premium_at_risk"] = ep["buy_cost"] * 100.0
    ep["ret_pct"] = (ep["exit_px"] / ep["entry_px"] - 1.0) * 100.0
    ep.loc[ep["sell_qty"] == 0, "ret_pct"] = -100.0
    ep["hold_min"] = (
        (pd.to_datetime(ep["exit_ts_et"]) - pd.to_datetime(ep["entry_ts_et"])).dt.total_seconds() / 60.0
    )
    ep["dte"] = (pd.to_datetime(ep["expiry"]) - pd.to_datetime(pd.to_datetime(ep["entry_ts_et"]).dt.date)).dt.days
    ep["is_0dte"] = ep["dte"] == 0
    ep["bias"] = ep["right"].map({"C": "bull", "P": "bear"})
    ep = ep.sort_values("entry_ts_et").reset_index(drop=True)
    ep["episode_id"] = ep.index
    return ep, anomalies


def size_band(q: int) -> str:
    if q <= 2:
        return "1-2"
    if q <= 5:
        return "3-5"
    if q <= 10:
        return "6-10"
    return "11+"


if __name__ == "__main__":
    fills, meta = load_fills()
    ep, anomalies = build_episodes(fills)
    print(meta)
    print("episodes:", len(ep), "closed:", int(ep["closed"].sum()),
          "family closed:", int((ep["closed"] & ep["is_family"]).sum()))
    print("anomalies:", len(anomalies))
    fam = ep[ep["closed"] & ep["is_family"]]
    print("family pnl total:", round(fam["pnl"].sum(), 2), "WR:", round((fam["pnl"] > 0).mean() * 100, 1))
