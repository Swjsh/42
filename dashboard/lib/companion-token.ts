import "server-only";

// gamma-companion/server.js mints a per-boot page token and injects it as
// <meta name="gamma-token"> into every HTML it serves. The cockpit page runs this
// same bootstrap server-side and re-renders the meta so the client components
// (fire, chat, army poll) can send x-gamma-token through the /companion proxy.
const COMPANION_ORIGIN = process.env.GAMMA_COMPANION_ORIGIN ?? "http://127.0.0.1:4317";
const TOKEN_META_RE = /<meta\s+name="gamma-token"\s+content="([^"]+)"/i;

export async function fetchCompanionToken(): Promise<string | null> {
  try {
    const res = await fetch(COMPANION_ORIGIN + "/", { cache: "no-store" });
    if (!res.ok) return null;
    const m = TOKEN_META_RE.exec(await res.text());
    return m ? m[1] : null;
  } catch {
    return null;
  }
}
