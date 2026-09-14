"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { HqApiResponse } from "./types";
import { personaStatusColor, timeAgoText } from "./palette";
import type { MotionEvent } from "@/lib/useMotionEvents";

const BLOCKED_SOURCE_LABEL: Record<string, string> = {
  discord: "Discord",
  conductor_proposal: "Proposal",
  queue_escalation: "Escalation",
};

/** One line, <=60 chars, per the roster panel's own spec -- collapses
 * newlines/repeated whitespace first so a multi-line recentOutput preview
 * (several collectors return a few lines) still reads as a single line. */
function truncateOneLine(text: string | null, max: number): string {
  if (!text) return "no output yet";
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat;
}

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
  const brief = data?.brief.text || "NO DATA -- no brief written yet";
  const personas = data?.company?.personas ?? [];
  const blockedItems = data?.blocked ?? [];

  return (
    <div style={{ position: "fixed", inset: 0, pointerEvents: "none", fontFamily: HUD_FONT, zIndex: 10 }}>
      <style>{`
        @keyframes hq-ticker-scroll {
          from { transform: translateX(100vw); }
          to { transform: translateX(-100%); }
        }

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
              <span style={{ color: "#c99457" }}> &middot; {timeAgoText(item.ts)}</span>
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
            return (
              <div
                key={p.name}
                className={p.status === "GREEN" ? "hq-pulse" : undefined}
                style={{
                  background: "rgba(3,4,10,0.6)", border: `1px solid ${color}55`,
                  borderRadius: 8, padding: "6px 12px",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ width: 10, height: 10, borderRadius: 999, flexShrink: 0, background: color, boxShadow: `0 0 6px ${color}` }} />
                  <span style={{ color: "#dff3ff", fontSize: 24, fontWeight: 700, whiteSpace: "nowrap" }}>
                    {p.emoji} {p.name}
                  </span>
                </div>
                <div style={{ color: "#9fb3cc", fontSize: 22, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", marginTop: 2 }}>
                  {timeAgoText(p.lastFireISO)} &mdash; {truncateOneLine(p.recentOutput, 60)}
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

      {/* Event ticker (J 2026-09-13, "they need MEANING"): the last ~3 real
          events that caused an agent to move, newest first, each with its
          ET time -- see lib/useMotionEvents.ts for the exact event->text
          mapping. Static stack (not scrolling like the brief below it) so
          all 3 stay readable at once; sits directly above the brief ticker. */}
      {motionEvents.length > 0 && (
        <div style={{ position: "absolute", left: 20, bottom: 78, maxWidth: "62vw", display: "flex", flexDirection: "column-reverse", gap: 2 }}>
          {motionEvents.slice(0, 3).map((ev) => (
            <div key={ev.id} style={{ color: "#7fd8b0", fontSize: 22, fontFamily: HUD_FONT, textShadow: "0 0 8px rgba(3,4,10,0.9)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              <span style={{ color: "#4fd6ff", fontVariantNumeric: "tabular-nums" }}>{ev.tsEt}</span> {ev.text}
            </div>
          ))}
        </div>
      )}

      {/* Bottom ticker: scrolling brief text -- ~26px per the readability pass */}
      <div
        style={{
          position: "absolute", left: 0, right: 0, bottom: 34, height: 40,
          overflow: "hidden", background: "rgba(3,4,10,0.6)", borderTop: "1px solid rgba(122,217,255,0.18)",
          borderBottom: "1px solid rgba(122,217,255,0.18)",
        }}
      >
        <div
          style={{
            whiteSpace: "nowrap", color: "#9fd8ff", fontSize: 26, lineHeight: "40px",
            display: "inline-block", animation: "hq-ticker-scroll 65s linear infinite",
          }}
        >
          {brief}
        </div>
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
