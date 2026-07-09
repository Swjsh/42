"use strict";

// The audit trail J asked for: a clean, human-readable, TWO-SIDED transcript of
// every voice session -> automation/state/logs/voice-bot-transcript-{date}.md,
// so J can open one file and read exactly what he said and what Gamma said back.
// Also mirrors each turn into the shared companion-conversation.jsonl (the ONE
// cross-face transcript per GAMMA-VOICE.md) so the typed face and the voice share
// memory. Best-effort: a transcript write must NEVER take a session down.

const fs = require("fs");
const path = require("path");

// DST-correct ET via Node's ICU (America/New_York) -- NOT Bash TZ (the rig scar
// is about Bash returning UTC; Node's Intl is timezone-correct here).
function etParts(d) {
  const f = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).formatToParts(d);
  const g = (t) => (f.find((p) => p.type === t) || {}).value || "";
  return { date: `${g("year")}-${g("month")}-${g("day")}`, time: `${g("hour")}:${g("minute")}:${g("second")}` };
}

class Transcript {
  constructor(root, sessionId) {
    this.root = root;
    this.sessionId = sessionId;
    const { date } = etParts(new Date());
    this.file = path.join(root, "automation", "state", "logs", `voice-bot-transcript-${date}.md`);
    this.convo = path.join(root, "automation", "state", "companion-conversation.jsonl");
    this._ensureHeader(date);
  }

  _ensureHeader(date) {
    try {
      fs.mkdirSync(path.dirname(this.file), { recursive: true });
      if (!fs.existsSync(this.file)) {
        fs.writeFileSync(this.file, `# Gamma voice transcript — ${date} ET\n\n`);
      }
      const { time } = etParts(new Date());
      fs.appendFileSync(this.file, `\n## Session \`${this.sessionId}\` — started ${time} ET\n\n`);
    } catch {
      /* best effort */
    }
  }

  // role: 'J' | 'Gamma' | 'tool' | 'note'
  line(role, text) {
    const t = String(text || "").trim();
    if (!t) return;
    const { time } = etParts(new Date());
    try {
      fs.appendFileSync(this.file, `- \`${time}\` **${role}:** ${t}\n`);
    } catch {
      /* best effort */
    }
    // Mirror real conversation turns (J / Gamma) into the shared cross-face log.
    if (role === "J" || role === "Gamma") {
      try {
        fs.appendFileSync(
          this.convo,
          JSON.stringify({
            ts: new Date().toISOString(),
            channel: "voice",
            role: role === "Gamma" ? "gamma" : "user",
            text: t.slice(0, 600),
          }) + "\n"
        );
      } catch {
        /* best effort */
      }
    }
  }

  close(reason, seconds, usage) {
    const { time } = etParts(new Date());
    try {
      fs.appendFileSync(
        this.file,
        `\n_— session ended ${time} ET (${reason}), ${seconds}s, tokens in/out ` +
          `${(usage && usage.input_tokens) || 0}/${(usage && usage.output_tokens) || 0} —_\n`
      );
    } catch {
      /* best effort */
    }
  }
}

module.exports = { Transcript };
