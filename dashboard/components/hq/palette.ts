// Shared palette + small deterministic helpers for the /hq space-station
// scene. Colors are plain hex strings (three.js accepts them directly on
// `color`/`emissive` props) so this file has zero three.js dependency and can
// be imported from the 2D fallback too.

export const PALETTE = {
  space: "#03040a",
  fogColor: "#050914",
  hubCore: "#7ad9ff",
  hubRing: "#22d3ee",
  floor: "#0c1220",
  deskDark: "#141b2e",
  corridor: "#12203a",
  amberAlert: "#ffb020",
  gamingAmber: "#ffb020",
  planet: "#16324a",
  planetRim: "#4fd6ff",
  text: "#dff3ff",
  textDim: "#7f93b0",
} as const;

export const HEALTH_COLOR: Record<string, string> = {
  green: "#22ff88",
  amber: "#ffb020",
  red: "#ff3b3b",
  frozen: "#6a86b8",
  zombie: "#a855f7",
};

export function healthColor(health: string): string {
  return HEALTH_COLOR[health] ?? "#7f93b0";
}

export const IDEA_STATUS_COLOR: Record<string, string> = {
  proposed: "#22d3ee",
  testing: "#ffb020",
  supported: "#22ff88",
  refuted: "#8a94a6",
  killed: "#ff3b3b",
  shipped: "#7ad9ff",
};

export function ideaStatusColor(status: string): string {
  return IDEA_STATUS_COLOR[status] ?? "#dff3ff";
}

/** A row counts as "parked" (dark module, no working animation) when its
 * STATE is one of the terminal/inactive values, or its HEALTH says frozen or
 * zombie -- see sector_rows.py's STATE_VALUES/HEALTH_VALUES; there is no
 * literal "parked" enum member on either, so this is the derived union the
 * brief's mapping table means by "state parked/killed/frozen". */
export function isParkedState(state: string, health: string): boolean {
  return (
    state === "killed" ||
    state === "dormant" ||
    state === "dead" ||
    health === "frozen" ||
    health === "zombie"
  );
}

/** xmur3 hash -> mulberry32 generator: a small, well-known, deterministic
 * seeded PRNG (public-domain algorithms, reimplemented here). Used ONLY to
 * pick a per-lane phase offset / next-walk interval at schedule time -- never
 * called inside a useFrame loop (CLAUDE.md "no Math.random per frame"). */
export function seededRandom(seed: string): () => number {
  let h = 1779033703 ^ seed.length;
  for (let i = 0; i < seed.length; i++) {
    h = Math.imul(h ^ seed.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  return function next(): number {
    h = Math.imul(h ^ (h >>> 16), 2246822519);
    h = Math.imul(h ^ (h >>> 13), 3266489917);
    h ^= h >>> 16;
    return (h >>> 0) / 4294967296;
  };
}

/** Parses a "YYYY-MM-DD HH:MM:SS ET" / "YYYY-MM-DDTHH:MM:SS..." string into a
 * comparable epoch-like number (Date.UTC of its own digits, NOT a real UTC
 * conversion -- both this and `nowEtMinutes` below are built the same way, so
 * their DELTA is a correct "minutes elapsed in ET wall-clock time" even
 * though neither value is a real UTC timestamp). Returns null if unparsable
 * ("unknown" is the honest fail-open value sector_rows.py uses). */
export function parseEtLikeMinutes(raw: string | null | undefined): number | null {
  if (!raw) return null;
  const m = /(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/.exec(raw);
  if (!m) return null;
  const [, y, mo, d, h, mi, s] = m.map(Number) as unknown as number[];
  return Date.UTC(y, mo - 1, d, h, mi, s) / 60000;
}

/** Current wall-clock time in America/New_York, expressed the same
 * Date.UTC-of-its-own-digits way as parseEtLikeMinutes so the two are
 * directly comparable. */
export function nowEtMinutes(): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).formatToParts(new Date());
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? "0");
  const hour = get("hour") % 24; // Intl can emit "24" for midnight in some locales
  return Date.UTC(get("year"), get("month") - 1, get("day"), hour, get("minute"), get("second")) / 60000;
}

/** Minutes between now (ET) and a sector row's last_evidence_et -- null when
 * either side is unparsable (row says "unknown", or a clock read failed). */
export function minutesSinceEvidence(lastEvidenceEt: string): number | null {
  const then = parseEtLikeMinutes(lastEvidenceEt);
  if (then === null) return null;
  return Math.max(0, nowEtMinutes() - then);
}

/** Freshness 0..1 for corridor pulse speed -- 1 = just happened, 0 = a day or
 * more stale. Deliberately coarse (one fixed 24h scale across every lane):
 * this is an ambient/glanceable visualization, not a per-lane SLA monitor. */
export function freshness01(minutesAgo: number | null): number {
  if (minutesAgo === null) return 0;
  const clamped = Math.min(Math.max(minutesAgo, 0), 1440);
  return 1 - clamped / 1440;
}

export function clamp01(v: number): number {
  return Math.min(1, Math.max(0, v));
}

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}
