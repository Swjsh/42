"""regime_stamp.py -- morning day-archetype stamp for the premarket surface (WS6).

Runs at 08:22 ET (Gamma_RegimeStamp), between Gamma_EmaSnapshot (08:20) and
Gamma_Premarket (08:30), mirroring the compute_ema_snapshot.py pre-seeder pattern:

  1. REBUILD analysis/regime-library/day-archetypes.json from the pinned CSV
     lineage (pure Python, deterministic -- the 16:16 ET data-append task has
     already landed yesterday's bars by now). Fail-open: if the rebuild throws,
     keep the stale artifact and stamp from it, flagging artifact_fresh=false.
  2. WRITE automation/state/regime-stamp.json -- the authoritative stamp:
     "yesterday was X, the recent mix is Y".
  3. PATCH automation/state/today-bias.json with a top-level ``regime_context``
     key (contract-safe: state models are ConfigDict(extra="allow")). The
     premarket prompt also lifts the stamp itself when it writes the file fresh.

DESCRIPTIVE ONLY -- the archetype of a COMPLETED day. Never a live entry input.

Cost: $0. No LLM, no MCP, no network.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3 -- copy of the 2026-07-14 fix) ===
# pythonw.exe + Windows 11 default-terminal can flash a WindowsTerminal window on
# the first stdout/stderr write. Redirect BEFORE any other import can print.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "regime-stamp.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "regime-stamp.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import datetime as dt
import json
import os
import sys
import time
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO / "backtest"), str(REPO / "backtest" / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

STATE_DIR = REPO / "automation" / "state"
STAMP_PATH = STATE_DIR / "regime-stamp.json"
BIAS_PATH = STATE_DIR / "today-bias.json"
ART_PATH = REPO / "analysis" / "regime-library" / "day-archetypes.json"

ET = ZoneInfo("America/New_York")   # zoneinfo conversion from UTC -- DST-correct
                                    # (the TZ foot-gun is Bash `TZ=` / naive local)


def _atomic_write_bytes_with_retry(path: Path, data: bytes, attempts: int = 4,
                                    base_delay_s: float = 0.35) -> None:
    """Write ``data`` to ``path`` atomically, retrying transient lock/race errors.

    Root cause (2026-08-04): a direct ``Path.write_bytes`` (open-for-write in
    place) on this OneDrive-synced repo (`%OneDrive%` env var set on this box --
    Desktop is a Known-Folder-Move target) hit a one-off
    ``OSError: [Errno 22] Invalid argument`` at 08:22:0x ET, almost certainly a
    transient OneDrive/AV handle race on the target file. The write raised,
    ``main()`` propagated the exception uncaught, and Python exited nonzero --
    but the launcher (``run_exe_hidden.vbs``'s ``shell.Run cmd, 0, False``) is
    fire-and-forget and never reports that exit code back to Task Scheduler, so
    ``LastTaskResult`` still read 0/"success" while ``regime-stamp.json`` sat
    frozen on the PRIOR day's content for 24h+ (self_check's REGIME-STAMP DRIFT
    check caught the *consequence*, not the cause). Two independent hardenings:
    (1) write to a unique temp file in the SAME directory then ``os.replace``
    (atomic rename -- never leaves a half-written or previously-open target
    file mid-write, and a temp-file CREATE is far less likely to collide with
    whatever briefly held the real path's handle); (2) retry a few times with
    backoff, since the lock (if OneDrive/AV) is normally sub-second.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    last_err: OSError | None = None
    for attempt in range(1, attempts + 1):
        try:
            tmp_path.write_bytes(data)
            os.replace(tmp_path, path)
            return
        except OSError as e:
            last_err = e
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
            if attempt < attempts:
                time.sleep(base_delay_s * attempt)
    assert last_err is not None
    raise last_err


def rebuild_artifact() -> bool:
    """Rebuild the library in-process. True on success, False = stamp from stale."""
    try:
        import build_day_archetypes as bda
        payload = bda.serialize(bda.build_artifact())
        bda.OUT_DIR.mkdir(parents=True, exist_ok=True)
        bda.OUT_JSON.write_bytes(payload)
        return True
    except Exception as e:  # fail-open, loud
        print(f"[WARN] regime library rebuild failed ({e!r}) -- stamping from "
              f"the existing artifact if present", file=sys.stderr)
        return False


def _fmt_pct(x: float) -> str:
    return f"{x:+.2f}%".replace("+-", "-")


def compose(artifact: dict, today_et: dt.date, fresh: bool) -> dict:
    days = artifact["days"]
    assignable = [(d, r) for d, r in sorted(days.items())
                  if r["archetype"] != "data-incomplete" and d < today_et.isoformat()]
    if not assignable:
        raise RuntimeError("no assignable days before today in the regime library")
    ydate, yrec = assignable[-1]
    recent = assignable[-25:]
    mix: dict[str, int] = {}
    for _, r in recent:
        mix[r["archetype"]] = mix.get(r["archetype"], 0) + 1
    mix_sorted = sorted(mix.items(), key=lambda kv: (-kv[1], kv[0]))
    mix_str = ", ".join(f"{k} {v}/25" for k, v in mix_sorted[:3])
    full_pct = artifact["distribution"]["full_pct"]
    n_pop = artifact["distribution"]["n_assignable"]
    top_recent = mix_sorted[0][0]
    one_liner = (
        f"Yesterday {ydate} ({yrec['dow']}) = {yrec['archetype']} "
        f"(range {yrec['range_pct']:.2f}%, gap {_fmt_pct(yrec['gap_pct']) if yrec['gap_pct'] is not None else 'n/a'}, "
        f"close_loc {yrec['close_loc']:.2f}). "
        f"Last-25 mix: {mix_str}; population baseline {top_recent} "
        f"{full_pct.get(top_recent, 0.0):.1f}% over {n_pop}d."
        + ("" if fresh else " [STALE LIBRARY -- rebuild failed this morning]")
    )
    return {
        "date": today_et.isoformat(),
        "generated_at_et": dt.datetime.now(tz=ET).isoformat(timespec="seconds"),
        "artifact_fresh": fresh,
        "spec_version": artifact.get("spec_version"),
        "yesterday": {
            "date": ydate,
            "archetype": yrec["archetype"],
            "session": yrec["session"],
            "range_pct": yrec["range_pct"],
            "gap_pct": yrec["gap_pct"],
            "close_loc": yrec["close_loc"],
            "vix_open": yrec["vix_open"],
            "vix_close": yrec["vix_close"],
        },
        "last_25_mix": {k: v for k, v in mix_sorted},
        "one_liner": one_liner,
        "_doc": ("Post-hoc day archetypes (analysis/regime-library). DESCRIPTIVE "
                 "ONLY -- never a live entry input for the current day."),
    }


def patch_today_bias(stamp: dict) -> bool:
    """Set today-bias.json#regime_context (this script owns that key)."""
    if not BIAS_PATH.exists():
        return False
    try:
        bias = json.loads(BIAS_PATH.read_bytes().decode("utf-8", errors="replace"))
        bias["regime_context"] = {
            "one_liner": stamp["one_liner"],
            "yesterday_archetype": stamp["yesterday"]["archetype"],
            "stamp_date": stamp["date"],
            "source": "regime_stamp_0822ET",
        }
        _atomic_write_bytes_with_retry(
            BIAS_PATH, json.dumps(bias, indent=2).encode("utf-8"))
        return True
    except Exception as e:
        print(f"[WARN] could not patch today-bias.json: {e}", file=sys.stderr)
        return False


def main() -> int:
    fresh = rebuild_artifact()
    if not ART_PATH.exists():
        print(f"[ERROR] no regime library artifact at {ART_PATH} and rebuild failed",
              file=sys.stderr)
        return 1
    artifact = json.loads(ART_PATH.read_text(encoding="ascii"))
    today_et = dt.datetime.now(tz=ET).date()
    stamp = compose(artifact, today_et, fresh)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_write_bytes_with_retry(
        STAMP_PATH,
        (json.dumps(stamp, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    print(f"[OK] regime-stamp.json written: {stamp['one_liner']}")
    if patch_today_bias(stamp):
        print("[OK] today-bias.json regime_context patched")
    else:
        print("[INFO] today-bias.json not patched (missing or unreadable)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
