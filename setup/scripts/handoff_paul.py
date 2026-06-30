"""handoff_paul.py -- generate a PAUL-structured session handoff for the next (cheaper Sonnet)
session, so a cold session can pick up without re-deriving context. The /insights "PAUL-structured
Sonnet handoff prompt", grounded in LIVE state (never fabricated -- an empty section says so).

PAUL =
  P -- Progress     : what shipped (recent commits + conductor outcomes)
  A -- Active state : where things stand RIGHT NOW (ET/market, self-check, engine-health, bias)
  U -- Up-next      : prioritized next actions (FUTURE-IMPROVEMENTS top + open conductor proposals)
  L -- Loose-ends   : known-broken + gotchas (STATUS.md ## Known broken)

$0, read-only, no LLM. Run: backtest/.venv/Scripts/python.exe setup/scripts/handoff_paul.py
Writes automation/state/handoff-latest.md and prints to stdout.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

try:  # Windows console is cp1252; emoji in commit msgs / docs choke print() otherwise
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

REPO = Path(__file__).resolve().parents[1].parent
STATE = REPO / "automation" / "state"
sys.path.insert(0, str(REPO / "setup" / "scripts"))
try:
    from et_clock import et_now
except Exception:  # noqa: BLE001
    import datetime as _dt
    def et_now(): return _dt.datetime.utcnow()


def _git(args: list[str]) -> str:
    try:
        return subprocess.run(["git", *args], cwd=str(REPO), capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def _json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return {}


def _lines(p: Path) -> list[str]:
    try:
        return [l for l in p.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    except Exception:  # noqa: BLE001
        return []


def build() -> str:
    now = et_now()
    mins = now.hour * 60 + now.minute
    mkt = "MARKET HOURS (production-only)" if (now.weekday() < 5 and 570 <= mins <= 955) else "closed / after-hours (build window)"
    sc = _json(STATE / "self-check-last.json")
    eh = _json(STATE / "engine-health.json")
    bias = _json(STATE / "today-bias.json")

    commits = _git(["log", "--oneline", "-14"]).splitlines()
    # Up-next: FUTURE-IMPROVEMENTS top bullets + open conductor proposals
    fi = [l for l in _lines(REPO / "markdown" / "planning" / "FUTURE-IMPROVEMENTS.md")
          if l.lstrip().startswith(("-", "*", "1.", "2.", "3."))][:6]
    props = []
    for ln in _lines(STATE / "conductor-proposals.jsonl")[-5:]:
        try:
            o = json.loads(ln)
            props.append(str(o.get("title") or o.get("proposal") or o.get("gap") or ln)[:140])
        except Exception:  # noqa: BLE001
            props.append(ln[:140])
    # Loose-ends: STATUS.md known-broken-ish lines + today-bias readiness flags
    broken = [l.strip() for l in _lines(REPO / "automation" / "overnight" / "STATUS.md")[-60:]
              if l.lstrip().startswith("-") and any(k in l.upper() for k in ("BROKEN", "STALE", "FAIL", "OWED"))][-8:]
    flags = bias.get("readiness_flags", []) if isinstance(bias.get("readiness_flags"), list) else []

    out: list[str] = []
    out.append(f"# Session handoff (PAUL) -- {now.strftime('%Y-%m-%d %H:%M ET')}")
    out.append("")
    out.append("> PAUL = **P**rogress / **A**ctive state / **U**p-next / **L**oose-ends. For the next "
               "(Sonnet) session to pick up cold. Auto-generated from LIVE state by `handoff_paul.py` -- "
               "verify anything load-bearing before acting on it (OP-33).")
    out.append("")
    out.append("## P -- Progress (recent commits)")
    out += [f"- `{c}`" for c in commits[:12]] or ["- (no recent commits)"]
    out.append("")
    out.append("## A -- Active state (right now)")
    out.append(f"- **ET {now.strftime('%Y-%m-%d %H:%M')}** -- {mkt}")
    out.append(f"- self-check: **{sc.get('verdict', '?')}** ({len(sc.get('problems', []) or [])} problems)")
    if sc.get("problems"):
        out += [f"  - {p}" for p in sc["problems"][:4]]
    out.append(f"- engine-health: **{eh.get('verdict', '?')}**" + (f" reds={eh.get('reds')}" if eh.get('reds') else ""))
    out.append(f"- today-bias: date=**{bias.get('date', '?')}** bias={bias.get('bias', '?')} "
               f"({'STALE -- premarket may have failed' if bias.get('date') and bias.get('date') != now.strftime('%Y-%m-%d') else 'current'})")
    out.append("")
    out.append("## U -- Up-next (prioritized)")
    out += [f"- {l.lstrip('-*0123456789. ').strip()}" for l in fi] or ["- (FUTURE-IMPROVEMENTS.md empty/unreadable)"]
    if props:
        out.append("- _open conductor proposals:_")
        out += [f"  - {p}" for p in props]
    out.append("")
    out.append("## L -- Loose-ends / known-broken")
    out += [f"- {b.lstrip('- ').strip()}" for b in broken] or ["- (nothing flagged in STATUS.md ## Known broken)"]
    if flags:
        out.append("- _today-bias readiness flags:_")
        out += [f"  - {f}" for f in flags[:6]]
    out.append("")
    out.append("---")
    out.append("_Next session: read this, then `gamma_status.py` for the verified live view before claiming anything works._")
    return "\n".join(out)


if __name__ == "__main__":
    text = build()
    try:
        (STATE / "handoff-latest.md").write_text(text, encoding="utf-8")
    except OSError:
        pass
    print(text)
