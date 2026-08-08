// Shells out to `gamma_hq.py --json` for the Gamma App's presence header.
// gamma_hq.py stays the ONE place that knows how to read this rig's state
// files and compute the 7-section view (state chip word, goal/focus, tape,
// right-now sentence, clocks, wants, recent ships) -- this bridge just runs
// it and parses stdout, so that logic is never re-derived in TypeScript.
// J rejected the terminal WINDOW as a presence surface (2026-08-08); this
// keeps the terminal's underlying DATA LOGIC as the shared source of truth
// for both the (deprecated-as-a-surface) terminal and the new web page.

import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { WORKSPACE_ROOT, paths } from "./workspace";
import type { PresenceView } from "./gamma-app-types";

const execFileAsync = promisify(execFile);

export async function fetchPresenceView(): Promise<PresenceView | null> {
  try {
    const { stdout } = await execFileAsync(paths.pythonExe, [paths.gammaHqScript, "--json"], {
      cwd: WORKSPACE_ROOT,
      timeout: 15_000,
      windowsHide: true,
      maxBuffer: 2_000_000,
    });
    const parsed = JSON.parse(stdout) as PresenceView & { error?: string };
    if (parsed.error) return null; // gamma_hq.py's own fail-open JSON error shape
    return parsed;
  } catch {
    // venv missing, script error, timeout, or non-JSON stdout -- the rest of
    // the Gamma App still renders fine without the presence header (fail-open).
    return null;
  }
}
