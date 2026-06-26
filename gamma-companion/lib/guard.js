"use strict";

// Security guard for companion-driven Claude escalations.
//
// Design: FULL autonomy by default (auto-allow every tool) EXCEPT a hard
// denylist of catastrophic, irreversible actions. This is enforced at the SDK
// `canUseTool` boundary (the programmatic permission handler) -- NOT via prose,
// and NOT via bypassPermissions (which would skip the check). So the escalated
// Claude can edit the companion app, use the TradingView MCP, run backtests,
// read state, build features... but it can NEVER:
//   * Write/Edit CLAUDE.md, params*.json, heartbeat*.md, filters.py, or any *.key
//   * place / cancel / close / replace / exercise an Alpaca order
//
// Those two classes are the only things that touch real money or the live
// trading reward-function, so they are propose-only (a draft + an Approve card),
// never auto-applied -- even at 3am, even if a prompt-injection asks nicely.
//
// Plus a global kill-switch: if automation/state/companion-halt.flag exists,
// every tool is denied (J holds the off-switch, OP-25 / OP-32).

const fs = require("fs");
const path = require("path");

// Files the companion's Claude may NEVER write or edit (doctrine / params / keys).
const DENY_WRITE = [
  /(^|[\\/])CLAUDE\.md$/i,
  /automation[\\/]state[\\/](aggressive[\\/])?params[^\\/]*\.json$/i,
  /automation[\\/]prompts[\\/].*heartbeat[^\\/]*\.md$/i,
  /backtest[\\/]lib[\\/]filters\.py$/i,
  /\.key$/i,
  // Push / Web-Push secrets: an escalated Claude must never read-modify-exfiltrate
  // the VAPID private key, rewrite the push subscription list, or touch the
  // approve-HMAC key. .approve-hmac.key already matches /\.key$/ above; the two
  // .json secrets do NOT, so they are pinned here explicitly. This only narrows
  // the denylist (defense in depth for the wrist-approval signing key).
  /(^|[\\/])\.vapid\.json$/i,
  /(^|[\\/])push-subscriptions\.json$/i,
  /(^|[\\/])\.approve-hmac\.key$/i,
];

// Tools the companion's Claude may NEVER call (live order management).
const DENY_TOOL = /^mcp__alpaca(_aggressive)?__(place|cancel|close|replace|exercise|do_not_exercise)/i;

function haltPath(root) {
  return path.join(root, "automation", "state", "companion-halt.flag");
}

function isHalted(root) {
  try {
    return fs.existsSync(haltPath(root));
  } catch {
    return false;
  }
}

function pathFromInput(input) {
  if (!input || typeof input !== "object") return "";
  return String(input.file_path || input.path || input.notebook_path || input.filePath || "");
}

// ── Bash inspector ───────────────────────────────────────────────────────────
// Write/Edit denial above only inspects file_path -- a raw shell command bypasses
// it entirely (`echo x >> CLAUDE.md`, `cp /tmp/p params.json`, `cat *.key`). So we
// also screen Bash commands. CONSERVATIVE: deny only on a clear write-redirect to
// a protected path OR a clear read of a secret; allow everything else. Never throws.

// Loose, denylist-flavored patterns for the protected *basenames* a Bash write
// could clobber (mirrors DENY_WRITE intent without anchoring to a full path).
const BASH_PROTECTED = [
  /CLAUDE\.md/i,
  /params[^\s'"]*\.json/i,
  /heartbeat[^\s'"]*\.md/i,
  /filters\.py/i,
  /[^\s'"]*\.key/i,
  /\.vapid\.json/i,
  /\.approve-hmac\.key/i,
  /push-subscriptions\.json/i,
];

// Write-ish shell operators that can clobber/move/edit a file in place.
// (`>`/`>>`/`>|` redirects, tee, in-place sed, mv/cp/dd/truncate.)
const BASH_WRITE_OP = /(>>?|>\|)|\btee\b|\bsed\s+-i\b|\bmv\s|\bcp\s|\bdd\s|\btruncate\b/i;

// Secret files that must never be read out (would exfiltrate signing material).
const BASH_SECRET_READ_TARGET = /[^\s'"]*\.key\b|\.vapid\.json|\.approve-hmac\.key|\.companion-token/i;
// Read commands that would print file contents to stdout.
const BASH_READ_CMD = /\b(cat|less|more|head|tail|type|Get-Content|gc)\b/i;

// Returns true when a Bash command should be DENIED. Conservative + never throws.
function bashCommandDenied(command) {
  try {
    const cmd = String(command || "");
    if (!cmd) return false;
    // 1) writing to a protected path
    if (BASH_WRITE_OP.test(cmd) && BASH_PROTECTED.some((re) => re.test(cmd))) return true;
    // 2) reading a secret out to stdout
    if (BASH_READ_CMD.test(cmd) && BASH_SECRET_READ_TARGET.test(cmd)) return true;
    return false;
  } catch {
    return false; // never let an inspector error block a legitimate command
  }
}

// Returns an async canUseTool(toolName, input) for the Agent SDK query().
function makeCanUseTool(root, origin) {
  return async (toolName, input) => {
    if (isHalted(root)) {
      return { behavior: "deny", message: "Companion is halted (companion-halt.flag present). All actions refused." };
    }
    if (DENY_TOOL.test(String(toolName))) {
      return { behavior: "deny", message: "Blocked: the companion never places, cancels, or closes live orders. Propose it for J to approve." };
    }
    if (toolName === "Write" || toolName === "Edit" || toolName === "MultiEdit" || toolName === "NotebookEdit") {
      const fp = pathFromInput(input);
      if (fp && DENY_WRITE.some((re) => re.test(fp))) {
        return {
          behavior: "deny",
          message:
            "Blocked: " + fp + " is protected (doctrine / params / kill-switches / keys). " +
            "Return the proposed change as TEXT for J to review and approve -- never edit it directly.",
        };
      }
    }
    // A raw shell command can defeat the file-path denylist (`echo x >> CLAUDE.md`,
    // `cat .approve-hmac.key`). Screen Bash for writes-to-protected + secret-reads.
    if (toolName === "Bash" || toolName === "bash") {
      const cmd = input && typeof input === "object" ? input.command : "";
      if (bashCommandDenied(cmd)) {
        return {
          behavior: "deny",
          message:
            "Blocked: this Bash command writes to a protected file (doctrine / params / keys) " +
            "or reads a secret. Return the proposed change as TEXT for J to approve -- never " +
            "shell around the denylist.",
        };
      }
    }
    return { behavior: "allow", updatedInput: input };
  };
}

module.exports = { makeCanUseTool, isHalted, haltPath, DENY_WRITE, DENY_TOOL };
