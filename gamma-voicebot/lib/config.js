"use strict";

// Config for the Gamma voice bot. Every credential comes from the same
// gitignored homes the rest of the rig uses -- NOTHING here is hardcoded:
//   Discord bot token + HQ channel/guild + J's user id -> automation/state/.discord-config.json
//   OpenAI key -> gamma-companion/lib/openai_key.js (env OPENAI_API_KEY, else
//                 automation/state/.openai.key) -- literal reuse of the companion loader.
// Non-secret knobs (voice channel pin, model, idle timeout) come from the optional
// automation/state/voice-bot-config.json so J can retune without touching code.

const fs = require("fs");
const path = require("path");

const ROOT = process.env.GAMMA_WORKSPACE || path.resolve(__dirname, "..", "..");
const STATE = (...p) => path.join(ROOT, "automation", "state", ...p);

// Verified live against the key's /v1/models catalog 2026-07-08 -- the current
// realtime-mini-class slug. Override via voice-bot-config.json or env.
const DEFAULT_MODEL = "gpt-realtime-2.1-mini";
const DEFAULT_IDLE_TIMEOUT_MS = 5 * 60 * 1000; // auto-leave is mandatory: an open session runs a paid meter

function readJson(file) {
  // utf-8-sig tolerance: PowerShell Out-File prepends a BOM (same trap the
  // Python bridge guards against with encoding="utf-8-sig").
  const raw = fs.readFileSync(file, "utf8").replace(/^﻿/, "");
  return JSON.parse(raw);
}

function loadDiscordConfig() {
  const file = STATE(".discord-config.json");
  let cfg;
  try {
    cfg = readJson(file);
  } catch (e) {
    throw new Error("cannot read " + file + " -- the bridge config is the bot's credential source: " + e.message);
  }
  for (const k of ["bot_token", "channel_id", "guild_id", "user_id"]) {
    if (!cfg[k]) throw new Error(file + " is missing required field '" + k + "'");
  }
  return cfg;
}

function loadBotConfig() {
  try {
    return readJson(STATE("voice-bot-config.json"));
  } catch {
    return {}; // optional file -- defaults apply
  }
}

function loadOpenAIKey() {
  // Literal reuse of the companion's loader (env override, else gitignored key
  // file; key never leaves the server side). Inline fallback keeps the bot
  // standalone if the companion tree is absent -- same mechanism either way.
  try {
    const loader = require(path.join(ROOT, "gamma-companion", "lib", "openai_key.js"));
    return loader.loadOpenAIKey(ROOT);
  } catch {
    const env = (process.env.OPENAI_API_KEY || "").trim();
    if (env.startsWith("sk-")) return env;
    try {
      const raw = fs.readFileSync(STATE(".openai.key"), "utf8");
      const first = raw.split(/\r?\n/).map((s) => s.trim()).find(Boolean) || "";
      if (first.startsWith("sk-")) return first;
    } catch {
      /* not configured */
    }
    return null;
  }
}

function load() {
  const discord = loadDiscordConfig();
  const bot = loadBotConfig();
  const openaiKey = loadOpenAIKey();
  return {
    root: ROOT,
    discord,
    openaiKey,
    model: (process.env.GAMMA_VOICE_MODEL || bot.model || DEFAULT_MODEL).trim(),
    // Voice channel: pinned in voice-bot-config.json when present; otherwise the
    // bot auto-discovers the guild's first voice channel at startup (logged).
    voiceChannelId: bot.voice_channel_id || null,
    idleTimeoutMs: Number(bot.idle_timeout_ms) > 0 ? Number(bot.idle_timeout_ms) : DEFAULT_IDLE_TIMEOUT_MS,
  };
}

module.exports = { load, ROOT, STATE };
