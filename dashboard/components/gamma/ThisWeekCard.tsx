import Section from "./Section";
import type { ThisWeekItem } from "@/lib/gamma-app-types";

const PRIORITY_COLOR: Record<string, string> = {
  CRITICAL: "var(--down)",
  HIGH: "var(--amber)",
  MED: "var(--cyan)",
  MEDIUM: "var(--cyan)",
  LOW: "var(--text-4)",
};

export default function ThisWeekCard({ items }: { items: ThisWeekItem[] }) {
  return (
    <Section title="How I make us money this week">
      {items.length > 0 ? (
        <ol className="flex flex-col gap-2">
          {items.map((it, i) => (
            <li key={it.id} className="flex items-start gap-3 text-sm">
              <span className="mt-0.5 shrink-0 font-mono" style={{ color: "var(--text-4)" }}>
                {i + 1}.
              </span>
              <div className="flex flex-col gap-0.5">
                <span style={{ color: "var(--text-1)" }}>{it.text}</span>
                <span className="flex items-center gap-2 text-[11px]" style={{ color: "var(--text-4)" }}>
                  <span style={{ color: PRIORITY_COLOR[it.priority] ?? "var(--text-4)" }}>{it.priority}</span>
                  <span className="font-mono">{it.id}</span>
                </span>
                {it.detail && (
                  <span className="text-[11px] leading-relaxed" style={{ color: "var(--text-3)" }}>
                    {it.detail}
                  </span>
                )}
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm" style={{ color: "var(--text-3)" }}>
          —
        </p>
      )}
    </Section>
  );
}
