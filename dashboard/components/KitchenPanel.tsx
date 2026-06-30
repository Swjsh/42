"use client";

import React from "react";
import type { KitchenStatus } from "@/lib/state";

interface Props {
  kitchen: KitchenStatus | null;
}

// ─── Design tokens (mirror TradingFloor's pixel-art palette) ───────────────────
const MONO = "'JetBrains Mono','IBM Plex Mono',ui-monospace,Menlo,monospace";
const G = {
  bg: "#020c05",
  card: "rgba(4,18,9,0.96)",
  cardElev: "rgba(3,14,7,0.95)",
  border: "rgba(0,180,70,0.18)",
  green: "#00d46a",
  greenDim: "#00a852",
  red: "#ff4455",
  redDim: "#c93040",
  yellow: "#ffc340",
  purple: "#a78bfa",
  cyan: "#22d3ee",
  dim: "#2a4a35",
  label: "#3d6b4d",
  text: "#d8f0e0",
  textBright: "#edfaef",
};

const LBL: React.CSSProperties = {
  fontFamily: MONO,
  fontSize: 9,
  fontWeight: 700,
  letterSpacing: "0.20em",
  textTransform: "uppercase",
  color: G.label,
};

// ─── Helpers ──────────────────────────────────────────────────────────────────
function minutesSince(iso: string | null | undefined): number | null {
  if (!iso) return null;
  // updated_at_et / completed_at may be naive ET or carry an offset. Date.parse
  // handles ISO-with-offset; for naive strings we treat them as the same wall
  // clock the browser renders in — good enough for a coarse "Xm ago" badge.
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return Math.floor((Date.now() - t) / 60000);
}

function relTime(iso: string | null | undefined): string {
  const m = minutesSince(iso);
  if (m === null) return "";
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return `${s.slice(0, n - 1).trimEnd()}…`;
}

function shortId(id: string | null): string {
  if (!id) return "—";
  return id.length > 8 ? id.slice(0, 8) : id;
}

// ─── Panel ────────────────────────────────────────────────────────────────────
export default function KitchenPanel({ kitchen }: Props) {
  const shell: React.CSSProperties = {
    fontFamily: MONO,
    color: G.text,
    background: `linear-gradient(180deg, ${G.card} 0%, ${G.bg} 100%)`,
    border: `1px solid ${G.border}`,
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

  // Null / unavailable guard ──────────────────────────────────────────────────
  if (!kitchen) {
    return (
      <section style={shell}>
        <div style={{
          position: "absolute", top: 0, left: 0, right: 0, height: 2,
          background: `linear-gradient(90deg, transparent, ${G.greenDim} 50%, transparent)`,
        }} />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
          <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.22em", color: G.label }}>
            🍳 KITCHEN
          </span>
        </div>
        <div style={{ fontSize: 10, color: G.dim, fontStyle: "italic" }}>
          kitchen status unavailable
        </div>
      </section>
    );
  }

  const alive = kitchen.daemon_alive ?? false;
  const idle = kitchen.idle ?? false;
  const cooking = alive && !idle;

  // Status flavour
  const statusColor = !alive ? G.red : cooking ? G.green : G.yellow;
  const statusLabel = !alive ? "DOWN" : cooking ? "COOKING" : "IDLE";
  const statusSub = !alive
    ? "daemon down"
    : cooking
    ? "alive + cooking"
    : "alive + idle";

  const completed = kitchen.queue_summary?.by_status?.completed ?? 0;
  const pending = kitchen.queue_summary?.by_status?.pending ?? 0;
  const failed = kitchen.queue_summary?.by_status?.failed_permanent ?? 0;
  const byPrio = kitchen.queue_summary?.by_priority_pending ?? null;

  const cost = kitchen.today_cost_usd_paid_tier ?? 0;
  const cap = kitchen.today_cost_cap_usd ?? 0;
  const freeTier = cost === 0;

  const recent = kitchen.recent_completed_top_10 ?? [];
  const plated = recent.slice(0, 5);

  const staleMins = minutesSince(kitchen.updated_at_et);
  const stale = staleMins !== null && staleMins > 30;

  return (
    <section style={shell}>
      {/* animated top accent — pulses when cooking */}
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: 2,
        background: cooking
          ? `linear-gradient(90deg, transparent, ${G.green} 50%, transparent)`
          : `linear-gradient(90deg, transparent, ${G.dim} 50%, transparent)`,
        animation: cooking ? "kitchenAccent 2s ease-in-out infinite" : "none",
      }} />

      {/* scoped keyframes for the "alive" pulse */}
      <style>{`
        @keyframes kitchenPulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.25; }
        }
        @keyframes kitchenAccent {
          0%, 100% { opacity: 0.5; }
          50% { opacity: 1; }
        }
      `}</style>

      {/* ── HEADER ── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
        <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.22em", color: G.green }}>
          🍳 KITCHEN
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 9, fontWeight: 700, color: statusColor }}>
          <span
            style={{
              width: 6, height: 6, borderRadius: "50%", background: statusColor, flexShrink: 0,
              filter: alive ? `drop-shadow(0 0 4px ${statusColor})` : "none",
              animation: cooking ? "kitchenPulse 1.1s ease-in-out infinite" : "none",
            }}
          />
          {statusLabel}
        </span>
      </div>

      {/* ── CHEF / DAEMON STATUS ── */}
      <div style={{
        display: "flex", alignItems: "center", gap: "0.5em",
        background: `${statusColor}10`,
        border: `1px solid ${statusColor}33`,
        borderRadius: 6,
        padding: "0.5em 0.6em",
        flexShrink: 0,
      }}>
        <span
          style={{
            fontSize: 22, lineHeight: 1,
            animation: cooking ? "kitchenPulse 1.1s ease-in-out infinite" : "none",
            filter: cooking ? `drop-shadow(0 0 6px ${G.green})` : "none",
            opacity: alive ? 1 : 0.4,
          }}
        >
          {cooking ? "🍳" : alive ? "▮" : "✕"}
        </span>
        <div style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0 }}>
          <span style={{ fontSize: 14, fontWeight: 900, color: statusColor, letterSpacing: "0.03em", lineHeight: 1 }}>
            {statusLabel}
          </span>
          <span style={{ fontSize: 8, color: G.dim, letterSpacing: "0.06em" }}>{statusSub}</span>
        </div>
      </div>

      {/* ── COMPLETED (dishes plated) ── */}
      <div style={{ borderTop: `1px solid ${G.border}`, paddingTop: 8, flexShrink: 0 }}>
        <div style={{ ...LBL, marginBottom: 4 }}>DISHES PLATED</div>
        <div style={{ display: "flex", alignItems: "baseline", gap: "0.4em" }}>
          <span style={{ fontSize: 30, fontWeight: 900, color: G.textBright, fontVariantNumeric: "tabular-nums", lineHeight: 1 }}>
            {completed.toLocaleString()}
          </span>
          <span style={{ fontSize: 9, color: G.dim }}>completed</span>
        </div>
        {failed > 0 && (
          <div style={{ fontSize: 8, color: G.redDim, marginTop: 2 }}>
            {failed} failed permanent
          </div>
        )}
      </div>

      {/* ── NOW COOKING ── */}
      <div style={{ borderTop: `1px solid ${G.border}`, paddingTop: 8, flexShrink: 0 }}>
        <div style={{ ...LBL, marginBottom: 4 }}>NOW COOKING</div>
        {cooking ? (
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ color: G.green, fontSize: 8, animation: "kitchenPulse 1.1s ease-in-out infinite" }}>●</span>
            <span style={{ fontSize: 11, fontWeight: 700, color: G.green, fontVariantNumeric: "tabular-nums" }}>
              {shortId(kitchen.current_task_id)}
            </span>
          </div>
        ) : (
          <div style={{ fontSize: 10, color: G.dim, fontStyle: "italic" }}>between dishes</div>
        )}
      </div>

      {/* ── QUEUE ── */}
      <div style={{ borderTop: `1px solid ${G.border}`, paddingTop: 8, flexShrink: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={LBL}>QUEUE</span>
          <span style={{ fontSize: 16, fontWeight: 900, color: pending > 0 ? G.yellow : G.dim, fontVariantNumeric: "tabular-nums" }}>
            {pending}
          </span>
        </div>
        {byPrio && (
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
            {Object.entries(byPrio).map(([prio, n]) => (
              <span key={prio} style={{ fontSize: 9, color: G.dim }}>
                <span style={{ color: G.label }}>{prio}</span>{" "}
                <span style={{ color: G.text, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{n}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* ── COST ── */}
      <div style={{ borderTop: `1px solid ${G.border}`, paddingTop: 8, flexShrink: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
          <span style={LBL}>COST TODAY</span>
          {freeTier && (
            <span style={{
              fontSize: 7, color: G.green, border: `1px solid ${G.green}50`,
              background: `${G.green}12`, padding: "1px 5px", borderRadius: 3,
              fontWeight: 700, letterSpacing: "0.1em",
            }}>
              FREE TIER
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: "0.3em" }}>
          <span style={{ fontSize: 14, fontWeight: 800, color: freeTier ? G.green : G.text, fontVariantNumeric: "tabular-nums" }}>
            ${cost.toFixed(2)}
          </span>
          <span style={{ fontSize: 9, color: G.dim }}>/ ${cap.toFixed(2)}</span>
        </div>
      </div>

      {/* ── RECENTLY PLATED feed ── */}
      <div style={{ borderTop: `1px solid ${G.border}`, paddingTop: 8, flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        <div style={{ ...LBL, marginBottom: 5, flexShrink: 0 }}>RECENTLY PLATED</div>
        {plated.length === 0 ? (
          <div style={{ fontSize: 9, color: G.dim, fontStyle: "italic" }}>nothing plated yet</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6, overflow: "hidden" }}>
            {plated.map((t, i) => (
              <div key={t.task_id ?? i} style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                <span style={{ fontSize: 9, color: G.text, lineHeight: 1.35 }}>
                  {truncate(t.task ?? "", 70)}
                </span>
                <span style={{ fontSize: 8, color: G.dim }}>{relTime(t.completed_at)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── STALENESS (honesty — never hidden) ── */}
      {stale && (
        <div style={{ flexShrink: 0, fontSize: 8, color: G.redDim, fontStyle: "italic", letterSpacing: "0.04em" }}>
          status last refreshed {staleMins}m ago
        </div>
      )}
    </section>
  );
}
