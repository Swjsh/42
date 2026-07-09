"""trade_autopsy.py -- the missing organ: Gamma forms its own hypotheses from its own losses.

WHY THIS EXISTS (J, 2026-07-08: "why doesn't Gamma think 'maybe we're stopping out too early'?
I need to stop having to prompt every single step"). Diagnosis: every autonomous loop was a
parameter-tuner (kitchen/chef/grinders) or a compliance-checker (analyst EOD) -- NO organ owned
"look at our own fills and ask why the money died." The 40/45-winners-stopped-first fact sat in
the fills-ledger for two weeks until J asked. This module is the standing fix: EVERY close it
autopsies EVERY real engine fill, replays counterfactuals through the LIVE exit_manager on real
1-min bars, tags the failure mechanism, and EMITS STRUCTURED HYPOTHESES into the queues the
kitchen/chef/conductor already consume. J reads one line in the firm-brief; the hypotheses flow
to the test machinery without anyone prompting.

The loop this closes (OP-33e -- the repeated question becomes an instrument):
    fills-ledger (broker truth, Gamma_BrokerFills)
      -> per-trade counterfactual replay (esp.replay_position = live exit_manager core)
      -> mechanism tags (stopped_then_paid / entry_spike / rode_winner_back / stop_cost $)
      -> rolling detectors -> hypothesis rows (automation/state/hypothesis-queue.jsonl)
      -> queue.md task blocks (conductor/chef intake) + Discord one-liner + firm-brief line.

Notify-only, $0 beyond the bar fetches, exits 0 always (a broken autopsy must never block
anything). Counterfactual shapes reference the STOP-A study; nothing here changes any live
shape (STOP-A/B governance untouched). Guard: backtest/tests/test_trade_autopsy.py.

Usage:
    backtest/.venv/Scripts/python.exe setup/scripts/trade_autopsy.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import sys
import time as _time_mod
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet",
           REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from et_clock import et_now  # noqa: E402

STATE = REPO / "automation" / "state"
LEDGER = STATE / "fills-ledger.jsonl"
OUT_DIR = REPO / "analysis" / "autopsies"
LAST_JSON = STATE / "trade-autopsy-last.json"
HYP_QUEUE = STATE / "hypothesis-queue.jsonl"
QUEUE_MD = REPO / "automation" / "overnight" / "queue.md"
OUTBOX = STATE / "discord-outbox.jsonl"
LENS = "markdown/trading-knowledge/GENERATIVE-LENS.md"

# Counterfactual menu -- the mechanism probes (NOT candidates; candidates live in the STOP-A
# pre-registration). Each answers ONE question about a dead trade.
COUNTERFACTUALS = {
    "wide_stop_-50": {   # "was the stop inside the noise floor?" (exit-A body)
        "premium_stop_pct": -0.50, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.667,
        "profit_lock_mode": "trailing", "trail_pct": 0.15, "runner_target_pct": 9.9},
    "no_stop_ride": {    # "what was the thesis worth with no stop at all?"
        "premium_stop_pct": -0.95, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.667,
        "profit_lock_mode": "trailing", "trail_pct": 0.15, "runner_target_pct": 9.9},
    "hold_to_time": {    # "does pure theta-ride beat what we did?"
        "premium_stop_pct": -0.95, "tp1_premium_pct": 999.0, "tp1_qty_fraction": 1.0,
        "profit_lock_mode": "fixed", "trail_pct": 0.0, "runner_target_pct": 999.0},
}

# Rolling-window hypothesis detectors: thresholds are the "is this a pattern yet" bar.
ROLL_N = 30                # positions in the rolling window
MIN_LOSERS = 6             # need at least this many losers before the stop-noise claim
STOP_NOISE_FRAC = 0.60     # >=60% of losers stopped-then-paid => hypothesis
ENTRY_SPIKE_MED = 0.08     # median paid-above-minute-low >= 8% => hypothesis
LEFT_TABLE_MIN = 300.0     # $ left on table (best-counterfactual delta) to matter
HYP_DEDUPE_DAYS = 7        # one emission per mechanism per week


# ---------- pure helpers (unit-tested; no I/O) ---------------------------------------------

def classify_position(actual_pnl: float, entry_price: float, entry_bar_low: float,
                      post_exit_high: float | None, cf_pnls: dict) -> dict:
    """Mechanism tags for ONE closed position. All inputs are plain numbers (testable).

    post_exit_high: highest premium AFTER the actual exit (None = no bars after / unknown).
    cf_pnls: {name: pnl} for the counterfactual replays (missing entries tolerated).
    """
    best_cf_name, best_cf = None, None
    for k, v in cf_pnls.items():
        if v is not None and (best_cf is None or v > best_cf):
            best_cf_name, best_cf = k, v
    stop_cost = round(best_cf - actual_pnl, 2) if best_cf is not None else None
    tags = []
    if actual_pnl < 0 and post_exit_high is not None and post_exit_high >= entry_price:
        tags.append("stopped_then_paid")           # the 741P class: loss, then thesis paid
    if stop_cost is not None and stop_cost > 25.0:
        tags.append("exit_shape_cost")             # a probe shape beat what we did
    entry_spike = None
    if entry_bar_low and entry_bar_low > 0:
        entry_spike = round(entry_price / entry_bar_low - 1.0, 4)
        if entry_spike >= 0.10:
            tags.append("paid_the_spike")          # defect #2: bought the signal-bar spike
    if (actual_pnl < 0 and cf_pnls.get("hold_to_time") is not None
            and cf_pnls["hold_to_time"] < actual_pnl):
        tags.append("exit_beat_theta")             # our exit was RIGHT vs riding (honesty tag)
    return {"tags": tags, "stop_cost_vs_best": stop_cost, "best_counterfactual": best_cf_name,
            "entry_spike_pct": entry_spike}


def detect_hypotheses(rows: list[dict], today: str) -> list[dict]:
    """Rolling-window detectors over autopsy rows (newest last). Pure. Each hypothesis is a
    STRUCTURED, testable claim with quoted evidence and concrete next tests."""
    window = rows[-ROLL_N:]
    losers = [r for r in window if r["actual_pnl"] < 0]
    hyps = []
    if len(losers) >= MIN_LOSERS:
        stp = [r for r in losers if "stopped_then_paid" in r.get("tags", [])]
        frac = len(stp) / len(losers)
        if frac >= STOP_NOISE_FRAC:
            hyps.append({
                "id": f"H-{today}-stop-noise", "mechanism": "stop_inside_noise_floor",
                "claim": "the live stop exits losers that then pay the thesis -- the stop is "
                         "harvesting winners, not cutting losers",
                "evidence": {"losers_in_window": len(losers), "stopped_then_paid": len(stp),
                             "fraction": round(frac, 3), "window_n": len(window)},
                "proposed_tests": [
                    "replay exit-A (-50/+150/sell66/trail15) on these exact fills via "
                    "exit_shape_parity_study (kill-check)",
                    "confirm on the fresh OPRA slice per the STOP-A pre-registration (T-W7)",
                ]})
    spikes = [r["entry_spike_pct"] for r in window if r.get("entry_spike_pct") is not None]
    if len(spikes) >= 8:
        med = sorted(spikes)[len(spikes) // 2]
        if med >= ENTRY_SPIKE_MED:
            hyps.append({
                "id": f"H-{today}-entry-spike", "mechanism": "paying_the_signal_spike",
                "claim": "entries fill materially above the signal-minute low -- the marketable "
                         "ask+buffer buys the local premium spike (defect #2)",
                "evidence": {"median_paid_above_min_low": round(med, 3), "n": len(spikes)},
                "proposed_tests": [
                    "entry_manager shadow (T-W5): log limit-below/patience counterfactual fills "
                    "next to real entries for 3+ sessions",
                ]})
    costs = [r["stop_cost_vs_best"] for r in window
             if r.get("stop_cost_vs_best") is not None and r["stop_cost_vs_best"] > 0]
    actual_sum = sum(r["actual_pnl"] for r in window)
    if costs and sum(costs) >= LEFT_TABLE_MIN and sum(costs) >= 2 * abs(actual_sum):
        hyps.append({
            "id": f"H-{today}-left-on-table", "mechanism": "exit_shape_dominated",
            "claim": "a fixed counterfactual shape beats the shipped exits by more than 2x the "
                     "window's net P&L -- the exit shape, not the signal, is the bottleneck",
            "evidence": {"sum_stop_cost": round(sum(costs), 2), "window_net_pnl": round(actual_sum, 2),
                         "n_dominated": len(costs), "window_n": len(window)},
            "proposed_tests": [
                "STOP-A sign-off -> T-W7 confirmatory on the frozen v2 candidates",
                f"enumerate levers beyond exit shape per {LENS} (DTE / spread / strike / sizing)",
            ]})
    return hyps


def dedupe_hypotheses(new: list[dict], existing_rows: list[dict], today: str) -> list[dict]:
    """One emission per mechanism per HYP_DEDUPE_DAYS. Pure."""
    cutoff = (datetime.fromisoformat(today) - timedelta(days=HYP_DEDUPE_DAYS)).date().isoformat()
    recent = {r.get("mechanism") for r in existing_rows
              if str(r.get("date", "")) >= cutoff}
    return [h for h in new if h["mechanism"] not in recent]


# ---------- I/O layer ----------------------------------------------------------------------

def load_engine_positions(date_et: str) -> list[dict]:
    """Closed engine option positions for date_et from the broker-truth ledger -- ANY arm
    (fleet_rest AND core), attribution=='engine' (broker_fills' pre-decided rule)."""
    import exit_shape_parity_study as esp
    if not LEDGER.exists():
        return []
    fills = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if (r.get("attribution") == "engine" and r.get("is_option")
                and not r.get("is_crypto")):
            fills.append(r)
    positions = esp.reconstruct_positions(fills)
    return [p for p in positions if p["date_et"] == date_et and p["exit_fills"]]


def autopsy_position(pos: dict, esp) -> dict | None:
    """Replay one position's counterfactual menu on real 1-min bars. None if bars missing."""
    bars = esp.fetch_option_bars(pos["symbol"], pos["date_et"])
    if not bars:
        return None
    entry_ts = pos["entry_ts_utc"]
    entry_price = pos["entry_price"]
    path = [b for b in bars if b["t"] >= entry_ts]
    if not path:
        return None
    entry_bar_low = float(path[0]["l"])
    mfe = max(b["h"] for b in path) / entry_price - 1.0
    mae = min(b["l"] for b in path) / entry_price - 1.0
    exit_ts = max(ef["ts_utc"] for ef in pos["exit_fills"])
    post = [b for b in path if b["t"] > exit_ts]
    post_exit_high = max((b["h"] for b in post), default=None)
    cf_pnls = {}
    for name, shape in COUNTERFACTUALS.items():
        r = esp.replay_position(pos, bars, shape)
        cf_pnls[name] = r.get("pnl")
    cls = classify_position(pos["actual_exit_pnl"], entry_price, entry_bar_low,
                            post_exit_high, cf_pnls)
    return {
        "date": pos["date_et"], "arm": pos["arm"], "symbol": pos["symbol"],
        "entry_ts_utc": entry_ts, "entry_price": entry_price, "qty": pos["entry_qty"],
        "actual_pnl": round(pos["actual_exit_pnl"], 2),
        "mfe_pct": round(mfe, 3), "mae_pct": round(mae, 3),
        "counterfactuals": cf_pnls, **cls,
    }


def load_recent_rows(days: int = 21) -> list[dict]:
    rows = []
    if OUT_DIR.exists():
        for f in sorted(OUT_DIR.glob("*.jsonl"))[-days:]:
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass
    return rows


def load_hypothesis_rows() -> list[dict]:
    if not HYP_QUEUE.exists():
        return []
    out = []
    for line in HYP_QUEUE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def render_md(date_et: str, rows: list[dict], hyps: list[dict]) -> str:
    L = [f"# Trade autopsy — {date_et}", ""]
    if not rows:
        L.append("No closed engine positions today (broker-truth ledger). Nothing to autopsy.")
        return "\n".join(L) + "\n"
    total = sum(r["actual_pnl"] for r in rows)
    uniq = len(set((r["date"], r["symbol"]) for r in rows))
    L.append(f"**{len(rows)} closed engine positions ({uniq} unique signals) · net "
             f"{'+' if total >= 0 else ''}${total:.2f}.** Counterfactuals replayed through the "
             f"live exit_manager on real 1-min bars (frictionless fills at trigger levels).")
    L.append("")
    L.append("| symbol | arm | actual | MFE | MAE | best counterfactual | Δ vs best | tags |")
    L.append("|---|---|--:|--:|--:|---|--:|---|")
    for r in rows:
        bc = r.get("best_counterfactual") or "—"
        bc_pnl = r["counterfactuals"].get(bc) if bc != "—" else None
        L.append(f"| {r['symbol'][-9:]} | {r['arm']} | ${r['actual_pnl']} "
                 f"| {r['mfe_pct']*100:+.0f}% | {r['mae_pct']*100:+.0f}% "
                 f"| {bc} (${bc_pnl}) | ${r.get('stop_cost_vs_best', '—')} "
                 f"| {', '.join(r['tags']) or '—'} |")
    L.append("")
    if hyps:
        L.append("## Hypotheses emitted (→ hypothesis-queue.jsonl + queue.md)")
        L.append("")
        for h in hyps:
            L.append(f"- **{h['id']}** ({h['mechanism']}): {h['claim']}. "
                     f"Evidence: `{json.dumps(h['evidence'])}`")
    else:
        L.append("_No new hypotheses this run (below thresholds or deduped this week)._")
    L.append("")
    L.append(f"_Generated by trade_autopsy.py (Gamma_TradeAutopsy 16:15 ET). Lever menu: {LENS}._")
    return "\n".join(L) + "\n"


def append_queue_md(hyps: list[dict], date_et: str) -> None:
    if not hyps:
        return
    try:
        with QUEUE_MD.open("a", encoding="utf-8") as fh:
            for h in hyps:
                fh.write(f"\n### T-AUTOPSY-{h['id']} MED — autopsy hypothesis: {h['mechanism']}\n\n"
                         f"**Claim:** {h['claim']}. **Evidence:** `{json.dumps(h['evidence'])}` "
                         f"(analysis/autopsies/{date_et}.md).\n"
                         f"**Action:** {' · '.join(h['proposed_tests'])} "
                         f":: depends:none :: status:proposed\n")
    except OSError as e:
        print(f"[autopsy] WARN queue.md append failed: {e}", file=sys.stderr)


def queue_ping(date_et: str, rows: list[dict], hyps: list[dict]) -> None:
    try:
        from trade_today_watcher import _load_user_mention
        mention = _load_user_mention()
    except Exception:  # noqa: BLE001
        mention = ""
    if not rows:
        return  # silent on no-trade days (don't spam)
    total = sum(r["actual_pnl"] for r in rows)
    stp = sum(1 for r in rows if "stopped_then_paid" in r["tags"])
    hyp_s = f" · {len(hyps)} new hypothesis(es): {', '.join(h['mechanism'] for h in hyps)}" if hyps else ""
    msg = (f"{mention}[AUTOPSY] {date_et}: {len(rows)} engine positions net ${total:.0f}; "
           f"{stp} stopped-then-paid{hyp_s}. analysis/autopsies/{date_et}.md")
    try:
        with OUTBOX.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"content": msg, "source": "trade_autopsy",
                                 "queued_at": et_now().isoformat()}) + "\n")
    except OSError as e:
        print(f"[autopsy] WARN outbox append failed: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="ET date to autopsy (default: today ET)")
    args = ap.parse_args()
    date_et = args.date or et_now().date().isoformat()

    try:
        import exit_shape_parity_study as esp
        positions = load_engine_positions(date_et)
        rows = []
        for p in positions:
            r = autopsy_position(p, esp)
            if r is not None:
                rows.append(r)
            _time_mod.sleep(0.1)

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        day_file = OUT_DIR / f"{date_et}.jsonl"
        day_file.write_text("\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""),
                            encoding="utf-8")

        history = load_recent_rows()
        # today's rows are already in history via the file we just wrote? load_recent_rows
        # re-reads the dir, so yes -- no double-append.
        new_hyps = detect_hypotheses(history, date_et)
        new_hyps = dedupe_hypotheses(new_hyps, load_hypothesis_rows(), date_et)
        if new_hyps:
            with HYP_QUEUE.open("a", encoding="utf-8") as fh:
                for h in new_hyps:
                    fh.write(json.dumps({**h, "date": date_et, "status": "proposed",
                                         "ts": et_now().isoformat()}) + "\n")
            append_queue_md(new_hyps, date_et)

        md = render_md(date_et, rows, new_hyps)
        (OUT_DIR / f"{date_et}.md").write_text(md, encoding="utf-8")
        LAST_JSON.write_text(json.dumps({
            "date": date_et, "n_positions": len(rows),
            "net_pnl": round(sum(r["actual_pnl"] for r in rows), 2) if rows else 0.0,
            "n_stopped_then_paid": sum(1 for r in rows if "stopped_then_paid" in r["tags"]),
            "new_hypotheses": [h["id"] for h in new_hyps],
            "md": f"analysis/autopsies/{date_et}.md",
            "generated_at": et_now().isoformat(),
        }, indent=2), encoding="utf-8")
        queue_ping(date_et, rows, new_hyps)
        print(f"[autopsy] {date_et}: {len(rows)} positions autopsied, "
              f"{len(new_hyps)} new hypotheses -> {day_file.name}")
    except Exception as e:  # noqa: BLE001 -- notify-only: never propagate a failure
        print(f"[autopsy] ERROR (fail-open): {e}", file=sys.stderr)
        try:
            LAST_JSON.write_text(json.dumps({"date": date_et, "error": str(e)[:300],
                                             "generated_at": et_now().isoformat()}), encoding="utf-8")
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
