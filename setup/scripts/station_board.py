"""station_board.py -- ideas-board persistence for the Station loop
(GOAL-GAMMA-STATION-2026-09-13 item (4)).

Owns `automation/state/station/ideas-board.json` + `station-brief.md`: dedupe (exact
normalized-title match, then difflib title-similarity), the board cap (oldest
killed/proposed rows drop first), and atomic writes (tmp + os.replace, never a partial
file on disk). Also hosts the two generic fail-open JSON/atomic-write primitives shared
with station_loop.py (config load, ledger-adjacent reads) -- kept here rather than a
fourth file since both are a handful of lines and board I/O is their main caller.

Split out of station_loop.py purely to keep that file under the 400-line guideline --
no behavior here depends on anything in station_loop.py or station_facts.py.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Optional


def read_json_or_none(path: Path):
    """Fail-open JSON read: parsed value on success, None on any missing/garbled file."""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return None


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").strip().lower())


def _short_id(title: str) -> str:
    return hashlib.sha256(_normalize_title(title).encode("utf-8")).hexdigest()[:10]


def _is_similar(a: str, b: str, threshold: float) -> bool:
    return difflib.SequenceMatcher(None, _normalize_title(a), _normalize_title(b)).ratio() >= threshold


def load_board(path: Path) -> list:
    data = read_json_or_none(path)
    return data if isinstance(data, list) else []


def _apply_cap(board: list, cap: int) -> list:
    """Drops oldest rows once over `cap`, preferring status in {killed, proposed} before
    ever touching anything else (a card promoted out of those statuses is protected)."""
    over = len(board) - cap
    if over <= 0:
        return board
    droppable = [i for i, c in enumerate(board) if c.get("status") in ("killed", "proposed")]
    to_drop = set(droppable[:over])
    if len(to_drop) < over:
        remaining = over - len(to_drop)
        rest = [i for i in range(len(board)) if i not in to_drop]
        to_drop.update(rest[:remaining])
    return [c for i, c in enumerate(board) if i not in to_drop]


def merge_new_cards(existing: list, new_cards: list, *, ts_et: str, model: str,
                    similarity_threshold: float, max_new: int, cap: int) -> tuple:
    """Returns (new_board, n_added). Dedupes by exact-normalized title and by difflib
    similarity >= similarity_threshold against every title already on the board (existing
    AND any just added this fire); caps at `cap`, dropping oldest killed/proposed first."""
    existing_titles = [c.get("title", "") for c in existing if isinstance(c, dict)]
    board = list(existing)
    added = 0
    for card in new_cards:
        if added >= max_new:
            break
        title = (card.get("title") or "").strip()
        if not title:
            continue
        if any(_normalize_title(title) == _normalize_title(t) for t in existing_titles):
            continue
        if any(_is_similar(title, t, similarity_threshold) for t in existing_titles):
            continue
        board.append({
            "id": _short_id(title),
            "ts_et": ts_et,
            "prompted_by": "station-loop",
            "status": "proposed",
            "model": model,
            "title": title,
            "mechanism": card.get("mechanism", ""),
            "evidence": card.get("evidence", []) if isinstance(card.get("evidence"), list) else [],
            "proposed_shadow_test": card.get("proposed_shadow_test", ""),
            "cost_line": card.get("cost_line", ""),
            "confidence": card.get("confidence", "low"),
        })
        existing_titles.append(title)
        added += 1
    board = _apply_cap(board, cap)
    return board, added


def write_ideas_board(path: Path, board: list) -> None:
    atomic_write_text(path, json.dumps(board, indent=2, ensure_ascii=False))


def write_brief(path: Path, ts_et: str, model: str, brief_text: str, board_size: int) -> None:
    header = f"{ts_et} - model {model} - {board_size} cards on the board\n\n"
    atomic_write_text(path, header + (brief_text or "").strip() + "\n")
