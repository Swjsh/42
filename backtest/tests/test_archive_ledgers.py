"""Guards for setup/scripts/archive_ledgers.py -- the durable custody archive.

WHAT THESE PROTECT (2026-08-19 data-custody emergency)
======================================================
automation/state/fills-ledger.jsonl is the ONLY surviving copy of 22 of our 35 trading
days: Alpaca's paper API has deleted its own history (a FILL query for 2026-06-25..08-03
returns zero rows while the same query from 08-03 returns rows). The file was found
untracked by git, unignored by .gitignore (so `git clean -fd` deletes it), AND absent from
the pre-existing ledger_archive.py SOURCES list.

The load-bearing tests here, in order of how badly their failure would hurt:

  test_critical_source_is_archived
      The EXACT bug that created this emergency: an archive that runs green every day
      while never copying the one irreplaceable file. This asserts fills-ledger.jsonl is
      in SOURCE_SPECS and is treated as CRITICAL.

  test_drill_reads_the_archive_not_the_live_file
      THE NEGATIVE CONTROL. A restore drill that secretly reads live state would pass
      forever while the archive rotted. We capture a 2-round-trip ledger, then swap the
      LIVE file to a 3-round-trip one without re-capturing, and assert the drill still
      reports 2 and FAILS the comparison. A drill that reports 3 is reading live data and
      is worthless.

  test_corrupted_blob_is_detected / test_truncated_blob_is_detected
      RED-proof of the checksum claim: flip a byte, lose the tail -- verification must SAY
      SO. An archive whose corruption is discovered years later is not an archive.

  test_live_ledger_still_reproduces_the_canonical_book
      The standing regression on real data: the live ledger must FIFO-reconstruct to
      exactly the row count and gross P&L that analysis/recommendations/trade-matrix.json
      claims. If someone truncates or rewrites the ledger, this goes RED the same day.
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_MOD_PATH = REPO / "setup" / "scripts" / "archive_ledgers.py"

for _p in (REPO / "setup" / "scripts", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_spec = importlib.util.spec_from_file_location("archive_ledgers", _MOD_PATH)
al = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(al)


# ────────────────────────────────────────────────────────────── synthetic book helpers
def _leg(arm: str, symbol: str, side: str, qty: float, price: float, ts: str) -> dict:
    """One fills-ledger row in the real production schema (see fills-ledger.jsonl)."""
    return {
        "activity_id": f"{ts}::{arm}:{symbol}:{side}:{price}",
        "arm": arm, "order_id": f"o-{ts}-{side}", "symbol": symbol, "side": side,
        "qty": qty, "price": price, "multiplier": 100, "is_crypto": False,
        "is_option": True, "ts_utc": f"{ts}Z", "ts_et": ts, "date_et": ts[:10],
        "attribution": "engine",
    }


def _ledger_bytes(trips: int) -> bytes:
    """`trips` closed round trips on arm safe-2, each a clean +$100 winner.

    Each trip is a distinct SPY strike so fills_fifo keys them separately; qty 1 at
    1.00 -> 2.00 gives real_pnl = (2.00-1.00)*1*100 = +$100 exactly.
    """
    rows = []
    for i in range(trips):
        sym = f"SPY260630C0075{i:04d}"
        day = f"2026-06-{26 + i:02d}"
        rows.append(_leg("safe-2", sym, "buy", 1.0, 1.00, f"{day}T10:00:0{i}"))
        rows.append(_leg("safe-2", sym, "sell", 1.0, 2.00, f"{day}T11:00:0{i}"))
    return ("\n".join(json.dumps(r) for r in rows) + "\n").encode("utf-8")


def _fake_repo(tmp: Path, *, trips: int, claim_rows: int, claim_gross: float) -> Path:
    """A minimal repo tree: a fills ledger plus the canonical table the drill compares to."""
    repo = tmp / "repo"
    (repo / "automation" / "state").mkdir(parents=True, exist_ok=True)
    (repo / al.CRITICAL).write_bytes(_ledger_bytes(trips))
    tm = repo / "analysis" / "recommendations" / "trade-matrix.json"
    tm.parent.mkdir(parents=True, exist_ok=True)
    tm.write_text(json.dumps({"row_count": claim_rows, "totals": {"gross": claim_gross}}),
                  encoding="utf-8")
    return repo


def _capture(repo: Path, root: Path) -> dict:
    return al.capture(repo, root, today="2026-08-20", now_iso="2026-08-20T00:00:00")


def _write_snapshot(root: Path, manifest: dict) -> None:
    d = root / "snapshots" / manifest["snapshot_date_et"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


# ────────────────────────────────────────────────────────────── the emergency's own bug
def test_critical_source_is_archived():
    """fills-ledger.jsonl MUST be a source. Its absence from ledger_archive.py's SOURCES
    is precisely why the only copy of 22 trading days had zero backups."""
    assert al.CRITICAL == "automation/state/fills-ledger.jsonl"
    assert al.CRITICAL in al.SOURCE_SPECS, (
        "the irreplaceable fills ledger is not in SOURCE_SPECS -- this is the exact "
        "failure mode that created the 2026-08-19 custody emergency")


def test_critical_source_exists_in_the_real_repo():
    """A source spec that no longer matches reality protects nothing."""
    assert (REPO / al.CRITICAL).is_file(), f"{al.CRITICAL} missing from the live repo"


def test_missing_critical_is_failed_not_skipped(tmp_path):
    """A run that cannot find the book must FAIL, never quietly report success."""
    repo = tmp_path / "empty-repo"
    (repo / "automation" / "state").mkdir(parents=True)
    manifest = _capture(repo, tmp_path / "arch")
    assert manifest["critical_present"] is False
    assert any(m["spec"] == al.CRITICAL for m in manifest["missing"])

    root = tmp_path / "arch"
    verify = al.verify_manifest(root, manifest, repo=repo)
    assert verify["status"] == "FAILED"
    assert verify["semantics"]["status"] == "MISSING"


def test_real_repo_sources_resolve_and_include_the_book():
    present, _missing = al.resolve_sources(REPO)
    assert al.CRITICAL in present, "SOURCE_SPECS no longer selects the irreplaceable book"
    assert len(present) > 20, f"only {len(present)} sources resolved -- specs have rotted"


# ────────────────────────────────────────────────────────────── secrets never get archived
@pytest.mark.parametrize("rel", [
    ".mcp.json",
    "automation/state/fleet/secrets.json",
    "automation/state/fleet/kalshi-1.pem",
    "automation/state/.openrouter.key",
    "automation/state/.alpaca-keys",
    "some/dir/.heartbeat-api-key-prod",
])
def test_secrets_are_refused(rel):
    """A second volume must never become a second place a credential leaks from."""
    with pytest.raises(al.SecretInArchiveError):
        al._assert_not_secret(rel)


def test_real_repo_specs_never_select_a_secret():
    """resolve_sources() over the LIVE repo must not pick up any credential file."""
    present, _ = al.resolve_sources(REPO)          # raises SecretInArchiveError if it does
    for rel in present:
        name = rel.rsplit("/", 1)[-1].lower()
        assert "secret" not in name
        assert not name.endswith((".pem", ".key"))
    assert ".mcp.json" not in present


def test_secrets_absent_from_the_real_archive_on_disk():
    """Belt-and-suspenders: nothing credential-shaped may appear in any real manifest."""
    root, _, _ = al.resolve_archive_root()
    date = al.latest_snapshot(root)
    if date is None:
        pytest.skip("archive has not run yet on this box")
    for f in al.load_manifest(root, date)["files"]:
        name = f["rel"].rsplit("/", 1)[-1].lower()
        assert "secret" not in name and not name.endswith((".pem", ".key")), f["rel"]


# ────────────────────────────────────────────────────────────── checksum RED-proofs
def test_capture_verify_roundtrip_is_clean(tmp_path):
    repo = _fake_repo(tmp_path, trips=2, claim_rows=2, claim_gross=200.0)
    root = tmp_path / "arch"
    manifest = _capture(repo, root)
    verify = al.verify_manifest(root, manifest, repo=repo)
    assert verify["status"] == "OK"
    assert verify["corruption"] == []
    assert verify["blobs_checked"] == verify["blobs_expected"] == manifest["file_count"]
    assert verify["semantics"]["from_archive"]["round_trips"] == 2
    assert verify["semantics"]["from_archive"]["gross_pnl"] == 200.0
    assert verify["semantics"]["agrees_with_live"] is True


def test_corrupted_blob_is_detected(tmp_path):
    """RED-proof: flip one byte inside a stored blob -- verification must call it out.

    We rewrite the blob as valid gzip of DIFFERENT content, which is the nastier case:
    the file still decompresses fine, so only the checksum can catch it.
    """
    repo = _fake_repo(tmp_path, trips=2, claim_rows=2, claim_gross=200.0)
    root = tmp_path / "arch"
    manifest = _capture(repo, root)

    entry = next(f for f in manifest["files"] if f["rel"] == al.CRITICAL)
    tampered = _ledger_bytes(2).replace(b'"price": 2.0', b'"price": 9.0', 1)
    (root / al.blob_rel(entry["sha256"])).write_bytes(gzip.compress(tampered))

    verify = al.verify_manifest(root, manifest, repo=repo)
    assert verify["status"] == "FAILED"
    problems = [c["problem"] for c in verify["corruption"]]
    assert any("SHA MISMATCH" in p for p in problems), verify["corruption"]


def test_truncated_blob_is_detected(tmp_path):
    """A half-written blob must be reported unreadable, not silently treated as fine."""
    repo = _fake_repo(tmp_path, trips=2, claim_rows=2, claim_gross=200.0)
    root = tmp_path / "arch"
    manifest = _capture(repo, root)
    entry = next(f for f in manifest["files"] if f["rel"] == al.CRITICAL)
    blob = root / al.blob_rel(entry["sha256"])
    blob.write_bytes(blob.read_bytes()[:12])

    verify = al.verify_manifest(root, manifest, repo=repo)
    assert verify["status"] == "FAILED"
    assert any("unreadable" in c["problem"] for c in verify["corruption"])
    # and it must REPORT the unreadable book, not raise out of the verifier
    assert verify["semantics"]["status"] == "UNREADABLE"


def test_blob_name_is_the_hash_of_its_content(tmp_path):
    """The integrity property the whole design rests on."""
    repo = _fake_repo(tmp_path, trips=3, claim_rows=3, claim_gross=300.0)
    root = tmp_path / "arch"
    manifest = _capture(repo, root)
    for f in manifest["files"]:
        raw = gzip.decompress((root / f["blob"]).read_bytes())
        assert hashlib.sha256(raw).hexdigest() == f["sha256"]
        # the address IS the digest: blobs/<aa>/<sha256>.gz
        assert Path(f["blob"]).name == f"{f['sha256']}.gz"
        assert Path(f["blob"]).parent.name == f["sha256"][:2]


# ────────────────────────────────────────────────────────────── restore fidelity
def test_restore_reproduces_bytes_exactly(tmp_path):
    repo = _fake_repo(tmp_path, trips=4, claim_rows=4, claim_gross=400.0)
    root = tmp_path / "arch"
    manifest = _capture(repo, root)
    _write_snapshot(root, manifest)

    dest = tmp_path / "restored"
    res = al.restore(root, "2026-08-20", dest)
    assert res["failed"] == []
    assert res["restored"] == manifest["file_count"]
    assert (dest / al.CRITICAL).read_bytes() == (repo / al.CRITICAL).read_bytes()


def test_restore_drill_passes_on_a_consistent_archive(tmp_path):
    repo = _fake_repo(tmp_path, trips=5, claim_rows=5, claim_gross=500.0)
    root = tmp_path / "arch"
    _write_snapshot(root, _capture(repo, root))

    drill = al.restore_drill(root, repo, deep=False)
    assert drill["status"] == "PASS", drill
    assert drill["rebuilt_from_archive"]["round_trips"] == 5
    assert drill["rebuilt_from_archive"]["gross_pnl"] == 500.0


def test_drill_reads_the_archive_not_the_live_file(tmp_path):
    """THE NEGATIVE CONTROL.

    Capture a 2-trip book, then swap the LIVE ledger to a 3-trip book WITHOUT re-capturing
    and point the canonical table at 3. A drill that genuinely restores from the archive
    reports 2 and FAILS the comparison. A drill that cheats by reading live state reports 3
    and passes -- which would make every future 'archive verified' claim meaningless.
    """
    repo = _fake_repo(tmp_path, trips=2, claim_rows=2, claim_gross=200.0)
    root = tmp_path / "arch"
    _write_snapshot(root, _capture(repo, root))

    # Live moves on; the archive does not.
    (repo / al.CRITICAL).write_bytes(_ledger_bytes(3))
    (repo / "analysis" / "recommendations" / "trade-matrix.json").write_text(
        json.dumps({"row_count": 3, "totals": {"gross": 300.0}}), encoding="utf-8")

    drill = al.restore_drill(root, repo, deep=False)
    assert drill["rebuilt_from_archive"]["round_trips"] == 2, (
        "drill reported the LIVE book -- it is not reading the archive at all")
    assert drill["rebuilt_from_archive"]["gross_pnl"] == 200.0
    assert drill["status"] == "FAILED"
    assert any(c["check"] == "fifo_round_trips_vs_canonical" and not c["pass"]
               for c in drill["checks"]), drill["checks"]


# ────────────────────────────────────────────────────────────── retention + idempotency
def test_second_capture_writes_no_new_blobs(tmp_path):
    """Idempotent by construction: re-running costs zero bytes and destroys nothing."""
    repo = _fake_repo(tmp_path, trips=3, claim_rows=3, claim_gross=300.0)
    root = tmp_path / "arch"
    first = _capture(repo, root)
    second = _capture(repo, root)
    assert first["new_blobs_written"] > 0
    assert second["new_blobs_written"] == 0
    assert second["file_count"] == first["file_count"]


def test_older_snapshots_are_never_pruned(tmp_path):
    """Retention is PERMANENT. An older day's blobs must survive later captures, even
    after the live file has changed -- the opposite of ledger_archive.py's 30-day prune."""
    repo = _fake_repo(tmp_path, trips=2, claim_rows=2, claim_gross=200.0)
    root = tmp_path / "arch"
    day1 = al.capture(repo, root, today="2026-08-18", now_iso="2026-08-18T00:00:00")
    _write_snapshot(root, day1)
    old_sha = next(f for f in day1["files"] if f["rel"] == al.CRITICAL)["sha256"]

    (repo / al.CRITICAL).write_bytes(_ledger_bytes(9))
    day2 = al.capture(repo, root, today="2026-08-20", now_iso="2026-08-20T00:00:00")
    _write_snapshot(root, day2)

    assert (root / al.blob_rel(old_sha)).is_file(), "an older snapshot's blob was pruned"
    assert al.verify_manifest(root, day1, repo=None)["status"] == "OK"
    assert al.latest_snapshot(root) == "2026-08-20"
    # and the OLD day still restores to the OLD book, not the new one
    assert al.restore_drill(root, repo, deep=False, date_str="2026-08-18"
                           )["rebuilt_from_archive"]["round_trips"] == 2


# ────────────────────────────────────────────────────────────── off-volume placement
def test_same_volume_root_is_reported_degraded(tmp_path):
    """An archive beside the repo is better than nothing but must NEVER read as healthy."""
    root, status, reason = al.resolve_archive_root(str(tmp_path / "same-vol"))
    if Path(tmp_path).drive.upper() == REPO.drive.upper():
        assert status == "DEGRADED"
        assert "SAME VOLUME" in reason.upper()
    else:  # pytest tmp dir landed off-volume; the healthy branch must then be reported
        assert status == "HEALTHY"


def test_configured_primary_is_off_volume_from_the_repo():
    """The deliberate design choice, pinned: the default archive root is not on C:."""
    assert al.PRIMARY_ROOT.drive.upper() != REPO.drive.upper(), (
        f"PRIMARY_ROOT {al.PRIMARY_ROOT} shares a volume with the repo {REPO} -- "
        "one disk failure or one `git clean -xfd` would take both copies")


# ────────────────────────────────────────────────────────────── the standing real-data check
def test_live_ledger_still_reproduces_the_canonical_book():
    """Real data, no fixtures: the live fills ledger must FIFO-reconstruct to exactly the
    row count and gross P&L that the canonical trade matrix claims.

    This is the tripwire for silent ledger truncation or rewrite. Measured 2026-08-19:
    303 round trips, gross -$1,805.00.

    WINDOW-BOUNDED 2026-08-21. The original compared the WHOLE live ledger against a
    DATED SNAPSHOT (trade-matrix.json, generated 2026-08-19, date_range 06-26..08-19).
    The ledger is append-only, so that comparison was guaranteed to go RED on the next
    trading day and did: 329 reconstructed vs 303 claimed, purely because we traded on
    08-20 and 08-21.

    That failure mode is worse than useless -- "the ledger grew" and "the ledger was
    truncated or rewritten" reported IDENTICALLY, so the tripwire fired constantly and
    said nothing. Same bug the bold_tier_rail regression anchor had (it drifted to n=20
    and sat RED for days catching nothing) and it has the same fix: bound the live side
    to the window the snapshot actually covers, using the snapshot's OWN declared
    date_range rather than a second hardcoded date that can drift from it.

    Trades after the snapshot's window are not evidence of corruption; they are evidence
    of trading. Re-running trade_matrix_build.py extends the window and this keeps working.
    """
    tm_path = REPO / "analysis" / "recommendations" / "trade-matrix.json"
    if not tm_path.is_file():
        pytest.skip("canonical trade-matrix.json not present")
    tm = json.loads(tm_path.read_text(encoding="utf-8"))
    lo, hi = tm["date_range"]

    sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
    import fills_fifo  # noqa: E402

    trips, gross = 0, 0.0
    for arm in al.ACTIVE_ARMS:
        for t in fills_fifo.mine_real_arm_fills(arm, REPO / al.CRITICAL):
            if lo <= t["date"] <= hi:          # the snapshot's OWN window, not a copy of it
                trips += 1
                gross += float(t["real_pnl"])
    gross = round(gross, 2)

    assert trips == tm["row_count"], (
        f"over the canonical window {lo}..{hi} the ledger reconstructs {trips} round trips "
        f"but the table claims {tm['row_count']} -- the ledger may have been truncated or "
        "rewritten. (Trades AFTER that window are expected and are excluded here.)")
    assert abs(gross - tm["totals"]["gross"]) < 0.005, (
        f"over {lo}..{hi} ledger gross {gross} != canonical {tm['totals']['gross']}")
