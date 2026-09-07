"""Guard (L317, 2026-09-07): a BOM at the top of STATUS.md must NOT make upsert() recreate a
second '## Known broken' heading. Before this guard the helper decoded plain utf-8, the
first line became '﻿## Known broken', the heading regex failed, and every producer
prepended a fresh section -- the live file reached three."""
import importlib.util, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("skb", ROOT / "setup/scripts/status_known_broken.py")
skb = importlib.util.module_from_spec(spec); sys.modules["skb"] = skb; spec.loader.exec_module(skb)

def test_bom_prefixed_status_keeps_single_heading(tmp_path):
    status = tmp_path / "STATUS.md"
    status.write_bytes("﻿## Known broken\n\n- [2026-09-06 10:00 ET] OLD-MARKER: x\n\n## Other\n\nbody\n".encode("utf-8"))
    assert skb.upsert("NEW-MARKER:", "- [2026-09-07 05:45 ET] NEW-MARKER: y", status_path=status)
    text = status.read_bytes().decode("utf-8")
    assert "﻿" not in text, "embedded/leading BOM must be stripped"
    assert text.count("## Known broken") == 1, "must not recreate the heading"
    assert "NEW-MARKER: y" in text and "OLD-MARKER: x" in text and "## Other" in text

def test_embedded_mojibake_bom_is_healed(tmp_path):
    status = tmp_path / "STATUS.md"
    status.write_text("## Known broken\n\n- a\n\nï»¿## Known broken\n\n- b\n", encoding="utf-8")
    skb.upsert("M:", "- [t] M: z", status_path=status)
    text = status.read_text(encoding="utf-8")
    assert "ï»¿" not in text
