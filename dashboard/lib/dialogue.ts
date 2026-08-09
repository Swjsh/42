import { promises as fs } from "node:fs";
import path from "node:path";
import { WORKSPACE_ROOT } from "./workspace";

const DIALOGUE_PATH = path.join(WORKSPACE_ROOT, "automation", "state", "dashboard-dialogue.json");

// Speech older than this is not "what Gamma is saying right now" -- it's
// stale history from a prior session and must not be shown as current.
const MAX_SPEECH_AGE_MS = 24 * 60 * 60 * 1000;

// Real on-disk schema of automation/state/dashboard-dialogue.json (verified
// by reading the live file): top-level claude_status/claude_reasoning plus
// an `agents` map keyed by agent name, each with active/speech/last_active_at
// and occasional extra fields (side/account on entry_block_watch).
interface AgentEntry {
  active?: boolean;
  speech?: string | null;
  last_active_at?: string | null;
  side?: string;
  account?: string;
}

interface DialogueFile {
  last_update_et?: string;
  updated_at?: string;
  claude_status?: string;
  claude_reasoning?: string;
  agents?: Record<string, AgentEntry>;
  ticker_speech?: string | null;
}

export interface LatestSpeech {
  /** Which agent key (premarket/heartbeat/review/eod/entry_block_watch/...) said it. */
  agent: string;
  speech: string;
  lastActiveAt: string;
  side?: string;
  account?: string;
}

async function readJson<T>(p: string): Promise<T | null> {
  try {
    const raw = await fs.readFile(p, "utf-8");
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

/**
 * The single most-recently-active agent's real first-person speech from
 * automation/state/dashboard-dialogue.json -- "what Gamma is saying right
 * now". This is REAL production narration already written by the daily
 * personas (premarket/heartbeat/review/eod/entry_block_watch), not a
 * fabricated line.
 *
 * Fails open to null when: the file is missing/malformed, no agent carries a
 * non-empty speech string, or the freshest speech is older than 24h (stale
 * history must never be presented as current).
 */
export async function getLatestSpeech(): Promise<LatestSpeech | null> {
  const file = await readJson<DialogueFile>(DIALOGUE_PATH);
  if (!file || !file.agents || typeof file.agents !== "object") return null;

  let best: LatestSpeech | null = null;
  let bestMs = -Infinity;

  for (const [name, entry] of Object.entries(file.agents)) {
    if (!entry || typeof entry.speech !== "string" || !entry.speech.trim()) continue;
    if (!entry.last_active_at) continue;
    const ms = Date.parse(entry.last_active_at);
    if (!Number.isFinite(ms)) continue;
    if (ms > bestMs) {
      bestMs = ms;
      best = {
        agent: name,
        speech: entry.speech,
        lastActiveAt: entry.last_active_at,
        side: entry.side,
        account: entry.account,
      };
    }
  }

  if (!best) return null;
  if (Date.now() - bestMs > MAX_SPEECH_AGE_MS) return null;

  return best;
}
