import Section from "./Section";
import type { PresenceView } from "@/lib/gamma-app-types";

const PLACEHOLDER = "—";

function ClockRow({
  label,
  have,
  need,
  extra,
}: {
  label: string;
  have: number | null;
  need: number;
  extra: string;
}) {
  const needSafe = need > 0 ? need : 1;
  const haveSafe = have && have > 0 ? have : 0;
  const pct = Math.max(0, Math.min(100, (Math.min(haveSafe, needSafe) / needSafe) * 100));
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="w-24 shrink-0 sm:w-28" style={{ color: "var(--text-2)" }}>
        {label}
      </span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full" style={{ background: "var(--border)" }}>
        <div
          className="h-full rounded-full transition-[width] duration-700 ease-out"
          style={{ width: `${pct}%`, background: "var(--cyan)" }}
        />
      </div>
      <span className="w-16 shrink-0 text-right font-mono text-xs" style={{ color: "var(--text-2)" }}>
        {have ?? PLACEHOLDER}/{need}
      </span>
      {extra && (
        <span
          className="hidden shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium sm:inline"
          style={{ background: "var(--amber-soft, rgba(245,158,11,.14))", color: "var(--amber)" }}
        >
          {extra}
        </span>
      )}
    </div>
  );
}

export default function MoneyView({ presence }: { presence: PresenceView | null }) {
  return (
    <div className="flex flex-col gap-8">
      <Section title="Goal">
        <p className="text-base" style={{ color: "var(--text-1)" }}>
          {presence?.goal_line ?? PLACEHOLDER}
        </p>
      </Section>

      <Section title="Today's tape">
        <p style={{ color: "var(--text-1)" }}>{presence?.tape_headline ?? PLACEHOLDER}</p>
        {presence && presence.tape_segments.length > 0 && (
          <ul className="flex flex-col gap-1 text-sm">
            {presence.tape_segments.map((s) => (
              <li key={s.account} style={{ color: "var(--text-2)" }}>
                {s.account}: {s.n} trade{s.n !== 1 ? "s" : ""},{" "}
                <span style={{ color: s.pnl > 0 ? "var(--up)" : s.pnl < 0 ? "var(--down)" : "var(--text-2)" }}>
                  {s.pnl >= 0 ? "+" : "-"}${Math.abs(s.pnl).toFixed(0)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="My clocks">
        <div className="flex flex-col gap-3">
          {(
            presence?.clocks ?? [
              { label: "SSR shadow", have: null, need: 20, extra: "" },
              { label: "MES mirror", have: null, need: 20, extra: "" },
              { label: "Cap re-check", have: null, need: 20, extra: "" },
            ]
          ).map((c) => (
            <ClockRow key={c.label} {...c} />
          ))}
        </div>
      </Section>
    </div>
  );
}
