"""gamma_narrative.py -- Gamma's first-person evening narrative (the colleague voice).

THE GAP THIS CLOSES (J 2026-07-08): "the 4PM report does not feel like something
I'm working alongside. I need: this is what I saw today, this is what happened,
here's how we're changing the engine."

Every evening this fire:
  1. gathers DETERMINISTIC facts from the ledgers (fill funnel incl. rule_blocked,
     trades P&L, kitchen R&D events, repo commits today, known-broken flags);
  2. asks the swarm 'strategist' role (local qwen3.6:35b floor -- $0) to write a
     <=280-word FIRST-PERSON narrative: SAW / DID / LEARNED / CHANGING, plus
     "One lever I want to test" (picked from the UNTESTED axis list -- the
     generative half, OP-33e) and "One question for J" (colleagues ask questions);
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
    }


PROMPT_TEMPLATE = """You are Gamma -- J's autonomous 0DTE SPY trading partner. Every evening you tell J
about YOUR day, first person, like a colleague at the next desk. J is a trader; be
direct, concrete, zero corporate filler.

STRICT RULES:
- Use ONLY the facts in the FACTS block. Never invent a number, trade, or event.
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

FACTS:
{facts}
"""


def compose(facts: dict) -> dict:
    """LLM narrative via roster roles: strategist (35b-class), then coordinator
    (14b floor -- fits fully in VRAM, survives big prompts; the 35b crashed on a
    4K-token prompt 2026-07-08, 0xc0000409). Deterministic digest on total failure
    -- never silent."""
    prompt = PROMPT_TEMPLATE.format(facts=json.dumps(facts, indent=1)[:9000])
    env: dict = {}
    for role in ("strategist", "coordinator"):
        env = sc.call_role(role, prompt, max_tokens=4000, temperature=0.4,
                           timeout=240, task_id="gamma.narrative")
        if env.get("ok") and len((env.get("content") or "").strip()) > 100:
            break
    text = (env.get("content") or "").strip()
    ok = bool(env.get("ok")) and len(text) > 100
    if not ok:
        text = ("(deterministic fallback -- narrative model unavailable: "
                f"{env.get('error')})\n" + facts["funnel_text"])
    lever = ""
    question = ""
    for ln in text.splitlines():
        low = ln.lower()
        if low.startswith("one lever"):
            lever = ln.split(":", 1)[-1].strip()
        elif low.startswith("one question"):
            question = ln.split(":", 1)[-1].strip()
    return {"ok": ok, "text": text, "lane": env.get("lane"),
            "elapsed_s": env.get("elapsed_s"), "lever": lever, "question": question}


def publish(day: str, facts: dict, narrative: dict, *, discord: bool = True) -> None:
    now_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    payload = {
        "date": day, "generated_at": now_iso,
        "ok": narrative["ok"], "lane": narrative["lane"],
        "elapsed_s": narrative["elapsed_s"],
        "text": narrative["text"],
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
