import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

// The cockpit payload is produced by setup/scripts/gamma_home.py (Gamma_Home, every 30 min)
// and written to gamma-companion/public/payload.json. This route only reads it.
export const dynamic = "force-dynamic";

const PAYLOAD = path.resolve(process.cwd(), "..", "gamma-companion", "public", "payload.json");

export async function GET() {
  try {
    const [raw, stat] = await Promise.all([fs.readFile(PAYLOAD, "utf-8"), fs.stat(PAYLOAD)]);
    const body = raw.replace(/^﻿/, "");
    return new NextResponse(body, {
      headers: {
        "content-type": "application/json; charset=utf-8",
        "cache-control": "no-store",
        "x-payload-mtime": stat.mtime.toISOString(),
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: "payload.json unreadable", detail: message, path: PAYLOAD }, { status: 503 });
  }
}
