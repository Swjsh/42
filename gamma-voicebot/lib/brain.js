"use strict";

// Stage 2: the "ask Claude" catch-all. When the voice model hits a question none
// of the read-only STATE tools cover (repo internals, doctrine, params values,
// strategy/lesson detail, "why/how does X work", kitchen history/frequency), it
// calls ask_gamma_brain -> here. We spawn a FAST, READ-ONLY Claude via the Agent
// SDK query() with cwd = repo root, so it can Read/Grep/Glob all of Chief and
// return a short spoken answer.
//
// Same subscription-auth pattern as gamma-companion/lib/escalate.js: NO apiKey is
// set, so the SDK uses J's Claude Code Max login ($0 per query). DIFFERENCES for
// voice, all deliberate:
//   (1) FAST model (haiku) + low maxTurns + a hard ~50s wall-clock, because a
//       voice caller is waiting in real time -- this is a quick lookup, not a build.
//   (2) STRICTLY read-only -- only Read/Grep/Glob are allowed; every other tool
//       (Write/Edit/Bash/order tools/MCP) is denied at the guard. The voice face
//       answers, it never acts.
//   (3) Never throws -- on any failure/timeout it returns a plain sentence the
//       voice model can speak, including the offer to run it as a full background job.

const VOICE_BRAIN_SOUL =
  "You are Gamma's brain, answering a question J just asked OUT LOUD over a Discord voice call. " +
  "Read whatever repo files you need (you're at the repo root) to answer ACCURATELY from the real " +
  "current tree -- never guess. Then reply in ONE to THREE short SPOKEN sentences: plain text, no " +
  "markdown, no bullet points, no code blocks, and don't read file paths aloud -- a text-to-speech " +
  "voice will speak your words, so write what a person would say. Lead with the answer, round " +
  "numbers. If you genuinely can't find it, say so in one sentence. You are READ-ONLY -- you cannot " +
  "change anything.";

// Only file read/search tools. Everything else is denied -> the voice brain
// answers, never acts. (Defense-in-depth: even though we prompt read-only, the
// guard makes a write/order structurally impossible from the voice face.)
const READ_ONLY_TOOLS = new Set(["Read", "Grep", "Glob"]);

async function canUseTool(name, input) {
  if (READ_ONLY_TOOLS.has(name)) return { behavior: "allow", updatedInput: input };
  return { behavior: "deny", message: "voice brain is read-only (" + name + " blocked)" };
}

// Returns a short spoken-answer string. NEVER throws.
async function askGammaBrain(root, question, opts) {
  const q = String(question || "").trim();
  if (!q) return "I didn't catch the question -- say it again?";
  const timeoutMs = (opts && opts.timeoutMs) || 50000;
  const model = (opts && opts.model) || "claude-haiku-4-5";
  const log = (opts && opts.log) || (() => {});

  let query;
  try {
    ({ query } = await import("@anthropic-ai/claude-agent-sdk"));
  } catch (e) {
    log("brain: SDK import failed: " + e.message);
    return "My deeper brain isn't wired up right now -- ask me again in a bit.";
  }

  const ac = new AbortController();
  let timedOut = false;
  const killer = setTimeout(() => {
    timedOut = true;
    try { ac.abort(); } catch { /* already gone */ }
  }, timeoutMs);

  const started = Date.now();
  let answer = "";
  try {
    for await (const m of query({
      prompt: q,
      options: {
        model,
        cwd: root,
        // claude_code preset = the real agent; append = the voice register + the
        // read-only boundary as SYSTEM prompt. settingSources:['project'] loads
        // CLAUDE.md (the soul) from cwd. NO apiKey -> J's Max login ($0/query).
        systemPrompt: { type: "preset", preset: "claude_code", append: VOICE_BRAIN_SOUL },
        settingSources: ["project"],
        maxTurns: 8,
        canUseTool,
        abortController: ac,
      },
    })) {
      if (m.type === "result") answer = String(m.result || "").trim();
    }
  } catch (e) {
    clearTimeout(killer);
    if (timedOut) {
      log("brain: timed out after " + timeoutMs + "ms on: " + q.slice(0, 80));
      return "That one's going deep and I can't get it in the time I've got on voice. Want me to run it as a full background job and message you when it's done?";
    }
    log("brain: error: " + ((e && e.message) || e));
    return "I hit a snag reaching my deeper brain on that one -- try again, or ask me through the companion.";
  }
  clearTimeout(killer);
  log("brain: answered in " + (Date.now() - started) + "ms (" + answer.length + " chars) for: " + q.slice(0, 80));
  if (!answer) return "I looked but couldn't pin that down from here -- want me to run it as a full background job?";
  return answer;
}

module.exports = { askGammaBrain };
