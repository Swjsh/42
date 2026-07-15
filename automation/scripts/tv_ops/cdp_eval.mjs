// cdp_eval.mjs — direct-CDP fallback driver for tv_ops JS helpers when the TV MCP
// bridge is down (built 2026-07-15: post-reboot the MCP session link stayed dead while
// CDP 9222 was healthy; this drives the same page-JS helpers over raw CDP).
// Usage: node cdp_eval.mjs <helper.js> [KEY=VALUE ...]
//   Each KEY=VALUE replaces the literal placeholder KEY in the helper source with VALUE
//   (VALUE is inserted verbatim — pass '"abc"' for a JS string).
// Prints the helper's JSON return value to stdout.
import { readFileSync } from "node:fs";

const [helperPath, ...subs] = process.argv.slice(2);
if (!helperPath) { console.error("usage: node cdp_eval.mjs <helper.js> [PLACEHOLDER=value ...]"); process.exit(2); }

let expr = readFileSync(helperPath, "utf8");
for (const s of subs) {
  const i = s.indexOf("=");
  expr = expr.split(s.slice(0, i)).join(s.slice(i + 1));
}

const targets = await (await fetch("http://127.0.0.1:9222/json")).json();
const page = targets.find(t => t.type === "page" && /tradingview\.com\/chart/.test(t.url || ""))
          || targets.find(t => t.type === "page");
if (!page) { console.error(JSON.stringify({ success: false, error: "no_page_target" })); process.exit(1); }

const ws = new WebSocket(page.webSocketDebuggerUrl);
const result = await new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error("cdp_timeout_15s")), 15000);
  ws.onopen = () => ws.send(JSON.stringify({ id: 1, method: "Runtime.evaluate",
    params: { expression: expr, returnByValue: true, awaitPromise: true } }));
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id === 1) { clearTimeout(timer); resolve(msg.result); ws.close(); }
  };
  ws.onerror = (e) => { clearTimeout(timer); reject(new Error("ws_error")); };
});

if (result?.exceptionDetails) {
  console.log(JSON.stringify({ success: false, error: "page_exception", detail: result.exceptionDetails.text }));
} else {
  console.log(JSON.stringify(result?.result?.value ?? { success: false, error: "no_value" }));
}
