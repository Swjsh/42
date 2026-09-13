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


# ---- config.json + tv.json merge (security amendment 6, 2026-09-13) ----
# automation/state/station/config.json is TRACKED in a PUBLIC repo (GitHub Swjsh/42).
# It must never carry real network facts -- TV IP/MAC, this PC's LAN IPs, or the
# derived LAN URL of the Station page. Those live ONLY in tv.json (gitignored,
# Fable's LAN-discovery output) and are overlaid on top of config.json AT RUNTIME,
# in memory, by this function -- config.json on disk is never rewritten with them.

def load_merged_station_config(config_path: Path, tv_json_path: Path) -> dict:
    """Loads config_path as the base config, then overlays tv_json_path's
    tv_host/tv_mac/pc_lan_ips on top (tv.json wins when present). Raises
    ValueError("tv.json missing") if tv.json does not exist or fails to parse --
    callers (station_serve.py's bind, station_tv.py's every command) MUST treat
    that as a hard stop: never bind a wildcard address, never guess a LAN IP or
    MAC, never fabricate a station_url. A garbled/missing config.json still
    degrades to {} (config.json's own contract is fail-open; only the tv.json
    half of this merge is fail-loud, since a missing config.json only loses
    non-identifying defaults while a missing tv.json would otherwise silently
    zero out the identifying facts this whole file exists to keep off disk)."""
    config = read_json_or_none(config_path)
    merged = dict(config) if isinstance(config, dict) else {}
    tv = read_json_or_none(tv_json_path)
    if not isinstance(tv, dict):
        raise ValueError("tv.json missing")
    for key in ("tv_host", "tv_mac", "pc_lan_ips"):
        if tv.get(key) is not None:
            merged[key] = tv[key]
    return merged


# ---- Dashboard inbox consumption (interactivity amendment, 2026-09-13) ----
# The Next.js dashboard's /api/station/action route appends {ts_et, card_id, action,
# note} rows to automation/state/station/station-inbox.jsonl for each Test/Kill/Ask
# button press. station_loop.py drains that file every fire (see apply_inbox_actions
# below) -- never gated on the model call, since applying a status change is a pure,
# cheap, deterministic file edit with no LLM and no trading-path involvement.

def read_jsonl(path: Path) -> list:
    """Fail-open JSONL read: one dict per non-blank line; a malformed line is
    skipped rather than aborting the whole read (same contract as read_json_or_none,
    just for the line-delimited shape). Missing/unreadable file -> []."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return []
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def append_jsonl(path: Path, rows: list) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def apply_inbox_actions(board: list, inbox_rows: list) -> tuple:
    """Applies J's per-card Test/Kill/Ask actions to the board. Returns
    (new_board, pending_notes):
      * kill -> that card's status becomes "killed". No note queued -- nothing for
                Gamma to answer, J just wants it gone.
      * test -> that card's status becomes "testing"; a pending note carries its
                proposed_shadow_test into the next model prompt as "J asked you to
                spec this test".
      * ask  -> no status change; a pending note carries J's free-text question,
                which the next brief must answer.
    A card_id absent from the board, or an unrecognized action string, is skipped
    (never raises) -- the row is still consumed by the caller either way, since a
    stale repost is not this function's problem to solve twice. Never mutates the
    caller's board/card objects in place."""
    board = [dict(c) if isinstance(c, dict) else c for c in board]
    by_id = {c.get("id"): c for c in board if isinstance(c, dict) and c.get("id")}
    pending_notes = []
    for row in inbox_rows:
        if not isinstance(row, dict):
            continue
        card_id = row.get("card_id")
        action = row.get("action")
        note = str(row.get("note") or "").strip()
        card = by_id.get(card_id)
        if action == "kill" and card is not None:
            card["status"] = "killed"
        elif action == "test" and card is not None:
            card["status"] = "testing"
            # GAMMA-STATION item 12 (2026-09-13): an inbox test row MAY carry an optional
            # `test_spec` ({type, params}) alongside the base {ts_et, card_id, action, note}
            # shape -- backward compatible (existing 4-field rows are untouched) and lets a
            # future dashboard "canned test type" picker (or a manual/ad-hoc verification run)
            # hand hypothesis_scorer.py a spec immediately instead of waiting on the
            # pending-notes round trip below. Shape is NOT validated here -- an invalid one is
            # a harmless, expected `spec_error` the next time hypothesis_scorer.score_card runs
            # (single source of truth for "what's a valid spec" stays hypothesis_scorer.py).
            got_spec = isinstance(row.get("test_spec"), dict)
            if got_spec:
                card["test_spec"] = row["test_spec"]
            if not got_spec and not isinstance(card.get("test_spec"), dict):
                pending_notes.append({
                    "card_id": card_id, "action": "test", "title": card.get("title", ""),
                    "proposed_shadow_test": card.get("proposed_shadow_test", ""), "note": note,
                })
        elif action == "ask":
            pending_notes.append({
                "card_id": card_id, "action": "ask",
                "title": (card or {}).get("title", ""), "note": note,
            })
        # else: unknown action, or kill/test naming a card_id not on the board --
        # silently skipped, still counted as consumed by the caller.
    return board, pending_notes


def render_pending_notes_text(notes: list) -> str:
    """Turns queued J-notes into a short block the model prompt can append
    verbatim. Empty input -> empty string (callers skip the section header
    entirely rather than print an empty one)."""
    if not notes:
        return ""
    lines = ["J's direct requests since the last fire (your brief must answer these):"]
    for n in notes:
        title = n.get("title") or n.get("card_id") or "?"
        if n.get("action") == "test":
            test = n.get("proposed_shadow_test") or "(no shadow test on file for this card)"
            line = f"  - J asked you to spec a test for '{title}': {test}"
        else:
            line = f"  - J asked (re: '{title}'): {n.get('note', '')}"
        if n.get("note") and n.get("action") == "test":
            line += f" -- J's note: {n['note']}"
        lines.append(line)
    return "\n".join(lines)


# ---- Closed idea loop (GAMMA-STATION item 12, 2026-09-13) -----------------------------------
# graveyard_titles() is a pure helper station_facts.py calls to build the FACTS block's
# "never re-propose" section. score_testing_cards() is a thin delegation to
# hypothesis_scorer.rescore_board() (lazy import -- hypothesis_scorer.py imports THIS module
# at its own top level for read_json_or_none/atomic_write_text/append_jsonl/load_board, so a
# top-level import here would be circular; station_loop.py calls this function by name per the
# approved plan, which is why the delegation lives here rather than station_loop.py importing
# hypothesis_scorer.py directly for it).

def graveyard_titles(board: list) -> list:
    """Titles of killed/refuted/supported cards -- station.md rule 3 ('never repeat a card')
    plus the closed-loop verdicts: once a card is settled, the model must never re-propose it
    under a new title. Cards still 'proposed'/'testing' are NOT graveyard (they're active,
    not dead) -- see gather_ideas_board_titles for those."""
    return [c.get("title") for c in board
            if isinstance(c, dict) and c.get("status") in ("killed", "refuted", "supported")
            and c.get("title")]


def score_testing_cards(board_path, *, autopsy_dir=None, verdicts_path=None,
                        settled_path=None, min_n: int = 10, now_et=None, dry_run: bool = False) -> dict:
    """Scores every 'testing'-status card on the board against real analysis/autopsies/*.jsonl
    rows -- deterministic, no LLM, safe to call on every Station fire (yielded or not). See
    hypothesis_scorer.rescore_board for the actual scoring contract; this is a thin, named
    delegation so station_loop.py's call site references the Station's own board module."""
    import hypothesis_scorer
    return hypothesis_scorer.rescore_board(
        board_path=board_path, autopsy_dir=autopsy_dir, verdicts_path=verdicts_path,
        settled_path=settled_path, min_n=min_n, now_et=now_et, dry_run=dry_run,
    )
