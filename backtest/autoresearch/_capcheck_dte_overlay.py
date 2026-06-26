"""CAP-CHECK OVERLAY — quantify the LIVE risk-cap defect against the validated DTE-stop edge.

THE DEFECT (confirmed at code level): risk_gate.check_order enforces RISK_CAP against
NOTIONAL = entry_premium * qty * 100, capped at the tighter of per_trade_risk_cap_pct and the
v15 per-tier max_pct table, AND a MIN_CONTRACTS floor (Safe 3 / Bold 5). simulator_real (and
the DTE-stop harness it underlies) has NO notional/buying-power cap, so the validated
+$57.59 (Safe) / +$73.91 (Bold) OOS expectancy assumes a qty-3 fill that the LIVE gate would
BLOCK on the more expensive 1DTE premiums.

WHAT THIS DOES (idempotent, $0, pure research — NO live edits, NO orders):
  For BOTH deployed cells over the FULL #1 vwap_continuation signal set at 1DTE / qty=3:
    Safe deployed cell : ATM   (offset 0), 1DTE, qty 3, equity $2,000  -> cap $600
    Bold deployed cell : ITM-2 (offset -2),1DTE, qty 3, equity $1,648  -> cap $824 + MIN 5
  1. Re-run the harness's BYTE-FOR-BYTE detection + premium-pull (run_cell) to get the EXACT
     per-trade entry premium and per-trade P&L from the OPRA cache (the same day-T entry bar the
     validation used). NOTHING is estimated.
  2. Per trade, ask the LIVE gate (pre_order_gate.check = risk_gate.check_order, the authority)
     whether qty-3 at that real entry premium is allowed. BLOCK if notional > cap OR qty < min.
  3. Report per account: block_rate_pct, affordable_n / total_n, cap-aware OOS expectancy over
     ONLY the affordable OOS trades vs the validated no-cap OOS exp, and the affordable-days
     premium profile (are only the cheap/low-vol days affordable?).

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_capcheck_dte_overlay.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# Reuse the DTE-stop harness byte-for-byte: same detector, same per-DTE OPRA premium-pull,
# same cell runner. We only OVERLAY the live cap gate on its per-trade output.
from autoresearch import _dte_stop_construction as H  # noqa: E402
from autoresearch._dte_expansion_sim import OOS_YEAR, QTY  # noqa: E402

# The LIVE gate authority. Folded into lib.cap_admission (the graduated order-ADMISSION
# layer), which delegates to lib.risk_gate.check_order — the same code the heartbeat invokes
# before every place_option_order. We use its per-order decision verbatim as the verdict.
from lib.cap_admission import decide as _cap_decide  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "capcheck-dte-overlay.json"

# Deployed cells (resolver live_order_params, qty = WP3_BASE_QTY = 3) per CLAUDE.md account ctx.
DEPLOYED = {
    "safe": {"tier": "ATM",   "offset": 0,  "equity": 2000.0, "cap": 600.0, "min_contracts": 3,
             "validated_oos_exp": 57.59},
    "bold": {"tier": "ITM-2", "offset": -2, "equity": 1648.0, "cap": 824.0, "min_contracts": 5,
             "validated_oos_exp": 73.91},
}
DTE = 1
QTY_DEPLOYED = 3


def _is_oos(date_str: str) -> bool:
    return int(date_str[:4]) == OOS_YEAR


def main() -> int:
    print("[capcheck] loading SPY+VIX (reusing DTE-stop harness) ...", flush=True)
    spy, vix = H._load_spy_vix()
    day_open_close = H.base._spy_day_open_close(spy)
    days = H.build_day_contexts(spy)
    from lib.ribbon import compute_ribbon
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    H.base._build_expiry_index(DTE)

    detect = H.FAMILIES_EXT["vwap_continuation"]
    signals = detect(days, vix, spy, ribbon)
    sig_days = len({spy.iloc[s.bar_idx]["timestamp_et"].date() for s in signals})
    print(f"[capcheck] #1 vwap_continuation signals={len(signals)} on {sig_days} days", flush=True)

    report = {
        "campaign": "CAP-CHECK OVERLAY — live risk-cap gate vs validated DTE-stop edge (#1 vwap_continuation)",
        "purpose": ("quantify how often the LIVE risk_gate (notional cap + MIN_CONTRACTS) BLOCKS the "
                    "qty-3 1DTE fill the validation assumed (simulator_real has NO cap), and the "
                    "cap-aware OOS expectancy over only the AFFORDABLE trades."),
        "gate_authority": "lib.cap_admission.decide -> lib.risk_gate.check_order (the live gate)",
        "dte": DTE, "qty": QTY_DEPLOYED, "n_signals_total": len(signals),
        "accounts": {},
    }

    for acct, cfg in DEPLOYED.items():
        # BYTE-FOR-BYTE detection + premium-pull at the deployed cell (1DTE, -8% percent stop =
        # the live default construction). The per-trade entry_premium and dollar_pnl come straight
        # from the OPRA cache via the harness's run_cell.
        cell = H.run_cell(signals, spy, day_open_close, DTE,
                          strike_offset=cfg["offset"], construction="percent",
                          stop_param=H.BASELINE_PCT)
        rows = cell.rows
        total_n = len(rows)

        affordable, blocked = [], []
        block_reasons = {}
        for r in rows:
            d = _cap_decide(acct, cfg["equity"], QTY_DEPLOYED, r.entry_premium)
            if d.allowed:
                affordable.append(r)
            else:
                blocked.append(r)
                block_reasons[d.code] = block_reasons.get(d.code, 0) + 1

        n_aff = len(affordable)
        n_blk = len(blocked)
        block_rate = round(100.0 * n_blk / total_n, 2) if total_n else 0.0

        # OOS slices (validation OOS = OOS_YEAR).
        oos_all = [r for r in rows if _is_oos(r.date)]
        oos_aff = [r for r in affordable if _is_oos(r.date)]
        nocap_oos_exp = round(float(np.mean([r.dollar_pnl for r in oos_all])), 2) if oos_all else 0.0
        capaware_oos_exp = round(float(np.mean([r.dollar_pnl for r in oos_aff])), 2) if oos_aff else 0.0

        # Premium profile: are only the cheap days affordable?
        prem_all = [r.entry_premium for r in rows]
        prem_aff = [r.entry_premium for r in affordable]
        prem_blk = [r.entry_premium for r in blocked]

        def _stats(xs):
            if not xs:
                return {"n": 0}
            a = np.asarray(xs, dtype=float)
            return {"n": len(xs), "min": round(float(a.min()), 3),
                    "median": round(float(np.median(a)), 3),
                    "mean": round(float(a.mean()), 3), "max": round(float(a.max()), 3)}

        acct_out = {
            "deployed_cell": {"tier": cfg["tier"], "offset": cfg["offset"], "dte": DTE,
                              "qty": QTY_DEPLOYED, "equity": cfg["equity"], "cap_dollars": cfg["cap"],
                              "min_contracts": cfg["min_contracts"]},
            "total_n": total_n,
            "affordable_n": n_aff,
            "blocked_n": n_blk,
            "block_rate_pct": block_rate,
            "block_reasons": block_reasons,
            "validated_nocap_oos_exp": cfg["validated_oos_exp"],
            "recomputed_nocap_oos_exp": nocap_oos_exp,
            "capaware_oos_exp_affordable_only": capaware_oos_exp,
            "oos_total_n": len(oos_all),
            "oos_affordable_n": len(oos_aff),
            "premium_profile": {
                "all_trades": _stats(prem_all),
                "affordable_trades": _stats(prem_aff),
                "blocked_trades": _stats(prem_blk),
            },
        }
        report["accounts"][acct] = acct_out

        print(f"\n=== {acct.upper()} deployed cell: {cfg['tier']} (off {cfg['offset']:+d}), "
              f"1DTE, qty {QTY_DEPLOYED}, equity ${cfg['equity']:.0f}, cap ${cfg['cap']:.0f}, "
              f"min_contracts {cfg['min_contracts']} ===", flush=True)
        print(f"  total signals filled : {total_n}", flush=True)
        print(f"  BLOCKED              : {n_blk}  ({block_rate}%)   reasons={block_reasons}", flush=True)
        print(f"  affordable           : {n_aff} / {total_n}", flush=True)
        print(f"  validated no-cap OOS exp/trade : ${cfg['validated_oos_exp']:.2f}", flush=True)
        print(f"  recomputed no-cap OOS exp/trade: ${nocap_oos_exp:.2f}  (n={len(oos_all)})", flush=True)
        print(f"  CAP-AWARE OOS exp/trade (affordable only): ${capaware_oos_exp:.2f}  "
              f"(n={len(oos_aff)})", flush=True)
        print(f"  premium profile all      : {_stats(prem_all)}", flush=True)
        print(f"  premium profile AFFORD   : {_stats(prem_aff)}", flush=True)
        print(f"  premium profile BLOCKED  : {_stats(prem_blk)}", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n[capcheck] wrote {OUT}", flush=True)

    safe = report["accounts"]["safe"]
    premise = safe["block_rate_pct"] >= 25.0
    print("\n=== VERDICT ===", flush=True)
    print(f"Safe block_rate = {safe['block_rate_pct']}%  -> premise_confirmed "
          f"(>= ~25% materially broken) = {premise}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
