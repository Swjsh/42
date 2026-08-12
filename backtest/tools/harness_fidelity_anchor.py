#!/usr/bin/env python
"""harness_fidelity_anchor.py -- can the replay reproduce REALITY before it is trusted with a
counterfactual?

J, 2026-08-11: "It seems like you made a harness and then just wrote tests that would pass and
then shipped it as good."

That is precisely what happened with the pre-TP1 ladder. The chain was: build a harness -> write
guard tests asserting my own expectations -> run a population study through the same harness ->
declare PASS -> ship to live. Every step validated against my own assumptions. The harness turned
out to score a TP1 partial as a full exit, and the "+$6,454 ladder win" evaporated.

THE MISSING TEST, and the only one that could have caught it early:
    Feed each REAL position the config it ACTUALLY traded under.
    Walk it through the harness.
    Compare to the ACTUAL broker P&L.
If the harness cannot reproduce what really happened, no counterfactual it produces means
anything. This is an ANCHOR test -- the oracle is the broker, which cannot be argued with and
which I did not author.

WHAT A PASS LOOKS LIKE. Not exact equality -- the harness legitimately cannot see structure or
ribbon exits (no SPY feed), fills at the trigger price with no slippage, and resolves intra-bar
ordering optimistically. So the bar is:
  * the SIGN agrees on most positions,
  * the median absolute error is small relative to trade size,
  * and critically, the error is NOT SYSTEMATICALLY ONE-DIRECTIONAL -- a harness that is
    optimistic on every position will manufacture edge out of nothing in any A/B run through it.
The last one is what actually matters, and it is reported as the headline.

Reads the config each position really traded from its own placement row (stop_mode,
premium_stop_pct, tp1_premium_pct, tp1_qty_fraction, profit_lock_mode, trail_pct), so this is
not "the current registry applied retroactively" -- it is per-position historical truth.

$0, deterministic, no network, no LLM.
"""

from __future__ import annotations

import collections
import glob
import json
import os
import statistics as stt
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "backtest/lib", "backtest/tools", "automation/state/fleet"):
    _full = str(REPO / _p)
    if _full not in sys.path:
        sys.path.insert(0, _full)

import pandas as _pd  # noqa: E402

import strategies as st  # noqa: E402
from ladder_population_killcheck import load_positions  # noqa: E402
from lib.option_pricing_real import load_contract_bars  # noqa: E402
from multileg_exit_walk import walk  # noqa: E402

OUT = REPO / "analysis" / "deep-research" / "2026-08-11-audit" / "harness-fidelity.json"


# The CORE accounts (safe-2 / bold-2) do NOT write automation/state/fleet/<arm>/decisions.jsonl
# -- they are the heartbeat_core path and log to automation/state/core-decisions.jsonl under a
# DIFFERENT schema (no `placement` block; `exec` carries ABSOLUTE tp/stop prices and the strategy
# sits at top-level `setup`). placement_configs() globbed only the fleet directory, so every core
# position was invisible to every replay study -- 81 of 274 real fills silently excluded, and the
# exclusion read as "no OPRA data" rather than "this arm has no reader". C7: the harness reported
# a smaller population instead of reporting that it could not see two accounts.
_CORE_LEDGER = REPO / "automation/state/core-decisions.jsonl"
_CORE_ACCOUNT_TO_ARM = {"safe": "safe-2", "bold": "bold-2"}
# tp1_qty_fraction is NOT recorded in the core exec block. It comes from params.json, whose value
# last changed 2026-06-15 (git log -S) -- BEFORE this population's first fill (2026-06-26) -- so a
# current read is historically correct for every row in scope. Re-verify before extending the
# window earlier than 2026-06-15.
_CORE_TP1_QTY_FRACTION = {"safe-2": 0.8, "bold-2": 0.667}
_CORE_PARAMS_STABLE_SINCE = "2026-06-15"


def _core_placement_configs() -> dict:
    """(arm, symbol, date) -> exit config for the CORE accounts, rebuilt from core-decisions.jsonl.

    Provenance is stamped per field-group on every row so a downstream study can refuse
    lower-fidelity reconstructions:
      core:explicit -- the exec block recorded the field itself (highest fidelity)
      core:derived  -- computed from the recorded ABSOLUTE tp/stop against entry premium
      core:params   -- params.json, verified unchanged across the population window
    Only status == PLACED rows are indexed; RISK_DENY_*/SKIP_*/PLACE_FAIL never became positions.
    """
    out: dict = {}
    if not _CORE_LEDGER.exists():
        return out
    with open(_CORE_LEDGER, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if "SPY2" not in line:  # cheap prefilter -- the ledger is ~52MB of HOLD ticks
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            ex = r.get("exec") or {}
            sym = ex.get("symbol")
            if not sym or ex.get("status") != "PLACED":
                continue
            arm = _CORE_ACCOUNT_TO_ARM.get(r.get("account"))
            if not arm:
                continue
            prem = ex.get("premium")
            try:
                prem = float(prem)
            except (TypeError, ValueError):
                prem = 0.0
            prov: dict = {}

            def _pct(explicit_key: str, abs_key: str, label: str):
                """Prefer the explicitly-logged pct; else derive it from the absolute price."""
                v = ex.get(explicit_key)
                if v is not None:
                    prov[label] = "core:explicit"
                    return float(v)
                a = ex.get(abs_key)
                if a is None or prem <= 0:
                    prov[label] = "core:absent"
                    return None
                prov[label] = "core:derived"
                return float(a) / prem - 1.0

            tp1 = _pct("tp1_premium_pct", "tp", "tp1_premium_pct")
            stop = _pct("premium_stop_pct", "stop", "premium_stop_pct")
            if ex.get("stop_mode") is not None:
                prov["stop_mode"] = "core:explicit"
            prov["tp1_qty_fraction"] = "core:params"
            out[(arm, sym, str(r.get("ts_et", ""))[:10])] = {
                "stop_mode": ex.get("stop_mode"),
                "premium_stop_pct": stop,
                "tp1_premium_pct": tp1,
                "tp1_qty_fraction": _CORE_TP1_QTY_FRACTION.get(arm),
                "profit_lock_mode": ex.get("profit_lock_mode"),
                "trigger_level": ex.get("trigger_level"),
                "strategy": ex.get("setup") or r.get("setup"),
                "_provenance": prov,
                "_source": "core-decisions",
            }
    return out


def placement_configs() -> dict:
    """(arm, symbol, date) -> the exit config that position was ACTUALLY placed under.

    Fleet arms come from their own per-arm decisions.jsonl; the CORE accounts (safe-2/bold-2)
    are recovered from core-decisions.jsonl. Fleet rows are written LAST so that if a key ever
    appears in both, the higher-fidelity fleet placement block wins.
    """
    out: dict = _core_placement_configs()
    for p in glob.glob(str(REPO / "automation/state/fleet/*/decisions.jsonl")):
        arm = os.path.basename(os.path.dirname(p))
        for line in open(p, encoding="utf-8"):
            if not line.strip() or "placement" not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            pl = r.get("placement") or {}
            if not (pl.get("placed") and pl.get("symbol")):
                continue
            out[(arm, pl["symbol"], str(r.get("ts_et", ""))[:10])] = {
                "stop_mode": pl.get("stop_mode"),
                "premium_stop_pct": pl.get("premium_stop_pct"),
                "tp1_premium_pct": pl.get("tp1_premium_pct"),
                "tp1_qty_fraction": pl.get("tp1_qty_fraction"),
                "profit_lock_mode": pl.get("profit_lock_mode"),
                "trigger_level": pl.get("trigger_level"),
                "strategy": pl.get("strategy"),
                "_source": "fleet",
            }
    return out


def spy_by_day() -> dict:
    """{date: {"HH:MM": closed-5m SPY close}} -- the same feed the live engine threads into
    plan_exit_actions as last_closed_5m_close. Without it structure stops cannot fire."""
    import glob as _g
    # UNION all caches, dedupe by timestamp -- pick-biggest-file selected a cache ENDING
    # 2026-07-22, so every later date had NO SpY feed, structure stops silently could not
    # fire, and the K2 zone grid returned all-identical cells. Same bug already fixed in
    # regime_shadow_counter.py; this is the second copy (L294-class sibling copies).
    frames = []
    for f in _g.glob(str(REPO / "backtest/data/spy_5m_*.csv")):
        try:
            d = _pd.read_csv(f)
            # The caches are a FEED PATCHWORK (data-provenance strata): some files embed
            # "-04:00" offsets, some are naive wall-ET. Normalize PER FILE: aware -> convert
            # to NY; naive -> localize as wall-ET (their on-disk convention). Never utc=True
            # on a naive column -- that would silently shift wall-ET by 4-5 hours.
            ts = _pd.to_datetime(d["timestamp_et"], format="mixed")
            if ts.dt.tz is not None:
                ts = ts.dt.tz_convert("America/New_York")
            else:
                ts = ts.dt.tz_localize("America/New_York")
            d["ts"] = ts
            frames.append(d)
        except Exception:  # noqa: BLE001
            continue
    if not frames:
        return {}
    best = _pd.concat(frames, ignore_index=True).drop_duplicates(subset=["ts"])
    best = best.sort_values("ts")
    out: dict = {}
    for day, g in best.groupby(best["ts"].dt.strftime("%Y-%m-%d")):
        out[day] = dict(zip(g["ts"].dt.strftime("%H:%M"), g["close"].astype(float)))
    return out


def main() -> int:
    cfgs = placement_configs()
    spy = spy_by_day()
    slip = float(os.environ.get("SLIPPAGE", "0"))
    positions = load_positions()
    cache: dict = {}
    for s in sorted({p["symbol"] for p in positions}):
        try:
            d = load_contract_bars(s)
            cache[s] = d if d is not None and not d.empty else None
        except Exception:  # noqa: BLE001
            cache[s] = None

    base = st.by_name("ribbon_ride").exit.to_dict()
    rows: list = []
    for q in positions:
        bars = cache.get(q["symbol"])
        cfg = cfgs.get((q["arm"], q["symbol"], q["date"]))
        if bars is None or cfg is None:
            continue
        shape = dict(base)
        # every pre_tp1 knob OFF -- these positions traded BEFORE the ladder existed
        shape.update(pre_tp1_be_floor_arm_pct=None, pre_tp1_floor_pct=None, pre_tp1_ladder=None,
                     pre_tp1_trail_arm_pct=None, pre_tp1_trail_pct=None)
        for k in ("premium_stop_pct", "tp1_premium_pct", "tp1_qty_fraction",
                  "profit_lock_mode", "stop_mode"):
            if cfg.get(k) is not None:
                shape[k] = cfg[k]
        r = walk(q, shape, bars, trigger_level=float(cfg.get("trigger_level") or 0.0),
                 fill_mode=os.environ.get("FILL_MODE", "extreme"),
                 spy_closes=spy.get(q["date"]), slippage=slip)
        if "error" in r:
            continue
        rows.append({"arm": q["arm"], "date": q["date"], "symbol": q["symbol"],
                     "qty": q["qty"], "entry": q["entry_premium"],
                     "actual": float(q["actual_pnl"]), "replay": r["pnl"],
                     "err": round(r["pnl"] - float(q["actual_pnl"]), 2),
                     "stage_path": [l["stage"] for l in r["legs"]],
                     "strategy": cfg.get("strategy"), "stop_mode": cfg.get("stop_mode")})

    if not rows:
        print("no positions could be anchored")
        return 1

    errs = [r["err"] for r in rows]
    actual_tot = sum(r["actual"] for r in rows)
    replay_tot = sum(r["replay"] for r in rows)
    sign_ok = sum(1 for r in rows
                  if (r["actual"] > 0) == (r["replay"] > 0) or abs(r["err"]) < 1e-9)
    over = sum(1 for e in errs if e > 0)
    under = sum(1 for e in errs if e < 0)

    print(f"=== HARNESS FIDELITY vs BROKER TRUTH  (n={len(rows)} positions) ===")
    print(f"  ACTUAL total  {actual_tot:>+10.0f}")
    print(f"  REPLAY total  {replay_tot:>+10.0f}     bias {replay_tot - actual_tot:>+9.0f} "
          f"({(replay_tot - actual_tot) / len(rows):+.1f}/position)")
    print(f"  sign agreement      {sign_ok}/{len(rows)} = {sign_ok / len(rows) * 100:.0f}%")
    print(f"  median abs error    ${stt.median([abs(e) for e in errs]):,.0f}")
    print(f"  DIRECTIONAL BIAS    replay too HIGH on {over}, too LOW on {under}  "
          f"({over / len(rows) * 100:.0f}% optimistic)")
    print()
    print("  >>> the load-bearing number is DIRECTIONAL BIAS. A harness that is optimistic on")
    print("      most positions manufactures edge out of nothing in ANY A/B run through it.")
    print()

    bym = collections.defaultdict(list)
    for r in rows:
        bym[str(r["stop_mode"])].append(r["err"])
    print("  bias by stop_mode (where does the harness diverge most?):")
    for m, v in sorted(bym.items()):
        print(f"    {m:10s} n={len(v):<4d} mean err {stt.mean(v):>+8.1f}  median {stt.median(v):>+8.1f}")

    worst = sorted(rows, key=lambda r: -abs(r["err"]))[:8]
    print()
    print("  worst 8 divergences:")
    for r in worst:
        print(f"    {r['date']} {r['arm']:8s} {r['symbol'][-9:]} x{r['qty']:<3d} "
              f"actual {r['actual']:>+8.0f} replay {r['replay']:>+8.0f} err {r['err']:>+8.0f} "
              f"path={r['stage_path']}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "n": len(rows), "actual_total": actual_tot, "replay_total": replay_tot,
        "bias_total": replay_tot - actual_tot, "sign_agreement": sign_ok / len(rows),
        "median_abs_error": stt.median([abs(e) for e in errs]),
        "pct_optimistic": over / len(rows),
        "known_harness_limits": [
            "no SPY feed -> structure/ribbon exits cannot fire",
            "fills at the trigger price, no slippage",
            "5-min bars, intra-bar high/low order resolved optimistically",
        ],
        "rows": rows,
    }, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
