"""
Scratch analysis script for G2 LEDGER TRUTH TABLE (ledger-binding-check).
READ-ONLY: automation/state/**, journal/**. No broker/network calls.

For every core tick since 2026-08-06 (and separately 2026-09-01..today) where the SAFE
core perception was gated (action starts with SKIP_) while BOLD's verdict read
ENTER_BULL/ENTER_BEAR, join against each fleet arm's own decisions.jsonl on core_tick_id
and record what that arm did. Mirror direction included (safe ENTER, bold gated).

Outputs a single JSON blob to stdout (redirected to a file by the caller).
"""
import json
import sys
from collections import Counter, defaultdict

REPO = "C:/Users/jackw/Desktop/42"

FLEET_ARMS = ["safe-3", "risky-1", "risky-3"]
ENTER_VERDICTS = {"ENTER_BULL", "ENTER_BEAR"}
ENTER_ACTIONS = {"ENTER_BULL", "ENTER_BEAR", "PLACED"}

WINDOWS = {
    "since_2026-08-06": "2026-08-06",
    "since_2026-09-01": "2026-09-01",
}


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def load_core_by_tick(min_date):
    """core_tick_id -> {'safe': rec, 'bold': rec}, restricted to ts_et >= min_date."""
    by_tick = {}
    for rec in load_jsonl(f"{REPO}/automation/state/core-decisions.jsonl"):
        ts = rec.get("ts_et", "")
        if ts < min_date:
            continue
        ct = rec.get("core_tick_id")
        if ct is None:
            continue
        acct = rec.get("account")
        if acct not in ("safe", "bold"):
            continue
        by_tick.setdefault(ct, {})[acct] = rec
    return by_tick


def load_fleet_by_tick(arm):
    """core_tick_id -> list of rows (usually 1) for one fleet arm."""
    by_tick = defaultdict(list)
    for rec in load_jsonl(f"{REPO}/automation/state/fleet/{arm}/decisions.jsonl"):
        ct = rec.get("core_tick_id")
        if ct is None:
            continue
        by_tick[ct].append(rec)
    return by_tick


def fleet_row_is_entry(row):
    action = row.get("action")
    return action in ENTER_ACTIONS


def classify_safe_gate(safe_rec):
    """Return the gate label for a gated safe row: the SKIP_* action verbatim."""
    action = safe_rec.get("action")
    if isinstance(action, str) and action.startswith("SKIP_"):
        return action
    return None


def build_table(core_by_tick, fleet_by_tick_all, direction):
    """
    direction = 'safe_gated_bold_enter'  -> Table A
    direction = 'bold_gated_safe_enter'  -> Table B (mirror)
    """
    gate_ticks = defaultdict(list)  # gate_label -> [core_tick_id, ...]
    for ct, accts in core_by_tick.items():
        safe_rec = accts.get("safe")
        bold_rec = accts.get("bold")
        if safe_rec is None or bold_rec is None:
            continue

        if direction == "safe_gated_bold_enter":
            gated_rec, other_rec = safe_rec, bold_rec
        else:
            gated_rec, other_rec = bold_rec, safe_rec

        gated_action = gated_rec.get("action")
        if not (isinstance(gated_action, str) and gated_action.startswith("SKIP_")):
            continue
        other_verdict = other_rec.get("verdict")
        if other_verdict not in ENTER_VERDICTS:
            continue

        gate_ticks[gated_action].append(ct)

    # Now build gate x arm table
    table = {}
    for gate, ticks in gate_ticks.items():
        n_ticks = len(ticks)
        arm_stats = {}
        for arm in FLEET_ARMS:
            fleet_by_tick = fleet_by_tick_all[arm]
            n_logged = 0
            n_entries = 0
            entry_tick_ids = []
            for ct in ticks:
                rows = fleet_by_tick.get(ct)
                if not rows:
                    continue  # absent from arm ledger -> no-entry (per instructions)
                n_logged += 1
                if any(fleet_row_is_entry(r) for r in rows):
                    n_entries += 1
                    entry_tick_ids.append(ct)
            share = (n_entries / n_ticks) if n_ticks else None
            arm_stats[arm] = {
                "n_ticks": n_ticks,
                "n_logged_in_arm_ledger": n_logged,
                "n_absent_from_arm_ledger": n_ticks - n_logged,
                "n_fleet_entries": n_entries,
                "share_of_ticks": share,
                "underpowered": n_ticks < 10,
                "sample_entry_core_tick_ids": entry_tick_ids[:5],
            }
        table[gate] = {
            "n_ticks": n_ticks,
            "sample_core_tick_ids": ticks[:5],
            "arms": arm_stats,
        }
    return table


def any_gate_ticks(core_by_tick, direction):
    ticks = []
    for ct, accts in core_by_tick.items():
        safe_rec = accts.get("safe")
        bold_rec = accts.get("bold")
        if safe_rec is None or bold_rec is None:
            continue
        if direction == "safe_gated_bold_enter":
            gated_rec, other_rec = safe_rec, bold_rec
        else:
            gated_rec, other_rec = bold_rec, safe_rec
        gated_action = gated_rec.get("action")
        if not (isinstance(gated_action, str) and gated_action.startswith("SKIP_")):
            continue
        if other_rec.get("verdict") not in ENTER_VERDICTS:
            continue
        ticks.append((ct, gated_action))
    return ticks


def aggregate_any_gate(core_by_tick, fleet_by_tick_all, direction, exclude_date=None):
    ticks = any_gate_ticks(core_by_tick, direction)
    if exclude_date:
        ticks = [t for t in ticks if t[0][:10] != exclude_date]
    n_ticks = len(ticks)
    by_date = Counter(ct[:10] for ct, _ in ticks)
    result = {
        "n_ticks": n_ticks,
        "n_distinct_dates": len(by_date),
        "top_dates": by_date.most_common(5),
        "top3_concentration_share": (
            sum(c for _, c in by_date.most_common(3)) / n_ticks if n_ticks else None
        ),
        "arms": {},
    }
    for arm in FLEET_ARMS:
        fleet_by_tick = fleet_by_tick_all[arm]
        n_logged = 0
        n_entries = 0
        for ct, _ in ticks:
            rows = fleet_by_tick.get(ct)
            if not rows:
                continue
            n_logged += 1
            if any(fleet_row_is_entry(r) for r in rows):
                n_entries += 1
        result["arms"][arm] = {
            "n_ticks": n_ticks,
            "n_logged": n_logged,
            "n_entries": n_entries,
            "share_of_all_ticks": (n_entries / n_ticks) if n_ticks else None,
            "share_of_logged_ticks": (n_entries / n_logged) if n_logged else None,
        }
    return result


def symmetric_gate_check(core_by_tick, gate_names):
    out = {}
    for gate in gate_names:
        both = 0
        either = 0
        for ct, accts in core_by_tick.items():
            s = accts.get("safe")
            b = accts.get("bold")
            if s is None or b is None:
                continue
            s_g = s.get("action") == gate
            b_g = b.get("action") == gate
            if s_g or b_g:
                either += 1
            if s_g and b_g:
                both += 1
        out[gate] = {"both_accounts_hit_it_together": both, "either_account_hit_it": either,
                      "symmetric": (both == either and either > 0)}
    return out


def main():
    out = {"windows": {}}
    for window_name, min_date in WINDOWS.items():
        core_by_tick = load_core_by_tick(min_date)
        fleet_by_tick_all = {arm: load_fleet_by_tick(arm) for arm in FLEET_ARMS}

        table_a = build_table(core_by_tick, fleet_by_tick_all, "safe_gated_bold_enter")
        table_b = build_table(core_by_tick, fleet_by_tick_all, "bold_gated_safe_enter")

        # overall counts for sanity
        n_total_ticks = len(core_by_tick)
        n_both = sum(1 for v in core_by_tick.values() if "safe" in v and "bold" in v)

        agg_a = aggregate_any_gate(core_by_tick, fleet_by_tick_all, "safe_gated_bold_enter")
        agg_b = aggregate_any_gate(core_by_tick, fleet_by_tick_all, "bold_gated_safe_enter")

        # drop-best-day robustness (drop the single most-populous date from each table)
        best_date_a = agg_a["top_dates"][0][0] if agg_a["top_dates"] else None
        best_date_b = agg_b["top_dates"][0][0] if agg_b["top_dates"] else None
        agg_a_dropbest = (
            aggregate_any_gate(core_by_tick, fleet_by_tick_all, "safe_gated_bold_enter",
                                exclude_date=best_date_a)
            if best_date_a else None
        )
        agg_b_dropbest = (
            aggregate_any_gate(core_by_tick, fleet_by_tick_all, "bold_gated_safe_enter",
                                exclude_date=best_date_b)
            if best_date_b else None
        )

        gate_names = set(table_a.keys()) | set(table_b.keys())
        symmetric = symmetric_gate_check(core_by_tick, gate_names)

        out["windows"][window_name] = {
            "min_date": min_date,
            "n_total_core_ticks_with_id": n_total_ticks,
            "n_ticks_both_accounts_present": n_both,
            "table_a_safe_gated_bold_enter": table_a,
            "table_b_bold_gated_safe_enter": table_b,
            "any_gate_aggregate_table_a": agg_a,
            "any_gate_aggregate_table_b": agg_b,
            "any_gate_aggregate_table_a_drop_best_day": agg_a_dropbest,
            "any_gate_aggregate_table_b_drop_best_day": agg_b_dropbest,
            "symmetric_gate_check": symmetric,
        }

    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
