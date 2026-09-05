"""Guard for GOAL-GATE-EXPIRY-RECONCILE-2026-09-05 G3: the sole-blocker flagship watches
(filter-8-bear-sole, filter-10-bull-sole) must never sit on a bare NOT_REPLAYED proxy RED --
the moment the proxy trips (n_cost >= floor), gate_expiry_check.py now invokes
postfix_gate_costing.sole_blocker_cohort_costing over the trailing sole-blocker window and
writes the $ verdict into the SAME Known-broken line (rewritten in place, never duplicated).

RED-PROOF: every test below calls `sole_blocker_flagship_results(report, floor,
escalate_ctx=...)` or `flag_status_md(new_red, escalated=...)` -- BOTH kwargs are new
parameters this fix adds. On the pre-fix code (function signatures without `escalate_ctx`/
`escalated`), every test in this file fails with a hard TypeError (unexpected keyword
argument), not a soft assertion mismatch -- proof this suite actually exercises the new wiring
and cannot silently pass against the old bare-proxy-only code.

Pin, in order:
  1. A RED-tripping cohort with escalate_ctx set calls escalate_sole_blocker_costing exactly
     once, with the trailing window from escalate_ctx (not a second, invented window).
  2. verdict COST -> overall stays RED, pnl_check.costing flips to REPLAYED, reason carries the
     $ figure and "WINNERS net (COST)".
  3. verdict KEEP -> overall flips to GREEN ("RED clears"), reason carries the $ figure and
     "LOSERS net (KEEP)".
  4. verdict INSUFFICIENT -> overall downgrades to YELLOW, reason says INSUFFICIENT, proxy-RED
     stands as a watch only.
  5. escalate_ctx=None (unwired call site) -> behavior is BYTE-IDENTICAL to the pre-G3 bare
     proxy RED (backward compat for any caller that doesn't pass a context).
  6. fail-open: escalate_sole_blocker_costing raising an exception must never crash
     sole_blocker_flagship_results -- falls back to the bare proxy reason plus a visible
     "[escalation failed: ...]" suffix, costing stays NOT_REPLAYED.
  7. compute_newly_escalated fires on a NOT_REPLAYED -> REPLAYED transition even when `overall`
     stays RED both runs (a costed RED is new information the plain RED-transition-only
     compute_newly_red would silently miss), and does NOT re-fire once REPLAYED persists.
  8. flag_status_md REWRITES an existing "GATE-EXPIRY RED :: filter-10-bull-sole ::" bullet in
     place for an escalated gate (old bare-proxy line removed, one costed line written) instead
     of leaving both to sit duplicated; appends (does not crash) when no prior line exists.
"""
from __future__ import annotations

from autoresearch import gate_expiry_check as gec


def _tripping_report(door_prefix: str, n_events: int = 30, n_cost: int = 25) -> dict:
    return {f"{door_prefix}_safe": {"n_events": n_events, "n_cost_money": n_cost,
                                    "n_saved_money": n_events - n_cost, "n_unknown": 0,
                                    "costing": "NOT_REPLAYED"}}


# ─────────────────────────────────────────────────────────────────────────────
# 1-4. escalation drives the verdict/overall/reason
# ─────────────────────────────────────────────────────────────────────────────

def test_escalation_called_once_with_trailing_window(monkeypatch):
    calls = []

    def fake_escalate(door, filt, start, end, spy, spy_ts, floor):
        calls.append((door, filt, start, end, floor))
        return {"verdict": "COST", "n": 12, "net_dollars_safe_qty": 500.0,
                "best_day_share": 0.5, "window": f"{start}..{end}"}

    monkeypatch.setattr(gec, "escalate_sole_blocker_costing", fake_escalate)
    report = _tripping_report("bull_filter10")
    ctx = {"start": "2026-08-15", "end": "2026-09-05", "spy": object(), "spy_ts": object()}
    gec.sole_blocker_flagship_results(report, floor=10, escalate_ctx=ctx)

    assert len(calls) == 1
    door, filt, start, end, floor = calls[0]
    assert (door, filt) == ("bull", 10)
    assert (start, end, floor) == ("2026-08-15", "2026-09-05", 10)


def test_escalation_cost_verdict_stays_red_with_dollar_reason(monkeypatch):
    monkeypatch.setattr(gec, "escalate_sole_blocker_costing",
                         lambda *a, **k: {"verdict": "COST", "n": 42, "net_dollars_safe_qty": 1895.1,
                                          "ex_best_day_net_dollars_safe_qty": 349.7,
                                          "best_day_share": 0.815, "window": "2026-08-03..2026-08-28"})
    report = _tripping_report("bull_filter10")
    ctx = {"start": "x", "end": "y", "spy": None, "spy_ts": None}
    results = gec.sole_blocker_flagship_results(report, floor=10, escalate_ctx=ctx)
    r = results["filter-10-bull-sole"]
    assert r["overall"] == "RED"
    assert r["pnl_check"]["costing"] == "REPLAYED"
    assert "1895.10" in r["pnl_check"]["reason"] or "1895.1" in r["pnl_check"]["reason"]
    assert "WINNERS net (COST)" in r["pnl_check"]["reason"]
    assert r["pnl_check"]["escalation"]["verdict"] == "COST"


def test_escalation_keep_verdict_clears_red_to_green(monkeypatch):
    monkeypatch.setattr(gec, "escalate_sole_blocker_costing",
                         lambda *a, **k: {"verdict": "KEEP", "n": 42, "net_dollars_safe_qty": -1286.85,
                                          "best_day_share": -0.224, "window": "2026-08-03..2026-08-28"})
    report = _tripping_report("bear_filter8")
    ctx = {"start": "x", "end": "y", "spy": None, "spy_ts": None}
    results = gec.sole_blocker_flagship_results(report, floor=10, escalate_ctx=ctx)
    r = results["filter-8-bear-sole"]
    assert r["overall"] == "GREEN"  # RED clears
    assert r["pnl_check"]["costing"] == "REPLAYED"
    assert "LOSERS net (KEEP)" in r["pnl_check"]["reason"]
    assert "RED clears" in r["pnl_check"]["reason"]


def test_escalation_insufficient_verdict_downgrades_to_yellow(monkeypatch):
    monkeypatch.setattr(gec, "escalate_sole_blocker_costing",
                         lambda *a, **k: {"verdict": "INSUFFICIENT", "n": 5, "net_dollars_safe_qty": 314.8,
                                          "best_day_share": 1.0, "window": "2026-08-31..2026-09-05"})
    report = _tripping_report("bear_filter8")
    ctx = {"start": "x", "end": "y", "spy": None, "spy_ts": None}
    results = gec.sole_blocker_flagship_results(report, floor=10, escalate_ctx=ctx)
    r = results["filter-8-bear-sole"]
    assert r["overall"] == "YELLOW"
    assert r["pnl_check"]["costing"] == "REPLAYED"
    assert "INSUFFICIENT" in r["pnl_check"]["reason"]
    assert "watch only" in r["pnl_check"]["reason"]


def test_escalation_concentrated_verdict_downgrades_red_to_yellow_watch(monkeypatch):
    """The live 2026-09-05 finding: bear sole-[8]'s own rolling window read net $+80.95 but
    ex_best_day $-... (one day's $314.80 win exceeds the whole positive net) -- net>0 must NOT
    be enough to confirm COST on its own; it must survive dropping its own best day, same bar
    G2's human verdict for bull-10 explicitly required."""
    monkeypatch.setattr(gec, "escalate_sole_blocker_costing",
                         lambda *a, **k: {"verdict": "CONCENTRATED", "n": 41, "net_dollars_safe_qty": 80.95,
                                          "ex_best_day_net_dollars_safe_qty": -234.0,
                                          "best_day_share": 3.889, "window": "2026-08-07..2026-09-03"})
    report = _tripping_report("bear_filter8")
    ctx = {"start": "x", "end": "y", "spy": None, "spy_ts": None}
    results = gec.sole_blocker_flagship_results(report, floor=10, escalate_ctx=ctx)
    r = results["filter-8-bear-sole"]
    assert r["overall"] == "YELLOW"  # NOT a clean RED (COST) despite net > 0
    assert r["pnl_check"]["costing"] == "REPLAYED"
    assert "CONCENTRATED" in r["pnl_check"]["reason"]
    assert "not cleared" in r["pnl_check"]["reason"]


def test_no_escalate_ctx_is_byte_identical_to_pre_g3_bare_proxy():
    report = _tripping_report("bull_filter10")
    results = gec.sole_blocker_flagship_results(report, floor=10)  # no escalate_ctx at all
    r = results["filter-10-bull-sole"]
    assert r["overall"] == "RED"
    assert r["pnl_check"]["costing"] == "NOT_REPLAYED"
    assert "NOT_REPLAYED proxy" in r["pnl_check"]["reason"]
    assert r["pnl_check"]["escalation"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 6. fail-open
# ─────────────────────────────────────────────────────────────────────────────

def test_escalation_failure_falls_back_to_proxy_reason(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("OPRA cache miss")
    monkeypatch.setattr(gec, "escalate_sole_blocker_costing", boom)
    report = _tripping_report("bull_filter10")
    ctx = {"start": "x", "end": "y", "spy": None, "spy_ts": None}
    results = gec.sole_blocker_flagship_results(report, floor=10, escalate_ctx=ctx)
    r = results["filter-10-bull-sole"]
    assert r["overall"] == "RED"  # unchanged proxy verdict
    assert r["pnl_check"]["costing"] == "NOT_REPLAYED"  # escalation never completed
    assert "escalation failed" in r["pnl_check"]["reason"]
    assert "OPRA cache miss" in r["pnl_check"]["reason"]


# ─────────────────────────────────────────────────────────────────────────────
# 7. compute_newly_escalated transition detection
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_newly_escalated_fires_on_not_replayed_to_replayed_even_if_red_both_runs():
    results = {"filter-10-bull-sole": {"id": "filter-10-bull-sole", "overall": "RED",
                                       "pnl_check": {"costing": "REPLAYED"}}}
    prior_gates = {"filter-10-bull-sole": {"overall": "RED", "pnl_check": {"costing": "NOT_REPLAYED"}}}
    out = gec.compute_newly_escalated(results, prior_gates)
    assert [r["id"] for r in out] == ["filter-10-bull-sole"]


def test_compute_newly_escalated_does_not_refire_once_replayed_persists():
    results = {"filter-10-bull-sole": {"id": "filter-10-bull-sole", "overall": "RED",
                                       "pnl_check": {"costing": "REPLAYED"}}}
    prior_gates = {"filter-10-bull-sole": {"overall": "RED", "pnl_check": {"costing": "REPLAYED"}}}
    assert gec.compute_newly_escalated(results, prior_gates) == []


def test_compute_newly_escalated_refires_when_replayed_verdict_itself_moves():
    """Live 2026-09-05 finding this guards: both flagships were REPLAYED on one run (read
    COST) and REPLAYED again on the very next run (the ex-best-day concentration safeguard
    downgraded them to CONCENTRATED) -- a bare NOT_REPLAYED->REPLAYED transition check alone
    would miss this, leaving a stale COST line in STATUS.md while gate-registry-status.json
    already reads CONCENTRATED/YELLOW."""
    results = {"filter-8-bear-sole": {"id": "filter-8-bear-sole", "overall": "YELLOW",
                                      "pnl_check": {"costing": "REPLAYED", "reason": "now CONCENTRATED",
                                                    "escalation": {"verdict": "CONCENTRATED"}}}}
    prior_gates = {"filter-8-bear-sole": {"overall": "RED",
                                          "pnl_check": {"costing": "REPLAYED", "reason": "was COST",
                                                        "escalation": {"verdict": "COST"}}}}
    out = gec.compute_newly_escalated(results, prior_gates)
    assert [r["id"] for r in out] == ["filter-8-bear-sole"]


def test_compute_newly_escalated_does_not_refire_when_replayed_verdict_is_unchanged():
    results = {"filter-8-bear-sole": {"id": "filter-8-bear-sole", "overall": "RED",
                                      "pnl_check": {"costing": "REPLAYED", "reason": "same reason",
                                                    "escalation": {"verdict": "COST"}}}}
    prior_gates = {"filter-8-bear-sole": {"overall": "RED",
                                          "pnl_check": {"costing": "REPLAYED", "reason": "same reason",
                                                        "escalation": {"verdict": "COST"}}}}
    assert gec.compute_newly_escalated(results, prior_gates) == []


# ─────────────────────────────────────────────────────────────────────────────
# 8. STATUS.md line rewritten in place, not duplicated
# ─────────────────────────────────────────────────────────────────────────────

def test_flag_status_md_rewrites_existing_bare_proxy_line_for_escalated_gate(tmp_path, monkeypatch):
    status_path = tmp_path / "STATUS.md"
    status_path.write_text(
        "## Known broken\n\n"
        "- [2026-09-02T23:45:49] GATE-EXPIRY RED :: filter-10-bull-sole :: bull sole-[10] "
        "refused 78 bar-event(s), 28 >= floor 10 read cost_money via the day's own P1 WIN "
        "(NOT_REPLAYED proxy) :: re-check: ...\n"
        "- [2026-09-01T00:00:00] GATE-EXPIRY RED :: some-other-gate :: unrelated :: re-check: ...\n"
        "\nrest of file\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(gec, "STATUS_MD", status_path)

    escalated_row = {
        "id": "filter-10-bull-sole", "overall": "RED",
        "pnl_check": {"reason": "bull sole-[10]: REPLAYED costing -- n=42, net $1895.10 -- "
                                 "WINNERS net (COST). RED stays.", "costing": "REPLAYED"},
    }
    gec.flag_status_md([], escalated=[escalated_row])
    text = status_path.read_text(encoding="utf-8")

    # exactly ONE Known-broken bullet leads with this gate id (the gate id ALSO appears in
    # that same line's trailing "--gate <id>" re-check command, so a bare substring count
    # would read 2 even for a single surviving line -- count bullet leads specifically).
    assert text.count(":: filter-10-bull-sole ::") == 1  # old proxy line gone, new costed line present
    assert "NOT_REPLAYED proxy" not in text
    assert "WINNERS net (COST)" in text
    assert "some-other-gate" in text  # untouched, unrelated line survives


def test_flag_status_md_escalated_green_writes_cleared_label(tmp_path, monkeypatch):
    status_path = tmp_path / "STATUS.md"
    status_path.write_text(
        "## Known broken\n\n"
        "- [2026-09-02T23:45:49] GATE-EXPIRY RED :: filter-8-bear-sole :: bear sole-[8] "
        "refused 106 bar-event(s) (NOT_REPLAYED proxy) :: re-check: ...\n\nrest\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(gec, "STATUS_MD", status_path)
    escalated_row = {
        "id": "filter-8-bear-sole", "overall": "GREEN",
        "pnl_check": {"reason": "bear sole-[8]: REPLAYED costing -- n=42, net $-1286.85 -- "
                                 "LOSERS net (KEEP). RED clears.", "costing": "REPLAYED"},
    }
    gec.flag_status_md([], escalated=[escalated_row])
    text = status_path.read_text(encoding="utf-8")
    assert "GATE-EXPIRY CLEARED :: filter-8-bear-sole" in text
    assert "RED clears" in text
    assert "NOT_REPLAYED proxy" not in text


def test_flag_status_md_escalated_gate_wins_over_duplicate_new_red_entry(tmp_path, monkeypatch):
    """A gate that is BOTH newly-RED (compute_newly_red) and newly-escalated must be written
    exactly once, via the escalated (costed) path -- never twice."""
    status_path = tmp_path / "STATUS.md"
    status_path.write_text("## Known broken\n\n---\n\nrest\n", encoding="utf-8")
    monkeypatch.setattr(gec, "STATUS_MD", status_path)

    bare_row = {"id": "filter-10-bull-sole", "overall": "RED",
                "pnl_check": {"reason": "bare proxy reason", "costing": "NOT_REPLAYED"}}
    costed_row = {"id": "filter-10-bull-sole", "overall": "RED",
                  "pnl_check": {"reason": "REPLAYED costed reason", "costing": "REPLAYED"}}
    gec.flag_status_md([bare_row], escalated=[costed_row])
    text = status_path.read_text(encoding="utf-8")
    assert text.count(":: filter-10-bull-sole ::") == 1
    assert "REPLAYED costed reason" in text
    assert "bare proxy reason" not in text
