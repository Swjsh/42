import { NextRequest, NextResponse } from "next/server";
import { promises as fs } from "node:fs";
import path from "node:path";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  try {
    const { dataUrl, name } = (await req.json()) as {
      dataUrl: string;
      name?: string;
    };
    if (!dataUrl?.startsWith("data:image/png;base64,")) {
      return NextResponse.json(
        { error: "expected data:image/png;base64,..." },
        { status: 400 },
      );
    }
    const b64 = dataUrl.slice("data:image/png;base64,".length);
    const buf = Buffer.from(b64, "base64");
    const outPath = path.join(
      "C:\\Users\\jackw\\Desktop\\42\\dashboard",
      `${name ?? "snapshot"}.png`,
    );
    await fs.writeFile(outPath, buf);
    return NextResponse.json({ ok: true, path: outPath, bytes: buf.length });
  } catch (error: unknown) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown" },
      { status: 500 },
    );
  }
}
