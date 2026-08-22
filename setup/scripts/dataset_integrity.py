"""Content-hash integrity for the frozen datasets studies stand on.

WHY THIS EXISTS. On 2026-08-15 `engine-fullhist-replay-2026-07-23.json` was found to have gone
from its published +$5,064.75 / 190 trades to +$4,808.75 / 191 -- one losing row added by
`df0348d9`, a regime-threshold commit with no business touching a replay artifact. Nothing
announced it. Three downstream tests went RED and were nearly dismissed as stale pins, and one
study (ENTRY-LOCATION-GATE) read the mutated file and published the wrong population size.

Independently, `trail_width_exit_ab`'s frozen population turned out to be OPRA-cache-dependent
and had silently grown 113 -> 284. Two findings, one root: **this repo had no integrity check on
the datasets its studies stand on**, so an out-of-band edit was invisible at the point of USE.

WHAT THIS DOES. Records a content hash + record count per frozen dataset in a manifest, and
verifies on demand. `verify()` is importable so a runner can assert integrity BEFORE computing
anything -- failing at the point of use, not three tests later.

DELIBERATELY NOT a git check. The 190->191 edit WAS committed, cleanly, by a passing build. Git
says "a file changed"; this says "the dataset a published conclusion rests on is no longer the
one it rested on", which is the question that actually matters.

Read-only apart from the manifest. Exit 0 on verify-pass, 1 on drift (so a caller can gate).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "analysis" / "recommendations" / "_dataset-manifest.json"

# Frozen datasets that published conclusions rest on. Add a row when a study freezes a
# population; the point is that this list is SHORT and every entry is load-bearing.
TRACKED: dict[str, str] = {
    "analysis/recommendations/engine-fullhist-replay-2026-07-23.json":
        "18-month full-engine replay; the population for structure_shift_cascade, "
        "regime_reslice, pnl_attribution, ENTRY-LOCATION-GATE and ENTRY-RANGE-CONTEXT",
    "analysis/trendlines/break-dataset-summary.json":
        "unconditional trendline-break baseline; TRENDLINE-BREAK-AT-LEVEL's G1 control",
    "analysis/pain-ledger/mae-mfe.json":
        "MAE/MFE scored positions; ribbon_flipback_ab_v2's frozen 219-row population "
        "(APPEND-ONLY -- tracked by frozen-prefix count, see APPEND_ONLY below)",
}

# APPEND-ONLY datasets: rel -> the number of leading records that are FROZEN.
#
# The manifest has claimed "tracked by frozen-prefix count" since 2026-08-15, but verify()
# only ever compared a WHOLE-FILE hash -- so this file DRIFTED every single trading day the
# producer appended to it (303 -> 350 by 2026-08-21), and the nightly suite carried a
# permanent RED that meant "we traded today". A guard that fires on normal operation is one
# everybody learns to skip, which is exactly how the 190->191 replay corruption nearly got
# waved through as a stale pin.
#
# What actually needs protecting is the FROZEN PREFIX a published conclusion stands on --
# ribbon_flipback_ab_v2's first 219 rows. Later rows are new trades, not tampering. So the
# prefix is hashed and the tail is allowed to grow; shrinking, reordering or editing any
# frozen row still DRIFTS.
APPEND_ONLY: dict[str, int] = {
    "analysis/pain-ledger/mae-mfe.json": 219,
}


def _records(obj: Any) -> "int | None":
    """Best-effort record count -- the number a human would quote as 'n'."""
    if isinstance(obj, list):
        return len(obj)
    if isinstance(obj, dict):
        for k in ("trades", "rows", "positions", "records", "entries"):
            v = obj.get(k)
            if isinstance(v, list):
                return len(v)
    return None


def fingerprint(rel: str) -> dict:
    p = REPO / rel
    if not p.exists():
        return {"present": False}
    raw = p.read_bytes()
    out: dict[str, Any] = {
        "present": True,
        # hash the PARSED-then-recanonicalised content, so reformatting/whitespace does not
        # read as a data change while a real row edit always does.
        "sha256_16": None,
        "bytes": len(raw),
        "n_records": None,
    }
    try:
        obj = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        out["sha256_16"] = hashlib.sha256(raw).hexdigest()[:16]
        out["note"] = "not JSON -- raw byte hash"
        return out
    canon = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    out["sha256_16"] = hashlib.sha256(canon).hexdigest()[:16]
    out["n_records"] = _records(obj)
    n_frozen = APPEND_ONLY.get(rel)
    if n_frozen is not None:
        out["frozen_prefix_n"] = n_frozen
        out["frozen_prefix_sha256_16"] = _prefix_hash(obj, n_frozen)
    return out


def _record_list(obj: Any) -> "list | None":
    """The record list itself -- same key order _records() counts."""
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("trades", "rows", "positions", "records", "entries"):
            v = obj.get(k)
            if isinstance(v, list):
                return v
    return None


def _prefix_hash(obj: Any, n: int) -> "str | None":
    """Canonical hash of the FIRST n records. None when the file is too short.

    Too-short is NOT silently OK: verify() treats a missing prefix hash as DRIFTED,
    because a file that can no longer produce its own frozen prefix has been truncated.
    """
    rows = _record_list(obj)
    if rows is None or len(rows) < n:
        return None
    canon = json.dumps(rows[:n], sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canon).hexdigest()[:16]


def load_manifest() -> dict:
    if not MANIFEST.exists():
        return {"datasets": {}}
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except ValueError:
        return {"datasets": {}}


def verify(strict_paths: "list[str] | None" = None) -> dict:
    """Compare every tracked dataset against the manifest. Never raises."""
    man = load_manifest().get("datasets", {})
    results = {}
    for rel in (strict_paths or list(TRACKED)):
        now = fingerprint(rel)
        was = man.get(rel)
        if was is None:
            results[rel] = {"status": "UNRECORDED", "now": now}
        elif not now.get("present"):
            results[rel] = {"status": "MISSING", "was": was}
        elif rel in APPEND_ONLY:
            # Append-only: the frozen prefix must be byte-identical and the file must not
            # shrink. Growth past the prefix is the producer doing its job.
            pre_now, pre_was = now.get("frozen_prefix_sha256_16"), was.get("frozen_prefix_sha256_16")
            grew = (now.get("n_records") or 0) >= (was.get("n_records") or 0)
            if pre_now is None:
                results[rel] = {"status": "DRIFTED", "was": was, "now": now,
                                "reason": f"file can no longer produce its frozen "
                                          f"{APPEND_ONLY[rel]}-record prefix -- truncated?"}
            elif pre_was is not None and pre_now != pre_was:
                results[rel] = {"status": "DRIFTED", "was": was, "now": now,
                                "reason": "the FROZEN PREFIX changed -- a published "
                                          "population was edited, not merely appended to"}
            elif not grew:
                results[rel] = {"status": "DRIFTED", "was": was, "now": now,
                                "reason": "append-only dataset SHRANK"}
            else:
                results[rel] = {"status": "OK", "sha256_16": now["sha256_16"],
                                "n_records": now.get("n_records"),
                                "append_only_prefix_n": APPEND_ONLY[rel],
                                "appended_since_record": (now.get("n_records") or 0)
                                                         - (was.get("n_records") or 0)}
        elif now["sha256_16"] != was.get("sha256_16"):
            results[rel] = {
                "status": "DRIFTED", "was": was, "now": now,
                "n_records_delta": (None if now.get("n_records") is None
                                    or was.get("n_records") is None
                                    else now["n_records"] - was["n_records"]),
            }
        else:
            results[rel] = {"status": "OK", "sha256_16": now["sha256_16"],
                            "n_records": now.get("n_records")}
    return results


def assert_intact(rel: str) -> None:
    """For runners: fail LOUDLY at the point of use, before computing anything.

    A study that silently reads a mutated population publishes a wrong number under a frozen
    prereg's authority. That is worse than not running.
    """
    r = verify([rel])[rel]
    if r["status"] not in ("OK", "UNRECORDED"):
        raise RuntimeError(
            f"DATASET INTEGRITY: {rel} is {r['status']} vs the recorded manifest "
            f"({r}). A published conclusion rests on this file. Resolve before computing.")


def record(rel_paths: "list[str] | None" = None) -> dict:
    man = load_manifest()
    man.setdefault("_doc", "Content hashes for frozen research datasets. Written by "
                           "setup/scripts/dataset_integrity.py --record. A DRIFT here means a "
                           "published conclusion's population changed after publication.")
    ds = man.setdefault("datasets", {})
    for rel in (rel_paths or list(TRACKED)):
        fp = fingerprint(rel)
        fp["purpose"] = TRACKED.get(rel, "")
        ds[rel] = fp
    MANIFEST.write_text(json.dumps(man, indent=1), encoding="utf-8")
    return ds


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--record" in sys.argv:
        ds = record()
        print(f"recorded {len(ds)} dataset fingerprints -> "
              f"{MANIFEST.relative_to(REPO).as_posix()}")
        for rel, fp in ds.items():
            print(f"  {fp.get('sha256_16')}  n={fp.get('n_records')}  {rel}")
        return 0
    res = verify()
    bad = {k: v for k, v in res.items() if v["status"] not in ("OK", "UNRECORDED")}
    for rel, r in res.items():
        mark = {"OK": "OK   ", "UNRECORDED": "NEW  ", "DRIFTED": "DRIFT", "MISSING": "GONE "}[r["status"]]
        extra = ""
        if r["status"] == "DRIFTED":
            extra = (f"  n {r['was'].get('n_records')} -> {r['now'].get('n_records')}"
                     f"  ({r['was'].get('sha256_16')} -> {r['now'].get('sha256_16')})")
        elif r["status"] == "OK":
            extra = f"  n={r['n_records']}"
        print(f"  [{mark}] {rel}{extra}")
    if bad:
        print(f"\n{len(bad)} dataset(s) DRIFTED or MISSING -- a published conclusion's "
              "population changed after publication.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
