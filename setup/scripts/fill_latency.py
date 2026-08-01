#!/usr/bin/env python
"""fill_latency.py -- the FILL-PIPELINE LATENCY DECOMPOSITION (WEEKEND-TWELVE Next-Twelve #5,
2026-08-01): per-fill breakdown of bar-close -> core verdict -> signal -> plan -> submit ->
broker-submitted -> fill, so a future incident like 2026-07-31 12:19 (a fill traced back to a
1-second-stale snapshot after a 4m03.9s pipeline -- WINNER-AUTOPSY-2026-07-31-1219.md) can be
diagnosed from a standing surface instead of a one-off forensic reconstruction.

INSTRUMENT, NOT REDESIGN. This module adds NO new behavior to the trade path -- it is a pure
READ-ONLY join over fields the entry path already writes (plus 4 new additive, logging-only
fields this same session added: core_tick_id + signal_written_at on the arm decision row,
plan_ts + submit_ts inside fleet_live._place_live's returned placement dict). Every field this
module reads was already being persisted to disk before this module existed, except those 4 --
see setup/scripts/heartbeat_core.py (core_tick_id), automation/state/fleet/build_shared_signal.py
(core_tick_id passthrough into shared-signal.json), and automation/state/fleet/fleet_live.py
(core_tick_id/signal_written_at/plan_ts/submit_ts) for exactly where each is written.

SCOPE (disclosed): the fleet_rest arms only (safe-3, risky-1, risky-3 -- the ones that go
through build_shared_signal.py -> fleet_live.py, the "fleet read" hop the 07-31 incident was
about). safe-2/bold-2 (execution="mcp_heartbeat") are placed DIRECTLY by heartbeat_core.py with
no separate signal-read hop, so "fleet read ts" does not apply to them; a bar-close -> core
verdict -> submit -> fill decomposition for that path is a DIFFERENT, narrower instrument and
is not built here (disclosed, not silently omitted).

STAGES (None whenever the source field is absent -- never guessed, never zero-filled):
  bar_close_ts        core-decisions.jsonl row's trigger_bar_et (the setup's own trigger bar)
  core_verdict_ts     core-decisions.jsonl row's ts_et (whichever account drove this arm's
                       perception; SAFE is used when ambiguous -- it is always written first)
  signal_written_ts   shared-signal.json's written_at, AS CAPTURED into the arm's OWN decision
                       row at signal_written_at (shared-signal.json itself is overwritten every
                       tick and is not archived, so the arm's own row is the only durable copy)
  plan_ts             fleet_live.py's per-arm "about to act" instant (placement.plan_ts)
  submit_ts           fleet_live.py's own wall-clock right before the broker POST
                       (placement.submit_ts) -- OUR clock, not the broker's
  broker_submitted_ts placement.broker.submitted_at -- the BROKER's own clock (Alpaca). The
                       gap vs submit_ts is real network latency, not a duplicate measurement.
  fill_ts             fills-ledger.jsonl's ts_et for the matching order_id -- the broker's
                       authoritative fill instant (fleet_live.py's own entry row does NOT
                       capture this: the order response fleet_live.py logs is the INITIAL POST
                       response, typically status="pending_new" -- confirmed against the real
                       2026-07-31 12:19 entry row, filled_at: null there. fills-ledger.jsonl,
                       built by fleet_journal_bridge.py's separate reconciliation pass against
                       broker account activities, is the only durable source of the TRUE fill.)

A row with fewer than 2 resolvable stages is EXCLUDED AND COUNTED (n_missing_instrumentation),
never fabricated -- honesty-rails convention matching pain_ledger.py. Every fill from BEFORE
this session's fix will have core_tick_id/signal_written_at/plan_ts/submit_ts == None (those
fields did not exist yet) and lands in that excluded bucket; this is the expected, disclosed
state until fills start flowing through the instrumented path (this fix ships after Friday's
close, so the first real population is Monday 2026-08-03 onward).

NIGHTLY: folded into the existing Gamma_WinnerAutopsy 16:25 ET fire (same additive-fold pattern
pain_ledger.py established), NO new scheduled task. Fail-open there: a failure here never costs
the winner-autopsy/pain-ledger product.

COST: $0. Pure Python, zero network calls, zero OPRA fetches -- three JSONL files, already on
disk, joined in memory.

Manual:
    python setup/scripts/fill_latency.py                      # today -> latency.json
    python setup/scripts/fill_latency.py --date 2026-08-03
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (FLEET_DIR, REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from et_clock import et_now  # noqa: E402

CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
FILLS_LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
LEDGER_OUT = REPO / "analysis" / "pain-ledger" / "latency.json"
FLEET_REST_ARMS = ("safe-3", "risky-1", "risky-3")  # see module docstring SCOPE
STAGE_ORDER = ("bar_close_ts", "core_verdict_ts", "signal_written_ts", "plan_ts", "submit_ts",
              "broker_submitted_ts", "fill_ts")
MIN_RESOLVABLE_STAGES = 2  # below this a row is excluded-and-counted, never partially reported


# ---------- pure helpers (unit-tested; no I/O) ----------------------------------------------

def _parse_iso(ts: "str | None") -> "float | None":
    """ISO8601 -> epoch seconds, tolerant of a trailing 'Z' and missing/naive tzinfo (treated
    as ET, matching every producer in this pipeline). None on anything unparsable -- never
    raises, never guesses a value."""
    if not isinstance(ts, str) or not ts:
        return None
    s = ts.replace("Z", "+00:00")
    from datetime import datetime  # noqa: PLC0415 -- kept local, this is the only user
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt.timestamp()


def stage_deltas(stages: dict[str, "str | None"]) -> dict[str, "float | None"]:
    """PURE: {stage_name: iso_ts_or_None} -> {"<a>_to_<b>_s": seconds_or_None} for every
    CONSECUTIVE pair in STAGE_ORDER, plus "total_s" (first resolvable -> last resolvable).
    A delta is None whenever either endpoint is None -- never interpolated, never assumed."""
    epochs = {k: _parse_iso(v) for k, v in stages.items()}
    out: dict[str, "float | None"] = {}
    for a, b in zip(STAGE_ORDER, STAGE_ORDER[1:]):
        ea, eb = epochs.get(a), epochs.get(b)
        out[f"{a}_to_{b}_s"] = None if (ea is None or eb is None) else round(eb - ea, 3)
    resolvable = [epochs[k] for k in STAGE_ORDER if epochs.get(k) is not None]
    out["total_s"] = None if len(resolvable) < 2 else round(max(resolvable) - min(resolvable), 3)
    out["n_resolvable_stages"] = len(resolvable)
    return out


def latency_row_from_fill(fill: dict, decision_row: "dict | None",
                          core_row: "dict | None") -> "dict | None":
    """PURE: join one fills-ledger.jsonl row against its matching arm decision row (by
    order_id -- caller resolves the match) and core-decisions.jsonl row (by core_tick_id --
    caller resolves the match) into one latency-decomposition row. None (excluded, caller
    counts it) when fewer than MIN_RESOLVABLE_STAGES stages are resolvable -- e.g. any fill
    from before this session's fix, where decision_row carries no core_tick_id/plan_ts/
    submit_ts at all."""
    placement = (decision_row or {}).get("placement") or {}
    broker = placement.get("broker") or {}
    stages = {
        "bar_close_ts": (core_row or {}).get("trigger_bar_et"),
        "core_verdict_ts": (core_row or {}).get("ts_et"),
        "signal_written_ts": (decision_row or {}).get("signal_written_at"),
        "plan_ts": placement.get("plan_ts"),
        "submit_ts": placement.get("submit_ts"),
        "broker_submitted_ts": broker.get("submitted_at"),
        "fill_ts": fill.get("ts_utc") or fill.get("ts_et"),
    }
    deltas = stage_deltas(stages)
    if deltas["n_resolvable_stages"] < MIN_RESOLVABLE_STAGES:
        return None
    return {
        "date_et": fill.get("date_et"), "arm": fill.get("arm"), "symbol": fill.get("symbol"),
        "order_id": fill.get("order_id"), "core_tick_id": (decision_row or {}).get("core_tick_id"),
        "stages": stages, **deltas,
    }


def summarize(rows: list[dict]) -> dict:
    """PURE: per-day/overall summary -- median + p90 of total_s and each hop, n scored. Never
    drops small-n silently (flagged, not hidden) -- SMALL_N mirrors pain_ledger.py's own bar."""
    SMALL_N = 5
    out: dict = {"n_scored": len(rows), "small_n": len(rows) < SMALL_N, "hops": {}}
    if not rows:
        return out
    for key in [f"{a}_to_{b}_s" for a, b in zip(STAGE_ORDER, STAGE_ORDER[1:])] + ["total_s"]:
        vals = sorted(r[key] for r in rows if r.get(key) is not None)
        if not vals:
            out["hops"][key] = {"n": 0, "median_s": None, "p90_s": None, "max_s": None}
            continue
        mid = vals[len(vals) // 2] if len(vals) % 2 else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2
        p90 = vals[min(len(vals) - 1, int(round(0.9 * (len(vals) - 1))))]
        out["hops"][key] = {"n": len(vals), "median_s": round(mid, 3), "p90_s": round(p90, 3),
                            "max_s": round(vals[-1], 3)}
    return out


# ---------- disk I/O (build_ledger + main) ---------------------------------------------------

def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return out


def _decision_rows_by_order_id(date_et: str) -> dict[str, dict]:
    """{order_id: decision_row} across every fleet_rest arm's decisions.jsonl for `date_et`.
    Only rows with a placed order carry a broker.id -- everything else is naturally excluded."""
    out: dict[str, dict] = {}
    for arm in FLEET_REST_ARMS:
        for row in _read_jsonl(FLEET_DIR / arm / "decisions.jsonl"):
            ts = row.get("ts_et") or ""
            if ts[:10] != date_et:
                continue
            oid = ((row.get("placement") or {}).get("broker") or {}).get("id")
            if oid:
                out[oid] = row
    return out


def _core_rows_by_tick_id(date_et: str) -> dict[str, dict]:
    """{core_tick_id: earliest-account row} for `date_et` -- SAFE wins when both accounts
    share a core_tick_id (it is always written first; see heartbeat_core.main()'s per-account
    loop order). Rows without a core_tick_id (pre-fix history) are naturally excluded."""
    out: dict[str, dict] = {}
    for row in _read_jsonl(CORE_DECISIONS):
        ts = row.get("ts_et") or ""
        if ts[:10] != date_et:
            continue
        tick_id = row.get("core_tick_id")
        if not tick_id:
            continue
        if tick_id not in out or row.get("account") == "safe":
            out[tick_id] = row
    return out


def build_ledger(date_et: "str | None" = None, out_path: Path = LEDGER_OUT) -> dict:
    """Build + write the latency ledger for one ET date (default: today). Fail-open at every
    step (a missing/corrupt source file yields an empty population, never a crash) -- this
    is a descriptive nightly fold, never load-bearing for any trading decision."""
    date_et = date_et or et_now().strftime("%Y-%m-%d")
    fills = [f for f in _read_jsonl(FILLS_LEDGER)
            if f.get("date_et") == date_et and f.get("arm") in FLEET_REST_ARMS
            and f.get("side") == "buy"]  # entry fills only -- exits are a separate instrument
    decisions_by_oid = _decision_rows_by_order_id(date_et)
    core_by_tick = _core_rows_by_tick_id(date_et)

    rows: list[dict] = []
    n_excluded_missing_instrumentation = 0
    n_excluded_no_decision_row = 0
    for fill in fills:
        decision_row = decisions_by_oid.get(fill.get("order_id"))
        if decision_row is None:
            n_excluded_no_decision_row += 1
            continue
        core_row = core_by_tick.get(decision_row.get("core_tick_id"))
        latency_row = latency_row_from_fill(fill, decision_row, core_row)
        if latency_row is None:
            n_excluded_missing_instrumentation += 1
            continue
        rows.append(latency_row)

    ledger = {
        "_doc": "Fill-pipeline latency decomposition (WEEKEND-TWELVE #5). INSTRUMENT ONLY -- "
                "descriptive, never load-bearing for any trading/gate decision. Rows before "
                "this session's fix (2026-08-01) carry no core_tick_id/plan_ts/submit_ts and "
                "are excluded-and-counted, never fabricated.",
        "date_et": date_et, "generated_at": et_now().isoformat(),
        "n_entry_fills": len(fills),
        "n_excluded_no_decision_row": n_excluded_no_decision_row,
        "n_excluded_missing_instrumentation": n_excluded_missing_instrumentation,
        "scope_arms": list(FLEET_REST_ARMS),
        "rows": rows,
        "summary": summarize(rows),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    return ledger


def main() -> int:
    ap = argparse.ArgumentParser(description="Fill-pipeline latency decomposition (descriptive only).")
    ap.add_argument("--date", default=None, help="ET date YYYY-MM-DD (default: today)")
    ap.add_argument("--out", default=None, help="override ledger output path")
    args = ap.parse_args()
    try:
        out = Path(args.out) if args.out else LEDGER_OUT
        ledger = build_ledger(date_et=args.date, out_path=out)
        print(f"[fill-latency] {ledger['date_et']}: {len(ledger['rows'])} scored / "
              f"{ledger['n_entry_fills']} entry fills "
              f"(missing_instrumentation={ledger['n_excluded_missing_instrumentation']}, "
              f"no_decision_row={ledger['n_excluded_no_decision_row']}) -> {out}")
    except Exception as e:  # noqa: BLE001 -- notify-only organ: never propagate a failure
        print(f"[fill-latency] ERROR (fail-open): {type(e).__name__}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
