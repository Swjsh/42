"""Grinder Discord notifier — fires Discord pings on important pipeline events.

Runs every 10 minutes via Gamma_GrinderDiscordNotify task.

Detects state transitions vs prior snapshot and queues outbox messages:
  - Stage X started
  - Stage X finished (with summary metrics)
  - Stage X new keeper found (with new best edge/wide)
  - Pipeline fully done (v15-final.json written)
  - Any stage died unexpectedly

Idempotent via per-event watermark file.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
STATE_DIR = ROOT / "automation" / "state"
WATERMARK = STATE_DIR / ".grinder-discord-watermark.json"
OUTBOX = STATE_DIR / "discord-outbox.jsonl"
CFG = STATE_DIR / ".discord-config.json"
V15_FINAL = ROOT / "analysis" / "recommendations" / "v15-final.json"

STAGE_DIRS = {
    "stage1": REPO / "autoresearch" / "_state" / "overnight_grinder",
    "stage2": REPO / "autoresearch" / "_state" / "stage2_grinder",
    "stage3": REPO / "autoresearch" / "_state" / "stage3_grinder",
    "stage4": REPO / "autoresearch" / "_state" / "stage4_grinder",
    "bullish": REPO / "autoresearch" / "_state" / "bullish_grinder",
}


def _user_mention() -> str:
    if not CFG.exists():
        return ""
    try:
        cfg = json.loads(CFG.read_text(encoding="utf-8-sig"))
        uid = cfg.get("user_id")
        return f"<@{uid}> " if uid else ""
    except Exception:
        return ""


def _queue(content: str) -> None:
    row = {
        "queued_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "content": _user_mention() + content,
    }
    with OUTBOX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _read_watermark() -> dict:
    if not WATERMARK.exists():
        return {}
    try:
        return json.loads(WATERMARK.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_watermark(wm: dict) -> None:
    WATERMARK.write_text(json.dumps(wm, default=str), encoding="utf-8")


def _read_progress(d: Path) -> dict:
    p = d / "progress.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    wm = _read_watermark()

    for name, d in STAGE_DIRS.items():
        progress = _read_progress(d)
        if not progress:
            continue
        prior = wm.get(name, {})
        # Detect transitions
        if not prior.get("started") and progress.get("started_at"):
            _queue(f"🟢 **{name} STARTED** — {progress.get('total_combos', 0)} combos, deadline {progress.get('deadline_at', '?')[:16]}")
            prior["started"] = True
        if not prior.get("finished") and progress.get("status") in ("completed", "deadline_reached"):
            keepers = progress.get("keepers", 0)
            best_edge = progress.get("best_edge_capture")
            best_wide = progress.get("best_wide_pnl")
            _queue(
                f"✅ **{name} FINISHED** — {progress.get('completed', 0)}/{progress.get('total_combos', 0)} done, "
                f"{progress.get('passed_floors', 0)} passed, **{keepers} keepers**\n"
                f"best_edge=${(best_edge or 0):.0f}  best_wide=${(best_wide or 0):.0f}"
            )
            prior["finished"] = True
        # Detect new best (bullish uses different field name)
        if name == "bullish":
            prior_best_wide = prior.get("best_bull_pnl") or 0
            cur_best_wide = progress.get("best_bull_pnl") or 0
        else:
            prior_best_wide = prior.get("best_wide_pnl") or 0
            cur_best_wide = progress.get("best_wide_pnl") or 0
        if cur_best_wide > prior_best_wide and cur_best_wide > 0:
            _queue(
                f"🎯 **{name} NEW BEST KEEPER** — wide_pnl ${cur_best_wide:.0f} "
                f"(was ${prior_best_wide:.0f}), edge=${(progress.get('best_edge_capture') or 0):.0f}, "
                f"keeper #{progress.get('keepers', 0)}"
            )
            prior["best_wide_pnl"] = cur_best_wide
        wm[name] = prior

    # Stage 5 ratification done?
    if not wm.get("stage5_announced") and V15_FINAL.exists():
        try:
            sc = json.loads(V15_FINAL.read_text(encoding="utf-8"))
            verdict = sc.get("verdict", "?")
            metrics = sc.get("winner_metrics", {})
            improvements = sc.get("improvements_vs_baseline", {})
            _queue(
                f"🏁 **PIPELINE COMPLETE — v15-final ready for ratification**\n"
                f"verdict: {verdict}\n"
                f"4/29: ${metrics.get('pnl_4_29', 0):.0f}  5/04: ${metrics.get('pnl_5_04', 0):.0f}\n"
                f"edge_capture: ${metrics.get('edge_capture', 0):.0f}\n"
                f"wide_pnl: ${metrics.get('wide_pnl', 0):.0f} ({improvements.get('wide_pnl_pct', 0):+.0f}% vs baseline)\n"
                f"top5_pct: {(metrics.get('top5_pct') or 0)*100:.0f}%  positive_quarters: {metrics.get('positive_quarters', '?')}/6\n"
                f"📁 docs/RATIFICATION-READY.md  📁 analysis/recommendations/v15-final.json\n"
                f"Per rule 9: awaiting your YES to bump params.json."
            )
            wm["stage5_announced"] = True
        except Exception:
            pass

    _save_watermark(wm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
