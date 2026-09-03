"""gamma_cockpit_data.py - the ENGINE ROOM and AGENT feeds for the cockpit.

Split out of gamma_home.py, which had reached the repo's 800-line ceiling. This
module answers three questions J asked for directly:

  "I want to see the heartbeat for each of the engines' ticks"
      -> engine_room(): per-engine last tick + a recent tick stream, read from
         each engine's OWN decision ledger. Not a summary of a summary.

  "I want to see what agents are doing"
      -> agent_feed(): what the free Manager dispatched, what the conductor
         shipped, what escalated, and crucially whether each worker artifact
         PASSED the anti-fabrication gate.

  "what we are thinking"
      -> thinking(): the pre-registered thesis for the session plus the engine's
         own stated reason for its last verdict. The engine already writes WHY it
         held (bull/bear scores and the named blockers); nothing surfaced it.

HYDRATION RULE (fixed 2026-08-20)
  Nothing here bakes a relative age. Every timestamp is emitted as an absolute
  ISO string and the page computes "how long ago" at VIEW time. A static page
  that hard-codes "0.1h" keeps claiming 0.1h six hours later, which is the
  silent-staleness anti-pattern this cockpit exists to avoid.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"

# ET is the ONLY frame this rig reports in. This box runs Mountain, so a raw
# mtime is 2h behind the ledgers' own ts_et stamps — showing both unconverted
# would put two different clocks on the same screen (the documented TZ scar).
_ET_OFFSET_H = None


def _et_offset_h() -> float:
    """Hours to add to LOCAL time to get ET, discovered at runtime, never hardcoded."""
    global _ET_OFFSET_H
    if _ET_OFFSET_H is not None:
        return _ET_OFFSET_H
    off = 0.0
    try:
        import subprocess, sys, re as _re
        _no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # OP-27 L41 / C8
        r = subprocess.run([sys.executable, str(REPO / "setup" / "scripts" / "et_clock.py")],
                           cwd=str(REPO), capture_output=True, text=True, timeout=30,
                           encoding="utf-8", errors="replace", creationflags=_no_window)
        m = _re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", r.stdout or "")
        if m:
            et = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            off = round((et - datetime.now()).total_seconds() / 3600.0 * 2) / 2
    except Exception:                            # noqa: BLE001 - fail to 0, never crash the page
        off = 0.0
    _ET_OFFSET_H = off
    return off


# Blocker indices are filter numbers from backtest/lib/filters.py.
#
# ⚠ THE TRAP THIS FIXES (found 2026-08-20, in code shipped the same day):
# evaluate_bearish_setup and evaluate_bullish_setup REUSE THE SAME INDICES FOR
# DIFFERENT FILTERS. The first version of this map was transcribed from the BULL
# function and applied to both, which mislabelled every bear tick on the cockpit
# AND in that day's EOD audit:
#     index 9  bull = "VIX < 22 hard cap"   bear = breakdown-bar VOLUME confirmation
#     index 10 bull = buyer pressure         bear = not enough triggers
#     index 11 bull = triggers/level-tied    bear = liquidity sweep at the level
# Filter 6 was also inverted in BOTH directions: it requires ribbon spread
# >= 30c, so it blocks when the ribbon is too NARROW (compressed/chop), not when
# a spread is "too wide". And note filter 6 reads the SATY RIBBON spread, not an
# option bid-ask spread — reading it as bid-ask produced a bogus "112c median
# spread" finding before this was traced.
#
# Verified by parsing each blockers.append(N) site inside its own function.
BEAR_BLOCKER_NAMES = {
    1: "time gate (pre-09:35 / no-trade window)",
    5: "ribbon not BEAR-stacked",
    6: "ribbon too narrow (needs spread >= 30c)",
    7: "volume divergence failed",
    8: "VIX gate (needs VIX > 17.30 AND rising)",
    9: "no breakdown bar (volume confirmation)",
    10: "not enough triggers",
    11: "liquidity sweep at the level",
}

BULL_BLOCKER_NAMES = {
    1: "time gate (pre-09:35 / no-trade window)",
    5: "ribbon not BULL-stacked",
    6: "ribbon too narrow (needs spread >= 30c)",
    7: "volume divergence",
    8: "VIX gate (needs VIX < 17.20 OR falling)",
    9: "VIX >= 22 hard cap",
    10: "no buyer pressure",
    11: "not enough triggers / none level-tied",
    12: "liquidity sweep at the level",
}

# Kept as the bear map so any legacy caller stays correct for the bear path,
# which is the one the cockpit renders by default.
BLOCKER_NAMES = BEAR_BLOCKER_NAMES


def blocker_name(b, side: str = "bear") -> str:
    """Name one blocker index. `side` MUST be supplied for bull ticks.

    An unknown index degrades to itself rather than inventing a name.
    """
    table = BULL_BLOCKER_NAMES if str(side).lower().startswith("bull") else BEAR_BLOCKER_NAMES
    try:
        return "%s · %s" % (b, table[int(b)])
    except (ValueError, TypeError, KeyError):
        return str(b)


MAX_TICKS = 40          # enough to see a session's shape without bloating the page


def _iso(p: Path):
    """Absolute mtime as an ET ISO string. The page turns it into an age at VIEW time."""
    try:
        local = datetime.fromtimestamp(p.stat().st_mtime)
        return (local + timedelta(hours=_et_offset_h())).isoformat(timespec="seconds")
    except OSError:
        return None


def _iso_now() -> str:
    """Now, in ET, ISO — the stamp the page does age arithmetic against."""
    return (datetime.now() + timedelta(hours=_et_offset_h())).isoformat(timespec="seconds")


def _tail_json(p: Path, n: int) -> list:
    try:
        lines = [l for l in p.open(encoding="utf-8", errors="replace") if l.strip()]
    except OSError:
        return []
    out = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _count(p: Path) -> int:
    try:
        return sum(1 for l in p.open(encoding="utf-8", errors="replace") if l.strip())
    except OSError:
        return 0


def _spy_tick(r: dict) -> dict:
    """One SPY core decision, reduced to what a human reads.

    The engine already records WHY: bull/bear scores and the named blockers that
    vetoed. That is the thinking; it just never reached a surface.
    """
    # Which side's blockers we are reading determines which NAME TABLE applies —
    # the two functions reuse indices for different filters.
    side = "bear" if (r.get("bear_score", 0) >= r.get("bull_score", 0)) else "bull"
    blockers = (r.get("bear_blockers") or []) if side == "bear" else (r.get("bull_blockers") or [])
    if isinstance(blockers, str):
        blockers = [blockers]
    return {
        "ts": r.get("ts_et"),
        "verdict": r.get("verdict"),
        "account": r.get("account"),
        "px": r.get("spy"),
        "why": r.get("reason") or "",
        "blockers": [blocker_name(b, side) for b in blockers][:4],
        "blocker_side": side,
        "scores": {"bull": r.get("bull_score"), "bear": r.get("bear_score")},
        "ctx": {"ribbon": r.get("ribbon"), "htf": r.get("htf_15m"), "vix": r.get("vix"),
                "spread_c": round(r["spread_cents"], 1) if isinstance(r.get("spread_cents"), (int, float)) else None},
        "setup": r.get("setup"), "side": r.get("side"),
    }


def _generic_tick(r: dict) -> dict:
    ts = r.get("ts_et") or r.get("at_et") or r.get("ts_utc") or r.get("ts") or r.get("date")
    return {
        "ts": ts,
        "verdict": r.get("verdict") or r.get("action") or r.get("signal_action") or r.get("decision") or "—",
        "why": str(r.get("reason") or r.get("note") or r.get("why") or "")[:180],
        "sym": r.get("symbol") or r.get("arm") or r.get("contract") or "",
    }


def _kalshi_weather_tick(r: dict) -> dict:
    """Shape one row of kalshi_auto.py's weather lane (weather-predictions.jsonl)
    for the cockpit tick stream. This lane has no `verdict` field the way other
    engines' decision rows do -- the "decision" is which contract it picked
    (`pick_ticker`) and, once the day's high has been observed, whether that pick
    won (`pick_won`). `_generic_tick` returns "—" for every row here because none
    of its verdict-ish keys exist on this shape (KALSHI-COCKPIT-ENGINE-TICK-STALE-LANE)."""
    scored = r.get("observed") is not None
    verdict = ("WIN" if r.get("pick_won") else "LOSS") if scored else "PICKED"
    label = r.get("label") or r.get("series") or "?"
    pick = r.get("pick_ticker") or ""
    p = r.get("pick_p")
    ask = r.get("pick_ask")
    why = "%s -> %s (p=%.2f, ask=%.2f)" % (label, pick, p if isinstance(p, (int, float)) else 0.0,
                                            ask if isinstance(ask, (int, float)) else 0.0)
    if scored:
        why += " observed=%s abs_err=%s" % (r.get("observed"), r.get("abs_err"))
    return {
        "ts": r.get("ts_utc"),
        "verdict": verdict,
        "why": why[:180],
        "sym": r.get("series") or "",
    }


def engine_room() -> dict:
    """Per-engine heartbeat. Each engine reports from its OWN ledger."""
    engines = []

    # --- SPY 0DTE core ---------------------------------------------------
    p = STATE / "core-decisions.jsonl"
    raw = _tail_json(p, MAX_TICKS)
    ticks = [_spy_tick(r) for r in raw]
    engines.append({
        "id": "spy-core", "name": "SPY 0DTE core", "desk": "spy-0dte",
        "cadence": "every 1 min, 09:30-15:55 ET",
        "engine": "setup/scripts/heartbeat_core.py (deterministic, no LLM on the tick)",
        "source": p.relative_to(REPO).as_posix(), "last_write": _iso(p),
        "total": _count(p), "ticks": list(reversed(ticks)),
        "verdicts": _tally(ticks),
    })

    # --- futures: two lanes, separate ledgers -----------------------------
    for sub, label, cad in (("trader", "Futures trader (fillsim)", "every 5 min RTH"),
                            ("trader-broker", "Futures broker lane", "every 5 min RTH")):
        p = STATE / "futures" / sub / "decisions.jsonl"
        raw = _tail_json(p, MAX_TICKS)
        ticks = [_generic_tick(r) for r in raw]
        engines.append({
            "id": "fut-" + sub, "name": label, "desk": "futures", "cadence": cad,
            "engine": "setup/scripts/futures_trader_runner.py",
            "source": p.relative_to(REPO).as_posix(), "last_write": _iso(p),
            "total": _count(p), "ticks": list(reversed(ticks)), "verdicts": _tally(ticks),
        })

    # --- multi-symbol shadow ---------------------------------------------
    p = STATE / "multi" / "shadow-ledger.jsonl"
    raw = _tail_json(p, MAX_TICKS)
    ticks = [_generic_tick(r) for r in raw]
    engines.append({
        "id": "multi-core", "name": "Multi-symbol shadow", "desk": "multi-sector",
        "cadence": "every 15 min RTH (~72-name universe)",
        "engine": "multi/core.py — contains no order-placement call by construction",
        "source": p.relative_to(REPO).as_posix(), "last_write": _iso(p),
        "total": _count(p), "ticks": list(reversed(ticks)), "verdicts": _tally(ticks),
    })

    # --- kalshi -------------------------------------------------------------
    # weather-predictions.jsonl is kalshi_auto.py's ledger -- the live weather
    # lane (Gamma_KalshiAuto, 18:10 ET daily). shadow-ledger.jsonl / last-tick.json
    # belong to the RETIRED kalshi_tick.py SPY-directional lane (superseded
    # 2026-08-09; no scheduled task for it exists) and were frozen since that date
    # while this block kept reading them as if they were live
    # (KALSHI-COCKPIT-ENGINE-TICK-STALE-LANE — same bug class already fixed in
    # desk_allocator.py#assess_prediction_markets()).
    p = STATE / "kalshi" / "weather-predictions.jsonl"
    raw = _tail_json(p, MAX_TICKS)
    ticks = [_kalshi_weather_tick(r) for r in raw]
    engines.append({
        "id": "kalshi", "name": "Kalshi weather", "desk": "prediction-markets",
        "cadence": "18:10 ET daily",
        "engine": "Gamma_KalshiAuto",
        "source": p.relative_to(REPO).as_posix(), "last_write": _iso(p),
        "total": _count(p), "ticks": list(reversed(ticks)), "verdicts": _tally(ticks),
    })

    return {"engines": engines,
            "built": (datetime.now() + timedelta(hours=_et_offset_h())).isoformat(timespec="seconds"),
            "tz": "ET"}


def _tally(ticks: list) -> dict:
    out = {}
    for t in ticks:
        k = str(t.get("verdict") or "—")
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1])[:6])


def agent_feed(limit: int = 45) -> dict:
    """What the agents actually did — including whether their output was TRUSTED.

    `artifact_verdict` is the anti-fabrication gate's ruling on that worker's
    report. Surfacing it is the point: 12 of 690 historical worker reports named
    artifacts that never existed, and nothing showed J which ones.
    """
    events = []

    mp = STATE / "manager-log.jsonl"
    for r in _tail_json(mp, 220):
        ph = r.get("phase")
        if ph not in ("dispatch", "escalate", "escalate_suppressed", "verify_error"):
            continue
        events.append({
            "ts": r.get("ts_et"), "who": r.get("role") or "coordinator", "tier": "free",
            "what": r.get("action") or r.get("reason") or ph,
            "ok": bool(r.get("ok", True)) and ph != "verify_error",
            "verdict": r.get("artifact_verdict") or ("SUPPRESSED" if ph == "escalate_suppressed" else None),
            "lane": (r.get("lane") or "").split("::")[-1],
            "err": str(r.get("error") or "")[:120],
            "phase": ph,
        })

    cp = STATE / "conductor-outcomes.jsonl"
    for r in _tail_json(cp, 40):
        events.append({
            "ts": r.get("ts_et") or r.get("ts"), "who": "conductor", "tier": "claude",
            "what": str(r.get("task_id") or r.get("task") or "fire")[:90],
            "ok": bool(r.get("drained", r.get("ok", True))),
            "verdict": None, "lane": r.get("model") or "", "err": "", "phase": "fire",
        })

    events = [e for e in events if e.get("ts")]
    events.sort(key=lambda e: str(e["ts"]), reverse=True)

    fab = [e for e in events if e.get("verdict") == "FABRICATED"]
    return {
        "events": events[:limit],
        "counts": {
            "total": len(events),
            "failed": sum(1 for e in events if not e["ok"]),
            "fabricated": len(fab),
            "suppressed": sum(1 for e in events if e.get("verdict") == "SUPPRESSED"),
        },
        "sources": [
            {"path": mp.relative_to(REPO).as_posix(), "last_write": _iso(mp)},
            {"path": cp.relative_to(REPO).as_posix(), "last_write": _iso(cp)},
        ],
    }


def thinking() -> dict:
    """The pre-registered thesis + the engine's own last stated reason."""
    out = {"claims": [], "bias": None, "note": "", "last": None, "source": None}
    bp = STATE / "today-bias.json"
    try:
        b = json.loads(bp.read_text(encoding="utf-8"))
        out["bias"] = b.get("bias")
        out["note"] = b.get("bias_note") or ""
        raw = b.get("falsifiable_predictions") or b.get("falsifiable_hypothesis") or []
        if isinstance(raw, (str, dict)):
            raw = [raw]
        for x in raw[:4]:
            if isinstance(x, str):
                try:
                    x = json.loads(x)
                except ValueError:
                    out["claims"].append({"claim": x, "window": ""})
                    continue
            if isinstance(x, dict):
                out["claims"].append({"claim": x.get("claim") or x.get("prediction") or "",
                                      "window": x.get("trigger_window") or ""})
        out["source"] = {"path": bp.relative_to(REPO).as_posix(), "last_write": _iso(bp)}
    except (OSError, ValueError):
        pass

    rows = _tail_json(STATE / "core-decisions.jsonl", 1)
    if rows:
        out["last"] = _spy_tick(rows[0])
    return out


def briefing(desks: list, allocation: dict, answers: list) -> dict:
    """What I would SAY if you walked in and asked how it is going.

    J: "command center should be like me talking to an employee." So this is
    first person, and it leads with the honest headline rather than a metric wall.

    DETERMINISTIC BY DESIGN - no LLM. Every sentence is a template filled from
    state that is already on disk, which means it can never invent a mood, a
    reason or a number the ledgers do not support. An LLM here would be the
    fabrication risk this whole cockpit was built to close, pointed at J's
    first paragraph.
    """
    th = thinking()
    lines, flags = [], []

    # 1. Where we stand — the engine's own last verdict and its own reason.
    last = th.get("last") or {}
    if last.get("verdict") == "HOLD" and last.get("why"):
        s = "Last tick I held — %s." % last["why"]
        if last.get("blockers"):
            s += " What stopped it: %s." % "; ".join(last["blockers"][:2])
        lines.append(s)
    elif last.get("verdict"):
        lines.append("Last tick I called %s%s." % (
            last["verdict"], (" on " + last["setup"]) if last.get("setup") else ""))

    # 2. What I was watching for, pre-registered before the session.
    if th.get("claims"):
        lines.append("Going in I was %s: %s" % (
            (th.get("bias") or "undecided").lower(), th["claims"][0]["claim"]))

    # 3. The desks, per desk — never an aggregate that hides a weak arm.
    live = [d for d in desks if "REAL" in str(d.get("chip", "")).upper()]
    sim = [d for d in desks if d not in live]
    if live:
        lines.append("Only %s is trading real fills. The other %d desk%s are shadow — "
                     "no money on them." % (live[0]["name"], len(sim), "s" if len(sim) != 1 else ""))

    # 4. The single thing I would raise first.
    top = (allocation.get("desks") or [{}])[0]
    if top.get("points", 0) > 0 and top.get("why"):
        w = top["why"][0]
        if "ROTTING" in w:
            lines.append("The one thing I would put in front of you: %s cleared its arming bar "
                         "and is sitting unarmed. That is a decision waiting on you, not a bug."
                         % top["name"])
            flags.append({"kind": "decision", "text": "%s — %s" % (top["name"], top.get("headline", ""))})
        elif "BROKEN" in w:
            lines.append("Heads up: %s is not ticking. %s" % (top["name"], top.get("headline", "")))
            flags.append({"kind": "broken", "text": w})

    # 5. Anything off-nominal, named rather than counted.
    bad = [a for a in answers if str(a.get("verdict", "")).upper() in ("RED", "YELLOW", "DEGRADED", "NO DATA")]
    if bad:
        lines.append("%d thing%s off-nominal: %s." % (
            len(bad), "" if len(bad) == 1 else "s",
            "; ".join(a["q"].rstrip("?") for a in bad[:3])))
    else:
        lines.append("Nothing is off-nominal right now.")

    return {"lines": lines, "flags": flags,
            "bias": th.get("bias"), "claims": th.get("claims", []),
            "last": last, "source": th.get("source")}


FILLS_LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"

# current-position*.json looked like the obvious source and is a TRAP: those files
# are 1,500-2,400h stale (Jun/Jul abandonment), still parse cleanly, and would have
# rendered a confident wrong answer. Positions are RECONSTRUCTED from the fills
# ledger instead, which is the same authority the P&L calendar settles against.
STALE_POSITION_FILES = (
    "automation/state/current-position.json",
    "automation/state/current-position-safe.json",
    "automation/state/current-position-bold.json",
    "automation/state/aggressive/current-position-bold.json",
)


def positions() -> dict:
    """Net open positions per arm, rebuilt from every fill.

    net(arm, symbol) = sum(buy qty) - sum(sell qty). A symbol nets to zero when
    the round trip closed, so anything left non-zero is genuinely open right now.
    FLAT is a real answer and gets stated plainly rather than shown as an empty
    table - "sitting out is a valid day".
    """
    rows = _tail_json(FILLS_LEDGER, 100000)
    net, last_close, arms = {}, None, {}
    for r in rows:
        if not r.get("is_option") or r.get("is_crypto"):
            continue
        arm, sym = r.get("arm"), r.get("symbol")
        q = float(r.get("qty") or 0) * (1 if str(r.get("side", "")).lower().startswith("b") else -1)
        key = (arm, sym)
        net[key] = net.get(key, 0.0) + q
        arms.setdefault(arm, {"fills": 0, "last_ts": None})
        arms[arm]["fills"] += 1
        arms[arm]["last_ts"] = r.get("ts_et") or arms[arm]["last_ts"]
        if q < 0:
            last_close = r

    open_rows = []
    for (arm, sym), q in net.items():
        if abs(q) < 1e-9:
            continue
        open_rows.append({"arm": arm, "symbol": sym, "qty": round(q, 4),
                          "side": "LONG" if q > 0 else "SHORT"})
    open_rows.sort(key=lambda r: (r["arm"], r["symbol"]))

    return {
        "flat": not open_rows,
        "open": open_rows,
        "arms": [{"arm": a, "fills": v["fills"], "last_fill": v["last_ts"]}
                 for a, v in sorted(arms.items())],
        "last_close": ({"symbol": last_close.get("symbol"), "arm": last_close.get("arm"),
                        "ts": last_close.get("ts_et"), "price": last_close.get("price"),
                        "qty": last_close.get("qty")} if last_close else None),
        "option_fills": sum(1 for r in rows if r.get("is_option") and not r.get("is_crypto")),
        "source": {"path": FILLS_LEDGER.relative_to(REPO).as_posix(),
                   "last_write": _iso(FILLS_LEDGER)},
        "ignored_stale": [
            {"path": p, "age_h": round(_age_of(REPO / p) or 0, 1)} for p in STALE_POSITION_FILES
        ],
    }


def _age_of(p: Path):
    try:
        return (datetime.now() - datetime.fromtimestamp(p.stat().st_mtime)).total_seconds() / 3600.0
    except OSError:
        return None
