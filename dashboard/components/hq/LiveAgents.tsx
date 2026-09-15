"use client";

// LIVE-AGENTS pass (2026-09-14, J: "use it to build itself ... watch it
// spawn up agents and see how they move and interact in the world ... make
// sure they move and navigate from place to place properly and have proper
// speech bubbles above their heads"). Real Claude Code sessions/subagents
// (lib/hq-agents.ts's own pulse.jsonl roster, up to 8, most recent first) --
// distinct from the persona bots (Scout/Chef/Coach/...) Agent.tsx already
// animates from crew-events.jsonl.
//
// Deliberately a NEW, smaller component rather than threading a sixth
// independent trigger channel through Agent.tsx (already 5 seen-value-diff
// walk channels, 1250+ lines, entirely persona/lane-tuned -- see that file's
// own header). A live agent's lifecycle is genuinely different from every
// existing AgentWalkKind: it spawns at the entry gate, walks to whichever
// REAL zone its own tool calls are touching right now, can retarget mid-life
// (a session that edits dashboard/ then backtest/), and despawns when the
// server stops reporting it (pulse.jsonl idle timeout) -- never a fixed
// roundtrip/arrival/allhands shape. What IS reused, per this task's own
// brief: KitAgentBody (KitAgent.tsx, the real rigged character + its own
// CLIP_TABLE-driven walk/idle/type animation -- ultra tier only, same tier
// gate as every other real-character render in this tree), the walk graph +
// corridor geometry (layout.ts#findWalkPath -- never a straight line through
// a wall), and the bubble size policy (bubbleText.ts/bubbleScale.ts's
// bubbleCounterScale, the exact function Agent.tsx/GammaCharacter.tsx's own
// head bubbles already use).
//
// Client-only, never imports lib/hq-agents.ts BY VALUE -- that module reads
// node:fs for its own pulse.jsonl tail reader, which must never enter a
// client bundle. Only its `LiveAgentState` TYPE (fully erased at compile
// time) is imported; `ENTRY_NODE_ID` is re-declared here as a plain string
// literal matching that module's own export (see the constant's own comment).

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import { KitAgentBody, WALK_SPEED, type KitAnimState } from "./KitAgent";
import { findWalkPath, type WalkGraph } from "./layout";
import { truncateOneLine } from "./palette";
import { bubbleCounterScale } from "./bubbleText";
import type { LiveAgent } from "./types";
import type { LiveAgentState } from "@/lib/hq-agents";

// Mirrors lib/hq-agents.ts#ENTRY_NODE_ID exactly (hub-center, layout.ts's own
// HUB origin) -- re-declared as a plain literal rather than a value import,
// see this file's own header for why that module can never be imported by
// value from a client component.
const ENTRY_NODE_ID = "hub-center";

// 8 distinct, saturated hues, cycled by arrival order -- deliberately NOT
// HEALTH_COLOR/PERSONA_STATUS_COLOR (palette.ts's own orthogonal-axes rule:
// a live agent's color means "which worker," never a health/status
// semantic) so these never get mistaken for a persona or a lane's own
// status glow ("distinct, readable look... so they don't read as personas"
// per this task's own brief).
const ACCENT_PALETTE = ["#ff6b6b", "#4ecdc4", "#ffe66d", "#a78bfa", "#38bdf8", "#fb923c", "#34d399", "#f472b6"];

const WORK_DWELL_ANIM: KitAnimState = "resting-working-type";
const WALK_ANIM: KitAnimState = "walking";
const MIN_WALK_S = 0.5;
const BUBBLE_HEAD_Y = 1.95; // matches Agent.tsx's ULTRA_HEAD_Y (CHARACTER_TARGET_HEIGHT*CHARACTER_SCALE*0.95) + BUBBLE_HEAD_GAP, re-derived as a plain constant here (small, self-contained component -- see this file's own header on why it does not import Agent.tsx's internals)
const BUBBLE_FADE_DISTANCE = 80; // same floor Agent.tsx's own bubble fade uses

function pathDistance(wp: ReadonlyArray<readonly [number, number, number]>): number {
  let total = 0;
  for (let i = 0; i < wp.length - 1; i++) {
    total += Math.hypot(wp[i + 1][0] - wp[i][0], wp[i + 1][2] - wp[i][2]);
  }
  return total;
}

/** Position + facing at fractional progress `t` (0..1) along a multi-leg
 * path -- a simplified sibling of Agent.tsx#resolvePathPose (no corner-yaw-
 * slerp blend; a live-agent worker's path is at most hub-center -> a couple
 * of corridor nodes -> its desk, so a small facing snap at a corner is an
 * acceptable, honest simplification for this new, separate component). */
function poseAlongPath(
  waypoints: ReadonlyArray<readonly [number, number, number]>,
  t: number,
): { position: [number, number, number]; facing: number } {
  if (waypoints.length === 0) return { position: [0, 0, 0], facing: 0 };
  if (waypoints.length === 1) return { position: [...waypoints[0]], facing: 0 };
  const legDist: number[] = [];
  let total = 0;
  for (let i = 0; i < waypoints.length - 1; i++) {
    const d = Math.hypot(waypoints[i + 1][0] - waypoints[i][0], waypoints[i + 1][2] - waypoints[i][2]);
    legDist.push(d);
    total += d;
  }
  const targetDist = Math.min(1, Math.max(0, t)) * total;
  let cum = 0;
  let legIndex = legDist.length - 1;
  for (let i = 0; i < legDist.length; i++) {
    if (targetDist <= cum + legDist[i] || i === legDist.length - 1) {
      legIndex = i;
      break;
    }
    cum += legDist[i];
  }
  const d = legDist[legIndex] || 0.0001;
  const localT = Math.min(1, Math.max(0, (targetDist - cum) / d));
  const from = waypoints[legIndex];
  const to = waypoints[legIndex + 1];
  const position: [number, number, number] = [
    from[0] + (to[0] - from[0]) * localT,
    from[1],
    from[2] + (to[2] - from[2]) * localT,
  ];
  const facing = Math.atan2(to[0] - from[0], to[2] - from[2]);
  return { position, facing };
}

// ─── Diagnostics (task's own contract: window.__hqLiveAgents, <=4x/s) ──────

export interface LiveAgentDiagEntry {
  id: string;
  label: string;
  state: "spawning" | "walking" | "working" | "leaving";
  pos: [number, number];
  target: string;
  bubble: string;
  bubbleOpacity: number;
  onWalkable: boolean;
}

declare global {
  interface Window {
    __hqLiveAgents?: LiveAgentDiagEntry[];
  }
}

const diagStore = new Map<string, LiveAgentDiagEntry>();
let diagIntervalStarted = false;

function ensureDiagInterval(): void {
  if (diagIntervalStarted || typeof window === "undefined") return;
  diagIntervalStarted = true;
  // 250ms = 4x/s, exactly this task's own "updated at most 4x/s" cap.
  setInterval(() => {
    window.__hqLiveAgents = Array.from(diagStore.values());
  }, 250);
}

// ─── One live-agent avatar ──────────────────────────────────────────────────

interface AvatarProps {
  liveAgentId: string;
  label: string;
  accentColor: string;
  bubble: string;
  walkGraph: WalkGraph;
  targetNodeId: string;
  serverState: LiveAgentState;
  leaving: boolean;
  reducedMotion: boolean;
  onDespawned: () => void;
}

function LiveAgentAvatar({
  liveAgentId, label, accentColor, bubble, walkGraph, targetNodeId, serverState, leaving, reducedMotion, onDespawned,
}: AvatarProps) {
  const group = useRef<THREE.Group>(null);
  const bubbleWrapRef = useRef<HTMLDivElement>(null);
  const bubbleDelta = useMemo(() => new THREE.Vector3(), []);
  const entryPos = useMemo<[number, number, number]>(
    () => (walkGraph.nodes.get(ENTRY_NODE_ID)?.position as [number, number, number] | undefined) ?? [0, 0, 0],
    [walkGraph],
  );

  const currentNode = useRef(ENTRY_NODE_ID);
  const path = useRef<[number, number, number][]>([entryPos, entryPos]);
  const walkDuration = useRef(MIN_WALK_S);
  const needsWalkStart = useRef(true); // first frame: begin the spawn->zone walk
  const walkStartT = useRef(0);
  const phase = useRef<"walking" | "working">("walking");
  const [animState, setAnimState] = useState<KitAnimState>(WALK_ANIM);
  const [walkable, setWalkable] = useState(true);
  const despawned = useRef(false);

  const activeDest = leaving ? ENTRY_NODE_ID : targetNodeId;
  const seenDest = useRef<string | null>(null);
  const leavingRef = useRef(leaving);
  leavingRef.current = leaving;
  const onDespawnedRef = useRef(onDespawned);
  onDespawnedRef.current = onDespawned;

  useEffect(() => {
    group.current?.position.set(...entryPos);
  }, [entryPos]);

  // Kicks a new walk whenever the destination genuinely changes (a fresh
  // zone from a new tool call, or the server dropping this agent -> leaving
  // flips true) -- same seen-value-diff convention Agent.tsx's own trigger
  // channels use, just one channel here since a live agent has exactly one
  // destination concept at a time (no roundtrip/allhands/purposeful variety).
  useEffect(() => {
    if (reducedMotion) {
      currentNode.current = activeDest;
      const pos = (walkGraph.nodes.get(activeDest)?.position as [number, number, number] | undefined) ?? entryPos;
      group.current?.position.set(...pos);
      phase.current = "working";
      setAnimState(WORK_DWELL_ANIM);
      if (leaving && !despawned.current) {
        despawned.current = true;
        onDespawnedRef.current();
      }
      return;
    }
    if (seenDest.current === activeDest) return;
    seenDest.current = activeDest;
    if (currentNode.current === activeDest) {
      // Already standing at the requested node (e.g. spawned straight into
      // the hub zone) -- settle immediately, no walk needed.
      phase.current = "working";
      setAnimState(WORK_DWELL_ANIM);
      if (leaving && !despawned.current) {
        despawned.current = true;
        onDespawnedRef.current();
      }
      return;
    }
    const found = findWalkPath(walkGraph, currentNode.current, activeDest);
    setWalkable(found !== null);
    const wp: [number, number, number][] = found ?? [
      (walkGraph.nodes.get(currentNode.current)?.position as [number, number, number] | undefined) ?? entryPos,
      (walkGraph.nodes.get(activeDest)?.position as [number, number, number] | undefined) ?? entryPos,
    ];
    path.current = wp;
    walkDuration.current = Math.max(MIN_WALK_S, pathDistance(wp) / WALK_SPEED);
    needsWalkStart.current = true;
    phase.current = "walking";
    setAnimState(WALK_ANIM);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeDest, reducedMotion, walkGraph]);

  useFrame((state) => {
    const g = group.current;
    if (!g) return;
    const t = state.clock.elapsedTime;
    if (needsWalkStart.current) {
      needsWalkStart.current = false;
      walkStartT.current = t;
    }
    if (phase.current === "walking") {
      const elapsed = t - walkStartT.current;
      const progress = Math.min(1, elapsed / walkDuration.current);
      const { position, facing } = poseAlongPath(path.current, progress);
      g.position.set(position[0], position[1], position[2]);
      g.rotation.y = facing;
      if (progress >= 1) {
        currentNode.current = activeDest;
        if (leavingRef.current) {
          if (!despawned.current) {
            despawned.current = true;
            onDespawnedRef.current();
          }
        } else {
          phase.current = "working";
          setAnimState(WORK_DWELL_ANIM);
        }
      }
    }

    // Speech-bubble camera-distance fade + counter-scale -- identical policy
    // to Agent.tsx's own updateBubbleFade (bubbleText.ts/bubbleScale.ts's
    // shared bubbleCounterScale), so a live agent's bubble stays readable at
    // exactly the same range a persona's does.
    const el = bubbleWrapRef.current;
    let bubbleOpacity = 1;
    if (el) {
      bubbleDelta.set(g.position.x - state.camera.position.x, g.position.y - state.camera.position.y, g.position.z - state.camera.position.z);
      const dist = bubbleDelta.length();
      bubbleOpacity = dist > BUBBLE_FADE_DISTANCE ? 0 : 1;
      el.style.opacity = String(bubbleOpacity);
      const k = bubbleCounterScale(dist);
      el.style.transform = Math.abs(k - 1) > 0.01 ? `scale(${k.toFixed(3)})` : "";
    }

    const diagState: LiveAgentDiagEntry["state"] =
      leavingRef.current ? "leaving" : phase.current === "walking" ? "walking" : serverState === "spawning" ? "spawning" : "working";
    diagStore.set(liveAgentId, {
      id: liveAgentId,
      label,
      state: diagState,
      pos: [g.position.x, g.position.z],
      target: activeDest,
      bubble,
      bubbleOpacity,
      onWalkable: walkable,
    });
  });

  const bubbleTrunc = truncateOneLine(bubble, 44);

  return (
    <group ref={group}>
      <Suspense fallback={null}>
        <KitAgentBody laneSeed={liveAgentId} animState={animState} accentColor={accentColor} />
      </Suspense>
      <Html position={[0, BUBBLE_HEAD_Y, 0]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
        <div ref={bubbleWrapRef} style={{ position: "relative", transformOrigin: "50% 100%" }}>
          <div className="hq-beam" style={{ "--beam-color": accentColor, borderRadius: 6 } as CSSProperties}>
            <div
              style={{
                position: "relative", overflow: "hidden",
                fontFamily: "system-ui, sans-serif", color: "#dff3ff", fontSize: 24,
                background: "rgba(3,4,10,0.78)", padding: "3px 10px", borderRadius: 5,
                whiteSpace: "nowrap", display: "flex", alignItems: "center", gap: 5,
              }}
            >
              <span key={bubbleTrunc} className="hq-shine" />
              <b style={{ fontWeight: 800 }}>{label}</b>
              <span style={{ color: "#7f93b0" }}>·</span>
              <span>{bubbleTrunc}</span>
            </div>
          </div>
          <div
            style={{
              position: "absolute", left: "50%", bottom: -4, width: 8, height: 8,
              transform: "translateX(-50%) rotate(45deg)",
              background: "rgba(3,4,10,0.78)",
              borderRight: `1px solid ${accentColor}`, borderBottom: `1px solid ${accentColor}`,
            }}
          />
        </div>
      </Html>
    </group>
  );
}

// ─── Roster diffing + mount/unmount ─────────────────────────────────────────

interface DisplayedAgent {
  id: string;
  label: string;
  serverState: LiveAgentState;
  bubble: string;
  targetNodeId: string;
  leaving: boolean;
  accentColor: string;
}

export interface LiveAgentsProps {
  agents: LiveAgent[];
  walkGraph: WalkGraph;
  ultra: boolean;
  reducedMotion: boolean;
}

/**
 * Renders real Claude Code sessions/subagents (lib/hq-agents.ts's own
 * pulse.jsonl roster, server-side) as walking KitAgentBody characters.
 * Diffs the incoming roster against what's currently mounted: a new id ->
 * spawns at the entry gate and walks to its zone; an id whose targetZone
 * changed -> walks to the new zone; an id that dropped out of the incoming
 * list (server-side idle timeout) -> walks back out and unmounts itself
 * once that walk completes (LiveAgentAvatar's own onDespawned callback).
 * Ultra tier only -- see this file's own header for why (real rigged
 * characters, same tier gate as every other KitAgentBody render).
 */
export default function LiveAgents({ agents, walkGraph, ultra, reducedMotion }: LiveAgentsProps) {
  const [displayed, setDisplayed] = useState<Map<string, DisplayedAgent>>(new Map());
  const colorIdx = useRef(new Map<string, number>());
  const nextColorIdx = useRef(0);

  useEffect(() => {
    ensureDiagInterval();
  }, []);

  useEffect(() => {
    setDisplayed((prev) => {
      const next = new Map(prev);
      const seen = new Set<string>();
      for (const a of agents) {
        seen.add(a.id);
        const bubble = `${a.state === "spawning" ? "arrived" : a.state === "cooling" ? "wrapping up" : "working"} · ${a.lastDetail}`;
        if (!colorIdx.current.has(a.id)) {
          colorIdx.current.set(a.id, nextColorIdx.current);
          nextColorIdx.current += 1;
        }
        const accentColor = ACCENT_PALETTE[colorIdx.current.get(a.id)! % ACCENT_PALETTE.length];
        next.set(a.id, {
          id: a.id,
          label: a.label,
          serverState: a.state,
          bubble,
          targetNodeId: a.targetZone,
          leaving: false,
          accentColor,
        });
      }
      // Any currently-displayed id the server no longer reports has gone
      // idle (>=3min with no pulse row) -- mark it "leaving" so its avatar
      // walks back out instead of popping out of existence.
      for (const [id, d] of next) {
        if (!seen.has(id) && !d.leaving) {
          next.set(id, { ...d, leaving: true });
        }
      }
      return next;
    });
  }, [agents]);

  const handleDespawned = (id: string) => {
    diagStore.delete(id);
    colorIdx.current.delete(id);
    setDisplayed((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Map(prev);
      next.delete(id);
      return next;
    });
  };

  if (!ultra) return null;

  return (
    <>
      {Array.from(displayed.values()).map((d) => (
        <LiveAgentAvatar
          key={d.id}
          liveAgentId={d.id}
          label={d.label}
          accentColor={d.accentColor}
          bubble={d.bubble}
          walkGraph={walkGraph}
          targetNodeId={d.targetNodeId}
          serverState={d.serverState}
          leaving={d.leaving}
          reducedMotion={reducedMotion}
          onDespawned={() => handleDespawned(d.id)}
        />
      ))}
    </>
  );
}
