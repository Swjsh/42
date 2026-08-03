#!/usr/bin/env python
"""catastrophe_cap_shadow_ledger.py -- ACCRUAL for CATASTROPHE-CAP-WIDEN-WATCH
(automation/overnight/queue.md, filed 2026-07-23 EOD).

BACKGROUND: catastrophe-stop-shakeout-2026-07-23.json found a REAL but UNDERPOWERED signal --
the -50% catastrophe premium cap (fires only on positions whose AT-ENTRY stop resolved
stop_mode=='structure') had fired on just n=4 historical bear/ribbon_ride trades, and 4/4 of
those were genuine shakeouts (premium recovered past the exit, 3/4 hit full TP1). Widening to
-70% or going structure-only both beat CONTROL on aggregate + drop-best-1 in that n=4 sample,
but FAIL majority-of-days and have ZERO held-out (OOS) fires -- a rare-tail lever can't be
decided on n=4. Queue instruction (verbatim): "ACCRUE: shadow-log every future catastrophe-cap
fire + its held-to-EOD counterfactual until n>=10, then a pre-registered decision. Do NOT widen
on n=4."

THIS MODULE IS THE ACCRUAL MECHANISM THAT DID NOT YET EXIST. It is descriptive-only, exactly
like pain_ledger.py's own banner: it writes ONLY the shadow ledger + a summary; it proposes no
knob, flips nothing live, and is never itself sufficient evidence for a stop-placement change
(C6 -- MAE/counterfactual knowledge is hindsight; a live stop cannot condition on a trade's
eventual outcome). The eventual n>=10 decision is its OWN future pre-registered A/B (mirroring
catastrophe_stop_shakeout_ab.py's 4-gate + BH-FDR methodology), which may cite this ledger only
as its evidence base.

WHAT COUNTS AS A FIRE (frozen definition, matches pain_ledger's own stop resolution so there is
exactly ONE definition of "the stop that was actually configured" in this codebase):
  1. At entry the position resolved stop_mode=='structure' (pain_ledger.stop_fields ->
     stop_basis=='structure_catastrophe_cap') -- i.e. the OPERATIVE stop was a chart level, and
     the premium number is only the -50% catastrophe backstop.
  2. The position's LAST exit fill closed via the exit_manager 'premium_stop' stage
     (winner_autopsy.stage_for_exit_fill). Per pain_ledger's own EXITMGR-STAGE-LABEL-CONFLATION
     note, 'premium_stop' is the identical label used for plain premium-mode stops -- but a
     'premium_stop'-staged fill on a stop_basis=='structure_catastrophe_cap' position is
     UNAMBIGUOUS: the catastrophe backstop is the ONLY premium check that can fire condition
     (1)'s positions (their operative invalidation is the chart level; the catastrophe cap is
     purely a floor). A position that instead closed via 'structure_stop' / 'ribbon_flip' /
     'tp1' / 'time_stop' etc. never had its catastrophe floor trip -- correctly excluded.

EXTEND, DON'T FORK -- reuses (no re-derivation, one source of truth each):
  trade_autopsy.load_engine_positions / fetch_bars_cached
  winner_autopsy.load_arm_rows / find_entry_decision / load_exit_trace / stage_for_exit_fill /
    _all_ledger_dates
  pain_ledger.stop_fields / recover_stop_mode_from_exit_trace
  exit_shape_parity_study.fetch_option_bars (real Alpaca OPRA 1-min, same path every other
    autopsy tool in this family uses -- no synthetic pricing path exists)

HELD-TO-EOD COUNTERFACTUAL: the last real OPRA 1-min bar printed before 16:00 ET (RTH close)
on the fire's own date, at the position's full entry qty -- mirrors
catastrophe_stop_shakeout_ab.py's compute_today_counterfactual "held_to_eod" method exactly,
generalized to any symbol/date instead of one hardcoded trade.

ACCRUAL_START_DATE = 2026-07-23 (the day AFTER the original shakeout study's population cutoff
2026-07-22) -- positions on/after this date were NOT part of that study's n=4, so scanning from
here can never double-count a historical fire already scored there.

Ledger (append-only, dedup on date_et+arm+symbol):
  analysis/recommendations/catastrophe-cap-shadow-ledger.jsonl
Summary (overwritten every run):
  automation/state/catastrophe-cap-shadow-summary.json

READINESS FLAG: when n_fires crosses 10 for the FIRST time, ONE line is appended to
automation/overnight/STATUS.md (transition-only, never re-spammed) naming the follow-up as a
queue item -- the actual pre-registered decision is a SEPARATE future study, not made here.

COST: $0 (pure Python). The only network call is fetch_option_bars for a brand-new fire's own
contract -- rare by construction (n=4 in ~14 months of live trading); a normal run with no new
fires makes zero network calls.

Manual: backtest/.venv/Scripts/python.exe setup/scripts/catastrophe_cap_shadow_ledger.py
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, 2026-07-14 popup-storm fix) =====
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "catastrophe-cap-shadow.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "catastrophe-cap-shadow.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet",
           REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from et_clock import et_now  # noqa: E402

LEDGER_OUT = REPO / "analysis" / "recommendations" / "catastrophe-cap-shadow-ledger.jsonl"
SUMMARY_OUT = REPO / "automation" / "state" / "catastrophe-cap-shadow-summary.json"
READY_STATE = REPO / "analysis" / "recommendations" / ".catastrophe-cap-shadow-ready-state.json"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"

ACCRUAL_START_DATE = "2026-07-23"   # day after the shakeout study's population cutoff
DECISION_N = 10                     # queue.md's frozen "then a pre-registered decision" bar
EOD_CUTOFF_UTC_HHMM = "20:00"       # 16:00 ET RTH close, EDT (-4h; this rig trades EDT months)


# ---------- pure helpers (unit-tested; no I/O) ----------------------------------------------

def is_catastrophe_cap_fire(stop_basis: str | None, exit_stage: str | None) -> bool:
    """PURE: the frozen fire definition (see module docstring). None-safe."""
    return stop_basis == "structure_catastrophe_cap" and exit_stage == "premium_stop"


def ledger_key(date_et: str, arm: str, symbol: str) -> str:
    """PURE: the dedup key -- one row per real fire, ever."""
    return f"{date_et}|{arm}|{symbol}"


def last_exit_fill(exit_fills: list[dict]) -> dict | None:
    """PURE: the exit fill that actually CLOSED the position (max ts_utc). None on empty."""
    if not exit_fills:
        return None
    return max(exit_fills, key=lambda ef: ef["ts_utc"])


def eod_bar(bars: list[dict], cutoff_hhmm: str = EOD_CUTOFF_UTC_HHMM) -> dict | None:
    """PURE: the last bar strictly before `cutoff_hhmm` UTC (16:00 ET RTH close). Bars are
    Alpaca-shaped ({'t': 'YYYY-MM-DDTHH:MM:SSZ', 'o','h','l','c','v'}). None on empty/no
    qualifying bar -- never guesses a close."""
    candidates = [b for b in bars if str(b["t"])[11:16] < cutoff_hhmm]
    if not candidates:
        return None
    return max(candidates, key=lambda b: b["t"])


def held_to_eod_counterfactual_pnl(entry_price: float, qty: float,
                                    eod_close: float | None) -> float | None:
    """PURE: what the position would have realized (full entry qty) had it been held to the
    last real OPRA print before EOD instead of catastrophe-stopped. None when no EOD bar."""
    if eod_close is None:
        return None
    return round((eod_close - entry_price) * qty * 100, 2)


def build_fire_row(pos: dict, stop: dict, exit_fill: dict, eod: dict | None) -> dict:
    """PURE: assemble one shadow-ledger row from already-resolved pieces (no I/O here --
    caller does all fetching; this only shapes the record)."""
    entry_price = float(pos["entry_price"])
    qty = float(pos["entry_qty"])
    eod_close = float(eod["c"]) if eod else None
    cf_pnl = held_to_eod_counterfactual_pnl(entry_price, qty, eod_close)
    actual_pnl = round(float(pos["actual_exit_pnl"]), 2)
    return {
        "date_et": pos["date_et"], "arm": pos["arm"], "symbol": pos["symbol"],
        "entry_ts_utc": pos["entry_ts_utc"], "entry_price": entry_price, "qty": qty,
        "exit_ts_utc": exit_fill["ts_utc"], "exit_price": float(exit_fill["price"]),
        "actual_realized_pnl": actual_pnl,
        "stop_premium": stop.get("stop_premium"), "premium_stop_pct": stop.get("premium_stop_pct"),
        "eod_bar_ts_utc": eod["t"] if eod else None, "eod_close": eod_close,
        "held_to_eod_counterfactual_pnl": cf_pnl,
        "would_have_been_better_held": (cf_pnl is not None and cf_pnl > actual_pnl),
        "delta_vs_actual": (round(cf_pnl - actual_pnl, 2) if cf_pnl is not None else None),
    }


def summarize(rows: list[dict]) -> dict:
    """PURE: the accrual summary -- n, aggregate actual vs counterfactual, readiness."""
    n = len(rows)
    scored = [r for r in rows if r["held_to_eod_counterfactual_pnl"] is not None]
    n_scored = len(scored)
    agg_actual = round(sum(r["actual_realized_pnl"] for r in rows), 2)
    agg_cf = round(sum(r["held_to_eod_counterfactual_pnl"] for r in scored), 2) if scored else None
    n_better_held = sum(1 for r in scored if r["would_have_been_better_held"])
    return {
        "n_fires": n, "n_counterfactual_scored": n_scored,
        "aggregate_actual_pnl": agg_actual,
        "aggregate_held_to_eod_counterfactual_pnl": agg_cf,
        "n_would_have_been_better_held": n_better_held,
        "rate_would_have_been_better_held": (round(n_better_held / n_scored, 3)
                                             if n_scored else None),
        "decision_n": DECISION_N,
        "ready_for_decision": n >= DECISION_N,
        "descriptive_only": True,
        "note": ("n < decision_n: DO NOT widen catastrophe_stop_pct on this evidence -- accrual "
                 "continues. File a fresh pre-registered A/B (mirroring "
                 "catastrophe_stop_shakeout_ab.py's 4-gate methodology) once ready."
                 if n < DECISION_N else
                 "n >= decision_n -- ready for a pre-registered decision study. This summary is "
                 "descriptive evidence ONLY, not itself a ship/hold verdict."),
    }


# ---------- I/O layer -------------------------------------------------------------------------

def _dates_since(start_date: str) -> list[str]:
    import winner_autopsy as wa
    return sorted(d for d in wa._all_ledger_dates() if d >= start_date)


def _load_existing_keys(ledger_path: Path = LEDGER_OUT) -> set:
    if not ledger_path.exists():
        return set()
    keys = set()
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        keys.add(ledger_key(r.get("date_et", ""), r.get("arm", ""), r.get("symbol", "")))
    return keys


def _load_existing_rows(ledger_path: Path = LEDGER_OUT) -> list[dict]:
    if not ledger_path.exists():
        return []
    out = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def scan_for_new_fires(start_date: str = ACCRUAL_START_DATE,
                        ledger_path: Path = LEDGER_OUT) -> list[dict]:
    """I/O: walk every closed engine position since `start_date`, find genuinely NEW
    catastrophe-cap fires (not already in the ledger), fetch each one's own real OPRA bars for
    the held-to-EOD counterfactual, and return the new rows (caller appends). Fail-open per
    position: a fetch/parse failure on one position never blocks the others."""
    import exit_shape_parity_study as esp
    import pain_ledger as pl
    import trade_autopsy as ta
    import winner_autopsy as wa

    existing = _load_existing_keys(ledger_path)
    new_rows: list[dict] = []
    for date_et in _dates_since(start_date):
        try:
            positions = ta.load_engine_positions(date_et)
        except Exception as e:  # noqa: BLE001 -- one bad date never blocks the scan
            print(f"[cat-cap-shadow] {date_et}: load_engine_positions failed: {e}", file=sys.stderr)
            continue
        for pos in positions:
            key = ledger_key(pos["date_et"], pos["arm"], pos["symbol"])
            if key in existing:
                continue
            try:
                arm_rows = wa.load_arm_rows(pos["arm"], pos["date_et"])
                entry_row = wa.find_entry_decision(arm_rows, pos["symbol"])
                placement = (entry_row.get("placement") or entry_row.get("exec")) if entry_row else None
                trace = wa.load_exit_trace(arm_rows, pos["symbol"])
                stop = pl.stop_fields(float(pos["entry_price"]), placement, None, exit_trace=trace)
                if stop.get("stop_basis") != "structure_catastrophe_cap":
                    continue
                fill = last_exit_fill(pos["exit_fills"])
                if fill is None:
                    continue
                exit_stage = wa.stage_for_exit_fill(trace, fill["ts_utc"], fill["qty"])
                if not is_catastrophe_cap_fire(stop.get("stop_basis"), exit_stage):
                    continue
                bars = esp.fetch_option_bars(pos["symbol"], pos["date_et"])
                eod = eod_bar(bars)
                row = build_fire_row(pos, stop, fill, eod)
                new_rows.append(row)
                existing.add(key)
                print(f"[cat-cap-shadow] NEW FIRE {key}: actual=${row['actual_realized_pnl']:+.2f} "
                      f"held_to_eod=${row['held_to_eod_counterfactual_pnl']}", flush=True)
            except Exception as e:  # noqa: BLE001 -- fail-open per position
                print(f"[cat-cap-shadow] {key}: skip on error: {e}", file=sys.stderr)
                continue
    return new_rows


def _append_rows(rows: list[dict], ledger_path: Path = LEDGER_OUT) -> None:
    if not rows:
        return
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")


def _flag_ready_transition(summary: dict, status_md: Path = STATUS_MD,
                           state_path: Path = READY_STATE) -> None:
    """Transition-only STATUS.md line the moment n crosses DECISION_N -- never re-spammed on
    subsequent runs (same pattern as pain_ledger._flag_population_floor_status_md)."""
    try:
        was_ready = json.loads(state_path.read_text(encoding="utf-8")).get("ready", False)
    except (OSError, ValueError):
        was_ready = False
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"ready": summary["ready_for_decision"]}), encoding="utf-8")
    if not summary["ready_for_decision"] or was_ready:
        return
    try:
        text = status_md.read_text(encoding="utf-8")
    except OSError:
        return
    marker = "## Known broken"
    line = (f"- [{et_now().isoformat()}] CATASTROPHE-CAP-SHADOW-LEDGER: n_fires reached "
            f"{summary['n_fires']} (>= {DECISION_N}) -- ready for the pre-registered widen "
            f"decision queued as CATASTROPHE-CAP-WIDEN-WATCH. NOT itself a verdict. "
            f"See analysis/recommendations/catastrophe-cap-shadow-ledger.jsonl.")
    if marker in text:
        head, _, tail = text.partition(marker + "\n")
        status_md.write_text(f"{head}{marker}\n\n{line}\n{tail.lstrip(chr(10))}", encoding="utf-8")
    else:
        status_md.write_text(text.rstrip("\n") + f"\n\n{line}\n", encoding="utf-8")


def run(start_date: str = ACCRUAL_START_DATE, ledger_path: Path = LEDGER_OUT,
        summary_path: Path = SUMMARY_OUT) -> dict:
    new_rows = scan_for_new_fires(start_date, ledger_path)
    _append_rows(new_rows, ledger_path)
    all_rows = _load_existing_rows(ledger_path)
    summary = summarize(all_rows)
    summary["generated_at_et"] = et_now().isoformat()
    summary["n_new_this_run"] = len(new_rows)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    _flag_ready_transition(summary)
    print(f"[cat-cap-shadow] n_fires={summary['n_fires']} new={len(new_rows)} "
          f"ready={summary['ready_for_decision']}")
    return summary


def main() -> int:
    try:
        run()
    except Exception as e:  # noqa: BLE001 -- notify-only accrual organ: never propagate
        print(f"[cat-cap-shadow] ERROR (fail-open): {type(e).__name__}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
