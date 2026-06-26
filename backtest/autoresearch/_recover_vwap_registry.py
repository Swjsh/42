"""ONE-SHOT recovery for the vwap-funnel glob bug (2026-06-25).

The single-process funnel's _load_done() globbed 'mass-grind-vwap-funnel-*.jsonl' (dash)
which did not match its own output 'mass-grind-vwap-funnel.jsonl' (no dash) -> it never saw
its own work -> the poll loop re-evaluated all bangers ~12x, writing duplicate rows to the
funnel jsonl AND duplicate _register() rows to the shared STRATEGY-SPACE-REGISTRY.jsonl.

The glob is fixed in mass_grind_vwap_funnel.py + consolidate_elites_vwap.py. This script
repairs the polluted artifacts:
  1. Dedup mass-grind-vwap-funnel.jsonl by label (rows are deterministic -> keep first).
  2. Strip every 'mass-grind-vwap*'-source row this session added to the registry.
  3. Re-add the UNIQUE P3/P4 survivors via the funnel's own _register (no format drift).

Pure file ops, $0. Idempotent (re-running on already-clean files is a no-op-ish rewrite).
Run: backtest/.venv/Scripts/python.exe -m autoresearch._recover_vwap_registry
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

RECO = ROOT / "analysis" / "recommendations"
FUNNEL = RECO / "mass-grind-vwap-funnel.jsonl"
REG = ROOT / "analysis" / "backtests" / "STRATEGY-SPACE-REGISTRY.jsonl"

import autoresearch.mass_grind_vwap_funnel as F  # noqa: E402 — reuse _register (no drift)


def main() -> int:
    # ── 1. dedup the funnel jsonl by label ────────────────────────────────────
    raw = [ln.strip() for ln in FUNNEL.read_text(encoding="utf-8").splitlines() if ln.strip()]
    rows, seen = [], set()
    for ln in raw:
        try:
            r = json.loads(ln)
        except Exception:
            continue
        lbl = r.get("label")
        if lbl and lbl not in seen:
            seen.add(lbl)
            rows.append(r)
    print(f"funnel: {len(raw)} raw rows -> {len(rows)} unique labels")
    print("  verdict dist:", dict(Counter(r.get("verdict") for r in rows)))
    FUNNEL.write_text("\n".join(json.dumps(r, default=str) for r in rows) + "\n", encoding="utf-8")

    # ── 2. strip this session's vwap rows from the shared registry ─────────────
    reg_lines = [ln.strip() for ln in REG.read_text(encoding="utf-8").splitlines() if ln.strip()]
    keep, dropped = [], 0
    for ln in reg_lines:
        try:
            r = json.loads(ln)
        except Exception:
            keep.append(ln)
            continue
        if str(r.get("source", "")).startswith("mass-grind-vwap"):
            dropped += 1
        else:
            keep.append(ln)
    print(f"registry: {len(reg_lines)} rows -> kept {len(keep)} non-vwap, dropped {dropped} vwap")
    REG.write_text("\n".join(keep) + "\n", encoding="utf-8")

    # ── 3. re-add the UNIQUE P3/P4 survivors via the funnel's own _register ────
    added = 0
    for r in rows:
        if r.get("phase_reached", 0) >= 3 and r.get("combo"):
            F._register(r)
            added += 1
    print(f"registry: re-added {added} unique vwap P3/P4 survivors (clean)")

    final = sum(1 for ln in REG.read_text(encoding="utf-8").splitlines() if ln.strip())
    print(f"registry final row count: {final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
