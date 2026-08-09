#!/usr/bin/env python
"""direction_symmetry_audit.py -- is the engine as willing to go LONG as it is to go SHORT?

J, 2026-08-09: "i dont understand the gripe witth 'calls' vs PUTS, you're very keen on bear
setups. we need to play both sides of the market, period."

He was right, and the reason nobody caught it is that the asymmetry is not in any ONE place --
it is spread across a numeric knob here, a VIX cap there, a time veto somewhere else. Each was
individually ratified with a scorecard. Nobody ever summed them and asked "what is the TOTAL
entry bar for a call versus a put?" This instrument asks exactly that question, every night, so
the answer is a traffic light instead of something J has to notice in prose.

That framing is not a preference -- it is ratified doctrine. CLAUDE.md OP-16: "Setup scope =
BOTH directions (UNLOCKED 2026-06-28) -- direction is NOT a scope, *validation* is." A gate may
absolutely be direction-specific IF its own evidence is direction-specific and current. What is
NOT allowed is drifting into a structurally harder long side by accumulation.

EXTEND, DO NOT FORK. Everything here reads existing sources:
  automation/state/gate-registry.json          the 23-gate registry (scope, armed_date,
                                               last_revalidated, revalidation_interval_days)
  automation/state/gate-registry-status.json   gate_expiry_check's own per-gate verdicts --
                                               REUSED, never recomputed (that harness owns the
                                               refused-cohort P&L question)
  automation/state/params.json                 core Safe live knobs
  automation/state/aggressive/params.json      Bold live knobs
No new registry, no second source of truth, no network, no LLM, $0.

WHAT IT FLAGS (and deliberately what it does NOT):
  - PAIRED NUMERIC KNOBS whose bull and bear values differ (e.g. filter_10_min_triggers_bull=2
    vs _bear=1 -- a call needs TWICE the triggers a put does).
  - SEMANTIC PAIRS that are not name-twins (vix_bull_hard_cap vs vix_bear_hard_cap).
  - UNPAIRED GATES: a direction-specific gate with no counterpart on the other side.
  - STALE EVIDENCE behind any of the above, via the registry's own dates.
It does NOT propose flipping anything. An asymmetry with current, direction-specific evidence
is legitimate; the instrument's job is to make sure every one of them is CHOSEN rather than
inherited.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "automation" / "state" / "gate-registry.json"
STATUS = REPO / "automation" / "state" / "gate-registry-status.json"
PARAMS = {"safe": REPO / "automation" / "state" / "params.json",
          "bold": REPO / "automation" / "state" / "aggressive" / "params.json"}
OUT = REPO / "automation" / "state" / "direction-symmetry.json"

# Knobs whose bull/bear halves are not simple name twins.
SEMANTIC_PAIRS = [("vix_bull_hard_cap", "vix_bear_hard_cap"),
                  ("premium_stop_pct_bull", "premium_stop_pct_bear")]
STALE_DAYS = 45          # matches the registry's own default_revalidation_interval_days spirit


def _load(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _direction(text: str) -> str | None:
    t = (text or "").lower()
    has_bull = bool(re.search(r"\bbull\b|_bull_|_bull$|bullish|call", t))
    has_bear = bool(re.search(r"\bbear\b|_bear_|_bear$|bearish|\bput\b", t))
    if has_bull and not has_bear:
        return "bull"
    if has_bear and not has_bull:
        return "bear"
    return None


def paired_knobs(params: dict) -> list[dict]:
    """Numeric knobs that exist for BOTH directions but carry DIFFERENT values."""
    out = []
    seen: set[tuple[str, str]] = set()
    for key in params:
        if key.startswith("_"):
            continue
        for a, b in (("bull", "bear"), ("bear", "bull")):
            if a not in key:
                continue
            twin = key.replace(a, b)
            if twin not in params:
                continue
            pair = tuple(sorted((key, twin)))
            if pair in seen:
                continue
            seen.add(pair)
            bull_k = key if a == "bull" else twin
            bear_k = twin if a == "bull" else key
            bv, rv = params.get(bull_k), params.get(bear_k)
            if isinstance(bv, bool) or isinstance(rv, bool) or bv == rv:
                continue
            if not isinstance(bv, (int, float)) or not isinstance(rv, (int, float)):
                continue
            out.append({"bull_key": bull_k, "bull_value": bv,
                        "bear_key": bear_k, "bear_value": rv,
                        "note": _read_knob(bull_k, bv, bear_k, rv)})
    for bull_k, bear_k in SEMANTIC_PAIRS:
        if bull_k in params and bear_k in params and params[bull_k] != params[bear_k]:
            if any(o["bull_key"] == bull_k for o in out):
                continue
            out.append({"bull_key": bull_k, "bull_value": params[bull_k],
                        "bear_key": bear_k, "bear_value": params[bear_k],
                        "note": _read_knob(bull_k, params[bull_k], bear_k, params[bear_k])})
    return out


def _read_knob(bk: str, bv, rk: str, rv) -> str:
    """Say which side the asymmetry FAVOURS in plain language -- a raw number pair is not a
    finding until someone states which direction it makes harder to trade."""
    if "min_triggers" in bk or "threshold" in bk:
        harder = "bull" if bv > rv else "bear"
        return f"{harder} needs the higher bar ({bv} vs {rv}) -- harder to ENTER {harder}"
    if "vix" in bk and "cap" in bk:
        harder = "bull" if bv < rv else "bear"
        return (f"{harder} is blocked at the LOWER VIX ({bv} vs {rv}) -- {harder}'s tradeable "
                f"volatility window is narrower by {abs(bv - rv)} VIX points")
    if "stop_pct" in bk:
        return f"stop widths differ: bull {bv} vs bear {rv}"
    return f"bull {bv} vs bear {rv}"


def unpaired_gates(registry: dict, params_by_acct: dict, status: dict) -> list[dict]:
    """Direction-specific gates with no counterpart on the opposite side."""
    gates = registry.get("gates") or []
    st_rows = {}
    for r in (status.get("gates") or status.get("rows") or []):
        if isinstance(r, dict):
            st_rows[r.get("id") or r.get("gate_id")] = r
    today = dt.date.today()
    out = []
    for g in gates:
        gid = g.get("id", "")
        d = _direction(" ".join(str(g.get(k, "")) for k in ("id", "params_key", "scope",
                                                            "description")))
        if d is None:
            continue
        pk = g.get("params_key") or gid
        armed_in = []
        for acct, p in params_by_acct.items():
            v = p.get(pk)
            if v is True or (isinstance(v, (int, float)) and not isinstance(v, bool) and v):
                armed_in.append(acct)
        # counterpart = a registry gate with the same shape on the other side
        other = "bear" if d == "bull" else "bull"
        twin_id = gid.replace(d, other) if d in gid else None
        has_twin = bool(twin_id and any(x.get("id") == twin_id for x in gates))
        age = None
        for key in ("last_revalidated", "armed_date", "cohort_validated_on"):
            raw = g.get(key)
            if isinstance(raw, str) and re.match(r"\d{4}-\d{2}-\d{2}", raw):
                age = (today - dt.date.fromisoformat(raw[:10])).days
                break
        srow = st_rows.get(gid) or {}
        out.append({"gate_id": gid, "direction": d, "params_key": pk,
                    "armed_in": armed_in, "has_opposite_twin": has_twin,
                    "evidence_age_days": age,
                    "evidence_stale": (age is not None and age > STALE_DAYS),
                    "expiry_verdict": srow.get("verdict") or srow.get("overall"),
                    "refused_cohort_note": srow.get("costing_note") or srow.get("note")})
    return out


def phantom_documented_knobs(params: dict) -> list[dict]:
    """A `_<key>_doc` whose `<key>` is ABSENT from live params -- documentation for a gate that
    is not wired.

    Added 2026-08-09 because it burned this session twice in one hour: `_vix_bull_hard_cap_doc`
    describes a bull VIX cap ("lowered 22->18, blocks all CALL entries when VIX>=18") in
    convincing, scorecard-citing detail -- and `vix_bull_hard_cap` exists in NEITHER params file
    and is enforced NOWHERE in code. I reported it to J as a live bull-side constraint. It is a
    fossil. The doc outlived the knob.

    This is L249's shape exactly ("several files' own comments claim behaviour the code doesn't
    deliver"), and it is worse here than in code comments: a params _doc reads like live config,
    so anyone auditing the engine by reading params.json -- human or model -- will count a gate
    that cannot fire. Direction audits are especially vulnerable, since a phantom on one side
    manufactures a symmetry (or an asymmetry) that does not exist."""
    out = []
    for key in params:
        if not (key.startswith("_") and key.endswith("_doc")):
            continue
        target = key[1:-4]
        if not target or target in params:
            continue
        # A doc whose target is a SUFFIXED label of a live key documents a trial/variant of
        # that key, not a missing gate (e.g. _block_elite_bull_trial2_doc -> block_elite_bull
        # IS live). Only flag when NO live key is a prefix of the target -- otherwise this
        # detector cries wolf on the repo's own trial-annotation convention and gets ignored,
        # which is how a real phantom slips through.
        parent = next((k for k in params
                       if not k.startswith("_") and target.startswith(k) and k != target), None)
        if parent:
            out.append({"doc_key": key, "target": target, "classification": "TRIAL_NOTE",
                        "documents_live_key": parent, "direction": _direction(target)})
            continue
        out.append({"doc_key": key, "target": target, "classification": "PHANTOM",
                    "documents_live_key": None, "direction": _direction(target),
                    "why_it_matters": ("no live params key and no live parent -- reads as "
                                       "config, cannot fire, and will be counted as a real "
                                       "constraint by anyone auditing params.json")})
    return out


def run() -> dict:
    registry, status = _load(REGISTRY), _load(STATUS)
    params_by_acct = {k: _load(p) for k, p in PARAMS.items()}

    knobs = {a: paired_knobs(p) for a, p in params_by_acct.items()}
    phantoms = {a: phantom_documented_knobs(p) for a, p in params_by_acct.items()}
    gates = unpaired_gates(registry, params_by_acct, status)

    armed_bull = [g for g in gates if g["direction"] == "bull" and g["armed_in"]]
    armed_bear = [g for g in gates if g["direction"] == "bear" and g["armed_in"]]
    n_knob_asym = sum(len(v) for v in knobs.values())
    stale = [g["gate_id"] for g in (armed_bull + armed_bear) if g["evidence_stale"]]
    lopsided = [g["gate_id"] for g in (armed_bull + armed_bear) if not g["has_opposite_twin"]]

    # Traffic light. RED is reserved for "the entry bar is materially uneven AND some of the
    # evidence holding it up has expired" -- an asymmetry with fresh, direction-specific
    # evidence is a CHOICE and stays YELLOW at worst.
    if n_knob_asym == 0 and not stale:
        light = "GREEN"
    elif stale and (n_knob_asym or lopsided):
        light = "RED"
    else:
        light = "YELLOW"

    out = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "doctrine": "CLAUDE.md OP-16 -- direction is NOT a scope, validation is.",
        "traffic_light": light,
        "summary": {
            "armed_bull_specific_gates": len(armed_bull),
            "armed_bear_specific_gates": len(armed_bear),
            "asymmetric_numeric_knobs": n_knob_asym,
            "gates_without_an_opposite_twin": lopsided,
            "gates_on_stale_evidence": stale,
            "phantom_documented_knobs": sum(len(v) for v in phantoms.values()),
            "stale_threshold_days": STALE_DAYS,
        },
        "asymmetric_knobs": knobs,
        "phantom_documented_knobs": phantoms,
        "direction_specific_gates": gates,
        "reading": (
            "Every row here may be individually justified. The question this instrument exists "
            "to answer is whether they are still justified TOGETHER: a call that needs more "
            "triggers AND a higher macro score AND a narrower VIX window AND survives a "
            "time veto faces a compounded bar nobody ever priced as a whole."),
        "not_a_proposal": "Descriptive only. Flips nothing, proposes nothing, places no order.",
    }
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def main() -> int:
    o = run()
    s = o["summary"]
    print(f"[dir-symmetry] {o['traffic_light']}  "
          f"bull-gates={s['armed_bull_specific_gates']} bear-gates={s['armed_bear_specific_gates']} "
          f"asym-knobs={s['asymmetric_numeric_knobs']}")
    for acct, rows in o["asymmetric_knobs"].items():
        for r in rows:
            print(f"   [{acct}] {r['bull_key']}={r['bull_value']} vs "
                  f"{r['bear_key']}={r['bear_value']}  -> {r['note']}")
    if s["gates_without_an_opposite_twin"]:
        print(f"   no opposite twin: {s['gates_without_an_opposite_twin']}")
    for acct, rows in o["phantom_documented_knobs"].items():
        for r in rows:
            print(f"   [{acct}] PHANTOM {r['doc_key']} -> '{r['missing_knob']}' is NOT a live key")
    if s["gates_on_stale_evidence"]:
        print(f"   STALE evidence (> {s['stale_threshold_days']}d): {s['gates_on_stale_evidence']}")
    print(f"[dir-symmetry] wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
