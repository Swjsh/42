"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import ChartPanel from "./ChartPanel";

// React 19 removed global JSX namespace — alias to keep function signatures intact
type ReactElement = React.JSX.Element;

// =============================================================================
// TYPES
// =============================================================================

export interface PersonaState {
  name: string;
  emoji: string;
  color: string;
  role: string;
  soulFile: string;
  schedule: string;
  status: "GREEN" | "YELLOW" | "RED" | "IDLE";
  lastFireISO: string | null;
  lastFireResult: string;
  deliverable: {
    path: string;
    exists: boolean;
    mtimeISO: string | null;
    ageMin: number | null;
  };
  logTail: Array<Record<string, unknown>>;
  recentOutput: string | null;
  guardrailsDeniedTools: string[];
}

export interface Handoff {
  from: string;
  to: string;
  status: "OK" | "STALE" | "MISSING";
  evidence: string;
  reasonIfStale: string | null;
}

export interface NextFire {
  task: string;
  nextRun: string | null;
  lastRun: string | null;
  result: number | null;
}

export interface PersonasBoard {
  generatedAt: string;
  todayET: string;
  personas: PersonaState[];
  handoffs: Handoff[];
  scheduledTasks: {
    auditHealth: string;
    activeCount: number;
    flagCount: number;
    nextFires: NextFire[];
  };
  status: { tail: string };
  pendingWork: {
    chefInbox: Array<{ name: string; mtimeISO: string; ageMin: number; sizeBytes: number }>;
    chefCandidates: Array<{ name: string; mtimeISO: string; sizeBytes: number }>;
    treasuryDrafts: { exists: boolean; mtimeISO: string | null; preview: string | null };
    mistakesTail: string | null;
  };
  errors: string[];
}

// =============================================================================
// DESIGN TOKENS — matches TradingFloor aesthetic
// =============================================================================

const C = {
  bgDeep:      "#040806",
  bgPanel:     "linear-gradient(180deg, #061410 0%, #081a14 100%)",
  borderPanel: "rgba(60,180,110,0.28)",
  glowPanel:   "0 0 24px rgba(40,200,120,0.08), inset 0 0 0 1px rgba(60,120,80,0.08)",
  green:       "#7ee0a8",
  greenDim:    "#4a7a60",
  greenMid:    "#55a870",
  body:        "#d4eadb",
  dim:         "#7a9a85",
  statusGreen: "#22c55e",
  statusYellow:"#eab308",
  statusRed:   "#ef4444",
  statusIdle:  "#4b5563",
  amber:       "#fbbf24",
  mono: "var(--font-jetbrains-mono), 'JetBrains Mono', ui-monospace, Menlo, monospace",
} as const;

const GLOBAL_CSS = `
  @keyframes ledPulse {
    0%, 100% { opacity: 1; transform: scale(1); box-shadow: inherit; }
    50%       { opacity: 0.5; transform: scale(0.85); }
  }
  @keyframes borderGlow {
    0%, 100% { box-shadow: 0 0 0 1px rgba(34,197,94,0.15), 0 0 20px rgba(34,197,94,0.06); }
    50%       { box-shadow: 0 0 0 1px rgba(34,197,94,0.35), 0 0 32px rgba(34,197,94,0.14); }
  }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation: none !important; transition: none !important; }
  }
  ::-webkit-scrollbar { width: 4px; height: 4px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: rgba(126,224,168,0.2); border-radius: 2px; }
`;

// =============================================================================
// UTILITIES
// =============================================================================

function statusColor(s: string): string {
  if (s === "GREEN" || s === "OK")      return C.statusGreen;
  if (s === "YELLOW" || s === "STALE")  return C.statusYellow;
  if (s === "RED" || s === "MISSING")   return C.statusRed;
  return C.statusIdle;
}

function relTime(iso: string | null): string {
  if (!iso) return "never";
  const min = (Date.now() - new Date(iso).getTime()) / 60000;
  if (min < 0)        return "soon";
  if (min < 1)        return "just now";
  if (min < 60)       return `${Math.floor(min)}m ago`;
  if (min < 1440)     return `${Math.floor(min / 60)}h ${Math.floor(min % 60)}m ago`;
  return `${Math.floor(min / 1440)}d ago`;
}

function relFuture(iso: string | null): string {
  if (!iso) return "-";
  const min = (new Date(iso).getTime() - Date.now()) / 60000;
  if (min < 0)    return "now";
  if (min < 1)    return "<1m";
  if (min < 60)   return `${Math.floor(min)}m`;
  if (min < 1440) return `${Math.floor(min / 60)}h ${Math.floor(min % 60)}m`;
  return `${Math.floor(min / 1440)}d`;
}

/** Match persona by slug prefix — handles "Gamma (Manager)" → "gamma" */
function slugMatch(personaName: string, slug: string): boolean {
  return personaName.toLowerCase().split(/[\s(]/)[0] === slug.toLowerCase();
}

/** Strip raw markdown/leaderboard blurb from recentOutput for clean display */
function cleanOutput(raw: string | null, lastFireResult: string): string {
  if (!raw) return "";
  // If the raw output looks like markdown file content, prefer the fire result
  if (raw.startsWith("sim hasn") || raw.startsWith("#") || raw.length > 400) {
    return lastFireResult || raw.slice(0, 200);
  }
  return raw.slice(0, 300);
}

// =============================================================================
// LIVE CLOCK HOOK
// =============================================================================

function useEtClock(): string {
  const [t, setT] = useState("--:--:--");
  useEffect(() => {
    const tick = () =>
      setT(new Date().toLocaleTimeString("en-US", { hour12: false, timeZone: "America/New_York" }));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return t;
}

// =============================================================================
// LED DOT
// =============================================================================

function LedDot({
  color,
  pulse = false,
  size = 10,
}: {
  color: string;
  pulse?: boolean;
  size?: number;
}): ReactElement {
  return (
    <span
      style={{
        display: "inline-block",
        width: size,
        height: size,
        borderRadius: "50%",
        background: color,
        boxShadow: `0 0 8px ${color}, 0 0 3px ${color}`,
        flexShrink: 0,
        animation: pulse ? "ledPulse 1.8s ease-in-out infinite" : "none",
      }}
    />
  );
}

// =============================================================================
// STATUS BADGE
// =============================================================================

function StatusBadge({ status }: { status: string }): ReactElement {
  const color = statusColor(status);
  const isPulse = status === "GREEN";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 10px",
        background: `${color}12`,
        border: `1px solid ${color}40`,
        borderRadius: 4,
        fontFamily: C.mono,
        fontSize: 11,
        fontWeight: 700,
        color,
        letterSpacing: "0.12em",
        whiteSpace: "nowrap",
        flexShrink: 0,
      }}
    >
      <LedDot color={color} pulse={isPulse} size={7} />
      {status}
    </span>
  );
}

// =============================================================================
// SECTION LABEL (horizontal rule with title)
// =============================================================================

function SectionLabel({ title, accent }: { title: string; accent?: string }): ReactElement {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        marginBottom: 12,
      }}
    >
      <span
        style={{
          width: 3,
          height: 16,
          background: accent ?? C.green,
          boxShadow: `0 0 8px ${accent ?? C.green}80`,
          borderRadius: 1,
          flexShrink: 0,
        }}
      />
      <span
        style={{
          fontFamily: C.mono,
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: "0.22em",
          color: C.green,
          textTransform: "uppercase",
        }}
      >
        {title}
      </span>
      <span
        style={{
          flex: 1,
          height: 1,
          background: "linear-gradient(90deg, rgba(60,180,110,0.25) 0%, transparent 80%)",
        }}
      />
    </div>
  );
}

// =============================================================================
// PANEL WRAPPER
// =============================================================================

function Panel({
  children,
  style,
  accent,
  featured,
}: {
  children: React.ReactNode;
  style?: React.CSSProperties;
  accent?: string;
  featured?: boolean;
}): ReactElement {
  return (
    <div
      style={{
        position: "relative",
        background: C.bgPanel,
        border: `1px solid ${accent ? `${accent}45` : C.borderPanel}`,
        borderLeft: accent ? `3px solid ${accent}` : `1px solid ${C.borderPanel}`,
        borderRadius: 6,
        boxShadow: featured
          ? `0 0 32px ${accent ?? C.green}25, inset 0 0 0 1px ${accent ?? C.green}12`
          : C.glowPanel,
        ...(featured && { animation: "borderGlow 3s ease-in-out infinite" }),
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

// =============================================================================
// PERSONA CARD
// =============================================================================

function PersonaCard({
  persona,
  featured = false,
}: {
  persona: PersonaState;
  featured?: boolean;
}): ReactElement {
  const [hover, setHover] = useState(false);
  const sc = statusColor(persona.status);
  const fireMin = persona.lastFireISO
    ? (Date.now() - new Date(persona.lastFireISO).getTime()) / 60000
    : Infinity;
  const shouldPulse = persona.status === "GREEN" && fireMin < 60;
  const output = cleanOutput(persona.recentOutput, persona.lastFireResult);

  return (
    <Panel
      accent={persona.color}
      featured={featured}
      style={{ minHeight: 0 }}
    >
      <div
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        style={{
          padding: featured ? "16px 18px" : "14px 16px",
          display: "flex",
          flexDirection: "column",
          gap: 10,
          height: "100%",
          transition: "background 0.15s ease",
          background: hover ? `${persona.color}08` : "transparent",
        }}
      >
        {/* NAME ROW */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span
            style={{
              fontSize: featured ? 24 : 20,
              lineHeight: 1,
              filter: `drop-shadow(0 0 8px ${persona.color}66)`,
              flexShrink: 0,
            }}
            aria-hidden="true"
          >
            {persona.emoji}
          </span>

          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                fontFamily: C.mono,
                fontSize: featured ? 15 : 13,
                fontWeight: 700,
                letterSpacing: "0.08em",
                color: persona.color,
                textTransform: "uppercase",
                textShadow: `0 0 10px ${persona.color}55`,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {persona.name}
            </div>
            <div
              style={{
                fontFamily: C.mono,
                fontSize: 11,
                color: C.dim,
                marginTop: 2,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
              title={persona.role}
            >
              {persona.role}
            </div>
          </div>

          <StatusBadge status={persona.status} />
        </div>

        {/* META GRID */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "max-content 1fr",
            columnGap: 12,
            rowGap: 3,
            fontFamily: C.mono,
            fontSize: 12,
          }}
        >
          <span style={{ color: C.greenDim, letterSpacing: "0.04em" }}>last fire</span>
          <span style={{ color: C.body }}>{relTime(persona.lastFireISO)}</span>

          <span style={{ color: C.greenDim, letterSpacing: "0.04em" }}>result</span>
          <span
            style={{
              color: C.body,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
            title={persona.lastFireResult}
          >
            {persona.lastFireResult || "—"}
          </span>

          <span style={{ color: C.greenDim, letterSpacing: "0.04em" }}>file</span>
          <span
            style={{
              color: persona.deliverable.exists ? C.statusGreen : C.greenDim,
            }}
          >
            {persona.deliverable.exists
              ? `✓ ${persona.deliverable.ageMin != null ? Math.floor(persona.deliverable.ageMin) + "m old" : "exists"}`
              : "no output yet"}
          </span>
        </div>

        {/* OUTPUT AREA */}
        <div
          style={{
            background: "rgba(0,0,0,0.38)",
            border: "1px solid rgba(60,180,110,0.14)",
            borderRadius: 4,
            padding: "8px 10px",
            fontFamily: C.mono,
            fontSize: 12,
            color: C.dim,
            maxHeight: hover ? 180 : (featured ? 80 : 64),
            minHeight: featured ? 64 : 52,
            overflowY: "auto",
            whiteSpace: "pre-wrap",
            lineHeight: 1.5,
            transition: "max-height 0.22s ease",
            flex: 1,
          }}
        >
          {output ? (
            output
          ) : (
            <span style={{ color: C.greenDim, fontStyle: "italic" }}>
              waiting for first fire…
            </span>
          )}
        </div>

        {/* SCHEDULE FOOTER */}
        <div
          style={{
            fontFamily: C.mono,
            fontSize: 11,
            color: C.greenDim,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            borderTop: "1px solid rgba(60,180,110,0.10)",
            paddingTop: 8,
          }}
          title={persona.schedule}
        >
          ⏱ {persona.schedule}
        </div>
      </div>
    </Panel>
  );
}

// =============================================================================
// HANDOFF PIPELINE
// =============================================================================

function HandoffPipeline({ handoffs }: { handoffs: Handoff[] }): ReactElement {
  if (!handoffs.length) return <div style={{ color: C.dim, fontFamily: C.mono, fontSize: 13 }}>no handoffs</div>;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "stretch",
        gap: 0,
        overflowX: "auto",
        paddingBottom: 4,
      }}
    >
      {handoffs.map((h, i) => {
        const color = statusColor(h.status);
        const isLast = i === handoffs.length - 1;
        return (
          <React.Fragment key={`${h.from}-${h.to}`}>
            <div
              title={h.reasonIfStale ?? h.evidence}
              style={{
                flex: "1 1 0",
                minWidth: 120,
                background: `${color}0a`,
                border: `1px solid ${color}35`,
                borderLeft: `3px solid ${color}`,
                borderRadius: 5,
                padding: "10px 14px",
                display: "flex",
                flexDirection: "column",
                gap: 5,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <LedDot color={color} size={7} />
                <span
                  style={{
                    fontFamily: C.mono,
                    fontSize: 12,
                    fontWeight: 700,
                    color: C.body,
                    letterSpacing: "0.04em",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {h.from}
                </span>
                <span style={{ flex: 1 }} />
                <span
                  style={{
                    fontFamily: C.mono,
                    fontSize: 10,
                    fontWeight: 700,
                    color,
                    letterSpacing: "0.12em",
                  }}
                >
                  {h.status}
                </span>
              </div>
              <div
                style={{
                  fontFamily: C.mono,
                  fontSize: 11,
                  color: C.dim,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                → {h.to}
              </div>
              {h.reasonIfStale && (
                <div
                  style={{
                    fontFamily: C.mono,
                    fontSize: 11,
                    color: C.statusYellow,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {h.reasonIfStale}
                </div>
              )}
            </div>
            {!isLast && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  padding: "0 8px",
                  color: C.greenDim,
                  fontFamily: C.mono,
                  fontSize: 16,
                  flexShrink: 0,
                }}
              >
                ›
              </div>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// =============================================================================
// NEXT FIRES PANEL
// =============================================================================

function NextFiresPanel({ fires, activeCount }: { fires: NextFire[]; activeCount: number }): ReactElement {
  const sorted = useMemo(
    () =>
      [...fires]
        .filter((f) => f.nextRun)
        .sort(
          (a, b) =>
            new Date(a.nextRun!).getTime() - new Date(b.nextRun!).getTime()
        )
        .slice(0, 12),
    [fires]
  );

  return (
    <Panel style={{ padding: 18 }}>
      <SectionLabel title={`Next Fires — ${activeCount} active`} />
      <div style={{ flex: 1, overflowY: "auto" }}>
        {sorted.map((f) => {
          const stale = f.result !== null && f.result !== 0;
          return (
            <div
              key={f.task}
              style={{
                display: "grid",
                gridTemplateColumns: "1fr auto auto",
                gap: 12,
                padding: "7px 0",
                borderBottom: "1px solid rgba(60,180,110,0.08)",
                fontFamily: C.mono,
                fontSize: 12,
                alignItems: "center",
              }}
            >
              <span
                style={{
                  color: stale ? C.statusYellow : C.body,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
                title={f.task}
              >
                {f.task.replace(/^Gamma_/, "")}
              </span>
              <span style={{ color: C.greenDim, whiteSpace: "nowrap" }}>
                {f.lastRun ? relTime(f.lastRun) : "—"}
              </span>
              <span
                style={{
                  color: C.green,
                  fontWeight: 700,
                  whiteSpace: "nowrap",
                  minWidth: 52,
                  textAlign: "right",
                }}
              >
                in {relFuture(f.nextRun)}
              </span>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

// =============================================================================
// STATUS TAIL PANEL
// =============================================================================

function StatusTailPanel({ tail }: { tail: string }): ReactElement {
  const ref = useRef<HTMLPreElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [tail]);

  return (
    <Panel style={{ padding: 18 }}>
      <SectionLabel title="STATUS.md tail" />
      <pre
        ref={ref}
        style={{
          flex: 1,
          margin: 0,
          background: "rgba(0,0,0,0.35)",
          border: "1px solid rgba(60,180,110,0.12)",
          borderRadius: 4,
          padding: "10px 12px",
          fontFamily: C.mono,
          fontSize: 12,
          color: C.dim,
          whiteSpace: "pre-wrap",
          overflowY: "auto",
          lineHeight: 1.55,
          minHeight: 0,
        }}
      >
        {tail || "(STATUS.md empty)"}
      </pre>
    </Panel>
  );
}

// =============================================================================
// PENDING WORK PANEL
// =============================================================================

function PendingWorkPanel({ pending }: { pending: PersonasBoard["pendingWork"] }): ReactElement {
  const [showMistakes, setShowMistakes] = useState(false);

  return (
    <Panel style={{ padding: 18 }}>
      <SectionLabel title="Pending Work" accent="#f97316" />

      {/* Chef inbox */}
      <div style={{ marginBottom: 14 }}>
        <div
          style={{
            fontFamily: C.mono,
            fontSize: 12,
            fontWeight: 700,
            color: "#f97316",
            letterSpacing: "0.06em",
            marginBottom: 6,
          }}
        >
          Chef Inbox ({pending.chefInbox.length})
        </div>
        {pending.chefInbox.length === 0 ? (
          <div style={{ fontFamily: C.mono, fontSize: 12, color: C.greenDim, fontStyle: "italic" }}>
            empty
          </div>
        ) : (
          pending.chefInbox.slice(0, 4).map((f) => (
            <div
              key={f.name}
              style={{
                fontFamily: C.mono,
                fontSize: 12,
                color: C.body,
                padding: "2px 0 2px 12px",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
              title={f.name}
            >
              — {f.name}{" "}
              <span style={{ color: C.greenDim }}>({Math.floor(f.ageMin / 60)}h)</span>
            </div>
          ))
        )}
      </div>

      {/* Chef candidates */}
      <div style={{ marginBottom: 14 }}>
        <div
          style={{
            fontFamily: C.mono,
            fontSize: 12,
            fontWeight: 700,
            color: "#f97316",
            letterSpacing: "0.06em",
            marginBottom: 6,
          }}
        >
          Candidates ({pending.chefCandidates.length})
        </div>
        {pending.chefCandidates.length === 0 ? (
          <div style={{ fontFamily: C.mono, fontSize: 12, color: C.greenDim, fontStyle: "italic" }}>
            none
          </div>
        ) : (
          pending.chefCandidates.slice(0, 4).map((f) => (
            <div
              key={f.name}
              style={{
                fontFamily: C.mono,
                fontSize: 12,
                color: C.body,
                padding: "2px 0 2px 12px",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
              title={f.name}
            >
              — {f.name}
            </div>
          ))
        )}
      </div>

      {/* Treasury */}
      <div style={{ marginBottom: 14 }}>
        <div
          style={{
            fontFamily: C.mono,
            fontSize: 12,
            fontWeight: 700,
            color: "#eab308",
            letterSpacing: "0.06em",
            marginBottom: 6,
          }}
        >
          Treasury Drafts
        </div>
        {pending.treasuryDrafts.exists ? (
          <div style={{ fontFamily: C.mono, fontSize: 12, color: C.statusYellow, paddingLeft: 12 }}>
            pending {relTime(pending.treasuryDrafts.mtimeISO)} — J ratifies
          </div>
        ) : (
          <div style={{ fontFamily: C.mono, fontSize: 12, color: C.greenDim, fontStyle: "italic", paddingLeft: 12 }}>
            no draft changes
          </div>
        )}
      </div>

      {/* Mistakes */}
      {pending.mistakesTail && (
        <div>
          <button
            type="button"
            onClick={() => setShowMistakes((v) => !v)}
            style={{
              background: "transparent",
              border: "1px solid rgba(239,68,68,0.3)",
              color: C.statusRed,
              fontFamily: C.mono,
              fontSize: 12,
              fontWeight: 700,
              letterSpacing: "0.06em",
              padding: "6px 10px",
              borderRadius: 4,
              cursor: "pointer",
              width: "100%",
              textAlign: "left",
            }}
          >
            Mistakes Log {showMistakes ? "▲" : "▼"}
          </button>
          {showMistakes && (
            <pre
              style={{
                background: "rgba(0,0,0,0.5)",
                border: "1px solid rgba(239,68,68,0.18)",
                borderRadius: 4,
                padding: "10px 12px",
                margin: "8px 0 0",
                fontFamily: C.mono,
                fontSize: 11,
                color: "#fca5a5",
                whiteSpace: "pre-wrap",
                maxHeight: 160,
                overflow: "auto",
                lineHeight: 1.5,
              }}
            >
              {pending.mistakesTail}
            </pre>
          )}
        </div>
      )}
    </Panel>
  );
}

// =============================================================================
// CHART WRAPPER
// =============================================================================

function ChartWrapper({ data }: { data: unknown }): ReactElement {
  return (
    <Panel style={{ padding: 0, flex: 1 }}>
      {/* CRT corner brackets */}
      {(["tl","tr","bl","br"] as const).map((pos) => (
        <span
          key={pos}
          aria-hidden="true"
          style={{
            position: "absolute",
            width: 16,
            height: 16,
            border: `2px solid ${C.green}70`,
            pointerEvents: "none",
            zIndex: 2,
            top:    pos.startsWith("t") ? 6 : undefined,
            bottom: pos.startsWith("b") ? 6 : undefined,
            left:   pos.endsWith("l")   ? 6 : undefined,
            right:  pos.endsWith("r")   ? 6 : undefined,
            borderRight:  pos.endsWith("l")   ? "none" : undefined,
            borderLeft:   pos.endsWith("r")   ? "none" : undefined,
            borderBottom: pos.startsWith("t") ? "none" : undefined,
            borderTop:    pos.startsWith("b") ? "none" : undefined,
          }}
        />
      ))}

      {/* Header bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "12px 16px 10px",
          borderBottom: "1px solid rgba(60,180,110,0.18)",
        }}
      >
        <span style={{ width: 3, height: 16, background: C.green, borderRadius: 1 }} />
        <span
          style={{
            fontFamily: C.mono,
            fontSize: 12,
            fontWeight: 700,
            color: C.green,
            letterSpacing: "0.2em",
            textTransform: "uppercase",
          }}
        >
          Floor TV · SPY · 5M · Live
        </span>
        <span style={{ flex: 1 }} />
        <LedDot color={C.statusGreen} pulse size={8} />
        <span style={{ fontFamily: C.mono, fontSize: 11, color: C.statusGreen, letterSpacing: "0.1em" }}>
          AMEX:SPY
        </span>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
        <ChartPanel data={data} />
      </div>
    </Panel>
  );
}

// =============================================================================
// DECK HEADER
// =============================================================================

function DeckHeader({
  composite,
  todayET,
  generatedAt,
  activeAgents,
  taskFlags,
}: {
  composite: "GREEN" | "YELLOW" | "RED";
  todayET: string;
  generatedAt: string;
  activeAgents: number;
  taskFlags: number;
}): ReactElement {
  const time = useEtClock();
  const color = statusColor(composite);

  return (
    <header
      style={{
        background: C.bgPanel,
        border: `1px solid ${C.borderPanel}`,
        borderRadius: 6,
        boxShadow: C.glowPanel,
        padding: "14px 20px",
        display: "flex",
        alignItems: "center",
        gap: 20,
        flexWrap: "wrap",
      }}
    >
      {/* Left: title */}
      <div style={{ display: "flex", alignItems: "center", gap: 14, flex: 1, minWidth: 200 }}>
        <span
          style={{
            fontSize: 28,
            lineHeight: 1,
            filter: "drop-shadow(0 0 8px rgba(126,224,168,0.45))",
          }}
        >
          🎩
        </span>
        <div>
          <div
            style={{
              fontFamily: "var(--font-press-start), monospace",
              fontSize: 14,
              color: C.green,
              letterSpacing: "0.1em",
              textShadow: "0 0 8px rgba(126,224,168,0.4)",
            }}
          >
            GAMMA / COMMAND DECK
          </div>
          <div
            style={{
              fontFamily: C.mono,
              fontSize: 12,
              color: C.greenDim,
              marginTop: 3,
              letterSpacing: "0.12em",
            }}
          >
            7 PERSONAS · {todayET} · refreshed {relTime(generatedAt)}
          </div>
        </div>
      </div>

      {/* Center: status pill + task count */}
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <StatusBadge status={`SYSTEM ${composite}`} />

        <div style={{ fontFamily: C.mono, fontSize: 13, display: "flex", gap: 18 }}>
          <span>
            <span style={{ color: C.greenDim }}>Tasks </span>
            <span style={{ color: C.body, fontWeight: 700 }}>{activeAgents}</span>
          </span>
          <span>
            <span style={{ color: C.greenDim }}>Flags </span>
            <span
              style={{
                color: taskFlags === 0 ? C.statusGreen : C.statusYellow,
                fontWeight: 700,
              }}
            >
              {taskFlags}
            </span>
          </span>
        </div>
      </div>

      {/* Right: clock */}
      <div
        style={{
          fontFamily: C.mono,
          fontSize: 22,
          fontWeight: 700,
          color: C.amber,
          letterSpacing: "0.06em",
          fontVariantNumeric: "tabular-nums",
          textShadow: "0 0 12px rgba(251,191,36,0.35)",
          whiteSpace: "nowrap",
        }}
      >
        {time}{" "}
        <span style={{ fontSize: 12, color: C.greenDim, letterSpacing: "0.18em" }}>ET</span>
      </div>
    </header>
  );
}

// =============================================================================
// MAIN — PersonasDesk
// =============================================================================

interface PersonasDeskProps {
  data: PersonasBoard;
}

export default function PersonasDesk({ data }: PersonasDeskProps): ReactElement {
  const composite = useMemo((): "GREEN" | "YELLOW" | "RED" => {
    if (data.personas.some((p) => p.status === "RED"))    return "RED";
    if (data.personas.some((p) => p.status === "YELLOW")) return "YELLOW";
    return "GREEN";
  }, [data.personas]);

  // Slot personas by fuzzy slug match — handles "Gamma (Manager)" correctly
  const find = (slug: string): PersonaState | undefined =>
    data.personas.find((p) => slugMatch(p.name, slug));

  const leftStack  = (["scout", "coach", "analyst", "treasurer"] as const).map(find).filter((p): p is PersonaState => Boolean(p));
  const rightStack = (["gamma", "pilot", "chef"] as const).map(find).filter((p): p is PersonaState => Boolean(p));
  const slotted    = new Set([...leftStack, ...rightStack].map((p) => p.name));
  const orphans    = data.personas.filter((p) => !slotted.has(p.name));

  // Pilot is the featured card during market hours / when status is active
  const pilotPersona = find("pilot");
  const pilotFeatured = pilotPersona?.status === "GREEN" || pilotPersona?.status === "YELLOW";

  return (
    <div
      style={{
        minHeight: "100vh",
        background: C.bgDeep,
        backgroundImage:
          "radial-gradient(ellipse 90% 50% at 50% 0%, rgba(34,200,120,0.05) 0%, transparent 55%), " +
          "radial-gradient(ellipse 60% 40% at 80% 100%, rgba(167,139,250,0.03) 0%, transparent 55%)",
        color: C.body,
        fontFamily: C.mono,
        padding: 20,
        display: "flex",
        flexDirection: "column",
        gap: 16,
        boxSizing: "border-box",
      }}
    >
      {/* Inject global CSS without styled-jsx */}
      <style dangerouslySetInnerHTML={{ __html: GLOBAL_CSS }} />

      {/* ── HEADER ─────────────────────────────────────── */}
      <DeckHeader
        composite={composite}
        todayET={data.todayET}
        generatedAt={data.generatedAt}
        activeAgents={data.scheduledTasks.activeCount}
        taskFlags={data.scheduledTasks.flagCount}
      />

      {/* ── THREE-COLUMN BODY ──────────────────────────── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(240px, 1fr) minmax(400px, 2fr) minmax(240px, 1fr)",
          gap: 16,
          flex: "0 0 auto",
        }}
      >
        {/* LEFT COLUMN — 4 advisory personas */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {leftStack.map((p) => (
            <PersonaCard key={p.name} persona={p} />
          ))}
        </div>

        {/* CENTER — chart (dominant) + chart-level info below */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 12,
            position: "relative",
          }}
        >
          <ChartWrapper data={null} />
        </div>

        {/* RIGHT COLUMN — 3 operational personas + pending work */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {rightStack.map((p) => (
            <PersonaCard
              key={p.name}
              persona={p}
              featured={slugMatch(p.name, "pilot") && pilotFeatured}
            />
          ))}
          <PendingWorkPanel pending={data.pendingWork} />
        </div>
      </div>

      {/* ── ORPHANED PERSONAS (defensive) ─────────────── */}
      {orphans.length > 0 && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
            gap: 12,
          }}
        >
          {orphans.map((p) => (
            <PersonaCard key={p.name} persona={p} />
          ))}
        </div>
      )}

      {/* ── HANDOFF PIPELINE ──────────────────────────── */}
      <Panel style={{ padding: 18 }}>
        <SectionLabel title="Handoff Pipeline" />
        <HandoffPipeline handoffs={data.handoffs} />
      </Panel>

      {/* ── STATUS TAIL + NEXT FIRES ──────────────────── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1.5fr 1fr",
          gap: 16,
          minHeight: 280,
        }}
      >
        <StatusTailPanel tail={data.status.tail} />
        <NextFiresPanel fires={data.scheduledTasks.nextFires} activeCount={data.scheduledTasks.activeCount} />
      </div>

      {/* ── API ERRORS ────────────────────────────────── */}
      {data.errors.length > 0 && (
        <div
          style={{
            background: "rgba(60,10,10,0.55)",
            border: "1px solid rgba(239,68,68,0.35)",
            borderRadius: 6,
            padding: "14px 18px",
            fontFamily: C.mono,
            fontSize: 13,
            color: "#fca5a5",
          }}
        >
          <strong style={{ letterSpacing: "0.1em" }}>API ERRORS</strong>
          <ul style={{ margin: "8px 0 0 20px", padding: 0, lineHeight: 1.6 }}>
            {data.errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      {/* ── FOOTER ────────────────────────────────────── */}
      <footer
        style={{
          textAlign: "center",
          color: C.greenDim,
          fontFamily: C.mono,
          fontSize: 11,
          letterSpacing: "0.18em",
          padding: "4px 0 8px",
        }}
      >
        GAMMA COMMAND DECK · auto-refresh 10s · /api/personas
      </footer>
    </div>
  );
}
