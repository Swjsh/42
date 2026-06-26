"use strict";
// Debug-only: boot the companion server on a separate port so the preview tool
// can attach a real browser (the Electron app holds 4317). Not used in prod.
process.env.GAMMA_COMPANION_PORT = "4319";
require("./server.js");
