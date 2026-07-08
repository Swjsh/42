"""sim_live_parity.py -- per-setup slippage/latency ledger: live fill vs the assumed entry.

G9 (2026-07-07 Fable gap-audit). For every RECONCILED live entry fill (filled_avg_price from
the FIX3 reconciliation), diff the ACTUAL fill against the price the engine ASSUMED when it
sized + priced the entry (entry_px marketable limit, else the mid premium) -- per setup. That
gap is the real execution slippage the backtest sim MUST match to be trustworthy; the ts gap
is the latency. This is the harness-vs-production parity check the playbook demands, on live
money instead of a sim self-comparison.

DATA SOURCES: core-decisions.jsonl + the 6 fleet-arm decisions.jsonl. A row counts ONLY when
it carries a filled_avg_price > 0 (a REAL fill) -- a mere PLACED order is not a fill.

HONEST STATE (verified 2026-07-08): filled_avg_price is `null` in EVERY decision row across
core + all six fleet arms -> ZERO reconciled fills exist yet. So this ledger's headline number
is currently `reconciled_fills: 0` and it doubles as a FILL-EXISTENCE MONITOR: the rig places
but has never recorded a reconciled entry fill (audit-confirmed green-while-dead). It populates
and starts reporting real per-setup slippage the moment the engine fills + reconciles one entry.

No live-trading path: read-only over the ledgers; writes analysis/parity/. The 'sim next-5m-bar
fill' reconstruction (OPRA-dependent) is a deferred v2 -- assumed-vs-filled is the MVP and is
what execution fidelity actually turns on.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean, median
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
OUT_DIR = REPO / "analysis" / "parity"
FLEET_ARMS = ("safe-1", "safe-2", "safe-3", "risky-1", "risky-3", "bold-2")


def _sources() -> list[Path]:
    srcs = [STATE / "core-decisions.jsonl"]
    srcs += [STATE / "fleet" / a / "decisions.jsonl" for a in FLEET_ARMS]
    return [p for p in srcs if p.exists()]


def _pos_num(x) -> Optional[float]:
    """A strictly-positive float, or None (nulls / 0 / bools / junk -> None)."""
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _dig_fill_price(row: dict) -> Optional[float]:
    """Find a reconciled fill price (>0) wherever the schema puts it (top-level, exec.fill,
    exec.broker.filled_avg_price). None when the row is a place-only / unfilled order."""
    ex = row.get("exec") if isinstance(row.get("exec"), dict) else {}
    containers = [row, ex,
                  ex.get("fill") if isinstance(ex.get("fill"), dict) else {},
                  ex.get("broker") if isinstance(ex.get("broker"), dict) else {}]
    for c in containers:
        if not isinstance(c, dict):
            continue
        for k in ("filled_avg_price", "avg_price", "fill_price"):
            v = _pos_num(c.get(k))
            if v is not None:
                return v
    return None


def _assumed_px(row: dict) -> Optional[float]:
    """The price the engine assumed at entry: the marketable limit entry_px, else the mid."""
    ex = row.get("exec") if isinstance(row.get("exec"), dict) else {}
    for c in (ex, row):
        for k in ("entry_px", "premium"):
            v = _pos_num(c.get(k))
            if v is not None:
                return v
    return None


def parse_fill(row: dict, arm: str) -> Optional[dict]:
    """A parity record for ONE reconciled fill, or None if the row is not a real fill.
    Slippage is computed only when the assumed price is also known (else fill is still logged)."""
    filled = _dig_fill_price(row)
    if filled is None:
        return None
    ex = row.get("exec") if isinstance(row.get("exec"), dict) else {}
    assumed = _assumed_px(row)
    setup = str(row.get("setup") or row.get("setup_name") or ex.get("setup") or "unknown")
    rec = {"arm": arm, "ts_et": row.get("ts_et") or row.get("timestamp_et"),
           "setup": setup, "symbol": row.get("symbol") or ex.get("symbol"),
           "assumed_px": assumed, "filled_avg_price": filled}
    if assumed is not None:
        rec["slippage"] = round(filled - assumed, 4)
        rec["slippage_pct"] = round((filled - assumed) / assumed, 4)
    return rec


def aggregate(fills: list[dict]) -> dict:
    per: dict = {}
    for f in fills:
        per.setdefault(f["setup"], []).append(f)
    setups = {}
    for setup, rows in per.items():
        slips = [r["slippage"] for r in rows if "slippage" in r]
        spct = [r["slippage_pct"] for r in rows if "slippage_pct" in r]
        setups[setup] = {
            "n": len(rows),
            "n_with_assumed": len(slips),
            "mean_slippage": round(mean(slips), 4) if slips else None,
            "median_slippage": round(median(slips), 4) if slips else None,
            "mean_slippage_pct": round(mean(spct), 4) if spct else None,
        }
    return {"reconciled_fills": len(fills), "setups": setups}


def build_ledger(sources: "list[Path] | None" = None) -> "tuple[list[dict], dict]":
    fills: list[dict] = []
    for p in (sources if sources is not None else _sources()):
        arm = "core" if p.name == "core-decisions.jsonl" else p.parent.name
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or "filled_avg_price" not in line:
                continue
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            rec = parse_fill(row, arm)
            if rec:
                fills.append(rec)
    return fills, aggregate(fills)


def main() -> int:
    fills, summary = build_ledger()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "sim-live-parity.jsonl").write_text(
        "\n".join(json.dumps(f) for f in fills) + ("\n" if fills else ""), encoding="utf-8")
    (OUT_DIR / "sim-live-parity-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    n = summary["reconciled_fills"]
    if n == 0:
        print("[sim_live_parity] 0 reconciled fills across core + 6 fleet arms -- "
              "filled_avg_price is null everywhere. The rig places but has never recorded a "
              "reconciled entry fill (audit-confirmed). Ledger armed; populates on first fill.")
    else:
        print(f"[sim_live_parity] {n} reconciled fills. Per-setup slippage:")
        for s, d in summary["setups"].items():
            print(f"  {s}: n={d['n']} mean_slip={d['mean_slippage']} ({d['mean_slippage_pct']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
