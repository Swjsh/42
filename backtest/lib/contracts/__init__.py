"""Contract validation for Project Gamma's load-bearing state files.

WHY THIS EXISTS
---------------
State files (``automation/state/*.json``, ``*.jsonl``) are the integration bus
between ~34 scheduled tasks. Today they are read with raw ``json.load`` -> a
missing or renamed field silently becomes ``None`` in the consumer, which then
makes a wrong decision with no error. That producer/consumer-silent-break bug
class has been hand-fixed for multiple nights (see CLAUDE.md "wave 1/2 of
bulletproofing", L84/L96/L106/L117 in the Lessons index).

THE FIX
-------
One typed Pydantic model per load-bearing state file, validated at the read
boundary. A consumer that reads a field a producer never wrote now fails LOUDLY
at read time (``StateContractError`` naming the file + the offending field),
instead of silently seeing ``None``.

SCOPE (lean by design)
-----------------------
Only the ~10 files that actually caused bugs are modeled -- NOT all 165 state
files. Every model sets ``extra='allow'`` so the 29 prose ``_doc`` essays and
diagnostic keys these files legitimately carry do not break validation. We are
asserting that the REQUIRED consumed fields EXIST and have the right shape, not
banning extras.

PUBLIC API
----------
``load_validated(path, model)``  -- read one JSON file, return validated model.
``load_jsonl_rows(path, model)`` -- read a JSONL ledger, return validated rows.
``StateContractError``           -- raised on any contract violation.

Plus the model classes (see ``contracts.models``), re-exported here.

MIGRATION NOTE
--------------
This package is ADDITIVE. Existing consumers still use raw ``json.load`` today.
Consumers should adopt ``load_validated`` INCREMENTALLY -- swap a raw
``json.loads(path.read_text())`` for ``load_validated(path, ParamsModel)`` one
call site at a time. No big-bang rewrite is required (or wanted) for Phase 0b.
The contract test (``backtest/tests/test_state_contracts.py``) proves every
current live file already validates, so adoption is safe to do piecemeal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, NamedTuple, Type, TypeVar, Union

from pydantic import BaseModel, ValidationError

from .models import (
    AggressiveCircuitBreakerModel,
    AggressiveParamsModel,
    CircuitBreakerModel,
    DecisionRowModel,
    KeyLevelsModel,
    LevelModel,
    LoopStateModel,
    ParamsModel,
    PositionModel,
    TodayBiasModel,
    WatcherObservationRowModel,
)

__all__ = [
    "StateContractError",
    "LedgerScan",
    "load_validated",
    "load_jsonl_rows",
    # models
    "ParamsModel",
    "AggressiveParamsModel",
    "LoopStateModel",
    "PositionModel",
    "CircuitBreakerModel",
    "AggressiveCircuitBreakerModel",
    "TodayBiasModel",
    "KeyLevelsModel",
    "LevelModel",
    "DecisionRowModel",
    "WatcherObservationRowModel",
]

_ModelT = TypeVar("_ModelT", bound=BaseModel)


class StateContractError(Exception):
    """Raised when a state file violates its declared contract.

    Carries the offending file path and the underlying pydantic
    ``ValidationError`` so callers can log a precise, actionable message
    (which file, which field, what was wrong) instead of a bare ``KeyError``
    or a silent ``None``.
    """

    def __init__(self, path: Union[str, Path], model: Type[BaseModel], cause: Exception):
        self.path = str(path)
        self.model_name = model.__name__
        self.cause = cause
        super().__init__(self._format())

    def _format(self) -> str:
        header = (
            f"State contract violation in '{self.path}' "
            f"(expected schema: {self.model_name}):"
        )
        if isinstance(self.cause, ValidationError):
            lines = []
            for err in self.cause.errors():
                loc = ".".join(str(p) for p in err.get("loc", ())) or "<root>"
                msg = err.get("msg", "invalid")
                lines.append(f"  - field '{loc}': {msg}")
            return header + "\n" + "\n".join(lines)
        return f"{header}\n  - {self.cause}"


def _read_text_bom_tolerant(path: Path) -> str:
    """Read a file as UTF-8, tolerant of a leading BOM.

    Several Gamma state files were written by PowerShell with a UTF-8 BOM
    (e.g. params.json -- note the mojibake ``â€”`` em-dashes in
    its ``_doc``). ``utf-8-sig`` strips the BOM if present and is a no-op
    otherwise, so this is always safe.
    """
    return path.read_text(encoding="utf-8-sig")


def load_validated(path: Union[str, Path], model: Type[_ModelT]) -> _ModelT:
    """Read a single JSON state file and return it as a validated model.

    This is the function consumers should use INSTEAD of raw ``json.load`` /
    ``json.loads``. On a contract violation (missing required field, wrong
    type) it raises :class:`StateContractError` naming the file and field --
    the whole point of Phase 0b -- rather than letting the consumer read a
    silent ``None``.

    Parameters
    ----------
    path:
        Path to the ``.json`` file.
    model:
        The Pydantic model class to validate against (e.g. ``ParamsModel``).

    Raises
    ------
    FileNotFoundError:
        If ``path`` does not exist. (Absence is a distinct, louder failure
        than corruption -- callers decide whether a missing file is fatal.)
    StateContractError:
        If the file is not valid JSON, or violates the model contract.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"State file not found: {p}")

    raw = _read_text_bom_tolerant(p)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StateContractError(p, model, exc) from exc

    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise StateContractError(p, model, exc) from exc


class LedgerScan(NamedTuple):
    """Result of a lenient JSONL ledger scan.

    ``rows``    -- validated models for every conforming line.
    ``errors``  -- ``(lineno, reason)`` for every line that failed (bad JSON or
                   contract violation). Empty means the whole ledger is clean.
    ``total``   -- count of non-blank lines examined.
    """

    rows: List[Any]
    errors: List[tuple]
    total: int


def load_jsonl_rows(
    path: Union[str, Path], model: Type[_ModelT], strict: bool = True
) -> Union[List[_ModelT], LedgerScan]:
    """Read an append-only JSONL ledger of validated rows.

    Blank lines are skipped. Each non-blank line must be a JSON object that
    satisfies ``model``.

    ``strict=True`` (default, for consumers): returns ``List[model]`` and raises
    :class:`StateContractError` on the FIRST offending row, naming the file +
    1-based line number. This is what a live consumer wants -- fail loud on a
    malformed row rather than silently skip it.

    ``strict=False`` (for audits / health checks): returns a :class:`LedgerScan`
    with the good rows AND a structured list of per-line errors, never raising on
    a bad row. Use this to REPORT corruption in long-lived ledgers (e.g.
    ``decisions.jsonl`` carries rows from several retired writer versions) without
    aborting on the first one.

    Used for ``decisions.jsonl`` and ``watcher-observations.jsonl``. These
    ledgers are append-only and long-lived, so rows from older schema versions
    can coexist -- the row models keep all-but-the-key-fields optional so old
    rows still validate (the whole point: assert the consumed fields exist,
    tolerate the rest).
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"State ledger not found: {p}")

    rows: List[_ModelT] = []
    errors: List[tuple] = []
    total = 0
    for lineno, line in enumerate(_read_text_bom_tolerant(p).splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        total += 1
        try:
            data = json.loads(stripped)
            rows.append(model.model_validate(data))
        except (json.JSONDecodeError, ValidationError) as exc:
            if strict:
                raise StateContractError(f"{p}:{lineno}", model, exc) from exc
            reason = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
            errors.append((lineno, reason))

    if strict:
        return rows
    return LedgerScan(rows=rows, errors=errors, total=total)
