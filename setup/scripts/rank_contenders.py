"""rank_contenders.py — rank the grind/sweep contenders by the J-edge bar. $0 pure-python.

READ-ONLY on analysis/recommendations/mass-grind-progress.jsonl (the live sweep writes
it; we only read). Ranks every scored contender against the OP-16 doctrine:
  * edge_capture >= 771  (50% of the 1542 J-edge max — the hard reject floor)
  * not op16_reject
  * expectancy > 0       (positive per-trade)
  * wf (walk-forward) >= 0.70 preferred
Writes a ranked shortlist to analysis/recommendations/contender-rank-{date}.json and a
one-glance summary. Flags PROFITABLE survivors (clear the floor + positive) to the
Discord outbox so J hears about money, not noise.

Safe to run while the sweep is still going — it just reports "N of M so far".

OP-33 honesty gate (2026-07-01): if the input hasn't changed since the last output,
this writes NOTHING and logs SKIP_UNCHANGED — a frozen sweep must never restamp
contender-rank-{date}.json into fake "fresh research" (6 days of byte-identical
rewrites, 06-26..07-01).
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1].parent
GRIND = REPO / "analysis" / "recommendations" / "mass-grind-progress.jsonl"
STATE = REPO / "automation" / "state"
OUTBOX = STATE / "discord-outbox.jsonl"
RANK_STATE = REPO / "analysis" / "recommendations" / ".contender-rank-input-state.json"

J_EDGE_FLOOR = 771.0   # OP-16: 50% of the 1542 max edge_capture; below = REJECT
WF_PREF = 0.70

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _et_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=-4)


def _flag(msg: str) -> None:
    try:
        with open(OUTBOX, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "source": "rank_contenders", "alert": msg[:500]}) + "\n")
    except OSError:
        pass


def _num(v):
    return v if isinstance(v, (int, float)) else None


def load() -> list[dict]:
    if not GRIND.exists():
        return []
    out = []
    for line in GRIND.read_text(encoding="utf-8", errors="replace").strip().splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def rank():
    rows = load()
    scored = [r for r in rows if _num(r.get("edge_capture")) is not None]
    # Survivors: clear the J-edge floor, not OP-16-rejected, positive expectancy
    survivors = []
    for r in scored:
        ec = _num(r.get("edge_capture"))
        exp = _num(r.get("expectancy"))
        if ec is None or ec < J_EDGE_FLOOR:
            continue
        if r.get("op16_reject"):
            continue
        if exp is not None and exp <= 0:
            continue
        survivors.append(r)
    survivors.sort(key=lambda r: _num(r.get("edge_capture")) or 0, reverse=True)

    def slim(r):
        return {k: r.get(k) for k in ("label", "edge_capture", "expectancy", "wr",
                                      "trades_per_day", "max_dd", "wf", "n", "combo")}

    top = [slim(r) for r in survivors[:15]]
    wf_strong = [s for s in top if (_num(s.get("wf")) or -9) >= WF_PREF]
    out = {
        "ranked_at_et": _et_now().strftime("%Y-%m-%d %H:%M"),
        "total_scored": len(scored),
        "total_rows": len(rows),
        "survivors_over_floor": len(survivors),
        "j_edge_floor": J_EDGE_FLOOR,
        "wf_pref": WF_PREF,
        "top": top,
        "n_wf_strong": len(wf_strong),
        "note": "READ-ONLY snapshot; the sweep may still be running (partial).",
    }
    dest = REPO / "analysis" / "recommendations" / f"contender-rank-{_et_now():%Y-%m-%d}.json"
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"scored {len(scored)}/{len(rows)} | survivors over {J_EDGE_FLOOR:.0f} floor: "
          f"{len(survivors)} | WF>={WF_PREF}: {len(wf_strong)}")
    for s in top[:6]:
        ec, exp, wf = s.get("edge_capture"), s.get("expectancy"), s.get("wf")
        print(f"  edge={ec:.0f} exp={exp} wf={wf} wr={s.get('wr')} :: {str(s.get('label'))[:55]}")
    if wf_strong:
        best = wf_strong[0]
        _flag(f"PROFITABLE contender: {best.get('label')} edge_capture={best.get('edge_capture'):.0f} "
              f"expectancy={best.get('expectancy')} wf={best.get('wf')} "
              f"({len(survivors)} clear the {J_EDGE_FLOOR:.0f} floor so far)")
    return out


def _input_fingerprint() -> dict:
    """Fingerprint the GRIND input so an untouched sweep never restamps output."""
    if not GRIND.exists():
        return {"sha256": None, "mtime": None, "size": None}
    st = GRIND.stat()
    return {"sha256": hashlib.sha256(GRIND.read_bytes()).hexdigest(),
            "mtime": st.st_mtime, "size": st.st_size}


def main():
    """Rank only when the input actually changed; otherwise write NOTHING."""
    fp = _input_fingerprint()
    prev = None
    if RANK_STATE.exists():
        try:
            prev = json.loads(RANK_STATE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prev = None
    if prev is not None and fp["sha256"] == prev.get("sha256"):
        if fp["mtime"] is not None:
            frozen = datetime.fromtimestamp(fp["mtime"], tz=timezone.utc) + timedelta(hours=-4)
            since = frozen.strftime("%Y-%m-%d %H:%M ET")
        else:
            since = "never (input missing)"
        print(f"SKIP_UNCHANGED (input frozen since {since})")
        return None
    out = rank()
    try:
        RANK_STATE.write_text(json.dumps(fp), encoding="utf-8")
    except OSError:
        pass
    return out


if __name__ == "__main__":
    main()
