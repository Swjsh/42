"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { Activity } from "lucide-react";
import type { VitalsView, VitalUnit, VitalStatus } from "@/app/api/vitals/route";

const REFRESH_MS = 30_000;

/** Every unattended thing in the rig, one bubble each, grouped by what it serves.
 *
 * J 2026-08-09: "each bubble represents an audit or a pipeline. i want to know if
 * things break when they go down now days after the facts."
 *
 * Two halves, and the second is the point:
 *   TOP    -- the current lights. Click a bubble to see what is wrong AND what
 *             silently degrades while it stays that way (`breaks`).
 *   BOTTOM -- the outage ledger. Every status transition the collector has ever
 *             recorded, newest first, so an outage that started on Tuesday and
 *             healed on Thursday is still legible on Sunday. A live-only tile
 *             answers "is it broken now"; this answers "did it break".
 *
 * Data: automation/state/unattended-health.json (+ unattended-events.jsonl),
 * written every 10 min by Gamma_UnattendedHealth. The snapshot's OWN age is
 * rendered whenever it goes stale -- the monitor is itself an unattended thing,
 * and a frozen snapshot must never read as a healthy rig.
 */

const TONE: Record<VitalStatus, { dot: string; text: string; label: string }> = {
  GREEN: { dot: "var(--up)", text: "var(--up)", label: "healthy" },
  YELLOW: { dot: "var(--amber)", text: "var(--amber)", label: "degraded" },
  RED: { dot: "var(--down)", text: "var(--down)", label: "down" },
  OFF: { dot: "var(--text-4)", text: "var(--text-4)", label: "off by design" },
  UNKNOWN: { dot: "#8b5cf6", text: "#8b5cf6", label: "unknown" },
};

const GROUP_ORDER = ["TRADING", "DATA", "AUDIT", "RESEARCH", "REPORTING", "INFRA"];
const RANK: Record<VitalStatus, number> = { RED: 0, YELLOW: 1, UNKNOWN: 2, OFF: 3, GREEN: 4 };

const fetcher = async (url: string): Promise<VitalsView> => {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as VitalsView;
};

function Bubble({ unit, active, onClick }: { unit: VitalUnit; active: boolean; onClick: () => void }) {
  const tone = TONE[unit.status] ?? TONE.UNKNOWN;
  const bad = unit.status === "RED" || unit.status === "YELLOW";
  return (
    <button
      onClick={onClick}
      title={`${unit.name} — ${tone.label}${unit.downFor ? ` for ${unit.downFor}` : ""}`}
      aria-label={`${unit.name}, ${tone.label}`}
      className="flex items-center gap-2 rounded-full py-1 pl-1.5 pr-2.5 text-left transition-colors"
      style={{
        background: active ? "rgba(255,255,255,0.07)" : "rgba(255,255,255,0.03)",
        border: `1px solid ${active ? `${tone.dot}66` : "var(--border)"}`,
      }}
    >
      <span
        className="shrink-0 rounded-full"
        style={{
          width: 9,
          height: 9,
          background: tone.dot,
          // Only failures glow. If everything pulses, nothing draws the eye.
          boxShadow: bad ? `0 0 7px ${tone.dot}` : "none",
          opacity: unit.status === "OFF" ? 0.45 : 1,
        }}
      />
      <span
        className="truncate text-[11px]"
        style={{ color: bad ? tone.text : "var(--text-2)", maxWidth: 152 }}
      >
        {unit.name}
      </span>
      {unit.downFor && (
        <span className="shrink-0 text-[9px] tabular-nums" style={{ color: tone.text, opacity: 0.8 }}>
          {unit.downFor}
        </span>
      )}
    </button>
  );
}

export default function VitalsTile() {
  const { data, error } = useSWR<VitalsView>("/api/vitals", fetcher, {
    refreshInterval: REFRESH_MS,
    keepPreviousData: true,
  });
  const [selected, setSelected] = useState<string | null>(null);
  const [showLedger, setShowLedger] = useState(false);

  const grouped = useMemo(() => {
    const units = data?.units ?? [];
    const byGroup = new Map<string, VitalUnit[]>();
    for (const u of units) {
      if (!byGroup.has(u.group)) byGroup.set(u.group, []);
      byGroup.get(u.group)!.push(u);
    }
    // Failures first inside each group -- a red bubble must never be buried
    // alphabetically behind twelve green ones.
    for (const list of byGroup.values()) {
      list.sort((a, b) => RANK[a.status] - RANK[b.status] || a.name.localeCompare(b.name));
    }
    return GROUP_ORDER.filter((g) => byGroup.has(g)).map((g) => [g, byGroup.get(g)!] as const);
  }, [data]);

  const detail = useMemo(
    () => data?.units.find((u) => u.id === selected) ?? null,
    [data, selected],
  );

  const counts = data?.counts ?? {};
  const red = counts.RED ?? 0;
  const yellow = counts.YELLOW ?? 0;
  const verdictTone = TONE[data?.verdict ?? "UNKNOWN"] ?? TONE.UNKNOWN;
  const stale = (data?.snapshotAgeMin ?? 0) > 30;

  return (
    <section
      className="overflow-hidden rounded-[var(--radius-lg)] border"
      style={{ background: "var(--bg-card)", borderColor: "var(--border)", boxShadow: "var(--shadow-sm)" }}
    >
      <header className="flex items-center gap-3 px-4 py-3" style={{ minHeight: 52 }}>
        <Activity size={16} style={{ color: "var(--text-3)" }} aria-hidden />
        <span
          className="text-[11px] font-semibold uppercase tracking-[0.16em]"
          style={{ color: "var(--text-3)" }}
        >
          Vitals
        </span>
        <span
          className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold"
          style={{
            color: verdictTone.text,
            background: "rgba(255,255,255,0.04)",
            border: `1px solid ${verdictTone.dot}33`,
          }}
        >
          {data?.verdict ?? "…"}
        </span>
        <span className="ml-auto text-[11px] tabular-nums" style={{ color: "var(--text-4)" }}>
          {red > 0 && <span style={{ color: "var(--down)" }}>{red} down · </span>}
          {yellow > 0 && <span style={{ color: "var(--amber)" }}>{yellow} degraded · </span>}
          {data ? `${data.units.length} units · ${data.nTasksLive} tasks` : "loading…"}
        </span>
      </header>

      <div className="px-4 pb-4">
        {error && (
          <p className="text-[12px]" style={{ color: "var(--amber)" }}>
            Vitals feed unreachable — showing last good data.
          </p>
        )}
        {data?.reason && (
          <p className="mb-3 text-[12px]" style={{ color: "var(--amber)" }}>
            {data.reason}
          </p>
        )}
        {stale && (
          <p className="mb-3 text-[12px]" style={{ color: "var(--amber)" }}>
            ⚠ These lights are {data!.snapshotAgeMin}m old — the collector itself may be down.
          </p>
        )}

        <div className="flex flex-col gap-3">
          {grouped.map(([group, units]) => (
            <div key={group}>
              <div
                className="mb-1.5 text-[9px] font-semibold uppercase tracking-[0.2em]"
                style={{ color: "var(--text-4)" }}
              >
                {group}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {units.map((u) => (
                  <Bubble
                    key={u.id}
                    unit={u}
                    active={selected === u.id}
                    onClick={() => setSelected(selected === u.id ? null : u.id)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>

        {detail && (
          <div
            className="mt-4 rounded-[var(--radius)] border p-3"
            style={{ borderColor: `${TONE[detail.status].dot}44`, background: "rgba(255,255,255,0.02)" }}
          >
            <div className="flex items-baseline gap-2">
              <span className="text-[13px] font-semibold" style={{ color: "var(--text-1)" }}>
                {detail.name}
              </span>
              <span className="text-[10px] uppercase tracking-wider" style={{ color: TONE[detail.status].text }}>
                {TONE[detail.status].label}
                {detail.downFor ? ` · ${detail.downFor}` : ""}
              </span>
              <span className="ml-auto text-[10px]" style={{ color: "var(--text-4)" }}>
                {detail.criticality} · since {detail.since ?? "—"}
              </span>
            </div>
            {detail.what && (
              <p className="mt-1.5 text-[12px]" style={{ color: "var(--text-2)" }}>
                {detail.what}
              </p>
            )}
            {detail.problems.length > 0 && (
              <ul className="mt-2 flex flex-col gap-1">
                {detail.problems.map((p, i) => (
                  <li key={i} className="text-[11px]" style={{ color: "var(--text-3)" }}>
                    · {p}
                  </li>
                ))}
              </ul>
            )}
            {/* The consequence, not just the symptom. A red light nobody can price
                is a light nobody acts on. */}
            {detail.breaks && detail.status !== "GREEN" && detail.status !== "OFF" && (
              <p
                className="mt-2 rounded-[var(--radius-sm)] px-2 py-1.5 text-[11px]"
                style={{ color: "var(--text-2)", background: "rgba(239,68,68,0.08)" }}
              >
                <span style={{ color: "var(--down)" }}>Breaks: </span>
                {detail.breaks}
              </p>
            )}
          </div>
        )}

        <button
          onClick={() => setShowLedger((v) => !v)}
          className="mt-4 text-[11px] underline-offset-2 hover:underline"
          style={{ color: "var(--text-4)" }}
        >
          {showLedger ? "Hide" : "Show"} outage ledger ({data?.events.length ?? 0} recorded changes)
        </button>

        {showLedger && (
          <div className="mt-2 max-h-[260px] overflow-y-auto pr-1">
            {(data?.events ?? []).length === 0 ? (
              <p className="text-[11px]" style={{ color: "var(--text-4)" }}>
                Nothing has changed state since the collector started.
              </p>
            ) : (
              <table className="w-full text-[11px]">
                <tbody>
                  {(data?.events ?? []).map((e, i) => (
                    <tr key={`${e.ts_et}-${e.id}-${i}`} style={{ color: "var(--text-3)" }}>
                      <td className="whitespace-nowrap py-1 pr-2 align-top tabular-nums" style={{ color: "var(--text-4)" }}>
                        {e.ts_et?.slice(5, 16)}
                      </td>
                      <td className="py-1 pr-2 align-top" style={{ color: "var(--text-2)" }}>
                        {e.name}
                      </td>
                      <td className="whitespace-nowrap py-1 pr-2 align-top">
                        <span style={{ color: TONE[e.from as VitalStatus]?.text ?? "var(--text-4)" }}>
                          {e.from}
                        </span>
                        {" → "}
                        <span style={{ color: TONE[e.to as VitalStatus]?.text ?? "var(--text-4)" }}>
                          {e.to}
                        </span>
                      </td>
                      <td className="py-1 align-top" style={{ color: "var(--text-4)" }}>
                        {e.detail}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        <p className="mt-3 text-[10px]" style={{ color: "var(--text-4)" }}>
          {data?.checkedAtEt ? `Collected ${data.checkedAtEt} ET` : "—"}
          {data && data.nTasksUnclaimed > 0
            ? ` · ${data.nTasksUnclaimed} live task(s) claimed by no unit`
            : ""}
        </p>
      </div>
    </section>
  );
}
