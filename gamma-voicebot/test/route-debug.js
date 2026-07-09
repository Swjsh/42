"use strict";
// Focused single-question probe: open ONE realtime session, send a deep question,
// log EVERY event, exit after 60s. Run: VOICE_DEBUG=1 node test/route-debug.js "question"
const config = require("../lib/config");
const { buildInstructions } = require("../lib/persona");
const { toolSchemas } = require("../lib/tools");
const { RealtimeSession } = require("../lib/realtime");

const cfg = config.load();
const question = process.argv[2] || "What does operating principle sixteen say in our doctrine?";

const session = new RealtimeSession({
  root: cfg.root,
  key: cfg.openaiKey,
  model: cfg.model,
  instructions: buildInstructions(cfg.root),
  tools: toolSchemas,
  origin: "route-debug",
  log: (m) => process.stdout.write(m + "\n"),
  onReady: () => {
    process.stdout.write(">> sending: " + question + "\n");
    session.sendUserText(question + " Answer in one or two spoken sentences.");
  },
  onTranscript: (t) => process.stdout.write('ANSWER: "' + t + '"\n'),
  onEnd: () => process.exit(0),
});
session.start().catch((e) => { process.stdout.write("start failed: " + e.message + "\n"); process.exit(1); });
setTimeout(() => { session.stop("debug_timeout"); }, 60000);
