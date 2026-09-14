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
  /** Pass G (2026-09-13, coordinator item 4): "on the ultra tier show THIS
   * device's numbers; the TV line only on the TV tier (or prefixed as a
   * second line, never alone)" -- the perf-line block below needs to know
   * which tier IT is rendering inside to pick data.perf vs data.perfOther
   * correctly; Hud.tsx previously always read data.perf regardless of
   * viewer. */
  tier: "ultra" | "tv";
}

/** Pass G (2026-09-13, coordinator item 1: "split layout... world left,
 * roster right, the Grok-Bot company view J liked"): fixed right-column
 * width shared with UltraCanvasRoot.tsx/CanvasRoot.tsx, whose OWN canvas
 * container is width-constrained to `calc(100% - HUD_RIGHT_COLUMN_WIDTH)`
 * so the 3D canvas physically CANNOT render a pixel under this column --
 * solved by construction, not by the camera-angle/opacity mitigations Pass
 * F tried (which helped but never fully eliminated the collision, per that
 * pass's own honest note). One constant, three files -- exported from here
 * since this component owns the column's actual content. */
export const HUD_RIGHT_COLUMN_WIDTH = 500;

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
export default function Hud({ data, error, kiosk, isValidating, motionEvents, tier }: HudProps) {
  const etClock = useEtClock();
  // LIVE-1 item 1 (2026-09-14): "H toggles the HUD" -- ultra tier only,
  // same scoping as the free camera itself (Scene.tsx's OrbitControls/
  // keyboard fly-to). A plain top-level toggle, not threaded through
  // Scene.tsx/Canvas at all -- this component already owns its own full
  // render tree (both overlay columns), so there is nothing to coordinate
  // with the 3D scene here. Defaults visible; a page reload always starts
  // visible again (no persisted preference -- this is a per-session view
  // toggle, not a setting).
  const [hudVisible, setHudVisible] = useState(true);
  useEffect(() => {
    if (tier !== "ultra") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "h" || e.key === "H") setHudVisible((v) => !v);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tier]);
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
    <>
    {/* LIVE-1 item 1 (2026-09-14): "H toggles the HUD" -- both overlay
        columns below are gated on `hudVisible` (ultra tier only triggers the
        keydown listener above; TV kiosk always renders, same as before this
        pass). */}
    {hudVisible && (
    <div
      style={{
        position: "fixed", top: 0, left: 0, bottom: 0, width: `calc(100% - ${HUD_RIGHT_COLUMN_WIDTH}px)`,
        pointerEvents: "none", fontFamily: HUD_FONT, zIndex: 10, overflow: "hidden",
      }}
    >
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

        /* Free-camera hint strip (LIVE-1 item 1, 2026-09-14): visible on
           mount, holds, then fades -- opacity only. Remounts (via the
           hudVisible-keyed div below) replay this every time H brings the
           HUD back, which doubles as a re-teach of the shortcut. */
        .hq-camera-hint { animation: hq-hint-fade 8s ease-in forwards; }
        @keyframes hq-hint-fade { 0%, 70% { opacity: 0.85; } 100% { opacity: 0; } }
      `}</style>

      {/* Free-camera hint strip (LIVE-1 item 1, 2026-09-14, ultra tier
          only -- the TV kiosk has no OrbitControls/keyboard camera to
          explain, see Scene.tsx's own `ultra`-gated CameraRig). Bottom-left
          of the CANVAS -- this wrapper div is already width-constrained to
          the same `calc(100% - HUD_RIGHT_COLUMN_WIDTH)` the canvas itself
          uses (UltraCanvasRoot.tsx), so `left` here is relative to that same
          box. Sits just above the bottom ticker strip (which occupies
          bottom:34..~74) rather than on top of it. `key={hudVisible}`
          remounts (replaying the fade) whenever H brings the HUD back. */}
      {tier === "ultra" && (
        <div
          key={String(hudVisible)}
          className="hq-camera-hint"
          style={{
            position: "absolute", left: 20, bottom: 84,
            color: "#9fb3cc", fontSize: 14, fontFamily: HUD_FONT,
            background: "rgba(3,4,10,0.55)", padding: "4px 12px", borderRadius: 6,
          }}
        >
          drag orbit &middot; wheel zoom &middot; 1-7 desks &middot; 0 overview &middot; H hides HUD
        </div>
      )}

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

      {/* Bottom-right corner: perf + synced status. Pass G (2026-09-13,
          coordinator item 4: "on the ultra tier show THIS device's
          numbers; the TV line only on the TV tier (or prefixed 'TV:' as a
          second line, never alone)") -- this used to ALWAYS read
          data.perf (the TV-tagged report, matched by UA) regardless of
          which tier was actually rendering it, so an ultra-tier viewer on
          J's own monitor saw a stale/unrelated TV number, never their own.
          Now: ultra tier reads data.perfOther (this session's own report,
          per PerfReporter.tsx's `enabled={kiosk}` gate) as the primary
          line, with the TV's own line added below it ONLY if data.perf
          exists (both labeled, never one bare number with no source). TV
          tier keeps exactly its old single line. */}
      <div style={{ position: "absolute", bottom: 8, right: 12, textAlign: "right" }}>
        {tier === "ultra" ? (
          <>
            {data?.perfOther && (
              <div style={{ color: "#5c7aa0", fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
                This device: {data.perfOther.fps} fps · {data.perfOther.w}x{data.perfOther.h} · {data.perfOther.calls} calls · {data.perfOther.tris} tris
              </div>
            )}
            {data?.perf && (
              <div style={{ color: "#3f4f68", fontSize: 11, fontVariantNumeric: "tabular-nums" }}>
                TV: {data.perf.fps} fps · {data.perf.w}x{data.perf.h} · {data.perf.calls} calls
              </div>
            )}
          </>
        ) : (
          data?.perf && (
            <div style={{ color: "#5c7aa0", fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
              TV: {data.perf.fps} fps · {data.perf.w}x{data.perf.h} · {data.perf.calls} calls
            </div>
          )
        )}
        <span style={{ color: "#4a5a78", fontSize: 11 }}>{syncedText}</span>
      </div>
    </div>
    )}

    {/* Right column (Pass G, 2026-09-13, coordinator item 1): needs-J +
        roster, solid background, normal document flow (no more per-item
        absolute positioning -- there's no camera-angle collision to dodge
        once the canvas physically cannot render under this column). Both
        moved here verbatim from the left overlay above (needs-J was
        top-left, roster was top-right -- now stacked together on the
        right, matching the coordinator's own "Grok-Bot company view"
        reference). Gated on `hudVisible` (LIVE-1 item 1, 2026-09-14) same
        as the left column above. */}
    {hudVisible && (
    <div
      style={{
        position: "fixed", top: 0, right: 0, bottom: 0, width: HUD_RIGHT_COLUMN_WIDTH,
        background: "#03040a", borderLeft: "1px solid rgba(122,217,255,0.15)",
        overflowY: "auto", zIndex: 10, padding: "20px 20px", pointerEvents: "none",
        display: "flex", flexDirection: "column", gap: 16,
      }}
    >
      {/* NEEDS-J card (Company Mode step 7, 2026-09-13): read-only amber
          alert aggregating discord-outbox mentions of J, pending conductor
          proposals, and FABLE-ESCALATION queue lines -- see
          lib/hq.ts#readBlocked. Newest 3 of up to 8; hidden entirely when
          there's nothing blocked so it never occupies space on a clean day. */}
      {blockedItems.length > 0 && (
        <div
          style={{
            background: "rgba(40,26,0,0.75)", border: "1px solid #ffb020", borderRadius: 8,
            padding: "8px 14px", flexShrink: 0,
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

      {/* Roster HUD (Company Mode step 5, 2026-09-13): emoji/name/status-
          dot/"Xm ago"/one line of recentOutput (<=60 chars) per persona,
          22-24px per the 10-foot-readability scale used everywhere else on
          this HUD. GREEN rows pulse (.hq-pulse, opacity-only); everything
          else is static text -- no per-row 3D geometry, so this never
          touches the scene's own budget. Opacity 0.93 (Pass F) kept even
          though the split-column layout (Pass G) makes it structurally
          redundant now -- cheap insurance, never hurts. */}
      {personas.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {personas.map((p) => {
            const color = personaStatusColor(p.status);
            const audit = auditByName.get(p.name);
            const auditColor = auditVerdictColor(audit?.verdict);
            const auditTitle = audit
              ? `Audit ${audit.verdict}: ${audit.checks.works.evidence}`
              : "Audit: not yet run for this persona";
            return (
              <div
                key={p.name}
                className={p.status === "GREEN" ? "hq-pulse" : undefined}
                style={{
                  background: "rgba(3,4,10,0.93)", border: `1px solid ${color}55`,
                  borderRadius: 8, padding: "6px 12px",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ width: 10, height: 10, borderRadius: 999, flexShrink: 0, background: color, boxShadow: `0 0 6px ${color}` }} />
                  <span style={{ color: "#dff3ff", fontSize: 24, fontWeight: 700, whiteSpace: "nowrap" }}>
                    {p.emoji} {p.name}
                  </span>
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
    </div>
    )}
    </>
  );
}
