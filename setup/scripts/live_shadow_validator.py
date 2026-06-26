"""live_shadow_validator.py — intra-day proof the free agents SEE + DECIDE the market right.

Runs every ~15 min during RTH (READ-ONLY, $0, free pool — does NOT contend with the
Haiku heartbeat's Max pool). For each NEW heartbeat decision tick, it feeds a free agent
the same objective market snapshot (with the engine's own read/decision HIDDEN) and checks:

  1. SIGHT  — does the free agent's read of the data match the engine's ground-truth?
              trend vs `ribbon_stack`, favored side vs `bull_score`/`bear_score`.
              A contradiction = the free agent is NOT seeing the market appropriately.
  2. DECISION — does the free agent's action match the proven live engine? (DT-agreement)

Writes a rolling live scorecard (automation/state/live-shadow-scorecard.json) and flags
a hard sight-contradiction or a DT-agreement drop to the Discord outbox. This is the
LIVE complement to the EOD Gamma_ShadowEval, and the data that graduates a free agent to
live decisions (>=85% DT + high sight-accuracy over >=15 live days).

NEVER places orders. NEVER touches heartbeat*.md / params*.json. Pure observer.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1].parent
sys.path.insert(0, str(REPO / "setup" / "scripts"))
import swarm_client as sc  # noqa: E402

STATE = REPO / "automation" / "state"
DECISIONS = STATE / "decisions.jsonl"
SCORECARD = STATE / "live-shadow-scorecard.json"
CHECKPOINT = STATE / ".live-shadow-checkpoint.json"
OUTBOX = STATE / "discord-outbox.jsonl"

READ_SCHEMA = {
    "type": "object",
    "required": ["trend", "favored", "action"],
    "properties": {
        "trend": {"type": "string", "description": "BULL / BEAR / NEUTRAL — your read of the trend"},
        "favored": {"type": "string", "description": "bull / bear / neutral — which side the momentum/scores favor"},
        "action": {"type": "string", "description": "HOLD / ENTER_BULL / ENTER_BEAR / EXIT — what you would do now"},
        "read": {"type": "string", "description": "one terse sentence on the market picture"},
    },
}

SYSTEM = (
    "You are a 0DTE SPY options market reader. Given a market snapshot, state your read. "
    "Be objective and consistent with the numbers. Output ONLY the JSON object."
)


def _et_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=-4)


def _is_rth() -> bool:
    et = _et_now()
    h = et.hour + et.minute / 60
    return et.weekday() < 5 and 9.5 <= h <= 16.0


def _flag(msg: str) -> None:
    try:
        with open(OUTBOX, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "source": "live_shadow_validator", "alert": msg[:400]}) + "\n")
    except OSError:
        pass


def _today_rows() -> list[dict]:
    if not DECISIONS.exists():
        return []
    today = _et_now().strftime("%Y-%m-%d")
    rows = []
    for line in DECISIONS.read_text(encoding="utf-8", errors="replace").strip().splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("date") == today:
            rows.append(d)
    return rows


def _snapshot(row: dict) -> str:
    # Objective inputs ONLY — the engine's own ribbon_stack / action / setup are HIDDEN
    # so the free agent must derive its read independently (then we check it).
    return (f"time_et={row.get('time_et')} SPY={row.get('spy')} VIX={row.get('vix')} "
            f"VIX_direction={row.get('vix_dir')} ribbon_spread_cents={row.get('ribbon_spread_cents')} "
            f"htf_15m_stack={row.get('htf_15m_stack')} bull_score={row.get('bull_score')} "
            f"bear_score={row.get('bear_score')} position={row.get('position_status')}")


def _norm_action(a: str) -> str:
    a = (a or "").upper()
    if "ENTER" in a or a in ("BUY", "LONG", "SHORT"):
        return "ENTER_BULL" if ("BULL" in a or "LONG" in a) else ("ENTER_BEAR" if ("BEAR" in a or "SHORT" in a) else "ENTER")
    if "EXIT" in a or "CLOSE" in a or "TP" in a or "STOP" in a:
        return "EXIT"
    return "HOLD"


def _sight_ok(read: dict, row: dict) -> tuple[bool, str]:
    """Compare the free agent's read to the engine's ground-truth anchors."""
    problems = []
    trend = (read.get("trend") or "").upper()
    ribbon = (row.get("ribbon_stack") or "").upper()
    if ribbon in ("BULL", "BEAR") and trend in ("BULL", "BEAR") and trend != ribbon:
        problems.append(f"trend={trend} but ribbon_stack={ribbon}")
    fav = (read.get("favored") or "").lower()
    bs, br = row.get("bull_score") or 0, row.get("bear_score") or 0
    if isinstance(bs, (int, float)) and isinstance(br, (int, float)) and bs != br:
        truth = "bull" if bs > br else "bear"
        if fav in ("bull", "bear") and fav != truth:
            problems.append(f"favored={fav} but bull={bs}/bear={br}")
    return (len(problems) == 0), "; ".join(problems)


def _committed(read: dict, row: dict):
    """Did the free agent COMMIT to the engine's CLEAR directional read?
    Returns None when the engine read isn't clear (N/A), else True/False. A free agent
    that hedges 'neutral' on a clearly directional tape isn't really SEEING the move."""
    ribbon = (row.get("ribbon_stack") or "").upper()
    bs, br = row.get("bull_score") or 0, row.get("bear_score") or 0
    clear = (ribbon in ("BULL", "BEAR") and isinstance(bs, (int, float))
             and isinstance(br, (int, float)) and abs(bs - br) >= 2)
    if not clear:
        return None
    return (read.get("trend") or "").upper() == ribbon


def main() -> int:
    if not _is_rth():
        print("skipped (not RTH)")
        return 0
    rows = _today_rows()
    if not rows:
        print("no decision rows yet today")
        return 0
    # Only score ticks newer than the last checkpoint
    last_id = 0
    if CHECKPOINT.exists():
        try:
            last_id = int(json.loads(CHECKPOINT.read_text(encoding="utf-8")).get("last_tick_id", 0))
        except (json.JSONDecodeError, OSError, ValueError):
            last_id = 0
    new = [r for r in rows if int(r.get("tick_id", 0) or 0) > last_id][-8:]  # cap per fire
    results = []
    for row in new:
        env, read = sc.call_role_json(
            "coordinator", "Market snapshot — give your read:\n" + _snapshot(row),
            READ_SCHEMA, system=SYSTEM, max_tokens=400, task_id="live_shadow")
        if not read:
            results.append({"tick": row.get("tick_id"), "ok": False, "err": "no_read", "lane": env.get("lane")})
            continue
        sight_ok, sight_why = _sight_ok(read, row)
        dt_agree = _norm_action(read.get("action")) == _norm_action(row.get("action"))
        results.append({"tick": row.get("tick_id"), "ok": True, "lane": env.get("lane"),
                        "sight_ok": sight_ok, "sight_why": sight_why, "dt_agree": dt_agree,
                        "committed": _committed(read, row),
                        "free_action": read.get("action"), "engine_action": row.get("action"),
                        "free_trend": read.get("trend"), "engine_ribbon": row.get("ribbon_stack")})
        if not sight_ok:
            _flag(f"SIGHT contradiction tick {row.get('tick_id')} ({env.get('lane')}): {sight_why}")

    scored = [r for r in results if r.get("ok")]
    n = len(scored)
    sight_rate = round(sum(1 for r in scored if r["sight_ok"]) / n, 3) if n else None
    dt_rate = round(sum(1 for r in scored if r["dt_agree"]) / n, 3) if n else None

    # Roll into today's scorecard (accumulate across fires)
    card = {}
    if SCORECARD.exists():
        try:
            card = json.loads(SCORECARD.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            card = {}
    if card.get("date") != _et_now().strftime("%Y-%m-%d"):
        card = {"date": _et_now().strftime("%Y-%m-%d"), "n": 0, "sight_ok": 0, "dt_agree": 0, "recent": []}
    card["n"] += n
    card["sight_ok"] += sum(1 for r in scored if r["sight_ok"])
    card["dt_agree"] += sum(1 for r in scored if r["dt_agree"])
    card["committed_yes"] = card.get("committed_yes", 0) + sum(1 for r in scored if r.get("committed") is True)
    card["committed_total"] = card.get("committed_total", 0) + sum(1 for r in scored if r.get("committed") is not None)
    card["recent"] = (card.get("recent", []) + results)[-20:]
    card["updated_et"] = _et_now().strftime("%H:%M")
    card["sight_accuracy"] = round(card["sight_ok"] / card["n"], 3) if card["n"] else None
    card["dt_agreement"] = round(card["dt_agree"] / card["n"], 3) if card["n"] else None
    card["commit_rate"] = round(card["committed_yes"] / card["committed_total"], 3) if card.get("committed_total") else None
    SCORECARD.write_text(json.dumps(card, indent=2), encoding="utf-8")

    if new:
        CHECKPOINT.write_text(json.dumps({"last_tick_id": int(new[-1].get("tick_id", last_id))}), encoding="utf-8")
    # Flag a sustained DT drop (>=5 ticks today and agreement < 0.6)
    if card["n"] >= 5 and (card["dt_agreement"] or 1) < 0.6:
        _flag(f"Free-agent DT-agreement low today: {card['dt_agreement']:.0%} over {card['n']} ticks")

    print(json.dumps({"scored_this_fire": n, "fire_sight": sight_rate, "fire_dt": dt_rate,
                      "today_sight_accuracy": card["sight_accuracy"],
                      "today_dt_agreement": card["dt_agreement"], "today_n": card["n"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
