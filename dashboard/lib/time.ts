const ET = "America/New_York";

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
