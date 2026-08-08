// Pure text-shaping helpers for raw, semi-trusted file content the Gamma App
// reads directly in TypeScript (discord-outbox.jsonl, queue.md, gamma-wants.json).
// Mirrors the DISCIPLINE of gamma_hq.py's _sanitize_line/_truncate (collapse to
// one line, ban known log-spew markers, truncate at a word boundary) -- ported
// rather than shared because the Python side already sanitizes its OWN fields
// before they reach PresenceView; this module exists for the NEW raw sources
// Python never touches. Keep semantics aligned if gamma_hq.py's rules change.

// "Is this whole row raw log-spew" (a SKIP decision, applied to short,
// single-purpose fields where the substring appearing at all means the field
// WAS copy-pasted from an infra dump -- e.g. an outbox row's message) is a
// DIFFERENT question from "clean up this text for display" (applied to
// long-form prose, like a queue.md research writeup, that may legitimately
// use the word "degraded" in an ordinary sentence without BEING spew). Two
// functions, not one -- conflating them into a single sanitize-or-refuse
// helper was a real bug here: queue.md's THIS-WEEK descriptions are
// multi-hundred-word writeups that often discuss a DEGRADED self-check flag
// as their subject matter, so the refuse-outright gate was silently
// collapsing legitimate, on-topic descriptions to a fallback placeholder.
const LOG_SPEW_MARKERS = ["traceback (most recent call last)", "degraded"];

/** True if `text` looks like a raw infra-ops dump rather than narrative
 * content -- use this to decide whether to SKIP a short, single-purpose field
 * entirely (e.g. an outbox row before it's ever shown), never as a filter
 * applied to long free-form prose after the fact. */
export function isLogSpew(text: string): boolean {
  const lowered = text.toLowerCase();
  return LOG_SPEW_MARKERS.some((marker) => lowered.includes(marker));
}

export function truncateWordBoundary(text: string, maxLen: number, ellipsis = "…"): string {
  if (text.length <= maxLen) return text;
  const budget = maxLen - ellipsis.length;
  if (budget <= 0) return text.slice(0, maxLen);
  let cut = text.slice(0, budget);
  const boundary = cut.lastIndexOf(" ");
  if (boundary > 0) cut = cut.slice(0, boundary);
  cut = cut.replace(/[\s,.;:-]+$/, "");
  if (!cut) cut = text.slice(0, budget);
  return cut + ellipsis;
}

/** Collapse arbitrary file content into one clean line: strip a leading Discord
 * mention (`<@1234>`), strip light markdown decoration (`**bold**`, `` `code` ``),
 * collapse embedded newlines/whitespace, then truncate at a word boundary.
 * Never throws; empty/missing input -> fallback. Does NOT filter content --
 * callers deciding whether a raw source row is spam should use isLogSpew()
 * on the ORIGINAL row before ever reaching this formatting step. */
export function sanitizeText(raw: unknown, maxLen = 160, fallback = ""): string {
  if (raw === null || raw === undefined) return fallback;
  let text = String(raw).trim();
  if (!text) return fallback;
  text = text.replace(/^<@!?\d+>\s*/, "");
  text = text.replace(/\*\*(.+?)\*\*/g, "$1").replace(/`([^`]+)`/g, "$1");
  text = text.split(/\s+/).join(" ");
  return truncateWordBoundary(text, maxLen);
}

export function fmtSignedMoney(x: number): string {
  if (Math.abs(x) < 0.005) return "flat $0";
  const sign = x > 0 ? "+" : "-";
  return `${sign}$${Math.abs(x).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

const CONVENTIONAL_PREFIX_RE = /^[a-z]+(\([^)]*\))?:\s*(.+)$/;

/** RECENT-SHIPS-style commit subject: strip a leading conventional-commit
 * "type(scope):"/"type:" prefix, sentence-case the remainder. */
export function humanizeCommitSubject(subject: unknown, maxLen: number): string {
  let text = sanitizeText(subject, 500);
  const m = CONVENTIONAL_PREFIX_RE.exec(text);
  if (m) text = m[2].trim();
  if (text) text = text[0].toUpperCase() + text.slice(1);
  return truncateWordBoundary(text, maxLen);
}

/** "BULLISH_RECLAIM_RIDE_THE_RIBBON" -> "Bullish reclaim ride the ribbon".
 * Turns a SCREAMING_SNAKE_CASE engine identifier (setup name, reason code)
 * into something that reads like a sentence fragment rather than a constant. */
export function humanizeIdentifier(id: unknown): string {
  const text = String(id ?? "").trim();
  if (!text) return "";
  const words = text.toLowerCase().split(/[_-]+/).filter(Boolean);
  if (words.length === 0) return "";
  return words[0][0].toUpperCase() + words[0].slice(1) + (words.length > 1 ? " " + words.slice(1).join(" ") : "");
}

/** Strip a leading "[TAG] " shout-caps prefix some producers write (e.g.
 * "[PROSPECTOR] 2026-08-08 beat=..."), since the caller already shows an icon
 * + source label for that context. */
export function stripLeadingBracketTag(text: string): string {
  return text.replace(/^\[[A-Z0-9_ -]+\]\s*/, "");
}
