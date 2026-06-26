"use strict";

// Drops two clearly-labelled DEMO approvals into the queue so you can feel the
// Approve/Reject loop end-to-end. Clicking a button removes the item and logs a
// line to automation/state/companion-decisions.jsonl.
//   node gamma-companion/seed-demo.js

const fs = require("fs");
const path = require("path");
const { approvalsPath } = require("./lib/approvals");

const root = process.env.GAMMA_WORKSPACE || path.resolve(__dirname, "..");
const now = new Date().toISOString();

const demo = {
  schema: "gamma-companion-approvals@1",
  updated_at: now,
  pending: [
    {
      id: "demo-ship-vwap",
      severity: "info",
      title: "Ship VWAP-continuation v2 live?",
      detail:
        "DEMO — OOS+ · WF 0.74 · anchors no-regression. Approve appends to companion-decisions.jsonl.",
      created_at: now,
    },
    {
      id: "demo-bold-drawdown",
      severity: "warn",
      title: "Bold down 18% on the day — keep trading?",
      detail: "DEMO — kill-switch trips at 50%. Your call to continue or stand down.",
      created_at: now,
    },
  ],
};

fs.writeFileSync(approvalsPath(root), JSON.stringify(demo, null, 2));
process.stdout.write("Seeded 2 demo approvals. Open the companion and click Approve / Not yet.\n");
