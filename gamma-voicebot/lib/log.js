"use strict";

// Tiny logger: timestamped lines to stdout AND automation/state/logs/voice-bot.log,
// so J can always read what the bot did independent of the console (OP-33c).
// Best-effort file writes -- a logging error must never take the bot down.

const fs = require("fs");
const path = require("path");

function makeLogger(root) {
  const logDir = path.join(root, "automation", "state", "logs");
  const logFile = path.join(logDir, "voice-bot.log");
  try {
    fs.mkdirSync(logDir, { recursive: true });
  } catch {
    /* best effort */
  }
  return function log(msg) {
    const line = new Date().toISOString() + " " + msg + "\n";
    try {
      process.stdout.write("[voice-bot] " + line);
    } catch {
      /* stdout may be gone under a headless host */
    }
    try {
      fs.appendFileSync(logFile, line);
    } catch {
      /* best effort */
    }
  };
}

module.exports = { makeLogger };
