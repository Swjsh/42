"""Guard: params files must be clean, plain-UTF-8, ASCII-only JSON.

Regression guard for the cp1252-mojibake foot-gun (2026-06-18): params.json and
aggressive/params.json had accumulated double-encoded smart-quotes / em-dashes /
arrows (e.g. the bytes for "  in prose `_doc` fields, and \\u00e2\\u20ac\\u201d
escape runs). Raw bytes that are not 7-bit ASCII make a plain
`json.load(open(path, encoding='utf-8'))` fragile: any consumer that opens the
file with the platform default codec (cp1252 on Windows) or `encoding='ascii'`
raises UnicodeDecodeError. These files are the single source of truth for rule
values and are read by many small scripts, so they MUST stay pure ASCII.

What this guards:
  1. Each file parses via plain `json.load(open(path, encoding='utf-8'))` — no error.
  2. The raw bytes contain zero non-ASCII bytes (>= 0x80).
  3. The DECODED string values contain zero non-ASCII characters — this also
     catches mojibake stored as `\\uXXXX` escape runs (ASCII bytes on disk, but
     they decode to non-ASCII chars).

If this fails: a non-ASCII character was reintroduced into a prose field. Replace
it with its ASCII equivalent (e.g. em-dash -> '-', smart quote -> '/'/'\\'',
arrow -> '->', '>=' / '<=' / 'x' / '+/-'). NEVER alter a functional value — only
normalize prose punctuation.

Run:  cd backtest && python -m pytest tests/test_params_encoding.py -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

PARAMS_FILES = [
    REPO / "automation" / "state" / "params.json",
    REPO / "automation" / "state" / "aggressive" / "params.json",
]


def _iter_strings(obj):
    """Yield every string that appears as a key or value anywhere in the JSON."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                yield k
            yield from _iter_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_strings(v)
    elif isinstance(obj, str):
        yield obj


@pytest.mark.parametrize("path", PARAMS_FILES, ids=lambda p: p.name)
def test_params_loads_via_plain_utf8(path: Path) -> None:
    """A plain `json.load(open(path, encoding='utf-8'))` must succeed (no BOM, valid)."""
    assert path.exists(), f"params file missing: {path}"
    # The canonical fragile read path. Must not raise.
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    assert isinstance(data, dict), f"{path.name}: expected a JSON object at top level"
    # No UTF-8 BOM (a BOM breaks naive json.load(open(path)) on some readers).
    raw = path.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf", f"{path.name}: file has a UTF-8 BOM; save without BOM"


@pytest.mark.parametrize("path", PARAMS_FILES, ids=lambda p: p.name)
def test_params_bytes_are_pure_ascii(path: Path) -> None:
    """No raw byte may be >= 0x80 — keeps the file readable under any codec (cp1252/ascii)."""
    raw = path.read_bytes()
    offenders = [(i, hex(b)) for i, b in enumerate(raw) if b > 0x7F]
    assert not offenders, (
        f"{path.name}: {len(offenders)} non-ASCII byte(s) found at offsets "
        f"{offenders[:8]}{'...' if len(offenders) > 8 else ''}. "
        "Replace mojibake/smart-punctuation in prose fields with ASCII "
        "(em-dash -> '-', smart quote -> ' or \", arrow -> '->', '>='/'<='/'x'/'+/-'). "
        "Do NOT change any functional value."
    )


@pytest.mark.parametrize("path", PARAMS_FILES, ids=lambda p: p.name)
def test_params_decoded_values_are_pure_ascii(path: Path) -> None:
    """Decoded string values must be ASCII too (catches mojibake stored as \\uXXXX escapes)."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    bad = []
    for s in _iter_strings(data):
        for ch in s:
            if ord(ch) > 0x7F:
                bad.append((s[:60], hex(ord(ch))))
                break
    assert not bad, (
        f"{path.name}: {len(bad)} string value(s) contain non-ASCII characters after decoding "
        f"(e.g. {bad[:3]}). These may be stored as \\uXXXX escapes (ASCII on disk but decode to "
        "mojibake). Normalize the prose punctuation to ASCII; never alter a functional value."
    )
