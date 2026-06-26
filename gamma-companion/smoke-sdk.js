"use strict";

// Verifies the official Claude Agent SDK escalation path end-to-end:
// dynamic ESM import + bypassPermissions + model selection + result capture.
//   node gamma-companion/smoke-sdk.js

(async () => {
  const { query } = await import("@anthropic-ai/claude-agent-sdk");
  let got = "";
  for await (const m of query({
    prompt: "Reply with exactly the single token: SDK_READY",
    options: {
      model: "claude-sonnet-4-6",
      permissionMode: "bypassPermissions",
      cwd: __dirname,
    },
  })) {
    if (m.type === "result") got = (m.subtype || "") + " | " + (m.result || "");
  }
  process.stdout.write("SMOKE: " + got + "\n");
})().catch((e) => {
  process.stdout.write("SMOKE_ERR: " + ((e && e.message) || e) + "\n");
  process.exit(1);
});
