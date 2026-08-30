"""gamma_glass.py -- the TRADING half of the single pane of glass.

WHY (J, 2026-08-30): "make my dashboard like single pane of glass ai trading command
center". Measured on the page before this existed: the desk rendered 3 of 18 payload
sections and dropped all 15 others -- every one of them the trading half. The live DOM
had `hasEquity:false, hasPosition:false`. A trading command center that never shows a
position, an equity, or a P&L is a name, not an instrument.

This is the counterpart to gamma_lanes.py (standing work) and gamma_autonomy.py (is the
loop alive). It answers the questions a trader actually asks on sight:

    am I in something right now?     -> position
    what is the book worth?          -> equity, per arm and total
    did today make money?            -> pnl.today / week / month, per arm
    what does the engine think?      -> bias, last verdict, and WHY it held
    which arms are actually running?  -> arms roster with real fill counts

EVERY NUMBER IS SOURCED OR ABSENT. There is no default, no placeholder, no "0.0" standing
in for a file that failed to load: a missing input yields None and the renderer says which
file it wanted. A dashboard that invents a P&L is worse than one that shows nothing,
because the invented one gets believed.

READ-ONLY. Opens no position, writes no state, decides nothing.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "automation" / "state"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from et_clock import ET_TZ as ET  # noqa: E402

# The arms whose money is real enough to show. Sourced from the fleet registry at import
# rather than hardcoded, so retiring an arm cannot leave a ghost row on the glass.
FLEET_FILE = STATE / "fleet" / "accounts.json"
EQUITY_FILE = STATE / "book-equity-snapshot.json"
CALENDAR_FILE = ROOT / "analysis" / "journal" / "calendar-data.json"
BIAS_FILE = STATE / "today-bias.json"
FILLS_FILE = STATE / "fills-ledger.jsonl"
POSITION_FILE = STATE / "current-position.json"
BEACON_FILE = STATE / "sight-beacon.json"          # the LIVE tape (age_s 0 when up)
CORE_DEC_FILE = STATE / "core-decisions.jsonl"     # the engine's per-tick verdict
ENGINE_HEALTH_FILE = STATE / "engine-health.json"

# calendar-data.json carries a precomputed BOOK view alongside the per-arm ones.
# Summing the arms AND including BOOK would double the whole book's P&L, so BOOK is
# excluded from every per-arm loop and used only where the aggregate is wanted.
BOOK_VIEW = "BOOK"

# A position file this old is not "flat", it is ABANDONED -- the engine stopped writing.
# Treating a stale file as truth is how a dashboard reports flat while a position is open.
POSITION_STALE_H = 24.0

# Statuses that mean "not in a trade". Anything else non-empty is a POSITION.
FLAT_WORDS = {"flat", "closed", "none", "no_position", "nopos", "out"}


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _age_h(path: Path):
    try:
        return (dt.datetime.now().timestamp() - path.stat().st_mtime) / 3600
    except OSError:
        return None


def _src(path: Path) -> dict:
    """Provenance travels with every group, so the page can name its own inputs."""
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    a = _age_h(path)
    return {"path": rel, "age_h": round(a, 2) if a is not None else None,
            "exists": path.exists()}


# --- equity -----------------------------------------------------------------------------

def group_equity() -> dict:
    d = _read(EQUITY_FILE)
    if not isinstance(d, dict):
        return {"ok": False, "source": _src(EQUITY_FILE), "arms": [], "total": None}
    arms, total, ts = [], 0.0, None
    for arm, row in sorted(d.items()):
        if not isinstance(row, dict) or not isinstance(row.get("equity"), (int, float)):
            continue
        arms.append({"arm": arm, "equity": round(float(row["equity"]), 2)})
        total += float(row["equity"])
        ts = ts or row.get("ts_et")
    return {"ok": bool(arms), "arms": arms,
            "total": round(total, 2) if arms else None,
            "as_of": ts, "source": _src(EQUITY_FILE)}


# --- P&L --------------------------------------------------------------------------------

def _calendar_views() -> dict:
    d = _read(CALENDAR_FILE)
    if isinstance(d, dict) and isinstance(d.get("views"), dict):
        return d["views"]
    return {}


def _day_net(row) -> float | None:
    """NET P&L for one calendar day row, after fees.

    Reads `pnl_net` -- the raw file's key. (The payload's compressed copy renames it to
    `n`; coding against that rename made every number here 0.0 until it was run.) NET
    rather than gross deliberately: showing gross on a glanceable surface flatters every
    figure by exactly the fee drag this project spent months proving matters.
    """
    if not isinstance(row, dict):
        return None
    v = row.get("pnl_net")
    return float(v) if isinstance(v, (int, float)) else None


def group_pnl() -> dict:
    """Per-arm daily NET P&L, plus the aggregate series the sparkline draws."""
    views = _calendar_views()
    if not views:
        return {"ok": False, "source": _src(CALENDAR_FILE), "arms": [], "series": []}

    today = dt.datetime.now(ET).strftime("%Y-%m-%d")
    per_arm = {k: v for k, v in views.items() if k != BOOK_VIEW}
    all_days = sorted({d for v in per_arm.values() for d in (v.get("days") or {})})
    series, cum = [], 0.0
    for day in all_days:
        net = 0.0
        for v in per_arm.values():
            n = _day_net((v.get("days") or {}).get(day))
            if n is not None:
                net += n
        cum += net
        series.append({"d": day, "n": round(net, 2), "cum": round(cum, 2)})

    def _sum(days_back: int) -> float:
        cutoff = (dt.datetime.now(ET) - dt.timedelta(days=days_back)).strftime("%Y-%m-%d")
        return round(sum(r["n"] for r in series if r["d"] > cutoff), 2)

    arms = []
    for arm in sorted(per_arm):
        days = (per_arm[arm].get("days") or {})
        vals = [n for n in (_day_net(r) for r in days.values()) if n is not None]
        t = _day_net(days.get(today))
        arms.append({
            "arm": arm,
            "today": round(t, 2) if t is not None else None,
            "net": round(sum(vals), 2) if vals else None,
            "days_traded": len(vals),
            "wins": sum(1 for v in vals if v > 0),
            "best": round(max(vals), 2) if vals else None,
            "worst": round(min(vals), 2) if vals else None,
        })

    todays = [r for r in series if r["d"] == today]
    return {
        "ok": True,
        "today": todays[0]["n"] if todays else None,
        "traded_today": bool(todays),
        "week": _sum(7), "month": _sum(30),
        "net_all": round(cum, 2),
        "days": len(series),
        "series": series[-60:],          # the sparkline window
        "arms": arms,
        "last_session": series[-1]["d"] if series else None,
        "source": _src(CALENDAR_FILE),
    }


# --- position ---------------------------------------------------------------------------

def _today_fills() -> list:
    """Only today's rows. The ledger is ~0.5MB; a reverse scan keeps this a tail read."""
    today = dt.datetime.now(ET).strftime("%Y-%m-%d")
    out = []
    for line in _tail_lines(FILLS_FILE, 400):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("date_et", "")[:10] == today:
            out.append(r)
    return out


def group_position() -> dict:
    """Open or flat -- and honest about not knowing.

    Three states, not two. `unknown` exists because the position file goes stale when the
    engine is not running, and a stale file that says flat is indistinguishable from a
    real flat unless the age is checked. Reporting `unknown` on a weekend is correct;
    reporting `flat` from a 2000-hour-old file would be a guess wearing a fact's clothes.
    """
    age = _age_h(POSITION_FILE)
    d = _read(POSITION_FILE)
    fills = _today_fills()
    last = None
    for line in reversed(_tail_lines(FILLS_FILE, 40)):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        last = {"symbol": r.get("symbol"), "arm": r.get("arm"), "side": r.get("side"),
                "qty": r.get("qty"), "price": r.get("price"), "ts_et": r.get("ts_et")}
        break

    if age is None:
        # No file at all. That is not flat -- nobody has told us anything.
        return {"ok": True, "state": "unknown",
                "note": "no position file has ever been written",
                "raw_status": None, "fills_today": len(fills), "last_fill": last,
                "source": _src(POSITION_FILE), "fills_source": _src(FILLS_FILE)}
    if age > POSITION_STALE_H:
        state = "unknown"
        note = "position file is {:.0f}h old -- the engine is not writing it".format(age)
    elif isinstance(d, dict) and str(d.get("status") or "").strip().lower() in FLAT_WORDS:
        # The original test was `if d.get("status")` -- ANY truthy string -- so the
        # literal "flat" or "closed" would have rendered IN A TRADE. Named flat-words
        # rather than an open-word whitelist: the engine writes real statuses like
        # "long_call" that no whitelist would have guessed, and being wrong in the
        # open->flat direction is the dangerous one.
        state = "flat"
        note = None
    elif isinstance(d, dict) and d.get("status"):
        state = "open"
        note = None
    else:
        state = "flat"
        note = None

    return {"ok": True, "state": state, "note": note,
            "raw_status": (d or {}).get("status") if isinstance(d, dict) else None,
            "fills_today": len(fills),
            "last_fill": last,
            "source": _src(POSITION_FILE), "fills_source": _src(FILLS_FILE)}


# --- what the engine thinks -------------------------------------------------------------

def _tail_lines(path: Path, n: int = 30, block: int = 65536) -> list:
    """Last n lines WITHOUT reading the file into memory.

    core-decisions.jsonl is 88 MB and /api/desk is polled every 30 seconds; the
    previous `fh.readlines()[-30:]` pulled all 88 MB into RAM on every poll to keep
    thirty lines. Seek from the end in blocks instead. Found by an adversarial review
    2026-08-30 and confirmed against the file's real size.
    """
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            end = fh.tell()
            buf, chunks = b"", 0
            while end > 0 and buf.count(b"\n") <= n and chunks < 64:
                step = min(block, end)
                end -= step
                fh.seek(end)
                buf = fh.read(step) + buf
                chunks += 1
    except OSError:
        return []
    return [x for x in buf.decode("utf-8", "replace").splitlines() if x.strip()][-n:]


def _beacon_age_s(beacon: dict):
    """How old the tape ACTUALLY is, from wall clock vs the beacon's own timestamp.

    NEVER `beacon["age_s"]`. sight_beacon.py writes that field as a literal constant
    0 on every successful snapshot -- it is baked in at write time and never updated,
    so a beacon that died three hours ago still reports age_s 0. The glass trusted it
    (`fresh = age < 120`) and therefore rendered "live - 0s old" unconditionally,
    beside a SPY price and ribbon that could be arbitrarily stale.

    Caught by an adversarial review pass 2026-08-30 and confirmed by measurement: the
    field said 0 while the file was 47.3 seconds old. This is the single most dangerous
    lie this page can tell -- "the engine is watching the market" when it is not -- so
    the freshness is computed here from ts_et, mirroring engine_health.check_sight_beacon.
    """
    ts = (beacon or {}).get("ts_et") or (beacon or {}).get("ts_utc")
    if not ts:
        return None
    try:
        when = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=ET)
    return max(0, int((dt.datetime.now(ET) - when).total_seconds()))


def _last_core_decision() -> dict:
    """The engine's most recent per-tick verdict, from its own ledger.

    NOT today-bias.json, which has no `last` key -- that composite is assembled elsewhere,
    and coding against it returned None for every field until this was run. This reads
    core-decisions.jsonl, which is what the live engine actually appends to.
    """
    for line in reversed(_tail_lines(CORE_DEC_FILE, 30)):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return {}


def group_bias() -> dict:
    """What the engine thinks, and why it is not in a trade.

    Joins three live sources rather than one: today-bias.json (the morning plan),
    core-decisions.jsonl (the last tick's verdict + the numbered blockers that stopped
    it) and sight-beacon.json (the tape right now). The blockers matter most -- "HOLD"
    alone reads as apathy, while "HOLD, bear blocked by 8, bull by 5/7/10/11" reads as a
    machine that looked and declined, which is the honest picture.
    """
    d = _read(BIAS_FILE) or {}
    dec = _last_core_decision()
    beacon = _read(BEACON_FILE) or {}
    health = _read(ENGINE_HEALTH_FILE) or {}
    preds = d.get("falsifiable_predictions")
    claim = None
    if isinstance(preds, list) and preds:
        first = preds[0]
        claim = first.get("claim") if isinstance(first, dict) else (
            first if isinstance(first, str) else None)

    return {
        "ok": bool(d or dec),
        "date": d.get("date"),
        "bias": d.get("bias"),
        "note": d.get("bias_note"),
        "claim": claim,
        "loss_budget": d.get("daily_loss_budget_dollars"),
        "day_trades_left": d.get("day_trades_remaining"),
        # last tick
        "verdict": dec.get("verdict"),
        "why": dec.get("reason"),
        "at": dec.get("ts_et"),
        "bear_score": dec.get("bear_score"),
        "bull_score": dec.get("bull_score"),
        "bear_blockers": dec.get("bear_blockers"),
        "bull_blockers": dec.get("bull_blockers"),
        # the tape, live
        "spy": beacon.get("spy"),
        "ribbon": beacon.get("ribbon_stack") or dec.get("ribbon"),
        "spread_cents": beacon.get("spread_cents"),
        "vix": dec.get("vix"),
        "tape_age_s": _beacon_age_s(beacon),
        "tape_at": beacon.get("ts_et"),
        "engine_health": health.get("verdict"),
        "source": _src(BIAS_FILE),
        "tape_source": _src(BEACON_FILE),
        "verdict_source": _src(CORE_DEC_FILE),
    }


# --- the arms ---------------------------------------------------------------------------

def group_arms() -> dict:
    """One row per fleet arm: its equity, its net, and whether it is actually filling.

    Deliberately joins THREE sources rather than trusting one: the fleet registry says
    which arms exist, the equity snapshot says what they are worth, and the calendar says
    what they earned. An arm present in the registry but absent from both others is a
    configured arm that has never traded, and the row says so instead of showing zeros.
    """
    fleet = _read(FLEET_FILE) or {}
    # accounts.json stores arms as a LIST of {id, display_name, live, ...}, not a dict.
    # Treating it as a dict silently produced an empty registry AND a phantom "BOOK" row.
    raw = fleet.get("arms")
    reg = {}
    if isinstance(raw, list):
        for a in raw:
            if isinstance(a, dict) and a.get("id"):
                reg[str(a["id"])] = a
    elif isinstance(raw, dict):
        reg = raw

    eq = {a["arm"]: a["equity"] for a in group_equity().get("arms", [])}
    pnl = {a["arm"]: a for a in group_pnl().get("arms", [])}

    # BOOK is the aggregate view, never an arm.
    names = sorted((set(reg) | set(eq) | set(pnl)) - {BOOK_VIEW})
    rows = []
    for arm in names:
        meta = reg.get(arm) if isinstance(reg.get(arm), dict) else {}
        if meta.get("retired") or meta.get("active") is False or meta.get("live") is False:
            continue
        # An arm with neither equity nor a single traded day is configuration noise on a
        # MONEY roster, registry entry or not -- the two dormant futures arms were
        # rendering as full rows of dashes, and a reader who learns that some rows are
        # empty by design stops reading rows. They are not hidden from the operator: the
        # futures LANE has its own card in the lanes rail, with its real health verdict.
        if not eq.get(arm) and not (pnl.get(arm) or {}).get("days_traded"):
            continue
        p = pnl.get(arm) or {}
        rows.append({
            "arm": arm,
            "label": meta.get("display_name") or meta.get("name") or arm,
            "live": meta.get("live") is not False,
            "equity": eq.get(arm),
            "net": p.get("net"),
            "today": p.get("today"),
            "days_traded": p.get("days_traded"),
            "wins": p.get("wins"),
        })
    return {"ok": bool(rows), "arms": rows, "source": _src(FLEET_FILE)}


def group_calendar(days_back: int = 90) -> dict:
    """The per-arm daily P&L grid that sits behind the NET cell.

    J asked for exactly this placement on 2026-08-29: "the total profit we can click
    into and the calendar page is behind that". So it is not on the glass by default --
    it is one click deep, which is what keeps a single pane single.

    Ships the raw per-day nets per arm plus the file's OWN precomputed BOOK summary.
    That summary is carried rather than recomputed on purpose: it is an independent
    cross-check of this module's aggregation, and the two agreeing to the cent
    (1814.86) is the only reason to trust either.
    """
    views = _calendar_views()
    if not views:
        return {"ok": False, "source": _src(CALENDAR_FILE)}

    cutoff = (dt.datetime.now(ET) - dt.timedelta(days=days_back)).strftime("%Y-%m-%d")
    roster = [k for k in views if k != BOOK_VIEW]
    dates = sorted({d for k in roster for d in (views[k].get("days") or {}) if d >= cutoff})

    rows = []
    for arm in sorted(roster):
        days = views[arm].get("days") or {}
        cells = []
        for d in dates:
            row = days.get(d)
            n = _day_net(row)
            cells.append({"d": d, "n": (round(n, 2) if n is not None else None),
                          "t": (row or {}).get("trade_count") if isinstance(row, dict) else None})
        cells_traded = [c for c in cells if c["n"] is not None]
        rows.append({
            "arm": arm, "cells": cells,
            "net": round(sum(c["n"] for c in cells_traded), 2) if cells_traded else None,
        })

    book = views.get(BOOK_VIEW) or {}
    bdays = book.get("days") or {}
    book_cells = []
    for d in dates:
        n = _day_net(bdays.get(d))
        book_cells.append({"d": d, "n": round(n, 2) if n is not None else None,
                           "t": (bdays.get(d) or {}).get("trade_count")})
    return {"ok": bool(dates), "dates": dates, "rows": rows,
            "book": {"arm": "BOOK", "cells": book_cells},
            "summary": book.get("summary"),
            "source": _src(CALENDAR_FILE)}


def build() -> dict:
    out = {"generated_at": dt.datetime.now(ET).isoformat(),
           "market_open": False}
    now = dt.datetime.now(ET)
    # Market-hours flag drives whether the page says "closed" or "live" -- weekend and
    # the 09:30-15:55 RTH band, matching the heartbeat's own window.
    if now.weekday() < 5:
        mins = now.hour * 60 + now.minute
        out["market_open"] = (9 * 60 + 30) <= mins <= (15 * 60 + 55)

    for name, fn in (("equity", group_equity), ("pnl", group_pnl),
                     ("position", group_position), ("bias", group_bias),
                     ("arms", group_arms), ("calendar", group_calendar)):
        try:
            out[name] = fn()
        except Exception as exc:  # noqa: BLE001
            # A group that cannot be built says so IN PLACE. Omitting the key would make
            # the renderer fall through to "no data" and hide a real breakage.
            out[name] = {"ok": False, "error": str(exc)[:200]}
    return out


if __name__ == "__main__":
    json.dump(build(), sys.stdout, indent=2, default=str)
