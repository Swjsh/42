import { NextResponse } from "next/server";
import { getLatestSpeech } from "@/lib/dialogue";

export const dynamic = "force-dynamic";
export const revalidate = 0;

// The real, already-running companion server (gamma-companion/server.js),
// bound to 127.0.0.1 only. Never collides with this Next.js app on :3000.
const COMPANION_ORIGIN = process.env.GAMMA_COMPANION_ORIGIN ?? "http://127.0.0.1:4317";

// server.js injects the page-auth token into every HTML response it serves,
// e.g. <meta name="gamma-token" content="..." /> (see serveStatic() in
// gamma-companion/server.js). It is a per-process-boot value with no
// documented API contract, so this is a best-effort scrape of the SAME
// bootstrap sequence the companion's own browser client performs -- just run
// server-side instead of in a browser.
const TOKEN_META_RE = /<meta\s+name="gamma-token"\s+content="([^"]+)"/i;

const OFFLINE_REPLY = "Gamma's voice brain is offline right now.";

interface CompanionChatResponse {
  ok?: boolean;
  reply?: string;
  escalate?: boolean;
  model?: string | null;
  ask_id?: string | null;
  error?: string;
}

function offline(detail: string) {
  return NextResponse.json(
    { ok: false, offline: true, reply: OFFLINE_REPLY, detail },
    { status: 200, headers: { "Cache-Control": "no-store" } }
  );
}

async function fetchCompanionToken(): Promise<string | null> {
  const res = await fetch(COMPANION_ORIGIN + "/", { cache: "no-store" });
  if (!res.ok) return null;
  const html = await res.text();
  const match = TOKEN_META_RE.exec(html);
  return match ? match[1] : null;
}

/**
 * GET /api/gamma-chat -- "what is Gamma saying right now". Serves the
 * real, already-live speech from automation/state/dashboard-dialogue.json
 * (via lib/dialogue.ts) for GammaPresence.tsx's speech bubble. Lives on this
 * route (rather than a 7th new file) because it's the same "Gamma's voice"
 * concern as the POST chat below -- one surface for everything GammaPresence
 * needs to render.
 */
export async function GET() {
  const speech = await getLatestSpeech();
  return NextResponse.json(
    { ok: true, speech },
    { headers: { "Cache-Control": "no-store, max-age=0" } }
  );
}

/**
 * POST /api/gamma-chat { message: string } -- proxies a real chat turn to the
 * companion's /api/chat. Fails open with an honest "offline" reply on any
 * connectivity problem (companion not running, wrong token, bad response) --
 * never throws, never fabricates a reply.
 */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid JSON body" }, { status: 400 });
  }

  const message =
    body && typeof body === "object" && "message" in body && typeof (body as { message: unknown }).message === "string"
      ? (body as { message: string }).message.trim()
      : "";

  if (!message) {
    return NextResponse.json({ ok: false, error: "message is required" }, { status: 400 });
  }

  let token: string | null;
  try {
    token = await fetchCompanionToken();
  } catch {
    return offline("companion unreachable while bootstrapping the page token (likely not running)");
  }
  if (!token) {
    return offline("companion is running but no gamma-token meta tag was found on its root page");
  }

  let companionRes: Response;
  try {
    companionRes = await fetch(COMPANION_ORIGIN + "/api/chat", {
      method: "POST",
      headers: { "content-type": "application/json", "x-gamma-token": token },
      body: JSON.stringify({ message }),
      cache: "no-store",
    });
  } catch {
    return offline("companion unreachable on /api/chat");
  }

  if (companionRes.status === 403) {
    return offline("companion rejected the token (403) -- likely rotated between bootstrap and call");
  }

  let data: CompanionChatResponse;
  try {
    data = (await companionRes.json()) as CompanionChatResponse;
  } catch {
    return offline("companion returned a non-JSON response");
  }

  return NextResponse.json(
    {
      ok: companionRes.ok,
      offline: false,
      reply: data.reply ?? "(no reply)",
      escalating: !!data.escalate,
      model: data.model ?? null,
      askId: data.ask_id ?? null,
    },
    { headers: { "Cache-Control": "no-store" } }
  );
}
