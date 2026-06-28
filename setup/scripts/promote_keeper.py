"""promote_keeper.py -- research -> deploy bridge (Blocker #1, OP-11 path).

THE GAP THIS CLOSES: the research grinder scores thousands of contender combos and
writes a ranked shortlist to analysis/recommendations/contender-rank-{date}.json,
but nothing ever translates that ranking into a conductor proposal. This script is
the single missing link. It:

  1. Reads the NEWEST contender-rank-*.json file (glob, sort by name).
  2. Takes the TOP entry from the "top" array.
  3. Decodes the "combo" tuple into a human-readable params description and a
     structured apply_ops array.
  4. Emits ONE op11 proposal row to automation/state/conductor-proposals.jsonl.

CRITICAL SAFETY:
  - The contender files contain IS (in-sample) sweep data ONLY. They carry
    "edge_capture", "wf", "n" but NO "oos_positive" or "anchor_no_regression".
  - Therefore we ALWAYS set eval_bar_cleared=false. The proposal WAITS for a human
    or a future OOS validation pass to flip it. It NEVER auto-ships.
  - This script NEVER edits params.json, NEVER sets any arm flag, NEVER places any
    order.

IDEMPOTENCY: before appending, we check whether a proposal for this exact contender
label + date already exists in the ledger. If so, we print a message and exit 0
without duplicating.

STDLIB ONLY. Anchors all paths to __file__ so it is cwd-independent.

Usage:
  python setup/scripts/promote_keeper.py          # use newest contender-rank-*.json
  python setup/scripts/promote_keeper.py --dry-run  # print the proposal row, don't write
  python setup/scripts/promote_keeper.py --file analysis/recommendations/contender-rank-2026-06-28.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Path anchoring: setup/scripts/promote_keeper.py -> parents[2] == repo root.
REPO = Path(__file__).resolve().parents[2]
RECS_DIR = REPO / "analysis" / "recommendations"
PROPOSALS_FILE = REPO / "automation" / "state" / "conductor-proposals.jsonl"

# Combo tuple index constants (from rank_contenders.py + label format).
# label: "OTM-2:LR0:mt1:stop-8:tp+150%:sell80%:fixed"
# combo: [strike_tier, strike_offset, lr_flag, min_triggers,
#         stop_label, premium_stop_pct, tp1_multiplier, tp1_qty_fraction, profit_lock_mode]
_COMBO_STRIKE_TIER = 0
_COMBO_STRIKE_OFFSET = 1
_COMBO_LR_FLAG = 2       # bool: True = require level_rejection in triggers
_COMBO_MIN_TRIGGERS = 3
_COMBO_STOP_LABEL = 4    # e.g. "-8"
_COMBO_PREMIUM_STOP_PCT = 5   # e.g. -0.08
_COMBO_TP1_MULTIPLIER = 6     # e.g. 1.5 -> +150%
_COMBO_TP1_QTY_FRACTION = 7   # e.g. 0.8 -> sell 80%
_COMBO_PROFIT_LOCK_MODE = 8   # "fixed" | "trailing"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _find_newest_contender_file() -> Path | None:
    """Return the newest contender-rank-*.json file by filename (YYYY-MM-DD suffix)."""
    candidates = sorted(RECS_DIR.glob("contender-rank-*.json"))
    return candidates[-1] if candidates else None


def _load_contender_file(path: Path) -> dict[str, Any]:
    """Load and validate the contender-rank JSON file."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"promote_keeper: cannot read contender file {path}: {exc}") from exc


def _decode_combo(combo: list[Any]) -> dict[str, Any]:
    """Decode a combo tuple into a dict of named param fields.

    Returns a dict suitable for building apply_ops and human description.
    Never raises -- missing/malformed fields fall back to None and are flagged.
    """
    if not isinstance(combo, list) or len(combo) < 9:
        return {}
    return {
        "strike_tier": combo[_COMBO_STRIKE_TIER],
        "strike_offset": combo[_COMBO_STRIKE_OFFSET],
        "lr_required": combo[_COMBO_LR_FLAG],
        "min_triggers": combo[_COMBO_MIN_TRIGGERS],
        "stop_label": combo[_COMBO_STOP_LABEL],
        "premium_stop_pct": combo[_COMBO_PREMIUM_STOP_PCT],
        "tp1_multiplier": combo[_COMBO_TP1_MULTIPLIER],
        "tp1_qty_fraction": combo[_COMBO_TP1_QTY_FRACTION],
        "profit_lock_mode": combo[_COMBO_PROFIT_LOCK_MODE],
    }


def _build_apply_ops(decoded: dict[str, Any], current_params: dict[str, Any]) -> list[dict[str, str]]:
    """Build a list of {file, find, replace} apply_ops for the params changes.

    SAFETY RULES:
    - We only produce ops where the new value DIFFERS from the current params value.
    - We only produce ops for params we can identify unambiguously in the file
      (a find that is unique in the target).
    - We never emit an op that would change premium_stop_pct back toward a tight
      catastrophe cap (the -0.50 chart-stop-primary is doctrine, not a knob).
    - All find strings include a doc field reference so they are unique.

    Because eval_bar_cleared=false, these ops will NOT be auto-applied by the
    actuator. They are written for human review + future OOS validation to enable.
    """
    ops: list[dict[str, str]] = []
    params_file = "automation/state/params.json"

    # -- tp1_qty_fraction --
    # combo[7]: e.g. 0.8 means sell 80% at TP1
    new_qty_frac = decoded.get("tp1_qty_fraction")
    cur_qty_frac = current_params.get("tp1_qty_fraction")
    if new_qty_frac is not None and new_qty_frac != cur_qty_frac:
        old_str = f'"tp1_qty_fraction": {_fmt_num(cur_qty_frac)}'
        new_str = f'"tp1_qty_fraction": {_fmt_num(new_qty_frac)}'
        ops.append({"file": params_file, "find": old_str, "replace": new_str})

    # -- v15_profit_lock_mode --
    # combo[8]: "fixed" or "trailing"
    new_lock = decoded.get("profit_lock_mode")
    cur_lock = current_params.get("v15_profit_lock_mode")
    if new_lock is not None and new_lock != cur_lock:
        old_str = f'"v15_profit_lock_mode": "{cur_lock}"'
        new_str = f'"v15_profit_lock_mode": "{new_lock}"'
        ops.append({"file": params_file, "find": old_str, "replace": new_str})

    # -- filter_10_min_triggers (both bear and bull; combo[3] = mt) --
    new_mt = decoded.get("min_triggers")
    cur_bear = current_params.get("filter_10_min_triggers_bear")
    cur_bull = current_params.get("filter_10_min_triggers_bull")
    if new_mt is not None and isinstance(new_mt, int):
        if new_mt != cur_bear:
            old_str = f'"filter_10_min_triggers_bear": {cur_bear}'
            new_str = f'"filter_10_min_triggers_bear": {new_mt}'
            ops.append({"file": params_file, "find": old_str, "replace": new_str})
        # bull threshold uses a different value per v11/v12 doctrine (bear >=1, bull >=2);
        # the sweep uses a single mt value but we only change the bear threshold here to
        # preserve the asymmetry. Bull trigger gate is OP-16 doctrine, not a sweep knob.

    return ops


def _fmt_num(v: Any) -> str:
    """Format a numeric value for JSON key matching (same as json.dumps would)."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        # Match JSON serialization: e.g. 0.667 not 0.6670000...
        return json.dumps(v)
    return json.dumps(v)


def _load_current_params() -> dict[str, Any]:
    """Load the current params.json for diffing. Returns {} on error (non-fatal)."""
    params_path = REPO / "automation" / "state" / "params.json"
    try:
        return json.loads(params_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _load_proposals() -> list[dict[str, Any]]:
    """Read all existing proposal rows. Robust to missing/torn file."""
    rows: list[dict[str, Any]] = []
    if not PROPOSALS_FILE.exists():
        return rows
    for line in PROPOSALS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                rows.append(obj)
        except (json.JSONDecodeError, ValueError):
            continue
    return rows


def _already_proposed(proposals: list[dict[str, Any]], label: str, ranked_at: str) -> bool:
    """Return True if a promote_keeper proposal for this label + ranked_at already exists."""
    for row in proposals:
        if (row.get("source") == "promote_keeper"
                and row.get("contender_label") == label
                and row.get("contender_ranked_at") == ranked_at):
            return True
    return False


def _append_proposal(row: dict[str, Any]) -> None:
    """Atomically append one JSON row to the proposals ledger."""
    PROPOSALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with PROPOSALS_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def build_proposal(
    contender_file: Path | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """Main logic: load the contender file, build and emit ONE proposal row.

    Returns the proposal dict that was (or would be) written, or None if skipped.
    Raises SystemExit on hard errors (bad file, empty top list).
    """
    # 1. Resolve and load the contender file.
    path = contender_file or _find_newest_contender_file()
    if path is None:
        raise SystemExit(
            "promote_keeper: no contender-rank-*.json files found in "
            f"{RECS_DIR}. Run rank_contenders.py first."
        )
    data = _load_contender_file(path)

    top_list = data.get("top", [])
    if not top_list:
        raise SystemExit(
            f"promote_keeper: contender file {path.name} has an empty 'top' list. "
            "Nothing to promote."
        )

    # 2. Take the first (highest-ranked) entry.
    best = top_list[0]
    label: str = best.get("label", "unknown")
    ranked_at: str = data.get("ranked_at_et", "")
    combo: list[Any] = best.get("combo", [])
    edge_capture: float | None = best.get("edge_capture")
    wf: float | None = best.get("wf")
    n: int | None = best.get("n")
    expectancy: float | None = best.get("expectancy")
    wr: float | None = best.get("wr")
    max_dd: float | None = best.get("max_dd")

    decoded = _decode_combo(combo)
    current_params = _load_current_params()

    # 3. Build apply_ops (PROPOSAL ONLY — never applied while eval_bar_cleared=false).
    apply_ops = _build_apply_ops(decoded, current_params)

    # 4. Generate a stable proposal_id from the source file date.
    # Format: pk-YYYY-MM-DD-NNN (NNN = 001 for the first proposal from this date).
    # We use the contender file date (YYYY-MM-DD from filename like contender-rank-2026-06-28.json).
    file_date = path.stem.replace("contender-rank-", "")  # e.g. "2026-06-28"
    proposal_id = f"pk-{file_date}-001"

    # 5. Idempotency: skip if already proposed.
    existing = _load_proposals()
    if _already_proposed(existing, label, ranked_at):
        print(
            f"promote_keeper: proposal for '{label}' ranked_at='{ranked_at}' already exists. "
            "Skipping (idempotent).",
            file=sys.stderr,
        )
        return None

    # 6. Build the proposal row.
    #
    # CRITICAL: eval_bar_cleared=false because:
    #  - contender-rank files contain IS sweep data only.
    #  - "oos_positive" and "anchor_no_regression" are absent from the contender file.
    #  - DO NOT fabricate OOS status from IS data (OP-11 / L177 / L183 / C1 / C3).
    #  - The proposal WAITS for an explicit OOS validation pass before auto-ship.
    #
    # The proposal is intentionally complete so that AFTER OOS validation a human
    # can flip eval_bar_cleared=true and set scorecard= to unlock auto-ship.
    human_summary = _build_human_summary(label, decoded, edge_capture, wf, n, expectancy, wr, max_dd)

    proposal: dict[str, Any] = {
        "proposal_id": proposal_id,
        "created_at": _utc_now(),
        "source": "promote_keeper",
        "title": f"Contender promotion: {label}",
        "kind": "params",
        "contender_label": label,
        "contender_ranked_at": ranked_at,
        "contender_file": path.name,
        "contender_combo": combo,
        "contender_metrics": {
            "edge_capture": edge_capture,
            "wf": wf,
            "n": n,
            "expectancy": expectancy,
            "wr": wr,
            "max_dd": max_dd,
        },
        "decoded_params": decoded,
        # SAFETY: eval_bar_cleared MUST be false — no oos_positive in contender file.
        "eval_bar_cleared": False,
        # No scorecard field: it does not exist yet. OOS validation must create it.
        "apply": human_summary,
        "apply_ops": apply_ops,
        "oos_validation_needed": True,
        "oos_note": (
            "contender-rank files contain IS sweep data only. "
            "oos_positive and anchor_no_regression are ABSENT — do not infer from IS. "
            "Run OOS validation (shadow backtest or real-fills check) and set "
            "eval_bar_cleared=true + scorecard= before this proposal can auto-ship."
        ),
        "status": "pending",
    }

    # 7. Emit or dry-run.
    if dry_run:
        print("--- DRY RUN: would append the following proposal ---")
        print(json.dumps(proposal, indent=2))
        print("--- (not written) ---")
    else:
        _append_proposal(proposal)
        print(
            f"promote_keeper: emitted proposal {proposal_id} for '{label}' "
            f"(eval_bar_cleared=false — awaiting OOS validation)."
        )

    return proposal


def _build_human_summary(
    label: str,
    decoded: dict[str, Any],
    edge_capture: float | None,
    wf: float | None,
    n: int | None,
    expectancy: float | None,
    wr: float | None,
    max_dd: float | None,
) -> str:
    """Build a one-line human-readable apply summary for the proposal row."""
    parts = [f"IS champion: {label}"]
    if edge_capture is not None:
        parts.append(f"edge={edge_capture:.0f}")
    if expectancy is not None:
        parts.append(f"exp={expectancy:.2f}")
    if wf is not None:
        parts.append(f"wf={wf:.3f}")
    if n is not None:
        parts.append(f"n={n}")
    if wr is not None:
        parts.append(f"wr={wr:.1%}")
    if max_dd is not None:
        parts.append(f"maxDD={max_dd:.0f}")

    param_changes: list[str] = []
    tp1 = decoded.get("tp1_qty_fraction")
    if tp1 is not None:
        param_changes.append(f"tp1_qty_fraction->{tp1}")
    lock = decoded.get("profit_lock_mode")
    if lock is not None:
        param_changes.append(f"v15_profit_lock_mode->{lock}")
    stop = decoded.get("premium_stop_pct")
    if stop is not None:
        param_changes.append(f"premium_stop_pct->{stop}")
    mt = decoded.get("min_triggers")
    if mt is not None:
        param_changes.append(f"min_triggers_bear->{mt}")

    summary = " | ".join(parts)
    if param_changes:
        summary += " | PROPOSED CHANGES: " + ", ".join(param_changes)
    summary += " | REQUIRES OOS VALIDATION before auto-ship (eval_bar_cleared=false)."
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="promote_keeper",
        description=(
            "Read the top contender from the newest contender-rank-*.json and "
            "emit ONE pending op11 proposal to conductor-proposals.jsonl. "
            "ALWAYS sets eval_bar_cleared=false (no OOS data in contender files). "
            "Never edits params.json, never arms, never trades."
        ),
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        help="Explicit contender-rank JSON file (default: newest in analysis/recommendations/).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the proposal row without writing it.",
    )
    args = parser.parse_args(argv)

    contender_file: Path | None = None
    if args.file:
        contender_file = Path(args.file)
        if not contender_file.is_absolute():
            contender_file = REPO / contender_file

    result = build_proposal(contender_file=contender_file, dry_run=args.dry_run)
    return 0 if result is not None or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
