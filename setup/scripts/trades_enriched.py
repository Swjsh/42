"""trades_enriched.py -- canonical per-trade enriched ledger (built 2026-08-27).

THE GAP THIS CLOSES: every analysis in this repo (month_matrix.py, entry-quality reports,
pain-ledger, ad-hoc EOD scripts) hand-rolls the SAME join -- group fills-ledger.jsonl buy/sell
fills into round trips, then join each round trip back to the decision row that ordered it
(core-decisions.jsonl for safe-2/bold-2, automation/state/fleet/*/decisions.jsonl for the
fleet arms) to recover setup/tier/scores/context. This script does that join ONCE,
deterministically, and writes the result to analysis/trades-enriched.jsonl so nothing else
has to re-derive it. $0, stdlib only, no broker imports, no LLM.

JOIN MECHANICS (C9 -- anchored to __file__, never CWD):
  1. Round trips: group option fills from fills-ledger.jsonl by (date_et, arm, symbol), THEN
     split that bucket into separate trips at every buy-to-flat-to-buy boundary (a symbol
     re-entered same day, e.g. vwap_continuation firing 3x on one strike, is 3 trips, not 1
     -- AUDIT FIX 2026-08-27: the pre-fix version merged all fills for a (date,arm,symbol)
     key into one row; pnl stayed correct (additive) but hold_min/entry_px/entry_hour_et/
     ctx-setup were silently wrong for merged rows -- confirmed real case: 2026-06-30 safe-1
     SPY260630C00750000 reported hold_min=170 for two actual <35min 0DTE scalps. 62 of 268
     buckets / 109 trips were affected). Balanced (sum buy qty == sum sell qty) -> a closed
     round trip. Unbalanced -> still emitted with unbalanced=true (never dropped -- C7 audit
     outputs, not exit codes).
  2. Context join: PRIMARY by entry order_id -- any buy fill's order_id matched against the
     entry decision row's broker order id (core: exec.broker.id after mapping account
     safe|bold -> arm safe-2|bold-2; fleet: placement.broker.id, arm from arm_id).
     FALLBACK: (date, arm, symbol) key when no order_id match exists.
  3. Exit reason: best-effort scan of exit_pass rows for the same (date, arm, symbol) whose
     timestamp falls inside [entry_ts, exit_ts] (+/- 2 min slack), collecting the SELL_ALL /
     SELL_PARTIAL stage names (premium_stop, tp1, trail, structure_stop, ribbon_flip,
     time_stop, runner_target). Never fabricated -- null when nothing matches.

     KNOWN UPSTREAM LABEL BUG, DISCLOSED NOT FIXED HERE (2026-08-27 A3 audit):
     exit_manager.py's stage="premium_stop" is a HARDCODED label whenever the pre-TP1
     exit-ALL check fires (worst_premium <= runner_stop), and it is only disambiguated from
     a ratcheted profit-lock floor exit (stage="profit_lock_floor") when floor_active checks
     TRUE -- which only covers profit_lock_arm_scope=="full" or pre_tp1_be_floor_arm_pct
     (the 2026-07-23 fix, commit c4ee425a). It was never extended to cover the LADDER/TRAIL
     knobs added 2026-08-10 (pre_tp1_ladder, pre_tp1_trail_arm_pct/pre_tp1_trail_pct -- LIVE
     on ribbon_ride, the strategy every account trades). So a pre-TP1 exit whose floor was
     raised ONLY by the ladder/trail still gets tagged stage="premium_stop" even when it
     closed at a PROFIT. Real-tape proof (2026-08-27 audit, no exit_manager.py change made):
     17 of 268 rows with exit_reason containing "premium_stop" closed with POSITIVE
     pnl_dollars (up to +$285 / +57.6% return) -- mathematically impossible for a genuine
     catastrophe/premium-floor hit. This script surfaces that fact via the
     `exit_reason_premium_stop_suspect` field (true when the row's own pnl/exit-vs-planned-
     stop data PROVES the tag can't be a raw stop hit) rather than silently trusting or
     silently rewriting the upstream label -- the real fix belongs in exit_manager.py's
     floor_active check, which is a live-order-path file outside this audit's authorized
     scope (blast-radius review needed: exit_manager_walk.py, t4_exit_matrix.py,
     hold_posture_ab_study.py, catastrophe_cap_shadow_ledger.py, pain_ledger.py all consume
     ExitAction.stage today, per the 2026-07-23 fix's own blast-radius note).

Idempotent full rebuild every run: reads all history in fills-ledger.jsonl (from 2026-06-29),
writes the WHOLE output fresh each time (no incremental merge, no accumulation drift).

Run:  backtest/.venv/Scripts/python.exe setup/scripts/trades_enriched.py [--quiet]
      (plain `python` also works -- stdlib only, no pandas/venv deps)
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
FILLS_PATH = STATE / "fills-ledger.jsonl"
CORE_DECISIONS_PATH = STATE / "core-decisions.jsonl"
FLEET_DIR = STATE / "fleet"
OUT_PATH = REPO / "analysis" / "trades-enriched.jsonl"

ACCOUNT_TO_ARM = {"safe": "safe-2", "bold": "bold-2"}
EXIT_SLACK_S = 120  # +/- 2 min around [entry_ts, exit_ts] when matching exit_pass rows

_TIER_RE = re.compile(r"tier (\w+)")
_SYM_RE = re.compile(r"^[A-Z]+\d{6}([CP])(\d{8})$")


# --------------------------------------------------------------------------- #
# Small parsing helpers -- fail loud on genuinely malformed data, fail open
# (return None) only on genuinely-optional/missing fields (C7).
# --------------------------------------------------------------------------- #

def _parse_ts(s: Optional[str]) -> Optional[datetime]:
    """Naive datetime, tz-info stripped. Fills/core ts_et are already naive local ET;
    fleet ts_et carries a numeric UTC offset (e.g. '-04:00') -- strip it so all three
    sources compare on the same naive-ET clock (0DTE round trips never cross midnight,
    so this is safe and matches month_matrix.py's reference behavior)."""
    if not s:
        return None
    s = str(s)
    # strip a trailing numeric UTC offset like -04:00 or +05:30 (not a 'Z')
    m = re.match(r"^(.*?)([+-]\d{2}:\d{2})$", s)
    if m:
        s = m.group(1)
    s = s.rstrip("Z")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def parse_symbol(symbol: str) -> tuple:
    """(right, strike) from an OCC-style option symbol, e.g. SPY260827C00768000 -> ('C', 768.0).
    Returns (None, None) on anything that doesn't match -- never raises, never guesses."""
    m = _SYM_RE.match(symbol or "")
    if not m:
        return None, None
    return m.group(1), int(m.group(2)) / 1000.0


# --------------------------------------------------------------------------- #
# Step 1: round trips from fills-ledger.jsonl
# --------------------------------------------------------------------------- #

def load_fills(path: Path = FILLS_PATH) -> list:
    fills = []
    with path.open(encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                fills.append(json.loads(ln))
            except json.JSONDecodeError:
                continue  # a single corrupt line must not kill the whole rebuild (C7)
    return fills


def _split_same_symbol_fills_into_trips(fs: list) -> list:
    """AUDIT FIX (2026-08-27, A3 code audit): a (date,arm,symbol) bucket can contain MORE
    than one real round trip -- e.g. vwap_continuation firing 3 separate entries on the same
    strike in one session (buy->flat->buy->flat->buy->flat). The pre-fix version bucketed
    ALL fills for a (date,arm,symbol) key into ONE merged 'trip': pnl_dollars stayed correct
    (additive), but hold_min, entry_hour_et, entry_px, ctx/setup attribution, and qty were all
    silently WRONG (hold_min could span the gap between unrelated trips -- confirmed real
    case 2026-06-30 safe-1 SPY260630C00750000: reported hold_min=170 for what were actually
    two <15-min 0DTE scalps). Real-tape audit: 62 of 268 (date,arm,symbol) buckets contained
    >1 real trip, 109 trips were being silently merged away.

    This walks fills (already ts-sorted by the caller) and starts a NEW trip group whenever a
    buy arrives while the running position is flat (0) -- i.e. every buy-to-flat-to-buy cycle
    becomes its own group. Never drops a fill (C7): a stray fill before any buy (e.g. an
    unmatched sell) still opens a group rather than being discarded."""
    groups: list = []
    current: list = []
    pos = 0.0
    for f in fs:
        q = f.get("qty", 0) or 0
        if not current:
            current = [f]
            pos = q if f["side"] == "buy" else -q
            continue
        current.append(f)
        pos += q if f["side"] == "buy" else -q
        if abs(pos) < 1e-9:
            groups.append(current)
            current = []
            pos = 0.0
    if current:
        groups.append(current)
    return groups


def _trip_from_fills(date: str, arm: str, symbol: str, fs: list) -> dict:
    buys = [f for f in fs if f["side"] == "buy"]
    sells = [f for f in fs if f["side"] == "sell"]
    buy_qty = sum(f["qty"] for f in buys)
    sell_qty = sum(f["qty"] for f in sells)
    unbalanced = (not buys) or (not sells) or abs(buy_qty - sell_qty) > 1e-6

    right, strike = parse_symbol(symbol)
    # multiplier is constant per contract (100 for every real SPY/equity option fill in this
    # ledger) -- sourced from the FIRST sell fill itself, never a stray loop-leaked variable
    # (AUDIT FIX: the pre-fix version read a bare `f` here that was left over from the
    # module-level `for f in fills:` bucketing loop, i.e. an unrelated fill from the END of
    # the ENTIRE input list, not this trip's own sells -- latent because multiplier is always
    # 100 in practice for this instrument, but a real correctness bug, not a nicety).
    multiplier = (sells[0].get("multiplier", 100) if sells else
                  (buys[0].get("multiplier", 100) if buys else 100))
    cost = sum(f["qty"] * f["price"] * f.get("multiplier", 100) for f in buys)
    proceeds = sum(f["qty"] * f["price"] * f.get("multiplier", 100) for f in sells)
    pnl = round(proceeds - cost, 2) if not unbalanced else None
    entry_ts = _parse_ts(buys[0]["ts_et"]) if buys else None
    exit_ts = _parse_ts(sells[-1]["ts_et"]) if sells else None
    hold_min = (
        round((exit_ts - entry_ts).total_seconds() / 60, 1)
        if entry_ts and exit_ts else None
    )
    attribution = "manual" if any(f.get("attribution") != "engine" for f in fs) else "engine"
    if any(f.get("attribution") == "engine" for f in fs) and attribution == "manual":
        attribution = "mixed"

    return {
        "date": date,
        "arm": arm,
        "symbol": symbol,
        "right": right,
        "strike": strike,
        "qty": buy_qty if buys else sell_qty,
        "entry_ts_et": buys[0]["ts_et"] if buys else None,
        "exit_ts_et": sells[-1]["ts_et"] if sells else None,
        "entry_hour_et": (entry_ts.hour + entry_ts.minute / 60) if entry_ts else None,
        "hold_min": hold_min,
        "entry_px": buys[0]["price"] if buys else None,
        "exit_px_avg": round(proceeds / multiplier / sell_qty, 4) if sells and sell_qty else None,
        "cost_dollars": round(cost, 2) if buys else None,
        "pnl_dollars": pnl,
        "ret_pct_of_premium": round(100 * (proceeds - cost) / cost, 2) if (not unbalanced and cost) else None,
        "attribution": attribution,
        "entry_order_ids": [f.get("order_id") for f in buys],
        "unbalanced": unbalanced,
        "_entry_ts_parsed": entry_ts,
        "_exit_ts_parsed": exit_ts,
    }


def build_round_trips(fills: list) -> list:
    buckets = collections.defaultdict(list)
    for f in fills:
        if f.get("is_option"):
            buckets[(f["date_et"], f["arm"], f["symbol"])].append(f)

    trips = []
    for (date, arm, symbol), fs in buckets.items():
        fs = sorted(fs, key=lambda x: x.get("ts_utc") or x.get("ts_et") or "")
        for leg in _split_same_symbol_fills_into_trips(fs):
            trips.append(_trip_from_fills(date, arm, symbol, leg))
    return trips


# --------------------------------------------------------------------------- #
# Step 2: context join -- core-decisions.jsonl (safe-2/bold-2) + fleet decisions
# --------------------------------------------------------------------------- #

CTX_FIELDS = (
    "setup", "tier", "bull_score", "bear_score", "vix", "ribbon", "spread_cents",
    "htf_15m", "triggers", "trigger_level", "stop_mode", "planned_stop", "planned_tp",
)


def _ctx_extras_from_bundle(cb: Optional[dict]) -> Optional[dict]:
    if not isinstance(cb, dict):
        return None
    per_tf = cb.get("per_tf") or {}
    per_tf_trends = {
        tf: v.get("trend") for tf, v in per_tf.items() if isinstance(v, dict)
    }
    today_ctx = cb.get("today_context") or {}
    levels_ctx = cb.get("levels_context") or {}
    events = cb.get("events") or {}
    return {
        "alignment_score": cb.get("alignment_score"),
        "per_tf_trends": per_tf_trends or None,
        "gap_pct_at_open": today_ctx.get("gap_pct_at_open"),
        "rvol_session_so_far": today_ctx.get("rvol_session_so_far"),
        "nearest_level_above_dist": (levels_ctx.get("nearest_level_above") or {}).get("distance"),
        "nearest_level_below_dist": (levels_ctx.get("nearest_level_below") or {}).get("distance"),
        "no_trade_window_active": events.get("no_trade_window_active"),
    }


def _note_ctx(ctx_by_key, ctx_by_order, key, ctx, order_id):
    if key not in ctx_by_key:
        ctx_by_key[key] = ctx
    if order_id and order_id not in ctx_by_order:
        ctx_by_order[order_id] = ctx


def load_context(core_path: Path = CORE_DECISIONS_PATH, fleet_dir: Path = FLEET_DIR):
    """Returns (ctx_by_order, ctx_by_key, exit_events).
    exit_events: (date, arm, symbol) -> list of (ts: datetime|None, stage: str)."""
    ctx_by_order: dict = {}
    ctx_by_key: dict = {}
    exit_events: dict = collections.defaultdict(list)

    def _collect_exit_pass(date, arm, symbol_hint, row_ts, exit_pass):
        for e in exit_pass or []:
            if not isinstance(e, dict):
                continue
            sym = e.get("symbol") or symbol_hint
            if not sym:
                continue
            for act in e.get("actions") or []:
                if not isinstance(act, dict):
                    continue
                if act.get("kind") not in ("SELL_ALL", "SELL_PARTIAL"):
                    continue
                if not act.get("placed"):
                    continue
                stage = act.get("stage") or act.get("kind")
                exit_events[(date, arm, sym)].append((row_ts, stage))

    # ---- core-decisions.jsonl (safe-2 / bold-2) ----
    if core_path.exists():
        with core_path.open(encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    r = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                arm = ACCOUNT_TO_ARM.get(r.get("account"), r.get("account"))
                date = str(r.get("ts_et") or "")[:10]
                row_ts = _parse_ts(r.get("ts_et"))
                _collect_exit_pass(date, arm, None, row_ts, r.get("exit_pass"))

                if r.get("verdict") not in ("ENTER_BULL", "ENTER_BEAR"):
                    continue
                exec_ = r.get("exec") or {}
                symbol = exec_.get("symbol") or r.get("symbol")
                if not symbol:
                    continue
                m = _TIER_RE.search(r.get("reason") or "")
                ctx = {
                    "setup": r.get("setup"),
                    "tier": m.group(1) if m else None,
                    "bull_score": r.get("bull_score"),
                    "bear_score": r.get("bear_score"),
                    "vix": r.get("vix"),
                    "ribbon": r.get("ribbon"),
                    "spread_cents": r.get("spread_cents"),
                    "htf_15m": r.get("htf_15m"),
                    "triggers": r.get("triggers"),
                    "trigger_level": r.get("trigger_level_exact"),
                    "stop_mode": exec_.get("stop_mode"),
                    "planned_stop": exec_.get("stop"),
                    "planned_tp": exec_.get("tp"),
                    "ctx_extras": _ctx_extras_from_bundle(r.get("context_bundle")),
                }
                order_id = (exec_.get("broker") or {}).get("id")
                _note_ctx(ctx_by_key, ctx_by_order, (date, arm, symbol), ctx, order_id)

    # ---- fleet arms ----
    fleet_files = sorted(fleet_dir.glob("*/decisions.jsonl")) if fleet_dir.exists() else []
    for p in fleet_files:
        arm = p.parent.name
        with p.open(encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    r = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                date = str(r.get("ts_et") or "")[:10]
                row_ts = _parse_ts(r.get("ts_et"))
                _collect_exit_pass(date, arm, None, row_ts, r.get("exit_pass"))

                if not str(r.get("action", "")).startswith("ENTER"):
                    continue
                pl = r.get("placement") or {}
                symbol = pl.get("symbol") or r.get("symbol")
                if not symbol:
                    continue
                ctx = {
                    "setup": r.get("setup_name"),
                    "tier": r.get("quality"),
                    "bull_score": None,
                    "bear_score": None,
                    "vix": None,
                    "ribbon": None,
                    "spread_cents": None,
                    "htf_15m": None,
                    "triggers": None,
                    "trigger_level": None,
                    "stop_mode": pl.get("stop_mode"),
                    "planned_stop": pl.get("stop"),
                    "planned_tp": pl.get("tp"),
                    "ctx_extras": None,
                }
                order_id = (pl.get("broker") or {}).get("id")
                _note_ctx(ctx_by_key, ctx_by_order, (date, arm, symbol), ctx, order_id)

    return ctx_by_order, ctx_by_key, exit_events


def _exit_reason_for(trip: dict, exit_events: dict) -> Optional[str]:
    key = (trip["date"], trip["arm"], trip["symbol"])
    events = exit_events.get(key)
    if not events:
        return None
    entry_ts = trip["_entry_ts_parsed"]
    exit_ts = trip["_exit_ts_parsed"]
    stages = set()
    for ts, stage in events:
        if entry_ts is None or exit_ts is None or ts is None:
            stages.add(stage)  # can't bound the window -- best effort, include it
            continue
        lo = entry_ts.timestamp() - EXIT_SLACK_S
        hi = exit_ts.timestamp() + EXIT_SLACK_S
        if lo <= ts.timestamp() <= hi:
            stages.add(stage)
    if not stages:
        return None
    return "+".join(sorted(stages))


# --------------------------------------------------------------------------- #
# Step 3: join + write
# --------------------------------------------------------------------------- #

def _premium_stop_suspect(row: dict) -> Optional[bool]:
    """True when the row's OWN pnl/price data PROVES an exit_reason "premium_stop" tag
    cannot be a raw catastrophe/premium-floor hit (see the module docstring's KNOWN
    UPSTREAM LABEL BUG section) -- i.e. exit_manager.py's stage label is disclosed-suspect
    for this row. None when exit_reason doesn't carry "premium_stop" at all (not applicable).
    False when it does carry the tag but nothing in this row's own data disproves it (most
    genuine catastrophe-cap hits land here -- this is NOT proof the tag IS correct, only that
    this cheap check found no contradiction). Never fabricated: only flags what the row's own
    numbers can prove, using no strategy-specific knowledge of the raw stop pct."""
    reason = row.get("exit_reason") or ""
    if "premium_stop" not in reason.split("+"):
        return None
    pnl = row.get("pnl_dollars")
    if pnl is not None and pnl > 0:
        return True  # a raw premium/catastrophe stop can never close at a profit
    exit_px = row.get("exit_px_avg")
    planned_stop = row.get("planned_stop")
    if exit_px is not None and planned_stop is not None and exit_px > planned_stop + 1e-6:
        return True  # exit filled ABOVE the raw stop level set at entry -> floor had ratcheted
    return False


def enrich(trips: list, ctx_by_order: dict, ctx_by_key: dict, exit_events: dict) -> tuple:
    matched = 0
    unmatched_keys = []
    rows = []
    for t in trips:
        ctx = None
        for oid in t["entry_order_ids"]:
            if oid and oid in ctx_by_order:
                ctx = ctx_by_order[oid]
                break
        if ctx is None:
            ctx = ctx_by_key.get((t["date"], t["arm"], t["symbol"]))
        ctx_matched = ctx is not None
        if ctx_matched:
            matched += 1
        else:
            unmatched_keys.append([t["date"], t["arm"], t["symbol"]])

        row = {k: v for k, v in t.items() if not k.startswith("_")}
        row["ctx_matched"] = ctx_matched
        for f in CTX_FIELDS:
            row[f] = (ctx or {}).get(f)
        row["ctx_extras"] = (ctx or {}).get("ctx_extras")
        row["exit_reason"] = _exit_reason_for(t, exit_events)
        row["exit_reason_premium_stop_suspect"] = _premium_stop_suspect(row)
        rows.append(row)
    rows.sort(key=lambda r: (r["date"], r["arm"], r["symbol"]))
    return rows, matched, unmatched_keys


def rebuild(repo: Path = REPO) -> dict:
    fills_path = repo / "automation" / "state" / "fills-ledger.jsonl"
    core_path = repo / "automation" / "state" / "core-decisions.jsonl"
    fleet_dir = repo / "automation" / "state" / "fleet"
    out_path = repo / "analysis" / "trades-enriched.jsonl"

    fills = load_fills(fills_path)
    trips = build_round_trips(fills)
    ctx_by_order, ctx_by_key, exit_events = load_context(core_path, fleet_dir)
    rows, matched, unmatched = enrich(trips, ctx_by_order, ctx_by_key, exit_events)

    n_engine = sum(1 for r in rows if r["attribution"] == "engine")
    n_with_exit_reason = sum(1 for r in rows if r.get("exit_reason"))
    n_unbalanced = sum(1 for r in rows if r["unbalanced"])
    n_premium_stop_tagged = sum(1 for r in rows if "premium_stop" in (r.get("exit_reason") or "").split("+"))
    n_premium_stop_suspect = sum(1 for r in rows if r.get("exit_reason_premium_stop_suspect") is True)
    meta = {
        "_meta": True,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_rows": len(rows),
        "n_engine": n_engine,
        "n_manual_or_mixed": len(rows) - n_engine,
        "n_unbalanced": n_unbalanced,
        "ctx_matched": matched,
        "ctx_match_rate": round(matched / len(rows), 4) if rows else None,
        "exit_reason_matched": n_with_exit_reason,
        "exit_reason_match_rate": round(n_with_exit_reason / len(rows), 4) if rows else None,
        "exit_reason_premium_stop_tagged": n_premium_stop_tagged,
        "exit_reason_premium_stop_suspect": n_premium_stop_suspect,
        "exit_reason_premium_stop_suspect_doc": (
            "count of rows whose exit_reason contains 'premium_stop' but whose OWN "
            "pnl_dollars/exit_px_avg PROVES it cannot be a raw catastrophe/premium-floor "
            "hit (upstream exit_manager.py stage-label gap, see module docstring "
            "KNOWN UPSTREAM LABEL BUG -- not fixed here, disclosed per row instead)."
        ),
        "unmatched": unmatched,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(meta, default=str) + "\n")
        for row in rows:
            fh.write(json.dumps(row, default=str) + "\n")

    return {"meta": meta, "rows": rows}


# --------------------------------------------------------------------------- #
# Verification -- known-good checks quoted in CLAUDE.md C7 (audit outputs, not
# exit codes). Fails LOUD (nonzero exit + printed mismatch) on any drift.
# --------------------------------------------------------------------------- #

def _engine_rows_for(rows: list, date: str = None, lo: str = None, hi: str = None) -> list:
    out = []
    for r in rows:
        if r["attribution"] != "engine" or r["unbalanced"]:
            continue
        if date is not None and r["date"] != date:
            continue
        if lo is not None and not (lo <= r["date"] <= hi):
            continue
        out.append(r)
    return out


def run_verification(rows: list, *, quiet: bool = False) -> bool:
    ok = True

    d1 = "2026-08-27"
    day_rows = _engine_rows_for(rows, date=d1)
    day_n, day_pnl = len(day_rows), sum(r["pnl_dollars"] for r in day_rows)
    d1_ok = day_n == 12 and abs(day_pnl - 1897.0) <= 5
    ok = ok and d1_ok
    print(f"[verify] {d1} engine round trips: n={day_n} (want 12) "
          f"pnl=${day_pnl:.2f} (want +$1897 +/-$5) -> {'PASS' if d1_ok else 'FAIL'}")

    mon_rows = _engine_rows_for(rows, lo="2026-08-01", hi="2026-08-31")
    mon_pnl = sum(r["pnl_dollars"] for r in mon_rows)
    mon_ok = abs(mon_pnl - 1744.0) <= 10
    ok = ok and mon_ok
    print(f"[verify] August 2026 engine total: n={len(mon_rows)} pnl=${mon_pnl:.2f} "
          f"(want +$1744 +/-$10) -> {'PASS' if mon_ok else 'FAIL'}")

    if not ok and not quiet:
        print("[verify] MISMATCH -- known-good checks failed. Root cause before trusting "
              "this ledger for anything downstream.", file=sys.stderr)
    return ok


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true", help="suppress row-level output, keep summary")
    args = ap.parse_args()

    result = rebuild(REPO)
    meta = result["meta"]

    print(f"[trades_enriched] wrote {meta['n_rows']} rows to {OUT_PATH.relative_to(REPO)}")
    print(f"[trades_enriched] engine={meta['n_engine']} manual/mixed={meta['n_manual_or_mixed']} "
          f"unbalanced={meta['n_unbalanced']}")
    print(f"[trades_enriched] ctx_matched={meta['ctx_matched']}/{meta['n_rows']} "
          f"({meta['ctx_match_rate']:.1%})" if meta["ctx_match_rate"] is not None else
          "[trades_enriched] ctx_matched=0/0")
    print(f"[trades_enriched] exit_reason_matched={meta['exit_reason_matched']}/{meta['n_rows']} "
          f"({meta['exit_reason_match_rate']:.1%})" if meta["exit_reason_match_rate"] is not None else
          "[trades_enriched] exit_reason_matched=0/0")
    if meta["unmatched"]:
        print(f"[trades_enriched] {len(meta['unmatched'])} unmatched (date,arm,symbol) rows "
              f"listed in _meta.unmatched (not dropped, per C7)")

    ok = run_verification(result["rows"], quiet=args.quiet)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
