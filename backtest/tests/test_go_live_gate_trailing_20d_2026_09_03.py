"""Guard: go_live_gate.py trailing-20-trading-day disclosure view (queue.md
GO-LIVE-GATE-TRAILING-WINDOW-VIEW, filed 2026-08-29 Fable full review).

J's recency-over-aggregate doctrine (2026-07-31, "every armed gate needs a revalidation
clock") applied to the gate itself: criterion 1's STATISTICAL bootstrap scores each arm's
FULL trading-day history (29-42 day windows reaching back into the July regime). This adds
a SIBLING disclosure view -- same three-view bootstrap (as-traded / ex-best-day /
cost-adjusted, PF CI-lower 2.5%), scored per arm over only its most recent 20 trading days
-- so the September clean window is readable on its own merits without July ghosts. It
NEVER replaces or changes the aggregate view or any pass/fail criterion.

Covers exactly the 3 areas named in the task brief:
  (a) additive key exists per arm
  (b) with a synthetic ledger where the first 30 days are losers and the last 20 winners,
      aggregate and trailing disagree in the expected direction
  (c) the verdict function ignores the trailing view (mutation-proof: monkeypatch trailing
      to a crazy value, verdict unchanged)
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = str(REPO / "setup" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import go_live_gate as glg  # noqa: E402


def _row(arm, date, pnl, qty=3.0, exit_px=1.0, attribution="engine"):
    return {
        "arm": arm, "date": date, "pnl_dollars": pnl, "attribution": attribution,
        "qty": qty, "exit_px_avg": exit_px, "symbol": "SPY000000C00000000",
    }


def _dates(n, start="2026-07-01"):
    """n consecutive weekday-ish calendar dates (gate treats dates as opaque sortable
    strings -- weekends don't matter to the bootstrap, only ordering does)."""
    import datetime as dt
    d = dt.date.fromisoformat(start)
    out = []
    while len(out) < n:
        out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


# --------------------------------------------------------------------------------------- #
# (a) additive key exists per arm
# --------------------------------------------------------------------------------------- #
def test_trailing_20d_key_present_per_arm(monkeypatch):
    monkeypatch.setattr(glg, "ACTIVE_ARMS", ["arm-a", "arm-b"])
    dates = _dates(25)
    rows = []
    for i, d in enumerate(dates):
        pnl = 50.0 if i % 2 == 0 else -20.0
        rows.append(_row("arm-a", d, pnl))
    # arm-b has zero engine trades -- must degrade gracefully, not crash.
    block = glg.trailing_20d_view(rows)
    assert set(block.keys()) == {"label", "n_days_requested", "per_arm"}
    assert block["n_days_requested"] == glg.TRAILING_20D_SCORED_WINDOW_DAYS
    assert set(block["per_arm"].keys()) == {"arm-a", "arm-b"}

    a = block["per_arm"]["arm-a"]
    assert set(a.keys()) == {"n_days_requested", "n_days", "window_start", "window_end", "detail"}
    assert a["n_days"] == glg.TRAILING_20D_SCORED_WINDOW_DAYS  # 25 days present, capped to 20
    assert a["window_start"] == dates[-glg.TRAILING_20D_SCORED_WINDOW_DAYS]
    assert a["window_end"] == dates[-1]
    assert a["detail"]["insufficient_data"] is False

    b = block["per_arm"]["arm-b"]
    assert b["n_days"] == 0
    assert b["window_start"] is None and b["window_end"] is None
    assert b["detail"]["insufficient_data"] is True
    assert b["detail"]["pass"] is False


def test_trailing_20d_additive_in_build_report_disclosures(monkeypatch):
    """The key lives at report['disclosures']['trailing_20d'] -- additive, never replacing
    any pre-existing disclosure key."""
    monkeypatch.setattr(glg, "ACTIVE_ARMS", ["arm-a"])
    dates = _dates(22)
    rows = [_row("arm-a", d, 10.0 if i % 3 else -5.0) for i, d in enumerate(dates)]
    monkeypatch.setattr(glg, "load_ledger_rows", lambda: rows)
    monkeypatch.setattr(glg, "operational_criterion", lambda: {"guards": {}, "pass": True})
    monkeypatch.setattr(glg, "reconciliation_criterion", lambda rows: {"per_arm": {}, "pass": True})
    monkeypatch.setattr(glg, "prod_shadow_criterion", lambda engine_rows: {"pass": False, "status": "NOT_WIRED"})
    report = glg.build_report()
    assert "trailing_20d" in report["disclosures"]
    # pre-existing disclosure keys still present -- additive, not a replacement
    assert {"frozen_config_window", "effective_evidence", "plan_reachability"} <= set(report["disclosures"].keys())
    assert "arm-a" in report["disclosures"]["trailing_20d"]["per_arm"]


# --------------------------------------------------------------------------------------- #
# (b) aggregate vs trailing disagree in the expected direction
# --------------------------------------------------------------------------------------- #
def test_aggregate_and_trailing_disagree_when_recent_history_diverges(monkeypatch):
    """First 30 days are heavy losers (drags the full-history aggregate below the CI-lower
    bar), last 20 days are strong winners (the September clean-window analogue). The
    trailing-20d view must read the recent, healthy window; the aggregate must still be
    dragged down by the losing history. This is the exact scenario the queue item names."""
    monkeypatch.setattr(glg, "ACTIVE_ARMS", ["arm-a"])
    all_dates = _dates(50, start="2026-07-01")
    losing_dates, winning_dates = all_dates[:30], all_dates[30:]

    rows = []
    for d in losing_dates:
        rows.append(_row("arm-a", d, -300.0))
    for i, d in enumerate(winning_dates):
        # 18 winning days + 2 losing days inside the trailing window itself, so the
        # trailing bootstrap has genuine variance (an all-one-sign window produces an
        # infinite/undefined PF that gets dropped from the CI, which would make this
        # comparison meaningless rather than a real disagreement).
        pnl = -30.0 if i in (5, 14) else 200.0
        rows.append(_row("arm-a", d, pnl))

    aggregate = glg.statistical_criterion(rows, "arm-a")
    trailing = glg.trailing_20d_view(rows)["per_arm"]["arm-a"]["detail"]

    assert aggregate["insufficient_data"] is False
    assert trailing["insufficient_data"] is False

    # Aggregate: full 50-day history, dominated by the 30 losing days -- point PF well
    # under 1 and the CI-lower bound must not clear the bar.
    assert aggregate["as_traded"]["pf_point"] < 1.0
    assert aggregate["pass"] is False

    # Trailing: only the last 20 (mostly-winning) days -- point PF comfortably above 1
    # and the CI-lower bound clears the bar.
    assert trailing["as_traded"]["pf_point"] > 1.0
    assert trailing["pass"] is True

    # The disagreement itself, stated explicitly (the point of this test).
    assert aggregate["pass"] != trailing["pass"]
    assert trailing["as_traded"]["ci_lower_2.5"] > aggregate["as_traded"]["ci_lower_2.5"]


# --------------------------------------------------------------------------------------- #
# (c) the verdict function ignores the trailing view (mutation-proof)
# --------------------------------------------------------------------------------------- #
def test_verdict_ignores_trailing_view_even_when_it_is_corrupted(monkeypatch):
    """RED-PROOF: force trailing_20d_view() to return an all-FAIL, malformed payload and
    confirm overall_verdict / criteria are byte-identical to a normal run. Proves the
    disclosure is read-only decoration, never an input to any pass/fail computation."""
    baseline = glg.build_report()

    def _corrupted(engine_rows):
        return {
            "label": "CORRUPTED FOR TEST",
            "n_days_requested": 20,
            "per_arm": {arm: {"n_days_requested": 20, "n_days": 0, "window_start": None,
                               "window_end": None,
                               "detail": {"insufficient_data": False, "pass": False,
                                          "as_traded": {"ci_lower_2.5": -999.0}}}
                        for arm in glg.ACTIVE_ARMS},
        }

    monkeypatch.setattr(glg, "trailing_20d_view", _corrupted)
    mutated = glg.build_report()

    assert mutated["overall_verdict"] == baseline["overall_verdict"]
    # Compare each criterion group's pass/fail verdict, not the full dict -- the
    # operational group's guard results legitimately carry a pytest wall-clock timing
    # string (summary_tail) that varies run-to-run and is irrelevant to this proof.
    for name in ("statistical", "operational", "reconciliation", "behavioural", "prod_shadow"):
        assert mutated["criteria"][name]["pass"] == baseline["criteria"][name]["pass"], name
    assert mutated["criteria"]["statistical"]["per_arm"] == baseline["criteria"]["statistical"]["per_arm"]
    assert mutated["criteria"]["prod_shadow"] == baseline["criteria"]["prod_shadow"]
    # the mutation DID land in the disclosure (proving the monkeypatch was live) --
    # so the verdict's stability above is a real proof, not a no-op.
    assert mutated["disclosures"]["trailing_20d"]["label"] == "CORRUPTED FOR TEST"
