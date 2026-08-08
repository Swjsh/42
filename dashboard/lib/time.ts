const ET = "America/New_York";
export const ET_ZONE = ET;

export function formatET(d: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: ET,
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(d);
}

export function todayET(d: Date = new Date()): string {
  // YYYY-MM-DD in ET. en-CA gives ISO format.
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: ET,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

export function isMarketHoursET(d: Date = new Date()): boolean {
  const time = formatET(d); // "HH:MM:SS"
  const [hh, mm] = time.split(":").map(Number);
  const minutes = hh * 60 + mm;
  return minutes >= 9 * 60 + 30 && minutes <= 16 * 60;
}

/** Convert a WALL-CLOCK time meant to be read in `timeZone` into the true UTC
 * instant it represents -- DST-correct, no hardcoded offset. This box's local
 * OS timezone is Mountain, not Eastern (see CLAUDE.md's "Bash TZ broken"
 * lesson) -- several state files this app reads write bare "YYYY-MM-DDTHH:MM:SS"
 * strings with NO zone suffix, meaning the wall-clock digits ARE Eastern time
 * but a naive `new Date(str)` would parse them as this process's local zone
 * and silently skew by 1-2 hours. Standard "round-trip through Intl to
 * discover the real offset" technique: guess the instant as if the digits
 * were UTC, ask Intl what wall-clock time that guess reads as in `timeZone`,
 * then correct by the difference. Two Intl calls in the same tz always land
 * on the same side of a DST boundary as the input, so this is safe even near
 * a spring-forward/fall-back transition.
 */
export function wallClockInZoneToUtc(
  y: number,
  month: number, // 1-12
  day: number,
  hour: number,
  minute: number,
  second = 0,
  timeZone: string = ET,
): Date {
  const guessUtcMs = Date.UTC(y, month - 1, day, hour, minute, second);
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(new Date(guessUtcMs));
  const get = (type: string): number => Number(parts.find((p) => p.type === type)?.value ?? 0);
  // Intl reports hour "24" for midnight in some locales/engines instead of "00".
  const hourPart = get("hour") % 24;
  const etReadingMs = Date.UTC(get("year"), get("month") - 1, get("day"), hourPart, get("minute"), get("second"));
  const driftMs = etReadingMs - guessUtcMs;
  return new Date(guessUtcMs - driftMs);
}

/** Parse a bare "YYYY-MM-DD[T ]HH:MM:SS(.ffffff)?" string (no zone suffix) as
 * a wall-clock time in `timeZone` (default ET) and return the true UTC
 * instant. Returns null on anything that doesn't match -- never throws. */
export function parseBareTimestampInZone(raw: unknown, timeZone: string = ET): Date | null {
  if (typeof raw !== "string") return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/.exec(raw.trim());
  if (!m) return null;
  const [, y, mo, d, hh, mm, ss] = m.map(Number) as unknown as number[];
  const dt = wallClockInZoneToUtc(y, mo, d, hh, mm, ss, timeZone);
  return Number.isNaN(dt.getTime()) ? null : dt;
}
