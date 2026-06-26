"use strict";

// Loads the OpenAI API key for the Realtime voice. Mirrors the .openrouter.key
// pattern: env var override, else the gitignored key file. The key NEVER reaches
// the browser -- it's only used server-side to mint a short-lived ephemeral token.

const fs = require("fs");
const path = require("path");

function keyPath(root) {
  return path.join(root, "automation", "state", ".openai.key");
}

function loadOpenAIKey(root) {
  const env = (process.env.OPENAI_API_KEY || "").trim();
  if (env.startsWith("sk-")) return env;
  try {
    const raw = fs.readFileSync(keyPath(root), "utf8");
    const first = raw.split(/\r?\n/).map((s) => s.trim()).find(Boolean) || "";
    if (first.startsWith("sk-")) return first;
  } catch {
    /* not configured yet */
  }
  return null;
}

module.exports = { loadOpenAIKey, keyPath };
