"""Reproducibility layer for backtest runs.

Karpathy method principle 5: every backtest run must be content-addressed so a
result that "changes" between runs is unambiguously attributable to data drift,
code drift, or params drift — never an unknown.

Public API:
    compute_run_id(spy_path, vix_path, params_path) -> RunIdentity
    write_registry_entry(run_identity, label, metadata) -> None

Hashes:
    data_hash   = sha256(spy_csv_bytes + vix_csv_bytes)
    code_hash   = git rev-parse HEAD if available, else sha256 of lib/*.py
    params_hash = sha256 of params.json (canonical JSON)

run_id format: {date}_{code_hash[:8]}_{data_hash[:6]}_{params_hash[:6]}
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

# CREATE_NO_WINDOW = 0x08000000 — suppress conhost on Windows subprocess spawns. OP-27 L41.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

REPO = Path(__file__).resolve().parents[2]
LIB_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = REPO / "analysis" / "backtests" / "REGISTRY.jsonl"


@dataclass(frozen=True)
class RunIdentity:
    """Frozen content-address of a backtest run's inputs."""

    run_id: str
    data_hash: str
    code_hash: str
    params_hash: str
    spy_path: str
    vix_path: str
    params_path: str
    spy_bytes: int
    vix_bytes: int
    code_source: str  # "git" or "files"
    computed_at: str


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _hash_inputs(spy_path: Path, vix_path: Path) -> tuple[str, int, int]:
    """Hash of (spy_csv || vix_csv). Order-stable: spy first, then vix.

    Returns (combined_hash, spy_bytes, vix_bytes).
    """
    spy_bytes = spy_path.read_bytes()
    vix_bytes = vix_path.read_bytes()
    h = hashlib.sha256()
    h.update(spy_bytes)
    h.update(vix_bytes)
    return h.hexdigest(), len(spy_bytes), len(vix_bytes)


def _git_rev_parse_head() -> str | None:
    """Return current git commit SHA, or None if not in a git repo / git missing."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _hash_lib_directory() -> str:
    """Fallback when git unavailable: hash all lib/*.py files in a stable order."""
    h = hashlib.sha256()
    for py_file in sorted(LIB_DIR.glob("*.py")):
        h.update(py_file.name.encode("utf-8"))
        h.update(b"\x00")
        h.update(py_file.read_bytes())
        h.update(b"\x00")
    return h.hexdigest()


def _compute_code_hash() -> tuple[str, str]:
    """Returns (hash, source) where source is 'git' or 'files'."""
    git_sha = _git_rev_parse_head()
    if git_sha:
        return git_sha, "git"
    return _hash_lib_directory(), "files"


def _hash_params(params_path: Path) -> str:
    """Canonicalize params.json (sort keys, no whitespace) before hashing.

    Defends against trivial whitespace/key-order changes producing false drift.
    """
    raw = json.loads(params_path.read_text(encoding="utf-8"))
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(canonical.encode("utf-8"))


def compute_run_id(
    spy_path: Path,
    vix_path: Path,
    params_path: Path | None = None,
) -> RunIdentity:
    """Compute content-addressed identity for a backtest run.

    params_path defaults to automation/state/params.json relative to repo root.
    """
    if params_path is None:
        params_path = REPO / "automation" / "state" / "params.json"
    if not spy_path.exists():
        raise FileNotFoundError(f"spy data missing: {spy_path}")
    if not vix_path.exists():
        raise FileNotFoundError(f"vix data missing: {vix_path}")
    if not params_path.exists():
        raise FileNotFoundError(f"params.json missing: {params_path}")

    data_hash, spy_bytes, vix_bytes = _hash_inputs(spy_path, vix_path)
    code_hash, code_source = _compute_code_hash()
    params_hash = _hash_params(params_path)
    today = dt.date.today().isoformat()
    run_id = f"{today}_{code_hash[:8]}_{data_hash[:6]}_{params_hash[:6]}"

    return RunIdentity(
        run_id=run_id,
        data_hash=data_hash,
        code_hash=code_hash,
        params_hash=params_hash,
        spy_path=str(spy_path),
        vix_path=str(vix_path),
        params_path=str(params_path),
        spy_bytes=spy_bytes,
        vix_bytes=vix_bytes,
        code_source=code_source,
        computed_at=dt.datetime.now().isoformat(timespec="seconds"),
    )


def write_registry_entry(
    identity: RunIdentity,
    label: str,
    metadata: dict,
) -> None:
    """Append one JSONL row to analysis/backtests/REGISTRY.jsonl.

    The registry is the durable index: any historical run can be reproduced by
    looking up its row, checking the hashes against current state, and re-running
    if all three match (or accepting that re-running with different hashes
    produces a different run_id).
    """
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {
        **asdict(identity),
        "label": label,
        "summary_metrics": {
            "trades_fired": metadata.get("trades_fired"),
            "hit_rate": metadata.get("hit_rate"),
            "total_pnl": metadata.get("total_pnl"),
            "expectancy": metadata.get("expectancy"),
            "max_drawdown": metadata.get("max_drawdown"),
            "wl_ratio": metadata.get("wl_ratio"),
            "thresholds_passed": metadata.get("thresholds_passed"),
        },
    }
    with REGISTRY_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def load_registry() -> list[dict]:
    """Read all registry entries. Returns [] if registry missing."""
    if not REGISTRY_PATH.exists():
        return []
    rows: list[dict] = []
    with REGISTRY_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def find_by_run_id(run_id: str) -> dict | None:
    """Look up a registry row by run_id."""
    for row in load_registry():
        if row.get("run_id") == run_id:
            return row
    return None
