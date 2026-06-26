"""Operator write-side of the shared activity spine (Jarvis unification, step 1).

The companion's `gamma-companion/lib/activity.js` is the READ side + the
companion's own write side. But the autonomous OPERATOR (conductor, kitchen,
heartbeat) had no way to write the same ledger -- so `gamma-activity.jsonl` only
ever held the companion's own escalations, and the assistant could not see what
the operator was doing. This module is the Python twin of `logActivity()`: it
appends a byte-identical row so the assistant's feed + face context reflect
EVERY operator move.

Row contract (must match activity.js exactly -- one JSON object per line):
    { ts, source, origin, tier, model, cost_usd, action, outcome }
`ts` is stamped HERE (callers never supply it), ISO-8601 UTC with a trailing Z
and millisecond precision, to match JavaScript's Date.toISOString().

Use it two ways:

  # from another Python producer (kitchen_daemon, etc.)
  from automation.scripts.log_activity import log_activity
  log_activity(source="kitchen", origin="auto", tier="kitchen",
               action="cooked candidate", outcome="PROMOTE")

  # from a shell / conductor prompt step
  python automation/scripts/log_activity.py \
      --source conductor --origin auto --tier engine \
      --action "fire complete" --outcome "shipped WP-0 parity test; engine GREEN"

Telemetry MUST NOT crash its caller: every path is defensive and the CLI always
exits 0. Path-anchored to __file__ (never the cwd) per lesson C9.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "automation" / "state" / "gamma-activity.jsonl"
ARCHIVE = ROOT / "automation" / "state" / "gamma-activity.archive.jsonl"
RETENTION_LINES = 5000  # OP-22: every append-only producer has a retention cap


def _utc_iso() -> str:
    """ISO-8601 UTC, millisecond precision, trailing 'Z' -- matches JS toISOString()."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _coerce_str(v):
    return str(v) if v is not None else None


def log_activity(
    source="unknown",
    origin=None,
    tier=None,
    model=None,
    cost_usd=0,
    action=None,
    outcome=None,
    root: Path | None = None,
):
    """Append one spine row. Returns the record dict, or None if the write failed.

    Never raises -- the ledger must not be able to break the thing it observes.
    """
    try:
        ledger = (Path(root) / "automation" / "state" / "gamma-activity.jsonl") if root else LEDGER
        try:
            cost = float(cost_usd)
        except (TypeError, ValueError):
            cost = 0.0
        record = {
            "ts": _utc_iso(),
            "source": _coerce_str(source) if source is not None else "unknown",
            "origin": _coerce_str(origin),
            "tier": _coerce_str(tier),
            "model": _coerce_str(model),
            "cost_usd": cost if cost == cost else 0.0,  # NaN guard
            "action": _coerce_str(action),
            "outcome": _coerce_str(outcome),
        }
        ledger.parent.mkdir(parents=True, exist_ok=True)
        # One write call for the whole line -> atomic enough for a single appender.
        with open(ledger, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        _enforce_retention(ledger)
        return record
    except Exception:
        return None


def _enforce_retention(ledger: Path) -> None:
    """If the ledger exceeds the cap, roll the oldest rows into the archive."""
    try:
        with open(ledger, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
        if len(lines) <= RETENTION_LINES:
            return
        overflow = lines[: len(lines) - RETENTION_LINES]
        keep = lines[len(lines) - RETENTION_LINES :]
        with open(ARCHIVE, "a", encoding="utf-8") as af:
            af.writelines(overflow)
        tmp = ledger.with_suffix(ledger.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as tf:
            tf.writelines(keep)
        os.replace(tmp, ledger)
    except Exception:
        # A failed trim just means the ledger grows a little past the cap; harmless.
        return


def _main(argv) -> int:
    p = argparse.ArgumentParser(description="Append a row to the Gamma activity spine.")
    p.add_argument("--source", default="unknown")
    p.add_argument("--origin", default=None)
    p.add_argument("--tier", default=None)
    p.add_argument("--model", default=None)
    p.add_argument("--cost", dest="cost_usd", default=0)
    p.add_argument("--action", default=None)
    p.add_argument("--outcome", default=None)
    try:
        a = p.parse_args(argv)
        rec = log_activity(
            source=a.source,
            origin=a.origin,
            tier=a.tier,
            model=a.model,
            cost_usd=a.cost_usd,
            action=a.action,
            outcome=a.outcome,
        )
        if rec is None:
            print("log_activity: write failed (non-fatal)", file=sys.stderr)
    except SystemExit:
        # argparse error -- still must not break a caller that shelled out.
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"log_activity: {exc} (non-fatal)", file=sys.stderr)
    return 0  # telemetry never fails its caller


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
