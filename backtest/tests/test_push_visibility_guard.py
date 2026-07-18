"""VISIBILITY guard (2026-07-18, OP-33e): the PUSH block on both glance surfaces
(gamma_glance.py + gamma_status.py) must correctly report whether J's phone/watch
can actually be pushed the answer to "is it running / is it trading" -- the
question j-question-ledger.jsonl shows J asked 40+ times over 18 days.

Root cause found this fire (two-layer, corrected mid-investigation): VAPID keys
DO exist (automation/state/.vapid.json, generated 2026-06-21), so sendPush() in
push.js/approvals.js/escalate.js is NOT silently disabled at that layer -- the
first hypothesis was wrong. The real gap is one layer deeper:
push-subscriptions.json is `[]` -- zero devices have EVER subscribed, 27 days
after VAPID went live -- because Android Chrome refuses push over plain
http://192.168.x.x (gamma-companion/MOBILE_PWA_DESIGN.md), so J needs a
one-time HTTPS front-door (Tailscale Serve) + phone-side subscribe step that
no autonomous Claude session can perform for him.

These tests pin all three states (VAPID absent / VAPID present+0 subs / VAPID
present+N subs) against a synthetic tmp STATE dir so a future edit can't
silently regress the diagnosis into a false GREEN or a false claim that push
already works.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def test_gamma_glance_push_vapid_absent(tmp_path, monkeypatch):
    gg = importlib.import_module("gamma_glance")
    monkeypatch.setattr(gg, "STATE", tmp_path)
    lines = gg._push_status()
    text = "\n".join(lines)
    assert "DISABLED" in text
    assert ".vapid.json absent" in text
    assert "gen-vapid.js" in text


def test_gamma_glance_push_vapid_present_zero_subs(tmp_path, monkeypatch):
    gg = importlib.import_module("gamma_glance")
    monkeypatch.setattr(gg, "STATE", tmp_path)
    (tmp_path / ".vapid.json").write_text(json.dumps({"publicKey": "x", "privateKey": "y"}), encoding="utf-8")
    (tmp_path / "push-subscriptions.json").write_text("[]", encoding="utf-8")
    lines = gg._push_status()
    text = "\n".join(lines)
    assert "0 devices subscribed" in text
    assert "MOBILE_PWA_DESIGN.md" in text
    assert "Tailscale" in text


def test_gamma_glance_push_vapid_present_with_subs(tmp_path, monkeypatch):
    gg = importlib.import_module("gamma_glance")
    monkeypatch.setattr(gg, "STATE", tmp_path)
    (tmp_path / ".vapid.json").write_text(json.dumps({"publicKey": "x", "privateKey": "y"}), encoding="utf-8")
    (tmp_path / "push-subscriptions.json").write_text(
        json.dumps([{"endpoint": "https://fcm.example/abc"}]), encoding="utf-8")
    lines = gg._push_status()
    text = "\n".join(lines)
    assert "1 device(s) subscribed" in text
    assert "pushes are live" in text
    # never leak the subscription endpoint/key content
    assert "fcm.example" not in text


def test_gamma_glance_push_never_flips_overall_red_alone(tmp_path, monkeypatch):
    """A 0-subscriber push state is a known, J-only, one-time setup gap -- it must
    never by itself flip build()'s bottom-line OVERALL verdict to RED (that would
    cry wolf on every glance until J does a phone-side task, drowning real reds).
    Forces every OTHER block to GREEN via monkeypatch so only PUSH is RED-shaped,
    then asserts the bottom line still reads GREEN."""
    gg = importlib.import_module("gamma_glance")
    monkeypatch.setattr(gg, "STATE", tmp_path)
    (tmp_path / ".vapid.json").write_text(json.dumps({"publicKey": "x", "privateKey": "y"}), encoding="utf-8")
    (tmp_path / "push-subscriptions.json").write_text("[]", encoding="utf-8")  # RED-shaped push block

    monkeypatch.setattr(gg, "_engine_today", lambda now: (gg.GREEN, ["  engine ok"]))
    monkeypatch.setattr(gg, "_funnel_today", lambda now: (gg.GREEN, ["  funnel ok"]))
    monkeypatch.setattr(gg, "_levels", lambda: (gg.GREEN, ["  levels ok"]))
    monkeypatch.setattr(gg, "_premarket", lambda now: (gg.GREEN, ["  premarket ok"]))
    monkeypatch.setattr(gg, "_arms", lambda: ["  arms ok"])
    monkeypatch.setattr(gg, "_structure_stop", lambda: ["  exit mode ok"])
    monkeypatch.setattr(gg, "_probe_arm", lambda now: ["  probe ok"])

    text = gg.build()
    assert "PUSH (phone/watch)" in text
    assert "0 devices subscribed" in text  # push block IS RED-shaped
    assert "OVERALL: " + gg.GREEN in text, "push-only RED must not flip the bottom-line verdict"


def test_gamma_status_push_glance_matches_gamma_glance(tmp_path, monkeypatch):
    """gamma_status.py's _push_glance() must agree with gamma_glance.py's
    _push_status() on the same fixture -- the two surfaces must never disagree
    about whether J's phone can actually be reached."""
    gs = importlib.import_module("gamma_status")
    monkeypatch.setattr(gs, "STATE", tmp_path)
    (tmp_path / ".vapid.json").write_text(json.dumps({"publicKey": "x", "privateKey": "y"}), encoding="utf-8")
    (tmp_path / "push-subscriptions.json").write_text("[]", encoding="utf-8")
    lines = gs._push_glance()
    text = "\n".join(lines)
    assert "0 devices subscribed" in text
    assert "MOBILE_PWA_DESIGN.md" in text


def test_gamma_status_push_vapid_absent(tmp_path, monkeypatch):
    gs = importlib.import_module("gamma_status")
    monkeypatch.setattr(gs, "STATE", tmp_path)
    lines = gs._push_glance()
    text = "\n".join(lines)
    assert "DISABLED" in text
    assert "gen-vapid.js" in text
