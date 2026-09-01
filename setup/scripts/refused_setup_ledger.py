"""refused_setup_ledger.py -- what did the gates COST us?

WHY THIS EXISTS (J 2026-08-31). J asked, of a blocked setup Gamma had announced out loud:
"would that trade have made $?" Nothing in the rig could answer it. Three surfaces looked
like they should and none did:

  * quote-recorder      -- records only contracts an arm ALREADY HOLDS
                           (`arms_open_last_cycle: []` on a flat day)
  * entry-quality/shadow-- scores blocked-vs-kept among entries that HAPPENED
  * full_send_vs_gated  -- compares arms on a signal at least one arm TOOK

Every one of them starts from a trade. A gate-refused setup never becomes a trade, so it
falls through all three and is never scored again. The consequence: F8 (`VIX > 17.30 AND
rising`) blocked 334 of 334 scored ticks on 2026-08-31 and its CUMULATIVE DOLLAR COST has
never been computed -- so the gate can only ever be argued about, never adjudicated.

WHAT THIS DOES. Reads `core-decisions.jsonl` for a session, finds every tick where a side
had real triggers and a real score but was refused, collapses consecutive refusals into
EPISODES (one decision, not 300 duplicates), and records what contract that setup would
have used. That file is the capture side of the loop; `score` prices closed episodes
against recorded 1-minute OPRA bars when they exist.

⛔ MEASUREMENT ONLY. This module reads state and writes `analysis/refusals/`. It never
places an order, never edits params, never changes a gate. It exists so that retiring or
keeping a gate becomes an evidence question. Config-freeze safe by construction.

    python setup/scripts/refused_setup_ledger.py --date 2026-08-31
    python setup/scripts/refused_setup_ledger.py --date 2026-08-31 --score
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
DECISIONS = STATE / "core-decisions.jsonl"
OUT_DIR = REPO / "analysis" / "refusals"
HIGHRES = REPO / "backtest" / "data" / "highres"

# A refusal is only interesting if the setup was REAL. Score-only ticks with no trigger are
# noise -- the engine is supposed to sit on those, and counting them would drown the signal.
MIN_TRIGGERS = 1
MIN_SCORE = 6

# Blocker id -> name. Source: backtest/lib/filters.py module docstrings (bear list) and
# evaluate_bullish_setup's docstring (bull list). Kept as data, not prose, so the ledger
# reports "vix_gate" rather than "8" to anyone reading it later.
BEAR_BLOCKERS = {
    1: "time_gate_0935", 2: "news_window", 3: "budget", 4: "day_trades",
    5: "ribbon_not_bear", 6: "spread_below_30c", 7: "volume_divergence",
    8: "vix_gate_17.30_rising", 9: "breakdown_bar", 10: "htf_align_and_2of3_triggers",
}
BULL_BLOCKERS = {
    1: "time_gate_0935", 2: "news_window", 3: "budget", 4: "day_trades",
    5: "ribbon_not_bull", 6: "spread_below_30c", 7: "volume_divergence",
    8: "vix_soft", 9: "vix_hard_22", 10: "buyer_pressure",
    11: "min_triggers_and_htf",
}

sys.path.insert(0, str(REPO / "setup" / "scripts"))
try:
    from et_clock import et_now
except Exception:  # noqa: BLE001
    def et_now() -> dt.datetime:
        return dt.datetime.now() + dt.timedelta(hours=2)


# ── reading ───────────────────────────────────────────────────────────────────

def load_rows(date: str) -> list[dict]:
    if not DECISIONS.exists():
        return []
    out: list[dict] = []
    with open(DECISIONS, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line or date not in line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("ts_et", "")).startswith(date):
                out.append(row)
    out.sort(key=lambda r: (str(r.get("ts_et")), str(r.get("account"))))
    return out


def _refusal(row: dict, side: str) -> Optional[dict]:
    """This tick's refusal for `side`, or None if there was nothing to refuse."""
    if str(row.get("verdict", "")).startswith("ENTER"):
        return None                                   # it traded; not a refusal
    score = row.get(f"{side}_score")
    triggers = row.get(f"{side}_triggers_raw") or []
    blockers = row.get(f"{side}_blockers") or []
    if score is None or not blockers:
        return None
    if len(triggers) < MIN_TRIGGERS or score < MIN_SCORE:
        return None
    names = BEAR_BLOCKERS if side == "bear" else BULL_BLOCKERS
    level = row.get("bear_rejection_level_raw") if side == "bear" else row.get("bull_reclaim_level_raw")
    return {
        "ts_et": row.get("ts_et"), "account": row.get("account"), "side": side,
        "score": score, "triggers": list(triggers),
        "blockers": list(blockers),
        "blocker_names": [names.get(b, f"unknown_{b}") for b in blockers],
        "spy": row.get("spy"), "vix": row.get("vix"), "ribbon": row.get("ribbon"),
        "htf_15m": row.get("htf_15m"), "level": level,
    }


def _strike(spot: float, side: str) -> Optional[int]:
    """ATM strike the v15 Safe core would have used (fills-verified 2026-07-11: ATM)."""
    if spot is None:
        return None
    return int(round(float(spot)))


def _occ(strike: int, side: str, date: str) -> str:
    """OCC symbol for the 0DTE contract this refusal would have bought."""
    y, m, d = date.split("-")
    cp = "P" if side == "bear" else "C"
    return f"SPY{y[2:]}{m}{d}{cp}{strike * 1000:08d}"


# ── episodes ──────────────────────────────────────────────────────────────────

def build_episodes(rows: Iterable[dict], date: str, gap_minutes: float = 10.0) -> list[dict]:
    """Collapse per-tick refusals into episodes.

    One structural setup refused on 300 consecutive ticks is ONE decision, not 300. Without
    this the ledger would count the same refusal hundreds of times and any cost figure
    derived from it would be meaningless.
    """
    per_key: dict[tuple, list[dict]] = {}
    for row in rows:
        for side in ("bear", "bull"):
            ref = _refusal(row, side)
            if ref:
                per_key.setdefault((ref["account"], side), []).append(ref)

    episodes: list[dict] = []
    for (account, side), refs in sorted(per_key.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
        refs.sort(key=lambda r: str(r["ts_et"]))
        current: list[dict] = []
        for ref in refs:
            if current:
                prev = dt.datetime.fromisoformat(current[-1]["ts_et"])
                now = dt.datetime.fromisoformat(ref["ts_et"])
                if (now - prev).total_seconds() / 60.0 > gap_minutes:
                    episodes.append(_close_episode(current, date))
                    current = []
            current.append(ref)
        if current:
            episodes.append(_close_episode(current, date))
    episodes.sort(key=lambda e: e["first_ts_et"])
    return episodes


def _close_episode(refs: list[dict], date: str) -> dict:
    first, last = refs[0], refs[-1]
    scores = [r["score"] for r in refs if r["score"] is not None]
    # The blocker that held on EVERY tick is the binding one -- the single thing that,
    # alone, kept this setup out. Intersection, not most-common: a blocker present on
    # 99% of ticks did not block the other 1%.
    binding = set(refs[0]["blockers"])
    for r in refs[1:]:
        binding &= set(r["blockers"])
    names = BEAR_BLOCKERS if first["side"] == "bear" else BULL_BLOCKERS
    spot = first["spy"]
    strike = _strike(spot, first["side"])
    return {
        "date": date,
        "account": first["account"],
        "side": first["side"],
        "first_ts_et": first["ts_et"],
        "last_ts_et": last["ts_et"],
        "n_ticks": len(refs),
        "peak_score": max(scores) if scores else None,
        "triggers": sorted({t for r in refs for t in r["triggers"]}),
        "binding_blockers": sorted(binding),
        "binding_blocker_names": [names.get(b, f"unknown_{b}") for b in sorted(binding)],
        "spy_at_first": spot,
        "vix_at_first": first["vix"],
        "level": first["level"],
        "would_be_strike": strike,
        "would_be_contract": _occ(strike, first["side"], date) if strike else None,
        "scored": False,
        "score_result": None,
    }


# ── scoring (T+1, only where real option bars exist) ──────────────────────────

def _load_highres(contract: str, date: str) -> list[tuple[str, float, float, float, float]]:
    path = HIGHRES / f"{contract}_1m_{date}.csv"
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.append((r["timestamp_et"][11:16], float(r["open"]), float(r["high"]),
                        float(r["low"]), float(r["close"])))
    return out


def score_episode(ep: dict, *, cat_cap: float = -0.50, tp1: float = 0.30,
                  arm: float = 0.05, trail: float = 0.15,
                  eod: str = "15:50") -> Optional[dict]:
    """Price one refusal against real 1-minute OPRA bars, using v15 exit logic.

    Returns None when no recorded bars exist for the contract -- an HONEST null, never a
    modelled guess. A Black-Scholes stand-in here would manufacture exactly the kind of
    fake-precision number this ledger exists to replace.
    """
    contract = ep.get("would_be_contract")
    if not contract:
        return None
    bars = [b for b in _load_highres(contract, ep["date"]) if b[0] <= eod]
    if not bars:
        return None
    entry_t = ep["first_ts_et"][11:16]
    at_entry = [b for b in bars if b[0] >= entry_t]
    if not at_entry:
        return None
    entry = at_entry[0][4]
    if entry <= 0:
        return None

    hwm, armed, result = entry, False, None
    for t, _o, h, low, _c in at_entry[1:]:
        if (low - entry) / entry <= cat_cap:                 # adverse checked first
            result = ("catastrophe_cap", t, entry * (1 + cat_cap)); break
        if armed and low <= hwm * (1 - trail):
            result = ("chandelier_trail", t, hwm * (1 - trail)); break
        if (h - entry) / entry >= tp1:
            result = ("tp1", t, entry * (1 + tp1)); break
        if (h - entry) / entry >= arm:
            armed = True
        hwm = max(hwm, h)
    if result is None:
        result = ("eod_flatten", at_entry[-1][0], at_entry[-1][4])

    kind, exit_t, exit_px = result
    return {
        "contract": contract, "entry_t": at_entry[0][0], "entry_px": round(entry, 2),
        "exit_t": exit_t, "exit_px": round(exit_px, 2), "exit_kind": kind,
        "pct": round((exit_px - entry) / entry * 100, 1),
        "per_contract_usd": round((exit_px - entry) * 100, 2),
        "mfe_pct": round((max(b[2] for b in at_entry) - entry) / entry * 100, 1),
        "mae_pct": round((min(b[3] for b in at_entry) - entry) / entry * 100, 1),
        "basis": "recorded 1m OPRA bars; v15 exits; NO slippage/commission modelled",
    }


# ── main ──────────────────────────────────────────────────────────────────────

def build(date: str, do_score: bool) -> dict:
    rows = load_rows(date)
    episodes = build_episodes(rows, date)
    n_scored = 0
    if do_score:
        for ep in episodes:
            res = score_episode(ep)
            if res:
                ep["scored"] = True
                ep["score_result"] = res
                n_scored += 1

    # Per-blocker rollup: the number that was never computed.
    by_blocker: dict[str, dict[str, Any]] = {}
    for ep in episodes:
        for name in ep["binding_blocker_names"]:
            slot = by_blocker.setdefault(name, {"episodes": 0, "scored": 0, "usd": 0.0})
            slot["episodes"] += 1
            if ep["scored"]:
                slot["scored"] += 1
                slot["usd"] = round(slot["usd"] + ep["score_result"]["per_contract_usd"], 2)

    doc = {
        "_meta": {
            "date": date,
            "generated_at_et": et_now().isoformat(timespec="seconds"),
            "builder": "setup/scripts/refused_setup_ledger.py",
            "shadow_only": "MEASUREMENT ONLY -- never places, arms, or edits a gate.",
            "min_score": MIN_SCORE, "min_triggers": MIN_TRIGGERS,
            "ticks_read": len(rows),
            "unscored_note": ("episodes with scored=false have NO recorded option bars for "
                              "their contract -- an honest null, not a zero"),
        },
        "n_episodes": len(episodes),
        "n_scored": n_scored,
        "by_binding_blocker": dict(sorted(by_blocker.items(),
                                          key=lambda kv: -kv[1]["episodes"])),
        "episodes": episodes,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{date}.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return doc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default=None, help="session date (default: today ET)")
    ap.add_argument("--score", action="store_true",
                    help="also price episodes against recorded OPRA bars")
    a = ap.parse_args()
    date = a.date or et_now().date().isoformat()

    doc = build(date, a.score)
    print(f"[refusals] {date}: {doc['n_episodes']} episode(s) from "
          f"{doc['_meta']['ticks_read']} tick(s); {doc['n_scored']} scored")
    for name, agg in doc["by_binding_blocker"].items():
        usd = f"  scored {agg['scored']}, ${agg['usd']:+.2f}" if agg["scored"] else "  (unscored)"
        print(f"   {name:<32} {agg['episodes']:>3} episode(s){usd}")
    print(f"[refusals] -> {OUT_DIR / (date + '.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
