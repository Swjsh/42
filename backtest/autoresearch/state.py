"""Persistent state for the autoresearch loop.

State files (per-mode if mode is set):
    _state/{mode}/state.json     — current params + train + validate baselines
    _state/{mode}/history.jsonl  — append-only log
    _state/state.json + history.jsonl  — when mode is None (legacy default)

Reverting a modification means we DO NOT update state.json, but we DO
append to history.jsonl with decision.keep=False.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import config
from .metrics import TradeMetrics

logger = logging.getLogger(__name__)
ROOT_STATE_DIR = Path(__file__).resolve().parent / "_state"
ROOT_STATE_DIR.mkdir(parents=True, exist_ok=True)


def _state_dir(mode: str | None) -> Path:
    """Return the per-mode state directory (creates it if needed)."""
    if mode is None:
        return ROOT_STATE_DIR
    p = ROOT_STATE_DIR / mode
    p.mkdir(parents=True, exist_ok=True)
    return p


def _state_file(mode: str | None) -> Path:
    return _state_dir(mode) / "state.json"


def _history_file(mode: str | None) -> Path:
    return _state_dir(mode) / "history.jsonl"


@dataclass
class State:
    """Persistent autoresearch state — extended for train/validate split + experiments."""

    current_params: dict[str, Any] = field(default_factory=dict)
    baseline_metrics: dict[str, Any] = field(default_factory=dict)           # TRAIN baseline
    validate_baseline_metrics: dict[str, Any] = field(default_factory=dict)  # VALIDATE baseline
    training_window: dict[str, str] = field(default_factory=dict)
    validate_window: dict[str, str] = field(default_factory=dict)
    iteration: int = 0
    modifications_kept: int = 0
    modifications_reverted: int = 0
    last_param_modified: str | None = None
    last_modification_at: str | None = None
    recently_modified: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: dt.datetime.utcnow().isoformat(timespec="seconds"))
    session_id: str | None = None
    mode: str | None = None
    experiment: str | None = None    # NEW 2026-05-09: which knob tier (lean/entries/exits/full/kitchen_sink)
    objective: str = config.DEFAULT_OBJECTIVE  # NEW 2026-05-09: train_sharpe (default) | validate_sharpe | validate_pnl | validate_expectancy

    def touch_param(self, param: str) -> None:
        # `param` may be "+"-joined for multi-knob proposals; record each one.
        self.last_param_modified = param
        self.last_modification_at = dt.datetime.utcnow().isoformat(timespec="seconds")
        for p in param.split("+"):
            self.recently_modified.insert(0, p)
        self.recently_modified = self.recently_modified[: config.PARAM_COOLDOWN_ITERATIONS]


def fresh_state(
    train_start: dt.date,
    train_end: dt.date,
    validate_start: dt.date,
    validate_end: dt.date,
    session_id: str | None = None,
    mode: str | None = None,
    starting_params: dict[str, Any] | None = None,
    experiment: str | None = None,
    objective: str = config.DEFAULT_OBJECTIVE,
) -> State:
    """Brand-new state seeded with mode-specific (or production) defaults."""
    params = starting_params if starting_params is not None else dict(config.BASELINE_PARAMS)
    # Always merge in any keys missing from the starting set (auto-seed new knobs).
    params = config.merge_missing_knobs(params)
    tag_parts = [mode, experiment]
    if objective != config.DEFAULT_OBJECTIVE:
        tag_parts.append(objective)
    tag = "_".join(filter(None, tag_parts))
    return State(
        current_params=params,
        baseline_metrics={},
        validate_baseline_metrics={},
        training_window={"start": train_start.isoformat(), "end": train_end.isoformat()},
        validate_window={"start": validate_start.isoformat(), "end": validate_end.isoformat()},
        iteration=0,
        mode=mode,
        experiment=experiment,
        objective=objective,
        session_id=(
            session_id
            or f"ar_{tag or 'default'}_{dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        ),
    )


def load_state(mode: str | None = None) -> State | None:
    sf = _state_file(mode)
    if not sf.exists():
        return None
    with open(sf, "r") as f:
        data = json.load(f)
    # Drop unknown keys (in case schema evolves and old state has stale fields).
    valid_fields = {f.name for f in State.__dataclass_fields__.values()}
    data = {k: v for k, v in data.items() if k in valid_fields}
    s = State(**data)
    # Auto-seed any new knobs that weren't in this state file.
    s.current_params = config.merge_missing_knobs(s.current_params)
    return s


def save_state(s: State) -> None:
    sf = _state_file(s.mode)
    tmp = sf.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(asdict(s), f, indent=2, default=str)
    tmp.replace(sf)


def append_history(record: dict, mode: str | None = None) -> None:
    """Append one JSON line to history.jsonl. Adds a UTC timestamp if missing."""
    record.setdefault("at", dt.datetime.utcnow().isoformat(timespec="seconds"))
    hf = _history_file(mode)
    with open(hf, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def update_baseline(s: State, m: TradeMetrics) -> None:
    """Replace TRAIN baseline metrics with a new TradeMetrics."""
    s.baseline_metrics = m.to_dict()


def update_validate_baseline(s: State, m: TradeMetrics) -> None:
    """Replace VALIDATE baseline metrics with a new TradeMetrics."""
    s.validate_baseline_metrics = m.to_dict()


# Legacy module-level constants kept for any old callers / tests.
STATE_DIR = ROOT_STATE_DIR
STATE_FILE = ROOT_STATE_DIR / "state.json"
HISTORY_FILE = ROOT_STATE_DIR / "history.jsonl"
