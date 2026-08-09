import { NextResponse } from "next/server";
import { getQuote } from "@/lib/quote";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  const quote = await getQuote();
  return NextResponse.json(quote, {
    headers: { "Cache-Control": "no-store, max-age=0" },
  });
}
