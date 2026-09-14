"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { HqApiResponse, TradingStatus, CrewEvent, PersonaState } from "./types";
import { auditVerdictColor, hhmmFromEtIso, isRegularTradingHours, minutesSinceEvidence, nowEtDayOfWeek, nowEtMinutes, personaStatusColor } from "./palette";
import type { MotionEvent } from "@/lib/useMotionEvents";
// CREW-2 (roster, 2026-09-14): the crew panel's pill/now/last/next derivation
// -- see lib/crew.ts's own header for why this logic lives there (pure,
// zero fs/fetch, ground truth stays in lib/personas.ts's PersonaState).
import { crewLastLine, crewNextLine, crewNowLine, deriveCrewPill, CREW_PILL_COLOR } from "@/lib/crew";

const BLOCKED_SOURCE_LABEL: Record<string, string> = {
  discord: "Discord",
  conductor_proposal: "Proposal",
  queue_escalation: "Escalation",
  goal_blocked: "Goal",
};

// ─── LIVE-1 item 5 (2026-09-14, coordinator-directed mid-task addition):
//     trading status strip -- "are we ready to trade today?" answered
//     without J asking. Pure functions, no component state -- recomputed
//     every Hud render (which already happens ~1x/sec off useEtClock's own
//     interval), matching this file's existing "read the clock fresh every
//     time" convention. ───────────────────────────────────────────────────

const TRADING_STRIP_COLOR = {
  green: "#22ff88",
  amber: "#ffb020",
  red: "#ff3b3b",
  grey: "#7f93b0",
} as const;
type TradingStripColor = keyof typeof TRADING_STRIP_COLOR;

const WEEKDAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

/** Next 09:30 ET weekday open, in ET minutes-since-midnight + day-of-week
 * terms (the SAME representation nowEtMinutes/nowEtDayOfWeek already use).
 * No market-holiday calendar is among this item's own listed source files,
 * so this is a plain weekday rule (Mon-Fri 09:30 ET) -- an honest,
 * documented simplification, not a claim of full exchange-calendar
 * accuracy (a real holiday would show as a "closed" market that ticks
 * anyway once its own scheduled tasks find nothing to do -- a known gap,
 * not a silent wrong answer). */
function nextOpenText(etMinutes: number, dayOfWeek: number): string {
  const minuteOfDay = etMinutes % (24 * 60);
  const openMin = 9 * 60 + 30;
  if (dayOfWeek >= 1 && dayOfWeek <= 5 && minuteOfDay < openMin) return "today 09:30 ET";
  let d = dayOfWeek;
  let daysAhead = 1;
  for (let i = 0; i < 7; i++) {
    d = (d + 1) % 7;
    if (d >= 1 && d <= 5) break;
    daysAhead++;
  }
  return `${daysAhead === 1 ? "tomorrow" : WEEKDAY_NAMES[d]} 09:30 ET`;
}

interface TradingStrip {
  color: TradingStripColor;
  text: string;
}

/** The one decision tree this whole item is built around -- see the task's
 * own spec: green = armed + a decision within 3min during RTH; amber =
 * readiness YELLOW; red = a decision older than 3min during RTH, or
 * readiness RED; grey = market closed. RED conditions are checked before
 * AMBER (a worse problem must never be masked by a lesser one displaying
 * instead) -- "isRth" itself comes from the SAME explicit-ET clock every
 * other RTH-gated piece of this app already uses (palette.ts's own
 * isRegularTradingHours/Scene.tsx#isRth), never a second clock source. */
function buildTradingStrip(trading: TradingStatus | undefined): TradingStrip {
  if (!trading) return { color: "grey", text: "Trading status unavailable" };
  const etMinutes = nowEtMinutes();
  const dayOfWeek = nowEtDayOfWeek();
  const { readiness, core } = trading;

  if (!isRegularTradingHours(etMinutes, dayOfWeek)) {
    const safeV = core.safe?.verdict ?? "?";
    const boldV = core.bold?.verdict ?? "?";
    return {
      color: "grey",
      text: `MARKET CLOSED · next open ${nextOpenText(etMinutes, dayOfWeek)} · last close: safe ${safeV} / bold ${boldV}`,
    };
  }

  const lastTickIso = [core.safe?.tsEt ?? null, core.bold?.tsEt ?? null].filter((v): v is string => !!v).sort().pop() ?? null;
  const ageMin = minutesSinceEvidence(lastTickIso ?? "");
  const bothArmed = !!core.safe?.armed && !!core.bold?.armed;
  const spy = core.safe?.spy ?? core.bold?.spy ?? null;
  const vix = core.safe?.vix ?? core.bold?.vix ?? null;
  const safeV = core.safe?.verdict ?? "?";
  const boldV = core.bold?.verdict ?? "?";

  let color: TradingStripColor;
  if (readiness.verdict === "RED" || ageMin === null || ageMin > 3) {
    color = "red";
  } else if (readiness.verdict === "YELLOW") {
    color = "amber";
  } else if (bothArmed && ageMin <= 3) {
    color = "green";
  } else {
    color = "amber";
  }

  const readinessPart = readiness.reasonDetail && readiness.verdict !== "GREEN"
    ? `readiness ${readiness.verdict} (${readiness.reasonDetail})`
    : `readiness ${readiness.verdict}`;

  const text = `MARKET OPEN · engine ticking ${hhmmFromEtIso(lastTickIso)} ET · safe ${safeV} / bold ${boldV} · `
    + `SPY ${spy !== null ? spy.toFixed(2) : "?"} · VIX ${vix !== null ? vix.toFixed(1) : "?"} · ${readinessPart}`;

  return { color, text };
}

// ─── R3 event feed (CREW-2, 2026-09-14): merges the existing diff-derived
//     ticker lines (lib/useMotionEvents.ts's MotionEvent[], prose already
//     formatted for reading) with the new crew-events.jsonl rows (which
//     carry a real structured actor -- `who`, optionally `to`) into one
//     capped, avatar-chipped list. Pure functions, no component state. ────

interface FeedRow {
  key: string;
  tsEt: string;
  actor: { emoji: string; color: string; name: string } | null;
  text: string;
}

const FEED_MAX_ROWS = 12;

/** Best-effort actor match for a MotionEvent's already-formatted prose line
 * -- useMotionEvents.ts pushes lines starting `${p.emoji} ${p.name} ...` for
 * every persona-attributable event (fires, walks, RED/recovered). A line
 * with no persona-emoji prefix (a Station-fire summary, an idea-card
 * update, a GPU/presence toggle) legitimately has no single actor and gets
 * no chip -- never a guessed/fabricated one. */
function actorForMotionText(text: string, personas: PersonaState[]): FeedRow["actor"] {
  for (const p of personas) {
    if (text.startsWith(p.emoji)) return { emoji: p.emoji, color: p.color, name: p.name };
  }
  return null;
}

/** Builds the merged, capped, newest-first feed. crew-events.jsonl rows
 * (structured, real `who`/`to`) lead; the existing motion-diff ticker lines
 * fill the remainder -- both are genuinely "what it reads today," per R3's
 * own spec, merged rather than either one replacing the other. Every " -> "
 * separator (both sources use plain ASCII arrows) renders as "→" for
 * handoff/interaction rows, uniformly. */
// A crew-events.jsonl row's own `line` sometimes ALREADY embeds the actor
// ("Coach: Gamma_Funnel_5 went Disabled"), sometimes doesn't ("8 lanes --
// 4 GREEN..."), and `to` is set on effectively every row (the producer uses
// it as a "who reads this" routing target, not only genuine handoffs) --
// verified against the live file this session (both shapes seen from the
// SAME `who`). Blindly prepending "${who} -> ${to}:" doubled the actor name
// on the first shape ("Coach -> Gamma: Coach: ... went Disabled"). Fixed by
// skipping the prefix when `line` already starts with it.
function formatCrewLine(e: CrewEvent): string {
  const withPrefix = e.line.startsWith(`${e.who}:`);
  if (withPrefix) return e.line;
  if (e.to) return `${e.who} → ${e.to}: ${e.line}`;
  return `${e.who}: ${e.line}`;
}

// crew-events.jsonl can carry a same-timestamp BURST (e.g. a one-time
// backfill of N "task went Disabled" rows) that would otherwise fill the
// entire row budget with one repeated shape and crowd out every other kind
// of activity -- the opposite of R3's own goal ("see these people
// interacting," plural). Capping crew's share below the full budget
// guarantees the motion-diff ticker (idea cards, handoffs, fires) always
// gets some room too.
const CREW_SHARE_MAX = Math.ceil(FEED_MAX_ROWS * 0.6);

function buildFeedRows(motionEvents: MotionEvent[], crewEvents: CrewEvent[], personas: PersonaState[]): FeedRow[] {
  const personaByName = new Map(personas.map((p) => [p.name, p]));
  const crewSlice = crewEvents.slice(-CREW_SHARE_MAX).reverse();
  const crewRows: FeedRow[] = crewSlice.map((e, i) => {
    const p = personaByName.get(e.who);
    const hhmm = /(\d{2}):(\d{2})/.exec(e.ts_et);
    return {
      key: `crew-${e.ts_et}-${i}`,
      tsEt: hhmm ? `${hhmm[1]}:${hhmm[2]}` : "--:--",
      actor: p ? { emoji: p.emoji, color: p.color, name: p.name } : null,
      text: formatCrewLine(e).replace(/ -> /g, " → "),
    };
  });
  const motionRows: FeedRow[] = motionEvents.map((ev) => ({
    key: `motion-${ev.id}`,
    tsEt: ev.tsEt,
    actor: actorForMotionText(ev.text, personas),
    text: ev.text.replace(/ -> /g, " → "),
  }));
  return [...crewRows, ...motionRows].slice(0, FEED_MAX_ROWS);
}

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
  // R3 (CREW-2): merged, capped, newest-first event feed -- see this file's
  // own buildFeedRows() header comment for the two sources it merges.
  const feedRows = buildFeedRows(motionEvents, data?.crewEvents ?? [], personas);
  // Company audit badge (commit 58d0b9c6, coordinator 2026-09-13: "the
  // roster must show ghosts as ghosts") -- matched by name, the same string
  // on both sides (PersonaState.name / PersonaAudit.name). `data.audit` is
  // null on an old build or a failed audit run (fail-open) -- every lookup
  // below falls back to "no badge" rather than a fake verdict.
  const auditByName = new Map((data?.audit?.personas ?? []).map((a) => [a.name, a]));
  // CREW-2 (roster): one "now" reference per render for every card's next:
  // line (lib/crew.ts#crewNextLine takes explicit time, never Date.now()
  // buried inside it) -- this component already re-renders ~1x/sec via
  // useEtClock's own interval, so this stays fresh without a second timer.
  const nowMs = Date.now();

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

        /* Ideas-wall card flip (LIVE-1 item 2d, 2026-09-14): IdeasWall.tsx
           applies this to every card row -- a keyed React list only ever
           MOUNTS (replaying this) a row whose id is genuinely new, an
           existing card's row is REUSED (no remount, no replay) when the
           list just shifts around it. transform + opacity only. */
        .hq-card-flip { animation: hq-card-flip-in 0.5s ease-out; transform-origin: top center; }
        @keyframes hq-card-flip-in { 0% { transform: rotateX(-85deg); opacity: 0; } 100% { transform: rotateX(0deg); opacity: 1; } }

        /* Free-camera hint strip (LIVE-1 item 1, 2026-09-14): visible on
           mount, holds, then fades -- opacity only. Remounts (via the
           hudVisible-keyed div below) replay this every time H brings the
           HUD back, which doubles as a re-teach of the shortcut. */
        .hq-camera-hint { animation: hq-hint-fade 8s ease-in forwards; }
        @keyframes hq-hint-fade { 0%, 70% { opacity: 0.85; } 100% { opacity: 0; } }

        /* CREW-2 (roster, 2026-09-14): crew card hover/focus -- NOT bound by
           the "transform/opacity/background-position only" rule the
           continuous @keyframes classes above follow, because this only
           ever runs off a real mouse-hover/keyboard-focus event, which the
           TV kiosk (no pointer, no keyboard) can never trigger -- there is
           no always-on TV-compositor cost here to guard against. Cheap
           properties anyway (border-color/background/transform, no blur or
           shadow spread). R2: click/Enter/Space flies the camera to that
           persona's desk (Scene.tsx's own keydown listener, dispatched via
           a synthetic KeyboardEvent -- never a Scene.tsx edit). */
        .hq-crew-card { transition: border-color 0.15s ease, background 0.15s ease, transform 0.15s ease; }
        .hq-crew-card:hover { border-color: rgba(122,217,255,0.65); background: rgba(9,13,24,0.97); transform: translateX(-2px); }
        .hq-crew-card:focus-visible { outline: 2px solid #7ad9ff; outline-offset: 2px; }
      `}</style>

      {/* Free-camera hint strip (LIVE-1 item 1, 2026-09-14, ultra tier
          only -- the TV kiosk has no OrbitControls/keyboard camera to
          explain, see Scene.tsx's own `ultra`-gated CameraRig). Bottom-left
          of the CANVAS -- this wrapper div is already width-constrained to
          the same `calc(100% - HUD_RIGHT_COLUMN_WIDTH)` the canvas itself
          uses (UltraCanvasRoot.tsx), so `left` here is relative to that same
          box. Sits above the bottom stack (ticker + item-5 trading strip,
          now one flex-column wrapper anchored at bottom:34 -- see that
          wrapper's own comment for why a hand-guessed pixel gap doesn't
          work here, the ticker's real height varies 1-3 lines). 195
          clears that wrapper's worst case (a full 3-line ticker + the
          trading strip) with margin -- verified against a real capture.
          `key={hudVisible}` remounts (replaying the fade) whenever H
          brings the HUD back. */}
      {tier === "ultra" && (
        <div
          key={String(hudVisible)}
          className="hq-camera-hint"
          style={{
            position: "absolute", left: 20, bottom: 195,
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
        {/* LIVE-1 item 3 (2026-09-14) follow-up: a text-shadow, not a color
            change -- the sky behind this overlay now legitimately brightens
            by day (SkyDome.tsx), and this medium-gray clock text had
            nothing else to keep it readable against that brighter
            background (the title next to it already had its own glow
            shadow). A soft dark halo keeps it legible against ANY sky
            brightness, day or night, without changing its look at night. */}
        <span style={{ color: "#7f93b0", fontSize: 20, fontVariantNumeric: "tabular-nums", textShadow: "0 1px 4px rgba(0,0,0,0.7)" }}>{etClock}</span>
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

      {/* Bottom stack: trading strip (LIVE-1 item 5) above the ticker
          (Pass F). A SINGLE flex-column wrapper anchored at bottom:34
          (instead of each strip hand-positioned with its own guessed
          `bottom` pixel offset) -- the ticker's own height is DYNAMIC (1-3
          lines depending on motionEvents.length, `minHeight:40` was never a
          cap), so a fixed `bottom:76` on a sibling above it overlapped the
          ticker's real (often ~100px+) rendered height the first time this
          shipped, caught on a real capture (hq-live-5.png) with 3 ticker
          lines showing. Normal (non-reversed) column flow: the FIRST child
          below renders at the TOP of this auto-height box, the LAST child
          renders at the BOTTOM (closest to bottom:34) -- so the trading
          strip (first) always sits directly above the ticker (last)
          regardless of how many ticker lines are currently showing. */}
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 34, display: "flex", flexDirection: "column" }}>
        {/* Trading status strip (LIVE-1 item 5, 2026-09-14, coordinator-
            directed: "so J never has to ask 'are we ready to trade
            today?'") -- same full-width banded-strip convention as the
            ticker below it, one line, colored by buildTradingStrip's own
            decision tree. */}
        {(() => {
          const strip = buildTradingStrip(data?.trading);
          const c = TRADING_STRIP_COLOR[strip.color];
          return (
            <div
              style={{
                background: "rgba(3,4,10,0.75)", borderTop: `1px solid ${c}55`, borderBottom: `1px solid ${c}55`,
                padding: "5px 20px", display: "flex", alignItems: "center", gap: 8, flexShrink: 0,
              }}
            >
              <span style={{ width: 10, height: 10, borderRadius: 999, flexShrink: 0, background: c, boxShadow: `0 0 6px ${c}` }} />
              <span style={{ color: "#dff3ff", fontSize: 20, fontFamily: HUD_FONT, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {strip.text}
              </span>
            </div>
          );
        })()}

        {/* R3 event feed (CREW-2, 2026-09-14, J's verdict: "we still need to
            see these people interacting and actually working on stuff...
            right now it's just a bunch of random text"). Replaces the old
            3-row 25px ticker: up to 12 rows at 15px, each ET-stamped, with
            the actor's avatar chip when one is known (buildFeedRows() above
            -- never a guessed chip), consecutive same-actor rows grouped
            (the chip renders once per run, not per row) so a burst of
            activity from one persona reads as one block, not noise. Sources
            merged in buildFeedRows(): crew-events.jsonl (structured, real
            `who`/`to`) plus the existing motion-diff ticker lines
            (lib/useMotionEvents.ts). Static, no scroll -- content is always
            <=FEED_MAX_ROWS by construction. */}
        <div
          style={{
            flexShrink: 0, background: "rgba(3,4,10,0.7)", borderTop: "1px solid rgba(122,217,255,0.18)",
            borderBottom: "1px solid rgba(122,217,255,0.18)", padding: "6px 20px",
            display: "flex", flexDirection: "column", gap: 3, fontVariantNumeric: "tabular-nums",
          }}
        >
          {feedRows.length > 0 ? (
            feedRows.map((row, i) => {
              const showChip = i === 0 || feedRows[i - 1].actor?.name !== row.actor?.name;
              return (
                <div key={row.key} style={{ display: "flex", alignItems: "center", gap: 7 }}>
                  <span style={{ color: "#4fd6ff", fontSize: 13, flexShrink: 0, width: 38 }}>{row.tsEt}</span>
                  <span
                    style={{
                      width: 18, height: 18, borderRadius: 5, flexShrink: 0, fontSize: 11,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      visibility: showChip && row.actor ? "visible" : "hidden",
                      background: row.actor ? `${row.actor.color}33` : "transparent",
                      border: row.actor ? `1px solid ${row.actor.color}88` : "none",
                    }}
                  >
                    {row.actor?.emoji ?? ""}
                  </span>
                  <span style={{ color: "#9fd8ff", fontSize: 15, fontFamily: HUD_FONT, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {row.text}
                  </span>
                </div>
              );
            })
          ) : (
            <div style={{ color: "#7f93b0", fontSize: 15, fontFamily: HUD_FONT }}>No events yet this session.</div>
          )}
        </div>
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

      {/* CREW-2 roster panel (2026-09-14, J's verdict: "that needs a lot of
          work... right now it's just some very large text" / "why are they
          on here if they're not doing anything?"). Replaces the old bare
          emoji+dot+"Xm ago -- text" rows with a real card per persona: an
          avatar chip, name + short role, a STATUS PILL that always carries
          a REASON (never a bare dot -- lib/crew.ts#deriveCrewPill reads
          PersonaState.quietReason, R4), then now:/last:/next: lines. Click
          (or Enter/Space when focused) flies the camera to that persona's
          desk -- R2, see this file's own .hq-crew-card style comment.
          Sizes per spec: names 18-20px, body 14-15px, pills 12px uppercase.
          GREEN rows still pulse via the pre-existing .hq-pulse class. */}
      {personas.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, fontVariantNumeric: "tabular-nums" }}>
          {personas.map((p, i) => {
            const color = personaStatusColor(p.status);
            const audit = auditByName.get(p.name);
            const auditColor = auditVerdictColor(audit?.verdict);
            const auditTitle = audit
              ? `Audit ${audit.verdict}: ${audit.checks.works.evidence}`
              : "Audit: not yet run for this persona";
            const pill = deriveCrewPill(p);
            const pillColor = CREW_PILL_COLOR[pill.kind];
            const nowLine = crewNowLine(p);
            const lastLine = crewLastLine(p);
            const nextLine = crewNextLine(p, nowMs);
            // R2: keys "1".."7" index cameraPresets[0..6] = [Gamma, ...6
            // personas] in Scene.tsx's own fixed order -- IDENTICAL to this
            // `personas` array's own order (both come from collectCompany()).
            // A synthetic window keydown is the only integration point --
            // Scene.tsx's listener is not edited (not this builder's file).
            const flyToDesk = () => window.dispatchEvent(new KeyboardEvent("keydown", { key: String(i + 1) }));
            return (
              <div
                key={p.name}
                className={`hq-crew-card${p.status === "GREEN" ? " hq-pulse" : ""}`}
                role="button"
                tabIndex={0}
                aria-label={`Fly to ${p.name}'s desk`}
                onClick={flyToDesk}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); flyToDesk(); }
                }}
                style={{
                  background: "rgba(3,4,10,0.93)", border: `1px solid ${color}55`,
                  borderRadius: 10, padding: "10px 12px", cursor: "pointer",
                  pointerEvents: "auto", opacity: pill.kind === "GHOST" ? 0.72 : 1,
                }}
              >
                <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                  <span
                    style={{
                      width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 17, background: `${p.color}2e`, border: `1px solid ${p.color}99`,
                    }}
                  >
                    {p.emoji}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ color: "#dff3ff", fontSize: 19, fontWeight: 800, letterSpacing: 0.2, whiteSpace: "nowrap" }}>
                        {p.name}
                      </span>
                      <span
                        title={auditTitle}
                        style={{
                          pointerEvents: "auto", marginLeft: "auto", fontSize: 13, fontWeight: 800,
                          color: "#03040a", background: auditColor, borderRadius: 4,
                          padding: "1px 5px", flexShrink: 0, letterSpacing: 0.5,
                        }}
                      >
                        {audit ? audit.verdict[0] : "?"}
                      </span>
                    </div>
                    <div style={{ color: "#7f93b0", fontSize: 12.5, lineHeight: 1.3, marginTop: 1 }}>{p.role}</div>
                  </div>
                </div>

                <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span
                    style={{
                      fontSize: 12, fontWeight: 800, textTransform: "uppercase", letterSpacing: 0.9,
                      padding: "2px 8px", borderRadius: 999, flexShrink: 0,
                      color: "#03040a", background: pillColor,
                    }}
                  >
                    {pill.kind}
                  </span>
                  <span style={{ fontSize: 13.5, color: "#9fb3cc", lineHeight: 1.35 }}>{pill.reason}</span>
                </div>

                {nowLine && (
                  <div style={{ fontSize: 14, color: "#cfe9ff", marginTop: 6, lineHeight: 1.35 }}>
                    <span style={{ color: "#5c7aa0", fontWeight: 700 }}>now </span>{nowLine}
                  </div>
                )}
                <div style={{ fontSize: 13, color: "#8296b3", marginTop: 4, lineHeight: 1.35, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  <span style={{ color: "#5c7aa0", fontWeight: 700 }}>last </span>{lastLine}
                </div>
                <div style={{ fontSize: 13, color: "#6c81a0", marginTop: 2, lineHeight: 1.35 }}>
                  <span style={{ color: "#5c7aa0", fontWeight: 700 }}>next </span>{nextLine}
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
