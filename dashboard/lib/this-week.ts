// Parses automation/overnight/queue.md's "## Active backlog" section for the
// THIS WEEK plan card. Format (documented at the top of queue.md itself):
//   - [ ] <id> (<priority>) :: <description> :: depends:<...> :: status:<...>
// Entries are dense multi-hundred-word engineering writeups (real research
// backlog, not consumer copy) -- this extracts just id + priority + a short,
// sanitized lead from the description clause. queue.md is currently ~700KB;
// this reads it once per request (matches this app's existing full-read
// convention for other state files) but bails out early once it has enough
// items rather than scanning the whole multi-thousand-line file.

import { promises as fs } from "node:fs";
import { paths } from "./workspace";
import { sanitizeText } from "./text";
import type { ThisWeekItem } from "./gamma-app-types";

const PRIORITY_RANK: Record<string, number> = { CRITICAL: 0, HIGH: 1, MED: 2, MEDIUM: 2, LOW: 3 };

const ITEM_RE = /^-\s\[ \]\s+(\S+)\s+\(([A-Z]+)[^)]*\)\s*::\s*(.*)$/;

export async function readThisWeek(limit = 3): Promise<ThisWeekItem[]> {
  try {
    const text = await fs.readFile(paths.overnightQueue, "utf-8");
    const activeIdx = text.indexOf("## Active backlog");
    const scope = activeIdx >= 0 ? text.slice(activeIdx) : text;

    const candidates: ThisWeekItem[] = [];
    for (const line of scope.split(/\r?\n/)) {
      const m = ITEM_RE.exec(line);
      if (!m) continue;
      const [, id, priority, rest] = m;
      // Description clause runs up to the NEXT "::" field separator
      // (depends:/status:); everything after that is real metadata worth
      // showing when the tile is expanded, not summary filler.
      const clauses = rest.split(/\s::\s/);
      const desc = clauses[0] ?? rest;
      const detailClauses = clauses.slice(1).filter((c) => c.trim());
      // Short, always-visible headline (an "ad tile" title, not the whole
      // engineering writeup) vs. the full clause + depends:/status: metadata,
      // which only appears once the card is clicked open.
      const shortText = sanitizeText(desc, 70, "(no description)");
      const fullText = sanitizeText(desc, 500, "");
      const breakdownParts = [fullText !== shortText ? fullText : "", ...detailClauses].filter((c) => c.trim());
      candidates.push({
        id,
        priority,
        text: shortText,
        detail: breakdownParts.length ? sanitizeText(breakdownParts.join(" · "), 600, "") || undefined : undefined,
      });
      if (candidates.length >= 40) break; // plenty to rank from without scanning the whole file
    }

    candidates.sort((a, b) => (PRIORITY_RANK[a.priority] ?? 9) - (PRIORITY_RANK[b.priority] ?? 9));
    return candidates.slice(0, limit);
  } catch {
    return [];
  }
}
