import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";
import {
  type PersonasBoard,
  collectScout,
  collectCoach,
  collectPilot,
  collectAnalyst,
  collectChef,
  collectTreasurer,
  collectGammaManager,
  computeHandoffs,
  getScheduledTaskStatus,
  getPendingWork,
} from "@/lib/personas";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const ROOT = path.join(process.cwd(), "..");

async function readText(p: string, maxBytes = 32 * 1024): Promise<string | null> {
  try {
    const buf = await fs.readFile(p);
    if (buf.length <= maxBytes) return buf.toString("utf8");
    return buf.subarray(buf.length - maxBytes).toString("utf8") + "\n[truncated]";
  } catch { return null; }
}

function todayET(): string {
  const now = new Date();
  const et = new Date(now.toLocaleString("en-US", { timeZone: "America/New_York" }));
  const y = et.getFullYear();
  const m = String(et.getMonth() + 1).padStart(2, "0");
  const d = String(et.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/**
 * GET /api/personas -- unchanged response shape (2026-09-13 refactor moved
 * every collector + computeHandoffs() into dashboard/lib/personas.ts so
 * /api/hq's Company Mode can reuse them without duplicating the logic; this
 * route now just imports and composes them exactly as it always did).
 */
export async function GET() {
  const errors: string[] = [];
  const board: PersonasBoard = {
    generatedAt: new Date().toISOString(),
    todayET: todayET(),
    personas: [],
    handoffs: [],
    scheduledTasks: { auditHealth: "UNKNOWN", activeCount: 0, flagCount: 0, nextFires: [] },
    status: { tail: "" },
    pendingWork: { chefInbox: [], chefCandidates: [], treasuryDrafts: { exists: false, mtimeISO: null, preview: null }, mistakesTail: null },
    errors,
  };

  try {
    const [scout, coach, pilot, analyst, chef, treasurer, gamma] = await Promise.all([
      collectScout(), collectCoach(), collectPilot(), collectAnalyst(),
      collectChef(), collectTreasurer(), collectGammaManager(),
    ]);
    board.personas = [gamma, scout, coach, pilot, analyst, chef, treasurer];
  } catch (e) { errors.push(`personas: ${e instanceof Error ? e.message : String(e)}`); }

  try { board.handoffs = await computeHandoffs(); } catch (e) { errors.push(`handoffs: ${e instanceof Error ? e.message : String(e)}`); }
  try { board.scheduledTasks = await getScheduledTaskStatus(); } catch (e) { errors.push(`schedule: ${e instanceof Error ? e.message : String(e)}`); }
  try { board.pendingWork = await getPendingWork(); } catch (e) { errors.push(`pending: ${e instanceof Error ? e.message : String(e)}`); }

  try {
    const statusMd = await readText(path.join(ROOT, "automation/overnight/STATUS.md"), 6000);
    board.status.tail = statusMd ? statusMd.split("\n").slice(-40).join("\n") : "";
  } catch (e) { errors.push(`status: ${e instanceof Error ? e.message : String(e)}`); }

  return NextResponse.json(board, { headers: { "Cache-Control": "no-store" } });
}
