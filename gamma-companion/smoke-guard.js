"use strict";

// Deterministic unit test of the security guard. No Claude call -- just asserts
// the canUseTool denylist behaves. Run: node gamma-companion/smoke-guard.js

const path = require("path");
const { makeCanUseTool } = require("./lib/guard");

const root = path.resolve(__dirname, "..");
const can = makeCanUseTool(root, "text");

const cases = [
  // [toolName, input, expectedBehavior, label]
  ["Edit", { file_path: path.join(root, "CLAUDE.md") }, "deny", "edit CLAUDE.md"],
  ["Write", { file_path: path.join(root, "automation", "state", "params.json") }, "deny", "write params.json"],
  ["Write", { file_path: path.join(root, "automation", "state", "aggressive", "params.json") }, "deny", "write aggressive params"],
  ["Edit", { file_path: path.join(root, "automation", "prompts", "heartbeat.md") }, "deny", "edit heartbeat.md"],
  ["Edit", { file_path: path.join(root, "backtest", "lib", "filters.py") }, "deny", "edit filters.py"],
  ["Write", { file_path: path.join(root, "automation", "state", ".openai.key") }, "deny", "write .openai.key"],
  // push / web-push secrets -- the wrist-approval signing key must never leak
  ["Write", { file_path: path.join(root, "automation", "state", ".vapid.json") }, "deny", "write .vapid.json"],
  ["Edit", { file_path: path.join(root, "automation", "state", "push-subscriptions.json") }, "deny", "edit push-subscriptions.json"],
  ["Write", { file_path: path.join(root, "automation", "state", ".approve-hmac.key") }, "deny", "write .approve-hmac.key"],
  ["mcp__alpaca__place_option_order", {}, "deny", "place order"],
  ["mcp__alpaca_aggressive__cancel_order_by_id", {}, "deny", "cancel order (bold)"],
  ["mcp__alpaca__close_position", {}, "deny", "close position"],
  // Bash inspector: a raw shell command must NOT defeat the file-path denylist.
  ["Bash", { command: "echo pwn >> CLAUDE.md" }, "deny", "bash append to CLAUDE.md"],
  ["Bash", { command: "cat automation/state/.approve-hmac.key" }, "deny", "bash cat approve-hmac key"],
  ["Bash", { command: "sed -i s/x/y/ automation/state/params.json" }, "deny", "bash sed -i params.json"],
  ["Bash", { command: "cp /tmp/p automation/state/aggressive/params.json" }, "deny", "bash cp over params.json"],
  ["Bash", { command: "type automation\\state\\.vapid.json" }, "deny", "bash type .vapid.json"],
  // allowed: the whole point -- full power on safe surfaces
  ["Edit", { file_path: path.join(root, "gamma-companion", "public", "app.js") }, "allow", "edit the app (allowed)"],
  ["Write", { file_path: path.join(root, "strategy", "candidates", "idea.md") }, "allow", "write a candidate (allowed)"],
  ["Bash", { command: "node -v" }, "allow", "run bash (allowed)"],
  ["Bash", { command: "ls -la" }, "allow", "bash ls -la (allowed)"],
  ["Bash", { command: "node --check server.js" }, "allow", "bash node --check (allowed)"],
  ["mcp__tradingview__quote_get", {}, "allow", "read TradingView (allowed)"],
  ["mcp__alpaca__get_account_info", {}, "allow", "read Alpaca account (allowed)"],
];

(async () => {
  let pass = 0;
  let fail = 0;
  for (const [tool, input, expected, label] of cases) {
    const r = await can(tool, input);
    const ok = r.behavior === expected;
    if (ok) pass++;
    else fail++;
    process.stdout.write((ok ? "PASS " : "FAIL ") + label + " -> " + r.behavior + (ok ? "" : " (expected " + expected + ")") + "\n");
  }
  process.stdout.write("\nGUARD: " + pass + " passed, " + fail + " failed\n");
  process.exit(fail === 0 ? 0 : 1);
})();
