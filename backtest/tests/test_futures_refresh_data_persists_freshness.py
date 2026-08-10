"""Guard for the 2026-08-10 conductor fix: `refresh_data()` (the live futures tick's
data-refresh call) must PERSIST `futures_live_data.FRESHNESS_FILE` on every call.

Root cause reproduced here: before this fix, `data-freshness.json` was only ever
written by `futures_live_data.py`'s own `--append`/`--check` CLI path. The live tick
loop (`futures_trader_core.refresh_data`, called from `run_tick` every 5 minutes
09:30-16:00 ET) read that file to decide whether to re-fetch, but never wrote it back
-- so the persisted snapshot silently froze at whatever a manual CLI run last wrote,
even while the live bar cache itself kept refreshing correctly. Caught 2026-08-10 via
`state_freshness_audit.py`: the file was dated 2026-08-09 on a live 2026-08-10 session.

This is the exact C7 class (silent success: something IS happening, but the thing
that's supposed to prove it happened stopped updating) that `futures_live_data.py`'s
own module docstring warns about -- the watchdog needed a watchdog on its own writer.

A second latent bug fixed in the same edit: the `data_refresh_failed` exception
handler referenced an undefined `paths` name, which would have raised a `NameError`
(masking the real fetch failure) the first time `append_live` ever actually raised.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

from futures import futures_live_data as fld  # noqa: E402
from futures import futures_trader_core as core  # noqa: E402

NOW = dt.datetime(2026, 8, 10, 11, 0)


@pytest.fixture()
def isolated_freshness_file(tmp_path, monkeypatch):
    """Point the module-level FRESHNESS_FILE/STATE_DIR at a scratch dir so this test
    never touches the real automation/state/futures/data-freshness.json."""
    state_dir = tmp_path / "futures_state"
    freshness_file = state_dir / "data-freshness.json"
    monkeypatch.setattr(fld, "STATE_DIR", state_dir)
    monkeypatch.setattr(fld, "FRESHNESS_FILE", freshness_file)
    return freshness_file


class TestRefreshDataPersistsFreshness:
    def test_refresh_data_writes_the_freshness_file(self, isolated_freshness_file,
                                                      monkeypatch):
        """The core regression: calling refresh_data() must leave a freshly-stamped
        FRESHNESS_FILE behind, not just an in-memory return value."""
        monkeypatch.setattr(fld, "append_live", lambda root, interval, **kw: {"ok": True})
        monkeypatch.setattr(fld, "freshness",
                            lambda root, interval: {"root": root, "verdict": "CLOSED"})
        monkeypatch.setattr(core, "et_now", lambda: NOW)
        monkeypatch.setattr(fld, "et_now", lambda: NOW)

        assert not isolated_freshness_file.exists()
        core.refresh_data("MES", "5m", force=True)

        assert isolated_freshness_file.exists(), \
            "refresh_data() must call write_freshness_snapshot -- the file was never written"
        snap = json.loads(isolated_freshness_file.read_text(encoding="utf-8"))
        assert snap["written_at_et"] == NOW.isoformat(timespec="seconds")
        assert "MES" in snap["feeds"]

    def test_stale_persisted_snapshot_gets_refreshed_on_next_tick(
            self, isolated_freshness_file, monkeypatch):
        """Reproduces the exact caught bug: an old on-disk snapshot (from a manual CLI
        run yesterday) must NOT survive a live tick untouched."""
        stale = NOW - dt.timedelta(days=1)
        isolated_freshness_file.parent.mkdir(parents=True, exist_ok=True)
        isolated_freshness_file.write_text(json.dumps({
            "written_at_et": stale.isoformat(timespec="seconds"),
            "feeds": {"MES": {"verdict": "CLOSED"}},
            "verdict": "CLOSED",
        }), encoding="utf-8")

        monkeypatch.setattr(fld, "append_live", lambda root, interval, **kw: {"ok": True})
        monkeypatch.setattr(fld, "freshness",
                            lambda root, interval: {"root": root, "verdict": "GREEN"})
        monkeypatch.setattr(core, "et_now", lambda: NOW)
        monkeypatch.setattr(fld, "et_now", lambda: NOW)

        core.refresh_data("MES", "5m", force=False)

        snap = json.loads(isolated_freshness_file.read_text(encoding="utf-8"))
        written = dt.datetime.fromisoformat(snap["written_at_et"])
        assert written == NOW, (
            f"persisted snapshot still stamped {written}, expected it refreshed to {NOW} "
            "-- refresh_data() did not re-persist on this tick"
        )

    def test_a_failed_fetch_does_not_raise_nameerror(self, isolated_freshness_file,
                                                       monkeypatch):
        """The second bug: the except-branch referenced an undefined `paths` name.
        A real append_live failure must be caught and journaled, never crash the tick."""
        def _boom(root, interval, **kw):
            raise RuntimeError("yfinance unreachable")

        monkeypatch.setattr(fld, "append_live", _boom)
        monkeypatch.setattr(fld, "freshness",
                            lambda root, interval: {"root": root, "verdict": "BLIND"})
        monkeypatch.setattr(core, "et_now", lambda: NOW)

        # Must not raise -- pre-fix this hit `NameError: name 'paths' is not defined`
        # inside the except block, which is worse than the original failure: it masks
        # the real fetch error entirely.
        result = core.refresh_data("MES", "5m", force=True)
        assert result["verdict"] == "BLIND"
