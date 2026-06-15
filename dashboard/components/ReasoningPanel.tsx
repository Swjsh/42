"use client";

import type { HeartbeatLine } from "@/lib/scores";
import { parseScoresFromSpeech } from "@/lib/scores";

interface Props {
  data: any;
}

const STATUS_TONE: Record<
  string,
  { fg: string; bg: string; border: string }
> = {
  LONG: {
    fg: "var(--up)",
    bg: "rgba(34,197,94,0.10)",
    border: "rgba(34,197,94,0.35)",
  },
  BULLISH: {
    fg: "var(--up)",
    bg: "rgba(34,197,94,0.10)",
    border: "rgba(34,197,94,0.35)",
  },
  SHORT: {
    fg: "var(--down)",
    bg: "rgba(239,68,68,0.10)",
    border: "rgba(239,68,68,0.35)",
  },
  BEARISH: {
    fg: "var(--down)",
    bg: "rgba(239,68,68,0.10)",
    border: "rgba(239,68,68,0.35)",
  },
  ARMED: {
    fg: "var(--cyan)",
    bg: "rgba(34,211,238,0.10)",
    border: "rgba(34,211,238,0.35)",
  },
  PAUSED: {
    fg: "var(--amber)",
    bg: "rgba(245,158,11,0.10)",
    border: "rgba(245,158,11,0.35)",
  },
  FLAT: {
    fg: "var(--text-2)",
    bg: "rgba(255,255,255,0.03)",
    border: "var(--border)",
  },
};

function StatusBadge({ status }: { status: string }) {
  const tone = STATUS_TONE[status] ?? STATUS_TONE.FLAT;
  return (
    <div
      style={{
        padding: "10px 14px",
        background: tone.bg,
        border: `1px solid ${tone.border}`,
        borderRadius: 10,
        textAlign: "center",
        fontFamily: "var(--font-space-grotesk), sans-serif",
        fontSize: 21,
        fontWeight: 700,
        letterSpacing: "0.08em",
        color: tone.fg,
      }}
    >
      {status}
    </div>
  );
}

function ScoreBar({
  label,
  score,
  max,
  color,
  glow,
}: {
  label: string;
  score: number | null;
  max: number;
  color: string;
  glow: string;
}) {
  const pct = score == null ? 0 : (score / max) * 100;
  return (
    <div className="flex items-center gap-2.5">
      <span
        className="font-mono"
        style={{
          fontSize: 13,
          fontWeight: 700,
          letterSpacing: "0.1em",
          color: "var(--text-3)",
          width: 36,
        }}
      >
        {label}
      </span>
      <div
        style={{
          flex: 1,
          height: 16,
          background: "var(--bg-base)",
          border: "1px solid var(--border)",
          borderRadius: 5,
          overflow: "hidden",
          position: "relative",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: `linear-gradient(90deg, ${color}99, ${color})`,
            transition: "width 500ms cubic-bezier(0.4, 0, 0.2, 1)",
            boxShadow: pct > 0 ? `0 0 12px ${glow}` : "none",
          }}
        />
      </div>
      <span
        className="font-mono tabular-nums"
        style={{
          fontSize: 14,
          fontWeight: 700,
          color: score != null ? color : "var(--text-3)",
          width: 44,
          textAlign: "right",
        }}
      >
        {score == null ? "—" : `${score}/${max}`}
      </span>
    </div>
  );
}

export default function ReasoningPanel({ data }: Props) {
  const dialogue = data?.dialogue;
  const loopState = data?.loopState;
  const journal = data?.journal;
  const latest: HeartbeatLine | null = journal?.latest ?? null;

  const status: string =
    dialogue?.claude_status ??
    (loopState?.trade_active
      ? loopState.direction === "BULLISH"
        ? "LONG"
        : "SHORT"
      : loopState?.setup_detected && loopState?.trigger_fired
        ? "ARMED"
        : "FLAT");

  const reasoning: string =
    dialogue?.claude_reasoning ?? loopState?.notes ?? "Waiting for state…";

  const ribbon = loopState?.ribbon;

  const fromSpeech = parseScoresFromSpeech(
    dialogue?.agents?.heartbeat?.speech,
  );
  const bullScore = latest?.bull_score ?? fromSpeech.bull;
  const bearScore = latest?.bear_score ?? fromSpeech.bear;

  const ribbonColor =
    ribbon?.order === "BULLISH"
      ? "var(--up)"
      : ribbon?.order === "BEARISH"
        ? "var(--down)"
        : "var(--amber)";

  return (
    <section
      className="tour-card flex flex-col p-4 min-h-0"
      data-accent="cyan"
    >
      <div className="flex items-center justify-between mb-3 flex-shrink-0">
        <span className="eyebrow">Claude Reasoning</span>
        {latest && (
          <span
            className="font-mono"
            style={{
              fontSize: 12,
              color: "var(--text-4)",
              letterSpacing: "0.05em",
            }}
          >
            HB#{latest.tick}
          </span>
        )}
      </div>

      <div className="mb-3 flex-shrink-0">
        <StatusBadge status={status} />
      </div>

      <div
        className="flex flex-col gap-2 mb-3 flex-shrink-0"
        style={{ padding: "10px 0" }}
      >
        <ScoreBar
          label="BULL"
          score={bullScore ?? null}
          max={11}
          color="#22c55e"
          glow="rgba(34,197,94,0.3)"
        />
        <ScoreBar
          label="BEAR"
          score={bearScore ?? null}
          max={10}
          color="#ef4444"
          glow="rgba(239,68,68,0.3)"
        />
      </div>

      {ribbon && (
        <div
          className="flex-shrink-0"
          style={{
            padding: "10px 12px",
            background: "var(--bg-base)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            fontFamily: "var(--font-jetbrains-mono), monospace",
            fontSize: 14,
            display: "grid",
            gap: 5,
            marginBottom: 12,
          }}
        >
          <div className="flex justify-between items-center">
            <span style={{ color: "var(--text-3)", letterSpacing: "0.05em" }}>
              ribbon
            </span>
            <span style={{ color: ribbonColor, fontWeight: 700 }}>
              {ribbon.order}
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span style={{ color: "var(--text-3)" }}>spread</span>
            <span style={{ color: "var(--text-1)" }} className="tabular-nums">
              {ribbon.spread.toFixed(2)}¢
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span style={{ color: "var(--text-3)" }}>scan</span>
            <span style={{ color: "var(--amber)", fontWeight: 700 }}>
              {loopState?.scan_mode ?? "—"}
            </span>
          </div>
        </div>
      )}

      <div
        className="flex-1 overflow-y-auto pr-1 min-h-0"
        style={{
          fontSize: 16,
          lineHeight: 1.55,
          color: "var(--text-2)",
        }}
      >
        {reasoning}
      </div>

      {latest && (
        <div
          style={{
            marginTop: 10,
            paddingTop: 10,
            borderTop: "1px solid var(--border)",
            fontFamily: "var(--font-jetbrains-mono), monospace",
            fontSize: 13,
            color: "var(--text-4)",
            display: "flex",
            justifyContent: "space-between",
            flexShrink: 0,
          }}
        >
          <span>{latest.time_et} ET</span>
          <span style={{ color: "var(--cyan)", fontWeight: 700 }}>
            {latest.action}
          </span>
        </div>
      )}
    </section>
  );
}
