import { NextResponse } from "next/server";
import { appendFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import { paths } from "@/lib/workspace";
import { nowEtStamp } from "@/lib/time";
import { readStationConfig, readStationFactsText, readStationPersona } from "@/lib/station";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const MAX_MESSAGE_LEN = 4000;
const OLLAMA_TIMEOUT_MS = 60_000;

// Module-scope single-flight lock. Valid for the lifetime of this ONE `next
// start` process (exactly this deployment -- a single local dashboard, not a
// serverless/multi-instance target), which is what "one request at a time"
// means here: a second "Talk to Gamma" message while the first is still
// waiting on Ollama gets a 429, never a queued/silently-dropped duplicate
// call to the model.
let askInFlight = false;

interface OllamaChatResponse {
  message?: { content?: string };
  error?: string;
}

/**
 * POST /api/station/ask { message } -- "Talk to Gamma". Calls Ollama directly
 * (http://127.0.0.1:11434/api/chat, loopback only) with the Station persona
 * (readStationPersona() -- amendment 5a, 2026-09-13: automation/prompts/
 * station-identity.md + a plain-prose chat contract appended, DELIBERATELY
 * NOT station.md, which is the 30-min loop's JSON-only output contract and
 * would make Gamma answer J in raw JSON here) plus a fresh facts block
 * (shells out to `python station_facts.py --json` -- the simpler of the two
 * options offered, since station_facts.py already owns that gather/render
 * logic and this is an occasional per-message call, not a hot path).
 * think:false, 60s timeout.
 *
 * HARD RULES: no orders, no broker calls, no credential file is read here;
 * the model's reply is treated as INERT TEXT ONLY -- it is JSON-serialized
 * back to the client and rendered as a plain string (see app/station/page.tsx),
 * never eval'd, never used to construct a shell command or file path, never
 * given any tool/function-calling capability. Every turn is appended to
 * automation/state/station/chat-ledger.jsonl for the record.
 */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid JSON body" }, { status: 400 });
  }
  const message =
    body && typeof body === "object" && typeof (body as Record<string, unknown>).message === "string"
      ? ((body as Record<string, unknown>).message as string).trim().slice(0, MAX_MESSAGE_LEN)
      : "";
  if (!message) {
    return NextResponse.json({ ok: false, error: "message is required" }, { status: 400 });
  }

  if (askInFlight) {
    return NextResponse.json(
      { ok: false, error: "Gamma is still answering the last question -- one at a time." },
      { status: 429 },
    );
  }
  askInFlight = true;

  try {
    const [config, persona, factsText] = await Promise.all([
      readStationConfig(),
      readStationPersona(),
      readStationFactsText(),
    ]);
    const model = config.model || "gamma-planner-fast";
    const baseUrl = config.ollama_base_url || "http://127.0.0.1:11434";
    const facts = factsText ?? "(facts block unavailable this turn -- station_facts.py did not return one)";
    const userContent = `${facts}\n\nJ says: ${message}`;

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), OLLAMA_TIMEOUT_MS);
    let reply: string;
    try {
      const res = await fetch(`${baseUrl.replace(/\/$/, "")}/api/chat`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          model,
          messages: [
            { role: "system", content: persona },
            { role: "user", content: userContent },
          ],
          stream: false,
          think: false,
        }),
        signal: controller.signal,
      });
      if (!res.ok) {
        return NextResponse.json(
          { ok: false, error: `Ollama returned HTTP ${res.status}` },
          { status: 502 },
        );
      }
      const data = (await res.json()) as OllamaChatResponse;
      reply = data.message?.content?.trim() || "(Gamma had nothing to say)";
    } catch (e) {
      const timedOut = e instanceof Error && e.name === "AbortError";
      return NextResponse.json(
        { ok: false, error: timedOut ? "Ollama timed out after 60s" : "Ollama unreachable at " + baseUrl },
        { status: 502 },
      );
    } finally {
      clearTimeout(timer);
    }

    const ledgerRow = { ts_et: nowEtStamp(), message, reply, model };
    try {
      await mkdir(dirname(paths.chatLedger), { recursive: true });
      await appendFile(paths.chatLedger, JSON.stringify(ledgerRow) + "\n", "utf-8");
    } catch {
      // the ledger append is a nice-to-have record, never a reason to fail
      // a reply J is actively waiting on
    }

    return NextResponse.json(
      { ok: true, reply, model, ts_et: ledgerRow.ts_et },
      { headers: { "Cache-Control": "no-store" } },
    );
  } finally {
    askInFlight = false;
  }
}
