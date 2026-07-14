"""sim_live_parity.py -- per-setup slippage/latency ledger: live fill vs the assumed entry.

G9 (2026-07-07 Fable gap-audit). For every REAL entry fill, diff the ACTUAL fill against the
price the engine ASSUMED when it sized + priced the entry (entry_px marketable limit, else the
mid premium) -- per setup. That gap is the real execution slippage the backtest sim MUST match
to be trustworthy; the ts gap is the latency. This is the harness-vs-production parity check
the playbook demands, on live money instead of a sim self-comparison.

T2 REWIRE (2026-07-08, HANDOFF-2026-07-09-TRUTH-AND-EXITS): the fill itself (existence + price)
now comes EXCLUSIVELY from setup/scripts/broker_fills.py's automation/state/fills-ledger.jsonl
(T1, Alpaca /account/activities/FILL -- broker-truth). The OLD `_dig_fill_price` scanned each
decision row for an embedded `filled_avg_price`, which the decision-writer never populates (a
separate reconciliation gap) -- so this ledger permanently reported `reconciled_fills: 0` and
"the rig has never recorded a fill" while the fleet filled real money daily (audit-confirmed
green-while-dead, 2026-07-08). Decision rows (core-decisions.jsonl + fleet/*/decisions.jsonl)
are used ONLY to recover each fill's SETUP NAME + ASSUMED price via an exact order_id match
(placement.broker.id / exec.broker.id) -- never as the source of whether a fill happened.

No live-trading path: read-only over broker_fills.py's ledger + the decision ledgers (for
setup/assumed-px lookup only); writes analysis/parity/. The 'sim next-5m-bar fill'
reconstruction (OPRA-dependent) is a deferred v2 -- assumed-vs-filled is the MVP and is what
execution fidelity actually turns on.
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
FILLS_LEDGER = STATE / "fills-ledger.jsonl"


def _decision_sources() -> list[Path]:
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


def _assumed_px(row: dict) -> Optional[float]:
    """The price the engine assumed at entry: the marketable limit entry_px, else the mid."""
    ex = row.get("exec") if isinstance(row.get("exec"), dict) else {}
    for c in (ex, row):
        for k in ("entry_px", "premium"):
            v = _pos_num(c.get(k))
            if v is not None:
                return v
    return None


def _entry_order_id(row: dict) -> Optional[str]:
    """The broker order id of THIS row's entry attempt (core: exec.broker.id; fleet-arm:
    placement.broker.id), wherever the schema puts it. Used ONLY to look up setup/assumed-px
    metadata -- never to decide whether a fill happened (that's T1's job)."""
    ex = row.get("exec") if isinstance(row.get("exec"), dict) else {}
    placement = row.get("placement") if isinstance(row.get("placement"), dict) else {}
    for c in (ex.get("broker") if isinstance(ex.get("broker"), dict) else {},
              placement.get("broker") if isinstance(placement.get("broker"), dict) else {}):
        if isinstance(c, dict) and c.get("id"):
            return c["id"]
    return None


def build_order_index(sources: "list[Path] | None" = None) -> dict:
    """order_id -> {arm, setup, assumed_px, symbol} for every ENTRY decision row across core +
    fleet-arm ledgers. This is DECISION metadata (what the engine intended/assumed) -- the
    fill itself (existence + price) never comes from here, only from T1's fills-ledger.jsonl."""
    index: dict = {}
    for p in (sources if sources is not None else _decision_sources()):
        arm = "core" if p.name == "core-decisions.jsonl" else p.parent.name
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            oid = _entry_order_id(row)
            if not oid:
                continue
            ex = row.get("exec") if isinstance(row.get("exec"), dict) else {}
            setup = str(row.get("setup") or row.get("setup_name") or ex.get("setup") or "unknown")
            index[oid] = {"arm": arm, "setup": setup, "assumed_px": _assumed_px(row),
                          "symbol": row.get("symbol") or ex.get("symbol")}
    return index


def load_broker_entry_fills(ledger_path: Path = FILLS_LEDGER) -> list[dict]:
    """BUY-side (entry) fills from T1's broker-truth ledger -- the ONLY source of "did a fill
    happen and at what price" in this module (ground rule 2)."""
    if not ledger_path.exists():
        return []
    out: list[dict] = []
    with ledger_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("side") == "buy" and not r.get("is_crypto"):
                out.append(r)
    return out


def parse_fill(fill: dict, order_index: dict) -> dict:
    """A parity record for ONE broker-truth entry fill. filled_avg_price is ALWAYS known (it's
    a real fill from T1); assumed_px/setup come from the matching decision row when its
    order_id is found in the index -- unmatched fills are still logged (setup='unknown',
    assumed_px=None) rather than silently dropped."""
    match = order_index.get(fill.get("order_id"), {})
    setup = match.get("setup", "unknown")
    assumed = match.get("assumed_px")
    rec = {"arm": fill["arm"], "ts_et": fill["ts_et"], "setup": setup,
           "symbol": fill["symbol"], "assumed_px": assumed,
           "filled_avg_price": fill["price"], "matched_decision_row": bool(match)}
    if assumed is not None:
        rec["slippage"] = round(fill["price"] - assumed, 4)
        rec["slippage_pct"] = round((fill["price"] - assumed) / assumed, 4)
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
    n_matched = sum(1 for f in fills if f.get("matched_decision_row"))
    return {"reconciled_fills": len(fills), "n_matched_decision_row": n_matched, "setups": setups}


def build_ledger(fills_ledger_path: Path = FILLS_LEDGER,
                 decision_sources: "list[Path] | None" = None) -> "tuple[list[dict], dict]":
    order_index = build_order_index(decision_sources)
    broker_fills = load_broker_entry_fills(fills_ledger_path)
    fills = [parse_fill(f, order_index) for f in broker_fills]
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
        print("[sim_live_parity] 0 broker-truth entry fills in fills-ledger.jsonl -- either "
              "the fleet genuinely hasn't filled since 2026-06-25, or broker_fills.py (T1) "
              "hasn't been run yet. Run setup/scripts/broker_fills.py first.")
    else:
        print(f"[sim_live_parity] {n} broker-truth entry fills "
              f"({summary['n_matched_decision_row']} matched to a decision row for slippage). "
              f"Per-setup slippage:")
        for s, d in summary["setups"].items():
            print(f"  {s}: n={d['n']} mean_slip={d['mean_slippage']} ({d['mean_slippage_pct']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
