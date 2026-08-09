import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import { paths } from "@/lib/workspace";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export type VitalStatus = "GREEN" | "YELLOW" | "RED" | "OFF" | "UNKNOWN";

export interface VitalUnit {
  id: string;
  name: string;
  group: string;
  criticality: string;
  status: VitalStatus;
  what: string | null;
  breaks: string | null;
  since: string | null;
  downFor: string;
  problems: string[];
}

export interface VitalEvent {
  ts_et: string;
  id: string;
  name: string;
  from: string;
  to: string;
  detail: string;
}

export interface VitalsView {
  fetchedAt: string;
  checkedAtEt: string | null;
  /** Minutes since the collector last wrote. The monitor is itself unattended --
   * a frozen snapshot must never render as a healthy rig. */
  snapshotAgeMin: number | null;
  verdict: VitalStatus;
  counts: Record<string, number>;
  nTasksLive: number;
  nTasksUnclaimed: number;
  reason: string | null;
  units: VitalUnit[];
  events: VitalEvent[];
}

const EMPTY: VitalsView = {
  fetchedAt: new Date(0).toISOString(),
  checkedAtEt: null,
  snapshotAgeMin: null,
  verdict: "UNKNOWN",
  counts: {},
  nTasksLive: 0,
  nTasksUnclaimed: 0,
  reason: "automation/state/unattended-health.json not readable — has Gamma_UnattendedHealth run?",
  units: [],
  events: [],
};

/** The snapshot stamp is naive ET wall clock; the dashboard renders on a
 * Mountain-time box. Convert via the live offset rather than a hardcoded +2 so
 * this stays correct across DST — the same trap state_freshness_audit documents. */
function minutesSinceEt(stamp: string | null): number | null {
  if (!stamp) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/.exec(stamp);
  if (!m) return null;
  const [, y, mo, d, h, mi, s] = m.map(Number) as unknown as number[];
  const etWall = Date.UTC(y, mo - 1, d, h, mi, s);
  const nowLocal = new Date();
  const localWall = Date.UTC(
    nowLocal.getFullYear(), nowLocal.getMonth(), nowLocal.getDate(),
    nowLocal.getHours(), nowLocal.getMinutes(), nowLocal.getSeconds(),
  );
  const offsetH = Math.round((etWall - localWall) / 3_600_000);
  return Math.floor((localWall + offsetH * 3_600_000 - etWall) / 60_000);
}

async function readEvents(limit: number): Promise<VitalEvent[]> {
  try {
    const raw = await readFile(paths.unattendedEvents, "utf8");
    return raw
      .split("\n")
      .filter((l) => l.trim())
      .slice(-limit)
      .reverse()
      .map((l) => JSON.parse(l) as VitalEvent)
      .filter((e) => e && e.id);
  } catch {
    return []; // no ledger yet = nothing has changed state. Not an error.
  }
}

export async function GET() {
  let snapshot: Record<string, unknown>;
  try {
    snapshot = JSON.parse(await readFile(paths.unattendedHealth, "utf8"));
  } catch {
    return NextResponse.json(
      { ...EMPTY, fetchedAt: new Date().toISOString() },
      { headers: { "Cache-Control": "no-store, max-age=0" } },
    );
  }

  const rawUnits = Array.isArray(snapshot.units) ? (snapshot.units as Record<string, unknown>[]) : [];
  // Trim aggressively: the on-disk snapshot carries every per-task/artifact row
  // (~70KB) and this endpoint is polled every 20s. The tile only needs the
  // verdict, the consequence and the first few problems.
  const units: VitalUnit[] = rawUnits.map((u) => ({
    id: String(u.id ?? ""),
    name: String(u.name ?? u.id ?? ""),
    group: String(u.group ?? "INFRA"),
    criticality: String(u.criticality ?? "medium"),
    status: (u.status as VitalStatus) ?? "UNKNOWN",
    what: (u.what as string) ?? null,
    breaks: (u.breaks as string) ?? null,
    since: (u.since as string) ?? null,
    downFor: String(u.down_for ?? ""),
    problems: Array.isArray(u.problems) ? (u.problems as string[]).slice(0, 6) : [],
  }));

  const checkedAtEt = (snapshot.checked_at_et as string) ?? null;

  return NextResponse.json(
    {
      fetchedAt: new Date().toISOString(),
      checkedAtEt,
      snapshotAgeMin: minutesSinceEt(checkedAtEt),
      verdict: (snapshot.verdict as VitalStatus) ?? "UNKNOWN",
      counts: (snapshot.counts as Record<string, number>) ?? {},
      nTasksLive: Number(snapshot.n_tasks_live ?? 0),
      nTasksUnclaimed: Number(snapshot.n_tasks_unclaimed ?? 0),
      reason: (snapshot.reason as string) ?? null,
      units,
      events: await readEvents(60),
    } satisfies VitalsView,
    { headers: { "Cache-Control": "no-store, max-age=0" } },
  );
}
