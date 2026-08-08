"use client";

import Section from "./Section";
import type { ActivityEvent, ActivityEventType } from "@/lib/gamma-app-types";

const TYPE_META: Record<ActivityEventType, { icon: string; label: string; color: string }> = {
  commit: { icon: "🧾", label: "shipped", color: "var(--text-3)" },
  narrative: { icon: "💬", label: "said", color: "var(--cyan)" },
  trade: { icon: "💵", label: "traded", color: "var(--text-1)" },
  shadow_fill: { icon: "🧪", label: "shadow", color: "var(--violet, #a78bfa)" },
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

interface ActivityFeedProps {
  events: ActivityEvent[];
  nowMs: number;
}

/** THE LIVE ACTIVITY STREAM -- the centerpiece: a reverse-chron feed of real
 * events (commits, first-person narrative, real fills, shadow-strategy fills),
 * each card icon-coded by type and colored by tone (win/loss) where one
 * genuinely exists. Every row here traces to a real file on disk -- see
 * lib/activity-feed.ts for the four sources and how each is filtered. */
export default function ActivityFeed({ events, nowMs }: ActivityFeedProps) {
  return (
    <Section title="Live activity">
      {events.length > 0 ? (
        <ul className="flex flex-col">
          {events.map((e, i) => {
            const meta = TYPE_META[e.type];
            const toneColor = e.tone === "up" ? "var(--up)" : e.tone === "down" ? "var(--down)" : undefined;
            return (
              <li
                key={`${e.type}-${e.atIso}-${i}`}
                className="flex items-start gap-3 py-2.5"
                style={{ borderTop: i > 0 ? "1px solid var(--border)" : undefined }}
              >
                <span className="mt-0.5 shrink-0 text-base leading-none" aria-hidden>
                  {meta.icon}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm leading-snug" style={{ color: toneColor ?? "var(--text-1)" }}>
                    {e.title}
                  </p>
                  {e.subtitle && (
                    <p className="mt-0.5 text-xs" style={{ color: "var(--text-4)" }}>
                      {e.subtitle}
                    </p>
                  )}
                </div>
                <span className="shrink-0 whitespace-nowrap text-xs" style={{ color: "var(--text-4)" }}>
                  {relativeTime(e.atIso, nowMs)}
                </span>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-sm" style={{ color: "var(--text-3)" }}>
          Nothing to show yet — check back after the next fire.
        </p>
      )}
    </Section>
  );
}
