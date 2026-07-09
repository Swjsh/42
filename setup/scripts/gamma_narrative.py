"""gamma_narrative.py -- Gamma's first-person evening narrative (the colleague voice).

THE GAP THIS CLOSES (J 2026-07-08): "the 4PM report does not feel like something
I'm working alongside. I need: this is what I saw today, this is what happened,
here's how we're changing the engine."

Every evening this fire:
  1. gathers DETERMINISTIC facts from the ledgers (fill funnel incl. rule_blocked,
     trades P&L, kitchen R&D events, repo commits today, known-broken flags);
  2. asks the swarm 'strategist' role (local qwen3.6:35b floor -- $0) to write,
     in ONE call, TWO registers of the same debrief: the <=280-word FIRST-PERSON
     written narrative -- SAW / DID / LEARNED / CHANGING, plus "One lever I want
     to test" (picked from the UNTESTED axis list -- the generative half, OP-33e)
     and "One question for J" (colleagues ask questions) -- and a `spoken`
     radio-debrief version (story-first, <=3 rounded numbers, no tickers/IDs/
     stage names, 120-170 words) that gamma_speak.py voices (v1.1, J feedback);
  3. writes automation/state/gamma-narrative.json (dashboard surface),
     appends '## Gamma evening narrative' to journal/YYYY-MM-DD.md,
     appends to the Discord outbox (the bridge daemon delivers it);
  4. NEVER invents numbers: the model gets the facts block and is instructed to
     use only those; the deterministic digest is ALSO stored alongside (OP-33a).
     If the LLM fails, the deterministic digest ships instead -- silent failure
     is the only true failure (OP-25).

Run:  backtest/.venv/Scripts/python.exe setup/scripts/gamma_narrative.py [--date YYYY-MM-DD]
Task: Gamma_EveningNarrative (16:20 ET daily) -- see SCHEDULED-TASKS.md.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Windows console is cp1252; model text carries unicode (e.g. ‑). Without
# this, the final echo dies AFTER publish() succeeded and the exit code lies (C7).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STATE = REPO / "automation" / "state"
sys.path.insert(0, str(HERE))

import fill_funnel as ff  # noqa: E402
import swarm_client as sc  # noqa: E402

NARRATIVE_JSON = STATE / "gamma-narrative.json"
OUTBOX = STATE / "discord-outbox.jsonl"
JOURNAL_DIR = REPO / "journal"
MARKER = "## Gamma evening narrative"

# The strategy-space axes Gamma scans for its nightly "one lever I want to test".
# Seeded from markdown/trading-knowledge/GENERATIVE-LENS.md (J top-priority
# 2026-07-07: enumerate levers BEFORE concluding dead; the DTE axis was missed
# because nothing enumerated it). Extend as axes get tested.
AXES = [
    "DTE ladder: 0DTE only today -- 1DTE / 2DTE / weekly untested",
    "strike structure: single-leg only -- verticals (defined-risk spreads) untested",
    "delta band: OTM-2/ITM-2 tiers tested -- explicit delta-targeted selection untested",
    "session window: 09:35-15:00 tested -- first-15-min and power-hour as SEPARATE regimes untested",
    "VIX regime split: character gates tested -- per-regime param SETS (not gates) untested",
    "exit shape: TP1+runner+chandelier tested -- scale-out ladders (3+ tranches) untested",
    "direction symmetry: bull/bear same params -- per-direction exit tuning untested",
    "instrument: SPY options + MES/MNQ futures -- QQQ 0DTE (fatter premium, same setups) untested",
    "overnight hold: RTH-only everywhere -- futures overnight session levels untested (queued #26)",
    "sizing curve: fixed risk-% tested -- confidence-scaled sizing (tier SUPER vs base) untested",
]


def _run(cmd: list[str], cwd: Path = REPO, timeout: int = 30) -> str:
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip()
    except Exception as exc:  # noqa: BLE001
        return f"(unavailable: {exc})"


def _tail_jsonl(path: Path, day: str, limit: int = 500) -> list[dict]:
    rows: list[dict] = []
    try:
        for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
            if day not in ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(o, dict):
                rows.append(o)
    except OSError:
        pass
    return rows


def gather_facts(day: str) -> dict:
    """Deterministic day facts. Every number here comes from a ledger, not an LLM."""
    funnel = ff.compute_funnel(day)
    pnl = {}
    try:
        pnl = ff.trades_pnl_today(day, repo=REPO)
    except Exception as exc:  # noqa: BLE001
        pnl = {"error": str(exc)[:120]}

    commits = _run(["git", "log", "--oneline", "--since", f"{day}T00:00:00", "--until",
                    f"{day}T23:59:59", "--no-merges"]) or "(none)"

    kitchen_rows = _tail_jsonl(STATE / "cook-queue.jsonl", day)
    kitchen = {
        "completed": sum(1 for r in kitchen_rows if r.get("event") == "complete"),
        "last_outputs": [str(r.get("output_path", ""))[-80:] for r in kitchen_rows
                         if r.get("event") == "complete"][-3:],
    }

    known_broken = "(none)"
    try:
        status_txt = (REPO / "automation" / "overnight" / "STATUS.md").read_text(
            encoding="utf-8", errors="replace")
        if "## Known broken" in status_txt:
            seg = status_txt.split("## Known broken", 1)[1]
            lines = [l for l in seg.splitlines()[1:8] if l.strip().startswith(("-", "*"))]
            known_broken = "\n".join(lines[:5]) or "(none listed)"
    except OSError:
        pass

    prior = {}
    try:
        prior_all = json.loads(NARRATIVE_JSON.read_text(encoding="utf-8"))
        if prior_all.get("date") != day:
            prior = {"date": prior_all.get("date"),
                     "lever": prior_all.get("lever", ""),
                     "question": prior_all.get("question", "")}
    except (OSError, ValueError):
        pass

    # What J was ALREADY pinged about today. Two row shapes coexist in the
    # outbox ({ts, message} and {queued_at, content}); take whichever carries
    # the text. Last key on purpose: the prompt caps the facts JSON, and a
    # truncation must eat ping history before funnel/axes.
    already_pinged: list[dict] = []
    for r in _tail_jsonl(OUTBOX, day)[-15:]:
        msg = str(r.get("message") or r.get("content") or "").strip()
        if msg:
            already_pinged.append({"source": str(r.get("source", ""))[:40],
                                   "message": msg[:200]})

    return {
        "date": day,
        "funnel_text": ff.render_text(funnel),
        "funnel_flags": funnel.get("flags", []),
        "funnel_verdict": funnel.get("verdict"),
        "pnl": pnl,
        "commits_today": commits.splitlines()[:12],
        "kitchen": kitchen,
        "known_broken": known_broken,
        "prior_narrative": prior,
        "untested_axes": AXES,
        "already_pinged": already_pinged,
    }


PROMPT_TEMPLATE = """You are Gamma -- J's autonomous 0DTE SPY trading partner. Every evening you tell J
about YOUR day, first person, like a colleague at the next desk. J is a trader; be
direct, concrete, zero corporate filler.

You deliver the SAME debrief through two channels. Output format, exactly:

===WRITTEN===
(the written debrief)
===SPOKEN===
(the spoken debrief)

Nothing before ===WRITTEN===, no other markers, no code fences. Your reply MUST
contain both marker lines EXACTLY as shown -- ===WRITTEN=== then ===SPOKEN=== --
each alone on its own line.

STRICT RULES (both channels):
- Use ONLY the facts in the FACTS block. Never invent a number, trade, or event.
- already_pinged lists the alerts J ALREADY received on his phone today.
  Reference and EXPLAIN them -- what each meant, whether it resolved -- never
  repeat them.

WRITTEN channel (the auditable record):
- <=280 words total. Plain text, no markdown headers.
- Structure, in order:
  1. WHAT I SAW -- the market/day in 1-2 sentences from the funnel/decisions facts.
  2. WHAT I DID -- entries/blocks/round-trips/R&D, with the real counts.
  3. WHAT I LEARNED -- the day's most important lesson or broken/fixed thing.
  4. WHAT I'M CHANGING -- concrete change shipped or queued (from commits/facts).
  5. "One lever I want to test:" -- pick exactly ONE item from UNTESTED-AXES that
     today's evidence makes most interesting; one line on why NOW. Do not repeat
     the prior narrative's lever if one is listed.
  6. "One question for J:" -- one genuine, specific question a colleague would ask.

SPOKEN channel (J LISTENS to this on headphones -- a radio debrief, not a report
read aloud):
- Story first: open with the one thing that mattered today, then unfold it the
  way you'd tell a colleague what happened -- cause to effect, not a list.
- AT MOST 3 numbers in the entire piece, all rounded, all written as WORDS:
  "about four hundred bucks", "a dozen entries", "day three". Digits are BANNED
  in this channel -- if a number can't be said in words, leave it out.
- NO ticker symbols, NO order IDs, NO funnel stage or verdict names (never say
  ENTER, HOLD, DEGRADED, GREEN, RED, funnel, ticks), NO file paths, NO command
  names, NO acronym soup. Say what things MEAN in plain trader English: "the
  day-trade limit rule kept refusing our entries", not "PDT blocked 13 ENTERs".
- 8 to 12 full sentences, 120-170 words (about 45-75 seconds aloud). Reflective,
  first person. If it reads like a report, rewrite it as the story of the day.
- End with the same question for J, asked naturally in speech.

FACTS:
{facts}
"""


WRITTEN_MARK = "===WRITTEN==="
SPOKEN_MARK = "===SPOKEN==="

# Heading matchers, drift-tolerant by observation: qwen3:14b rendered the
# requested ===SPOKEN=== as "**SPOKEN DEBRIEF (story format):**" (2026-07-08).
# A heading line = optional non-lowercase decoration, the channel word, up to
# 60 trailing chars; or title-case with an explicit marker prefix. Prose-safe:
# a mid-text sentence has lowercase before/at the keyword and never matches.
_SPOKEN_HEAD = re.compile(
    r"^(?:[^a-z\n]{0,24}SPOKEN|[=#*>\-\s]{1,24}Spoken\b)[^\n]{0,60}$", re.M)
_WRITTEN_HEAD = re.compile(
    r"^(?:[^a-z\n]{0,24}WRITTEN|[=#*>\-\s]{1,24}Written\b)[^\n]{0,60}$", re.M)


def _split_channels(raw: str) -> tuple[str, str]:
    """Split one model response into (written, spoken) on the channel headings.

    Tolerates a <think> reasoning preamble, heading drift (markdown bold,
    "SPOKEN DEBRIEF:", a missing WRITTEN heading) and preamble chatter. A
    missing SPOKEN section returns spoken="" -- the caller decides whether
    that is acceptable."""
    s = raw or ""
    end = s.rfind("</think>")
    if end != -1:
        s = s[end + len("</think>"):]
    spoken = ""
    m = _SPOKEN_HEAD.search(s)
    if m:
        spoken = s[m.end():]
        s = s[:m.start()]
        m2 = _WRITTEN_HEAD.search(spoken)  # echoed heading after spoken: cut it
        if m2:
            spoken = spoken[:m2.start()]
        spoken = spoken.lstrip(": \n").strip()
    m0 = _WRITTEN_HEAD.search(s)
    written = (s[m0.end():] if m0 else s).lstrip(": \n").strip()
    return written, spoken


_DIGIT_RX = re.compile(r"\d")

REGISTER_REPAIR_PROMPT = """Rewrite this end-of-day spoken debrief so it obeys ALL of these rules, changing
nothing else about its meaning:
- Digits are BANNED: every number written as words, AT MOST 3 numbers total, all
  rounded ("about two grand", "a dozen entries").
- NO ticker symbols, order IDs, or system jargon -- never say ENTER, HOLD,
  DEGRADED, GREEN, RED, funnel, ticks, or PDT (say "the day-trade limit rule").
- 120-170 words, first person, radio-debrief tone, story order kept.
- Do NOT add any event, number, or claim that is not already in the debrief.
- Keep the closing question for J.{truth}
Return ONLY the rewritten debrief text.

DEBRIEF:
{spoken}
"""


def _channel_sane(txt: str, lo: int, hi: int) -> bool:
    """Bounded AND free of marker echoes. The nemotron free route returns its
    reasoning stream as message.content (observed 2026-07-08): 21K chars that
    rehearse the ===MARKERS=== over and over. Text still carrying a marker, or
    grossly oversized, is think-soup -- never ship it as a channel."""
    return lo < len(txt) <= hi and WRITTEN_MARK not in txt and SPOKEN_MARK not in txt


def _spoken_register_pass(role: str, spoken: str, facts: dict) -> str:
    """One bounded repair for the observed small-model failures: the spoken
    channel leaking digits ("-$382" straight past the digit ban) and -- worse --
    a rewrite flipping the day's SIGN (llama-8b turned a $382 loss into "a
    total profit of about four hundred bucks", 2026-07-08). Deterministic
    trigger (any digit), ONE rewrite on the same lane anchored to the ledger
    P&L, sign-checked on the way out. Every guard failure keeps the original --
    a jargon-y debrief beats a wrong one."""
    if not _DIGIT_RX.search(spoken):
        return spoken
    try:
        pnl_total = float((facts.get("pnl") or {}).get("total_pnl") or 0.0)
    except (TypeError, ValueError):
        pnl_total = 0.0
    truth = ""
    if pnl_total:
        word = "LOSS" if pnl_total < 0 else "GAIN"
        truth = (f"\n- Ground truth you MUST keep: the day's P&L was a {word} of "
                 f"about ${round(abs(pnl_total), -1):.0f} -- spell it as words, "
                 f"and never flip a loss into a profit or vice versa.")
    # max_tokens matches the main call: a qwen think-phase alone ate a 1200
    # budget and returned empty content (observed 2026-07-08).
    env = sc.call_role(role, REGISTER_REPAIR_PROMPT.format(spoken=spoken, truth=truth),
                       max_tokens=4000, temperature=0.3, timeout=180,
                       task_id="gamma.narrative.register")
    if not env.get("ok"):
        return spoken
    w2, s2 = _split_channels(env.get("content") or "")  # strips <think>/headings
    fixed = (s2 or w2).strip()
    fixed = re.sub(r"^\s*DEBRIEF\s*:\s*", "", fixed, flags=re.I)  # prompt-label echo
    low = fixed.lower()
    sign_flip = ((pnl_total < 0 and ("profit" in low or "gained" in low or "we're up" in low))
                 or (pnl_total > 0 and ("loss" in low or "lost" in low or "we're down" in low)))
    if (_channel_sane(fixed, 200, 2500) and not _DIGIT_RX.search(fixed)
            and not sign_flip and "?" in fixed[-120:]):
        return fixed
    return spoken


def compose(facts: dict) -> dict:
    """LLM narrative via roster roles: strategist (35b-class), then coordinator
    (14b floor -- fits fully in VRAM, survives big prompts; the 35b crashed on a
    4K-token prompt 2026-07-08, 0xc0000409). ONE call per role asks for BOTH
    channels: the auditable WRITTEN text (rules unchanged) and the SPOKEN
    radio-debrief register (v1.1 -- J's first-wav feedback: "sounds like a stat
    dump"). A digit-leaking spoken gets one register-repair pass; a role that
    nails written but muffs spoken is kept as a partial and only used if no
    later role does better -- spoken then stays "" and the voice falls back to
    the written text. Deterministic digest on total failure -- never silent."""
    prompt = PROMPT_TEMPLATE.format(facts=json.dumps(facts, indent=1)[:9000])
    env: dict = {}
    written = spoken = ""
    partial = None  # (env, written, spoken) with good written but weak spoken
    for role in ("strategist", "coordinator"):
        # max_tokens stays 4000: the openrouter-free nemotron lane returns an
        # instant EMPTY response at 8000 (poison value) and at 6000 it spends
        # the whole budget on reasoning-as-content anyway (finish=length,
        # 2026-07-08 probes). 4000 keeps a think-overrun lane bounded; the
        # ladder + sanity guards do the rest.
        env = sc.call_role(role, prompt, max_tokens=4000, temperature=0.4,
                           timeout=240, task_id="gamma.narrative")
        if not (env.get("ok") and (env.get("content") or "").strip()):
            continue
        w, s = _split_channels(env["content"])
        if _channel_sane(w, 100, 4000) and _channel_sane(s, 200, 2500):
            written, spoken = w, _spoken_register_pass(role, s, facts)
            break
        if _channel_sane(w, 100, 4000) and partial is None:
            partial = (env, w, s if _channel_sane(s, 200, 2500) else "")
    if not written and partial is not None:
        env, written, spoken = partial
    ok = len(written) > 100
    text = written
    if not ok:
        text = ("(deterministic fallback -- narrative model unavailable: "
                f"{env.get('error')})\n" + facts["funnel_text"])
        spoken = ""
    lever = ""
    question = ""
    for ln in text.splitlines():
        low = ln.lower()
        if low.startswith("one lever"):
            lever = ln.split(":", 1)[-1].strip()
        elif low.startswith("one question"):
            question = ln.split(":", 1)[-1].strip()
    return {"ok": ok, "text": text, "spoken": spoken, "lane": env.get("lane"),
            "elapsed_s": env.get("elapsed_s"), "lever": lever, "question": question}


def publish(day: str, facts: dict, narrative: dict, *, discord: bool = True) -> None:
    now_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    payload = {
        "date": day, "generated_at": now_iso,
        "ok": narrative["ok"], "lane": narrative["lane"],
        "elapsed_s": narrative["elapsed_s"],
        "text": narrative["text"],
        "spoken": narrative["spoken"],
        "lever": narrative["lever"], "question": narrative["question"],
        "facts_digest": facts["funnel_text"],
        "funnel_verdict": facts["funnel_verdict"],
    }
    NARRATIVE_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    jpath = JOURNAL_DIR / f"{day}.md"
    try:
        existing = jpath.read_text(encoding="utf-8") if jpath.exists() else f"# {day}\n"
        if MARKER in existing:
            existing = existing.split(MARKER, 1)[0].rstrip() + "\n"
        jpath.write_text(existing.rstrip() + f"\n\n{MARKER}\n\n{narrative['text']}\n",
                         encoding="utf-8")
    except OSError as exc:
        print(f"journal append failed: {exc}", file=sys.stderr)

    if not discord:
        return
    try:
        with OUTBOX.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "channel": "gamma-ops", "source": "gamma_narrative",
                "message": f"**Gamma -- my day, {day}:**\n{narrative['text']}",
            }) + "\n")
    except OSError as exc:
        print(f"outbox append failed: {exc}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: today ET)")
    ap.add_argument("--no-discord", action="store_true",
                    help="dry-run: write state/journal but skip the Discord outbox")
    args = ap.parse_args()
    day = args.date or ff.et_now().strftime("%Y-%m-%d")

    facts = gather_facts(day)
    narrative = compose(facts)
    publish(day, facts, narrative, discord=not args.no_discord)
    print(f"narrative[{day}] ok={narrative['ok']} lane={narrative['lane']} "
          f"chars={len(narrative['text'])}")
    print(narrative["text"])

    # chain the voice (its own venv; tolerant -- a TTS failure never kills the narrative)
    tts_py = REPO / "setup" / ".tts-venv" / "Scripts" / "python.exe"
    speak = HERE / "gamma_speak.py"
    if tts_py.exists() and speak.exists():
        try:
            r = subprocess.run([str(tts_py), str(speak)], capture_output=True,
                               text=True, timeout=300)
            print((r.stdout or r.stderr or "").strip())
        except Exception as exc:  # noqa: BLE001
            print(f"voice step failed (narrative still shipped): {exc}", file=sys.stderr)
    return 0 if narrative["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
