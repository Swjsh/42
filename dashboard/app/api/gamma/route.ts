import { NextResponse } from "next/server";
import { buildGammaAppView } from "@/lib/gamma-app";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  const view = await buildGammaAppView();
  return NextResponse.json(view, {
    headers: { "Cache-Control": "no-store, max-age=0" },
  });
}
