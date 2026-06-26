# _INTEGRATION-soul.md — wiring the one Gamma voice into the companion

> **What this is.** A wiring contract, not a persona. The canonical Gamma persona is
> [`automation/presence/GAMMA-VOICE.md`](../../automation/presence/GAMMA-VOICE.md) (the parent soul) with
> [`automation/presence/SOUL.md`](../../automation/presence/SOUL.md) as the trade-tape register. The companion's
> two talking faces — the free FACE brain and the realtime VOICE — must both speak as that one Gamma. This file
> documents exactly where each face pulls the soul from, so the brain and the mouth never drift into two
> different personalities. **This is a proposal for J — it does NOT edit `face_brain.py` or `server.js`.**

---

## The two injection points

| Face | File | How it loads the soul | What it gets |
|---|---|---|---|
| **FACE brain** (free, $0, the real Gamma) | `face/face_brain.py` | `GAMMA-VOICE.md` loaded as the **SYSTEM** prompt (whole file, or the persona body) | Full persona: identity, voice, 3-tier boundary, hard limits |
| **VOICE** (gpt-realtime-2, thin mouth) | `server.js#/api/realtime-token` → `sessionConfig.session.instructions` | the **HEAD** of `GAMMA-VOICE.md` injected (down through "The hard limits") | Identity + voice + limits, compact enough for a realtime preamble |

The asymmetry is deliberate. The **FACE brain is the genuine Gamma** — it reads live state and decides everything, so it gets the *full* soul as SYSTEM. The **VOICE is a thin mouth** that forwards every real turn to the brain via the `ask_gamma` tool — so it only needs the *head* of the soul (who Gamma is, the voice, the limits) to (a) sound like Gamma on filler/acknowledgement turns and (b) refuse anything that obviously violates a hard limit before it even reaches the brain. The VOICE must never improvise trading numbers; the brain (reading state) is the only source of facts.

---

## FACE brain — load `GAMMA-VOICE.md` as SYSTEM (proposed)

Today `face/face_brain.py` hardcodes the persona in the `SYSTEM` string constant (line ~46). The proposed change makes the file the source of truth so the brain and the doctrine can never drift:

```python
# proposed — replaces the hardcoded SYSTEM constant
from pathlib import Path

_VOICE = Path(__file__).resolve().parents[2] / "automation" / "presence" / "GAMMA-VOICE.md"

def _load_soul() -> str:
    try:
        return _VOICE.read_text(encoding="utf-8")
    except Exception:
        return _SYSTEM_FALLBACK  # keep the current inline string as a fallback constant

# The runtime contract the brain needs on top of the persona (escalation format,
# state-reading) is appended to the loaded soul so behaviour is unchanged:
SYSTEM = _load_soul() + "\n\n" + _BRAIN_RUNTIME_CONTRACT
```

`_BRAIN_RUNTIME_CONTRACT` keeps the existing operational instructions that are NOT persona — i.e. the three behaviours already in the current SYSTEM string:
- **Tier 1 (TALK):** answer from the live state block, plain text, 2–4 sentences, end with a proactive next-step.
- **Tier 2 (ESCALATE):** emit the fenced ```escalate {"model":"opus"|"sonnet","task":"…"}``` block exactly as `parse_escalation()` expects; "opus" for reasoning/strategy, "sonnet" for coding/edits.
- **Tier 3 (VETO):** never trade, never edit live doctrine/params, never claim unverified work — refuse in-voice with the one-line reason.

Net effect: the *persona* comes from `GAMMA-VOICE.md` (one edit point, shared with every other face); the *escalation mechanics* stay in code where `parse_escalation()` can rely on them. Keep `_SYSTEM_FALLBACK` so the brain still boots if the file is ever missing (fail-safe, never silent — log the fallback).

---

## VOICE — inject the soul head into realtime instructions (proposed)

Today `server.js#/api/realtime-token` hardcodes a one-paragraph `instructions` string (line ~284). The proposed change reads the HEAD of `GAMMA-VOICE.md` and prepends it, so the spoken Gamma and the typed Gamma are the same character:

```js
// proposed — near the top of /api/realtime-token
const fs = require("fs");
const path = require("path");

function loadVoiceHead(root) {
  try {
    const md = fs.readFileSync(
      path.join(root, "automation", "presence", "GAMMA-VOICE.md"), "utf8"
    );
    // take everything down through the "## The hard limits" section — identity+voice+limits,
    // small enough for a realtime preamble; drop the deep builder/architecture sections.
    const cut = md.indexOf("\n## The identity of a thing that builds itself");
    return (cut > 0 ? md.slice(0, cut) : md).trim();
  } catch {
    return ""; // fall through to the existing inline string
  }
}

const soulHead = loadVoiceHead(ROOT);
const REALTIME_RUNTIME = "You are SPEAKING OUT LOUD. For ANY request about the system, " +
  "live data, status, analysis, coding, or any real work, call the ask_gamma tool and speak " +
  "its answer concisely in your own warm voice. Never invent trading numbers. If a tool call " +
  "takes a moment, say a short 'one sec' ONCE then wait silently. After answering, offer one " +
  "useful next step.";

const instructions = (soulHead ? soulHead + "\n\n---\n\n" : "") + REALTIME_RUNTIME;
// ...sessionConfig.session.instructions = instructions;
```

The `REALTIME_RUNTIME` tail keeps the realtime-specific mechanics that are NOT persona (forced `ask_gamma` tool every real turn, the "one sec" filler rule, never-invent-numbers reinforced at the mouth). The persona HEAD makes the voice *sound* like Gamma; the tail makes it *behave* like a thin mouth over the brain.

---

## Why both faces stay one Gamma

- **Single source of truth:** edit `GAMMA-VOICE.md` once → both the typed brain and the spoken mouth update. No persona copy-paste, no drift.
- **Same boundary everywhere:** the 3-tier talk/escalate/veto and the 5 hard limits are identical across faces because they come from the same file. The VOICE enforces them as a pre-filter; the FACE brain enforces them as the decision-maker; the conductor enforces them as the auto-shipper.
- **Fail-safe, never silent:** if the soul file can't be read, each face falls back to its existing inline string and logs it — Gamma still talks, and the drift is visible, not hidden.
- **No new powers:** this wiring changes only *where the words come from*. It grants no tool, touches no doctrine, places no order. The guard (`guard.js`), the inflight cap, and the market-hours defer all sit downstream of the mouth and are untouched.

**Open item for J:** approve swapping the hardcoded persona strings in `face_brain.py` and `server.js` for the file-loaded soul above. Until then, `GAMMA-VOICE.md` is the canonical text and these two faces should be kept hand-synced to its head.
