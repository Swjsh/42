"""gamma_home.py - THE command center. One self-contained HTML page, no server needed.

WHY THIS EXISTS (read markdown/planning/GAMMA-WORKER.md "Why the three prior
embodiments didn't stick" before touching this file)
------------------------------------------------------------------------------
Five presence surfaces have been built for J: the Next.js "Trade House"
dashboard, the Electron gamma-companion (:4317), the Discord voicebot, the
GAMMA HQ terminal, and the Next.js /gamma app. Their own post-mortem names the
common thread: "presence kept getting solved as an ADD-ON channel instead of
upgrading the ONE surface J might actually open unprompted."

This file is NOT a sixth channel. It is the consolidation, and it is only
justified because it RETIRES surfaces rather than adding one:
  * localhost:3000/gamma was verified DEAD on 2026-08-19 (no response) despite
    Gamma_DashboardKeepalive existing - a home base that needs a Node server
    babysat by a scheduled task is a home base that is offline when J looks.
  * J's own stated preference (2026-08-19): a localhost HTML page, "more
    editable and we can make it look how I want it to look" - the exact pattern
    he had just built himself in journal_calendar.py.

So: one Python generator -> one self-contained .html file. Double-clickable,
diffable, restyleable, and it cannot be "down".

ZERO DUPLICATED LOGIC (the state-librarian contract)
  * Presence/state/clocks/wants come from `gamma_hq.py --json` - the same pure
    helpers the terminal renders from. This page never recomputes them.
  * The calendar comes from `analysis/journal/calendar-data.json`, written by
    journal_calendar.py. This page never re-derives P&L.
  * The answers below come from live state files, each shown WITH its source
    path and its age.

FAIL LOUD, NEVER FABRICATE (OP-33 / C7)
  Any section whose source is missing or stale renders a visible amber "NO
  DATA" card naming the file it wanted. Nothing is invented, nothing silently
  degrades to a plausible-looking default.

USAGE
  python setup/scripts/gamma_home.py            # write analysis/home/index.html
  python setup/scripts/gamma_home.py --open     # ...and open it
  python setup/scripts/gamma_home.py --quiet    # no stdout except the path
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import et_clock  # noqa: E402 -- DST-aware ET stamp for source mtimes (spec 10.2)

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
OUT_HTML = REPO / "analysis" / "home" / "index.html"
# Dual-write target (spec sec 1's "one architectural tension"): identical bytes to
# OUT_HTML, but served by gamma-companion (:4317) instead of opened as a file. The
# server injects <meta name="gamma-token"> into THIS copy only (server.js's
# serveStatic), which is what lets the page's own JS tell file:// (snapshot mode,
# no network) apart from served-over-http (live mode, 1s poll). Never hand-edit --
# same generator, same OUT_HTML.gitignore reasoning, see .gitignore.
COMPANION_HTML = REPO / "gamma-companion" / "public" / "cockpit.html"
COMPANION_JSON = REPO / "gamma-companion" / "public" / "payload.json"

# OP-27 L41 / C8: never let a headless (pythonw) scheduled task flash a conhost window.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

CALENDAR_JSON = REPO / "analysis" / "journal" / "calendar-data.json"
CALENDAR_HTML = REPO / "analysis" / "journal" / "calendar.html"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"
SIGNATURE_MD = REPO / "analysis" / "winner-autopsies" / "SIGNATURE.md"
# Written by setup/scripts/gamma_cost_meter.py -- today + trailing-7d Claude Code /
# MiniMax / Groq spend, broken down by origin where the data supports it. Every
# figure inside already carries its own {"usd","known","coverage","method"}
# provenance (see that module's docstring) -- this page never recomputes or
# reformats a dollar number, only renders what the meter already decided.
COST_METER_JSON = STATE / "cost-meter.json"

# A source older than this is shown with an amber staleness badge rather than
# presented as current. Generous on purpose: this page is read after hours too.
STALE_HOURS = 24.0

# A want unverified for longer than this is shown with a badge, not as fact.
WANT_STALE_DAYS = 14


# ---------------------------------------------------------------- helpers

_MD_NOISE = re.compile(r"(\*\*|`|^\s*>+\s*|^#+\s*|^\s*[-*]\s+|(?<![\w.])_(?=\w)|(?<=\w)_(?![\w.]))")


def _clean(s) -> str:
    """Strip markdown so a doc line reads as a sentence on a card.

    The sources are human/agent-authored markdown. Rendering them raw leaked
    `> **Signal J wakes to (OP-25).**` and `_Generated ... ._` onto the page.
    """
    if not isinstance(s, str):
        s = str(s)
    return re.sub(r"\s+", " ", _MD_NOISE.sub("", s)).strip()


def _clip(s: str, cap: int = 240) -> str:
    """Cut to a sentence boundary near `cap`, never mid-word."""
    s = _clean(s)
    if len(s) <= cap:
        return s
    cut = s[:cap]
    stop = max(cut.rfind(". "), cut.rfind("; "), cut.rfind(" -- "))
    if stop > cap * 0.5:
        return cut[:stop + 1].strip()
    return cut.rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _claim_of(x) -> str:
    """Pull the human claim out of a falsifiable-prediction row.

    today-bias.json stores these as dicts (and sometimes as JSON strings);
    dumping them raw put `{"claim": "...", "trigger_window": ...` on the page.
    """
    if isinstance(x, str):
        s = x.strip()
        if s.startswith("{"):
            try:
                x = json.loads(s)
            except ValueError:
                return _clean(s)
        else:
            return _clean(s)
    if isinstance(x, dict):
        claim = x.get("claim") or x.get("prediction") or x.get("hypothesis") or ""
        win = x.get("trigger_window") or ""
        return _clean(claim) + (" (%s)" % _clean(win) if win else "")
    return _clean(x)


GAMMA_WANTS = STATE / "gamma-wants.json"


def _wants_full() -> list:
    """Full-text wants, straight from source.

    gamma_hq.py runs every want through `_sanitize_line(max_len=120)` because an
    80-column ANSI window has to bound one bad field or the layout blows out.
    A web page has no such constraint, and inheriting it cut every want mid-
    sentence -- J (2026-08-19) on want #2: "it's cut off. I don't know what it
    is." So the page reads the registry directly and falls back to the
    librarian's truncated copy only if the file is unreadable.
    """
    try:
        raw = json.loads(GAMMA_WANTS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = raw.get("wants") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []
    rows = []
    for w in items:
        if isinstance(w, dict):
            text = str(w.get("text", "")).strip()
            pri = w.get("priority", 99)
            verified = str(w.get("verified_at", "")).strip()
        else:
            text, pri, verified = str(w).strip(), 99, ""
        if not text:
            continue
        # STALENESS BADGE (2026-08-20). Two wants sat on this page for weeks while
        # being factually wrong. A want is a claim; an unverified claim gets flagged
        # rather than presented as current.
        stale = True
        if verified:
            try:
                stale = (datetime.now() - datetime.strptime(verified, "%Y-%m-%d")).days > WANT_STALE_DAYS
            except ValueError:
                stale = True
        rows.append({"priority": pri, "text": _clean(text),
                     "verified_at": verified, "stale": stale})
    rows.sort(key=lambda r: r["priority"])
    return rows[:3]


REGISTRY = STATE / "worker-registry.json"


def _rows(p: Path) -> int:
    try:
        return sum(1 for l in p.open(encoding="utf-8", errors="replace") if l.strip())
    except OSError:
        return 0


def _age_h(p: Path):
    try:
        return (datetime.now() - datetime.fromtimestamp(p.stat().st_mtime)).total_seconds() / 3600.0
    except OSError:
        return None


def _mtime_et(p: Path):
    """Absolute ET timestamp from a file's own mtime (spec COCKPIT-DESIGN-
    SPEC-2026-09-03.md 10.2: Answers rows need "a real age (wire
    sources[0].mtime -> data-stamp; never 'unknown age' when the source
    exists)"). `age_h` above is a build-time relative number this same meta
    dict already carried; this is the absolute stamp the client's own
    paintAge() timer needs to keep ticking after the page loads. Never
    raises -- None when the file cannot be stat'd."""
    try:
        return et_clock.et_now(
            now_utc=datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        ).replace(microsecond=0).isoformat()
    except OSError:
        return None


def _load_json(p: Path):
    """Return (data, meta). data is None when the source cannot be trusted."""
    meta = {"path": p.relative_to(REPO).as_posix() if str(p).startswith(str(REPO)) else str(p),
            "age_h": _age_h(p), "mtime_et": _mtime_et(p), "ok": False}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        meta["ok"] = True
        return data, meta
    except (OSError, ValueError) as e:
        meta["error"] = str(e)[:160]
        return None, meta


def _hq_json() -> tuple:
    """The state librarian. Same helpers gamma_hq's terminal renders from."""
    meta = {"path": "setup/scripts/gamma_hq.py --json", "age_h": 0.0, "ok": False}
    try:
        r = subprocess.run(
            [sys.executable, str(REPO / "setup" / "scripts" / "gamma_hq.py"), "--json"],
            cwd=str(REPO), capture_output=True, text=True, timeout=180,
            encoding="utf-8", errors="replace", creationflags=NO_WINDOW,
        )
        if r.returncode == 0 and r.stdout.strip():
            meta["ok"] = True
            return json.loads(r.stdout), meta
        meta["error"] = (r.stderr or "exit %d" % r.returncode)[:160]
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        meta["error"] = str(e)[:160]
    return None, meta


def _latest_status() -> tuple:
    """Newest STATUS.md entry: (verdict, headline, body_first_para)."""
    meta = {"path": "automation/overnight/STATUS.md", "age_h": _age_h(STATUS_MD),
            "mtime_et": _mtime_et(STATUS_MD), "ok": False}
    try:
        text = STATUS_MD.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        meta["error"] = str(e)[:160]
        return None, meta
    m = re.search(r"^##\s*(\[[^\]]*\])\s*(.*)$", text, re.MULTILINE)
    if not m:
        meta["error"] = "no '## [ts]' heading found"
        return None, meta
    head = m.group(2).strip()
    verdict = "INFO"
    for v in ("RED", "YELLOW", "GREEN", "OK"):
        if re.match(r"^%s\b" % v, head) or head.startswith(v):
            verdict = v
            break
    body = ""
    for line in text[m.end():].splitlines():
        line = line.strip()
        if line.startswith("##"):
            break
        if line and not line.startswith("<!--"):
            body = line
            break
    meta["ok"] = True
    return {"verdict": verdict, "stamp": m.group(1).strip("[]"),
            "headline": _clip(head, 200), "body": _clip(body, 260)}, meta


def _signature_lines(n: int = 6) -> tuple:
    meta = {"path": "analysis/winner-autopsies/SIGNATURE.md", "age_h": _age_h(SIGNATURE_MD), "ok": False}
    try:
        raw = SIGNATURE_MD.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        meta["error"] = str(e)[:160]
        return None, meta
    out = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "<!--", "---", "|--", ">", "|")):
            continue
        c = _clean(s)
        # Skip the generator's own provenance stamp - it is not a finding.
        if not c or re.match(r"^Generated\b", c) or "pure Python" in c:
            continue
        out.append(c)
        if len(out) >= n:
            break
    meta["ok"] = bool(out)
    return out, meta


# ------------------------------------------------- the six repeated questions

def build_answers() -> list:
    """Pre-answer the six things J repeatedly asks.

    Sources are the registry's own j_intents mapping
    (automation/state/worker-registry.json). Every answer names its source file
    and its age; an unreadable source becomes a visible NO DATA card, never a
    confident-sounding guess.
    """
    answers = []

    # 1. Are we good to trade today? ----------------------------------------
    eng, eng_m = _load_json(STATE / "engine-health.json")
    una, una_m = _load_json(STATE / "unattended-health.json")
    chk, chk_m = _load_json(STATE / "self-check-last.json")
    parts, worst = [], "GREEN"
    rank = {"GREEN": 0, "OK": 0, "YELLOW": 1, "DEGRADED": 1, "RED": 2}
    for label, d, m in (("engine", eng, eng_m), ("unattended", una, una_m), ("self-check", chk, chk_m)):
        if not d:
            parts.append("%s: NO DATA" % label)
            worst = "RED" if worst != "RED" else worst
            continue
        v = str(d.get("verdict", "?")).upper()
        parts.append("%s %s" % (label, v))
        if rank.get(v, 1) > rank.get(worst, 0):
            worst = v
    reds = (eng or {}).get("reds") or (eng or {}).get("red_checks") or []
    detail = ""
    if isinstance(reds, list) and reds:
        detail = "RED: " + " · ".join(_clip(x, 90) for x in reds[:3])
    elif isinstance(chk, dict) and chk.get("problems"):
        pr = chk["problems"]
        detail = "problems: " + " · ".join(_clip(x, 90) for x in (pr if isinstance(pr, list) else [pr])[:3])
    answers.append({
        "q": "Are we good to trade today?",
        "verdict": worst,
        "answer": " · ".join(parts),
        "detail": detail,
        "means": ("Nothing is blocking an entry — the engine will trade if a setup fires."
                  if worst in ("GREEN", "OK") else
                  "Something upstream is degraded. Read the detail before trusting a quiet tape."),
        "sources": [eng_m, una_m, chk_m],
    })

    # 2. What's the status? --------------------------------------------------
    st, st_m = _latest_status()
    answers.append({
        "q": "What's the status?",
        "verdict": (st or {}).get("verdict", "NO DATA"),
        "answer": (st or {}).get("headline", "STATUS.md unreadable"),
        "detail": (st or {}).get("body", ""),
        "means": "This is the newest thing any autonomous fire wrote about itself.",
        "sources": [st_m],
    })

    # 3. What are we theorizing today? --------------------------------------
    bias, bias_m = _load_json(STATE / "today-bias.json")
    preds = []
    if bias:
        raw = bias.get("falsifiable_predictions") or bias.get("falsifiable_hypothesis") or []
        if isinstance(raw, (str, dict)):
            raw = [raw]
        if isinstance(raw, list):
            preds = [c for c in (_claim_of(x) for x in raw[:3]) if c]
    answers.append({
        "q": "What are we theorizing today?",
        "verdict": str((bias or {}).get("bias", "NO DATA")).upper(),
        "answer": _clip((bias or {}).get("bias_note") or "today-bias.json unreadable", 300),
        "detail": " · ".join(_clip(p, 160) for p in preds),
        "means": "These are falsifiable calls written BEFORE the session — they get graded, not forgotten.",
        "sources": [bias_m],
        "stamp": (bias or {}).get("date", ""),
    })

    # 4. What's our edge? ----------------------------------------------------
    sig, sig_m = _signature_lines()
    answers.append({
        "q": "What's our edge — what's actually working?",
        "verdict": "EDGE" if sig else "NO DATA",
        "answer": _clip((sig or ["SIGNATURE.md unreadable"])[0], 220),
        "detail": " · ".join(_clip(x, 150) for x in (sig or [])[1:4]),
        "means": "Mined from real fills only — the winner signature, not a backtest.",
        "sources": [sig_m],
    })

    # 5. Where's the money? --------------------------------------------------
    cal, cal_m = _load_json(CALENDAR_JSON)
    summ = ((cal or {}).get("views", {}).get("BOOK", {}) or {}).get("summary", {})
    if summ:
        net = summ.get("total_pnl_net", 0.0)
        ans = ("BOOK net %s over %s trading days (%s trades)"
               % (_money(net), summ.get("trading_days", "?"), summ.get("total_trades", "?")))
        det = ("day win-rate %.0f%% · best %s %s · worst %s %s · $%s fees"
               % (100 * float(summ.get("win_rate_by_day_net") or 0),
                  (summ.get("best_day_net") or {}).get("date", "?"),
                  _money((summ.get("best_day_net") or {}).get("pnl", 0)),
                  (summ.get("worst_day_net") or {}).get("date", "?"),
                  _money((summ.get("worst_day_net") or {}).get("pnl", 0)),
                  format(float(summ.get("total_fees") or 0), ",.0f")))
        verdict = "GREEN" if net > 0 else "RED"
    else:
        ans, det, verdict = "calendar-data.json unreadable", "", "NO DATA"
    answers.append({
        "q": "Where's the money?",
        "verdict": verdict,
        "answer": ans,
        "detail": det,
        "means": "Net of fees, real fills, all five arms. The calendar below is the same data day by day.",
        "sources": [cal_m],
    })

    # 6. Is futures working? ------------------------------------------------
    # ADDED 2026-08-20. J: "SO IS FUTURES WORKING" — the third time a state
    # question about a lane with no home-page line forced him to ask. OP-33(e):
    # a repeated question is a missing instrument. The readiness card above only
    # ever covered the SPY engine; futures runs five separate lanes and none of
    # them had a glanceable line anywhere.
    fut = STATE / "futures"
    lanes, live, stale_lanes = [], 0, []
    LANES = [
        ("trader (fillsim)", fut / "trader" / "heartbeat.json"),
        ("trader (broker)", fut / "trader-broker" / "heartbeat.json"),
        ("MES mirror", fut / "shadow-progress.json"),
        ("MES->MNQ edge3", fut / "edge3-sim-progress.json"),
        ("SSR shadow", fut / "ssr-shadow-progress.json"),
    ]
    for label, path in LANES:
        a = _age_h(path)
        # 24h: these lanes only write during a session, so an overnight read is
        # expected to be ~8h old. Anything past a day means it missed a session.
        if a is not None and a <= 24:
            live += 1
            lanes.append("%s ok" % label)
        else:
            stale_lanes.append("%s %s" % (label, ("%.0fh" % a) if a is not None else "MISSING"))
    mirror, _mm = _load_json(fut / "shadow-progress.json")
    edge3, _em = _load_json(fut / "edge3-sim-progress.json")
    bar = (mirror or {}).get("arming_bar", {})
    armable = bool(bar.get("armable"))
    detail_bits = []
    if mirror:
        detail_bits.append("MES mirror %s/%s round trips, %s, %s null%s" % (
            bar.get("round_trips_have", "?"), bar.get("round_trips_needed", "?"),
            _money(mirror.get("total_pnl_usd")),
            "beats" if bar.get("beats_null") else "fails",
            " -- ARMABLE" if armable else ""))
    if edge3:
        detail_bits.append("edge3 %s/%s trips, %s (%s/trip vs validated $%s)" % (
            edge3.get("n_closed_round_trips", "?"), edge3.get("falsification_floor", "?"),
            _money(edge3.get("total_pnl_usd_mnq")), _money(edge3.get("mean_pnl_usd_mnq")),
            edge3.get("validated_oos_per_trade", "?")))
    if stale_lanes:
        detail_bits.append("STALE: " + ", ".join(stale_lanes))
    answers.append({
        "q": "Is futures working?",
        "verdict": ("GREEN" if live == len(LANES) else "YELLOW") if live else "RED",
        "answer": "%d of %d lanes live -- ALL shadow/sim, zero real fills" % (live, len(LANES)),
        "detail": " · ".join(detail_bits),
        "means": ("Running and self-scoring. MES mirror has cleared its arming bar -- that is a "
                  "decision waiting, not a bug." if armable else
                  "Running and self-scoring; nothing has cleared its arming bar yet."),
        "sources": [{"path": "automation/state/futures/", "age_h": _age_h(fut / "trader" / "heartbeat.json"),
                     "ok": live > 0}],
    })

    # 7. What changed since I last looked? -----------------------------------
    # ADDED 2026-08-29. J: "Every time you come back you ask me." -- a repeated
    # question is a missing instrument (CLAUDE.md judgment-guards), so this
    # reads the digest whats_changed.py writes rather than answering by hand.
    # Read-only: this card never runs the script or advances its marker --
    # merely looking at the page must never clear the digest. Run
    # `python setup/scripts/whats_changed.py --seen` to mark it read.
    wch, wch_m = _load_json(STATE / "whats-changed.json")
    if wch:
        answers.append({
            "q": "What changed since I last looked?",
            "verdict": "GREEN" if wch.get("total_changes") else "OK",
            "answer": wch.get("headline", "?"),
            "detail": _clip("; ".join(
                "%s: %d" % (name, sec.get("count", 0))
                for name, sec in (wch.get("sections") or {}).items()
                if isinstance(sec, dict) and sec.get("count")
            ), 200),
            "means": ("New activity since the marker -- run `whats_changed.py --seen` once you've "
                      "read it to reset the digest." if wch.get("total_changes") else
                      "Quiet since the marker -- nothing to catch up on."),
            "sources": [wch_m],
        })
    else:
        answers.append({
            "q": "What changed since I last looked?",
            "verdict": "NO DATA",
            "answer": "whats-changed.json unreadable",
            "detail": "run: python setup/scripts/whats_changed.py",
            "means": "The digest hasn't been generated yet (or its file is unreadable).",
            "sources": [wch_m],
        })

    return answers


# Org-shaped builders live in gamma_cockpit_org (800-line ceiling). Re-exported
# here so every existing import site and test keeps working unchanged.
from gamma_cockpit_org import (            # noqa: E402
    build_desks, build_allocation, build_org, compact_calendar, calendar_scale,
)


def _cd():
    """The engine-room / agent / thinking feeds live in their own module so this
    file stays under the 800-line ceiling."""
    import gamma_cockpit_data
    return gamma_cockpit_data


def _army():
    """The Army view's orchestrator/session/worker/pulse builder lives in its
    own module -- same 800-line-ceiling reasoning as gamma_cockpit_data."""
    import gamma_cockpit_army
    return gamma_cockpit_army


def _cards():
    """Action Cards' deterministic ranker lives in its own module -- same
    800-line-ceiling reasoning, and it ALSO persists automation/state/
    action-cards.json as a side effect (gamma-companion/server.js reads that
    file at fire-time so a card's stored prompt is authoritative over
    whatever the client POSTs -- see gamma_cockpit_cards.py's own docstring)."""
    import gamma_cockpit_cards
    return gamma_cockpit_cards


def _money(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "?"
    return ("+$" if v >= 0 else "-$") + format(abs(v), ",.0f")


def build(quiet: bool = False) -> dict:
    hq, hq_meta = _hq_json()
    cal, cal_meta = _load_json(CALENDAR_JSON)
    cost_meter, cost_meter_meta = _load_json(COST_METER_JSON)
    payload = {
        "generated_et": _et_label(),
        # ISO ET stamp for the page's view-time age maths. _et_label() is a HUMAN
        # string ("2026-08-20 01:38:51 Thursday EDT") that Date.parse cannot read,
        # which rendered the briefing badge as "unknown age".
        "built_at_et": _cd()._iso_now(),
        "today": datetime.now().strftime("%Y-%m-%d"),
        "stale_hours": STALE_HOURS,
        "hq": hq or {},
        "hq_source": hq_meta,
        "calendar": compact_calendar(cal or {}),
        "calendar_full": cal or {},
        "calendar_scale": calendar_scale(cal or {}),
        "calendar_source": cal_meta,
        "cost_meter": cost_meter or {},
        "cost_meter_source": cost_meter_meta,
        "answers": build_answers(),
        "desks": build_desks(),
        "allocation": build_allocation(),
        "org": build_org(),
        "engine_room": _cd().engine_room(),
        "agents": _cd().agent_feed(),
        "thinking": _cd().thinking(),
        "positions": _cd().positions(),
        "briefing": None,   # filled below, needs desks+allocation+answers
        "wants_full": _wants_full(),
        "wants_source": {"path": GAMMA_WANTS.relative_to(REPO).as_posix(),
                         "age_h": _age_h(GAMMA_WANTS), "ok": GAMMA_WANTS.exists()},
        # WHAT GAMMA DID WHILE J SLEPT. He asked for it by name -- "i dont see
        # anywhere what gamma did all night or anything of an activity feed". The
        # digest already existed as a CLI (whats_changed.py, built for the same
        # repeated question); this only puts it on the page instead of behind a
        # command. Read-only, and a failure degrades to an empty feed.
        "activity": None,
        # IS GAMMA AWAKE, AND WHAT DOES IT THINK IT SHOULD DO NEXT. J: "where is
        # the autonomy ... give it the ability to do actions like choose recc
        # action cards, theorize whats next". The loop was real and invisible.
        "autonomy": None,
        "army": None,   # filled below; a presence-telemetry failure must not lose the page
        "cards": None,  # filled below; a card-generation failure must not lose the page
        # THE TRADING HALF. Added 2026-08-30 after a research pass read payload.json cold
        # and found no `glass` key: the app was getting it ONLY from /api/desk, so with
        # the companion down the trading band degraded to named-empty-states -- the very
        # blindness this page was rebuilt to end. The live path stays authoritative
        # (equity and position at payload age are wrong answers, not stale ones); this is
        # the floor beneath it.
        "glass": None,
        # Standing research lanes, same reasoning as glass.
        "lanes": None,
        # THE GOAL, surfaced at the top level for convenience -- vAutonomy and the
        # Overview "Working on" strip both read D.goal rather than reaching through
        # D.autonomy.goal. Filled below from the same autonomy payload; never
        # re-derived from the goal file a second time.
        "goal": None,
        # WHAT GAMMA LEARNED. J's goal DONE-WHEN (c): a rollup of the existing
        # ledgers (kitchen, preregs, shadow, candidates, conductor, commits, study,
        # self-audit) so "constantly testing and learning" has a number attached.
        # Built by learning_ledger.py (a sibling builder's module on this same
        # goal) -- absent until that lands, and its absence must render as NO DATA,
        # never crash this page.
        "learning": None,
    }
    try:
        sys.path.insert(0, str(REPO / "setup" / "scripts"))
        import gamma_autonomy as _au
        payload["autonomy"] = _au.build()
        payload["goal"] = payload["autonomy"].get("goal")
    except Exception as e:                       # noqa: BLE001 - status must never 500 the page
        payload["autonomy"] = {"error": str(e)[:160], "awake": None}
        payload["goal"] = None

    try:
        sys.path.insert(0, str(REPO / "setup" / "scripts"))
        import learning_ledger as _ll
        payload["learning"] = _ll.build()
        try:
            _ll.write(payload["learning"])
        except Exception:
            pass   # writing the ledger's own cache file is a bonus, not a dependency
    except ImportError:
        # A1's sibling module hasn't landed yet, or landed without ever writing its
        # cache -- fall back to the file it would have written, then to an honest
        # NO DATA rather than losing this whole section of the page.
        led = _load_json(STATE / "learning-ledger.json")[0]
        payload["learning"] = led or {"error": "NO DATA", "windows": {}, "latest_verdicts": []}
    except Exception as e:                        # noqa: BLE001 - never lose the page over a feed
        payload["learning"] = {"error": str(e)[:160], "windows": {}, "latest_verdicts": []}

    for _key, _mod in (("glass", "gamma_glass"), ("lanes", "gamma_lanes")):
        try:
            sys.path.insert(0, str(REPO / "setup" / "scripts"))
            payload[_key] = __import__(_mod).build()
        except Exception as e:                   # noqa: BLE001 - never lose the page over a slice
            payload[_key] = {"error": str(e)[:160]}

    try:
        sys.path.insert(0, str(REPO / "setup" / "scripts"))
        import whats_changed as _wc
        payload["activity"] = _wc.build_digest()
    except Exception as e:                       # noqa: BLE001 - never lose the page over a feed
        payload["activity"] = {"error": str(e)[:160], "sections": {}, "total_changes": 0}

    try:
        payload["army"] = _army().build_army()
    except Exception as e:                       # noqa: BLE001 - Army view must degrade, not 500 the page
        payload["army"] = {"orchestrator": None, "sessions": [], "workers": [], "pulses": [],
                            "session_overflow": 0, "legend": "", "scope_note": "", "source": {},
                            "error": str(e)[:160]}
    try:
        # write=True: this IS the generation point that keeps action-cards.json
        # (server.js's authoritative prompt store) in sync with what the page shows.
        payload["cards"] = _cards().build_cards(write=True)
    except Exception as e:                        # noqa: BLE001 - Cards view must degrade, not 500 the page
        payload["cards"] = {"cards": [], "rth_now": False, "quiet_active": False,
                             "legend": "", "source": {}, "error": str(e)[:160]}
    # The briefing reads the already-built desks/allocation/answers so it never
    # re-derives a number a card already shows.
    try:
        payload["briefing"] = _cd().briefing(
            payload["desks"]["desks"], payload["allocation"], payload["answers"])
    except Exception as e:                      # noqa: BLE001 - a missing briefing must not lose the page
        payload["briefing"] = {"lines": [], "flags": [], "error": str(e)[:160]}

    # 9 new Command-view tiles (WS-D, 2026-09-03): gate/prep/eod/standup/shadow/
    # watchers/guards/tasks/gym. Each tile already fails safe on its own source;
    # this guards the IMPORT itself so a broken tiles module never loses the page.
    try:
        sys.path.insert(0, str(REPO / "setup" / "scripts"))
        from gamma_cockpit_tiles import build_tiles as _build_tiles
        payload.update(_build_tiles())
    except Exception as e:                       # noqa: BLE001 - tiles must never lose the page
        for _k in ("gate", "prep", "eod", "standup", "shadow", "watchers", "guards", "tasks", "gym"):
            payload[_k] = {"ok": False, "path": None, "stamp_et": None, "verdict": "off",
                           "say": "NO DATA, tiles module failed: %s" % str(e)[:120], "fresh_h": 24}

    if not quiet:
        if not hq_meta["ok"]:
            print("WARN: state librarian unavailable (%s) - presence renders NO DATA"
                  % hq_meta.get("error", "?"), file=sys.stderr)
        if not cal_meta["ok"]:
            print("WARN: calendar-data.json unavailable - calendar renders NO DATA", file=sys.stderr)
    return payload


def _et_label() -> str:
    try:
        r = subprocess.run([sys.executable, str(REPO / "setup" / "scripts" / "et_clock.py")],
                           cwd=str(REPO), capture_output=True, text=True, timeout=30,
                           encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().splitlines()[0]
    except (OSError, subprocess.SubprocessError):
        pass
    return datetime.now().strftime("%Y-%m-%d %H:%M (local — et_clock unavailable)")


def render(payload: dict) -> str:
    """Delegate to the cockpit UI + JS modules (presentation lives there)."""
    import gamma_cockpit_ui as ui
    import gamma_cockpit_js as vjs
    return ui.render(payload, vjs.JS)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate the Gamma command center HTML.")
    ap.add_argument("--open", action="store_true", help="open the page after writing it")
    ap.add_argument("--quiet", action="store_true", help="print only the output path")
    a = ap.parse_args()

    payload = build(quiet=a.quiet)
    html = render(payload)
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(OUT_HTML.relative_to(REPO) if a.quiet else "wrote -> %s" % OUT_HTML.relative_to(REPO))

    # Companion copy is a bonus (live pulses), never a dependency: OUT_HTML above is
    # the surface that must always succeed. gamma-companion/ may be absent on a
    # fresh checkout (npm install not run yet) -- that is not a reason to fail this
    # script's primary job.
    try:
        COMPANION_HTML.parent.mkdir(parents=True, exist_ok=True)
        COMPANION_HTML.write_text(html, encoding="utf-8")
        if not a.quiet:
            print("wrote -> %s" % COMPANION_HTML.relative_to(REPO))
    except OSError as e:
        if not a.quiet:
            print("WARN: companion copy not written (%s) -> %s" % (COMPANION_HTML, e), file=sys.stderr)

    # The same payload as raw JSON, for the app under public/app/. That app is real
    # static files rather than a generated blob, so it FETCHES its data instead of
    # having it baked in -- one source of truth, and the app can refresh without a
    # rebuild. Same bonus-not-dependency contract as the companion copy above.
    try:
        COMPANION_JSON.parent.mkdir(parents=True, exist_ok=True)
        COMPANION_JSON.write_text(json.dumps(payload, default=str), encoding="utf-8")
        if not a.quiet:
            print("wrote -> %s" % COMPANION_JSON.relative_to(REPO))
    except OSError as e:
        if not a.quiet:
            print("WARN: payload.json not written (%s) -> %s" % (COMPANION_JSON, e), file=sys.stderr)

    if not a.quiet:
        nodata = [x["q"] for x in payload["answers"] if str(x.get("verdict")).upper() in ("NO DATA", "NODATA")]
        print("answers: %d rendered, %d NO DATA%s"
              % (len(payload["answers"]), len(nodata), (" -> " + "; ".join(nodata)) if nodata else ""))
    if a.open:
        webbrowser.open(OUT_HTML.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
