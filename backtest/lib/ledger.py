"""Canonical append-only writer for Project Gamma decision ledgers.

WHY THIS EXISTS
---------------
The decision ledgers (``automation/state/decisions.jsonl`` + the ``aggressive/``
variant + the satellite ``fast-path-decisions.jsonl`` /
``shadow-model-decisions.jsonl`` files) had multiple competing producers writing
INCOMPATIBLE formats into the same append-only files:

  * pretty-printed ``json.dump(obj, f, indent=2)`` -> one logical object spread
    across many physical lines (the #1 corruption: 56/122 rows in the safe
    ledger were fragments of multi-line objects).
  * objects written without a trailing newline -> two objects concatenated on
    one physical line ("Extra data" / "Expecting property name"; 168/427 rows in
    the aggressive ledger).
  * schema drift -- ``bear_score`` vs ``bearish_score``, ``action`` vs
    ``decision``, missing ``tick_id`` / ``date``.

The state-contract test (``backtest/tests/test_state_contracts.py``) documents
this legacy debt. Existing ledger rows are IMMUTABLE by project doctrine -- we do
NOT rewrite history. This module fixes the WRITE side so every NEW row is clean.

THE CONTRACT (one row, one line, always valid)
----------------------------------------------
``append_decision(path, row)``:
  1. validates ``row`` against :class:`DecisionRowModel` (the canonical schema --
     ``tick_id`` + ``date`` + ``action`` required; ``bull_score`` / ``bear_score``
     the canonical score field names) -- raising LOUDLY on a bad row instead of
     writing garbage,
  2. serializes with ``json.dumps(..., separators=(",", ":"))`` -- COMPACT, a
     single physical line,
  3. appends exactly that line plus ``"\n"`` to the file (utf-8, append mode),
     and ``flush()``es so a crash mid-tick still leaves a complete line.

CANONICAL FIELD NAMES (the pin, and why)
----------------------------------------
``action`` (NOT ``decision``) and ``bull_score`` / ``bear_score`` (NOT
``bearish_score``). These are the field names the MAJORITY of consumers already
index on:
  * ``automation/prompts/heartbeat.md`` + ``aggressive/heartbeat.md`` -- the
    producers themselves document this exact shape (``"action": ...``,
    ``"bull_score": 0, "bear_score": 0``).
  * ``backtest/autoresearch/eod_deep/main.py`` (``d.get("tick_id")``,
    ``time_et``, ``action``).
  * ``backtest/autoresearch/pattern_backtest.py`` (``action``, ``bull_score``,
    ``bear_score``).
  * ``backtest/tools/near_miss_audit.py`` (``bear_score`` / ``bull_score`` /
    ``action``).
  * ``setup/scripts/shadow_model_eval.py`` (``bull_score`` from the ledger).
So the canonical schema = ``DecisionRowModel`` as it already stands. This module
just enforces it at the write boundary.

SCOPE
-----
Lean by design: one writer helper. It does NOT touch existing data and does NOT
change any producer's decision LOGIC -- producers only swap their ad-hoc write
call for ``append_decision``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Union

from pydantic import ValidationError

from .contracts import DecisionRowModel, StateContractError

__all__ = ["append_decision", "serialize_decision"]


def serialize_decision(row: Dict[str, Any]) -> str:
    """Validate ``row`` and return its canonical single-line JSON string.

    No trailing newline (callers that already manage newlines, e.g. a batch
    writer, can add their own). Raises :class:`StateContractError` if the row
    violates :class:`DecisionRowModel`.

    Validation goes through :class:`DecisionRowModel` (fail-loud on a bad row),
    but the SERIALIZED line is the producer's ORIGINAL ``row`` -- not
    ``model_dump()``. This is deliberate: ``model_dump()`` injects ``null`` for
    every unset Optional field (``time_et``, ``setup_name``, ...) the producer
    never wrote, polluting the ledger with keys it didn't intend. Serializing the
    validated input keeps the line exactly what the producer emitted (every
    diagnostic key, in producer order, no injected nulls) while still guaranteeing
    it satisfies the contract.
    """
    try:
        DecisionRowModel.model_validate(row)
    except ValidationError as exc:
        # Re-raise as the project's loud, file-naming contract error. We have no
        # path here, so name the schema; callers that DO have a path (the writer
        # below) raise a path-tagged variant.
        raise StateContractError("<decision-row>", DecisionRowModel, exc) from exc

    return json.dumps(
        row,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def append_decision(path: Union[str, Path], row: Dict[str, Any]) -> None:
    """Append ONE validated decision row as ONE compact JSON line.

    This is the single canonical writer every Python producer of a decision
    ledger should call instead of its own ``open(...,'a')`` + ``json.dump`` /
    ``json.dumps`` block. It guarantees one-row-per-line, canonical-schema output
    forever.

    Parameters
    ----------
    path:
        Target ``.jsonl`` ledger (created with parents if absent).
    row:
        The decision dict. MUST carry ``tick_id`` (int), ``date`` (str), and
        ``action`` (str); ``bull_score`` / ``bear_score`` and any diagnostic
        keys are optional and ride along.

    Raises
    ------
    StateContractError:
        If ``row`` violates :class:`DecisionRowModel` -- FAIL LOUD, write nothing.
        (The whole point: a malformed row never reaches disk to corrupt the
        ledger; the producer crashes visibly instead.)
    """
    p = Path(path)

    # Validate + serialize BEFORE touching the file. If this raises, nothing is
    # written -- no half-line, no garbage.
    try:
        line = serialize_decision(row)
    except StateContractError as exc:
        # Re-tag with the real destination path so the operator sees WHICH ledger
        # the bad write targeted.
        raise StateContractError(p, DecisionRowModel, exc.cause) from exc

    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
