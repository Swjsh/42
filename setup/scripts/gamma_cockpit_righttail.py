"""gamma_cockpit_righttail.py -- cockpit tile builder for GOAL-RIGHT-TAIL-
CAPTURE-2026-09-05 R5.

Reads analysis/right-tail/ledger.jsonl (written daily by
setup/scripts/right_tail_capture.py, fired by Gamma_RightTailCapture 16:20 ET)
and rolls it up to a 20-SESSION per-arm capture rate + the count of waves
flagged `would_be_refused_under_cap4` (the TIGHT-LADDER forward-ledger
question the 09-29 checkpoint needs) -- rendered on the cockpit's Engine/Rig
tile group (ProducerTiles "Right-tail capture" tile).

READ-ONLY. Fail-open: a missing/empty ledger returns ok:False with a NO-DATA
`say`, never raises, never fabricates a number.

CONTRACT (fixed -- dashboard/components/cockpit/producer-tiles.tsx renders
directly off this):
    build(path=None, sessions=20) -> {
        ok, path, stamp_et, verdict ("green"/"amber"/"off"),
        sessions_counted, per_arm: {arm: {n_waves, n_taken, capture_rate, top_mechanism}},
        book_capture_rate, cap4_would_refuse_count,
        say,
    }

`top_mechanism` (added GOAL-FLEET-CAPTURE-GAP-2026-09-05 F5) is the most frequent
`refused_by_gate` code (text before ':') among this arm's missed waves in the trailing
window, e.g. "GATE" / "HOLD" / "SKIP_MIN_PREMIUM_FLOOR" / "NOT_FLAT" -- None when the
arm has no missed waves in the window. Purely descriptive (not a mechanism-number
lookup -- see analysis/right-tail/CAPTURE-GAP-2026-09-05.json for the full 1-8
classification); additive field, does not change any existing key's shape.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
DEFAULT_PATH = REPO / "analysis" / "right-tail" / "ledger.jsonl"
ARMS = ["safe-2", "bold-2", "safe-3", "risky-1"]

sys.path.insert(0, str(Path(__file__).resolve().parent))
from et_clock import et_now  # noqa: E402


def _stamp_et() -> str:
    try:
        return et_now().strftime("%Y-%m-%d %H:%M:%S ET")
    except Exception:
        return ""


def build(path: Path | None = None, sessions: int = 20) -> dict[str, Any]:
    p = path or DEFAULT_PATH
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError):
        return {
            "ok": False, "path": str(p), "stamp_et": _stamp_et(), "verdict": "off",
            "sessions_counted": 0, "per_arm": {}, "book_capture_rate": None,
            "cap4_would_refuse_count": 0,
            "say": f"NO DATA -- {p.name} not found (Gamma_RightTailCapture has not fired yet)",
        }

    rows: list[dict[str, Any]] = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError:
            continue

    if not rows:
        return {
            "ok": False, "path": str(p), "stamp_et": _stamp_et(), "verdict": "off",
            "sessions_counted": 0, "per_arm": {}, "book_capture_rate": None,
            "cap4_would_refuse_count": 0,
            "say": "NO DATA -- ledger is empty",
        }

    dates = sorted({r.get("date") for r in rows if r.get("date")})
    trailing_dates = set(dates[-sessions:])

    per_arm: dict[str, dict[str, Any]] = {a: {"n_waves": 0, "n_taken": 0} for a in ARMS}
    mechanism_counts: dict[str, dict[str, int]] = {a: {} for a in ARMS}
    cap4_count = 0
    for r in rows:
        if r.get("date") not in trailing_dates:
            continue
        arm = r.get("arm")
        if arm not in per_arm:
            continue
        if "taken" in r:  # a wave_event row, not a second_wave_summary row
            per_arm[arm]["n_waves"] += 1
            if r.get("taken"):
                per_arm[arm]["n_taken"] += 1
            elif r.get("refused_by_gate"):
                code = str(r["refused_by_gate"]).split(":", 1)[0].strip()
                mechanism_counts[arm][code] = mechanism_counts[arm].get(code, 0) + 1
            if r.get("would_be_refused_under_cap4"):
                cap4_count += 1

    for arm, d in per_arm.items():
        d["capture_rate"] = round(d["n_taken"] / d["n_waves"], 4) if d["n_waves"] else None
        counts = mechanism_counts[arm]
        d["top_mechanism"] = max(counts, key=counts.get) if counts else None

    total_waves = sum(d["n_waves"] for d in per_arm.values())
    total_taken = sum(d["n_taken"] for d in per_arm.values())
    book_rate = round(total_taken / total_waves, 4) if total_waves else None

    if book_rate is None:
        verdict = "off"
    elif book_rate >= 0.75:
        verdict = "green"
    elif book_rate >= 0.5:
        verdict = "amber"
    else:
        verdict = "red"

    say = (
        f"{len(trailing_dates)}-session book capture {book_rate * 100:.0f}%"
        if book_rate is not None else "NO DATA -- no waves in trailing window"
    ) + (f", {cap4_count} cap-4 would-refuse flags" if cap4_count else "")

    return {
        "ok": True, "path": str(p), "stamp_et": _stamp_et(), "verdict": verdict,
        "sessions_counted": len(trailing_dates),
        "per_arm": per_arm,
        "book_capture_rate": book_rate,
        "cap4_would_refuse_count": cap4_count,
        "say": say,
    }


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, default=str))
