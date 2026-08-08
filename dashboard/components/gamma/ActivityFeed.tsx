"use client";

import { useEffect, useRef, useState } from "react";
import * as Tooltip from "@radix-ui/react-tooltip";
import { GitCommitVertical, MessageSquare, DollarSign, FlaskConical, type LucideIcon } from "lucide-react";
import type { ActivityEvent, ActivityEventType } from "@/lib/gamma-app-types";

const TYPE_META: Record<ActivityEventType, { icon: LucideIcon; color: string }> = {
  commit: { icon: GitCommitVertical, color: "var(--text-3)" },
  narrative: { icon: MessageSquare, color: "var(--cyan)" },
  trade: { icon: DollarSign, color: "var(--text-1)" },
  shadow_fill: { icon: FlaskConical, color: "var(--violet)" },
};

function relativeTime(iso: string, now: number): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const diffSec = Math.max(0, Math.round((now - then) / 1000));
  if (diffSec < 60) return "just now";
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  return `${diffDay}d ago`;
}

function absoluteTime(iso: string): string {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "—";
  return then.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

interface ActivityFeedProps {
  events: ActivityEvent[];
  nowMs: number;
}

/** THE LIVE ACTIVITY STREAM -- the centerpiece: a reverse-chron feed of real
 * events (commits, first-person narrative, real fills, shadow-strategy fills),
 * each row icon-coded by type and colored by tone (win/loss) where one
 * genuinely exists. Every row here traces to a real file on disk -- see
 * lib/activity-feed.ts for the four sources and how each is filtered.
 * Hovering the relative-time label shows the absolute timestamp (Tooltip).
 * A row whose atIso is new since the last render gets a brief enter
 * animation; the rest of an unchanged feed never re-animates on a poll. */
export default function ActivityFeed({ events, nowMs }: ActivityFeedProps) {
  const prevTopIso = useRef<string | null>(null);
  const [newestIso, setNewestIso] = useState<string | null>(null);

  useEffect(() => {
    const top = events[0]?.atIso ?? null;
    if (top && top !== prevTopIso.current) {
      setNewestIso(prevTopIso.current === null ? null : top); // don't animate the very first paint
      prevTopIso.current = top;
    }
  }, [events]);

  return (
    <>
      {events.length > 0 ? (
        <Tooltip.Provider delayDuration={200}>
          <ul className="flex flex-col">
            {events.map((e, i) => {
              const meta = TYPE_META[e.type];
              const Icon = meta.icon;
              const toneColor = e.tone === "up" ? "var(--up)" : e.tone === "down" ? "var(--down)" : undefined;
              const isNew = e.atIso === newestIso && i === 0;
              return (
                <li
                  key={`${e.type}-${e.atIso}-${i}`}
                  className={`flex items-start gap-3 py-2.5${isNew ? " activity-row-in" : ""}`}
                  style={{ borderTop: i > 0 ? "1px solid var(--border)" : undefined }}
                >
                  <Icon size={15} className="mt-0.5 shrink-0" style={{ color: meta.color }} aria-hidden />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm leading-snug" style={{ color: toneColor ?? "var(--text-1)" }}>
                      {e.title}
                    </p>
                    {e.subtitle && (
                      <p className="mt-0.5 text-xs" style={{ color: "var(--text-4)" }}>
                        {e.subtitle}
                      </p>
                    )}
                    {e.detail && (
                      <p className="mt-1 text-xs leading-relaxed" style={{ color: "var(--text-3)" }}>
                        {e.detail}
                      </p>
                    )}
                  </div>
                  <Tooltip.Root>
                    <Tooltip.Trigger asChild>
                      <span
                        tabIndex={0}
                        className="shrink-0 whitespace-nowrap text-xs"
                        style={{ color: "var(--text-4)" }}
                      >
                        {relativeTime(e.atIso, nowMs)}
                      </span>
                    </Tooltip.Trigger>
                    <Tooltip.Portal>
                      <Tooltip.Content
                        side="top"
                        sideOffset={6}
                        className="rounded-md px-2 py-1 text-xs"
                        style={{
                          background: "var(--bg-overlay)",
                          color: "var(--text-1)",
                          border: "1px solid var(--border-mid)",
                          boxShadow: "var(--shadow-sm)",
                        }}
                      >
                        {absoluteTime(e.atIso)}
                        <Tooltip.Arrow style={{ fill: "var(--bg-overlay)" }} />
                      </Tooltip.Content>
                    </Tooltip.Portal>
                  </Tooltip.Root>
                </li>
              );
            })}
          </ul>
        </Tooltip.Provider>
      ) : (
        <p className="text-sm" style={{ color: "var(--text-3)" }}>
          Nothing to show yet — check back after the next fire.
        </p>
      )}
    </>
  );
}
