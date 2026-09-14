"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { HqApiResponse } from "./types";
import { auditVerdictColor, personaStatusColor, rosterEvidenceText, truncateOneLine } from "./palette";
import type { MotionEvent } from "@/lib/useMotionEvents";

const BLOCKED_SOURCE_LABEL: Record<string, string> = {
  discord: "Discord",
  conductor_proposal: "Proposal",
  queue_escalation: "Escalation",
  goal_blocked: "Goal",
};

interface HudProps {
  data: HqApiResponse | undefined;
  error: unknown;
  kiosk: boolean;
  isValidating: boolean;
  motionEvents: MotionEvent[];
}

function useEtClock(): string {
  const [text, setText] = useState("--:--:--");
  useEffect(() => {
    const fmt = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    });
    const tick = () => setText(fmt.format(new Date()) + " ET");
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return text;
}

const HUD_FONT = "system-ui, -apple-system, Segoe UI, Roboto, sans-serif";

/**
 * Plain HTML overlay (not 3D text -- crisp at any TV viewing distance).
 * Sits in a fixed, full-viewport, pointer-events-none wrapper above the
 * <Canvas>; individual controls (Home link) re-enable pointer events.
 */
export default function Hud({ data, error, kiosk, isValidating, motionEvents }: HudProps) {
  const etClock = useEtClock();
  const mode = data?.mode ?? "unknown";
  const gaming = mode === "gaming";
  const present = data?.presence?.present ?? null;
  const syncedText = data
    ? `Synced ${new Date(data.fetched_at).toLocaleTimeString()}${isValidating ? " -- syncing..." : ""}`
    : error
      ? `Refresh failed (${error instanceof Error ? error.message : "fetch failed"})`
      : "Loading...";
  const personas = data?.company?.personas ?? [];
  const blockedItems = data?.blocked ?? [];
  // Company audit badge (commit 58d0b9c6, coordinator 2026-09-13: "the
  // roster must show ghosts as ghosts") -- matched by name, the same string
  // on both sides (PersonaState.name / PersonaAudit.name). `data.audit` is
  // null on an old build or a failed audit run (fail-open) -- every lookup
  // below falls back to "no badge" rather than a fake verdict.
  const auditByName = new Map((data?.audit?.personas ?? []).map((a) => [a.name, a]));

  return (
    <div style={{ position: "fixed", inset: 0, pointerEvents: "none", fontFamily: HUD_FONT, zIndex: 10 }}>
      <style>{`
        /* "Epic animations for the folders" (2026-09-13, J via 21st.dev) --
           hand-implemented (no code copied), concepts credited per rule:
           transform/opacity/background-position ONLY (no filter:blur,
           box-shadow spreads, or backdrop-filter -- those melt the TV's
           Mali-G31 compositor). Shared here so drei's <Html>-portaled
           content elsewhere in the tree (module panels, brain plaque) can
           use the same classes -- <style> is a plain global stylesheet. */

        /* Border Beam (https://21st.dev/s/border, "Border Beam": a beam
           that travels around a card's edge) -- a rotating conic-gradient
           behind a 1px-padded wrapper; the inner panel's own background
           covers everything except that 1px ring. transform:rotate only. */
        .hq-beam { position: relative; padding: 1px; }
        .hq-beam::before {
          content: ""; position: absolute; inset: -100%;
          background: conic-gradient(from 0deg, transparent 0%, var(--beam-color, #7ad9ff) 6%, transparent 16%);
          animation: hq-beam-spin 4.5s linear infinite;
        }
        @keyframes hq-beam-spin { to { transform: rotate(360deg); } }

        /* Shine Border (https://21st.dev/s/border, "Shine Border": a moving
           light effect that travels across the border) -- reimagined as a
           one-shot diagonal shine sweep across the panel, replayed by
           remounting the span via a changing React key prop whenever the
           row's health/state changes. transform:translateX + opacity only. */
        .hq-shine {
          position: absolute; top: -30%; bottom: -30%; left: -60%; width: 35%;
          background: linear-gradient(100deg, transparent, rgba(255,255,255,0.5), transparent);
          animation: hq-shine-sweep 0.9s ease-out;
          pointer-events: none;
        }
        @keyframes hq-shine-sweep {
          from { transform: translateX(0%); opacity: 0; }
          15% { opacity: 1; }
          to { transform: translateX(420%); opacity: 0; }
        }

        /* Meteors (a "meteor shower" pattern -- a group of beams drifting
           through a container; see e.g. magicui.design/docs/components/meteors,
           cross-listed on 21st.dev) -- a subtle decorative drift behind the
           HUD title, low-opacity so it never competes with the readable
           text on top of it. transform:translate + opacity only. */
        .hq-meteor {
          position: absolute; width: 2px; height: 46px; top: -50px; left: 0;
          background: linear-gradient(180deg, rgba(122,217,255,0.85), transparent);
          animation: hq-meteor-fall linear infinite;
        }
        @keyframes hq-meteor-fall {
          0% { transform: translate(0, 0) rotate(35deg); opacity: 0; }
          12% { opacity: 0.65; }
          85% { opacity: 0.65; }
          100% { transform: translate(150px, 130px) rotate(35deg); opacity: 0; }
        }

        /* Roster panel accent (Company Mode step 5, 2026-09-13): a GREEN
           persona row breathes gently -- opacity only, same TV-safe
           constraint as everything above. Cheap enough to run per-row
           (bounded at 7 rows max, the fixed roster size). */
        .hq-pulse { animation: hq-pulse-glow 1.8s ease-in-out infinite; }
        @keyframes hq-pulse-glow { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
      `}</style>

      {/* Meteors drifting behind the title (decorative only, z-index below
          the text) -- trimmed from 5 to 3 (2026-09-13, Company Mode step 5)
          to make room in the animated-DOM-element budget (cap 24) for the
          roster panel's per-GREEN-row pulses below. */}
      <div style={{ position: "absolute", top: 0, left: 0, width: 260, height: 70, overflow: "hidden" }}>
        {[0, 2.5, 5].map((delay, i) => (
          <span key={i} className="hq-meteor" style={{ left: 20 + i * 48, animationDelay: `${delay}s`, animationDuration: "6s" }} />
        ))}
      </div>

      {/* Top-left: title + ET clock + mode badge. 10-foot-readability sizing
          (2026-09-13, J: "it's just like text ... no animations"): mode
          badge bumped to ~34px per spec; title/clock bumped alongside it so
          the badge doesn't outsize its own header. */}
      <div style={{ position: "absolute", top: 14, left: 20, display: "flex", alignItems: "center", gap: 16 }}>
        <span style={{ color: "#dff3ff", fontSize: 34, fontWeight: 800, letterSpacing: 1.5, textShadow: "0 0 14px rgba(122,217,255,0.6)" }}>
          GAMMA HQ
        </span>
        <span style={{ color: "#7f93b0", fontSize: 20, fontVariantNumeric: "tabular-nums" }}>{etClock}</span>
        <span
          style={{
            fontSize: 22, fontWeight: 700, padding: "3px 16px", borderRadius: 999,
            background: gaming ? "rgba(255,176,32,0.18)" : "rgba(34,255,136,0.14)",
            color: gaming ? "#ffb020" : "#22ff88",
            border: `2px solid ${gaming ? "#ffb020" : "#22ff88"}`,
          }}
        >
          {gaming ? "GPU RESERVED" : `mode: ${mode}`}
        </span>
      </div>

      {/* NEEDS-J card (Company Mode step 7, 2026-09-13): read-only amber
          alert aggregating discord-outbox mentions of J, pending conductor
          proposals, and FABLE-ESCALATION queue lines -- see
          lib/hq.ts#readBlocked. Newest 3 of up to 8; hidden entirely when
          there's nothing blocked so it never occupies space on a clean day. */}
      {blockedItems.length > 0 && (
        <div
          style={{
            position: "absolute", top: 70, left: 20, width: 380,
            background: "rgba(40,26,0,0.75)", border: "1px solid #ffb020", borderRadius: 8,
            padding: "8px 14px",
          }}
        >
          <div style={{ color: "#ffb020", fontSize: 18, fontWeight: 800, letterSpacing: 0.5, marginBottom: 4 }}>
            NEEDS J ({blockedItems.length})
          </div>
          {blockedItems.slice(0, 3).map((item, i) => (
            <div key={`${item.source}-${item.ts ?? i}`} style={{ fontSize: 14, color: "#ffe0a3", marginTop: i === 0 ? 0 : 6, lineHeight: 1.3 }}>
              <span style={{ color: "#ffb020", fontWeight: 700 }}>[{BLOCKED_SOURCE_LABEL[item.source] ?? item.source}]</span>{" "}
              {item.text}
              <span style={{ color: "#c99457" }}> &middot; {item.age}</span>
            </div>
          ))}
        </div>
      )}

      {/* Roster HUD (Company Mode step 5, 2026-09-13): right-edge company
          roster -- emoji/name/status-dot/"Xm ago"/one line of recentOutput
          (<=60 chars) per persona, 22-24px per the 10-foot-readability
          scale used everywhere else on this HUD. GREEN rows pulse
          (.hq-pulse, opacity-only); everything else is static text -- no
          per-row 3D geometry, so this never touches the scene's own budget. */}
      {personas.length > 0 && (
        <div style={{ position: "absolute", top: 70, right: 20, width: 460, display: "flex", flexDirection: "column", gap: 8 }}>
          {personas.map((p) => {
            const color = personaStatusColor(p.status);
            const audit = auditByName.get(p.name);
            const auditColor = auditVerdictColor(audit?.verdict);
            // Hover title (coordinator 2026-09-13: "works-evidence line on
            // hover/plaque") -- native title attribute, a real OS tooltip,
            // cheapest correct way to surface a long evidence string without
            // permanently spending screen space on it.
            const auditTitle = audit
              ? `Audit ${audit.verdict}: ${audit.checks.works.evidence}`
              : "Audit: not yet run for this persona";
            return (
              <div
                key={p.name}
                className={p.status === "GREEN" ? "hq-pulse" : undefined}
                style={{
                  // Pass F (2026-09-13, coordinator's real-monitor capture,
                  // item 4 "reserve the right 480px for the roster"):
                  // opacity 0.6->0.93 -- a 3D-projected lane/persona label
                  // can land anywhere on screen depending on camera angle
                  // (they're not screen-space-aware of this HUD column), so
                  // a near-opaque background is what actually GUARANTEES
                  // this column reads clean regardless of what's behind it,
                  // rather than relying on camera angle alone to avoid
                  // ever placing something back there.
                  background: "rgba(3,4,10,0.93)", border: `1px solid ${color}55`,
                  borderRadius: 8, padding: "6px 12px",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ width: 10, height: 10, borderRadius: 999, flexShrink: 0, background: color, boxShadow: `0 0 6px ${color}` }} />
                  <span style={{ color: "#dff3ff", fontSize: 24, fontWeight: 700, whiteSpace: "nowrap" }}>
                    {p.emoji} {p.name}
                  </span>
                  {/* Audit badge -- a SEPARATE dot from the status dot above
                      (status = "is it firing on schedule", audit = "is the
                      work real" -- the two can disagree, e.g. Treasurer
                      fires on time but has never once produced its
                      deliverable, a ghost this badge is the point of
                      catching). Letter, not just a color, since PASS/WARN
                      both use warm-adjacent hues some viewers won't
                      distinguish by color alone. */}
                  <span
                    title={auditTitle}
                    style={{
                      pointerEvents: "auto", marginLeft: "auto", fontSize: 15, fontWeight: 800,
                      color: "#03040a", background: auditColor, borderRadius: 4,
                      padding: "1px 5px", flexShrink: 0, letterSpacing: 0.5,
                    }}
                  >
                    {audit ? audit.verdict[0] : "?"}
                  </span>
                </div>
                <div style={{ color: "#9fb3cc", fontSize: 24, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", marginTop: 2 }}>
                  {rosterEvidenceText(p.lastFireISO)} &mdash; {truncateOneLine(p.recentOutput, 60)}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Non-kiosk only: Home link, slim */}
      {!kiosk && (
        <div style={{ position: "absolute", top: 16, right: 20, pointerEvents: "auto", display: "flex", alignItems: "center", gap: 14 }}>
          <Link href="/" style={{ color: "#7f93b0", fontSize: 13, textDecoration: "none" }}>
            &larr; Home
          </Link>
        </div>
      )}

      {/* Top-right: presence lamp (kiosk) */}
      {kiosk && (
        <div style={{ position: "absolute", top: 18, right: 20, display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              width: 9, height: 9, borderRadius: 999,
              background: present ? "#22ff88" : "#3a4560",
              boxShadow: present ? "0 0 8px #22ff88" : "none",
            }}
          />
          <span style={{ color: "#7f93b0", fontSize: 13 }}>{present ? "J is here" : "J is away"}</span>
        </div>
      )}

      {/* Bottom ticker (Pass F, 2026-09-13, coordinator's real-monitor
          capture): the OLD version below this comment -- a 40px scrolling
          sentence of raw brief.text, cut off at both ends -- is GONE. It
          directly violated this project's own HQ FACE RULES ("motion =
          events with a ticker," never raw prose) and was the coordinator's
          #5 flagged item. This is now the ONE bottom ticker: the same real
          event lines (lib/useMotionEvents.ts, "they need MEANING") that
          used to sit in a floating stack above the brief scroll, now
          resized to the coordinator's 24-26px spec and given a proper
          bordered strip (matching the removed ticker's own band styling)
          instead of floating transparently over the 3D scene. Newest-first,
          each line ET-stamped, 3 max, static (no scroll needed -- 3 short
          lines already fit one strip width without truncation). */}
      <div
        style={{
          position: "absolute", left: 0, right: 0, bottom: 34, minHeight: 40,
          overflow: "hidden", background: "rgba(3,4,10,0.7)", borderTop: "1px solid rgba(122,217,255,0.18)",
          borderBottom: "1px solid rgba(122,217,255,0.18)", padding: "6px 20px",
          display: "flex", flexDirection: "column-reverse", gap: 2,
        }}
      >
        {motionEvents.length > 0 ? (
          motionEvents.slice(0, 3).map((ev) => (
            <div key={ev.id} style={{ color: "#9fd8ff", fontSize: 25, fontFamily: HUD_FONT, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              <span style={{ color: "#4fd6ff", fontVariantNumeric: "tabular-nums" }}>{ev.tsEt}</span> {ev.text}
            </div>
          ))
        ) : (
          <div style={{ color: "#7f93b0", fontSize: 25, fontFamily: HUD_FONT }}>No events yet this session.</div>
        )}
      </div>

      {/* Bottom-right corner: TV self-reported perf (J must SEE the number) + synced status.
          2026-09-13 bug fix: /api/hq now separates the TV's own reports from a PC-browser
          LAN visit (lib/hq.ts#readLatestHqPerf) -- label says "TV" only when the row's own
          UA actually is one; a PC visit shows as "Last visit" instead so it never gets
          mistaken for the TV's real number. */}
      <div style={{ position: "absolute", bottom: 8, right: 12, textAlign: "right" }}>
        {(() => {
          const p = data?.perf;
          if (!p) return null;
          const isTv = /SMART-TV|Tizen/.test(p.ua);
          return (
            <div style={{ color: "#5c7aa0", fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
              {isTv ? "TV" : "Last visit"} {p.fps} fps · {p.w}x{p.h} · {p.calls} calls
            </div>
          );
        })()}
        <span style={{ color: "#4a5a78", fontSize: 11 }}>{syncedText}</span>
      </div>
    </div>
  );
}
