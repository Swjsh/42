"""One-shot script to bulk-dismiss noisy HARVEST queue items.

Removes from automation/overnight/queue.md:
1. All HARVEST-FOOTGUN items where |close_drift| < 500 BTC cents
2. All HARVEST-SRCDISAGREE items (v02 KNOWN_FLAKY per OP-26)
3. Keeps HARVEST-RSIEXTREME, HARVEST-RIBBONFLIP, HARVEST-VOLSPIKE, HARVEST-SWEEP
4. Keeps HARVEST-FOOTGUN items with |close_drift| >= 500 BTC cents

These items represent normal operation of the closed-bar filter — the filter is
working correctly. Sub-threshold catches don't need individual investigation.
The gym harvester has been patched (FOOT_GUN_MIN_DRIFT_CENTS=500) so this
cleanup is a one-shot for the existing backlog.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
QUEUE_PATH = REPO / "automation" / "overnight" / "queue.md"

DRIFT_PATTERN = re.compile(r"close_drift_naive_vs_filtered=([+-]?\d+(?:\.\d+)?)")


def should_dismiss(line: str) -> bool:
    """Return True if this queue item is noise that should be removed."""
    if "HARVEST-SRCDISAGREE" in line:
        return True
    if "HARVEST-FOOTGUN" in line:
        m = DRIFT_PATTERN.search(line)
        if m:
            drift = abs(float(m.group(1)))
            if drift < 500.0:
                return True
        else:
            # No drift value found — keep it (can't assess)
            return False
    return False


def main() -> None:
    text = QUEUE_PATH.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    kept = []
    dismissed_count = 0
    for line in lines:
        if should_dismiss(line):
            dismissed_count += 1
        else:
            kept.append(line)

    if dismissed_count == 0:
        print("No noise harvest items found. Queue is already clean.")
        return

    QUEUE_PATH.write_text("".join(kept), encoding="utf-8")
    print(f"Dismissed {dismissed_count} noise HARVEST items from queue.md")
    print("  - HARVEST-FOOTGUN with |close_drift| < 500 BTC cents: removed")
    print("  - HARVEST-SRCDISAGREE (v02 KNOWN_FLAKY): removed")
    print("  Gym harvester patched to prevent re-generation (FOOT_GUN_MIN_DRIFT_CENTS=500)")


if __name__ == "__main__":
    main()
