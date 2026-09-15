"use client";

import type { HqApiResponse } from "./types";
import { personaStatusColor, rosterEvidenceText } from "./palette";
import { STANDBY_BANNER_MAX_WIDTH_CSS, STANDBY_BANNER_RIGHT_PX } from "./standbyBannerLayout";

interface StandbyPanelProps {
  data: HqApiResponse | undefined;
}

const BLOCKED_SOURCE_LABEL: Record<string, string> = {
  discord: "Discord",
  conductor_proposal: "Proposal",
  queue_escalation: "Escalation",
  goal_blocked: "Goal",
};

/**
 * Ultra tier, paused state (2026-09-13 -- J: "wtf is this slop" on the old
 * dim-the-3D + giant plaque approach). This REPLACES that entirely: the
 * canvas is hidden (not dimmed), and this is a plain designed HTML panel --
 * dark glass, three columns, base font 22-26px, readable at 1440p. It is
 * what J sees the whole time he's gaming, so it has to be sharp and
 * truthful on its own, not a degraded fallback.
 */
export default function StandbyPanel({ data }: StandbyPanelProps) {
  const personas = data?.company?.personas ?? [];
  const blocked = data?.blocked ?? [];
  const gpu = data?.brainVitals?.gpu;
  const modelName = data?.brainVitals?.models?.[0]?.name ?? null;
  const brief = data?.brief.text || "NO DATA -- no brief written yet";
  // GPU-YIELD (queue item e, 2026-09-15): this panel is now ALSO shown
  // while the local brain (Ollama) is mid-inference-burst, a different
  // cause from "J is gaming" -- the banner below must say which one it
  // actually is rather than always claiming "reserved for J".
  const brainBusy = data?.runtime?.brain?.busy === true;
  const gaming = data?.mode === "gaming";
  const standbyText = gaming
    ? "Standby -- GPU reserved for J, resumes automatically"
    : brainBusy
      ? "Standby -- brain thinking (local GPU inference), resumes automatically"
      : "Standby -- resumes automatically";

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 20, overflow: "auto",
        background: "radial-gradient(ellipse at 50% 30%, #0b1220 0%, #03040a 70%)",
        color: "#dff3ff", fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
      }}
    >
      <div
        // Queue item h (2026-09-15, real-screen capture): was pinned at
        // `right: 32`, which at 1920px put its left edge around x=1160 --
        // inside Hud.tsx's fixed right column (starts at x=1420, see
        // standbyBannerLayout.ts's own header for the full evidence + why
        // this fix keeps the banner's geometry structurally clear of that
        // column rather than depending on stacking order). `maxWidth` +
        // `whiteSpace: "normal"` let the text wrap onto a second line
        // instead of ever being clipped, at any viewport width.
        style={{
          position: "fixed", top: 24, right: STANDBY_BANNER_RIGHT_PX, maxWidth: STANDBY_BANNER_MAX_WIDTH_CSS,
          padding: "8px 22px", borderRadius: 16,
          background: "rgba(255,176,32,0.12)", border: "1px solid #ffb020", color: "#ffb020",
          fontSize: 20, fontWeight: 700, letterSpacing: 0.3, whiteSpace: "normal", textAlign: "right",
        }}
      >
        {standbyText}
      </div>

      <div style={{ maxWidth: 2560, margin: "0 auto", padding: "96px 60px 60px", display: "grid", gridTemplateColumns: "1.1fr 1fr 1fr", gap: 48 }}>
        {/* Column 1: roster, real status lines only */}
        <div>
          <h2 style={{ fontSize: 28, fontWeight: 800, marginBottom: 18, color: "#7ad9ff" }}>ROSTER</h2>
          {personas.map((p) => (
            <div key={p.name} style={{ marginBottom: 20, paddingBottom: 16, borderBottom: "1px solid rgba(122,217,255,0.15)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 25, fontWeight: 700 }}>
                <span style={{ width: 13, height: 13, borderRadius: 999, flexShrink: 0, background: personaStatusColor(p.status), boxShadow: `0 0 6px ${personaStatusColor(p.status)}` }} />
                <span>{p.emoji} {p.name}</span>
              </div>
              <div style={{ fontSize: 22, color: "#9fb3cc", marginTop: 4 }}>{rosterEvidenceText(p.lastFireISO)}</div>
              <div style={{ fontSize: 22, color: "#7f93b0", marginTop: 2, lineHeight: 1.4 }}>
                {p.recentOutput ? p.recentOutput.replace(/\s+/g, " ").slice(0, 100) : "no evidence file"}
              </div>
            </div>
          ))}
        </div>

        {/* Column 2: NEEDS J */}
        <div>
          <h2 style={{ fontSize: 28, fontWeight: 800, marginBottom: 18, color: "#ffb020" }}>NEEDS J ({blocked.length})</h2>
          {blocked.length === 0 && <div style={{ fontSize: 22, color: "#7f93b0" }}>Nothing blocked right now.</div>}
          {blocked.map((item, i) => (
            <div key={`${item.source}-${item.ts ?? i}`} style={{ marginBottom: 18, fontSize: 22, color: "#ffe0a3", lineHeight: 1.4 }}>
              <span style={{ color: "#ffb020", fontWeight: 700 }}>[{BLOCKED_SOURCE_LABEL[item.source] ?? item.source}]</span>{" "}
              {item.text} <span style={{ color: "#c99457" }}>&middot; {item.age}</span>
            </div>
          ))}
        </div>

        {/* Column 3: brain/GPU vitals + latest brief */}
        <div>
          <h2 style={{ fontSize: 28, fontWeight: 800, marginBottom: 18, color: "#7ad9ff" }}>BRAIN / GPU</h2>
          <div style={{ fontSize: 25, fontWeight: 700, marginBottom: 10 }}>{modelName || "no model loaded"}</div>
          {gpu && (
            <div style={{ fontSize: 22, color: "#9fb3cc", lineHeight: 1.6 }}>
              <div>GPU util: {gpu.util_pct ?? "?"}%</div>
              <div>Memory: {gpu.mem_used_mib ?? "?"} / {gpu.mem_total_mib ?? "?"} MiB</div>
              <div>Temp: {gpu.temp_c ?? "?"}C &middot; Power: {gpu.power_w ?? "?"}W</div>
            </div>
          )}
          <h3 style={{ fontSize: 24, fontWeight: 700, marginTop: 30, marginBottom: 10, color: "#7f93b0" }}>Latest brief</h3>
          <div style={{ fontSize: 22, color: "#c7d6e8", whiteSpace: "pre-wrap", lineHeight: 1.5 }}>
            {brief.slice(0, 700)}
          </div>
        </div>
      </div>
    </div>
  );
}
