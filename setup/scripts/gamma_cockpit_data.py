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


# Blocker indices are filter numbers from backtest/lib/filters.py. Bare integers
# on a screen are noise; these are what each one actually vetoed.
BLOCKER_NAMES = {
    1: "time gate (pre-09:35 or no-trade window)",
    5: "ribbon not stacked",
    6: "spread too wide (>=30c)",
    7: "volume divergence",
    8: "VIX regime (not low, not falling)",
    9: "VIX >= 22 hard stop",
    10: "no buyer/seller pressure",
    11: "not enough triggers / none level-tied",
    12: "liquidity sweep at the level",
}


def blocker_name(b) -> str:
    try:
        return "%s · %s" % (b, BLOCKER_NAMES[int(b)])
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
    blockers = (r.get("bear_blockers") or []) if (r.get("bear_score", 0) >= r.get("bull_score", 0)) \
        else (r.get("bull_blockers") or [])
    if isinstance(blockers, str):
        blockers = [blockers]
    return {
        "ts": r.get("ts_et"),
        "verdict": r.get("verdict"),
        "account": r.get("account"),
        "px": r.get("spy"),
        "why": r.get("reason") or "",
        "blockers": [blocker_name(b) for b in blockers][:4],
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

    # --- kalshi -----------------------------------------------------------
    p = STATE / "kalshi" / "shadow-ledger.jsonl"
    lt = STATE / "kalshi" / "last-tick.json"
    raw = _tail_json(p, MAX_TICKS)
    ticks = [_generic_tick(r) for r in raw]
    engines.append({
        "id": "kalshi", "name": "Kalshi weather", "desk": "prediction-markets",
        "cadence": "18:10 ET daily",
        "engine": "Gamma_KalshiAuto",
        "source": p.relative_to(REPO).as_posix(), "last_write": _iso(lt) or _iso(p),
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
