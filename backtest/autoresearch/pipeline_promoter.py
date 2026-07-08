"""Pipeline promoter — route a passing stage5 scorecard to a CONSUMABLE output.

Called by kitchen_daemon._run_pipeline_scorecard() after a terminal scorecard script
(e.g. shotgun_scalper_stage5) completes successfully.

Gates (must ALL pass for auto-promote):
  1. walk_forward.passed        — OOS test window net-positive
  2. wf_ratio >= 0.70           — per-quarter-normalized test/train expectancy
                                  (C4: normalize OOS — raw pnl ratio is structurally
                                  unpassable when train=4Q vs test=2Q)
  3. sub_window_stable          — all test quarters net-positive
  4. anchor_no_regression       — directional_score >= 2 on J's winner days
  5. concentration_ok           — top_5_pct <= 0.50 (OP-20 gate)

OUTPUT CONTRACT (rewritten 2026-07-01 — PIPELINE-AUDIT-2026-07-01 break #2):
  The old contract wrote '{watcher}_stage5_cleared' into params.json — a key read
  by NOTHING (a dead key that faked progress). The new contract routes to the
  engine's ONLY real consumable surface:

  * Watcher HAS a dispatcher entry in setup_dispatch.py's roster:
      -> write its ACTUAL enable-flag key (from the roster, e.g.
         'gap_and_go_enabled': true) into params.json — WATCH mode only.
         extra_setup_exec_armed is NEVER written here (exec-arming stays a
         validation-gated step; live money needs J per OP-0 #1).
  * Watcher has NO dispatcher entry:
      -> write NO params key at all. Instead append a structured
         'WIRE-DETECTOR-<watcher>' proposal row to conductor-proposals.jsonl
         with the scorecard evidence, so the wiring gap becomes a visible,
         pickable work item instead of a silently-dead key.

Schema note (fix for audit break (d)): stage5 writes {best: {...walk_forward,
concentration, dir_score...}, all_results: [...]}; the legacy promoter expected
top-level walk_forward + best_keeper and therefore ALWAYS failed closed on fresh
scorecards. _check_gates now reads BOTH shapes.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
RECS_DIR = REPO / "analysis" / "recommendations"
STATE_DIR = REPO / "automation" / "state"
DISCORD_OUTBOX = STATE_DIR / "discord-outbox.jsonl"
PARAMS_PATH = STATE_DIR / "params.json"
AGG_PARAMS_PATH = STATE_DIR / "aggressive" / "params.json"
PROPOSALS_PATH = STATE_DIR / "conductor-proposals.jsonl"
DISPATCH_SOURCE = REPO / "setup" / "scripts" / "setup_dispatch.py"

sys.path.insert(0, str(REPO / "backtest" / "lib"))
from armability import account_armability_disclosure  # noqa: E402  shared armability primitive (G7)

# OP-22 auto-ship gates
WF_RATIO_GATE = 0.70          # per-quarter-normalized test/train ratio
MIN_DIRECTIONAL_SCORE = 2     # J's anchor days: fire in the right direction
MAX_CONCENTRATION = 0.50      # top-5 days <= 50% of total P&L
MAX_SCORECARD_AGE_DAYS = 7    # freshness guard: refuse stale scorecards (the
                              # dash-variant fallback once resolved to a 2026-05-16
                              # file — promoting on 6-week-old research is a bug)

# Matches roster rows in SetupDispatcher.run(), e.g.:
#   ("vwap_continuation", "j_vwap_cont_enabled", self._dispatch_vwap_continuation),
_ROSTER_ROW_RE = re.compile(
    r"""\(\s*"(?P<setup>\w+)"\s*,\s*"(?P<flag>\w+)"\s*,\s*self\._dispatch_\w+\s*\)"""
)


def _et_now() -> datetime:
    now_utc = datetime.now(timezone.utc)
    y = now_utc.year
    march = datetime(y, 3, 1, tzinfo=timezone.utc)
    dst_start = (march + timedelta(days=(6 - march.weekday()) % 7 + 7)).replace(hour=7)
    nov = datetime(y, 11, 1, tzinfo=timezone.utc)
    dst_end = (nov + timedelta(days=(6 - nov.weekday()) % 7)).replace(hour=6)
    offset = -4 if (dst_start <= now_utc < dst_end) else -5
    return (now_utc + timedelta(hours=offset)).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Dispatcher roster — the engine's real strategy menu
# ---------------------------------------------------------------------------

def read_dispatcher_roster(source_path: Optional[Path] = None) -> dict[str, str]:
    """Parse setup_dispatch.py and return {setup_name: enable_flag_key}.

    The roster is the tuple list inside SetupDispatcher.run(). We parse the
    SOURCE (not import) so this works without the backtest venv and always
    reflects the live file — including entries added after this module loaded.

    Fail-CLOSED: unreadable/unparseable source returns {} → every watcher is
    treated as un-wired → proposal row, never a params write. Uncertainty must
    not write params keys.
    """
    p = source_path or DISPATCH_SOURCE
    try:
        src = p.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[pipeline_promoter] cannot read dispatcher source {p}: {exc}", file=sys.stderr)
        return {}
    return {m.group("setup"): m.group("flag") for m in _ROSTER_ROW_RE.finditer(src)}


# ---------------------------------------------------------------------------
# Scorecard reading + gates
# ---------------------------------------------------------------------------

def _scorecard_age_days(path: Path, scorecard: dict) -> float:
    """Age of a scorecard in days — generated_at field if parseable, else file mtime."""
    gen = scorecard.get("generated_at")
    if gen:
        try:
            gen_dt = datetime.fromisoformat(str(gen).replace("Z", "+00:00"))
            if gen_dt.tzinfo is None:
                gen_dt = gen_dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - gen_dt).total_seconds() / 86400.0
        except ValueError:
            pass
    try:
        return (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) / 86400.0
    except OSError:
        return float("inf")


def _read_scorecard(script_name: str, recs_dir: Optional[Path] = None) -> Optional[dict]:
    """Read the JSON scorecard produced by the stage5 script.

    Freshness guard (2026-07-01): refuse scorecards older than
    MAX_SCORECARD_AGE_DAYS. The dash-variant fallback below can resolve to a
    stale file from a long-dead run; auto-promoting on it would ship weeks-old
    research as if it were tonight's result.
    """
    rd = recs_dir or RECS_DIR
    candidates = [
        rd / f"{script_name}.json",
        rd / f"{script_name.replace('_stage5', '-stage5')}.json",
        rd / f"{script_name.replace('_', '-')}.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                scorecard = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            age_days = _scorecard_age_days(p, scorecard)
            if age_days > MAX_SCORECARD_AGE_DAYS:
                print(
                    f"[pipeline_promoter] REFUSED stale scorecard {p.name} "
                    f"(age={age_days:.1f}d > {MAX_SCORECARD_AGE_DAYS}d freshness gate)",
                    file=sys.stderr,
                )
                continue
            return scorecard
    return None


def _best_entry(scorecard: dict) -> dict:
    """Resolve the winning entry across scorecard schema generations.

    stage5 (fresh, 2026-07-01+) writes 'best'; legacy scorecards wrote
    'best_keeper' or 'winner'.
    """
    for key in ("best", "best_keeper", "winner"):
        v = scorecard.get(key)
        if isinstance(v, dict) and v:
            return v
    return {}


def _quarter_counts(best: dict) -> tuple[int, int]:
    """Derive (train_quarters, test_quarters) from best.quarter_pnl.

    stage5's walk-forward convention: test = quarters of the LAST calendar year
    present, train = everything before it (stage5.py: train=2025, test=2026).
    Returns (0, 0) when quarter_pnl is absent/underivable.
    """
    qpnl = best.get("quarter_pnl")
    if not isinstance(qpnl, dict) or not qpnl:
        return 0, 0
    years = sorted({str(q).split("-")[0] for q in qpnl})
    if len(years) < 2:
        return 0, 0
    test_year = years[-1]
    n_test = sum(1 for q in qpnl if str(q).startswith(test_year))
    n_train = len(qpnl) - n_test
    return n_train, n_test


def _check_gates(scorecard: dict) -> tuple[bool, dict]:
    """Return (gates_passed, details_dict).

    Reads BOTH scorecard shapes:
      - fresh stage5: best.walk_forward / best.concentration.top5_pct / best.dir_score
      - legacy:       top-level walk_forward + best_keeper{directional_score, top5_pct}
    """
    details: dict = {}
    best = _best_entry(scorecard)

    # Gate 1+2: walk-forward
    wf = scorecard.get("walk_forward") or best.get("walk_forward") or {}
    wf_passed = bool(wf.get("passed", False))
    train_pnl = float(wf.get("train_pnl", 0) or 0)
    test_pnl = float(wf.get("test_pnl", 0) or 0)
    wf_ratio = (test_pnl / train_pnl) if train_pnl > 0 else 0.0
    # C4 normalization: when the train/test windows are unequal (stage5 uses
    # train=4 quarters vs test=2), the raw pnl ratio can never clear 0.70 even
    # for a perfectly stable edge. Normalize per-quarter when derivable.
    n_train_q, n_test_q = _quarter_counts(best)
    if train_pnl > 0 and n_train_q > 0 and n_test_q > 0:
        wf_ratio = (test_pnl / n_test_q) / (train_pnl / n_train_q)
        details["wf_ratio_normalization"] = f"per-quarter (train={n_train_q}Q test={n_test_q}Q)"
    details["wf_passed"] = wf_passed
    details["wf_ratio"] = round(wf_ratio, 3)
    details["wf_ratio_gate"] = WF_RATIO_GATE

    # Gate 3: sub-window stability (all test quarters positive)
    test_pos_quarters = int(wf.get("test_positive_quarters", 0))
    total_test_quarters = int(wf.get("total_test_quarters", n_test_q or 2))
    sub_stable = test_pos_quarters == total_test_quarters and total_test_quarters > 0
    details["sub_window_stable"] = sub_stable
    details["test_positive_quarters"] = test_pos_quarters

    # Gate 4: anchor no-regression (directional_score from stage4 winners)
    dir_score = int(best.get("directional_score", best.get("dir_score", 0)) or 0)
    anchor_ok = dir_score >= MIN_DIRECTIONAL_SCORE
    details["anchor_no_regression"] = anchor_ok
    details["directional_score"] = dir_score

    # Gate 5: concentration (fresh: best.concentration.top5_pct; legacy: best.top5_pct)
    conc = best.get("concentration") if isinstance(best.get("concentration"), dict) else {}
    top5_raw = best.get("top5_pct", best.get("concentration_top5", conc.get("top5_pct", 1.0)))
    top5_pct = float(1.0 if top5_raw is None else top5_raw)
    conc_ok = top5_pct <= MAX_CONCENTRATION
    details["concentration_ok"] = conc_ok
    details["top5_pct"] = round(top5_pct, 3)

    passed = wf_passed and wf_ratio >= WF_RATIO_GATE and sub_stable and anchor_ok and conc_ok
    details["all_gates_passed"] = passed
    return passed, details


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

def _write_discord_ping(watcher_name: str, details: dict, scorecard: dict,
                        *, flag_key: Optional[str], outbox: Optional[Path] = None) -> None:
    best = _best_entry(scorecard)
    wide_pnl = best.get("wide_pnl", "?")
    exp = best.get("expectancy", best.get("expectancy_per_trade", best.get("wide_expectancy", "?")))
    if flag_key:
        action = (
            f"WATCH flag written: {flag_key}=true in params.json (WATCH_NOT_ARMED).\n"
            f"ARM to trade: add extra_setup_exec_armed['{watcher_name}']=true (needs validation + J for live)."
        )
    else:
        action = (
            f"NO dispatcher entry in setup_dispatch.py — no params key written.\n"
            f"Filed WIRE-DETECTOR-{watcher_name} proposal in conductor-proposals.jsonl instead."
        )
    msg = (
        f"PIPELINE PROMOTE: **{watcher_name}** cleared all 5 gates.\n"
        f"WF ratio={details['wf_ratio']:.2f} (gate={WF_RATIO_GATE}) | "
        f"OOS quarters={details['test_positive_quarters']} pos | "
        f"dir_score={details['directional_score']} | "
        f"top5={details['top5_pct']:.0%} | "
        f"wide_pnl=${wide_pnl} | exp/trade=${exp}\n"
        f"{action}\n"
        f"Scorecard: analysis/recommendations/promote_{watcher_name}.json"
    )
    event = {
        "ts": _et_now().isoformat(),
        "channel": "gamma-ops",
        "message": msg,
        "source": "pipeline_promoter",
    }
    try:
        with open(outbox or DISCORD_OUTBOX, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except OSError:
        pass


# --- G7 armability disclosure -------------------------------------------------------------
# Core account tiers for the per-cell armability disclosure. Equity is a DOCUMENTED tier
# default (params.json carries no equity field -- wire live equity via accounts_status for
# exactness); risk_frac is read live from params when present. Disclosure-only: it surfaces
# whether a promoted cell is affordable at the floor, and NEVER blocks a promotion (a swept /
# defaulted premium must not veto a real edge).
_ACCT_EQUITY_DEFAULT = {"Gamma-Safe-2": 2000.0, "Gamma-Bold-2": 1670.0}
_ACCT_RISK_DEFAULT = {"Gamma-Safe-2": 0.30, "Gamma-Bold-2": 0.50}
_ACCT_PARAMS = {"Gamma-Safe-2": PARAMS_PATH, "Gamma-Bold-2": AGG_PARAMS_PATH}
_RISK_KEYS = ("per_trade_risk_frac", "risk_frac", "per_trade_risk_pct", "risk_pct",
              "per_trade_risk")


def _read_risk_frac(params_path: Path, default: float) -> float:
    """Best-effort read of the per-trade risk fraction from a params file. Accepts a fraction
    (0.30) or a percent (30) -- normalizes >1 by /100. Falls back to the documented default;
    the disclosure must never crash the promoter."""
    try:
        params = json.loads(params_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    for k in _RISK_KEYS:
        v = params.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            return v / 100.0 if v > 1 else float(v)
    return default


def _promoter_accounts() -> dict:
    """{alias: {equity, risk_frac}} for the armability disclosure -- documented equity tiers,
    live risk_frac from params where available."""
    return {
        alias: {"equity": _ACCT_EQUITY_DEFAULT[alias],
                "risk_frac": _read_risk_frac(_ACCT_PARAMS[alias], _ACCT_RISK_DEFAULT[alias])}
        for alias in _ACCT_EQUITY_DEFAULT
    }


def _write_promote_scorecard(watcher_name: str, details: dict, scorecard: dict,
                             *, flag_key: Optional[str], recs_dir: Path) -> None:
    if flag_key:
        note = (
            f"Auto-promoted to WATCH_NOT_ARMED via '{flag_key}': true. "
            "Set extra_setup_exec_armed[watcher_name]=true in params.json to arm execution."
        )
    else:
        note = (
            "Gates passed but the watcher has NO dispatcher entry in setup_dispatch.py. "
            f"WIRE-DETECTOR-{watcher_name} proposal filed in conductor-proposals.jsonl; "
            "no params key written (a key nothing reads is not a promotion)."
        )
    out = {
        "promoted_at_et": _et_now().isoformat(),
        "watcher_name": watcher_name,
        "gates": details,
        "best": _best_entry(scorecard),
        "dispatcher_wired": flag_key is not None,
        "watch_flag_key": flag_key,
        "exec_armed": False,
        "note": note,
        "armability": account_armability_disclosure(_promoter_accounts()),  # G7 disclose-only
    }
    path = recs_dir / f"promote_{watcher_name}.json"
    recs_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")


def _write_watch_flag_to_params(params_path: Path, watcher_name: str,
                                flag_key: str, best_combo: dict) -> bool:
    """Write the dispatcher's REAL enable-flag key (WATCH mode) + best_combo snapshot.

    Does NOT set extra_setup_exec_armed — that requires validation + J for live
    money (OP-0 #1). Atomic write via temp file. Returns True on success.
    """
    if not params_path.exists():
        return False
    try:
        params = json.loads(params_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False

    combo_key = f"{watcher_name}_best_combo"
    doc_key = f"_{watcher_name}_promote_doc"

    # Immutable update: build a new dict
    updated = {
        **params,
        flag_key: True,
        combo_key: best_combo,
        doc_key: (
            f"AUTO-PROMOTED by pipeline_promoter ({_et_now().date()}). All 5 gates passed. "
            f"WATCH_NOT_ARMED ({flag_key}=true; exec not armed). "
            f"Arm: extra_setup_exec_armed['{watcher_name}']=true."
        ),
    }

    tmp = params_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(updated, indent=2), encoding="utf-8")
    tmp.replace(params_path)
    return True


def _append_wire_detector_proposal(watcher_name: str, details: dict, scorecard: dict,
                                   proposals_path: Path) -> bool:
    """File the wiring gap as a visible, pickable proposal row.

    Follows the conductor-proposals.jsonl row schema (proposal_id / created_at /
    source / title / kind / apply / status). Idempotent: skips when a pending
    WIRE-DETECTOR row for this watcher already exists. Returns True if a row
    was appended (False = already filed or write failed).
    """
    title = f"WIRE-DETECTOR-{watcher_name}"
    try:
        if proposals_path.exists():
            for line in proposals_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (isinstance(row, dict) and row.get("title") == title
                        and row.get("status") == "pending"):
                    print(f"[pipeline_promoter] {title} already pending — not duplicating",
                          file=sys.stderr)
                    return False
    except OSError:
        pass  # unreadable ledger -> still append (append-only is the safe default)

    best = _best_entry(scorecard)
    now_et = _et_now()
    proposal = {
        "proposal_id": f"pp-{now_et.date().isoformat()}-{watcher_name}",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": "pipeline_promoter",
        "title": title,
        "kind": "wiring",
        "watcher_name": watcher_name,
        "apply": (
            f"{watcher_name} cleared all 5 stage5 promote gates but has NO detector/dispatcher "
            f"entry in setup/scripts/setup_dispatch.py — the signal cannot reach the engine. "
            f"Wire: (1) detector in backtest/lib/watchers/, (2) roster tuple + _dispatch method "
            f"in setup_dispatch.py, (3) '<flag>_enabled' key + WATCH validation before any exec-arm. "
            f"Evidence: analysis/recommendations/promote_{watcher_name}.json"
        ),
        "gates": details,
        "scorecard_evidence": {
            "wide_pnl": best.get("wide_pnl"),
            "sharpe": best.get("sharpe"),
            "n_trades": best.get("n_trades"),
            "expectancy": best.get("expectancy", best.get("expectancy_per_trade")),
            "dir_score": best.get("dir_score", best.get("directional_score")),
            "walk_forward": (scorecard.get("walk_forward") or best.get("walk_forward")),
            "combo": best.get("combo"),
        },
        "status": "pending",
        "note": (
            "Filed by the rewritten promoter contract (2026-07-01): a gates-pass on an "
            "un-wired watcher is a WIRING work item, not a params key. Rail-4: wiring is "
            "code — propose-only."
        ),
    }
    try:
        proposals_path.parent.mkdir(parents=True, exist_ok=True)
        with proposals_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(proposal) + "\n")
        return True
    except OSError as exc:
        print(f"[pipeline_promoter] failed to append {title}: {exc}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def check_and_promote(
    script_name: str,
    watcher_name: str,
    *,
    recs_dir: Optional[Path] = None,
    params_paths: Optional[list[Path]] = None,
    proposals_path: Optional[Path] = None,
    dispatch_source: Optional[Path] = None,
    discord_outbox: Optional[Path] = None,
) -> bool:
    """Entry point called by kitchen_daemon after a scorecard script runs.

    Returns True when all gates passed AND a consumable output landed
    (WATCH flag for roster watchers / WIRE-DETECTOR proposal otherwise).

    Keyword overrides exist so tests run against tmp-dir fixtures — NEVER point
    them at live state in a test.
    """
    rd = recs_dir or RECS_DIR
    scorecard = _read_scorecard(script_name, recs_dir=rd)
    if scorecard is None:
        print(f"[pipeline_promoter] no fresh scorecard JSON found for {script_name}", file=sys.stderr)
        return False

    passed, details = _check_gates(scorecard)

    promote_path = rd / f"promote_{watcher_name}.json"
    rd.mkdir(parents=True, exist_ok=True)
    promote_path.write_text(
        json.dumps({"gates_checked_at_et": _et_now().isoformat(), "gates": details, "passed": passed}, indent=2),
        encoding="utf-8",
    )

    if not passed:
        failed = [k for k, v in details.items() if k != "all_gates_passed" and v is False]
        print(f"[pipeline_promoter] {watcher_name} BLOCKED — failed gates: {failed}", file=sys.stderr)
        return False

    roster = read_dispatcher_roster(dispatch_source)
    flag_key = roster.get(watcher_name)
    best_combo = _best_entry(scorecard).get("combo", _best_entry(scorecard))

    if flag_key:
        wrote_any = False
        for p in (params_paths if params_paths is not None else [PARAMS_PATH, AGG_PARAMS_PATH]):
            wrote_any = _write_watch_flag_to_params(p, watcher_name, flag_key, best_combo) or wrote_any
        if not wrote_any:
            print(f"[pipeline_promoter] {watcher_name}: no params file writable — NOT promoted",
                  file=sys.stderr)
            return False
        outcome = f"WATCH flag {flag_key}=true written"
    else:
        _append_wire_detector_proposal(
            watcher_name, details, scorecard,
            proposals_path or PROPOSALS_PATH,
        )
        outcome = "no dispatcher entry — WIRE-DETECTOR proposal filed, NO params key written"

    _write_promote_scorecard(watcher_name, details, scorecard, flag_key=flag_key, recs_dir=rd)
    _write_discord_ping(watcher_name, details, scorecard, flag_key=flag_key, outbox=discord_outbox)

    print(
        f"[pipeline_promoter] PROMOTED {watcher_name} — "
        f"WF={details['wf_ratio']:.2f} dir={details['directional_score']} "
        f"top5={details['top5_pct']:.0%} | {outcome}",
        file=sys.stderr,
    )
    return True


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Check gates and promote a watcher")
    ap.add_argument("--script", default="shotgun_scalper_stage5")
    ap.add_argument("--watcher", default="shotgun_scalper")
    args = ap.parse_args()
    result = check_and_promote(args.script, args.watcher)
    sys.exit(0 if result else 1)
