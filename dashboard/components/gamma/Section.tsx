interface SectionProps {
  title: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}

/** Shared section shell for the Gamma App: a small uppercase label + optional
 * right-aligned meta, generous vertical rhythm. Deliberately plain -- no card
 * border/gradient chrome (that's the busier "Trade House" language this page
 * is intentionally NOT using). */
export default function Section({ title, right, children }: SectionProps) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <h2
          className="text-[11px] font-semibold uppercase tracking-[0.16em]"
          style={{ color: "var(--text-3)" }}
        >
          {title}
        </h2>
        {right && (
          <span className="text-xs" style={{ color: "var(--text-4)" }}>
            {right}
          </span>
        )}
      </div>
      {children}
    </section>
  );
}
