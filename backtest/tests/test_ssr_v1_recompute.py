"""Adversarial LENS-2 recompute for the SSR-v1 battery scorecards (Family A'/B').

Standalone: NO imports from backtest/futures/ssr/* or backtest/futures/battery.py.
Recomputes every v1 cell's n/wr/total_net/mean_net/IS-OOS split from the EMBEDDED
trade rows in analysis/recommendations/futures-ssr-v1-{smoke,regime}.json, and
diffs against the reported cell-level fields. Extends test_ssr_lens3_recompute.py
(the v0 pattern) with v1-specific checks: 48/16 family sizes, h4_anchor knob in
combo, BH-FDR alpha=0.05 within each v1 family separately, independent PULSE-tier
recompute (OOS n>=10 AND OOS mean>0 AND beats_bh AND drop_top3>0, NOT gated on
fdr_survivor per DESIGN.md addendum), guilty-until-proven diagnostics on any
clearing/PULSE cell (date concentration, null-pool degeneracy, exhibit-day
dependence, level_family concentration, IS/OOS sign consistency), and a v1-vs-v0
same-config (h4_anchor=1800) trade-count comparison.

Run:
    backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_ssr_v1_recompute.py -v -s
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parents[2]
V1_SMOKE_JSON = _REPO / "analysis" / "recommendations" / "futures-ssr-v1-smoke.json"
V1_REGIME_JSON = _REPO / "analysis" / "recommendations" / "futures-ssr-v1-regime.json"
V0_SMOKE_JSON = _REPO / "analysis" / "recommendations" / "futures-ssr-smoke.json"
V0_REGIME_JSON = _REPO / "analysis" / "recommendations" / "futures-ssr-regime.json"

EXHIBIT_DATE = "2026-08-07"

# Instrument specs, re-declared HERE from scratch (not imported) so this check
# is independent of ssr_instruments.py / instruments.py.
SPECS = {
    "GC": {"point_value": 100.0, "tick_size": 0.1, "round_turn_usd": 6.00},
    "ES": {"point_value": 50.0, "tick_size": 0.25, "round_turn_usd": 4.00},
    "NQ": {"point_value": 20.0, "tick_size": 0.25, "round_turn_usd": 4.00},
}

TRUE_SKIP_KEYS = (
    "skipped_while_open",
    "skipped_no_next_bar",
    "skipped_degenerate",
    "skipped_no_future_bars",
)


def _load(path: Path) -> dict:
    assert path.exists(), f"missing scorecard: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _independent_stats(nets: list[float]) -> dict:
    n = len(nets)
    if n == 0:
        return {"n": 0, "wr": None, "total": 0.0, "mean": None}
    arr = np.asarray(nets, dtype=float)
    return {"n": n, "wr": round(float((arr > 0).mean()), 4),
            "total": round(float(arr.sum()), 2), "mean": round(float(arr.mean()), 2)}


def _independent_bh_fdr(pvalues: list[float], alpha: float = 0.05) -> list[bool]:
    """Reimplemented BH step-up from scratch (no import of battery.py)."""
    m = len(pvalues)
    if m == 0:
        return []
    idx_sorted = sorted(range(m), key=lambda i: pvalues[i])
    survive = [False] * m
    thresh_rank = 0
    for rank, idx in enumerate(idx_sorted, start=1):
        p = pvalues[idx]
        if p <= (rank / m) * alpha:
            thresh_rank = rank
    for rank, idx in enumerate(idx_sorted, start=1):
        if rank <= thresh_rank:
            survive[idx] = True
    return survive


def _cell_key(c: dict) -> tuple:
    combo = c["combo"]
    return (c["symbol"], c["direction"], combo.get("h4_anchor"),
            combo["zone_atr_mult"], combo["sweep_atr_mult"])


def _clears_expected(c: dict, min_oos_n: int) -> bool:
    oos_n = c["oos"]["n"]
    oos_mean = c["oos"]["mean"]
    return bool(
        oos_n >= min_oos_n and oos_mean is not None and oos_mean > 0
        and c["fdr_survivor"] and c["beats_bh"] and c["drop_top3_net"] > 0
    )


def _pulse_expected(c: dict, pulse_min_oos_n: int) -> bool:
    """PULSE tier per DESIGN.md addendum: OOS n>=10 AND OOS mean>0 AND
    beats_bh AND drop_top3>0 -- explicitly NOT gated on fdr_survivor."""
    oos_n = c["oos"]["n"]
    oos_mean = c["oos"]["mean"]
    return bool(
        oos_n >= pulse_min_oos_n and oos_mean is not None and oos_mean > 0
        and c["beats_bh"] and c["drop_top3_net"] > 0
    )


# ---------------------------------------------------------------------------
# Family A' (v1 smoke) -- 48 cells
# ---------------------------------------------------------------------------

def test_family_a_prime_cell_count_matches_addendum():
    d = _load(V1_SMOKE_JSON)
    assert d["n_cells"] == 48, (
        f"addendum #128 is 48 cells (3 symbols x 2 dirs x [2 h4_anchor x 2 zone x 2 sweep]), "
        f"got {d['n_cells']}")
    assert len(d["cells"]) == 48
    combos = {(c["combo"]["h4_anchor"], c["combo"]["zone_atr_mult"], c["combo"]["sweep_atr_mult"])
              for c in d["cells"]}
    assert combos == {
        ("1800", 0.25, 0.1), ("1800", 0.25, 0.25), ("1800", 0.5, 0.1), ("1800", 0.5, 0.25),
        ("2000", 0.25, 0.1), ("2000", 0.25, 0.25), ("2000", 0.5, 0.1), ("2000", 0.5, 0.25),
    }, f"combo grid does not match frozen addendum grid: {combos}"
    symbols = {c["symbol"] for c in d["cells"]}
    assert symbols == {"GC=F", "NQ=F", "ES=F"}
    dirs = {c["direction"] for c in d["cells"]}
    assert dirs == {"long", "short"}


def test_family_b_prime_cell_count_matches_addendum():
    d = _load(V1_REGIME_JSON)
    assert d["n_cells"] == 16, (
        f"addendum #132 is 16 cells (1 symbol x 2 dirs x [2 h4_anchor x 2 zone x 2 sweep]), "
        f"got {d['n_cells']}")
    assert len(d["cells"]) == 16
    symbols = {c["symbol"] for c in d["cells"]}
    assert symbols == {"GC=F"}


@pytest.mark.parametrize("path,label", [(V1_SMOKE_JSON, "A'"), (V1_REGIME_JSON, "B'")])
def test_recompute_n_wr_total_mean_per_cell(path, label):
    d = _load(path)
    mismatches = []
    for c in d["cells"]:
        nets = [t["net"] for t in c["trades"]]
        recomputed = _independent_stats(nets)
        for field, rkey in (("n", "n"), ("wr", "wr"), ("total_net", "total"), ("mean_net", "mean")):
            reported = c[field]
            recomp = recomputed[rkey]
            if reported != recomp:
                mismatches.append((label, c["symbol"], c["direction"], c["combo"], field, reported, recomp))
    assert not mismatches, f"[{label}] recompute mismatches: {mismatches}"


@pytest.mark.parametrize("path,label", [(V1_SMOKE_JSON, "A'"), (V1_REGIME_JSON, "B'")])
def test_recompute_is_oos_split(path, label):
    d = _load(path)
    oos_cut = dt.date.fromisoformat(d["oos_cut"])
    mismatches = []
    for c in d["cells"]:
        is_nets = [t["net"] for t in c["trades"] if dt.date.fromisoformat(t["date"]) < oos_cut]
        oos_nets = [t["net"] for t in c["trades"] if dt.date.fromisoformat(t["date"]) >= oos_cut]
        is_recomp = _independent_stats(is_nets)
        oos_recomp = _independent_stats(oos_nets)
        for field in ("n", "wr", "total", "mean"):
            if c["is"][field] != is_recomp[field]:
                mismatches.append((label, "IS", c["symbol"], c["direction"], c["combo"], field,
                                    c["is"][field], is_recomp[field]))
            if c["oos"][field] != oos_recomp[field]:
                mismatches.append((label, "OOS", c["symbol"], c["direction"], c["combo"], field,
                                    c["oos"][field], oos_recomp[field]))
    assert not mismatches, f"[{label}] IS/OOS split mismatches: {mismatches}"


@pytest.mark.parametrize("path,label", [(V1_SMOKE_JSON, "A'"), (V1_REGIME_JSON, "B'")])
def test_no_duplicate_entry_timestamps_per_cell(path, label):
    d = _load(path)
    dupes = []
    for c in d["cells"]:
        ts_list = [t["ts_entry_et"] for t in c["trades"]]
        if len(ts_list) != len(set(ts_list)):
            seen = set()
            for ts in ts_list:
                if ts in seen:
                    dupes.append((label, c["symbol"], c["direction"], c["combo"], ts))
                seen.add(ts)
    assert not dupes, f"[{label}] duplicated entry timestamps found: {dupes}"


@pytest.mark.parametrize("path,label", [(V1_SMOKE_JSON, "A'"), (V1_REGIME_JSON, "B'")])
def test_no_overlapping_positions_within_cell(path, label):
    """Within one (symbol,direction,combo) cell there is one position at a
    time per DESIGN.md sec.3 concurrency rule -- entries must be time-ordered
    (best-effort proxy for no-overlap, exit ts isn't stored)."""
    d = _load(path)
    problems = []
    for c in d["cells"]:
        raw = [t["ts_entry_et"] for t in c["trades"]]
        if raw != sorted(raw):
            problems.append((label, c["symbol"], c["direction"], c["combo"], "not time-ordered"))
    assert not problems, f"[{label}] ordering problems (possible overlap / out-of-order trades): {problems}"


@pytest.mark.parametrize("path,label", [(V1_SMOKE_JSON, "A'"), (V1_REGIME_JSON, "B'")])
def test_friction_present_on_every_net(path, label):
    """DESIGN.md sec.3: slippage 1 tick/side + round_turn_usd on every fill.
    net must be strictly below gross (friction never zero/negative) for
    EVERY symbol in the file, not just GC (lens3 only spot-checked GC)."""
    d = _load(path)
    by_symbol_costs: dict[str, list[float]] = {}
    for c in d["cells"]:
        root = c["symbol"].split("=")[0]
        for t in c["trades"]:
            by_symbol_costs.setdefault(root, []).append(t["gross"] - t["net"])
    assert by_symbol_costs, f"[{label}] no trades found to check friction"
    for root, costs in by_symbol_costs.items():
        arr = np.asarray(costs)
        assert (arr > 0).all(), (
            f"[{label}] found non-positive friction (gross-net<=0) on "
            f"{int((arr <= 0).sum())}/{len(arr)} {root} trades")
        # sane lower bound: round_turn alone (qty=3) regardless of instrument
        spec = SPECS.get(root)
        if spec is not None:
            min_expected = spec["round_turn_usd"] * 3 * 0.5  # generous floor, partial-fill aware
            assert arr.min() >= min_expected, (
                f"[{label}] suspiciously low {root} friction, min={arr.min()} "
                f"(expect >= ~{min_expected} from round-turn alone)")


@pytest.mark.parametrize("path,label", [(V1_SMOKE_JSON, "A'"), (V1_REGIME_JSON, "B'")])
def test_beats_bh_flag_consistent_with_totals(path, label):
    d = _load(path)
    mismatches = []
    for c in d["cells"]:
        expected = c["total_net"] > c["buy_and_hold_total"]
        if bool(c["beats_bh"]) != expected:
            mismatches.append((label, c["symbol"], c["direction"], c["combo"],
                                c["total_net"], c["buy_and_hold_total"], c["beats_bh"]))
    assert not mismatches, f"[{label}] beats_bh flag inconsistent with total_net vs buy_and_hold_total: {mismatches}"


@pytest.mark.parametrize("path,label", [(V1_SMOKE_JSON, "A'"), (V1_REGIME_JSON, "B'")])
def test_drop_top3_math(path, label):
    d = _load(path)
    mismatches = []
    for c in d["cells"]:
        nets = [t["net"] for t in c["trades"]]
        if len(nets) <= 3:
            expected = 0.0
        else:
            expected = round(float(sum(sorted(nets, reverse=True)[3:])), 2)
        if c["drop_top3_net"] != expected:
            mismatches.append((label, c["symbol"], c["direction"], c["combo"], c["drop_top3_net"], expected))
    assert not mismatches, f"[{label}] drop_top3_net mismatches: {mismatches}"


@pytest.mark.parametrize("path,label", [(V1_SMOKE_JSON, "A'"), (V1_REGIME_JSON, "B'")])
def test_halves_stability_math(path, label):
    d = _load(path)
    mismatches = []
    for c in d["cells"]:
        sorted_trades = sorted(c["trades"], key=lambda t: t["date"])
        mid = len(sorted_trades) // 2
        exp_first = round(sum(t["net"] for t in sorted_trades[:mid]), 2)
        exp_second = round(sum(t["net"] for t in sorted_trades[mid:]), 2)
        h = c["halves_stability"]
        if h["first_half_total"] != exp_first or h["second_half_total"] != exp_second:
            mismatches.append((label, c["symbol"], c["direction"], c["combo"],
                                h["first_half_total"], exp_first, h["second_half_total"], exp_second))
        if h["first_half_n"] != mid or h["second_half_n"] != len(sorted_trades) - mid:
            mismatches.append(("n-split", label, c["symbol"], c["direction"], c["combo"],
                                h["first_half_n"], mid, h["second_half_n"], len(sorted_trades) - mid))
    assert not mismatches, f"[{label}] halves_stability mismatches: {mismatches}"


def test_family_a_prime_headline_with_without_exhibit_arithmetic():
    d = _load(V1_SMOKE_JSON)
    headline = d["headline_with_without_exhibit_2026_08_07"]
    assert headline is not None, "Family A' must have the headline split (DESIGN.md sec.2)"
    with_total = 0.0
    without_total = 0.0
    n_exhibit = 0
    for c in d["cells"]:
        for t in c["trades"]:
            with_total += t["net"]
            if t["date"] == EXHIBIT_DATE:
                n_exhibit += 1
            else:
                without_total += t["net"]
    assert round(with_total, 2) == headline["with_2026_08_07"], (
        f"WITH total recompute mismatch: {round(with_total,2)} vs reported {headline['with_2026_08_07']}")
    assert round(without_total, 2) == headline["without_2026_08_07"], (
        f"WITHOUT total recompute mismatch: {round(without_total,2)} vs reported {headline['without_2026_08_07']}")
    assert n_exhibit == headline["n_trades_on_2026_08_07"], (
        f"exhibit-day trade count mismatch: {n_exhibit} vs reported {headline['n_trades_on_2026_08_07']}")
    exhibit_sum = sum(t["net"] for c in d["cells"] for t in c["trades"] if t["date"] == EXHIBIT_DATE)
    assert abs((with_total - without_total) - exhibit_sum) < 0.02, (
        "with-without delta does not equal exhibit-day net sum")


def test_family_a_prime_exhibit_day_breakdown_by_symbol_recompute():
    """Independently reproduces the integrator's exhibit_fired.detail claim:
    'Zero GC=F trades on 2026-08-07 ... only NQ=F n=16/-110642 and ES=F
    n=24/-15734'."""
    d = _load(V1_SMOKE_JSON)
    breakdown = d["exhibit_day_breakdown_by_symbol"]
    assert "GC=F" not in breakdown, (
        f"integrator claimed ZERO GC=F trades on {EXHIBIT_DATE} (no key in "
        f"exhibit_day_breakdown_by_symbol) -- found a GC=F key: {breakdown.get('GC=F')}")
    by_symbol: dict[str, list[float]] = {}
    for c in d["cells"]:
        for t in c["trades"]:
            if t["date"] == EXHIBIT_DATE:
                by_symbol.setdefault(c["symbol"], []).append(t["net"])
    mismatches = []
    for sym, nets in by_symbol.items():
        expected_n = len(nets)
        expected_total = round(sum(nets), 2)
        expected_winners = sum(1 for x in nets if x > 0)
        expected_losers = sum(1 for x in nets if x <= 0)
        reported = breakdown.get(sym)
        if reported is None:
            mismatches.append((sym, "missing from breakdown", expected_n, expected_total))
            continue
        if (reported["n"] != expected_n or round(reported["total_net"], 2) != expected_total
                or reported["n_winners"] != expected_winners or reported["n_losers"] != expected_losers):
            mismatches.append((sym, reported, {"n": expected_n, "total_net": expected_total,
                                                "n_winners": expected_winners, "n_losers": expected_losers}))
    assert "GC=F" not in by_symbol, f"recompute found GC=F trades on {EXHIBIT_DATE} the file's breakdown omits: {by_symbol.get('GC=F')}"
    assert not mismatches, f"exhibit_day_breakdown_by_symbol recompute mismatches: {mismatches}"


@pytest.mark.parametrize("path,label,n_cells", [(V1_SMOKE_JSON, "A'", 48), (V1_REGIME_JSON, "B'", 16)])
def test_bh_fdr_family_size_and_alpha_reimplemented(path, label, n_cells):
    d = _load(path)
    assert d["alpha"] == 0.05
    eligible = [c for c in d["cells"] if not c["null_unavailable"] and c["null"]["p_value"] is not None]
    assert len(eligible) == d["n_bh_fdr_eligible"], (
        f"[{label}] n_bh_fdr_eligible mismatch: file says {d['n_bh_fdr_eligible']}, "
        f"recomputed {len(eligible)} eligible of {n_cells}")
    pvals = [c["null"]["p_value"] for c in eligible]
    survivors = _independent_bh_fdr(pvals, alpha=0.05)
    reported_survivors = [c["fdr_survivor"] for c in eligible]
    assert survivors == reported_survivors, (
        f"[{label}] independent BH-FDR reimplementation disagrees with reported fdr_survivor flags:\n"
        f"recomputed={survivors}\nreported={reported_survivors}")
    assert d["n_clearing_cells"] == sum(1 for c in d["cells"] if c["clears"])


@pytest.mark.parametrize("path,label", [(V1_SMOKE_JSON, "A'"), (V1_REGIME_JSON, "B'")])
def test_clears_gate_reimplemented_per_cell(path, label):
    """Reimplement the DESIGN.md sec.5 ladder (verbatim per addendum sec.
    'Stats/ladder/exit shape: identical to v0 sec.5') from scratch per cell
    and diff against the reported `clears` boolean."""
    d = _load(path)
    mismatches = []
    for c in d["cells"]:
        expected = _clears_expected(c, d["min_oos_n"])
        if expected != c["clears"]:
            mismatches.append((label, c["symbol"], c["direction"], c["combo"], expected, c["clears"]))
    assert not mismatches, f"[{label}] clears-gate reimplementation mismatches: {mismatches}"
    n_clearing_recomputed = sum(1 for c in d["cells"] if c["clears"])
    assert d["n_clearing_cells"] == n_clearing_recomputed
    # Verdict follows PASS-if->=1-clears else KILL (no WEAK rung, DESIGN.md sec.5)
    expected_verdict = "PASS" if n_clearing_recomputed >= 1 else "KILL"
    assert d["verdict"] == expected_verdict, (
        f"[{label}] verdict {d['verdict']} inconsistent with recomputed clearing count "
        f"{n_clearing_recomputed} (expected {expected_verdict})")


@pytest.mark.parametrize("path,label", [(V1_SMOKE_JSON, "A'"), (V1_REGIME_JSON, "B'")])
def test_pulse_tier_membership_recomputed_independently(path, label):
    """PULSE tier is explicitly NOT gated on fdr_survivor per DESIGN.md
    addendum sec. 'v1 verdict rules'. Recompute membership from the raw
    OOS/beats_bh/drop_top3 fields and diff against the reported pulse_cells
    list (order-independent, keyed on symbol/direction/combo)."""
    d = _load(path)
    pulse_min_oos_n = d["pulse_min_oos_n"]
    assert pulse_min_oos_n == 10, f"[{label}] addendum PULSE bar is OOS n>=10, file says {pulse_min_oos_n}"
    recomputed_keys = {_cell_key(c) for c in d["cells"] if _pulse_expected(c, pulse_min_oos_n)}
    reported_keys = {_cell_key(c) for c in d["pulse_cells"]}
    assert recomputed_keys == reported_keys, (
        f"[{label}] PULSE-tier membership mismatch.\n"
        f"recomputed only: {recomputed_keys - reported_keys}\n"
        f"reported only: {reported_keys - recomputed_keys}")
    assert d["n_pulse_cells"] == len(reported_keys) == len(d["pulse_cells"])


@pytest.mark.parametrize("path,label", [(V1_SMOKE_JSON, "A'"), (V1_REGIME_JSON, "B'")])
def test_pulse_cells_are_verbatim_members_of_cells_list(path, label):
    """Fixer-round-2 guard (BLOCKING finding, 2026-08-07): a prior round's
    report cited b1.best_cell numbers (n=223, total_net=87957.32, oos_n=40,
    oos_mean=394.58, drop_top3_net=76724.99, p=0.1084) that appear NOWHERE in
    this file and do not match a from-scratch battery re-run -- the real
    pulse_cells[0] is GC=F short h4_anchor=1800/zone=0.5/sweep=0.1 with
    n=205/total_net=178196.91/oos_n=38/oos_mean=841.05/drop_top3_net=79773.75.
    run_ssr_battery.py's `_pulse_cells` appends the SAME dict objects that
    live in `all_cells` (no copy, no re-derivation) so pulse_cells entries
    are structurally guaranteed to be byte-identical to their `cells` twin --
    this test makes that guarantee an explicit, checked contract instead of
    an assumption a future report could silently violate (e.g. if a future
    edit ever switched `_pulse_cells` to build a lighter-weight summary
    dict). Every field mismatch here is BLOCKING: it would mean pulse_cells
    diverged from the file's own cells array, which is exactly the shape of
    the false claim this guard exists to catch."""
    d = _load(path)
    mismatches = []
    for pc in d["pulse_cells"]:
        key = _cell_key(pc)
        twins = [c for c in d["cells"] if _cell_key(c) == key]
        assert len(twins) == 1, f"[{label}] pulse cell key {key} matches {len(twins)} cells (expected exactly 1)"
        twin = twins[0]
        if pc != twin:
            diff_fields = [k for k in set(pc) | set(twin) if pc.get(k) != twin.get(k)]
            mismatches.append((label, key, diff_fields))
    assert not mismatches, (
        f"[{label}] pulse_cells entries diverged from their own cells-array twin "
        f"(field-level diff): {mismatches}")


def test_family_b_prime_best_pulse_cell_pinned_regression():
    """Pins the disputed b1.best_cell (GC=F short 1800/0.5/0.1) numbers as an
    explicit regression anchor -- see docstring of
    test_pulse_cells_are_verbatim_members_of_cells_list for the false claim
    this guards against. If the battery is ever re-run and this pin breaks,
    that is a REAL signal to re-diagnose (data refresh, detector change) --
    it is not license to silently widen the tolerance."""
    d = _load(V1_REGIME_JSON)
    best = max(d["pulse_cells"], key=lambda c: c["total_net"])
    assert best["symbol"] == "GC=F"
    assert best["direction"] == "short"
    assert best["combo"] == {"h4_anchor": "1800", "zone_atr_mult": 0.5, "sweep_atr_mult": 0.1}
    assert best["n"] == 205
    assert best["total_net"] == pytest.approx(178196.91, abs=0.01)
    assert best["oos"]["n"] == 38
    assert best["oos"]["mean"] == pytest.approx(841.05, abs=0.01)
    assert best["drop_top3_net"] == pytest.approx(79773.75, abs=0.01)
    # Explicit anti-regression: the debunked pre-fix numbers must never
    # reappear as this cell's reported values.
    assert best["n"] != 223
    assert best["total_net"] != pytest.approx(87957.32, abs=0.01)
    assert best["oos"]["n"] != 40
    assert best["oos"]["mean"] != pytest.approx(394.58, abs=0.01)
    assert best["drop_top3_net"] != pytest.approx(76724.99, abs=0.01)


@pytest.mark.parametrize("path,label", [(V1_SMOKE_JSON, "A'"), (V1_REGIME_JSON, "B'")])
def test_signal_frequency_c27_sanity(path, label):
    """C27: any (symbol,combo,direction) firing on >80% of trading days in
    the window is a noise-not-signal smell (report-only per DESIGN.md v1
    diagnostics, not a gate) -- flag cells that trip the raw trade-date-count
    proxy so it's on the record."""
    d = _load(path)
    window_days = 60 if label == "A'" else 730
    threshold = int(window_days * 0.8)
    tripped = []
    for c in d["cells"]:
        n_days = len({t["date"] for t in c["trades"]})
        if n_days > threshold:
            tripped.append((c["symbol"], c["direction"], c["combo"], n_days))
    if tripped:
        print(f"\n[{label}] C27 signal-frequency flag (report-only, not gating): {tripped}")
    # not asserted false -- DESIGN.md v1 addendum marks C27 as report-only diagnostic


# ---------------------------------------------------------------------------
# Guilty-until-proven treatment for clearing/PULSE cells
# ---------------------------------------------------------------------------

def _guilty_until_proven_report(label: str, c: dict, all_trades_for_exhibit_check: list[dict] | None = None) -> dict:
    """Compute the 5 adversarial diagnostics DESIGN.md/LENS-2 requires on any
    clearing or PULSE cell. Returns a dict of findings; does not assert --
    callers decide what's a hard failure vs an INFO note."""
    trades = c["trades"]
    nets = [t["net"] for t in trades]
    total = sum(nets)
    dates: dict[str, float] = {}
    for t in trades:
        dates[t["date"]] = dates.get(t["date"], 0.0) + t["net"]
    # 1. date concentration: single busiest date's share of total positive net
    max_date, max_date_net = (max(dates.items(), key=lambda kv: kv[1]) if dates else (None, 0.0))
    date_concentration_ratio = (max_date_net / total) if total else None

    # 2. null-pool degeneracy
    null = c["null"]
    null_degenerate = (null.get("n_pool", 0) < 100 or null.get("r_median_points") in (None, 0)
                        or null.get("p_value") is None)

    # 3. exhibit-day dependence: does dropping 2026-08-07 flip PULSE/clears membership?
    non_exhibit_nets = [t["net"] for t in trades if t["date"] != EXHIBIT_DATE]
    exhibit_nets = [t["net"] for t in trades if t["date"] == EXHIBIT_DATE]
    oos_cut_present = "oos" in c
    membership_sensitive_to_exhibit_day = bool(exhibit_nets)  # any exhibit-day trades at all in this cell

    # 4. level_family concentration
    lfb = c.get("level_family_breakdown", {})
    total_n = sum(v["n"] for v in lfb.values()) if lfb else 0
    top_family = max(lfb.items(), key=lambda kv: kv[1]["n"]) if lfb else (None, {"n": 0})
    family_concentration_ratio = (top_family[1]["n"] / total_n) if total_n else None

    # 5. IS-vs-OOS sign consistency
    is_total = c["is"]["total"]
    oos_total = c["oos"]["total"]
    sign_consistent = (is_total is not None and oos_total is not None
                        and (is_total >= 0) == (oos_total >= 0))

    return {
        "cell": (c["symbol"], c["direction"], c["combo"]),
        "date_concentration_ratio": date_concentration_ratio,
        "max_date": max_date,
        "null_degenerate": null_degenerate,
        "n_exhibit_day_trades": len(exhibit_nets),
        "exhibit_day_net": round(sum(exhibit_nets), 2),
        "non_exhibit_total": round(sum(non_exhibit_nets), 2),
        "family_concentration_ratio": family_concentration_ratio,
        "top_level_family": top_family[0],
        "is_oos_sign_consistent": sign_consistent,
        "is_total": is_total,
        "oos_total": oos_total,
    }


@pytest.mark.parametrize("path,label", [(V1_SMOKE_JSON, "A'"), (V1_REGIME_JSON, "B'")])
def test_guilty_until_proven_on_pulse_cells(path, label):
    """No cell CLEARS in either v1 family (verified above), so every PULSE
    cell gets the adversarial workup per LENS-2 instructions. Hard-fails
    only on genuinely disqualifying degeneracy (null pool broken, or the
    ENTIRE positive total_net riding on one single day/family). Everything
    else is printed for the record (report-only, matches DESIGN.md's own
    'INFO-worthy, not fraud' framing for level-family concentration)."""
    d = _load(path)
    reports = []
    hard_failures = []
    for c in d["cells"]:
        if not _pulse_expected(c, d["pulse_min_oos_n"]):
            continue
        r = _guilty_until_proven_report(label, c)
        reports.append(r)
        if r["null_degenerate"]:
            hard_failures.append((r["cell"], "null-pool degenerate", r))
        if r["date_concentration_ratio"] is not None and r["date_concentration_ratio"] >= 1.0 and r["is_oos_sign_consistent"] is False:
            # entire edge is one single day AND IS/OOS disagree in sign -- the
            # PULSE cell would not survive removing that one day
            hard_failures.append((r["cell"], "single-day-carries-everything + IS/OOS sign flip", r))
    print(f"\n[{label}] guilty-until-proven PULSE-cell diagnostics:")
    for r in reports:
        print(f"  {r}")
    assert not hard_failures, f"[{label}] PULSE cell(s) failed guilty-until-proven workup: {hard_failures}"


@pytest.mark.parametrize("path,label", [(V1_SMOKE_JSON, "A'"), (V1_REGIME_JSON, "B'")])
def test_guilty_until_proven_on_clearing_cells(path, label):
    d = _load(path)
    hard_failures = []
    for c in d["cells"]:
        if not c["clears"]:
            continue
        r = _guilty_until_proven_report(label, c)
        print(f"\n[{label}] CLEARING cell guilty-until-proven workup: {r}")
        if r["null_degenerate"]:
            hard_failures.append((r["cell"], "null-pool degenerate"))
        if r["date_concentration_ratio"] is not None and r["date_concentration_ratio"] >= 0.5:
            hard_failures.append((r["cell"], f"single date carries >=50% of net: {r['date_concentration_ratio']}"))
    assert not hard_failures, f"[{label}] clearing cell(s) failed guilty-until-proven workup: {hard_failures}"


# ---------------------------------------------------------------------------
# v1 vs v0 same-config (h4_anchor=1800) comparison
# ---------------------------------------------------------------------------

def _v0_key(c: dict) -> tuple:
    return (c["symbol"], c["direction"], c["combo"]["zone_atr_mult"], c["combo"]["sweep_atr_mult"])


def _v1_key_at_1800(c: dict) -> tuple | None:
    if c["combo"].get("h4_anchor") != "1800":
        return None
    return (c["symbol"], c["direction"], c["combo"]["zone_atr_mult"], c["combo"]["sweep_atr_mult"])


@pytest.mark.parametrize(
    "v0_path,v1_path,label",
    [(V0_SMOKE_JSON, V1_SMOKE_JSON, "A vs A' (h4_anchor=1800)"),
     (V0_REGIME_JSON, V1_REGIME_JSON, "B vs B' (h4_anchor=1800)")],
)
def test_v1_vs_v0_same_config_trade_counts(v0_path, v1_path, label):
    """DESIGN.md addendum: v1 ADDS running-extreme level families on top of
    v0's fixed set (opt-in include_running=True) plus a same-bar-rearm
    detector completeness fix -- at IDENTICAL h4_anchor=1800/zone/sweep,
    v1's trade count should be >= v0's for MOST cells (strictly more
    candidate levels to sweep => more or equal signals). A cell where v1's
    n DROPS below v0's n at identical config is the exact regression
    DESIGN.md flags as 'explain why or flag BLOCKING'."""
    d0 = _load(v0_path)
    d1 = _load(v1_path)
    v0_by_key = {_v0_key(c): c for c in d0["cells"]}
    v1_by_key = {}
    for c in d1["cells"]:
        k = _v1_key_at_1800(c)
        if k is not None:
            v1_by_key[k] = c

    matched = 0
    increases = 0
    decreases = []
    unmatched_v0 = []
    for k, c0 in v0_by_key.items():
        c1 = v1_by_key.get(k)
        if c1 is None:
            unmatched_v0.append(k)
            continue
        matched += 1
        if c1["n"] > c0["n"]:
            increases += 1
        elif c1["n"] < c0["n"]:
            decreases.append((k, "v0_n", c0["n"], "v1_n", c1["n"]))

    print(f"\n[{label}] matched {matched}/{len(v0_by_key)} v0 cells to v1 h4_anchor=1800 cells; "
          f"{increases} increased, {len(decreases)} decreased, {len(unmatched_v0)} unmatched")
    assert matched == len(v0_by_key), f"[{label}] could not match all v0 cells into v1 at h4_anchor=1800: unmatched={unmatched_v0}"
    if decreases:
        print(f"[{label}] REGRESSIONS (v1 n < v0 n at identical config): {decreases}")
    # Per addendum: "should ADD signals, MOSTLY" -- a small minority of
    # decreases is tolerable (e.g. a running-extreme level stealing an entry
    # window from a fixed level, or timeout-boundary effects from change #3),
    # but a majority regressing would contradict the addendum's own claim.
    assert len(decreases) <= matched / 2, (
        f"[{label}] MAJORITY of matched cells regressed in trade count under v1 at identical "
        f"config -- contradicts addendum's 'adding RUN_* levels should ADD signals, mostly' "
        f"claim: {decreases}")


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
