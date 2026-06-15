"use client";

interface Props {
  data: any;
}

interface CellProps {
  label: string;
  value: string;
  valueColor?: string;
  accent?: string;
}

function Cell({ label, value, valueColor = "var(--text-1)", accent }: CellProps) {
  return (
    <div
      style={{
        padding: "8px 16px",
        display: "flex",
        flexDirection: "column",
        gap: 2,
        position: "relative",
        minWidth: 100,
      }}
    >
      {accent && (
        <span
          style={{
            position: "absolute",
            left: 0,
            top: 12,
            bottom: 12,
            width: 2,
            background: accent,
            borderRadius: 2,
            boxShadow: `0 0 8px ${accent}`,
          }}
        />
      )}
      <span
        className="font-mono"
        style={{
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: "0.15em",
          textTransform: "uppercase",
          color: "var(--text-3)",
        }}
      >
        {label}
      </span>
      <span
        className="font-mono tabular-nums"
        style={{
          fontSize: 19,
          fontWeight: 700,
          color: valueColor,
          letterSpacing: "0.02em",
        }}
      >
        {value}
      </span>
    </div>
  );
}

export default function StatusBar({ data }: Props) {
  const cb = data?.circuitBreaker;
  const mode: string = data?.mode?.mode ?? "—";
  const tradesToday: number = data?.tradesToday ?? 0;
  const dailyMax = 3;
  const setup: string | null = data?.loopState?.setup_detected ?? null;
  const position = data?.currentPosition?.status;
  const positionLabel =
    !position || position === "null" || position === null
      ? "FLAT"
      : String(position).toUpperCase();

  const pnl = cb ? cb.current_equity - cb.starting_equity_today : 0;
  const pnlColor =
    pnl > 0
      ? "var(--up)"
      : pnl < 0
        ? "var(--down)"
        : "var(--text-1)";

  const modeColor =
    mode === "live-paper"
      ? "var(--up)"
      : mode === "live"
        ? "var(--down)"
        : "var(--amber)";

  const positionColor =
    positionLabel === "FLAT" ? "var(--text-3)" : "var(--cyan)";

  return (
    <footer
      className="tour-card flex items-center justify-between"
      data-accent="green"
      style={{
        flexShrink: 0,
        padding: "4px 8px",
      }}
    >
      <div className="flex items-center" style={{ gap: 4 }}>
        <Cell
          label="Equity"
          value={cb ? `$${cb.current_equity.toFixed(2)}` : "—"}
          valueColor="var(--amber)"
          accent="var(--amber)"
        />
        <span
          style={{ width: 1, height: 28, background: "var(--border)" }}
        />
        <Cell
          label="Daily P&L"
          value={cb ? `${pnl >= 0 ? "+" : ""}$${pnl.toFixed(2)}` : "—"}
          valueColor={pnlColor}
          accent={pnl !== 0 ? pnlColor : undefined}
        />
        <span
          style={{ width: 1, height: 28, background: "var(--border)" }}
        />
        <Cell label="Day Trades" value={`${tradesToday} / ${dailyMax}`} />
        <span
          style={{ width: 1, height: 28, background: "var(--border)" }}
        />
        <Cell
          label="Position"
          value={positionLabel}
          valueColor={positionColor}
          accent={positionLabel !== "FLAT" ? positionColor : undefined}
        />
      </div>

      <div className="flex items-center" style={{ gap: 4 }}>
        {setup && (
          <>
            <Cell
              label="Setup"
              value={setup.length > 20 ? setup.slice(0, 18) + "…" : setup}
              valueColor="var(--amber)"
              accent="var(--amber)"
            />
            <span
              style={{ width: 1, height: 28, background: "var(--border)" }}
            />
          </>
        )}
        <Cell
          label="Mode"
          value={mode.toUpperCase()}
          valueColor={modeColor}
          accent={modeColor}
        />
      </div>
    </footer>
  );
}
