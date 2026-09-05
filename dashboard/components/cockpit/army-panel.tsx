"use client";

import * as React from "react";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { AnimatedBeam } from "@/components/ui/animated-beam";
import { BorderBeam } from "@/components/ui/border-beam";
import type { CockpitPayload } from "@/lib/cockpit-data";
import { COMPANION, ageLabel } from "@/lib/cockpit-data";

/* ---------- types (loose -- payload is producer-authored JSON) ---------- */

type ArmySession = {
  session_id: string;
  name?: string;
  title?: string;
  kind?: string;
  alive?: boolean;
  activity?: string;
  worker_count?: number;
  worker_active?: number;
  context_pct?: number;
  last_write_min?: number;
  is_orchestrator?: boolean;
};

type ArmyWorker = {
  agent_id: string;
  session_id: string;
  agent_type?: string;
  model?: string;
  description?: string;
  purpose?: string;
  last_write?: string;
  active?: boolean;
};

type ArmyPulse = {
  ts: string;
  event: string;
  session_id?: string;
  agent_id?: string;
  to?: string;
  detail?: string;
};

/* ---------- humaniser: no raw commands/paths on the glass ---------- */

function humanizePulse(detail?: string): string {
  const d = (detail || "").trim();
  if (!d) return "Working";
  if (/^Editing\s/i.test(d)) return "Edited a file";
  const ran = d.match(/^Ran:\s*(.+)/i);
  if (ran) {
    const cmd = ran[1].replace(/^cd\s+\S+\s*(?:&&|;)\s*/i, "");
    if (/pytest/i.test(cmd)) return "Ran tests";
    if (/^git\b/i.test(cmd)) return "Ran a git command";
    if (/\bsed\b|\bcat\b|\bhead\b|\btype\b/i.test(cmd)) return "Read a file";
    if (/\bgrep\b|\brg\b|\bfindstr\b/i.test(cmd)) return "Searched the repo";
    if (/python(w)?(\.exe)?\b/i.test(cmd)) return "Ran a script";
    return "Ran a command";
  }
  if (/^Running\s/i.test(d)) return d.length > 36 ? "Ran a script" : d;
  return d.length > 42 ? d.slice(0, 40) + "…" : d;
}

function eventLabel(p: ArmyPulse): string {
  switch (p.event) {
    case "spawn":
      return "Spawned a worker";
    case "message":
      return "Sent a message";
    case "fail":
      return "Hit a failure";
    case "idle":
      return "Went idle";
    case "act":
    default:
      return humanizePulse(p.detail);
  }
}

function relTime(iso?: string): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const s = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.round(m / 60)}h ago`;
}

function initials(name?: string): string {
  const s = (name || "?").replace(/[^a-zA-Z0-9]/g, " ").trim();
  if (!s) return "?";
  const parts = s.split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

function activityColor(activity?: string, alive?: boolean): string {
  if (alive === false) return "var(--gc-text-3)";
  switch (activity) {
    case "active":
      return "var(--gc-cyan)";
    case "stale":
      return "var(--gc-warn)";
    case "idle":
    default:
      return "var(--gc-text-3)";
  }
}

/* ---------- live poll: /companion/api/army?since=cursor, 1s ---------- */

function useArmyLive(seedPulses: ArmyPulse[]) {
  const [pulses, setPulses] = React.useState<ArmyPulse[]>(seedPulses);
  const [live, setLive] = React.useState(false);
  const cursorRef = React.useRef<string>(
    seedPulses.length ? seedPulses[seedPulses.length - 1].ts : ""
  );
  const failedRef = React.useRef(0);
  const gammaToken = () =>
    (document.querySelector('meta[name="gamma-token"]') as HTMLMetaElement | null)?.content ?? "";

  React.useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      if (stopped) return;
      try {
        const r = await fetch(
          `${COMPANION}/api/army?since=${encodeURIComponent(cursorRef.current)}`,
          {
            cache: "no-store",
            // server.js authed(): every /api/* call must carry the page token.
            headers: { "x-gamma-token": gammaToken() },
          }
        );
        if (!r.ok) throw new Error(String(r.status));
        const j = await r.json();
        if (j && j.ok) {
          setLive(true);
          failedRef.current = 0;
          const rows: ArmyPulse[] = j.rows || [];
          if (rows.length) {
            setPulses((prev) => [...prev, ...rows].slice(-200));
            cursorRef.current = j.cursor || rows[rows.length - 1].ts;
          }
        } else {
          failedRef.current += 1;
        }
      } catch {
        failedRef.current += 1;
        if (failedRef.current >= 2) setLive(false);
      } finally {
        if (!stopped) timer = setTimeout(poll, 1000);
      }
    }

    timer = setTimeout(poll, 1000);
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { pulses, live };
}

/* ---------- component ---------- */

export function ArmyPanel({ data }: { data: CockpitPayload }) {
  const army = (data?.army || {}) as {
    orchestrator?: ArmySession | null;
    sessions?: ArmySession[];
    workers?: ArmyWorker[];
    pulses?: ArmyPulse[];
    peak_24h_sessions?: number;
  };

  const orchestrator = army.orchestrator || null;
  const sessions = (army.sessions || []).filter(
    (s) => !orchestrator || s.session_id !== orchestrator.session_id
  );
  const workers = army.workers || [];
  const seedPulses = army.pulses || [];
  const { pulses, live } = useArmyLive(seedPulses);
  const reducedMotion = useReducedMotion();

  const containerRef = React.useRef<HTMLDivElement>(null);
  const orcRef = React.useRef<HTMLDivElement>(null);
  const sessionRefs = React.useRef<Record<string, React.RefObject<HTMLDivElement | null>>>({});
  const workerRefs = React.useRef<Record<string, React.RefObject<HTMLDivElement | null>>>({});

  for (const s of sessions) {
    if (!sessionRefs.current[s.session_id]) {
      sessionRefs.current[s.session_id] = React.createRef<HTMLDivElement>();
    }
  }
  for (const w of workers) {
    if (!workerRefs.current[w.agent_id]) {
      workerRefs.current[w.agent_id] = React.createRef<HTMLDivElement>();
    }
  }

  const now = Date.now();
  const hotSessions = React.useMemo(() => {
    const set = new Set<string>();
    for (const p of pulses.slice(-40)) {
      const t = Date.parse(p.ts);
      if (!Number.isNaN(t) && now - t < 10_000 && p.session_id) set.add(p.session_id);
    }
    return set;
  }, [pulses, now]);

  const recentPulses = React.useMemo(() => pulses.slice(-8).reverse(), [pulses]);

  const hasAgents = !!orchestrator || sessions.length > 0;

  const workersBySession = React.useMemo(() => {
    const m = new Map<string, ArmyWorker[]>();
    for (const w of workers) {
      const arr = m.get(w.session_id) || [];
      arr.push(w);
      m.set(w.session_id, arr);
    }
    return m;
  }, [workers]);

  return (
    <div className="gc-glass relative overflow-hidden rounded-2xl border border-[var(--gc-line)] p-4 sm:p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="gc-grad-text text-sm font-semibold tracking-wide">Agent map</h2>
        <div className="flex items-center gap-2">
          <Badge
            variant="outline"
            className="gap-1.5 border-[var(--gc-line-strong)] text-[11px] font-medium"
            style={{ color: live ? "var(--gc-cyan)" : "var(--gc-text-3)" }}
          >
            <span
              className="inline-block h-1.5 w-1.5 rounded-full"
              style={{
                background: live ? "var(--gc-cyan)" : "var(--gc-text-3)",
                boxShadow: live ? "0 0 6px var(--gc-cyan)" : "none",
              }}
            />
            {live ? "Live" : "Snapshot"}
          </Badge>
          {typeof army.peak_24h_sessions === "number" && (
            <span className="text-[11px] text-[var(--gc-text-3)]">
              peak 24h: {army.peak_24h_sessions}
            </span>
          )}
        </div>
      </div>

      {!hasAgents ? (
        <div className="flex h-40 items-center justify-center text-sm text-[var(--gc-text-3)]">
          No agents running
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {/* node graph: orchestrator on top, session row below, beams between */}
          <div ref={containerRef} className="relative flex flex-col items-center gap-3">
            {/* orchestrator node */}
            {orchestrator && (
              <div
                ref={orcRef}
                className="relative flex w-full max-w-[220px] shrink-0 flex-col items-center gap-1.5 rounded-xl border border-[var(--gc-line-strong)] bg-[var(--gc-panel)] p-3"
              >
                {orchestrator.activity === "active" && (
                  <BorderBeam size={60} duration={4} colorFrom="var(--gc-indigo)" colorTo="var(--gc-cyan)" />
                )}
                <Avatar className="h-12 w-12 border-2" style={{ borderColor: "var(--gc-violet)" }}>
                  <AvatarFallback
                    className="text-sm font-semibold"
                    style={{ background: "var(--gc-grad)", color: "var(--gc-text)" }}
                  >
                    {initials(orchestrator.name)}
                  </AvatarFallback>
                </Avatar>
                <div className="w-full min-w-0 text-center">
                  <div className="truncate text-[13px] font-semibold text-[var(--gc-text)]">
                    {orchestrator.name || "Orchestrator"}
                  </div>
                  <div className="truncate text-[11px] text-[var(--gc-text-3)]">
                    {orchestrator.title || "Orchestrator"}
                  </div>
                </div>
                {typeof orchestrator.context_pct === "number" && (
                  <div className="flex w-full items-center gap-2">
                    <Progress value={Math.min(100, orchestrator.context_pct)} className="h-1 flex-1" />
                    <span className="shrink-0 text-[10px] tabular-nums text-[var(--gc-text-3)]">
                      {Math.round(orchestrator.context_pct)}%
                    </span>
                  </div>
                )}
                <span
                  className="absolute right-2 top-2 inline-block h-2 w-2 rounded-full"
                  style={{
                    background: activityColor(orchestrator.activity, orchestrator.alive),
                    boxShadow: `0 0 6px ${activityColor(orchestrator.activity, orchestrator.alive)}`,
                  }}
                />
              </div>
            )}

            {/* session nodes: horizontal row, each compact */}
            {sessions.length > 0 && (
              <div className="flex w-full flex-wrap items-start justify-center gap-2">
                {sessions.map((s) => {
                  const sessionWorkers = workersBySession.get(s.session_id) || [];
                  return (
                    <div
                      key={s.session_id}
                      ref={sessionRefs.current[s.session_id]}
                      title={sessionWorkers.map((w) => w.purpose || w.description || w.agent_type).filter(Boolean).join(", ")}
                      className="flex w-24 max-w-[96px] shrink-0 flex-col items-center gap-1 rounded-lg border border-[var(--gc-line)] bg-[var(--gc-panel)] p-2"
                    >
                      <div className="relative">
                        <Avatar className="h-9 w-9">
                          <AvatarFallback
                            className="text-[10px] font-semibold"
                            style={{ background: "var(--gc-panel-solid)", color: "var(--gc-text-2)" }}
                          >
                            {initials(s.name)}
                          </AvatarFallback>
                        </Avatar>
                        <span
                          className="absolute -right-0.5 -top-0.5 inline-block h-2 w-2 rounded-full"
                          style={{
                            background: activityColor(s.activity, s.alive),
                            boxShadow: `0 0 6px ${activityColor(s.activity, s.alive)}`,
                          }}
                        />
                      </div>
                      <div className="w-full min-w-0 text-center">
                        <div className="truncate text-[13px] font-medium text-[var(--gc-text)]">
                          {s.title || s.name || "Session"}
                        </div>
                      </div>
                      {typeof s.context_pct === "number" && (
                        <Progress value={Math.min(100, s.context_pct)} className="h-1 w-full" />
                      )}
                      <span className="truncate text-[10px] text-[var(--gc-text-3)]">
                        {s.worker_count ?? 0} workers
                      </span>
                    </div>
                  );
                })}
              </div>
            )}

            {!reducedMotion &&
              orchestrator &&
              sessions.map((s) =>
                hotSessions.has(s.session_id) ? (
                  <AnimatedBeam
                    key={s.session_id}
                    containerRef={containerRef}
                    fromRef={orcRef}
                    toRef={sessionRefs.current[s.session_id]}
                    duration={2.5}
                    gradientStartColor="var(--gc-indigo)"
                    gradientStopColor="var(--gc-cyan)"
                  />
                ) : null
              )}
          </div>

          {/* pulse feed: bottom strip, capped short */}
          <div className="w-full min-w-0">
            <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-[var(--gc-text-3)]">
              Recent activity
            </div>
            <ScrollArea className="h-[120px] rounded-xl border border-[var(--gc-line)] bg-[var(--gc-panel)] p-1.5">
              <AnimatePresence initial={false}>
                {recentPulses.length === 0 && (
                  <div className="p-2 text-[12px] text-[var(--gc-text-3)]">No recent activity</div>
                )}
                {recentPulses.slice(0, 5).map((p, i) => (
                  <motion.div
                    key={`${p.ts}-${p.session_id}-${i}`}
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.2 }}
                    className="flex min-w-0 items-center justify-between gap-2 border-b border-[var(--gc-line)] px-1.5 py-1 last:border-0"
                  >
                    <span className="min-w-0 flex-1 truncate text-[13px] text-[var(--gc-text-2)]">
                      {eventLabel(p)}
                    </span>
                    <span className="shrink-0 text-[11px] text-[var(--gc-text-3)]">
                      {relTime(p.ts) || ageLabel(p.ts)}
                    </span>
                  </motion.div>
                ))}
              </AnimatePresence>
            </ScrollArea>
          </div>
        </div>
      )}
    </div>
  );
}

export default ArmyPanel;
