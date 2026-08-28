"""daily_brief.py -- Gamma's twice-daily self-initiated presence brief (J directive 2026-07-22).

THE GAP THIS CLOSES (J, verbatim): "I need to figure out how to turn gamma into a real
person... I can't prompt it over and over... obviously gamma's not doing anything." Gamma
runs 10-20 autonomous fires/day (conductor/kitchen/analyst/autopsy) but has ZERO PROACTIVE
touchpoints -- J only ever meets Gamma when HE prompts it. This is the first one: two short,
first-person, honest voice briefs assembled DETERMINISTICALLY (no LLM, $0) from state files
that already exist, spoken via the existing Kokoro TTS pipeline (setup/tts/, gamma_speak.py's
synthesis path -- extended here with a generic --text-file mode, same model/voice/venv, no new
TTS stack) and delivered as a Discord AUDIO FILE through the discord-bridge outbox (extended
here to carry an optional `file` field -- see discord-bridge.py drain_outbox / _send_file_message).

Modes:
  --mode morning  (Gamma_MorningBrief, 08:45 ET weekdays) -- today-bias.json bias + hypothesis,
                  both kill-switches armed?, top-3 key levels nearest spot, what the overnight
                  conductor shipped (STATUS.md's newest "## [date] ..." section headers).
  --mode eod      (Gamma_EodBrief, 16:20 ET weekdays, scheduled AFTER Gamma_TradeAutopsy 16:15
                  so its output is citable) -- per-account realized P&L today (pnl-statement.json
                  via fill_funnel.trades_pnl_today, the T1 broker-truth source), fills + setups
                  traded, an honest wins/losses one-liner (no sugar), top of tonight's active
                  backlog (queue.md), film-room availability (dojo session-brief for today).
                  TAIL CALL (2026-08-27): after composing the brief text, best-effort rebuilds
                  analysis/trades-enriched.jsonl (setup/scripts/trades_enriched.py, the
                  canonical per-trade ledger) -- same chain, no new scheduled task. Failure
                  there is logged, never breaks the brief (_rebuild_trades_enriched).

Every reader below is FAIL-OPEN: a missing/garbled state file degrades to "no data" phrasing,
never a crash (C7). NO broker imports anywhere in the import chain (fill_funnel / et_clock /
arm_display are pure-stdlib, read-only ledger readers) -- this script never touches Alpaca.
NO LLM calls on the generation path -- pure deterministic string assembly, $0.

Run:  backtest/.venv/Scripts/python.exe setup/scripts/daily_brief.py --mode morning|eod [--date YYYY-MM-DD] [--no-voice]
Task: Gamma_MorningBrief (08:45 ET) / Gamma_EodBrief (16:20 ET) weekdays -- see SCHEDULED-TASKS.md.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
AGG = STATE / "aggressive"
sys.path.insert(0, str(REPO / "setup" / "scripts"))
from et_clock import et_now, et_today_str  # noqa: E402
import fill_funnel as ff  # noqa: E402  -- pure-ledger reader, $0, NO broker imports

TODAY_BIAS_PATH = STATE / "today-bias.json"
KEY_LEVELS_PATH = STATE / "key-levels.json"
PREMARKET_READINESS_PATH = STATE / "premarket-readiness.json"
SAFE_BREAKER_PATH = STATE / "circuit-breaker.json"
BOLD_BREAKER_PATH = AGG / "circuit-breaker.json"
STATUS_MD_PATH = REPO / "automation" / "overnight" / "STATUS.md"
QUEUE_MD_PATH = REPO / "automation" / "overnight" / "queue.md"
TRADE_TODAY_PATH = STATE / "trade-today.json"
TRENDLINE_WATCH_PATH = STATE / "trendline-watch.json"  # WS8 2026-08-01 (trendline_watch.py)
CORE_DECISIONS_PATH = STATE / "core-decisions.jsonl"
FLEET_DIR = STATE / "fleet"
DOJO_BRIEFS_DIR = STATE / "dojo" / "session-briefs"
DISCORD_CFG = STATE / ".discord-config.json"
OUTBOX = STATE / "discord-outbox.jsonl"
BRIDGE_HEARTBEAT = STATE / "discord-bridge-heartbeat.json"

WORD_CAP = 140
BREAKER_DATE_FIELD = {"safe": "last_reset", "bold": "session_id"}


# --------------------------------------------------------------------------- #
# Fail-open readers -- every one degrades to None/[]/"" on any error, never raises.
# --------------------------------------------------------------------------- #

def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


_STATUS_HEADER_RE = re.compile(r"^##\s*\[([^\]]+)\]\s*(.*)$", re.M)


def _status_headers(path: Path, n: int = 3) -> list[str]:
    """Newest n '## [date ...] ...' section headers from STATUS.md, stripped to the text
    after the leading '## ' marker. STATUS.md is newest-first (fresh entries prepended),
    so these are simply the FIRST n matches. Never raises; [] on any read failure."""
    txt = _read_text(path)
    if not txt:
        return []
    out = []
    for m in _STATUS_HEADER_RE.finditer(txt):
        out.append(f"[{m.group(1)}] {m.group(2)}".strip())
        if len(out) >= n:
            break
    return out


_QUEUE_TITLE_RE = re.compile(r"^###\s*(.+)$", re.M)


def _queue_backlog_titles(path: Path, n: int = 2) -> list[str]:
    """First n '### TITLE (...)' headers under queue.md's '## Active backlog' section,
    trimmed to the id/name portion before the parenthetical detail. [] on any failure."""
    txt = _read_text(path)
    if not txt:
        return []
    if "## Active backlog" in txt:
        txt = txt.split("## Active backlog", 1)[1]
    if "## Completed" in txt:
        txt = txt.split("## Completed", 1)[0]
    out = []
    for m in _QUEUE_TITLE_RE.finditer(txt):
        title = m.group(1).strip()
        title = title.split(" (", 1)[0].strip()
        if title:
            out.append(title)
        if len(out) >= n:
            break
    return out


def _first_sentence(text: str, max_chars: int = 200) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
    s = parts[0] if parts else text
    return s[:max_chars].rstrip()


def _nearest_levels(key_levels: Optional[dict], n: int = 3) -> list[dict]:
    if not key_levels:
        return []
    spot = key_levels.get("spot_at_compute")
    levels = key_levels.get("levels") or []
    if not isinstance(levels, list) or spot is None:
        return []
    try:
        ranked = sorted(
            (lv for lv in levels if isinstance(lv, dict) and isinstance(lv.get("price"), (int, float))),
            key=lambda lv: abs(lv["price"] - spot),
        )
    except TypeError:
        return []
    return ranked[:n]


def _breaker_armed_str(breaker: Optional[dict], date_field: str, today: str) -> str:
    """'armed' / 'armed (stale re-arm)' / 'TRIPPED (reason)' / 'unknown' -- mirrors
    open_bell_status.py's _breaker_summary contract (kept terse for the spoken register)."""
    if breaker is None:
        return "unknown"
    if bool(breaker.get("tripped")):
        reason = breaker.get("tripped_reason") or breaker.get("trip_reason") or "unspecified"
        return f"TRIPPED ({reason})"
    raw_date = breaker.get(date_field)
    bdate = str(raw_date)[:10] if raw_date else None
    return "armed" if bdate == today else "armed (stale re-arm)"


def _premarket_readiness_line(day: str, data: Optional[dict]) -> str:
    """PURE. Leads the morning brief with the standing WS2 premarket-readiness verdict
    (built 2026-07-27: J had to ask "are we ready to trade?" after a review missed 3 of 6
    accounts -- the SECOND time that class of miss happened -- and later the same day TV/CDP
    was found dead with nothing flagging it). `premarket_readiness.py` runs standalone at
    09:00 ET and writes automation/state/premarket-readiness.json; this just RENDERS it.

    ORDERING CAVEAT: Gamma_MorningBrief fires 08:45 ET, 15 minutes BEFORE
    Gamma_PremarketReadiness (09:00 ET) -- on a normal morning this degrades to the neutral
    "not yet run" phrasing below until that ordering is revisited. It still reports the real
    verdict on any day the gate happened to run earlier (manual re-run, a later brief re-fire).
    Fail-open (C7): missing/stale/garbled -> a neutral line, never a crash -- the brief must
    compose exactly as before even if this file was never written."""
    if not data:
        return "Premarket readiness check: not yet run today."
    checked_day = str(data.get("ts_et", ""))[:10]
    if checked_day != day:
        return "Premarket readiness check: not yet run today (fires 09:00 ET)."
    verdict = str(data.get("verdict", "UNKNOWN")).upper()
    if verdict == "GREEN":
        return "Premarket readiness check: GREEN, every trading-critical system checked out."
    reds = data.get("reds") or []
    if not reds:
        return f"Premarket readiness check: {verdict}."
    checks = data.get("checks") or []
    head = next((c.get("detail") for c in checks if c.get("name") == reds[0]), reds[0])
    return f"Premarket readiness check: {verdict} -- {head}."


def _ribbon_scope_note(day: str) -> Optional[dict]:
    """RIBBON-SESSION-SCOPE-DIVERGENCE Lane-A wiring, morning-brief half (queue.md
    2026-07-23, PART-2-RESOLVED remainder). The morning brief runs premarket (08:45 ET) --
    `day`'s own intraday bars don't exist yet, so this reports on the most recent day that
    DOES have data (typically yesterday's open) via
    backtest/tools/ribbon_scope_compare.latest_available_day()/compare_at(): does the
    engine's RTH-scope ribbon agree with the full extended-hours (J's-chart-validated) ribbon
    at that day's open? Returns None (never fabricated) on any import/data failure, or when
    that day's open bar hasn't warmed up in either scope -- degrades the brief to silence on
    this point, never a crash or a guessed value."""
    try:
        backtest_dir = REPO / "backtest"
        if str(backtest_dir) not in sys.path:
            sys.path.insert(0, str(backtest_dir))
        from tools import ribbon_scope_compare as rsc  # noqa: E402 -- lazy, mirrors dojo/session.py
    except ImportError:
        return None
    try:
        prior = rsc.latest_available_day(before=day)
        if prior is None:
            return None
        cmp = rsc.compare_at(prior, f"{prior} 09:30:00")
    except Exception:  # noqa: BLE001 -- fail-open, never blocks the brief (C7)
        return None
    if not cmp.rth_stack or not cmp.eth_stack:
        return None
    return {"day": prior, "agree": cmp.agree, "rth_stack": cmp.rth_stack,
            "eth_stack": cmp.eth_stack, "max_ema_diff": cmp.max_ema_diff}


def _dojo_brief_info(day: str) -> dict:
    path = DOJO_BRIEFS_DIR / f"{day}.md"
    if not path.exists():
        return {"exists": False, "n_exhibits": 0}
    txt = _read_text(path)
    n = len(re.findall(r"^## EXHIBIT", txt, re.M))
    return {"exists": True, "n_exhibits": n}


def _setups_traded_today(day: str) -> list[str]:
    """Distinct setups that actually EXECUTED for `day` -- never the merely-scored ones.

    BUG FIX (2026-07-22 smoke): the first version collected row['setup'] from every decision
    row, but core rows carry the SCORED setup name even on HOLD ticks (the 07-22 smoke brief
    claimed 'BULLISH_RECLAIM_RIDE_THE_RIBBON' traded when the real fills were
    vwap_continuation via the extra_exec lane). A brief that misreports what traded is worse
    than no brief. Executed truth per lane: core rows -> extra_exec[].setup where action is
    PLACED, or row['setup'] only on ENTER_* verdicts; fleet rows -> row['setup'] only when
    the row records a real placement (action ENTER/PLACED or a placement/broker block).
    Bounded tail read; [] on any failure -- never blocks the brief."""
    setups: set[str] = set()
    paths = [CORE_DECISIONS_PATH]
    try:
        paths += sorted(FLEET_DIR.glob("*/decisions.jsonl"))
    except OSError:
        pass
    for p in paths:
        is_core = p == CORE_DECISIONS_PATH
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[-4000:]
        except OSError:
            continue
        for ln in lines:
            if day not in ln:
                continue
            try:
                row = json.loads(ln)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(row, dict):
                continue
            if is_core:
                for e in row.get("extra_exec") or []:
                    if isinstance(e, dict) and e.get("action") == "PLACED":
                        s = e.get("setup")
                        if isinstance(s, str) and s.strip():
                            setups.add(s.strip())
                if str(row.get("verdict", "")).startswith("ENTER"):
                    s = row.get("setup")
                    if isinstance(s, str) and s.strip():
                        setups.add(s.strip())
            else:
                placed = (
                    str(row.get("action", "")).upper() in ("ENTER", "PLACED")
                    or isinstance(row.get("placement"), dict)
                    or isinstance(row.get("broker"), dict)
                )
                if placed:
                    s = row.get("setup")
                    if isinstance(s, str) and s.strip():
                        setups.add(s.strip())
    return sorted(setups)


def truncate_to_word_cap(text: str, cap: int = WORD_CAP) -> str:
    words = text.split()
    if len(words) <= cap:
        return text
    return " ".join(words[:cap]).rstrip(".,;: ") + "."


# --------------------------------------------------------------------------- #
# MORNING -- pure composition (all inputs already-loaded, testable from fixtures).
# --------------------------------------------------------------------------- #

def gather_morning_facts(
    day: str,
    *,
    today_bias: Optional[dict] = None,
    key_levels: Optional[dict] = None,
    safe_breaker: Optional[dict] = None,
    bold_breaker: Optional[dict] = None,
    status_headers: Optional[list[str]] = None,
    ribbon_scope: Optional[dict] = None,
    premarket_readiness: Optional[dict] = None,
) -> dict:
    return {
        "day": day,
        "bias": (today_bias or {}).get("bias") or "unknown",
        "bias_reason": _first_sentence((today_bias or {}).get("bias_note", "")) or "no premarket read on file",
        "levels": _nearest_levels(key_levels),
        "safe_breaker": _breaker_armed_str(safe_breaker, BREAKER_DATE_FIELD["safe"], day),
        "bold_breaker": _breaker_armed_str(bold_breaker, BREAKER_DATE_FIELD["bold"], day),
        "overnight_headers": status_headers or [],
        "ribbon_scope": ribbon_scope,
        "readiness_line": _premarket_readiness_line(day, premarket_readiness),
    }


def _crypto_overnight_line() -> str:
    """One spoken sentence on what the crypto twin did on ITS OWN signal overnight.

    J's standing question is "did Gamma make money on crypto" -- a repeated question is a
    missing instrument (OP-33e), so it goes in the brief rather than waiting to be asked.
    Reports the ORGANIC bucket only: forced coverage-battery trades measure spread and random
    walk, and quoting them as performance is the exact overstatement this whole surface exists
    to prevent. Fail-open -- the brief must compose even if the twin's journal is unreadable.
    """
    try:
        import crypto_twin_pnl as ctp
        trips = ctp.reconstruct_trips()
        s = ctp.summarize([t for t in trips if t["bucket"] == "ORGANIC"])
        if not s["n"]:
            return ("On crypto, the twin has not yet taken a trade on its own signal "
                    "overnight -- no organic round trips to report.")
        verb = "up" if s["total_pct"] > 0 else "down"
        return (f"On crypto, I traded my own signal {s['n']} times overnight: "
                f"{s['win_rate']:.0f} percent win rate, {verb} "
                f"{abs(s['total_pct']):.2f} percent. Paper, and not SPY evidence.")
    except Exception:  # noqa: BLE001 -- never let a telemetry read break the brief
        return "Crypto twin P&L unavailable this morning -- worth a look."


def _trendline_morning_line() -> str:
    """WS8 (2026-08-01): ONE lean spoken sentence from the trendline watch surface
    (automation/state/trendline-watch.json, producer backtest/autoresearch/
    trendline_watch.py -- "N active trendlines, nearest at X" + last break).
    The producer fires RTH-only (Gamma_Trendlines), so at 08:45 the line carries
    its own as-of stamp from yesterday's close -- honest, never implied-fresh.
    Fail-open (C7): a missing/garbled watch file degrades to explicit no-data
    phrasing, never a crash."""
    try:
        d = _read_json(TRENDLINE_WATCH_PATH)
        line = (d or {}).get("premarket_line")
        if isinstance(line, str) and line.strip():
            return line.strip()
        return "Trendlines: no watch surface on file yet."
    except Exception:  # noqa: BLE001 -- never let a telemetry read break the brief
        return "Trendlines: watch surface unreadable this morning."


def compose_morning_text(facts: dict) -> str:
    lines = [f"Gamma here. Morning brief, {facts['day']}."]
    # LEADS with the readiness verdict (WS2, 2026-07-27): "ready to trade?" must never again
    # require J to ask -- ahead of bias, on purpose, same precedent as the EOD liveness alarm.
    lines.append(facts.get("readiness_line") or "Premarket readiness check: not yet run today.")
    lines.append(f"Bias is {facts['bias']}: {facts['bias_reason']}")
    levels = facts.get("levels") or []
    if levels:
        lvl_txt = "; ".join(f"{lv['price']:.2f} {lv.get('type', '?')}" for lv in levels)
        lines.append(f"Nearest levels: {lvl_txt}.")
    else:
        lines.append("No fresh key levels on file.")
    lines.append(_trendline_morning_line())
    lines.append(f"Kill switches: Safe {facts['safe_breaker']}, Bold {facts['bold_breaker']}.")
    lines.append(_crypto_overnight_line())
    overnight = facts.get("overnight_headers") or []
    if overnight:
        lines.append("Overnight I shipped: " + "; ".join(overnight) + ".")
    else:
        lines.append("Quiet overnight -- nothing shipped.")
    rs = facts.get("ribbon_scope")
    if rs and not rs.get("agree"):
        diff = rs.get("max_ema_diff")
        diff_txt = f"${diff:.2f}" if isinstance(diff, (int, float)) else "an unknown amount"
        lines.append(
            f"Heads up: at {rs['day']}'s open my ribbon read {rs['rth_stack']} while the full "
            f"extended-hours chart read {rs['eth_stack']}, {diff_txt} apart -- worth a gap "
            f"check this morning."
        )
    return truncate_to_word_cap(" ".join(lines))


# --------------------------------------------------------------------------- #
# EOD -- pure composition.
# --------------------------------------------------------------------------- #

def gather_eod_facts(
    day: str,
    *,
    pnl: Optional[dict] = None,
    trade_today: Optional[dict] = None,
    setups: Optional[list[str]] = None,
    queue_titles: Optional[list[str]] = None,
    dojo_info: Optional[dict] = None,
) -> dict:
    pnl = pnl or {}
    by_arm = pnl.get("by_arm") or []
    active_arms = [a for a in by_arm if a.get("n_round_trips")]
    total_pnl = pnl.get("total_pnl")
    return {
        "day": day,
        "pnl_source": pnl.get("source") or "no P&L source found",
        "total_pnl": total_pnl,
        "by_arm": active_arms,
        "n_filled": (trade_today or {}).get("spy_fills_today"),
        "n_unfilled": (trade_today or {}).get("placed_not_filled_today"),
        "setups": setups or [],
        "queue_titles": queue_titles or [],
        "dojo": dojo_info or {"exists": False, "n_exhibits": 0},
    }


def _pnl_oneliner(total_pnl) -> str:
    if total_pnl is None:
        return "P&L unknown -- no ledger entry for today"
    if abs(total_pnl) < 0.005:
        return "flat -- dead even"
    sign = "up" if total_pnl > 0 else "down"
    return f"{sign} ${abs(total_pnl):.0f}"


def _liveness_alarm(day: str) -> Optional[str]:
    """LEAD-LINE alarm when the engine did not run on a day the market was open.

    The 2026-07-24 incident: machine off, zero ticks, and NOTHING said so -- engine-health.json
    read GREEN because its checks all degrade to "(market closed -- quiet OK)". The brief is the
    one surface that reaches J off-box, so the alarm leads here, ahead of P&L. Fail-open: any
    import/read problem returns None and the brief composes exactly as before (C7)."""
    try:
        from engine_liveness_check import alarm_line, check_day  # noqa: PLC0415 -- optional dep
        return alarm_line(check_day(day))
    except Exception:  # noqa: BLE001 -- a broken check must never break the brief
        return None


def _blind_alarm(day: str) -> Optional[str]:
    """LEAD-LINE alarm when the engine traded with ZERO key levels loaded (2026-07-30).

    Sibling of _liveness_alarm and additive to it. On 2026-07-30 the engine ran a full 772
    ticks -- so the liveness alarm above stayed silent, correctly -- but every one of those
    ticks carried `levels_active: []`, and the engine silently fell through to its worst
    entry mode and produced 11 ENTER_BEAR verdicts at the low of the day. "I ran today" and
    "I could see today" are different claims; this is the second one. J must hear it BEFORE
    P&L, because a blind day's P&L means nothing. Fail-open: any import/read problem returns
    None and the brief composes exactly as before (C7)."""
    try:
        from levels_blind_check import (alarm_line, check_day,  # noqa: PLC0415 -- optional dep
                                        check_levels_file)
        rows = check_day(day)
        file_res = None
        try:
            from et_clock import et_now  # noqa: PLC0415
            file_res = check_levels_file(et_now().replace(tzinfo=None))
        except Exception:  # noqa: BLE001 -- the file half is context only, never required
            file_res = None
        return alarm_line(rows, file_res)
    except Exception:  # noqa: BLE001 -- a broken check must never break the brief
        return None


def compose_eod_text(facts: dict) -> str:
    lines = [f"Gamma here. End of day, {facts['day']}."]
    alarm = _liveness_alarm(facts["day"])
    if alarm:
        # Ahead of P&L on purpose: "$0 today" and "the engine was dead today" must never sound alike.
        lines.append(alarm)
    blind = _blind_alarm(facts["day"])
    if blind:
        # Also ahead of P&L: a day traded with no levels is not a P&L result, it is an outage.
        lines.append(blind)
    by_arm = facts.get("by_arm") or []
    if by_arm:
        arm_txt = "; ".join(
            f"{a['arm']} {'up' if a['realized_pnl'] >= 0 else 'down'} ${abs(a['realized_pnl']):.0f} "
            f"on {a['n_round_trips']} round trips" for a in by_arm
        )
        lines.append(f"By account: {arm_txt}.")
    else:
        lines.append("No account traded today.")
    lines.append(f"Overall I was {_pnl_oneliner(facts.get('total_pnl'))}. No sugar-coating either way.")
    nf = facts.get("n_filled")
    if nf is not None:
        lines.append(f"{nf} fill(s), {facts.get('n_unfilled') or 0} placed-not-filled.")
    setups = facts.get("setups") or []
    if setups:
        lines.append("Setups traded: " + ", ".join(setups) + ".")
    queue_titles = facts.get("queue_titles") or []
    if queue_titles:
        lines.append("Tonight's top of the backlog: " + "; ".join(queue_titles) + ".")
    dojo = facts.get("dojo") or {}
    if dojo.get("exists"):
        lines.append(f"Film room is ready -- {dojo.get('n_exhibits', 0)} exhibits queued if you want to walk them.")
    return truncate_to_word_cap(" ".join(lines))


def build_caption(mode: str, day: str, facts: dict) -> str:
    """3-line Discord text caption accompanying the audio attachment -- NOT the spoken
    script; a glanceable summary for anyone who can't/won't tap play."""
    if mode == "morning":
        line1 = f"GAMMA MORNING BRIEF -- {day}"
        line2 = f"Bias: {facts['bias']} | Safe: {facts['safe_breaker']} | Bold: {facts['bold_breaker']}"
        line3 = f"{len(facts.get('overnight_headers') or [])} overnight fire(s) shipped"
    else:
        line1 = f"GAMMA EOD BRIEF -- {day}"
        line2 = f"P&L: {_pnl_oneliner(facts.get('total_pnl'))} | {facts.get('n_filled') or 0} fill(s)"
        dojo = facts.get("dojo") or {}
        line3 = f"Film room: {dojo.get('n_exhibits', 0)} exhibits ready" if dojo.get("exists") else "Film room: none today"
    return f"{line1}\n{line2}\n{line3}"


# --------------------------------------------------------------------------- #
# Voice render -- shells out to the EXISTING Kokoro pipeline (setup/.tts-venv,
# gamma_speak.py's --text-file generic mode; same model/voice, no new TTS stack).
# --------------------------------------------------------------------------- #

def render_voice(text: str, out_path: Path) -> "tuple[bool, str]":
    tts_py = REPO / "setup" / ".tts-venv" / "Scripts" / "python.exe"
    speak = REPO / "setup" / "scripts" / "gamma_speak.py"
    if not tts_py.exists() or not speak.exists():
        return False, f"TTS venv or script missing ({tts_py} / {speak})"
    tmp_txt = out_path.with_suffix(".txt")
    try:
        tmp_txt.write_text(text, encoding="utf-8")
    except OSError as exc:
        return False, f"could not write temp text file: {exc}"
    try:
        r = subprocess.run(
            [str(tts_py), str(speak), "--text-file", str(tmp_txt), "--out", str(out_path)],
            capture_output=True, text=True, timeout=300,
            creationflags=(0x08000000 if sys.platform == "win32" else 0),
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"tts subprocess failed: {exc}"
    finally:
        try:
            tmp_txt.unlink()
        except OSError:
            pass
    ok = r.returncode == 0 and out_path.exists()
    msg = (r.stdout or r.stderr or "").strip()
    return ok, msg


# --------------------------------------------------------------------------- #
# Discord delivery -- outbox pattern (discord-bridge.py drains it; extended with
# an optional `file` field for attachment sends -- see that module's drain_outbox).
# --------------------------------------------------------------------------- #

def _load_user_mention() -> str:
    try:
        cfg = json.loads(DISCORD_CFG.read_text(encoding="utf-8-sig"))
        uid = cfg.get("user_id")
        return f"<@{uid}> " if uid else ""
    except Exception:  # noqa: BLE001
        return ""


def bridge_is_alive(max_age_s: int = 90) -> bool:
    hb = _read_json(BRIDGE_HEARTBEAT)
    if not hb or not hb.get("last_tick_at"):
        return False
    try:
        ts = str(hb["last_tick_at"]).rstrip("Z")
        last = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - last).total_seconds()
        return 0 <= age <= max_age_s
    except Exception:  # noqa: BLE001
        return False


def queue_discord_delivery(content: str, wav_path: Optional[Path], *, source: str) -> dict:
    row = {"queued_at": datetime.now().isoformat(timespec="seconds"), "content": content, "source": source}
    if wav_path is not None:
        row["file"] = str(wav_path)
    try:
        with OUTBOX.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        return {"queued": False, "error": str(exc)}
    return {"queued": True}


def _rebuild_prod_shadow() -> None:
    """Best-effort tail call (2026-08-28, TASK C1): rebuild the PROD-1 shadow
    (analysis/prod-shadow/{ledger,summary}.json via setup/scripts/prod_shadow.py) right
    after trades_enriched so it always runs against the freshest source ledger. Fail-open
    (C7): any failure here must never break the brief itself -- logged, not raised. No new
    scheduled task, placed at the END of the eod chain per instruction."""
    try:
        import prod_shadow as psh  # noqa: PLC0415 -- lazy, mirrors other optional deps above
        result = psh.run(write=True)
        fh = result["summary"]["full_history"]
        print(f"[daily_brief:eod] prod_shadow rebuilt: {len(result['ledger'])} ledger rows, "
              f"full-history net={fh.get('total_pnl_net')} over {fh.get('n_trading_days')} days")
    except Exception as exc:  # noqa: BLE001 -- never let this break the EOD brief
        print(f"[daily_brief:eod] prod_shadow rebuild FAILED (non-fatal): "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)


def _rebuild_trades_enriched() -> None:
    """Best-effort tail call (2026-08-27): rebuild analysis/trades-enriched.jsonl, the
    canonical per-trade ledger (setup/scripts/trades_enriched.py), at the end of the same
    16:20 ET eod chain that already reads fill_funnel's T1 broker-truth. Deterministic,
    $0, idempotent full rebuild, no broker imports. Fail-open (C7): any failure here must
    never break the brief itself -- logged, not raised. Placed at the END of the eod
    branch per instruction (smallest diff, no new scheduled task)."""
    try:
        import trades_enriched as te  # noqa: PLC0415 -- lazy, mirrors other optional deps above
        result = te.rebuild(REPO)
        meta = result["meta"]
        ok = te.run_verification(result["rows"], quiet=True)
        print(f"[daily_brief:eod] trades_enriched rebuilt: {meta['n_rows']} rows, "
              f"ctx_match_rate={meta['ctx_match_rate']}, verify={'PASS' if ok else 'FAIL'}")
    except Exception as exc:  # noqa: BLE001 -- never let this break the EOD brief
        print(f"[daily_brief:eod] trades_enriched rebuild FAILED (non-fatal): "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["morning", "eod"], required=True)
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: today ET)")
    ap.add_argument("--no-voice", action="store_true", help="text-only dry run: skip TTS + delivery")
    args = ap.parse_args()

    day = args.date or et_today_str()

    if args.mode == "morning":
        facts = gather_morning_facts(
            day,
            today_bias=_read_json(TODAY_BIAS_PATH),
            key_levels=_read_json(KEY_LEVELS_PATH),
            safe_breaker=_read_json(SAFE_BREAKER_PATH),
            bold_breaker=_read_json(BOLD_BREAKER_PATH),
            status_headers=_status_headers(STATUS_MD_PATH, n=3),
            ribbon_scope=_ribbon_scope_note(day),
            premarket_readiness=_read_json(PREMARKET_READINESS_PATH),
        )
        text = compose_morning_text(facts)
    else:
        try:
            pnl = ff.trades_pnl_today(day, repo=REPO)
        except Exception as exc:  # noqa: BLE001 -- fail-open, never crash the brief
            pnl = {"error": str(exc)}
        facts = gather_eod_facts(
            day,
            pnl=pnl,
            trade_today=_read_json(TRADE_TODAY_PATH),
            setups=_setups_traded_today(day),
            queue_titles=_queue_backlog_titles(QUEUE_MD_PATH, n=2),
            dojo_info=_dojo_brief_info(day),
        )
        text = compose_eod_text(facts)
        _rebuild_trades_enriched()
        _rebuild_prod_shadow()

    caption = build_caption(args.mode, day, facts)
    n_words = len(text.split())
    print(f"[daily_brief:{args.mode}] {day} ({n_words} words)\n{text}\n")
    print(f"caption:\n{caption}\n")

    if args.no_voice:
        print("[daily_brief] --no-voice: text-only dry run, no TTS/delivery attempted")
        return 0

    wav_path = STATE / f"gamma-voice-brief-{day.replace('-', '')}-{args.mode}.wav"
    ok, msg = render_voice(text, wav_path)
    mention = _load_user_mention()

    if not ok:
        print(f"[daily_brief:{args.mode}] VOICE RENDER FAILED -- falling back to a text-only "
              f"Discord brief (J's fallback rule: say so, don't go silent): {msg}", file=sys.stderr)
        fallback = f"{mention}{caption}\n\n(voice unavailable this fire: {msg[:200]})\n\n{text}"
        result = queue_discord_delivery(fallback[:1900], None, source=f"daily_brief_{args.mode}_text_fallback")
        if result.get("queued"):
            print("[daily_brief] fallback TEXT brief queued to outbox")
            return 1
        print(f"[daily_brief] fallback queue FAILED: {result.get('error')}", file=sys.stderr)
        return 1

    print(f"[daily_brief:{args.mode}] voice rendered OK: {msg}")
    alive = bridge_is_alive()
    result = queue_discord_delivery(mention + caption, wav_path, source=f"daily_brief_{args.mode}")
    if result.get("queued"):
        status = "bridge is LIVE -- should drain within ~15s" if alive else \
                 "bridge NOT detected alive -- queued, will deliver when it next starts"
        print(f"[daily_brief:{args.mode}] queued to Discord outbox with audio attachment ({status})")
        return 0
    print(f"[daily_brief:{args.mode}] OUTBOX QUEUE FAILED: {result.get('error')}", file=sys.stderr)
    return 1


# --------------------------------------------------------------------------- #
# Crash guard -- 2026-08-08 delivery-chain audit finding.
#
# ROOT CAUSE: Gamma_MorningBrief/Gamma_EodBrief launch via
# wscript -> run_exe_hidden.vbs -> pythonw.exe daily_brief.py, and run_exe_hidden.vbs calls
# `shell.Run cmd, 0, False` -- fire-and-forget (no wait) with NO stdout/stderr redirection.
# Every individual state-file reader in this module is already fail-open (never raises), but
# nothing wrapped main() itself: an uncaught exception anywhere in its call graph (a future
# regression in a compose/gather function, a bad edit, an environment change) would vanish
# with ZERO trace -- no log, no Discord signal -- contradicting install-daily-brief.ps1's own
# documented "fails open ... never silent" guarantee. This is the same masked-exit class
# self_check.py already monitors for run_cmd_hidden.py/run-ps1-hidden.ps1-launched tasks
# (RUN-CMD-HIDDEN / RUN-PS1-HIDDEN MASKED EXIT), just via a third, previously-uncovered
# wrapper. It is also the reason 2026-07-30 -- a weekday when the box was confirmed awake and
# Task Scheduler confirmed healthy in both the 06:45 and 14:20 MT windows (dozens of sibling
# tasks fired normally that exact minute), yet BOTH briefs produced no artifact at all -- is
# forensically unsolvable: nothing anywhere records what daily_brief.py did that day.
#
# Fix: wrap main() in a last-resort guard that logs any uncaught exception to a dedicated
# file AND makes a best-effort attempt to push a short CRASHED alert through the SAME outbox
# mechanism the rest of this file already uses -- so a future crash is at minimum visible
# same-day, never silent. main() itself is unchanged; every existing test/behavior is
# unaffected. Guard test: backtest/tests/test_daily_brief.py::test_run_guarded_*.
# --------------------------------------------------------------------------- #

CRASH_LOG_PATH = STATE / "logs" / "daily-brief.stderr.log"


def _log_crash(mode: str, exc: BaseException) -> None:
    """Best-effort: write the traceback to disk, then queue a short Discord alert. Every
    step is individually guarded -- the crash guard itself must never raise (that would
    just be a second, more embarrassing silent failure)."""
    import traceback
    try:
        CRASH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CRASH_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"\n--- {datetime.now().isoformat(timespec='seconds')} mode={mode} ---\n")
            traceback.print_exception(type(exc), exc, exc.__traceback__, file=fh)
    except OSError:
        pass
    try:
        queue_discord_delivery(
            f"GAMMA DAILY BRIEF CRASHED ({mode}): {type(exc).__name__}: {exc}"[:1900],
            None, source=f"daily_brief_{mode}_crash",
        )
    except Exception:  # noqa: BLE001 -- the crash guard itself must never raise
        pass


def run_guarded(argv: "list[str] | None" = None) -> int:
    """__main__ entry point: run main(), and if ANYTHING escapes it uncaught, log + alert
    instead of vanishing into run_exe_hidden.vbs's discarded stdout/stderr (see module
    comment above). `argv` is accepted only so tests can force a --mode label without
    touching real sys.argv; production always calls this with no argument."""
    try:
        return main()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 -- last-resort net, must not re-raise
        args = argv if argv is not None else sys.argv[1:]
        mode = "unknown"
        for i, a in enumerate(args):
            if a == "--mode" and i + 1 < len(args):
                mode = args[i + 1]
        _log_crash(mode, exc)
        return 1


if __name__ == "__main__":
    sys.exit(run_guarded())
