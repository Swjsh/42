import { NextResponse } from "next/server";
import { appendFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import { paths } from "@/lib/workspace";
import { nowEtStamp } from "@/lib/time";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const VALID_ACTIONS = new Set(["test", "kill", "ask"]);
const MAX_NOTE_LEN = 2000;

/**
 * POST /api/station/action { card_id, action, note? } -- the ONLY effect is
 * appending one JSON line to automation/state/station/station-inbox.jsonl.
 * setup/scripts/station_loop.py drains that file on its very next fire
 * (station_board.apply_inbox_actions) -- this route never touches the ideas
 * board itself, never calls an LLM, never places an order, never reads or
 * writes any credential file. Loopback-only by construction (the dashboard
 * process binds 127.0.0.1 -- see package.json's `start` script).
 */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid JSON body" }, { status: 400 });
  }

  if (!body || typeof body !== "object") {
    return NextResponse.json({ ok: false, error: "body must be an object" }, { status: 400 });
  }
  const { card_id, action, note } = body as Record<string, unknown>;

  if (typeof card_id !== "string" || !card_id.trim()) {
    return NextResponse.json({ ok: false, error: "card_id is required" }, { status: 400 });
  }
  if (typeof action !== "string" || !VALID_ACTIONS.has(action)) {
    return NextResponse.json(
      { ok: false, error: `action must be one of: ${[...VALID_ACTIONS].join(", ")}` },
      { status: 400 },
    );
  }
  const noteText = typeof note === "string" ? note.slice(0, MAX_NOTE_LEN) : "";

  const row = { ts_et: nowEtStamp(), card_id: card_id.trim(), action, note: noteText };

  try {
    await mkdir(dirname(paths.stationInbox), { recursive: true });
    await appendFile(paths.stationInbox, JSON.stringify(row) + "\n", "utf-8");
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: `failed to write station-inbox.jsonl: ${e instanceof Error ? e.message : String(e)}` },
      { status: 500 },
    );
  }

  return NextResponse.json({ ok: true, queued: row }, { headers: { "Cache-Control": "no-store" } });
}
