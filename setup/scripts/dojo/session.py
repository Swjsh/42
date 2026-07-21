"""dojo/session.py — the DOJO session spine: state machine, append-only ledger, hard fence, CLI.

Run by the SESSION AGENT (Sonnet + J), never a broker. See DOJO-ARCHITECTURE-DECISION.md.
The agent drives TradingView via MCP tools; between MCP calls it invokes this CLI:

  python -m dojo.session start   --replay-day 2026-07-17
  python -m dojo.session step    --session <id> --cursor <tv_current_date_epoch>
  python -m dojo.session directive --session <id> --json '<directive json>'
  python -m dojo.session close   --session <id>
  python -m dojo.session status  --session <id>

HARD FENCE: this module writes ONLY under automation/state/dojo/, imports no broker/alpaca
module, and performs no git operations. Guard-tested in backtest/tests/test_dojo_fence.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# --- path setup (mirror futures_edge3_sim.py): make sibling engine modules importable ---
_ROOT = Path(__file__).resolve().parents[3]  # .../42
for _p in ("backtest", "setup/scripts", "automation/state/fleet"):
    _ap = str(_ROOT / _p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

from dojo import clock  # noqa: E402  (pure, no I/O, safe)

ET = ZoneInfo("America/New_York")
DOJO_DIR = _ROOT / "automation" / "state" / "dojo"
SESSIONS_DIR = DOJO_DIR / "sessions"

PHASE_CREATED = "CREATED"
PHASE_STEPPING = "STEPPING"
PHASE_CLOSED = "CLOSED"


# --------------------------------------------------------------------------- fence
def _assert_under_dojo(path: Path) -> Path:
    """Every write goes through here: refuse any path not under automation/state/dojo/."""
    rp = path.resolve()
    if DOJO_DIR.resolve() not in rp.parents and rp != DOJO_DIR.resolve():
        raise PermissionError(f"DOJO fence: refusing to write outside {DOJO_DIR}: {rp}")
    return path


def _now_et() -> datetime:
    return datetime.now(ET)


# --------------------------------------------------------------------------- state
@dataclass
class SessionState:
    session_id: str
    replay_day: str
    phase: str
    created_et: str
    last_cursor_epoch: int | None = None
    last_bar_et: str | None = None
    step_count: int = 0
    directive_count: int = 0

    @property
    def ledger_path(self) -> Path:
        return SESSIONS_DIR / f"{self.session_id}.jsonl"

    @property
    def state_path(self) -> Path:
        return SESSIONS_DIR / f"{self.session_id}.state.json"


def _write_state(st: SessionState) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    _assert_under_dojo(st.state_path).write_text(json.dumps(asdict(st), indent=2), encoding="utf-8")


def _load_state(session_id: str) -> SessionState:
    p = SESSIONS_DIR / f"{session_id}.state.json"
    if not p.exists():
        raise FileNotFoundError(f"no dojo session {session_id!r} at {p}")
    return SessionState(**json.loads(p.read_text(encoding="utf-8")))


def _append_ledger(st: SessionState, row: dict) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    row = {"logged_et": _now_et().isoformat(), **row}
    with open(_assert_under_dojo(st.ledger_path), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


# --------------------------------------------------------------------------- commands
def cmd_start(replay_day: str) -> dict:
    _validate_day(replay_day)
    sid = f"{replay_day}-{_now_et():%H%M%S}"
    st = SessionState(session_id=sid, replay_day=replay_day, phase=PHASE_CREATED,
                      created_et=_now_et().isoformat())
    _write_state(st)
    _append_ledger(st, {"event": "session_start", "replay_day": replay_day})
    return {"ok": True, "session_id": sid, "phase": st.phase,
            "ledger": str(st.ledger_path), "note": "agent: replay_start on TV, then step per bar"}


def cmd_step(session_id: str, cursor_epoch: int) -> dict:
    st = _load_state(session_id)
    if st.phase == PHASE_CLOSED:
        return {"ok": False, "error": "session is CLOSED"}
    cursor_et = clock.resolve_cursor(cursor_epoch)
    bar_et = clock.latest_closed_5m_bar_et(cursor_et)
    st.phase = PHASE_STEPPING
    st.last_cursor_epoch = cursor_epoch
    st.last_bar_et = bar_et.isoformat() if bar_et else None
    st.step_count += 1

    if bar_et is None:
        whisper = f"[{cursor_et:%Y-%m-%d %H:%M ET}] pre-RTH / no closed 5-min bar yet — engine idle."
        _append_ledger(st, {"event": "step", "cursor_epoch": cursor_epoch,
                            "cursor_et": cursor_et.isoformat(), "bar_et": None,
                            "rth": clock.is_rth(cursor_et), "decisions": []})
        _write_state(st)
        return {"ok": True, "session_id": session_id, "bar_et": None, "whisper": whisper}

    # --- lazy engine reuse (Agent A) + whisper (Agent B); graceful if not built yet ---
    # NB: `from dojo import X` (mirrors the module-top `from dojo import clock`) — bare
    # `import X` does NOT resolve because setup/scripts/dojo/ is not itself on sys.path
    # (only its parent setup/scripts is); a bare import could also shadow-collide.
    try:
        from dojo import engine_step  # type: ignore
        from dojo import whisper as dojo_whisper  # type: ignore
    except ImportError as e:
        _write_state(st)
        return {"ok": True, "session_id": session_id, "bar_et": bar_et.isoformat(),
                "whisper": f"[{bar_et:%H:%M ET}] engine_step/whisper module not built yet "
                           f"(Phase 1 in progress): {e}"}

    bars_df = engine_step.load_day_bars(st.replay_day)
    decisions = engine_step.step(st.replay_day, bar_et, bars_df)
    # sim executor advances any open directed positions (Agent C); graceful if not built
    events = _advance_sim(st, bar_et, bars_df)
    whisper = dojo_whisper.render(decisions, bar_et)
    _append_ledger(st, {"event": "step", "cursor_epoch": cursor_epoch,
                        "cursor_et": cursor_et.isoformat(), "bar_et": bar_et.isoformat(),
                        "rth": clock.is_rth(cursor_et),
                        "decisions": [_decision_row(d) for d in decisions],
                        "sim_events": events})
    _write_state(st)
    return {"ok": True, "session_id": session_id, "bar_et": bar_et.isoformat(), "whisper": whisper}


def cmd_directive(session_id: str, raw_json: str) -> dict:
    st = _load_state(session_id)
    if st.phase != PHASE_STEPPING:
        return {"ok": False, "error": f"can only issue a directive while STEPPING (phase={st.phase})"}
    try:
        from dojo import directive as dojo_directive  # type: ignore
    except ImportError as e:
        return {"ok": False, "error": f"directive module not built yet (Phase 1): {e}"}
    try:
        raw = json.loads(raw_json)
        d = dojo_directive.parse_and_validate(raw)
    except Exception as e:  # fail LOUD per contract
        return {"ok": False, "error": f"directive rejected: {e}"}
    st.directive_count += 1
    _append_ledger(st, {"event": "directive", "directive": dojo_directive.to_ledger_row(d)})
    _arm_sim(st, d)
    _write_state(st)
    return {"ok": True, "session_id": session_id, "directive_id": getattr(d, "id", None),
            "armed_arms": getattr(d, "arms", None)}


def cmd_close(session_id: str) -> dict:
    st = _load_state(session_id)
    st.phase = PHASE_CLOSED
    _append_ledger(st, {"event": "session_close",
                        "steps": st.step_count, "directives": st.directive_count})
    result = {"ok": True, "session_id": session_id, "steps": st.step_count,
              "directives": st.directive_count}
    try:
        from dojo import scorecard  # type: ignore
        result["scorecard"] = scorecard.score_session(st.ledger_path)
    except ImportError:
        result["scorecard"] = "scorecard module not built yet (Phase 1b)"
    _write_state(st)
    result["harvest_stub"] = str(_write_harvest_stub(st))
    return result


def cmd_status(session_id: str) -> dict:
    st = _load_state(session_id)
    return {"ok": True, **asdict(st)}


# --------------------------------------------------------------------------- sim glue (Agent C)
def _advance_sim(st: SessionState, bar_et, bars_df) -> list:
    try:
        from dojo import sim_executor  # type: ignore
    except ImportError:
        return []
    return sim_executor.advance_session(st.session_id, bar_et, bars_df, dojo_dir=DOJO_DIR)


def _arm_sim(st: SessionState, directive) -> None:
    try:
        from dojo import sim_executor  # type: ignore
    except ImportError:
        return
    sim_executor.arm_directive(st.session_id, directive, dojo_dir=DOJO_DIR)


# --------------------------------------------------------------------------- helpers
def _decision_row(d) -> dict:
    if hasattr(d, "_asdict"):
        return d._asdict()
    if hasattr(d, "__dict__"):
        return {k: v for k, v in vars(d).items()}
    return dict(d)


def _write_harvest_stub(st: SessionState) -> Path:
    p = SESSIONS_DIR / f"{st.session_id}-harvest.md"
    body = (
        f"# DOJO session harvest — replay {st.replay_day} (session {st.session_id})\n\n"
        f"> Two-lane routing (DOJO-ARCHITECTURE-DECISION.md). Every divergence goes to ONE lane.\n\n"
        f"Steps: {st.step_count} · Directives: {st.directive_count}\n\n"
        f"## LANE A — capability gaps (code could not express J's directive) -> build queue\n\n- \n\n"
        f"## LANE B — policy rules (engine SHOULD do X when Y) -> pre-registered hypothesis\n\n- \n\n"
        f"## Divergences (J-directed vs engine-actual) — from scorecard\n\n- \n"
    )
    _assert_under_dojo(p).write_text(body, encoding="utf-8")
    return p


def _validate_day(replay_day: str) -> None:
    datetime.strptime(replay_day, "%Y-%m-%d")  # raises on malformed


# --------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dojo.session", description="DOJO replay training session spine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("start"); p.add_argument("--replay-day", required=True)
    p = sub.add_parser("step"); p.add_argument("--session", required=True); p.add_argument("--cursor", required=True, type=int)
    p = sub.add_parser("directive"); p.add_argument("--session", required=True); p.add_argument("--json", required=True)
    p = sub.add_parser("close"); p.add_argument("--session", required=True)
    p = sub.add_parser("status"); p.add_argument("--session", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "start":
        out = cmd_start(a.replay_day)
    elif a.cmd == "step":
        out = cmd_step(a.session, a.cursor)
    elif a.cmd == "directive":
        out = cmd_directive(a.session, a.json)
    elif a.cmd == "close":
        out = cmd_close(a.session)
    else:
        out = cmd_status(a.session)
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
