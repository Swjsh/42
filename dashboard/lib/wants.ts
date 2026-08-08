// Reads automation/state/gamma-wants.json directly (rather than relying only
// on PresenceView's already-truncated top-3 text) so the "I WANT" cards can
// show the real priority number + stable id for badges/keys.

import { promises as fs } from "node:fs";
import { paths } from "./workspace";
import { sanitizeText } from "./text";
import type { WantItem } from "./gamma-app-types";

interface RawWant {
  priority?: number;
  id?: string;
  text?: string;
  title?: string;
  want?: string;
  summary?: string;
  label?: string;
}

function extractText(item: unknown): string {
  if (typeof item === "string") return item;
  if (item && typeof item === "object") {
    const d = item as RawWant;
    for (const key of ["text", "title", "want", "summary", "label"] as const) {
      const v = d[key];
      if (typeof v === "string" && v.trim()) return v;
    }
  }
  return "";
}

export async function readWants(limit = 4): Promise<WantItem[]> {
  try {
    const raw = JSON.parse(await fs.readFile(paths.gammaWants, "utf-8")) as unknown;
    let items: unknown[] = [];
    if (Array.isArray(raw)) items = raw;
    else if (raw && typeof raw === "object" && Array.isArray((raw as { wants?: unknown }).wants)) {
      items = (raw as { wants: unknown[] }).wants;
    }
    return items.slice(0, limit).map((item, i) => {
      const d = (item && typeof item === "object" ? (item as RawWant) : {}) as RawWant;
      return {
        id: typeof d.id === "string" ? d.id : `want-${i}`,
        priority: typeof d.priority === "number" ? d.priority : i + 1,
        text: sanitizeText(extractText(item), 180, "(unavailable)"),
      };
    });
  } catch {
    return [];
  }
}
