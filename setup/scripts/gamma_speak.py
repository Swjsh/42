"""gamma_speak.py -- give the evening narrative a literal voice (Kokoro TTS, $0 local).

Reads automation/state/gamma-narrative.json (written by gamma_narrative.py),
synthesizes speech with Kokoro-82M (Apache-2.0, runs on CPU in seconds), writes
automation/state/gamma-voice-{date}.wav for the dashboard / J to play.

Runs in its own venv: setup/.tts-venv/Scripts/python.exe setup/scripts/gamma_speak.py
Model weights live in setup/tts/ (gitignored -- 340MB, never in the public repo).
Chained after gamma_narrative.py by the Gamma_EveningNarrative task.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
TTS_DIR = REPO / "setup" / "tts"
VOICE = "am_michael"  # calm US male; see kokoro voices list for alternatives

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


def speech_text(narrative: dict) -> str:
    """Make the written narrative pleasant to LISTEN to: strip label prefixes,
    normalize unicode punctuation the TTS chokes on."""
    text = str(narrative.get("text") or "")
    text = re.sub(r"^\(deterministic fallback.*?\)\s*", "", text, flags=re.S)
    text = re.sub(r"^(WHAT I SAW|WHAT I DID|WHAT I LEARNED|WHAT I'M CHANGING)\s*:\s*",
                  "", text, flags=re.M | re.I)
    text = (text.replace("‑", "-").replace("–", "-").replace("—", " - ")
                .replace("’", "'").replace("‘", "'")
                .replace("“", '"').replace("”", '"'))
    text = re.sub(r"[#*_`|>]", "", text)          # markdown remnants
    text = re.sub(r"\s+", " ", text).strip()
    day = narrative.get("date", "")
    return f"Gamma here. My day, {day}. {text}"


def main() -> int:
    try:
        narrative = json.loads((STATE / "gamma-narrative.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"NO NARRATIVE TO SPEAK: {exc}", file=sys.stderr)
        return 1

    try:
        import soundfile as sf
        from kokoro_onnx import Kokoro
    except ImportError as exc:
        print(f"TTS DEPS MISSING (run in setup/.tts-venv): {exc}", file=sys.stderr)
        return 1

    model = TTS_DIR / "kokoro-v1.0.onnx"
    voices = TTS_DIR / "voices-v1.0.bin"
    if not model.exists() or not voices.exists():
        print(f"MODEL FILES MISSING in {TTS_DIR} (see module docstring)", file=sys.stderr)
        return 1

    text = speech_text(narrative)
    kokoro = Kokoro(str(model), str(voices))
    samples, sample_rate = kokoro.create(text, voice=VOICE, speed=1.05, lang="en-us")

    out = STATE / f"gamma-voice-{narrative.get('date', 'unknown')}.wav"
    sf.write(str(out), samples, sample_rate)
    dur = len(samples) / float(sample_rate)
    print(f"spoke {len(text)} chars -> {out} ({dur:.1f}s @ {sample_rate}Hz)")
    return 0 if dur > 3 else 1


if __name__ == "__main__":
    sys.exit(main())
