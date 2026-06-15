"use client";

import type { KeyLevel } from "@/lib/state";

interface Props {
  data: any;
}

function levelTone(level: KeyLevel, isAbove: boolean | null): {
  fg: string;
  bg: string;
  border: string;
} {
  const isResistance =
    level.type === "resistance" || level.secondary_type === "resistance";
  if (isResistance) {
    return {
      fg: "var(--down)",
      bg: "rgba(239,68,68,0.08)",
      border: "rgba(239,68,68,0.2)",
    };
  }
  return {
    fg: "var(--up)",
    bg: "rgba(34,197,94,0.08)",
    border: "rgba(34,197,94,0.2)",
  };
}

export default function KeyLevels({ data }: Props) {
  const levels: KeyLevel[] = data?.keyLevels?.levels ?? [];
  const spy: number | undefined = data?.loopState?.spy_price;
  const now = new Date();

  const active = levels
    .filter((l) => {
      if (!l.expires_at) return true;
      return new Date(l.expires_at) >= now;
    })
    .sort((a, b) => b.price - a.price);

  return (
    <section
      className="tour-card flex flex-col p-4 min-h-0"
      data-accent="cyan"
    >
      <div className="flex items-center justify-between mb-3 flex-shrink-0">
        <span className="eyebrow">Key Levels</span>
        <span
          className="font-mono"
          style={{
            fontSize: 13,
            color: "var(--text-4)",
            letterSpacing: "0.1em",
          }}
        >
          {active.length} active
        </span>
      </div>

      <div className="flex-1 overflow-y-auto pr-1 min-h-0">
        {active.length === 0 ? (
          <div
            style={{
              color: "var(--text-3)",
              fontSize: 13,
              fontStyle: "italic",
              padding: "8px 0",
            }}
          >
            no active levels
          </div>
        ) : (
          <ul style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {active.map((l) => {
              const distance = spy != null ? l.price - spy : null;
              const isAbove = distance != null ? distance > 0 : null;
              const tone = levelTone(l, isAbove);
              const isResistance =
                l.type === "resistance" || l.secondary_type === "resistance";

              return (
                <li
                  key={`${l.price}-${l.type}`}
                  className="flex items-center"
                  style={{
                    padding: "7px 9px",
                    borderRadius: 6,
                    background: tone.bg,
                    border: `1px solid ${tone.border}`,
                    fontFamily: "var(--font-jetbrains-mono), monospace",
                    fontSize: 15,
                    gap: 8,
                  }}
                >
                  <span
                    style={{
                      width: 3,
                      height: 14,
                      background: tone.fg,
                      borderRadius: 2,
                      flexShrink: 0,
                    }}
                  />
                  <span
                    style={{
                      color: "var(--text-1)",
                      fontWeight: 700,
                      width: 56,
                      letterSpacing: "0.02em",
                    }}
                  >
                    {l.price.toFixed(2)}
                  </span>
                  <span
                    style={{
                      color: tone.fg,
                      fontSize: 12,
                      fontWeight: 700,
                      letterSpacing: "0.1em",
                    }}
                  >
                    {isResistance ? "R" : "S"}
                  </span>
                  {distance != null && (
                    <span
                      style={{
                        marginLeft: "auto",
                        color: "var(--text-3)",
                        fontSize: 14,
                      }}
                    >
                      {isAbove ? "+" : ""}
                      {distance.toFixed(2)}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {spy != null && (
        <div
          className="flex items-center justify-between"
          style={{
            marginTop: 12,
            paddingTop: 12,
            borderTop: "1px solid var(--border)",
            flexShrink: 0,
          }}
        >
          <span
            className="font-mono"
            style={{
              fontSize: 13,
              fontWeight: 700,
              letterSpacing: "0.15em",
              textTransform: "uppercase",
              color: "var(--text-3)",
            }}
          >
            SPY
          </span>
          <span
            className="font-display tabular-nums"
            style={{
              fontSize: 26,
              fontWeight: 700,
              color: "var(--amber)",
              letterSpacing: "-0.02em",
            }}
          >
            {spy.toFixed(2)}
          </span>
        </div>
      )}
    </section>
  );
}
