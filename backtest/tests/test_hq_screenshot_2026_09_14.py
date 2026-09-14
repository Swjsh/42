"""Guard for the 2026-09-14 conductor-fire discovery: a RELATIVE --user-data-dir silently kept
Chrome's headless DevTools port from ever opening on this box (every CDP poll timed out; the port
never listened at all). `hq_screenshot.profile_dir()` must always return an absolute path so this
foot-gun cannot silently return in a future edit. See setup/scripts/hq_screenshot.py::profile_dir.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "setup" / "scripts"))

from hq_screenshot import profile_dir  # noqa: E402


def test_profile_dir_is_always_absolute_relative_cwd():
    out = Path("scratchpad/hq-visuals/hq-check.png")  # a relative Path, as CLI --out defaults to
    p = profile_dir(out)
    assert p.is_absolute(), (
        f"profile_dir() returned a relative path ({p}) -- this is the exact 2026-09-14 "
        "foot-gun: Chrome's headless DevTools port never opens with a relative --user-data-dir "
        "on this box."
    )


def test_profile_dir_is_absolute_given_an_already_absolute_out():
    out = Path(r"C:\Users\jackw\Desktop\42\scratchpad\hq-visuals\hq-check.png")
    p = profile_dir(out)
    assert p.is_absolute()


def test_profile_dir_lives_alongside_the_output_not_some_shared_temp():
    # keeps captures self-contained per --out directory rather than colliding across concurrent
    # callers (e.g. two screenshot runs with different --out dirs must not share one Chrome profile)
    out_a = Path("scratchpad/hq-visuals/a.png")
    out_b = Path("scratchpad/other-dir/b.png")
    assert profile_dir(out_a) != profile_dir(out_b)
    assert profile_dir(out_a).parent == out_a.resolve().parent
