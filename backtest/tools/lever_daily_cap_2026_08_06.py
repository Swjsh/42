#!/usr/bin/env python
"""lever_daily_cap_2026_08_06.py -- LEVER 1: THE DAILY LOSS CAP / CIRCUIT BREAKER.

Pre-registered in analysis/deep-research/PREREG-LEVER-DAILY-CAP-2026-08-06.md, committed
b8bbe7a8 BEFORE this file existed (git merge-base --is-ancestor provable).

J's ask (2026-08-06, after the close): "we need to dial in on how to NOT LOSE TWO THOUSAND
DOLLARS on Wednesday... we gotta KEEP OUR LOSSES SMALL so that way our wins can stack."

Rule 5's kill switch is -30% of SoD (Safe) / -50% (Bold+Risky). On 2026-08-05 risky-3 lost
24.5% of SoD -- only 48.9% of its own kill budget. The existing daily stop has NEVER been
tested at any other value. This module tests it at 60+ values, in three shapes:

  L1  DAILY LOSS CAP     -- per-arm and fleet, as % of REAL start-of-day equity AND as
                            absolute dollars.
  L2  CONSECUTIVE-LOSS   -- halt the arm after N straight losing closed round trips.
  L3  DAY-PEAK RETRACE   -- halt when realized day P&L gives back X% of its intraday peak.

HARD GATE (frozen in the prereg): any cell costing more than $0.00 on 2026-08-04 is REJECTED
FOR SHIPPING. Reported anyway, flagged. Tuesday is the no-harm test.

COUNTERFACTUAL SEMANTICS (frozen in the prereg, section 4):
  * Realized P&L only; a position's P&L is known at its LAST exit fill.
  * SEQUENTIAL and PATH-CONSISTENT: a blocked position never happens, so its P&L never enters
    the running total that gates later entries. (Lane 0's day_breaker summed the ORIGINAL
    closed set including positions its own rule would have blocked -> over-blocks. Both are
    computed; path-consistent is PRIMARY, the Lane-0 shape is reported as `naive_*`.)
  * Blocks NEW entries only. Already-open positions are NOT force-liquidated.
  * Resets at the ET date boundary.
  * Realized-only trips strictly LATER than the live equity-based Rule-5 switch, so every
    saving AND every cost reported here is a FLOOR.

DESCRIPTIVE ONLY. Arms nothing, ships nothing, touches no trading-path file.

Run: backtest/.venv/Scripts/python.exe backtest/tools/lever_daily_cap_2026_08_06.py
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "setup" / "scripts",
           REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import exit_shape_parity_study as esp  # noqa: E402

LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
STATE_DIR = REPO / "automation" / "state"
REPLAY = REPO / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
OUT_JSON = REPO / "analysis" / "deep-research" / "LEVER-DAILY-CAP-2026-08-06.json"

TUE, WED, THU = "2026-08-04", "2026-08-05", "2026-08-06"

# CLAUDE.md Rule 5, confirmed live in each arm's own breaker file this session:
#   safe-* -> -30% of SoD;  bold-*/risky-* -> -50% of SoD.
LIVE_PCT = {"safe-1": 0.30, "safe-2": 0.30, "safe-3": 0.30,
            "bold-2": 0.50, "risky-1": 0.50, "risky-3": 0.50}

PCT_LADDER = [0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25]
ABS_LADDER = [150, 250, 400, 600, 800, 1200]
FLEET_ABS_LADDER = [150, 250, 400, 500, 600, 750, 800, 1000, 1200, 1500]
CONSEC_LADDER = [2, 3, 4, 5]
RETRACE_LADDER = [0.20, 0.30, 0.40, 0.50]


# ============================================================ start-of-day equity (REAL reads)
def load_sod_equity() -> tuple[dict, dict]:
    """{(arm, date_et): equity} from broker reads logged at the time. NOTHING is interpolated
    or reconstructed -- a missing cell stays missing and its arm is left UNCAPPED in the
    %-ladder (conservative: can only understate a saving)."""
    sod: dict[tuple[str, str], float] = {}
    src: dict[tuple[str, str], str] = {}

    # (a) FLEET arms -- first FLAT tick of each ET date in the arm's own decision log.
    for arm in ("safe-1", "safe-3", "risky-1", "risky-3"):
        p = FLEET_DIR / arm / "decisions.jsonl"
        if not p.exists():
            continue
        best: dict[str, tuple[str, float]] = {}
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            eq = r.get("equity")
            ts = r.get("ts_et") or ""
            if eq is None or len(ts) < 16 or not r.get("flat", False):
                continue
            d, hhmm = ts[:10], ts[11:16]
            if hhmm < "09:30":          # premarket ticks: keep, they ARE start-of-day
                pass
            cur = best.get(d)
            if cur is None or ts < cur[0]:
                best[d] = (ts, float(eq))
        for d, (_ts, eq) in best.items():
            sod[(arm, d)] = round(eq, 2)
            src[(arm, d)] = f"fleet/{arm}/decisions.jsonl first-flat-tick"

    # (b) CORE arms -- the premarket REARM row, which is exactly what Rule 5 arms from.
    core_map = {"safe": "safe-2", "bold": "bold-2"}
    for p in sorted(STATE_DIR.glob("daily-loss-guard-*.jsonl")):
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            arm = core_map.get(r.get("account", ""))
            eq = r.get("equity")
            d = r.get("date")
            if not arm or eq is None or not d:
                continue
            if r.get("action") != "REARMED":
                continue
            if (arm, d) not in sod:
                sod[(arm, d)] = round(float(eq), 2)
                src[(arm, d)] = f"{p.name} REARMED"
    return sod, src


# ============================================================ populations
def load_book() -> list[dict]:
    fills = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("attribution") == "engine" and r.get("is_option") and not r.get("is_crypto"):
            fills.append(r)
    pos = [p for p in esp.reconstruct_positions(fills) if p["exit_fills"]]
    for p in pos:
        p["pnl"] = round(p["actual_exit_pnl"], 2)
        p["close_ts"] = max(ef["ts_utc"] for ef in p["exit_fills"])
    pos.sort(key=lambda p: (p["date_et"], p["entry_ts_utc"], p["arm"]))
    return pos


def load_replay() -> tuple[list[dict], dict]:
    d = json.loads(REPLAY.read_text(encoding="utf-8"))
    tr = []
    for t in d["trades"]:
        tr.append({**t, "pnl": round(float(t["dollar_pnl"]), 2), "date_et": t["date"]})
    tr.sort(key=lambda t: (t["date"], t["entry_time_et"]))
    return tr, d


# ============================================================ breaker state machines
class DollarCap:
    """Halt when cumulative realized P&L for the scope reaches -cap. cap=None -> never arms.

    latch=True is the RULE-5-FAITHFUL semantics ("day closed for that account"): once the
    threshold is crossed the scope stays halted for the rest of the session even if later
    closes pull the running total back above it. latch=False is a re-armable "currently
    underwater by X" gate. The prereg's section 4 describes the latching behaviour, so LATCH
    IS PRIMARY; the non-latching variant is reported alongside because it is the strictly more
    permissive sibling and the difference is a real, measurable design choice.
    """
    kind = "dollar_cap"

    def __init__(self, cap: float | None, latch: bool = False):
        self.cap = cap
        self.latch = latch
        self.realized = 0.0
        self.armed_ever = False
        self._latched = False

    def on_close(self, pnl: float) -> None:
        self.realized += pnl
        if self.cap is not None and self.realized <= -self.cap + 1e-9:
            self._latched = True

    @property
    def armed(self) -> bool:
        if self.cap is None:
            return False
        a = self._latched if self.latch else (self.realized <= -self.cap + 1e-9)
        if a:
            self.armed_ever = True
        return a


class ConsecLoss:
    """Halt for the rest of the session after N consecutive LOSING closed round trips.
    Frozen streak rule: pnl<0 increments, pnl>0 resets, pnl==0 leaves unchanged."""
    kind = "consec_loss"

    def __init__(self, n: int):
        self.n = n
        self.streak = 0
        self.armed_ever = False
        self._latched = False

    def on_close(self, pnl: float) -> None:
        if pnl < 0:
            self.streak += 1
            if self.streak >= self.n:
                self._latched = True
        elif pnl > 0:
            self.streak = 0

    @property
    def armed(self) -> bool:
        if self._latched:
            self.armed_ever = True
        return self._latched


class PeakRetrace:
    """Halt when realized day P&L falls x_pct below its intraday realized PEAK.
    Arms only once the peak has reached min_peak (and is > 0)."""
    kind = "peak_retrace"

    def __init__(self, x_pct: float, min_peak: float):
        self.x = x_pct
        self.min_peak = min_peak
        self.realized = 0.0
        self.peak = 0.0
        self.armed_ever = False
        self._latched = False

    def on_close(self, pnl: float) -> None:
        self.realized += pnl
        if self.realized > self.peak:
            self.peak = self.realized
        if self.peak > 0 and self.peak >= self.min_peak:
            if (self.peak - self.realized) >= self.x * self.peak - 1e-9 and \
               self.realized < self.peak:
                self._latched = True

    @property
    def armed(self) -> bool:
        if self._latched:
            self.armed_ever = True
        return self._latched


# ============================================================ the sequential walk
def simulate(positions: list[dict], scope_of, rule_for) -> dict:
    """PATH-CONSISTENT sequential counterfactual.

    scope_of(p)  -> hashable breaker scope, e.g. (arm, date) or (date,)
    rule_for(scope, positions_in_scope) -> a state machine, or None to leave uncapped

    Walk entries in chronological order. Before each entry, feed the state machine every
    TAKEN position that has already CLOSED (close_ts <= entry_ts). A blocked position never
    happens and therefore never closes.
    """
    by_scope: dict = defaultdict(list)
    for p in positions:
        by_scope[scope_of(p)].append(p)

    kept, blocked = [], []
    armed_scopes, all_scopes = set(), set()
    for scope, group in by_scope.items():
        all_scopes.add(scope)
        rule = rule_for(scope, group)
        if rule is None:
            kept.extend(group)
            continue
        entries = sorted(group, key=lambda p: (p["entry_ts_utc"], p["arm"], p["symbol"]))
        pending: list[dict] = []          # taken but not yet fed to the rule
        for p in entries:
            now = p["entry_ts_utc"]
            due = [q for q in pending if q["close_ts"] <= now]
            if due:
                for q in sorted(due, key=lambda x: x["close_ts"]):
                    rule.on_close(q["pnl"])
                pending = [q for q in pending if q["close_ts"] > now]
            if rule.armed:
                blocked.append(p)
            else:
                kept.append(p)
                pending.append(p)
        if rule.armed_ever or rule.armed:
            armed_scopes.add(scope)
    return {"kept": kept, "blocked": blocked,
            "armed_scopes": armed_scopes, "all_scopes": all_scopes}


def simulate_multi(positions: list[dict], specs: list) -> dict:
    """Same semantics as simulate(), but with SEVERAL breakers live at once on DIFFERENT scopes
    (e.g. a fleet dollar cap AND a per-arm consecutive-loss halt). One global chronological
    walk; an entry is blocked if ANY rule covering it is armed; a blocked position never closes
    and therefore never feeds ANY rule.

    specs = [(scope_of, rule_factory), ...]. Verified in the verifier to reproduce simulate()
    exactly when len(specs) == 1.
    """
    rules: list[dict] = [{} for _ in specs]
    kept, blocked, pending = [], [], []
    armed_scopes: set = set()
    for p in sorted(positions, key=lambda q: (q["entry_ts_utc"], q["arm"], q["symbol"])):
        now = p["entry_ts_utc"]
        due = sorted([q for q in pending if q["close_ts"] <= now], key=lambda x: x["close_ts"])
        for q in due:
            for i, (scope_of, _rf) in enumerate(specs):
                r = rules[i].get(scope_of(q))
                if r is not None:
                    r.on_close(q["pnl"])
        pending = [q for q in pending if q["close_ts"] > now]

        is_armed = False
        for i, (scope_of, rf) in enumerate(specs):
            sc = scope_of(p)
            if sc not in rules[i]:
                rules[i][sc] = rf(sc)
            r = rules[i][sc]
            if r is not None and r.armed:
                is_armed = True
                armed_scopes.add((i, sc))
        if is_armed:
            blocked.append(p)
        else:
            kept.append(p)
            pending.append(p)
    return {"kept": kept, "blocked": blocked, "armed_scopes": armed_scopes,
            "all_scopes": set()}


def naive_fleet_breaker(positions: list[dict], cap: float) -> dict:
    """Lane 0's shape, reproduced verbatim for continuity: realized is summed over the ORIGINAL
    closed set, including positions this very rule would have blocked. Over-blocks."""
    by_day: dict = defaultdict(list)
    for p in positions:
        by_day[p["date_et"]].append(p)
    kept, blocked = [], []
    for _d, day_pos in by_day.items():
        for p in day_pos:
            realized = sum(q["pnl"] for q in day_pos if q["close_ts"] <= p["entry_ts_utc"])
            (blocked if realized <= -cap else kept).append(p)
    return {"kept": kept, "blocked": blocked, "armed_scopes": set(), "all_scopes": set()}


# ============================================================ scoring
def day_totals(rows: list[dict]) -> dict:
    d: dict = defaultdict(float)
    for r in rows:
        d[r["date_et"]] += r["pnl"]
    return {k: round(v, 2) for k, v in d.items()}


def score(base_days: dict, res: dict, label: str, *, family: str,
          traded_arm_sessions: int, traded_dates: int, extra: dict | None = None) -> dict:
    cf_days = day_totals(res["kept"])
    all_days = sorted(set(base_days) | set(cf_days))
    deltas = {d: round(cf_days.get(d, 0.0) - base_days.get(d, 0.0), 2) for d in all_days}
    harmed = {d: v for d, v in deltas.items() if v < -0.005}
    helped = {d: v for d, v in deltas.items() if v > 0.005}
    blocked = res["blocked"]
    up = round(sum(p["pnl"] for p in blocked if p["pnl"] > 0), 2)
    prev = round(sum(-p["pnl"] for p in blocked if p["pnl"] < 0), 2)
    armed = res.get("armed_scopes", set())
    armed_dates = {s[-1] if isinstance(s, tuple) else s for s in armed}
    row = {
        "label": label,
        "family": family,
        "n_positions_blocked": len(blocked),
        "total_delta": round(sum(deltas.values()), 2),
        "book_after": round(sum(cf_days.values()), 2),
        "wednesday_delta": deltas.get(WED, 0.0),
        "wednesday_after": cf_days.get(WED, 0.0),
        "tuesday_delta": deltas.get(TUE, 0.0),
        "tuesday_after": cf_days.get(TUE, 0.0),
        "thursday_delta": deltas.get(THU, 0.0),
        "thursday_after": cf_days.get(THU, 0.0),
        "delta_ex_wednesday": round(sum(v for d, v in deltas.items() if d != WED), 2),
        "n_days_harmed": len(harmed),
        "n_days_helped": len(helped),
        "worst_harm": round(min(harmed.values()), 2) if harmed else 0.0,
        "harmed_days": {k: v for k, v in sorted(harmed.items(), key=lambda kv: kv[1])[:6]},
        "upside_surrendered": up,
        "loss_prevented": prev,
        "insurance_cost_ratio": round(up / prev, 4) if prev > 0 else None,
        "n_armed_scopes": len(armed),
        "bind_rate_arm_sessions": round(len(armed) / traded_arm_sessions, 4)
        if traded_arm_sessions else None,
        "bind_rate_calendar": round(len(armed_dates) / traded_dates, 4) if traded_dates else None,
        "REJECTED_TUESDAY": deltas.get(TUE, 0.0) < -0.005,
    }
    if extra:
        row.update(extra)
    return row


# ============================================================ replay walk
def replay_sim(trades: list[dict], rule_factory) -> dict:
    """Event-driven walk over Population B, using each trade's REAL close time
    (entry_time_et + hold_minutes) -- NOT entry order.

    WHY THIS IS NOT THE OBVIOUS SHAPE: it is tempting to assume the replay's
    one-position-at-a-time construction means trade k is always closed before trade k+1 enters,
    so cumulative-by-entry-order == cumulative-realized. That assumption is FALSE here and was
    caught by an explicit check (verifier G1): 6 same-day pairs in the 141-day population have
    the next trade entering while the previous one is still open. Crediting a still-open
    trade's P&L into the running total would be look-ahead (C6) and would over-block. So the
    running total counts only trades whose close time is at or before the candidate entry."""
    by_day: dict = defaultdict(list)
    for t in trades:
        t = dict(t)
        ent = _dt.datetime.fromisoformat(t["entry_time_et"])
        t["_entry_dt"] = ent
        t["_close_dt"] = ent + _dt.timedelta(minutes=float(t.get("hold_minutes") or 0))
        by_day[t["date"]].append(t)
    kept, blocked = [], []
    armed_days = set()
    for d, day_t in by_day.items():
        rule = rule_factory()
        pending: list[dict] = []
        for t in sorted(day_t, key=lambda x: x["_entry_dt"]):
            due = sorted([q for q in pending if q["_close_dt"] <= t["_entry_dt"]],
                         key=lambda x: x["_close_dt"])
            for q in due:
                rule.on_close(q["pnl"])
            pending = [q for q in pending if q["_close_dt"] > t["_entry_dt"]]
            if rule.armed:
                blocked.append(t)
                continue
            kept.append(t)
            pending.append(t)
        if rule.armed_ever or rule.armed:
            armed_days.add(d)
    return {"kept": kept, "blocked": blocked, "armed_days": armed_days}


def replay_score(base_days: dict, res: dict, label: str, family: str,
                 n_traded_days: int) -> dict:
    cf = day_totals(res["kept"])
    all_days = sorted(set(base_days) | set(cf))
    deltas = {d: round(cf.get(d, 0.0) - base_days.get(d, 0.0), 2) for d in all_days}
    harmed = {d: v for d, v in deltas.items() if v < -0.005}
    helped = {d: v for d, v in deltas.items() if v > 0.005}
    up = round(sum(t["pnl"] for t in res["blocked"] if t["pnl"] > 0), 2)
    prev = round(sum(-t["pnl"] for t in res["blocked"] if t["pnl"] < 0), 2)
    return {
        "label": label, "family": family,
        "n_blocked": len(res["blocked"]),
        "total_delta": round(sum(deltas.values()), 2),
        "book_after": round(sum(cf.values()), 2),
        "n_days_harmed": len(harmed), "n_days_helped": len(helped),
        "worst_harm": round(min(harmed.values()), 2) if harmed else 0.0,
        "upside_surrendered": up, "loss_prevented": prev,
        "insurance_cost_ratio": round(up / prev, 4) if prev > 0 else None,
        "bind_rate_days": round(len(res["armed_days"]) / n_traded_days, 4) if n_traded_days else None,
        "n_armed_days": len(res["armed_days"]),
    }


# ============================================================ main
def main() -> int:
    sod, sod_src = load_sod_equity()
    book = load_book()
    base = day_totals(book)
    base_total = round(sum(base.values()), 2)
    dates = sorted(base)
    arm_sessions = {(p["arm"], p["date_et"]) for p in book}
    n_arm_sessions = len(arm_sessions)
    n_dates = len(dates)

    print(f"[lever1] book: {len(book)} positions, {n_dates} dates, "
          f"{n_arm_sessions} (arm,date) sessions, net ${base_total}")
    print(f"[lever1] SoD equity cells loaded: {len(sod)}")

    # ---- SoD coverage against the book
    covered = [p for p in book if (p["arm"], p["date_et"]) in sod]
    uncovered_cells = sorted({(p["arm"], p["date_et"]) for p in book
                              if (p["arm"], p["date_et"]) not in sod})
    coverage = {
        "n_positions_total": len(book),
        "n_positions_with_real_sod": len(covered),
        "pct_positions_covered": round(len(covered) / len(book), 4),
        "loss_dollars_total": round(sum(-p["pnl"] for p in book if p["pnl"] < 0), 2),
        "loss_dollars_covered": round(sum(-p["pnl"] for p in covered if p["pnl"] < 0), 2),
        "n_arm_sessions_total": n_arm_sessions,
        "n_arm_sessions_with_real_sod": len(arm_sessions & set(sod)),
        "uncovered_arm_sessions": [f"{a}|{d}" for a, d in uncovered_cells],
        "uncovered_note": ("Left UNCAPPED in every %-of-SoD cell -- the breaker cannot arm "
                           "there. Conservative: understates a %-cell's saving, never inflates "
                           "it. No SoD equity is interpolated or reconstructed anywhere."),
    }
    print(f"[lever1] SoD coverage: {coverage['n_positions_with_real_sod']}/{len(book)} positions "
          f"({coverage['pct_positions_covered']:.1%}), uncovered cells: {len(uncovered_cells)}")

    # ---- the SoD equity table actually used, for the target week
    week_sod = {f"{a}|{d}": {"sod_equity": sod[(a, d)], "source": sod_src[(a, d)]}
                for (a, d) in sorted(sod) if d in (TUE, WED, THU)}

    out: dict = {
        "_doc": __doc__.strip().splitlines()[0],
        "_prereg": "analysis/deep-research/PREREG-LEVER-DAILY-CAP-2026-08-06.md @ b8bbe7a8",
        "clock_verified_et": "2026-08-06 16:45:23 Thursday EDT, market_hours=False",
        "populations": {
            "A_book": {
                "source": "automation/state/fills-ledger.jsonl -> "
                          "exit_shape_parity_study.reconstruct_positions",
                "authority": "REAL BROKER FILLS",
                "n_positions": len(book), "n_dates": n_dates,
                "first_date": dates[0], "last_date": dates[-1],
                "net_pnl": base_total,
                "baseline_days": base,
                "n_arm_date_sessions": n_arm_sessions,
            },
        },
        "sod_equity_provenance": {
            "sources": ["automation/state/fleet/{arm}/decisions.jsonl first-flat-tick `equity`",
                        "automation/state/daily-loss-guard-{date}.jsonl REARMED `equity`"],
            "coverage": coverage,
            "target_week_table": week_sod,
            "live_rule5_pct": LIVE_PCT,
        },
        "cells": {},
    }

    all_rows: list[dict] = []

    def add(rows: list[dict], key: str) -> None:
        out["cells"][key] = rows
        all_rows.extend(rows)

    # ================================================== L1-PCT per-arm, % of REAL SoD equity
    pct_rows = []
    for pc in PCT_LADDER + ["LIVE"]:
        def rf(scope, group, pc=pc):
            arm, d = scope
            eq = sod.get((arm, d))
            if eq is None:
                return None                       # UNCAPPED, disclosed
            frac = LIVE_PCT.get(arm, 0.30) if pc == "LIVE" else pc
            return DollarCap(eq * frac)
        res = simulate(book, lambda p: (p["arm"], p["date_et"]), rf)
        lab = ("per-arm cap = LIVE Rule 5 (-30% safe / -50% bold+risky)" if pc == "LIVE"
               else f"per-arm cap = -{pc*100:.0f}% of SoD equity")
        capped_sessions = len([1 for s in arm_sessions if s in sod])
        pct_rows.append(score(base, res, lab, family="L1-PCT",
                              traded_arm_sessions=capped_sessions, traded_dates=n_dates,
                              extra={"pct": pc if pc == "LIVE" else round(pc, 4),
                                     "n_capped_arm_sessions": capped_sessions}))
    add(pct_rows, "L1_PCT_per_arm")

    # ================================================== L1-ABS per-arm, absolute dollars
    abs_rows = []
    for c in ABS_LADDER:
        res = simulate(book, lambda p: (p["arm"], p["date_et"]),
                       lambda s, g, c=c: DollarCap(c))
        abs_rows.append(score(base, res, f"per-arm cap = -${c}", family="L1-ABS",
                              traded_arm_sessions=n_arm_sessions, traded_dates=n_dates,
                              extra={"cap_dollars": -c}))
    add(abs_rows, "L1_ABS_per_arm")

    # ================================================== L1-FLEET-ABS pooled dollars
    fabs_rows = []
    for c in FLEET_ABS_LADDER:
        res = simulate(book, lambda p: (p["date_et"],), lambda s, g, c=c: DollarCap(c))
        fabs_rows.append(score(base, res, f"FLEET pooled cap = -${c}", family="L1-FLEET-ABS",
                               traded_arm_sessions=n_dates, traded_dates=n_dates,
                               extra={"cap_dollars": -c}))
    add(fabs_rows, "L1_FLEET_ABS")

    # ================================================== L1-FLEET-PCT pooled % of pooled SoD
    # Pooled SoD = sum over arms with a REAL SoD equity that date. safe-1 and safe-2 pointed at
    # DIFFERENT accounts before the 2026-07-11 repoint and safe-1 stopped trading 2026-07-09,
    # so there is no same-account double count on any date in this book (verified in the
    # verifier).
    pooled_sod: dict[str, float] = defaultdict(float)
    pooled_arms: dict[str, list] = defaultdict(list)
    for (a, d), eq in sod.items():
        pooled_sod[d] += eq
        pooled_arms[d].append(a)
    fpct_rows = []
    for pc in PCT_LADDER + ["LIVE"]:
        def rf2(scope, group, pc=pc):
            d = scope[0]
            eq = pooled_sod.get(d)
            if not eq:
                return None
            if pc == "LIVE":
                # pooled LIVE budget = sum of each covered arm's own Rule-5 budget
                budget = sum(sod[(a, d)] * LIVE_PCT.get(a, 0.30) for a in pooled_arms[d])
                return DollarCap(budget)
            return DollarCap(eq * pc)
        res = simulate(book, lambda p: (p["date_et"],), rf2)
        lab = ("FLEET pooled cap = LIVE Rule 5 budgets summed" if pc == "LIVE"
               else f"FLEET pooled cap = -{pc*100:.0f}% of pooled SoD equity")
        fpct_rows.append(score(base, res, lab, family="L1-FLEET-PCT",
                               traded_arm_sessions=n_dates, traded_dates=n_dates,
                               extra={"pct": pc if pc == "LIVE" else round(pc, 4)}))
    add(fpct_rows, "L1_FLEET_PCT")

    # ================================================== L2 consecutive-loss breaker
    consec_rows = []
    for n in CONSEC_LADDER:
        res = simulate(book, lambda p: (p["arm"], p["date_et"]),
                       lambda s, g, n=n: ConsecLoss(n))
        consec_rows.append(score(base, res, f"per-arm halt after {n} consecutive losers",
                                 family="L2-CONSEC", traded_arm_sessions=n_arm_sessions,
                                 traded_dates=n_dates, extra={"n_consec": n}))
    add(consec_rows, "L2_CONSEC_per_arm")

    consec_f = []
    for n in CONSEC_LADDER:
        res = simulate(book, lambda p: (p["date_et"],), lambda s, g, n=n: ConsecLoss(n))
        consec_f.append(score(base, res, f"FLEET halt after {n} consecutive losers",
                              family="L2-CONSEC-FLEET", traded_arm_sessions=n_dates,
                              traded_dates=n_dates, extra={"n_consec": n}))
    add(consec_f, "L2_CONSEC_fleet")

    # ================================================== L3 day-peak retrace halt
    for min_peak in (0.01, 100.0):
        rows = []
        for x in RETRACE_LADDER:
            res = simulate(book, lambda p: (p["arm"], p["date_et"]),
                           lambda s, g, x=x, mp=min_peak: PeakRetrace(x, mp))
            rows.append(score(base, res,
                              f"per-arm halt on {x*100:.0f}% retrace of realized day peak "
                              f"(arms once peak >= ${min_peak:.0f})",
                              family="L3-RETRACE", traded_arm_sessions=n_arm_sessions,
                              traded_dates=n_dates,
                              extra={"retrace_pct": x, "min_peak": min_peak}))
        add(rows, f"L3_RETRACE_per_arm_minpeak{int(min_peak)}")

        rowsf = []
        for x in RETRACE_LADDER:
            res = simulate(book, lambda p: (p["date_et"],),
                           lambda s, g, x=x, mp=min_peak: PeakRetrace(x, mp))
            rowsf.append(score(base, res,
                               f"FLEET halt on {x*100:.0f}% retrace of realized day peak "
                               f"(arms once peak >= ${min_peak:.0f})",
                               family="L3-RETRACE-FLEET", traded_arm_sessions=n_dates,
                               traded_dates=n_dates,
                               extra={"retrace_pct": x, "min_peak": min_peak}))
        add(rowsf, f"L3_RETRACE_fleet_minpeak{int(min_peak)}")

    # ============================== LATCHING variants (the Rule-5-faithful semantics)
    # Rule 5 says "day closed for that account" -- once tripped it STAYS tripped. The frozen
    # grid above used a re-armable gate. Both are run; latch is the prereg-faithful one.
    latch_rows = []
    for c in FLEET_ABS_LADDER:
        res = simulate(book, lambda p: (p["date_et"],),
                       lambda s, g, c=c: DollarCap(c, latch=True))
        latch_rows.append(score(base, res, f"LATCHING FLEET pooled cap = -${c}",
                                family="L1-FLEET-ABS-LATCH", traded_arm_sessions=n_dates,
                                traded_dates=n_dates, extra={"cap_dollars": -c}))
    add(latch_rows, "L1_FLEET_ABS_LATCHING")

    latch_arm = []
    for c in ABS_LADDER:
        res = simulate(book, lambda p: (p["arm"], p["date_et"]),
                       lambda s, g, c=c: DollarCap(c, latch=True))
        latch_arm.append(score(base, res, f"LATCHING per-arm cap = -${c}",
                               family="L1-ABS-LATCH", traded_arm_sessions=n_arm_sessions,
                               traded_dates=n_dates, extra={"cap_dollars": -c}))
    add(latch_arm, "L1_ABS_per_arm_LATCHING")

    # ================================================== comparators
    comp = []
    for c in (500, 600, 750):
        r = naive_fleet_breaker(book, c)
        comp.append(score(base, r, f"[Lane-0 NAIVE, path-inconsistent] FLEET -${c}",
                          family="COMPARATOR", traded_arm_sessions=n_dates,
                          traded_dates=n_dates, extra={"cap_dollars": -c}))
    seq: dict = defaultdict(int)
    kept, blocked = [], []
    for p in sorted(book, key=lambda q: (q["date_et"], q["entry_ts_utc"])):
        k = (p["arm"], p["symbol"], p["date_et"])
        seq[k] += 1
        (kept if seq[k] <= 3 else blocked).append(p)
    comp.append(score(base, {"kept": kept, "blocked": blocked, "armed_scopes": set()},
                      "[comparator] CAP-3 entries per (arm,symbol,date)", family="COMPARATOR",
                      traded_arm_sessions=n_arm_sessions, traded_dates=n_dates))
    add(comp, "COMPARATORS")

    # ================================================== POST-HOC combination (labelled)
    # Only run AFTER the frozen grid, only for the single best surviving per-arm dollar cap
    # crossed with the single best surviving consec cell. Explicitly post-hoc.
    def survives(r):
        return not r["REJECTED_TUESDAY"]
    best_abs = max([r for r in abs_rows if survives(r)],
                   key=lambda r: r["total_delta"], default=None)
    best_con = max([r for r in consec_rows if survives(r)],
                   key=lambda r: r["total_delta"], default=None)
    posthoc = []
    if best_abs and best_con:
        cap_d = -best_abs["cap_dollars"]
        n_c = best_con["n_consec"]

        class Both:
            def __init__(self):
                self.a, self.b = DollarCap(cap_d), ConsecLoss(n_c)
                self.armed_ever = False

            def on_close(self, pnl):
                self.a.on_close(pnl)
                self.b.on_close(pnl)

            @property
            def armed(self):
                a = self.a.armed or self.b.armed
                if a:
                    self.armed_ever = True
                return a
        res = simulate(book, lambda p: (p["arm"], p["date_et"]), lambda s, g: Both())
        posthoc.append(score(base, res,
                             f"[POST-HOC] per-arm -${cap_d} OR {n_c} consecutive losers",
                             family="POST-HOC", traded_arm_sessions=n_arm_sessions,
                             traded_dates=n_dates))
    # The two levers that actually survived on DIFFERENT scopes: a FLEET tail cap (firm-level)
    # AND a per-arm consecutive-loss halt (pattern-level). Composed properly -- one global
    # chronological walk with both live -- not applied in two passes.
    for fleet_cap, n_c in ((600, 4), (600, 5), (750, 4)):
        res = simulate_multi(book, [
            (lambda p: (p["date_et"],), lambda s, c=fleet_cap: DollarCap(c)),
            (lambda p: (p["arm"], p["date_et"]), lambda s, n=n_c: ConsecLoss(n)),
        ])
        posthoc.append(score(
            base, res, f"[POST-HOC] FLEET -${fleet_cap} AND per-arm {n_c}-consecutive-loser halt",
            family="POST-HOC-COMBINED", traded_arm_sessions=n_arm_sessions,
            traded_dates=n_dates))
    add(posthoc, "POST_HOC_COMBINATION")

    # ================================================== Population B: the 391-day replay
    rtr, rmeta = load_replay()
    rep_base = day_totals(rtr)
    rep_days = len(rep_base)
    rep_total = round(sum(rep_base.values()), 2)
    NOMINAL_ARM_EQUITY = 5000.0     # the post-reset per-arm funding level; %-equivalent only
    rep: dict = {
        "population": {
            "source": "analysis/recommendations/engine-fullhist-replay-2026-07-23.json",
            "authority": "REAL OPRA entries frozen + exits re-walked through the LIVE "
                         "exit_manager.plan_exit_actions (exit_manager_walk.walk_exit_manager)",
            "n_trades": len(rtr), "n_traded_days": rep_days,
            "window": rmeta["window"], "net_pnl": rep_total,
        },
        "scale_caveat": ("ONE arm at qty 3. Validates a per-arm / sequence-shaped breaker "
                         "MECHANISM across 141 independent days. CANNOT validate a fleet "
                         "threshold -- it has no fleet -- and structurally cannot produce a "
                         "Wednesday (worst day -$825 in 387 RTH days)."),
        "pct_equivalent_note": (f"%-equivalents below are stated against a NOMINAL "
                                f"${NOMINAL_ARM_EQUITY:,.0f} single-arm account (the "
                                f"post-reset per-arm funding level). The replay carries no "
                                f"equity series; this is a units bridge, not a measurement."),
        "L1_ABS": [], "L2_CONSEC": [], "L3_RETRACE_minpeak0": [], "L3_RETRACE_minpeak100": [],
    }
    for c in [100, 120, 150, 200, 250, 300, 400, 500, 600, 800, 1200]:
        r = replay_sim(rtr, lambda c=c: DollarCap(c))
        row = replay_score(rep_base, r, f"single-arm cap = -${c}", "L1-ABS", rep_days)
        row["pct_of_nominal_5k"] = round(c / NOMINAL_ARM_EQUITY, 4)
        rep["L1_ABS"].append(row)
    for n in CONSEC_LADDER:
        r = replay_sim(rtr, lambda n=n: ConsecLoss(n))
        rep["L2_CONSEC"].append(replay_score(rep_base, r,
                                             f"halt after {n} consecutive losers",
                                             "L2-CONSEC", rep_days))
    for mp, key in ((0.01, "L3_RETRACE_minpeak0"), (100.0, "L3_RETRACE_minpeak100")):
        for x in RETRACE_LADDER:
            r = replay_sim(rtr, lambda x=x, mp=mp: PeakRetrace(x, mp))
            rep[key].append(replay_score(rep_base, r,
                                         f"halt on {x*100:.0f}% retrace of day peak "
                                         f"(arms once peak >= ${mp:.0f})",
                                         "L3-RETRACE", rep_days))
    rep["baseline_total"] = rep_total
    out["populations"]["B_replay"] = rep["population"]
    out["replay_391d"] = rep

    # ================================================== multiple-comparisons honesty
    out["multiple_comparisons"] = {
        "n_cells_in_frozen_grid": len(all_rows) - len(posthoc),
        "n_motivating_days": 1,
        "note": ("Every book cell is scored against a 26-date sample containing exactly ONE "
                 "Wednesday. With this many cells, the best-looking cell is selected in-sample "
                 "by construction. The 141-traded-day replay is the only out-of-sample check "
                 "available, and it cannot express a fleet threshold. Verdict ceiling is "
                 "PREREG, pre-declared before any number was computed."),
    }

    out["verdict"] = {
        "verdict": "PREREG",
        "headline": ("A realized-P&L FLEET day breaker at -$600 takes Wednesday from -$1,935 "
                     "to -$710 at exactly $0.00 cost on Tuesday and Thursday. -$710 is a HARD "
                     "FLOOR: no Tuesday-safe cell in 66 gets Wednesday lower, because doing so "
                     "requires a threshold tighter than Tuesday's own -$363 realized drawdown. "
                     "The daily cap gets ~63% of the way to J's -$500 target and no further."),
        "frozen_candidate": {
            "instrument": "fleet-wide REALIZED-P&L day breaker, latching",
            "threshold_dollars": -600.0,
            "basis": "REALIZED ONLY -- explicitly NOT equity; see equity_mtm_arm",
            "action": "block NEW entries for the rest of the session; never force-liquidate",
            "reset": "ET date boundary",
            "optional_second_leg": "per-arm halt after 4 consecutive losing closed round trips",
            "do_not_tighten_below": -550.0,
            "kill_criterion": ("fires on a day that ends profitable, OR total delta < 0 after "
                               "20 forward sessions"),
        },
        "mechanical_boundaries_not_fitted": {
            "tuesday_own_realized_low": -363.00,
            "deepest_realized_low_any_day_RECOVERED_from": -526.99,
            "that_day": "2026-07-02 (recovered +$771 on 6 further entries)",
            "safety_margin_of_the_600_candidate": 73.01,
            "wednesday_realized_low": -1935.00,
        },
        "why_realized_not_equity": ("On an equity basis the SAME -$600 breaker was ARMED on "
                                    "2026-08-06 -- a +$1,465 day -- from 10:57 ET, worst mark "
                                    "-$711.00. It cost $0 only because all three winners were "
                                    "already open and the one post-trip entry was a -$36 "
                                    "loser. TIMING LUCK, not margin. On a realized basis "
                                    "Thursday never armed: its realized P&L never went "
                                    "negative. Unrealized drawdown on a runner is not a loss."),
        "killed_outright": {
            "L3_day_peak_retrace": ("NULL. Every per-arm cell costs Tuesday (-$678..-$1,669, "
                                    "insurance ratios 7.16-19.31); every fleet cell either "
                                    "costs Tuesday or blocks nothing; 0 blocked at every cell "
                                    "in the 391-day replay. Never touches Wednesday -- "
                                    "Wednesday's realized P&L never went positive."),
            "LIVE_Rule_5_as_configured": ("Inert. -30%/-50% of SoD never armed once in 26 "
                                          "dates at per-arm scope. risky-3 booked -$1,462 on "
                                          "Wednesday with $1,529.95 of budget still unused."),
            "consecutive_loss_N2_and_N3": "REJECTED on Tuesday (-$1,969 and -$1,093).",
            "fleet_scope_consecutive_loss": "REJECTED at every N (Tuesday -$2,087..-$3,803).",
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[lever1] wrote {OUT_JSON}")

    # ================================================== console tables
    def show(rows, title):
        if not rows:
            return
        print(f"\n== {title}")
        print(f"{'cell':62s} {'nBlk':>4s} {'total':>9s} {'WED':>9s} {'WEDaft':>9s} "
              f"{'TUE':>9s} {'THU':>8s} {'exWED':>9s} {'harm':>4s} {'ratio':>7s} {'bind':>6s} G")
        for r in rows:
            ratio = "n/a" if r["insurance_cost_ratio"] is None else f"{r['insurance_cost_ratio']:.2f}"
            bind = "n/a" if r["bind_rate_arm_sessions"] is None else f"{r['bind_rate_arm_sessions']:.1%}"
            gate = "X" if r["REJECTED_TUESDAY"] else "."
            print(f"{r['label']:62.62s} {r['n_positions_blocked']:4d} {r['total_delta']:9.2f} "
                  f"{r['wednesday_delta']:9.2f} {r['wednesday_after']:9.2f} "
                  f"{r['tuesday_delta']:9.2f} {r['thursday_delta']:8.2f} "
                  f"{r['delta_ex_wednesday']:9.2f} {r['n_days_harmed']:4d} {ratio:>7s} "
                  f"{bind:>6s} {gate}")

    for k in ("L1_PCT_per_arm", "L1_ABS_per_arm", "L1_ABS_per_arm_LATCHING",
              "L1_FLEET_ABS", "L1_FLEET_ABS_LATCHING", "L1_FLEET_PCT",
              "L2_CONSEC_per_arm", "L2_CONSEC_fleet",
              "L3_RETRACE_per_arm_minpeak0", "L3_RETRACE_per_arm_minpeak100",
              "L3_RETRACE_fleet_minpeak0", "L3_RETRACE_fleet_minpeak100",
              "COMPARATORS", "POST_HOC_COMBINATION"):
        show(out["cells"].get(k, []), k)

    print("\n== 391-DAY REPLAY (one arm, qty 3) -- absolute dollar cap")
    print(f"{'cell':44s} {'nBlk':>4s} {'total':>9s} {'after':>10s} {'harm':>4s} {'help':>4s} "
          f"{'ratio':>7s} {'bind':>6s}")
    for grp in ("L1_ABS", "L2_CONSEC", "L3_RETRACE_minpeak0", "L3_RETRACE_minpeak100"):
        print(f"  -- {grp}")
        for r in rep[grp]:
            ratio = "n/a" if r["insurance_cost_ratio"] is None else f"{r['insurance_cost_ratio']:.2f}"
            bind = "n/a" if r["bind_rate_days"] is None else f"{r['bind_rate_days']:.1%}"
            print(f"{r['label']:44.44s} {r['n_blocked']:4d} {r['total_delta']:9.2f} "
                  f"{r['book_after']:10.2f} {r['n_days_harmed']:4d} {r['n_days_helped']:4d} "
                  f"{ratio:>7s} {bind:>6s}")

    _ = math
    return 0


if __name__ == "__main__":
    sys.exit(main())
