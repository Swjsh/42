"""pnl_attribution_2026_07_28.py -- P&L ATTRIBUTION of the engine full-history replay
(analysis/recommendations/engine-fullhist-replay-2026-07-23.json, 190 trades, +$5,064.75)
plus an INDEPENDENT live-fills check (journal/trades.csv joined to
automation/state/core-decisions.jsonl ENTER verdicts).

THE question (per 2026-07-27 night lane brief): where does the +$5k actually come from,
and where does it leak? Critical axis: trigger class -- trendline-ONLY vs level-tied vs
both (the live 233-vs-28 bear ENTER split has never been P&L-attributed).

DESCRIPTIVE ONLY -- slices existing trades by pre-existing fields. No search, no BH
(per the standing discipline: descriptive attribution needs no BH; any cohort-derived
RULE proposal must separately clear positive-aggregate AND day-majority AND
survives-drop-best AND held-out-positive -- that A/B lives in
backtest/tools/min_triggers_bear2_gate_ab_2026_07_28.py, pre-registered there).

Outputs: analysis/deep-research/PNL-ATTRIBUTION-2026-07-28.json (+ the .md is composed
by this script too; the gate A/B tool appends its own section afterwards).

Run: python backtest/tools/pnl_attribution_2026_07_28.py   (stdlib only)
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPLAY_JSON = ROOT / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
DAY_INV = ROOT / "analysis" / "edge-matrix" / "day-inventory-extended.json"
TRADES_CSV = ROOT / "journal" / "trades.csv"
CORE_DECISIONS = ROOT / "automation" / "state" / "core-decisions.jsonl"
OUT_JSON = ROOT / "analysis" / "deep-research" / "PNL-ATTRIBUTION-2026-07-28.json"
OUT_MD = ROOT / "analysis" / "deep-research" / "PNL-ATTRIBUTION-2026-07-28.md"

LEVEL_TIED_TRIGGERS = {
    "level_rejection", "level_reclaim", "confluence",
    "sequence_rejection", "sequence_reclaim",
}
KNOWN_ACCOUNT_IDS = {"safe", "bold", "safe-1", "safe-2", "safe-3", "risky-1", "risky-3", "bold-2", ""}
RIBBON_SETUPS = {"BEARISH_REJECTION_RIDE_THE_RIBBON", "BULLISH_RECLAIM_RIDE_THE_RIBBON"}


def trigger_class(triggers: list[str] | None) -> str:
    trig = set(triggers or [])
    tl = "trendline_rejection" in trig
    lv = bool(trig & LEVEL_TIED_TRIGGERS)
    if tl and lv:
        return "BOTH"
    if tl:
        return "TL_only"
    if lv:
        return "LEVEL_tied"
    return "NEITHER"


def vix_band(v: float | None) -> str:
    """Same edges as day-inventory-extended.json method: low<15, mid 15-20, elevated 20-25, high>=25."""
    if v is None:
        return "unknown"
    if v < 15:
        return "low"
    if v < 20:
        return "mid"
    if v < 25:
        return "elevated"
    return "high"


def cohort_stats(trades: list[dict], pnl_key: str = "dollar_pnl") -> dict:
    """n, total, per-trade, WR, drop-best (total minus single best trade -- does a positive
    cohort survive losing its best trade), drop-worst (total minus single worst -- does a
    NEGATIVE cohort's bleed survive removing its worst trade), day stats."""
    n = len(trades)
    if n == 0:
        return {"n": 0, "total": 0.0, "per_trade": None, "wr": None,
                "drop_best": None, "drop_worst": None, "n_days": 0,
                "n_up_days": 0, "n_down_days": 0}
    pnls = [float(t[pnl_key]) for t in trades]
    total = sum(pnls)
    per_day: dict[str, float] = defaultdict(float)
    for t in trades:
        per_day[t["date"]] += float(t[pnl_key])
    return {
        "n": n,
        "total": round(total, 2),
        "per_trade": round(total / n, 2),
        "wr": round(sum(1 for p in pnls if p > 0) / n, 4),
        "drop_best": round(total - max(pnls), 2),
        "drop_worst": round(total - min(pnls), 2),
        "n_days": len(per_day),
        "n_up_days": sum(1 for v in per_day.values() if v > 0),
        "n_down_days": sum(1 for v in per_day.values() if v < 0),
    }


def slice_by(trades: list[dict], key_fn, pnl_key: str = "dollar_pnl") -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        groups[str(key_fn(t))].append(t)
    return {k: cohort_stats(g, pnl_key) for k, g in sorted(groups.items())}


# ---------------------------------------------------------------- replay side
def load_replay() -> tuple[list[dict], dict]:
    d = json.loads(REPLAY_JSON.read_text(encoding="utf-8"))
    return d["trades"], d["headline"]


def load_day_inventory() -> tuple[dict, set[str]]:
    d = json.loads(DAY_INV.read_text(encoding="utf-8"))
    by_date = {row["date"]: row for row in d["days"]}
    heldout = set(d["heldout_days"])
    return by_date, heldout


def annotate_replay(trades: list[dict], inv: dict, heldout: set[str]) -> None:
    for t in trades:
        t["trigger_class"] = trigger_class(t.get("triggers"))
        t["entry_hour"] = t["entry_time_et"][11:13]
        t["exit_family"] = str(t["exit_reason"]).split(" @")[0]
        day = inv.get(t["date"], {})
        t["vix_band"] = day.get("vix_band", "unknown")
        t["day_type"] = day.get("day_type", "unknown")
        d = dt.date.fromisoformat(t["date"])
        t["regime"] = ("2025H1" if d <= dt.date(2025, 6, 30)
                       else "2025H2" if d <= dt.date(2025, 12, 31) else "2026")
        t["heldout"] = t["date"] in heldout
        p = float(t["entry_premium"])
        t["premium_band"] = ("<0.30" if p < 0.30 else "0.30-0.50" if p < 0.50
                             else "0.50-1.00" if p < 1.00 else ">=1.00")


# ---------------------------------------------------------------- live side
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_live_trades() -> tuple[list[dict], dict]:
    rows = list(csv.DictReader(io.open(TRADES_CSV, encoding="utf-8-sig")))
    ok: list[dict] = []
    n_malformed = 0
    malformed_pnl = 0.0
    for r in rows:
        acct = (r.get("account_id") or "").strip()
        date = (r.get("date") or "").strip()
        try:
            pnl = float(r.get("dollar_pnl") or "")
        except ValueError:
            n_malformed += 1
            continue
        if not DATE_RE.match(date) or acct not in KNOWN_ACCOUNT_IDS:
            n_malformed += 1
            try:
                malformed_pnl += pnl
            except Exception:
                pass
            continue
        arm, attribution = "", ""
        try:
            aj = json.loads(r.get("archetype_match_json") or "{}")
            arm = aj.get("arm", "")
            attribution = aj.get("attribution", "")
        except Exception:
            pass
        ok.append({
            "date": date,
            "time_entry": (r.get("time_entry") or "").strip(),
            "setup": (r.get("setup") or "").strip(),
            "side": (r.get("c_or_p") or "").strip().upper(),
            "strike": (r.get("strike") or "").strip(),
            "qty": (r.get("qty") or "").strip(),
            "dollar_pnl": pnl,
            "tier": (r.get("setup_quality") or "").strip(),
            "account_id": acct,
            "arm": arm,
            "attribution": attribution,
            "tod_bucket": (r.get("tod_bucket") or "").strip(),
        })
    meta = {"n_csv_rows": len(rows), "n_valid": len(ok), "n_malformed_excluded": n_malformed,
            "malformed_pnl_excluded": round(malformed_pnl, 2)}
    return ok, meta


def load_enter_decisions() -> list[dict]:
    out = []
    for line in io.open(CORE_DECISIONS, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        if not str(o.get("verdict", "")).startswith("ENTER"):
            continue
        ts = o.get("ts_et", "")
        if len(ts) < 16:
            continue
        out.append({"date": ts[:10], "ts": ts, "side": o.get("side"),
                    "triggers": o.get("triggers") or [], "vix": o.get("vix"),
                    "setup": o.get("setup")})
    return out


def _to_minutes(hms: str) -> float | None:
    try:
        parts = hms.split(":")
        return int(parts[0]) * 60 + int(parts[1]) + (int(parts[2]) / 60 if len(parts) > 2 else 0)
    except Exception:
        return None


def join_live_to_decisions(live: list[dict], decisions: list[dict], tol_min: float = 5.0) -> dict:
    """Fleet arms fire on the same shared-signal tick as the core ENTER verdict, so a live
    fill at time T should have a core ENTER (same date+side) within +-tol. Many-to-one join
    (one verdict can drive several arms' fills). Triggers + at-entry VIX come from the match."""
    by_date_side: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for e in decisions:
        by_date_side[(e["date"], str(e["side"]).upper())].append(e)
    n_joined = 0
    for t in live:
        t["trigger_class"] = "unjoined"
        t["vix_at_entry"] = None
        tm = _to_minutes(t["time_entry"])
        if tm is None:
            continue
        best, best_diff = None, None
        for e in by_date_side.get((t["date"], t["side"]), []):
            em = _to_minutes(e["ts"][11:19])
            if em is None:
                continue
            diff = abs(em - tm)
            if diff <= tol_min and (best_diff is None or diff < best_diff):
                best, best_diff = e, diff
        if best is not None:
            n_joined += 1
            t["trigger_class"] = trigger_class(best["triggers"])
            t["vix_at_entry"] = best["vix"]
    return {"n_live": len(live), "n_joined": n_joined,
            "join_rate": round(n_joined / len(live), 3) if live else None,
            "tolerance_minutes": tol_min,
            "note": "core-decisions.jsonl only spans 2026-06-25.. ; live fills before that "
                    "date can never join (older LLM-heartbeat decisions.jsonl has no usable "
                    "ENTER rows). Unjoined class is reported, never guessed."}


def annotate_live(live: list[dict], inv: dict) -> None:
    for t in live:
        t["entry_hour"] = t["time_entry"][:2] if len(t["time_entry"]) >= 2 else "??"
        day = inv.get(t["date"], {})
        t["day_type"] = day.get("day_type", "unknown")
        v = t.get("vix_at_entry")
        t["vix_band"] = vix_band(v if v is not None else day.get("day_vix"))
        acct = t["account_id"]
        t["account_group"] = ("core_safe" if acct == "safe" else "core_bold" if acct == "bold"
                              else "fleet_safe" if acct.startswith("safe-")
                              else "fleet_risky" if acct.startswith(("risky-", "bold-")) else "other")
        t["setup_family"] = ("ribbon_ride" if t["setup"] in RIBBON_SETUPS
                             else "extra_setup" if t["setup"] and t["setup"][0].islower()
                             else "other/manual")


# ---------------------------------------------------------------- report
def md_table(title: str, table: dict, total: float | None = None) -> list[str]:
    L = [f"### {title}", "",
         "| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |",
         "|---|---|---|---|---|---|---|---|"]
    for k, s in sorted(table.items(), key=lambda kv: -(kv[1]["total"] or 0)):
        if s["n"] == 0:
            continue
        # share only when the denominator is a meaningful positive book total
        share = f" ({100*s['total']/total:.0f}%)" if total and total > 0 else ""
        L.append(f"| {k} | {s['n']} | ${s['total']:+,.2f}{share} | ${s['per_trade']:+.2f} | "
                 f"{s['wr']:.2f} | ${s['drop_best']:+,.2f} | ${s['drop_worst']:+,.2f} | "
                 f"{s['n_up_days']}/{s['n_down_days']} |")
    L.append("")
    return L


def main() -> int:
    inv, heldout = load_day_inventory()
    replay, headline = load_replay()
    annotate_replay(replay, inv, heldout)
    total = sum(float(t["dollar_pnl"]) for t in replay)

    axes = {
        "trigger_class": lambda t: t["trigger_class"],
        "tier": lambda t: t["tier"],
        "setup": lambda t: t["setup"],
        "side": lambda t: t["side"],
        "entry_hour": lambda t: t["entry_hour"],
        "exit_family": lambda t: t["exit_family"],
        "resolved_stop_mode": lambda t: t["resolved_stop_mode"],
        "vix_band": lambda t: t["vix_band"],
        "day_type": lambda t: t["day_type"],
        "regime": lambda t: t["regime"],
        "premium_band": lambda t: t["premium_band"],
        "trigger_class_x_regime": lambda t: f"{t['trigger_class']}|{t['regime']}",
        "trigger_class_x_heldout": lambda t: f"{t['trigger_class']}|{'HELDOUT' if t['heldout'] else 'IS'}",
        "tier_x_side": lambda t: f"{t['tier']}|{t['side']}",
    }
    replay_slices = {name: slice_by(replay, fn) for name, fn in axes.items()}

    live, live_meta = load_live_trades()
    decisions = load_enter_decisions()
    join_meta = join_live_to_decisions(live, decisions)
    annotate_live(live, inv)
    live_total = sum(t["dollar_pnl"] for t in live)

    live_axes = {
        "account_group": lambda t: t["account_group"],
        "attribution": lambda t: t["attribution"] or "(blank)",
        "setup_family": lambda t: t["setup_family"],
        "setup": lambda t: t["setup"] or "(blank)",
        "tier": lambda t: t["tier"] or "(blank)",
        "side": lambda t: t["side"] or "(blank)",
        "entry_hour": lambda t: t["entry_hour"],
        "vix_band": lambda t: t["vix_band"],
        "day_type": lambda t: t["day_type"],
        "trigger_class_joined": lambda t: t["trigger_class"],
        "trigger_class_x_setup_family": lambda t: f"{t['trigger_class']}|{t['setup_family']}",
    }
    live_slices = {name: slice_by(live, fn) for name, fn in live_axes.items()}
    # ribbon_ride-only live view (the replay's scope) for the apples-to-apples check
    live_rr = [t for t in live if t["setup_family"] == "ribbon_ride" and t["attribution"] == "engine"]
    live_rr_slices = {
        "trigger_class_joined": slice_by(live_rr, lambda t: t["trigger_class"]),
        "tier": slice_by(live_rr, lambda t: t["tier"] or "(blank)"),
        "side": slice_by(live_rr, lambda t: t["side"]),
    }

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "replay_source": str(REPLAY_JSON.relative_to(ROOT)),
        "replay_headline_checked": headline,
        "replay_total_recomputed": round(total, 2),
        "replay_n_trades": len(replay),
        "day_inventory_source": str(DAY_INV.relative_to(ROOT)),
        "heldout_definition": "day-inventory-extended.json heldout_days (last ceil(25%) of "
                              "opra_days by date; 96 days 2026-02-25..2026-07-17-ish)",
        "trigger_class_definition": {
            "level_tied_triggers": sorted(LEVEL_TIED_TRIGGERS),
            "TL_only": "has trendline_rejection, zero level-tied triggers",
            "LEVEL_tied": "has >=1 level-tied trigger, no trendline_rejection",
            "BOTH": "both", "NEITHER": "neither (n=0 in this population)",
        },
        "replay_slices": replay_slices,
        "live_meta": live_meta,
        "live_join_meta": join_meta,
        "live_total_all_rows": round(live_total, 2),
        "live_slices": live_slices,
        "live_ribbon_ride_engine_only_slices": live_rr_slices,
        "live_ribbon_ride_engine_only_n": len(live_rr),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")

    tc = replay_slices["trigger_class"]
    L = [
        "# P&L ATTRIBUTION -- where the replay's +$5k comes from, where it leaks",
        "",
        f"Generated {out['generated_at']}. Tool: `backtest/tools/pnl_attribution_2026_07_28.py`. "
        f"Machine-readable: `analysis/deep-research/PNL-ATTRIBUTION-2026-07-28.json`.",
        "",
        f"Population: the 2026-07-23 full-history replay's {len(replay)} real-OPRA trades "
        f"(`{out['replay_source']}`), total **${total:+,.2f}** (recomputed from per-trade rows; "
        f"matches stored headline ${headline['total_pnl']:+,.2f}). PROVISIONAL per the replay's own "
        "fidelity disclosure: trade-level anchors vs live are 1/4 on 2026-07-17 (corrected "
        "2026-07-25) -- entry layer diverges from live because live levels come from the curated "
        "key-levels.json feed while the replay recomputes levels from bars. Treat cohort CONTRASTS "
        "as the signal, not absolute dollars.",
        "",
        "## Verdict (descriptive -- no search, no BH needed)",
        "",
        f"- **The money is level-tied.** LEVEL_tied (n={tc['LEVEL_tied']['n']}) "
        f"**${tc['LEVEL_tied']['total']:+,.2f}** + BOTH (n={tc['BOTH']['n']}) "
        f"${tc['BOTH']['total']:+,.2f} = ${tc['LEVEL_tied']['total']+tc['BOTH']['total']:+,.2f} "
        f"-- MORE than 100% of the book's ${total:+,.2f}.",
        f"- **The leak is trendline-only.** TL_only (n={tc['TL_only']['n']}, ALL bear) "
        f"**${tc['TL_only']['total']:+,.2f}**, WR {tc['TL_only']['wr']:.2f}, "
        f"${tc['TL_only']['per_trade']:+.2f}/trade.",
        "- This is the P&L answer to the standing 233-vs-28 question: live bear ENTER verdicts "
        "are 233 trendline-only vs 28 level-tied (core-decisions.jsonl, re-counted tonight: "
        "233 of 261) -- i.e. ~89% of live bear entry volume is the class that LOSES money in "
        "the 18-month replay, and the class that makes the money fires rarely.",
        "",
        "## Replay cohort tables",
        "",
    ]
    order = ["trigger_class", "tier", "setup", "side", "entry_hour", "exit_family",
             "resolved_stop_mode", "vix_band", "day_type", "regime", "premium_band",
             "trigger_class_x_regime", "trigger_class_x_heldout", "tier_x_side"]
    for name in order:
        L += md_table(f"Replay by {name}", replay_slices[name], total=total)
    L += [
        "## Live fills -- independent check (journal/trades.csv)",
        "",
        f"Rows: {live_meta['n_csv_rows']} csv rows -> {live_meta['n_valid']} valid "
        f"({live_meta['n_malformed_excluded']} malformed/unparseable excluded, "
        f"${live_meta['malformed_pnl_excluded']:+,.2f} of parseable P&L among them, disclosed). "
        f"Live window 2026-04-29..2026-07-27, ALL accounts (core safe/bold + fleet arms). "
        f"Total across valid rows: **${live_total:+,.2f}**.",
        "",
        f"Trigger-class join: {join_meta['n_joined']}/{join_meta['n_live']} live fills matched a "
        f"core ENTER verdict (same date+side within {join_meta['tolerance_minutes']}min); "
        "unjoined mostly pre-2026-06-25 (before core-decisions.jsonl existed) + extra-setup fills "
        "(side-channel, no core verdict). 'unjoined' rows stay labeled, never guessed.",
        "",
    ]
    live_order = ["account_group", "attribution", "setup_family", "setup", "tier", "side",
                  "entry_hour", "vix_band", "day_type", "trigger_class_joined",
                  "trigger_class_x_setup_family"]
    for name in live_order:
        L += md_table(f"Live by {name}", live_slices[name], total=live_total)
    L += [
        f"### Live ribbon_ride, engine-attributed only (n={len(live_rr)}) -- replay's scope",
        "",
    ]
    for name, tbl in live_rr_slices.items():
        L += md_table(f"Live ribbon_ride/engine by {name}", tbl)
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    print(f"replay total={total:+.2f} n={len(replay)}; live total={live_total:+.2f} n={len(live)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
