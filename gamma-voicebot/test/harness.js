"use strict";

// OP-33 verification harness -- proves the seams WITHOUT needing J in a voice
// channel:
//   node test/harness.js             -> run the 3 tools directly against real state,
//                                       build the persona (prints everything)
//   node test/harness.js --realtime  -> ALSO mint an ephemeral token, open a real
//                                       Realtime WS session (logs the session id),
//                                       ask a state question BY TEXT, verify the
//                                       model calls a tool and answers from it,
//                                       verify the usage row lands.
// Exit 0 only when every step passed.

const fs = require("fs");
const path = require("path");

const config = require("../lib/config");
const { toolSchemas, runTool } = require("../lib/tools");
const { buildInstructions } = require("../lib/persona");
const { RealtimeSession } = require("../lib/realtime");

const REALTIME = process.argv.includes("--realtime");
const cfg = config.load();
const out = (s) => process.stdout.write(s + "\n");

let failures = 0;
function check(name, ok, detail) {
  out((ok ? "PASS" : "FAIL") + "  " + name + (detail ? " -- " + detail : ""));
  if (!ok) failures += 1;
}

async function main() {
  out("root=" + cfg.root);
  out("model=" + cfg.model);
  out("openai_key_present=" + !!cfg.openaiKey);
  out("tools=" + toolSchemas.map((t) => t.name).join(","));
  out("");

  // 1) the three tools, straight against real state
  for (const t of toolSchemas) {
    const started = Date.now();
    const res = await runTool(cfg.root, t.name);
    const ok = typeof res === "string" && res.length > 0 && !/^(engine_state|funnel_today|evening_debrief) ERROR/.test(res);
    check("tool:" + t.name, ok, (Date.now() - started) + "ms");
    out("  " + String(res).slice(0, 700).replace(/\n/g, "\n  "));
    out("");
  }

  // 2) persona
  const instructions = buildInstructions(cfg.root);
  check("persona_build", instructions.length > 400 && /Gamma/.test(instructions), instructions.length + " chars");
  out("  persona head: " + instructions.slice(0, 200).replace(/\n/g, " / "));
  out("");

  // 3) full realtime session (text-driven; costs ~a cent, metered like any session)
  if (REALTIME) {
    if (!cfg.openaiKey) {
      check("realtime_session", false, "no OpenAI key");
    } else {
      await realtimeSmoke(instructions);
    }
  }

  out("");
  out(failures === 0 ? "HARNESS: ALL PASS" : "HARNESS: " + failures + " FAILURE(S)");
  process.exit(failures === 0 ? 0 : 1);
}

function usageFile() {
  return path.join(cfg.root, "automation", "state", "voice-bot-usage.jsonl");
}

async function realtimeSmoke(instructions) {
  const usageLinesBefore = fs.existsSync(usageFile())
    ? fs.readFileSync(usageFile(), "utf8").split(/\r?\n/).filter(Boolean).length
    : 0;

  let sessionId = null;
  let toolCalled = false;
  let transcript = "";
  let settled = false;

  await new Promise((resolve) => {
    const finish = () => {
      if (!settled) {
        settled = true;
        resolve();
      }
    };
    const session = new RealtimeSession({
      root: cfg.root,
      key: cfg.openaiKey,
      model: cfg.model,
      instructions,
      tools: toolSchemas,
      origin: "harness",
      log: (m) => {
        out("  [session] " + m);
        if (/^tool call:/.test(m)) toolCalled = true;
      },
      onReady: (id) => {
        sessionId = id;
        session.sendUserText(
          "What is the engine state right now? Answer in one or two spoken sentences."
        );
      },
      onTranscript: (t) => {
        // The persona says "one sec" BEFORE a tool call -- so the first
        // transcript may be the preamble. Only finish once a tool ran and the
        // model spoke AFTER it (the real answer).
        transcript = t;
        if (toolCalled) session.stop("harness_done");
      },
      onEnd: finish,
    });
    session.start().catch((e) => {
      out("  [session] start failed: " + e.message);
      finish();
    });
    setTimeout(() => {
      session.stop("harness_timeout");
      finish();
    }, 90000);
  });

  check("realtime_session_opened", !!sessionId, "session_id=" + sessionId);
  check("realtime_tool_called", toolCalled, "model invoked a tool for a state question");
  check("realtime_answer_spoken", transcript.length > 0, JSON.stringify(transcript.slice(0, 220)));

  const usageLinesAfter = fs.existsSync(usageFile())
    ? fs.readFileSync(usageFile(), "utf8").split(/\r?\n/).filter(Boolean).length
    : 0;
  check("usage_row_written", usageLinesAfter === usageLinesBefore + 1, usageFile());
  if (usageLinesAfter > 0) {
    const last = fs.readFileSync(usageFile(), "utf8").trim().split(/\r?\n/).pop();
    out("  usage row: " + last);
  }
}

main().catch((e) => {
  out("HARNESS CRASH: " + (e && e.stack ? e.stack : e));
  process.exit(1);
});
