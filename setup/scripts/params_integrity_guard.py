"""params_integrity_guard.py — RULE-9 DETECTOR (not a blocker) for mid-session params
mutation. Closes RULE-ENGINE-ALIGNMENT-2026-08-18.md finding #1.

THE GAP THIS CLOSES: Rule 9 ("No mid-session rule changes. Rules update on weekends, in
writing, with documented reason") is currently HONOUR-SYSTEM ONLY — heartbeat_core.py
re-reads params.json fresh from disk on EVERY tick (run_account(): `params =
json.loads(cfg["params"].read_text(...))`, heartbeat_core.py ~L1454), so a same-day edit
takes live effect within about one minute, and nothing detects or reports it.

WHY DETECT, NOT BLOCK (state this tradeoff explicitly, per the fix instructions): this
rig's OP-32 scar is a market-hours guard that locked J out of his own system — a firewall
that ended up blocking J's OWN intentional intervention, not just a bug. Guards on this
codebase MUST fail open and must NEVER prevent J's own deliberate mid-session edit from
taking effect (CLAUDE.md OP-25: "Guards MUST fail open — never kill/block J's interactive
session"). So this module ONLY ever observes and reports; it never refuses a tick, never
denies an order, never mutates params back. The fix for Rule 9 is VISIBILITY — nothing
silently changes mid-session without a loud, dated, per-key record — not enforcement.
Enforcement (e.g. refusing to trade on drift) would be a separate, deliberate, J-approved
follow-up, not something a detector should decide unilaterally.

MECHANISM: heartbeat_core.py's main() runs ONCE per Task Scheduler fire (~1/min RTH), not
as a persistent daemon, so "first tick of the session" cannot be held in memory — it is
recovered from a persisted snapshot file (SNAPSHOT_PATH), keyed by ET calendar date. On the
first RTH tick of a new ET session, this module hashes each watched params/gate-config file
and stores the hash plus a full parsed key/value snapshot. On every subsequent tick THAT
SAME session, it re-hashes only — cheap, this runs on the hot path once a minute during
market hours: N small file reads + sha256, no JSON parse, no diff — and compares against the
stored hash. A hash match is the overwhelmingly common case. Only on a MISMATCH does it pay
for a full JSON parse + per-key diff (added/changed/removed), because that branch should be
rare (ideally zero on almost every real session) and this is exactly where the extra cost is
justified by the value of a precise "which knob moved" answer instead of "something changed".

SURFACES REUSED (do not invent a new one — the fix's own instruction): the two existing
operator-visible surfaces this codebase already funnels detector findings into (see
setup/scripts/self_check.py `_alert`, the established pattern for "a detector found
something, tell the operator"):
  1. automation/overnight/STATUS.md — appended block, always (unthrottled), so the
     permanent written record exists even if nobody is watching Discord right now.
  2. automation/state/discord-outbox.jsonl — one JSON line, same schema self_check.py
     already writes ({"ts","channel","source","message"}), so whatever already drains
     this file to Discord picks this up with zero new wiring.
It also logs a loud, distinctly-typed row into the CORE decision ledger
(automation/state/core-decisions.jsonl, via the SAME heartbeat_core._log() every tick row
already uses — passed in as log_fn) tagged `"event": "RULE9_PARAMS_CHANGED_MID_SESSION"`,
trivially greppable/filterable from the ~1/min normal tick rows.

RE-ALERT DISCIPLINE: after an alert fires for a given file, this module's OWN stored
hash/values for THAT file are rolled forward to the new (changed) state — so the identical
drift can never re-fire on the next tick (self_check.py had to retrofit a time-window
suppression to stop exactly this "identical alert re-sent every ~30 min for 12 hours"
failure mode on 2026-08-17; this module avoids the whole class structurally instead of by a
timer — only a GENUINELY NEW change can ever trigger a second alert). The full day's
mutation history still survives in the snapshot's own `change_events` list, so an
end-of-day read shows every mutation, not just the latest.

Guard: backtest/tests/test_params_integrity_guard_2026_08_18.py.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"

# The 3 params/gate-config surfaces the live path reads (core safe, core bold, fleet gate
# config) — RULE-ENGINE-ALIGNMENT-2026-08-18.md finding #1's explicit scope.
WATCHED_FILES: dict[str, Path] = {
    "core_safe": STATE / "params.json",
    "core_bold": STATE / "aggressive" / "params.json",
    "fleet_accounts": STATE / "fleet" / "accounts.json",
}

SNAPSHOT_PATH = STATE / "params-integrity.json"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"
DISCORD_OUTBOX = STATE / "discord-outbox.jsonl"


def _hash_bytes(path: Path) -> Optional[str]:
    """sha256 hex digest of the file's raw bytes, or None if unreadable/missing. Fail-open:
    a missing/unreadable file is not itself treated as "changed" this tick — it simply
    can't be hashed (the same non-answer a fresh disk read would give anyway)."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _flat_diff(old: dict, new: dict) -> dict:
    """Per-key diff: added / removed / changed(old,new). Top-level keys only — these params
    files are flat-ish key:value config, and a top-level key NAME is exactly what an
    operator needs to answer "which knob moved" (the audit's own complaint: "'params
    changed' is nearly useless at 15:55 when you need to know WHICH knob moved")."""
    old = old or {}
    new = new or {}
    added = {k: new[k] for k in new.keys() - old.keys()}
    removed = {k: old[k] for k in old.keys() - new.keys()}
    changed = {k: {"old": old[k], "new": new[k]}
               for k in old.keys() & new.keys() if old[k] != new[k]}
    return {"added": added, "removed": removed, "changed": changed}


def _read_snapshot(snapshot_path: Path) -> dict:
    try:
        return json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_snapshot(snapshot_path: Path, snap: dict) -> None:
    try:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = snapshot_path.with_name(snapshot_path.name + ".tmp")
        tmp.write_text(json.dumps(snap, indent=2), encoding="utf-8")
        os.replace(tmp, snapshot_path)  # atomic — same pattern as heartbeat_core._write_tick_marker
    except OSError:
        pass


def _surface(status_md: Path, discord_outbox: Path, watched_files: dict[str, Path],
             ts_et: str, file_changes: dict) -> None:
    """Append the loud, distinct alert to the two existing operator-visible surfaces —
    reused verbatim, nothing new invented (see module docstring). Fail-open: a write
    failure here must never raise into the caller's live tick."""
    lines = [f"\n### RULE9 PARAMS CHANGED MID-SESSION: {ts_et}\n"]
    msg_parts = []
    for name, diff in file_changes.items():
        changed_keys = sorted(diff["changed"].keys())
        added_keys = sorted(diff["added"].keys())
        removed_keys = sorted(diff["removed"].keys())
        lines.append(f"- **{name}** (`{watched_files[name]}`)\n")
        for k in changed_keys:
            old_v = diff["changed"][k]["old"]
            new_v = diff["changed"][k]["new"]
            lines.append(f"  - CHANGED `{k}`: `{old_v!r}` -> `{new_v!r}`\n")
        for k in added_keys:
            lines.append(f"  - ADDED `{k}` = `{diff['added'][k]!r}`\n")
        for k in removed_keys:
            lines.append(f"  - REMOVED `{k}` (was `{diff['removed'][k]!r}`)\n")
        if changed_keys or added_keys or removed_keys:
            msg_parts.append(f"{name}: {len(changed_keys)} changed/"
                              f"{len(added_keys)} added/{len(removed_keys)} removed")
    lines.append("\nDetector: setup/scripts/params_integrity_guard.py "
                  "(DETECTS ONLY — never blocks a tick; see module docstring for why).\n")
    try:
        status_md.parent.mkdir(parents=True, exist_ok=True)
        with status_md.open("a", encoding="utf-8") as f:
            f.writelines(lines)
    except OSError:
        pass
    try:
        discord_outbox.parent.mkdir(parents=True, exist_ok=True)
        with discord_outbox.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": ts_et, "channel": "gamma-ops", "source": "params_integrity_guard",
                "message": "RULE9 PARAMS CHANGED MID-SESSION: " + "; ".join(msg_parts)[:500],
            }) + "\n")
    except OSError:
        pass


def _paths_for(state_dir: Optional[Path]) -> tuple[dict[str, Path], Path, Path, Path]:
    """Resolve (watched_files, snapshot_path, status_md, discord_outbox) for this call.

    HERMETICITY CONTRACT (2026-08-18, caught by test_fleet_tick_pairing_race_2026_08_01.py
    going RED on first wiring): heartbeat_core.py's own STATE constant is exactly what its
    test suite monkeypatches to a tmp_path for hermetic runs of main()/run_account() (e.g.
    `monkeypatch.setattr(hc, "STATE", tmp_path)`) — but this module's WATCHED_FILES/
    SNAPSHOT_PATH/etc. are independently REPO-anchored globals in a SEPARATE module
    namespace, so patching hc.STATE does nothing to them. The first wiring pass called
    check() with no state awareness at all, so every test that drives heartbeat_core.main()
    silently did REAL file I/O against production automation/state/params.json,
    automation/overnight/STATUS.md and automation/state/discord-outbox.jsonl — exactly the
    "no ledger leak from tests" failure class this codebase has its own dedicated guard for
    (test_no_ledger_leak_from_tests_2026_08_06.py).

    Fix: heartbeat_core.main() passes its OWN (test-overridable) `STATE` global as
    `state_dir` on every call — a live name lookup at call time, so it correctly sees
    whatever the current test monkeypatched it to. When `state_dir` is given, every path
    this module touches is derived from it (mirroring the real repo's own automation/state
    + automation/overnight sibling layout); when omitted (standalone/direct use — this
    module's own test file exercises it exactly this way), the module-level globals apply
    unchanged."""
    if state_dir is None:
        return WATCHED_FILES, SNAPSHOT_PATH, STATUS_MD, DISCORD_OUTBOX
    watched = {
        "core_safe": state_dir / "params.json",
        "core_bold": state_dir / "aggressive" / "params.json",
        "fleet_accounts": state_dir / "fleet" / "accounts.json",
    }
    snapshot_path = state_dir / "params-integrity.json"
    discord_outbox = state_dir / "discord-outbox.jsonl"
    # automation/overnight is automation/state's sibling in the real layout; a test's flat
    # tmp_path has no such sibling, so this simply resolves to a path that is never written
    # (_surface's own try/except OSError already fails open on a missing parent dir) — never
    # the real production STATUS.md.
    status_md = state_dir.parent / "overnight" / "STATUS.md"
    return watched, snapshot_path, status_md, discord_outbox


def check(et: datetime, log_fn: Optional[Callable[[dict], None]] = None, *,
          state_dir: Optional[Path] = None) -> dict:
    """Call ONCE per tick from heartbeat_core.main() (only reached on an RTH tick — main()
    already early-returns on a non-RTH invocation, which is exactly "first tick of the
    session" / "every subsequent tick that session" scoping for free). heartbeat_core.py
    passes `state_dir=STATE` (its own global) so a test that monkeypatches hc.STATE
    automatically makes this detector hermetic too — see _paths_for's docstring.

    Cheap on the hot (no-change) path: len(watched_files) small file reads + sha256, one
    snapshot-file read, zero JSON parses, zero diffing. Only the rare mismatch path pays for
    a full parse+diff. Never raises — this is a visibility instrument; it must never break
    the tick it's watching (fail-open, see module docstring)."""
    try:
        watched_files, snapshot_path, status_md, discord_outbox = _paths_for(state_dir)
        session_date = et.strftime("%Y-%m-%d")
        ts_et = et.strftime("%Y-%m-%dT%H:%M:%S")
        snap = _read_snapshot(snapshot_path)
        current_hashes = {name: _hash_bytes(path) for name, path in watched_files.items()}

        stale_session = snap.get("date") != session_date
        missing_baseline = any(name not in (snap.get("hashes") or {}) for name in watched_files)
        if stale_session or missing_baseline:
            # First tick of a (possibly brand-new) ET session — take the baseline. A stale
            # (prior-day) session's snapshot is intentionally NOT compared against — a
            # cross-day difference is exactly the "rules update on weekends, in writing"
            # case Rule 9 permits, never a mid-session mutation.
            values = {name: _load_json(path) for name, path in watched_files.items()}
            new_snap = {
                "date": session_date, "ts_et": ts_et,
                "hashes": current_hashes, "values": values,
                "change_events": (snap.get("change_events") or []) if not stale_session else [],
            }
            _write_snapshot(snapshot_path, new_snap)
            return {"status": "SNAPSHOT_TAKEN", "changed": []}

        prior_hashes = snap.get("hashes") or {}
        changed_files = [name for name in watched_files
                          if current_hashes.get(name) != prior_hashes.get(name)]
        if not changed_files:
            return {"status": "OK", "changed": []}

        # Rare path: a real mismatch this session. Pay for parse + per-key diff now.
        prior_values = snap.get("values") or {}
        file_changes: dict = {}
        for name in changed_files:
            new_values = _load_json(watched_files[name])
            diff = _flat_diff(prior_values.get(name) or {}, new_values)
            file_changes[name] = diff
            # Roll the baseline forward so the SAME drift can never re-fire next tick —
            # only a genuinely new subsequent change will.
            snap.setdefault("hashes", {})[name] = current_hashes[name]
            snap.setdefault("values", {})[name] = new_values

        event = {"ts_et": ts_et, "event": "RULE9_PARAMS_CHANGED_MID_SESSION",
                  "files": changed_files, "diff": file_changes}
        if log_fn is not None:
            try:
                log_fn(event)
            except Exception:  # noqa: BLE001 — ledger write must never break the tick
                pass
        _surface(status_md, discord_outbox, watched_files, ts_et, file_changes)

        snap["change_events"] = list(snap.get("change_events") or []) + [event]
        _write_snapshot(snapshot_path, snap)
        return {"status": "CHANGED", "changed": changed_files, "diff": file_changes}
    except Exception:  # noqa: BLE001 — visibility instrument must never break a live tick
        return {"status": "ERROR", "changed": []}
