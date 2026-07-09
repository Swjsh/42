"use strict";

// The cost meter (Groq scar: meter BEFORE trusting "cheap"). One JSONL row per
// Realtime session into automation/state/voice-bot-usage.jsonl so spend_summary
// can price voice later. Includes the model's own token usage totals (accumulated
// from response.done events) -- wall-seconds alone can't price a Realtime session.

const fs = require("fs");
const path = require("path");

function appendUsage(root, row) {
  try {
    const file = path.join(root, "automation", "state", "voice-bot-usage.jsonl");
    fs.appendFileSync(file, JSON.stringify(row) + "\n");
    return true;
  } catch {
    return false; // never let the meter take a session down; caller logs the miss
  }
}

module.exports = { appendUsage };
