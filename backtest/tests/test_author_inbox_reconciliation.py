"""Reconciliation test for the OP-29 author inboxes (closing-handshake guard, L170).

THE BUG THIS GUARDS (L170): author-inbox items have no closing handshake.
When an author persona (validator/skill/lesson/chef) ships its artifact, NOTHING
renames the source inbox item ``.DONE``. The artifact (the producer) and the
inbox file (the consumer-signal) drift: the validator exists on disk, but the
inbox still reads "pending." A later ``Gamma_Conductor`` fire then reads the
stale item as drainable work (STAGE 1 priority #3) and can rebuild a near-
duplicate (e.g. a redundant v44 of v42). This is the same producer/consumer-
silent-break class as ``test_watcher_registry`` — here applied to the inbox
lifecycle: "being-implemented == inbox-closed".

The invariant this enforces, for the ``_validator-inbox`` (the only author inbox
whose artifacts have a machine-checkable on-disk identity):

    for any `_validator-inbox/*.md` (NOT *.DONE, NOT *.STALE.md, NOT README)
    carrying a `proposed_validator:` frontmatter field, if the implementing
    validator ALREADY EXISTS in crypto/validators/ (matched by SLUG, because the
    proposed name `v_sizing_risk_cap_guard` is shipped as `v42_sizing_risk_cap_guard.py`),
    the inbox item MUST be `.DONE`.

Items WITHOUT a `proposed_validator:` field (legacy free-form asks like the
ghost-entry one) cannot be auto-reconciled, so they are reported as ADVISORY —
surfaced via a captured-warning test, never hard-failed (do-no-harm; fail-open).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]          # .../42 (repo root)
_CANDIDATES_DIR = _REPO_ROOT / "strategy" / "candidates"
_INBOX_DIR = _CANDIDATES_DIR / "_validator-inbox"
_VALIDATORS_DIR = _REPO_ROOT / "crypto" / "validators"

# The four OP-29 author inboxes (L173 staleness ratchet walks all of them).
_AUTHOR_INBOXES = ("_validator-inbox", "_skill-inbox", "_lesson-inbox", "_chef-inbox")
# An open inbox item older than this (by file mtime) is a SUPERSEDE-direction
# disposition candidate — surface it for triage so it cannot re-cost every fire.
_STALE_AGE_DAYS = 7.0

# A validator filename is `v<NN>_<slug>.py` (NN optional). We reconcile by SLUG
# so the proposed name (often `v_<slug>` or just `<slug>`) matches the shipped
# `v<NN>_<slug>` regardless of the assigned number.
_VALIDATOR_FILE_RE = re.compile(r"^v\d*_(.+)\.py$")


def _slugify(name: str) -> str:
    """Normalize a proposed/implemented validator name to its bare slug.

    `v_sizing_risk_cap_guard` -> `sizing_risk_cap_guard`
    `v42_sizing_risk_cap_guard` -> `sizing_risk_cap_guard`
    `sizing_risk_cap_guard` -> `sizing_risk_cap_guard`
    """
    name = name.strip().lower()
    if name.endswith(".py"):
        name = name[:-3]
    m = re.match(r"^v\d*_(.+)$", name)
    if m:
        return m.group(1)
    return name


def _implemented_slugs() -> set[str]:
    """Slugs of every validator currently on disk in crypto/validators/."""
    slugs: set[str] = set()
    if not _VALIDATORS_DIR.is_dir():
        return slugs
    for p in _VALIDATORS_DIR.glob("v*.py"):
        m = _VALIDATOR_FILE_RE.match(p.name)
        if m:
            slugs.add(m.group(1).lower())
    return slugs


def _frontmatter_field(text: str, field: str) -> str | None:
    """Pull a single scalar field out of a leading `---` YAML frontmatter block.

    Deliberately dependency-free (no PyYAML) and lenient — we only need one flat
    scalar. Returns None if there is no frontmatter or the field is absent.
    """
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    block = text[3:end]
    for line in block.splitlines():
        key, sep, val = line.partition(":")
        if sep and key.strip() == field:
            return val.strip().strip('"').strip("'") or None
    return None


@dataclass(frozen=True)
class Reconciliation:
    violations: tuple[str, ...]   # implemented-but-not-DONE (hard fail)
    advisories: tuple[str, ...]   # no proposed_validator frontmatter (soft)


def reconcile_inbox(inbox_dir: Path, implemented: set[str]) -> Reconciliation:
    """Pure core: given an inbox dir and the set of implemented validator slugs,
    return the open items whose validator already exists (violations) and the
    open items that lack frontmatter to reconcile (advisories).

    Only files ending exactly in `.md` are "open" — `.DONE` / `.STALE.md` /
    `README.md` are skipped.
    """
    violations: list[str] = []
    advisories: list[str] = []
    if not inbox_dir.is_dir():
        return Reconciliation((), ())
    for p in sorted(inbox_dir.glob("*.md")):
        if p.name == "README.md" or p.name.endswith(".STALE.md"):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        proposed = _frontmatter_field(text, "proposed_validator")
        if proposed is None:
            advisories.append(p.name)
            continue
        if _slugify(proposed) in implemented:
            violations.append(p.name)
    return Reconciliation(tuple(violations), tuple(advisories))


# ── Supersede-direction staleness ratchet (L173) ─────────────────────────────
#
# L170 (above) is the IMPLEMENT direction: an artifact exists on disk -> the inbox
# item MUST be `.DONE` (hard fail, machine-checkable). L173 is the SUPERSEDE
# direction: research rendered moot by a strategic verdict / standing directive
# leaves no artifact, so nothing closes it and it re-costs every conductor fire.
# Supersession is a judgment call (NOT machine-checkable), so this is ADVISORY
# (fail-open) — it surfaces old open items for explicit SUPERSEDED / RESOLVED /
# BACKLOG triage; it never hard-fails legitimate in-flight work.

@dataclass(frozen=True)
class StaleItem:
    inbox: str        # which author inbox (e.g. "_chef-inbox")
    name: str         # the open *.md filename
    age_days: float   # file mtime age in days (rounded)


def find_stale_undisposed(
    candidates_dir: Path,
    inboxes: tuple[str, ...] = _AUTHOR_INBOXES,
    *,
    max_age_days: float = _STALE_AGE_DAYS,
    now: float | None = None,
) -> tuple[StaleItem, ...]:
    """Return open inbox items (NOT `.DONE` / `.STALE.md` / `README.md`) across
    all author inboxes whose file mtime is older than ``max_age_days``.

    These are SUPERSEDE-direction disposition candidates (L173): an item this old
    with no closing handshake is debt that re-costs every fire. Advisory only —
    the caller triages each to SUPERSEDED / RESOLVED / BACKLOG and renames `.DONE`.
    Fail-open: a non-existent dir contributes nothing; never raises on a stray file.
    """
    ref = time.time() if now is None else now
    stale: list[StaleItem] = []
    for inbox in inboxes:
        d = candidates_dir / inbox
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.md")):
            if p.name == "README.md" or p.name.endswith(".STALE.md"):
                continue
            try:
                age_days = (ref - p.stat().st_mtime) / 86400.0
            except OSError:
                continue  # fail-open on an unreadable/racing file
            if age_days > max_age_days:
                stale.append(StaleItem(inbox, p.name, round(age_days, 1)))
    return tuple(stale)


# ── The live invariant over the real inbox ───────────────────────────────────

def test_implemented_validators_have_closed_their_inbox_item():
    """No phantom backlog: any `_validator-inbox/*.md` whose `proposed_validator`
    already exists on disk MUST be `.DONE`. This is the closing-handshake guard
    that the 2026-06-20 stale-inbox incident (L170) demands."""
    rec = reconcile_inbox(_INBOX_DIR, _implemented_slugs())
    assert not rec.violations, (
        "Author-inbox closing-handshake VIOLATION (L170): these `_validator-inbox` "
        "items name a `proposed_validator:` that already exists in crypto/validators/ "
        "but are NOT renamed `.DONE`. A conductor fire will misread them as pending "
        "work and may rebuild a duplicate. Append a CLOSED note + rename `.DONE`:\n  "
        + "\n  ".join(rec.violations)
    )


def test_frontmatterless_inbox_items_are_surfaced_as_advisory():
    """Items without a `proposed_validator:` field can't be auto-reconciled.
    They are NOT a hard failure (fail-open), but they ARE surfaced so they don't
    rot silently — this test passes but documents them in its captured output."""
    rec = reconcile_inbox(_INBOX_DIR, _implemented_slugs())
    # This is intentionally non-fatal — it exists to make the advisory set visible
    # in -v / -rA output and to lock in that the reconciler classifies them as
    # advisory rather than crashing on missing frontmatter.
    if rec.advisories:
        print(
            "ADVISORY (L170): `_validator-inbox` items without `proposed_validator:` "
            "frontmatter cannot be machine-reconciled — verify manually:\n  "
            + "\n  ".join(rec.advisories)
        )
    assert isinstance(rec.advisories, tuple)


# ── Pure-logic reproducers (synthetic — prove the guard fires when it should) ─

def test_reconciler_flags_implemented_but_not_done(tmp_path):
    inbox = tmp_path / "_validator-inbox"
    inbox.mkdir()
    (inbox / "README.md").write_text("# readme", encoding="utf-8")
    (inbox / "open-implemented.md").write_text(
        "---\nproposed_validator: v_foo_guard\ntitle: x\n---\n\nbody",
        encoding="utf-8",
    )
    rec = reconcile_inbox(inbox, {"foo_guard"})
    assert rec.violations == ("open-implemented.md",), rec
    assert rec.advisories == ()


def test_reconciler_ignores_done_and_missing(tmp_path):
    inbox = tmp_path / "_validator-inbox"
    inbox.mkdir()
    # .DONE — already closed, must be ignored even though validator exists
    (inbox / "closed.md.DONE").write_text(
        "---\nproposed_validator: v_foo_guard\n---\nbody", encoding="utf-8"
    )
    # open but validator does NOT exist yet — genuine pending work, no violation
    (inbox / "open-unbuilt.md").write_text(
        "---\nproposed_validator: v_not_built_yet\n---\nbody", encoding="utf-8"
    )
    rec = reconcile_inbox(inbox, {"foo_guard"})
    assert rec.violations == ()
    assert rec.advisories == ()


def test_reconciler_marks_frontmatterless_as_advisory(tmp_path):
    inbox = tmp_path / "_validator-inbox"
    inbox.mkdir()
    (inbox / "free-form.md").write_text("# Validator request: foo\n\nno frontmatter here", encoding="utf-8")
    rec = reconcile_inbox(inbox, {"anything"})
    assert rec.violations == ()
    assert rec.advisories == ("free-form.md",)


# ── Supersede-direction staleness ratchet tests (L173) ───────────────────────

def test_stale_ratchet_flags_old_open_item_across_inboxes(tmp_path):
    """An open *.md older than the threshold, in ANY author inbox, is surfaced."""
    cand = tmp_path / "candidates"
    chef = cand / "_chef-inbox"
    chef.mkdir(parents=True)
    old = chef / "2026-05-21-superseded-idea.md"
    old.write_text("# off-strategy entry candidate\n", encoding="utf-8")
    # Force mtime to 10 days ago (> 7-day threshold).
    ten_days_ago = time.time() - 10 * 86400
    import os
    os.utime(old, (ten_days_ago, ten_days_ago))

    stale = find_stale_undisposed(cand)
    assert len(stale) == 1, stale
    assert stale[0].inbox == "_chef-inbox"
    assert stale[0].name == "2026-05-21-superseded-idea.md"
    assert stale[0].age_days >= 7.0


def test_stale_ratchet_ignores_fresh_done_and_readme(tmp_path):
    """Fresh items, `.DONE` closures (even if old), and README are never flagged."""
    cand = tmp_path / "candidates"
    lesson = cand / "_lesson-inbox"
    lesson.mkdir(parents=True)
    import os
    old_ts = time.time() - 30 * 86400

    # README — skipped regardless of age
    readme = lesson / "README.md"
    readme.write_text("# inbox", encoding="utf-8")
    os.utime(readme, (old_ts, old_ts))
    # .DONE — already disposed, must be ignored even though it's old
    done = lesson / "closed-long-ago.md.DONE"
    done.write_text("body", encoding="utf-8")
    os.utime(done, (old_ts, old_ts))
    # fresh open item — genuine in-flight work, not stale
    fresh = lesson / "2026-06-21-just-filed.md"
    fresh.write_text("body", encoding="utf-8")  # mtime ~ now

    stale = find_stale_undisposed(cand)
    assert stale == (), stale


def test_stale_ratchet_fails_open_on_missing_dirs(tmp_path):
    """No inboxes present -> empty tuple, never raises (fail-open)."""
    assert find_stale_undisposed(tmp_path / "candidates") == ()


def test_live_stale_undisposed_items_are_surfaced_as_advisory():
    """Non-fatal: surface any real author-inbox item open > 7 days so the SUPERSEDE
    direction (L173) cannot silently re-cost every conductor fire. ADVISORY by
    design — supersession is a judgment call, so this prints rather than fails."""
    stale = find_stale_undisposed(_CANDIDATES_DIR)
    if stale:
        print(
            "ADVISORY (L173): author-inbox items open > 7 days with no closing "
            "handshake — triage each to SUPERSEDED / RESOLVED / BACKLOG, then "
            "rename `.DONE`:\n  "
            + "\n  ".join(f"{s.inbox}/{s.name} ({s.age_days}d)" for s in stale)
        )
    assert isinstance(stale, tuple)


def test_slugify_strips_v_number_prefix():
    assert _slugify("v_sizing_risk_cap_guard") == "sizing_risk_cap_guard"
    assert _slugify("v42_sizing_risk_cap_guard") == "sizing_risk_cap_guard"
    assert _slugify("v42_sizing_risk_cap_guard.py") == "sizing_risk_cap_guard"
    assert _slugify("sizing_risk_cap_guard") == "sizing_risk_cap_guard"


def test_implemented_slugs_finds_known_validators():
    """Sanity floor — the real validators dir resolves and contains the fleet."""
    slugs = _implemented_slugs()
    assert "sizing_risk_cap_guard" in slugs
    assert "ghost_entry_detection" in slugs
    assert len(slugs) >= 20
