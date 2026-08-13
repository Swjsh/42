"""Guard: bg_status must SEE Agent-tool subagents, and must flag dud returns (2026-08-12).

WHY THIS EXISTS. `bg_status.py` was built on 2026-08-06 specifically to retire J's repeated
"is the background work still running?" question (OP-33(e): a repeated question is a MISSING
INSTRUMENT). It then failed to retire it -- J asked a **37th** time on 2026-08-12
(`automation/state/j-question-ledger.jsonl`, intent `is_running`) -- because the instrument globbed
only `subagents/workflows/*/journal.jsonl`. That covers runs of the Workflow tool. It does NOT
cover subagents spawned with the **Agent tool**, which is how nearly all background work in this
repo is actually dispatched. With 13 agents on disk the tool printed "No workflow runs found."

That is L292 exactly: a monitor whose coverage SCOPE is narrower than the thing it monitors reports
"nothing is running" when the truth is "I cannot see". The failure is silent and reads as good news,
which is the worst possible direction (C7).

The second half of this guard pins the HOLDING? detector. Two of the 13 agents that night returned
long, well-formatted, entirely plausible payloads whose actual content was "I am still waiting on my
sub-agents." A character-count check (EMPTY_PAYLOAD_CHARS) cannot see that -- one of them was 1,422
chars of genuine-looking analysis table whose lede was "Holding for the arms to finish." Both ledes
below are verbatim from that night and are the regression fixtures.

WHAT MUST NEVER ROT:
  * Agent-tool metas are discovered at all.
  * The completion oracle stays self-contained (last-record shape), NOT a scan of the parent
    session transcript -- a sub-agent's tool_result lands in its PARENT AGENT's transcript, so
    session-scanning marks every depth-2 agent permanently "outstanding" (verified 2026-08-12:
    6 of 13 misreported that way).
  * HOLDING? checks the LEDE ONLY. A tail-only window (first cut) missed the 1,422-char case; a
    head+tail window then made `test_mid_body_mention_of_waiting_is_NOT_flagged` go RED, because on
    a sub-700-char message head+tail covers the whole text and an ordinary report that mentions a
    still-running nightly task gets flagged. All three observed duds lead with the tell, so the
    window follows the evidence. Do not re-add a tail window without a REAL sign-off example.
  * Output never dies on its own payload (cp1252 console + an emoji in an agent summary).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import bg_status as bs  # noqa: E402

# Verbatim ledes from the two dud returns of 2026-08-12.
LEDE_CONSTANTS_AUDIT = (
    "All three sweep agents are still running. Once their reports arrive I'll synthesize the "
    "ranked register -- the exemplar's siblings are already coming into focus."
)
LEDE_SLIPPAGE = (
    "Holding for the arms to finish. Meaningful analysis landed while waiting.\n\n"
    + ("**Why the re-baseline was very unlikely to resurrect anything.** " * 20)
)


def _mk_agent(root: Path, agent_id: str, *, desc: str, final_text: str | None = None,
              mid_tool: bool = False, depth: int = 1, model: str = "sonnet") -> None:
    """Write a session-shaped agent pair: agent-<id>.meta.json + agent-<id>.jsonl."""
    sub = root / "C--proj" / "sess" / "subagents"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / f"agent-{agent_id}.meta.json").write_text(json.dumps({
        "agentType": "general-purpose", "description": desc,
        "toolUseId": f"toolu_{agent_id}", "spawnDepth": depth, "model": model,
    }), encoding="utf-8")

    content: list[dict] = []
    if final_text is not None:
        content.append({"type": "text", "text": final_text})
    if mid_tool:
        content.append({"type": "tool_use", "name": "Bash", "input": {}})
    lines = [
        json.dumps({"type": "user", "message": {"content": "go"}}),
        json.dumps({"type": "assistant", "message": {"content": content}}),
    ]
    (sub / f"agent-{agent_id}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture()
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "_sessions_root", lambda: tmp_path)
    return tmp_path


def _scan_one(root: Path, agent_id: str) -> dict:
    meta = root / "C--proj" / "sess" / "subagents" / f"agent-{agent_id}.meta.json"
    return bs._scan_agent(meta)


# --------------------------------------------------------------------------- coverage


def test_agent_tool_subagents_are_discovered_at_all(root):
    """THE REGRESSION. If this goes RED the instrument is blind to Agent-tool work again and J
    gets 'nothing running' while a dozen agents are live."""
    _mk_agent(root, "aaa111", desc="some background work", final_text="x" * 500)
    found = bs._find_agent_metas(None)
    assert len(found) == 1, f"Agent-tool subagents are invisible to bg_status again: {found}"


def test_workflow_scanning_is_not_broken_by_the_agent_addition(root):
    """Scope guard: agents were ADDED, workflows were not traded away for them."""
    wf = root / "C--proj" / "sess" / "subagents" / "workflows" / "wf_x"
    wf.mkdir(parents=True)
    (wf / "journal.jsonl").write_text(
        json.dumps({"type": "started"}) + "\n"
        + json.dumps({"type": "result", "label": "lane1", "value": "y" * 500}) + "\n",
        encoding="utf-8")
    dirs = bs._find_workflow_dirs(None)
    assert len(dirs) == 1
    assert bs._scan(dirs[0])["state"] == "COMPLETE"


def test_completion_oracle_is_self_contained_not_a_session_transcript_scan():
    """A depth-2 agent's tool_result never appears in the session transcript. Reading the session
    file to decide completion marked 6 of 13 agents permanently 'outstanding' on 2026-08-12, so
    the oracle must not depend on it."""
    src = (SCRIPTS / "bg_status.py").read_text(encoding="utf-8")
    for banned in ("tool_result", ".jsonl'", 'sessionId'):
        assert banned not in src.split("def _scan_agent")[1].split("def ")[0], (
            f"_scan_agent reaches for {banned!r} -- the completion oracle must stay local to the "
            "agent's own transcript")


# --------------------------------------------------------------------------- states


def test_running_agent_mid_tool_call_is_not_reported_done(root):
    """An assistant turn ending in tool_use means the agent is waiting on a tool, not finished."""
    _mk_agent(root, "run001", desc="live work", final_text="working on it", mid_tool=True)
    assert _scan_one(root, "run001")["state"] == "RUNNING"


def test_finished_agent_with_real_payload_is_done(root):
    _mk_agent(root, "done01", desc="real work", final_text="A real verdict. " * 60)
    assert _scan_one(root, "done01")["state"] == "DONE"


def test_empty_return_is_flagged(root):
    """The 2026-08-06 API-529 class: agent completes, returns nothing."""
    _mk_agent(root, "mt0001", desc="died on 529", final_text="")
    assert _scan_one(root, "mt0001")["state"] == "EMPTY"


@pytest.mark.parametrize("lede", [LEDE_CONSTANTS_AUDIT, LEDE_SLIPPAGE])
def test_holding_returns_are_flagged_not_counted_as_answers(root, lede):
    """Both verbatim 2026-08-12 dud returns. Long and plausible; neither delivered an answer."""
    _mk_agent(root, "hold01", desc="dud return", final_text=lede)
    got = _scan_one(root, "hold01")
    assert got["state"] == "HOLDING?", (
        f"a waiting-message return scored {got['state']} with {got['final_chars']} chars -- a "
        "character count cannot catch this, which is why it went unnoticed for hours")


def test_the_1422_char_case_would_pass_a_pure_size_check(root):
    """Pins WHY the size heuristic is insufficient: the slippage dud was 20x EMPTY_PAYLOAD_CHARS."""
    _mk_agent(root, "size01", desc="big dud", final_text=LEDE_SLIPPAGE)
    got = _scan_one(root, "size01")
    assert got["final_chars"] > bs.EMPTY_PAYLOAD_CHARS * 10
    assert got["state"] == "HOLDING?"


def test_mid_body_mention_of_waiting_is_NOT_flagged(root):
    """False-positive guard. A report whose BODY mentions a still-running task is ordinary prose;
    only the lede and the sign-off indicate a dud return."""
    body = ("VERDICT: the ladder is dead on arrival. " * 8
            + "The nightly task is still running on its own schedule. "
            + "Conclusion stands on 391 days of real fills. " * 8)
    _mk_agent(root, "prose1", desc="genuine report", final_text=body)
    assert _scan_one(root, "prose1")["state"] == "DONE"


def test_third_real_dud_lede_is_caught(root):
    """The slippage agent's 3rd notification, verbatim. Its BODY carried genuinely firm findings
    (the exit-slippage asymmetry bug, proven to the cent) -- which is exactly why the lede matters:
    a useful-looking report can still be an unfinished one, and the status column must say so."""
    _mk_agent(root, "third1", desc="3rd notification",
              final_text="77/78 -- control arm nearly done, treatment chain will fire "
                         "automatically. Waiting on the completion notifications.\n\n"
                         + "Validity controls are now all in place. " * 40)
    assert _scan_one(root, "third1")["state"] == "HOLDING?"


def test_no_tail_window_was_reintroduced():
    """Pins the lede-only decision. A tail window is what made the false-positive guard go RED;
    re-adding one without a REAL observed sign-off case re-opens that hole."""
    src = (SCRIPTS / "bg_status.py").read_text(encoding="utf-8")
    assert "HOLDING_TAIL_CHARS" not in src, (
        "a tail window came back -- on short messages head+tail covers the whole text and ordinary "
        "reports get flagged HOLDING?; see test_mid_body_mention_of_waiting_is_NOT_flagged")


# --------------------------------------------------------------------------- robustness


def test_output_never_dies_on_its_own_payload(root, capsys):
    """cp1252 consoles here raised UnicodeEncodeError mid-print on an emoji in an agent summary,
    killing the whole report. A status tool that crashes on its payload reports nothing at all."""
    _mk_agent(root, "uni001", desc="emoji ❌ report \U0001f4c9",
              final_text="Still waiting for the arms ❌ " + "detail " * 40)
    assert bs.main([]) == 0
    out = capsys.readouterr().out
    assert "HOLDING?" in out
    out.encode("ascii")  # raises if any non-ascii escaped into the report


def test_fails_open_on_a_corrupt_meta(root):
    sub = root / "C--proj" / "sess" / "subagents"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / "agent-bad001.meta.json").write_text("{not json", encoding="utf-8")
    got = bs._scan_agent(sub / "agent-bad001.meta.json")
    assert "error" in got, "a corrupt meta must degrade to an ERR row, never raise"
    assert bs.main([]) == 0


def test_live_filter_shows_only_running(root, capsys):
    _mk_agent(root, "run002", desc="live one", final_text="working", mid_tool=True)
    _mk_agent(root, "don002", desc="finished one", final_text="A real verdict. " * 60)
    bs.main(["--live"])
    out = capsys.readouterr().out
    assert "live one" in out
    assert "finished one" not in out


def test_json_mode_reports_a_running_count(root):
    _mk_agent(root, "run003", desc="live", final_text="w", mid_tool=True)
    _mk_agent(root, "don003", desc="done", final_text="A real verdict. " * 60)
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bs.main(["--json"])
    payload = json.loads(buf.getvalue())
    assert payload["n_running"] == 1
    assert len(payload["agents"]) == 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
