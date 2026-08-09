import Section from "./Section";
import ExpandableCard from "./ExpandableCard";
import type { ThisWeekItem } from "@/lib/gamma-app-types";

const PRIORITY_COLOR: Record<string, string> = {
  CRITICAL: "var(--down)",
  HIGH: "var(--amber)",
  MED: "var(--cyan)",
  MEDIUM: "var(--cyan)",
  LOW: "var(--text-4)",
};

/** Each queue item as an "ad tile": a short headline (the item's own long
 * engineering writeup, trimmed to one line), always visible; click for the
 * full clause plus the item's id/depends/status metadata -- the technical
 * identifiers (e.g. "G1-FILTER5-VS-REJECTION-SETUPS") live in the
 * breakdown, not the glance view. See lib/this-week.ts for the split. */
export default function ThisWeekCard({ items }: { items: ThisWeekItem[] }) {
  return (
    <Section title="How I make us money this week">
      {items.length > 0 ? (
        <div className="flex flex-col gap-2">
          {items.map((it, i) => (
            <ExpandableCard
              key={it.id}
              icon={
                <span className="mt-0.5 shrink-0 font-mono text-xs" style={{ color: "var(--text-4)" }}>
                  {i + 1}.
                </span>
              }
              headline={it.text}
              breakdown={
                it.detail || it.id ? (
                  <>
                    {it.detail}
                    {it.detail && <br />}
                    <span className="font-mono" style={{ color: "var(--text-4)" }}>
                      {it.id}
                    </span>
                  </>
                ) : undefined
              }
              aside={
                <span
                  className="mt-0.5 shrink-0 text-[11px] font-semibold"
                  style={{ color: PRIORITY_COLOR[it.priority] ?? "var(--text-4)" }}
                >
                  {it.priority}
                </span>
              }
            />
          ))}
        </div>
      ) : (
        <p className="text-sm" style={{ color: "var(--text-3)" }}>
          —
        </p>
      )}
    </Section>
  );
}
