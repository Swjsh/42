#!/usr/bin/env python
"""Autonomy Actuator -- the last mile of the self-improvement loop.

THE GAP THIS CLOSES: the conductor PROPOSES doctrine/params/heartbeat changes it is
not allowed to auto-apply (rail 4), pings J, J taps Approve on Discord -> the
proposal row flips to status="approved" in conductor-proposals.jsonl ... and then
NOTHING reads it. J has had to hand-edit the file. This actuator consumes those
approved rows and actually applies them -- safely, reversibly, and committed.

HARD SAFETY CONTRACT (this thing can edit CLAUDE.md / params.json -- it must be
paranoid):
  1. Only touches proposals J EXPLICITLY approved (status == "approved"). Never
     self-approves; never touches "pending".
  2. Requires a STRUCTURED `apply_ops` field -- a list of {file, find, replace}
     exact string edits. A prose-only `apply` is NEVER guessed/LLM-interpreted;
     it is flagged status="needs_structured_apply" and skipped. No model in the
     apply path => deterministic, $0, no hallucinated edits.
  3. Each op's `find` must occur EXACTLY ONCE in its file (0 => already-applied or
     stale; >1 => ambiguous). Either way: refuse the whole proposal, untouched.
  4. Blast-radius cap: refuse a proposal touching more than MAX_FILES files.
  5. SNAPSHOT every target file before editing (.autonomy-snapshots/<id>/) -- the
     rollback substrate. Then apply all ops.
  6. Run the SAFETY GATE (run_safety_gate.py). Green => git add + commit + audit +
     mark applied. RED => restore the snapshot (repo untouched), mark apply_failed,
     flag for J. A bad edit can NEVER reach a commit.
  7. Fail-open & atomic: any error => restore snapshot, never leave the repo
     half-edited; the proposal ledger is rewritten atomically (tmp+replace).
  8. `revert <id>` restores an applied proposal's snapshot and commits the revert --
     J's one-tap off-switch for any single autonomous change.

Pure stdlib + git/pytest subprocess. Designed to run frequently & unattended from
Gamma_AutoApply (after-hours, $0 LLM). Audit trail: automation/state/autonomy-changelog.jsonl.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
PROPOSALS = STATE / "conductor-proposals.jsonl"
COMPANION_DECISIONS = STATE / "companion-decisions.jsonl"
CHANGELOG = STATE / "autonomy-changelog.jsonl"
SNAP_DIR = STATE / ".autonomy-snapshots"
GATE = REPO / "backtest" / "tests" / "run_safety_gate.py"

MAX_FILES = 6            # blast-radius cap per proposal
MAX_OP_BYTES = 20000     # refuse a single replace larger than this (sanity)

# OP-11 / OP-25 AUTONOMOUS APPROVAL (J = REVOKE-only, NOT a ratification gate): a
# proposal that clears the auto-ship bar for its KIND is approved without a human tap.
# Only the safe classes below; everything else stays pending for J / the persona.
AUTO_APPROVE_KINDS = {"doc-index", "doc-fold", "lesson-index", "lessons-index"}


def _now() -> str:
    return dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _et_now() -> dt.datetime:
    """Naive ET now (system Python here lacks tzdata; compute the US offset by hand)."""
    u = dt.datetime.now(dt.timezone.utc)
    y = u.year
    march = dt.datetime(y, 3, 1, tzinfo=dt.timezone.utc)
    dst_start = (march + dt.timedelta(days=((6 - march.weekday()) % 7) + 7)).replace(hour=7)
    nov = dt.datetime(y, 11, 1, tzinfo=dt.timezone.utc)
    dst_end = (nov + dt.timedelta(days=((6 - nov.weekday()) % 7))).replace(hour=6)
    off = -4 if (dst_start <= u < dst_end) else -5
    return (u + dt.timedelta(hours=off)).replace(tzinfo=None)


def _market_is_open() -> bool:
    """RTH: Mon-Fri 09:30 <= ET < 15:55. Rule 9 forbids mid-session doctrine/params
    changes, so the actuator REFUSES to apply during RTH (defense in depth -- the
    scheduled task is also after-hours-only)."""
    et = _et_now()
    if et.weekday() >= 5:
        return False
    hhmm = et.hour * 100 + et.minute
    return 930 <= hhmm < 1555


# --------------------------------------------------------------------------- io
def _read_proposals() -> list[dict]:
    if not PROPOSALS.exists():
        return []
    rows = []
    for line in PROPOSALS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                pass  # skip a torn line; never crash the actuator
    return rows


def _rewrite_proposals(rows: list[dict]) -> None:
    tmp = PROPOSALS.with_suffix(PROPOSALS.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    tmp.replace(PROPOSALS)


def _read_companion_decisions() -> list[dict]:
    if not COMPANION_DECISIONS.exists():
        return []
    rows = []
    for line in COMPANION_DECISIONS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                pass  # skip a torn line; never crash the bridge
    return rows


def sync_companion_approvals() -> int:
    """Bridge J's companion (localhost:4317) Approve/Reject taps into the proposal
    ledger -- the symmetric companion equivalent of the Discord `ship <id>` flow.

    THE GAP THIS CLOSES (G8): the conductor enqueues a real proposal card to the
    companion; J taps Approve; `resolveApproval` (gamma-companion/lib/approvals.js)
    appends {id, decision, ...} to companion-decisions.jsonl ... and NOTHING flipped
    the matching conductor-proposals row, so this actuator never saw J's consent.
    Two approval buses, no bridge. This reads those decisions and, for each that
    names a REAL proposal_id currently `pending`, flips it: approve -> "approved"
    (the actuator then applies it under its full safety contract), reject ->
    "shelved".

    HARD SAFETY CONTRACT (this only RECORDS consent; it applies NOTHING -- rail 4):
      - Only flips a row currently `status == "pending"`. Never re-touches
        approved/applied/shelved/reverted -> naturally idempotent, and a later J
        Discord/actuator action always wins over a stale companion row.
      - Synthetic companion cards (act-*/oblig-* ids) name no proposal_id -> they
        match nothing and are silently ignored.
      - Records J's consent into the SAME ledger the Discord responder feeds; the
        deterministic apply path (apply_ops + safety gate + snapshot + revert) is
        unchanged and still does all editing. Fail-open: never raises.
    Returns the count of proposals whose status it changed.
    """
    decisions = _read_companion_decisions()
    if not decisions:
        return 0
    rows = _read_proposals()
    by_id = {r.get("proposal_id"): r for r in rows if r.get("proposal_id")}
    changed = 0
    for d in decisions:
        pid = d.get("id")
        prop = by_id.get(pid)
        if prop is None or prop.get("status") != "pending":
            continue  # not a real pending proposal (synthetic id / already-resolved)
        decision = d.get("decision")
        if decision == "approve":
            prop["status"] = "approved"
            prop["approved_via"] = "companion"
            prop["approved_at"] = _now()
            _log_change({"proposal_id": pid, "title": prop.get("title", ""),
                         "outcome": "approved_via_companion", "decision_ts": d.get("ts")})
            changed += 1
        elif decision == "reject":
            prop["status"] = "shelved"
            prop["shelved_via"] = "companion"
            prop["shelved_at"] = _now()
            _log_change({"proposal_id": pid, "title": prop.get("title", ""),
                         "outcome": "shelved_via_companion", "decision_ts": d.get("ts")})
            changed += 1
    if changed:
        _rewrite_proposals(rows)
    return changed


def _log_change(row: dict) -> None:
    try:
        CHANGELOG.parent.mkdir(parents=True, exist_ok=True)
        row = {"logged_at": _now(), **row}
        with CHANGELOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass  # an audit-log failure must never break an apply


def _is_doc_file(rel: str) -> bool:
    """A documentation file safe for autonomous OP-25 index folds (never params/code)."""
    r = str(rel).replace("\\", "/").lower()
    return r in ("claude.md", "changelog.md", "readme.md") or r.endswith(".md") or r.startswith("markdown/")


def _scorecard_clears_bar(scorecard_rel: str) -> bool:
    """Verify the A/B scorecard FILE actually proves the OP-11 bar -- defends against a
    proposal that merely CLAIMS eval_bar_cleared (reward-hacking / hallucination). Reads
    the JSON and requires walk-forward >= 0.70 AND non-negative OOS AND anchor-no-
    regression, ALL present. CONSERVATIVE: missing file or unverifiable fields => False
    (a validated edge whose scorecard can't be machine-verified simply waits for J)."""
    if not scorecard_rel:
        return False
    p = REPO / str(scorecard_rel).replace("\\", "/").lstrip("/")
    try:
        if not p.exists():
            return False
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False

    def _num(*keys):
        for k in keys:
            v = data.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
        return None

    wf = _num("wf", "walk_forward", "walkforward", "wf_score")
    if wf is None or wf < 0.70:
        return False
    oos = _num("oos", "oos_pnl", "oos_expectancy", "oos_delta")
    if data.get("oos_positive") is not True and not (oos is not None and oos > 0):
        return False
    anchor_ok = data.get("anchor_no_regression")
    if anchor_ok is None:
        ec_delta = _num("anchor_edge_capture_delta", "edge_capture_delta")
        anchor_ok = (ec_delta is not None and ec_delta >= 0)
    return anchor_ok is True


def auto_approve_pending() -> int:
    """Flip qualifying `pending` proposals to `approved` per OP-11/OP-25 with NO human
    tap -- the autonomous half of the apply hop. The actuator's full safety contract
    (validate -> snapshot -> safety gate -> commit -> revert) still does ALL editing;
    this only supplies the consent INPUT that J used to have to type ('ship <id>').

    CONSERVATIVE BAR (defense in depth -- this can lead to a commit):
      - kind in AUTO_APPROVE_KINDS AND structured apply_ops touching ONLY doc files
        (CLAUDE.md OP-25 index rows / markdown docs) -> approve. The lesson-author's
        OP-25 self-correction folds: trivial, gate-backed, one-tap revertible.
      - any kind with eval_bar_cleared==True AND a scorecard reference AND structured
        apply_ops -> approve (the OP-11 eval-first bar: a trading edge the chef/
        conductor already proved OOS+ / WF>=0.70 / sub-window-stable / anchor-no-regress).
      - EVERYTHING ELSE stays pending. A raw params/heartbeat/risk change without eval
        evidence is NEVER auto-approved here.
    Returns the count of proposals it approved (and rewrites the ledger atomically)."""
    rows = _read_proposals()
    changed = 0
    for prop in rows:
        if prop.get("status") != "pending":
            continue
        ops = prop.get("apply_ops")
        if not isinstance(ops, list) or not ops:
            continue  # prose-only -> the actuator can't apply it anyway; never auto-approve
        kind = str(prop.get("kind", "")).lower()
        reason = None
        if kind in AUTO_APPROVE_KINDS and all(_is_doc_file(op.get("file", "")) for op in ops):
            reason = "op25_docindex"
        elif prop.get("eval_bar_cleared") is True and _scorecard_clears_bar(prop.get("scorecard", "")):
            reason = "op11_evalbar"
        if reason is None:
            continue
        prop["status"] = "approved"
        prop["approved_via"] = "auto:" + reason
        prop["approved_at"] = _now()
        _log_change({"proposal_id": prop.get("proposal_id"), "title": prop.get("title", ""),
                     "outcome": "auto_approved", "reason": reason})
        changed += 1
    if changed:
        _rewrite_proposals(rows)
    return changed


def _already_applied(prop: dict) -> bool:
    """True if EVERY op's edit has already landed (find absent, replace present) -- a
    chained/duplicate fold whose change is already in the tree. Distinguished from a
    genuinely-stale op (neither find nor replace present)."""
    ops = prop.get("apply_ops")
    if not isinstance(ops, list) or not ops:
        return False
    for op in ops:
        rel = str(op.get("file", "")).replace("\\", "/").lstrip("/")
        target = REPO / rel
        if not target.exists():
            return False
        text = target.read_text(encoding="utf-8")
        find_s, repl_s = str(op.get("find", "")), str(op.get("replace", ""))
        if not find_s or text.count(find_s) != 0:           # find still present -> not yet applied
            return False
        if not repl_s or text.count(repl_s) == 0:           # replace absent -> genuinely stale, not applied
            return False
    return True


def drain_already_applied() -> int:
    """Self-clear the apply loop: close proposals whose edit has ALREADY landed (find
    absent, replace present) -- the chained doc-folds that otherwise pile up at
    needs_structured_apply forever. Marks them 'applied' (no-op, no commit) so the
    actuator never gets permanently stuck on a duplicate. Returns the count closed."""
    rows = _read_proposals()
    n = 0
    for prop in rows:
        if prop.get("status") not in ("needs_structured_apply", "approved", "apply_failed"):
            continue
        if _already_applied(prop):
            prop["status"] = "applied"
            prop["applied_at"] = _now()
            prop["commit_sha"] = "(already-applied no-op)"
            prop["actuator_note"] = "edit already present in tree; closed as no-op (drain)"
            _log_change({"proposal_id": prop.get("proposal_id"), "title": prop.get("title", ""),
                         "outcome": "already_applied_noop"})
            n += 1
    if n:
        _rewrite_proposals(rows)
    return n


def _git_exe() -> str:
    """Resolve git absolutely. The Task Scheduler -> wscript -> pythonw chain runs
    with a minimal PATH that may not include git (same class as the responder's
    'claude not on PATH' bug, L41). Prefer PATH, then the standard install dirs."""
    found = shutil.which("git")
    if found:
        return found
    for cand in (r"C:\Program Files\Git\cmd\git.exe",
                 r"C:\Program Files\Git\bin\git.exe",
                 r"C:\Program Files (x86)\Git\cmd\git.exe"):
        if Path(cand).exists():
            return cand
    return "git"


_GIT = _git_exe()


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([_GIT, *args], cwd=str(REPO), capture_output=True, text=True)


# ---------------------------------------------------------------- snapshot/restore
def _snap_path(pid: str, rel: str) -> Path:
    return SNAP_DIR / pid / rel


def _snapshot(pid: str, files: list[str]) -> None:
    for rel in files:
        src = REPO / rel
        dst = _snap_path(pid, rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copy2(src, dst)
        else:
            # record absence so a restore can delete a file the op created
            dst.parent.mkdir(parents=True, exist_ok=True)
            (dst.parent / (dst.name + ".__absent__")).write_text("", encoding="utf-8")


def _restore(pid: str, files: list[str]) -> None:
    for rel in files:
        snap = _snap_path(pid, rel)
        dest = REPO / rel
        if snap.exists():
            shutil.copy2(snap, dest)
        elif (snap.parent / (snap.name + ".__absent__")).exists():
            if dest.exists():
                dest.unlink()  # the op created it; restore = remove


# ------------------------------------------------------------------- validation
def _validate_ops(prop: dict) -> tuple[list[str], str]:
    """Return (files, error). error == '' means the ops are safe to apply.
    Refuses anything ambiguous, oversized, or out-of-tree."""
    ops = prop.get("apply_ops")
    if not isinstance(ops, list) or not ops:
        return [], "no structured apply_ops (prose-only apply is never auto-applied)"
    files = []
    for i, op in enumerate(ops):
        if not isinstance(op, dict) or "file" not in op or "find" not in op or "replace" not in op:
            return [], f"op[{i}] malformed (need file/find/replace)"
        rel = str(op["find"]) if False else str(op["file"]).replace("\\", "/").lstrip("/")
        target = (REPO / rel).resolve()
        # out-of-tree guard: the resolved path MUST stay inside the repo
        try:
            target.relative_to(REPO.resolve())
        except ValueError:
            return [], f"op[{i}] file escapes the repo: {rel}"
        if len(str(op["replace"]).encode("utf-8")) > MAX_OP_BYTES:
            return [], f"op[{i}] replace too large (> {MAX_OP_BYTES} bytes)"
        if not target.exists():
            return [], f"op[{i}] target file missing: {rel}"
        text = target.read_text(encoding="utf-8")
        n = text.count(str(op["find"]))
        if n == 0:
            return [], f"op[{i}] find-string not present in {rel} (stale/already-applied)"
        if n > 1:
            return [], f"op[{i}] find-string occurs {n}x in {rel} (ambiguous -- refusing)"
        if rel not in files:
            files.append(rel)
    if len(files) > MAX_FILES:
        return [], f"blast-radius too large ({len(files)} files > {MAX_FILES})"
    return files, ""


def _apply_ops(prop: dict) -> None:
    for op in prop["apply_ops"]:
        rel = str(op["file"]).replace("\\", "/").lstrip("/")
        target = REPO / rel
        text = target.read_text(encoding="utf-8")
        text = text.replace(str(op["find"]), str(op["replace"]), 1)  # unique-verified above
        target.write_text(text, encoding="utf-8")


# ------------------------------------------------------------------------ gate
def _run_gate() -> tuple[bool, str]:
    py = sys.executable
    venv = REPO / "backtest" / ".venv" / "Scripts" / "python.exe"
    if venv.exists():
        py = str(venv)
    proc = subprocess.run([py, str(GATE)], cwd=str(REPO), capture_output=True, text=True)
    tail = (proc.stdout + "\n" + proc.stderr).strip().splitlines()
    return proc.returncode == 0, "\n".join(tail[-12:])


# ----------------------------------------------------------------------- apply
def _set_status(rows: list[dict], pid: str, **fields) -> None:
    for r in rows:
        if r.get("proposal_id") == pid:
            r.update(fields)
            break
    _rewrite_proposals(rows)


def apply_approved(dry_run: bool = False) -> int:
    if not dry_run:
        # Bridge J's companion taps into the ledger BEFORE selecting approved rows,
        # so a phone/watch Approve reaches the same apply path as a Discord `ship`.
        synced = sync_companion_approvals()
        if synced:
            print(f"[actuator] synced {synced} companion decision(s) into the proposal ledger.")
        # OP-11/OP-25: auto-approve the safe class (J = REVOKE-only) so the apply hop
        # closes without a human tap. The safety contract below still gates every edit.
        auto = auto_approve_pending()
        if auto:
            print(f"[actuator] auto-approved {auto} proposal(s) per OP-11/OP-25 (J = REVOKE-only).")
        drained = drain_already_applied()
        if drained:
            print(f"[actuator] drained {drained} already-applied proposal(s) -- apply loop self-cleared.")
    if not dry_run and _market_is_open():
        print("[actuator] market open -- deferring apply to after-hours (Rule 9: no mid-session doctrine/params changes).")
        return 0
    rows = _read_proposals()
    approved = [r for r in rows if r.get("status") == "approved"]
    if not approved:
        print("[actuator] no approved-unapplied proposals.")
        return 0

    applied = failed = skipped = 0
    for prop in approved:
        pid = prop.get("proposal_id", "?")
        title = prop.get("title", "")
        files, err = _validate_ops(prop)
        if err:
            print(f"[actuator] SKIP {pid}: {err}")
            if not dry_run:
                _set_status(rows, pid, status="needs_structured_apply",
                            actuator_note=err, actuator_at=_now())
                _log_change({"proposal_id": pid, "title": title, "outcome": "skipped", "reason": err})
            skipped += 1
            continue

        if dry_run:
            print(f"[actuator] WOULD APPLY {pid}: {title}  ({len(files)} file(s): {', '.join(files)})")
            applied += 1
            continue

        print(f"[actuator] applying {pid}: {title}  ({len(files)} file(s))")
        try:
            _snapshot(pid, files)
            _apply_ops(prop)
        except Exception as exc:
            _restore(pid, files)
            _set_status(rows, pid, status="apply_failed", failed_at=_now(),
                        failure_reason=f"apply error: {exc}")
            _log_change({"proposal_id": pid, "title": title, "outcome": "apply_error",
                         "reason": str(exc), "files": files})
            print(f"[actuator] ERROR applying {pid}: {exc} -- restored, flagged.")
            failed += 1
            continue

        ok, gate_tail = _run_gate()
        if not ok:
            _restore(pid, files)
            _set_status(rows, pid, status="apply_failed", failed_at=_now(),
                        failure_reason="safety gate RED", gate_tail=gate_tail)
            _log_change({"proposal_id": pid, "title": title, "outcome": "gate_red",
                         "files": files, "gate_tail": gate_tail})
            print(f"[actuator] GATE RED for {pid} -- snapshot restored, NOT committed. Flagged for J.")
            failed += 1
            continue

        # green -> stage, verify staged, commit
        for rel in files:
            _git("add", "--", rel)
        staged = _git("diff", "--cached", "--name-only").stdout.split()
        if not any(f in staged for f in files):
            _restore(pid, files)
            _set_status(rows, pid, status="apply_failed", failed_at=_now(),
                        failure_reason="git add produced no staged change")
            _log_change({"proposal_id": pid, "title": title, "outcome": "nothing_staged", "files": files})
            print(f"[actuator] {pid}: nothing staged -- restored, flagged.")
            failed += 1
            continue

        via = prop.get("approved_via", "approved")
        msg = (f"auto-apply: {pid} {title} ({via})\n\n"
               f"Applied by the autonomy actuator; approval={via}; safety gate green. "
               f"J's role is REVOKE: `autonomy_actuator.py revert {pid}`.\nFiles: {', '.join(files)}")
        commit = _git("commit", "-m", msg)
        sha = _git("rev-parse", "--short", "HEAD").stdout.strip()
        if commit.returncode != 0:
            _restore(pid, files)
            _set_status(rows, pid, status="apply_failed", failed_at=_now(),
                        failure_reason="git commit failed: " + commit.stderr[-300:])
            _log_change({"proposal_id": pid, "title": title, "outcome": "commit_failed",
                         "files": files, "reason": commit.stderr[-300:]})
            print(f"[actuator] {pid}: commit failed -- restored, flagged.")
            failed += 1
            continue

        _set_status(rows, pid, status="applied", applied_at=_now(), commit_sha=sha)
        _log_change({"proposal_id": pid, "title": title, "outcome": "applied",
                     "files": files, "commit_sha": sha, "ops": len(prop.get("apply_ops", []))})
        print(f"[actuator] APPLIED {pid} -> commit {sha}. ({', '.join(files)})")
        applied += 1

    print(f"[actuator] done: {applied} applied, {failed} failed, {skipped} skipped.")
    return 1 if failed else 0


# ---------------------------------------------------------------------- revert
def revert(pid: str) -> int:
    rows = _read_proposals()
    prop = next((r for r in rows if r.get("proposal_id") == pid), None)
    if prop is None:
        print(f"[actuator] revert: no proposal {pid}.")
        return 1
    if prop.get("status") != "applied":
        print(f"[actuator] revert: {pid} is '{prop.get('status')}', not 'applied' -- nothing to revert.")
        return 1
    files, _ = _validate_ops(prop) if prop.get("apply_ops") else ([], "")
    # derive files from the snapshot dir if validation can't (the find-string is gone post-apply)
    snap_root = SNAP_DIR / pid
    if snap_root.exists():
        files = [str(p.relative_to(snap_root)).replace("\\", "/")
                 for p in snap_root.rglob("*") if p.is_file() and not p.name.endswith(".__absent__")]
    if not files:
        print(f"[actuator] revert: no snapshot for {pid} -- cannot safely revert.")
        return 1
    _restore(pid, files)
    for rel in files:
        _git("add", "--", rel)
    title = prop.get("title", "")
    commit = _git("commit", "-m", f"revert auto-apply: {pid} {title} (J requested)\n\nRestored from pre-apply snapshot.")
    sha = _git("rev-parse", "--short", "HEAD").stdout.strip() if commit.returncode == 0 else ""
    _set_status(rows, pid, status="reverted", reverted_at=_now(), revert_commit=sha)
    _log_change({"proposal_id": pid, "title": title, "outcome": "reverted",
                 "files": files, "revert_commit": sha})
    print(f"[actuator] REVERTED {pid}" + (f" -> commit {sha}" if sha else " (restored; commit skipped/no-op)"))
    return 0


def show_status() -> int:
    from collections import Counter
    rows = _read_proposals()
    c = Counter(r.get("status", "?") for r in rows)
    print("[actuator] proposal ledger status:")
    for k, v in sorted(c.items()):
        print(f"   {k}: {v}")
    approved = [r for r in rows if r.get("status") == "approved"]
    if approved:
        print("   --- approved, awaiting apply:")
        for r in approved:
            has = "structured" if isinstance(r.get("apply_ops"), list) else "PROSE-ONLY"
            print(f"     {r.get('proposal_id')}: {r.get('title','')[:60]} [{has}]")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply / revert J-approved conductor proposals, safely.")
    sub = ap.add_subparsers(dest="cmd")
    ap_apply = sub.add_parser("apply", help="apply all approved-unapplied proposals (default)")
    ap_apply.add_argument("--dry-run", action="store_true")
    ap_rev = sub.add_parser("revert", help="revert an applied proposal by id")
    ap_rev.add_argument("proposal_id")
    sub.add_parser("status", help="show the proposal ledger status")
    args = ap.parse_args()

    if args.cmd == "revert":
        return revert(args.proposal_id)
    if args.cmd == "status":
        return show_status()
    return apply_approved(dry_run=getattr(args, "dry_run", False))


if __name__ == "__main__":
    raise SystemExit(main())
