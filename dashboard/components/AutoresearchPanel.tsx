"use client";

import useSWR from "swr";

interface ModeBaseline {
  n_trades?: number;
  win_rate?: number;
  total_pnl?: number;
  sharpe_daily?: number;
  expectancy?: number;
}

interface ModeReport {
  mode: string;
  state_exists: boolean;
  iterations: number;
  keeps: number;
  keep_rate: number;
  validate_baseline: ModeBaseline;
  issues: string[];
}

interface WatchdogReport {
  generated_at: string;
  healthy: boolean;
  overall_iterations: number;
  overall_keeps: number;
  overall_keep_rate: number;
  issues: string[];
  modes: ModeReport[];
}

interface ApiResponse {
  fetched_at: string;
  available: boolean;
  report?: WatchdogReport;
  error?: string;
}

const fetcher = (url: string): Promise<ApiResponse> =>
  fetch(url, { cache: "no-store" }).then((r) => r.json());

// ── colours ──────────────────────────────────────────────────────────────────
const T = {
  bgCard: "#161e35",
  bgElev: "#131b2e",
  border: "rgba(255,255,255,0.08)",
  text1: "#e6edf7",
  text2: "#a4afc4",
  text3: "#6e7a92",
  text4: "#4a5570",
  up: "#22c55e",
  down: "#ef4444",
  amber: "#f59e0b",
  cyan: "#22d3ee",
  violet: "#a78bfa",
  blue: "#60a5fa",
};

const MODES: Record<string, { accent: string; label: string }> = {
  strict:     { accent: T.violet, label: "STRICT" },
  balanced:   { accent: T.blue,   label: "BALANCD" },
  aggressive: { accent: T.amber,  label: "AGGRSSV" },
};

const F_MONO = "var(--font-jetbrains-mono), 'JetBrains Mono', monospace";

function fmtMoney(v: number | undefined | null): string {
  if (v == null) return "—";
  const sign = v >= 0 ? "+" : "−";
  return `${sign}$${Math.abs(v).toFixed(0)}`;
}

function fmtSharpe(v: number | undefined | null): string {
  if (v == null) return "—";
  const sign = v >= 0 ? "+" : "−";
  return `${sign}${Math.abs(v).toFixed(2)}`;
}

function fmtTimeSince(iso: string): string {
  const diff = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (diff < 60) return `${diff}s`;
  if (diff < 3600) return `${Math.round(diff / 60)}m`;
  return `${Math.round(diff / 3600)}h`;
}

function pnlColor(v: number | undefined | null): string {
  if (v == null) return T.text3;
  return v > 0 ? T.up : v < 0 ? T.down : T.text1;
}

// ── component ────────────────────────────────────────────────────────────────

export default function AutoresearchPanel() {
  const { data } = useSWR<ApiResponse>("/api/autoresearch", fetcher, {
    refreshInterval: 5000,
    revalidateOnFocus: true,
  });

  const shell: React.CSSProperties = {
    fontFamily: F_MONO,
    color: T.text1,
    background: `linear-gradient(180deg, ${T.bgCard} 0%, ${T.bgElev} 100%)`,
    border: `1px solid ${T.border}`,
    borderRadius: 12,
    padding: "12px 10px",
    height: "100%",
    minHeight: 0,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    position: "relative",
    gap: 10,
    boxShadow: "0 12px 32px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.04)",
  };

  const report = data?.report;
  const healthColor = report?.healthy ? T.up : T.amber;

  return (
    <section style={shell}>
      {/* top accent */}
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: 2,
        background: `linear-gradient(90deg, transparent, ${T.cyan} 40%, ${T.violet} 60%, transparent)`,
      }} />

      {/* ── HEADER ── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
        <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.22em", color: T.cyan }}>
          RESEARCH
        </span>
        {report && (
          <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 9, fontWeight: 700, color: healthColor }}>
            <span style={{ width: 5, height: 5, borderRadius: "50%", background: healthColor, flexShrink: 0 }} />
            {report.healthy ? "OK" : "⚠"}
          </span>
        )}
      </div>

      {!report ? (
        <div style={{ fontSize: 10, color: T.text3 }}>loading…</div>
      ) : (
        <>
          {/* ── TIME ── */}
          <div style={{ fontSize: 9, color: T.text4 }}>
            {fmtTimeSince(report.generated_at)} ago
          </div>

          {/* ── TOP-LINE STATS ── */}
          <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 8, flexShrink: 0 }}>
            <div style={{ fontSize: 9, color: T.text3, marginBottom: 5, letterSpacing: "0.16em" }}>STATS</div>
            {[
              { label: "iters", val: report.overall_iterations, color: T.text1 },
              { label: "keeps", val: report.overall_keeps,      color: T.text1 },
              { label: "rate",  val: `${(report.overall_keep_rate * 100).toFixed(1)}%`, color: T.amber },
            ].map(({ label, val, color }) => (
              <div key={label} style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 2 }}>
                <span style={{ color: T.text3 }}>{label}</span>
                <span style={{ color, fontWeight: 700 }}>{val}</span>
              </div>
            ))}
          </div>

          {/* ── MODES ── */}
          <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 8, flexShrink: 0 }}>
            <div style={{ fontSize: 9, color: T.text3, marginBottom: 5, letterSpacing: "0.16em" }}>MODES</div>
            {report.modes.map((m) => {
              const accent = MODES[m.mode]?.accent ?? T.text3;
              const label  = MODES[m.mode]?.label  ?? m.mode.slice(0, 7).toUpperCase();
              const pnl    = m.validate_baseline?.total_pnl;
              return (
                <div key={m.mode} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, marginBottom: 4 }}>
                  <span style={{ width: 5, height: 5, borderRadius: "50%", background: m.state_exists ? accent : T.text4, flexShrink: 0 }} />
                  <span style={{ color: m.state_exists ? T.text2 : T.text4, flex: 1, fontSize: 9 }}>{label}</span>
                  <span style={{ color: pnlColor(pnl), fontVariantNumeric: "tabular-nums", fontSize: 10, fontWeight: 700 }}>
                    {fmtMoney(pnl)}
                  </span>
                </div>
              );
            })}
          </div>

          {/* ── WINNER ── */}
          {(() => {
            const winner = [...report.modes]
              .filter((m) => m.state_exists && m.validate_baseline?.total_pnl != null)
              .sort((a, b) => (b.validate_baseline.total_pnl ?? 0) - (a.validate_baseline.total_pnl ?? 0))[0];
            if (!winner) return null;
            const accent = MODES[winner.mode]?.accent ?? T.text1;
            const label  = MODES[winner.mode]?.label  ?? winner.mode.toUpperCase();
            return (
              <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 8, marginTop: "auto", flexShrink: 0 }}>
                <div style={{ fontSize: 9, color: T.text3, marginBottom: 4, letterSpacing: "0.16em" }}>BEST</div>
                <div style={{ fontSize: 11, fontWeight: 700, color: accent, marginBottom: 3 }}>{label}</div>
                <div style={{ fontSize: 10, color: T.text2, lineHeight: 1.6 }}>
                  <div>α {fmtSharpe(winner.validate_baseline?.sharpe_daily)}</div>
                  <div style={{ color: pnlColor(winner.validate_baseline?.total_pnl) }}>
                    {fmtMoney(winner.validate_baseline?.total_pnl)}
                  </div>
                </div>
              </div>
            );
          })()}

          {/* ── ISSUES ── */}
          {report.issues.length > 0 && (
            <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 6, flexShrink: 0 }}>
              <div style={{ fontSize: 9, color: T.amber, fontWeight: 700, marginBottom: 3 }}>
                ⚠ {report.issues.length}
              </div>
              <div style={{ fontSize: 9, color: T.text3, lineHeight: 1.4 }}>
                {report.issues[0].slice(0, 55)}{report.issues[0].length > 55 ? "…" : ""}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
