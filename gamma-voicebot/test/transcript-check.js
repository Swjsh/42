"use strict";
// Standalone proof the two-sided transcript file writes cleanly (J can't be the
// first to find a bug in his own audit file). Run: node test/transcript-check.js
const fs = require("fs");
const path = require("path");
const { Transcript } = require("../lib/transcript");

const root = process.env.GAMMA_WORKSPACE || path.resolve(__dirname, "..", "..");
const t = new Transcript(root, "sess_selftest_ABC");
t.line("J", "hey gamma what did we do today");
t.line("Gamma", "We stayed flat -- rules blocked the entries, no fills.");
t.close("selftest", 12, { input_tokens: 1200, output_tokens: 64 });

const parts = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
}).formatToParts(new Date());
const g = (x) => parts.find((p) => p.type === x).value;
const file = path.join(root, "automation", "state", "logs", `voice-bot-transcript-${g("year")}-${g("month")}-${g("day")}.md`);
const body = fs.readFileSync(file, "utf8");
const section = body.split("sess_selftest_ABC")[1] || "(section not found)";
process.stdout.write("FILE: " + file + "\n----\n## Session `sess_selftest_ABC" + section + "----\n");
process.stdout.write(/\*\*J:\*\*/.test(body) && /\*\*Gamma:\*\*/.test(body) ? "TWO_SIDED_OK\n" : "MISSING A SIDE\n");
