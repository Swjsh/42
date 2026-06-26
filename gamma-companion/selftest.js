"use strict";

// Verifies the data layer against the REAL state files, no server / no port.
//   node gamma-companion/selftest.js

const path = require("path");
const { buildState } = require("./lib/state");

const root = process.env.GAMMA_WORKSPACE || path.resolve(__dirname, "..");
const s = buildState(root);

const out = {
  verdict: s.verdict,
  market_open: s.market_open,
  speech: s.speech,
  accounts: s.accounts,
  kitchen: s.kitchen && {
    daemon_alive: s.kitchen.daemon_alive,
    pending: s.kitchen.pending,
    completed: s.kitchen.completed,
    cost_today: s.kitchen.cost_today,
  },
  approvals_pending: s.approvals.length,
  feed_count: s.feed.length,
  feed_preview: s.feed.slice(0, 3).map((f) => `${f.kind}: ${String(f.text).slice(0, 64)}`),
};

process.stdout.write(JSON.stringify(out, null, 2) + "\n");
