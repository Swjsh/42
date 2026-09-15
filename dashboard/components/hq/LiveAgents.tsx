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
// time) is imported.
//
// COORDINATOR FIX (2026-09-14, browser verification of e990319f found 2
// defects): the walk-decision math (DEFECT 2, stuck leave) and the stand-
// slot ring math (DEFECT 1, stacking) both moved into liveAgentWalk.ts, a
// pure react/three-free sibling module -- see that file's own header for
// the root-cause writeup and the fix each pure function encodes. This file
// now only wires those pure decisions to real refs/THREE objects/r3f hooks.

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import { KitAgentBody, WALK_SPEED, type KitAnimState } from "./KitAgent";
import { findWalkPath, type WalkGraph } from "./layout";
import { truncateOneLine } from "./palette";
import { bubbleCounterScale } from "./bubbleText";
import { PRIORITY } from "./labelDeclutter";
import { useLabelDeclutter } from "./useLabelDeclutter";
import { CHARACTER_SCALE, CHARACTER_TARGET_HEIGHT } from "./SetKit";
import type { LiveAgent } from "./types";
import type { LiveAgentState } from "@/lib/hq-agents";
import {
  computeStandSlot, decideNextWalk, ENTRY_NODE_ID, pathDistance, poseAlongPath, reconcileLiveAgentRoster,
  STAND_BUBBLE_Y_STEP, STAND_RING_RADIUS,
} from "./liveAgentWalk";

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
// BUBBLE-FIX (2026-09-15, coordinator review item 2): this used to be a bare
// literal 1.95 with a comment claiming it "matches" Agent.tsx's own derived
// ULTRA_HEAD_Y + BUBBLE_HEAD_GAP -- it did not: Agent.tsx derives
// ULTRA_HEAD_Y = CHARACTER_TARGET_HEIGHT(1.8) * CHARACTER_SCALE(1.25) * 0.95
// = 2.1375, + BUBBLE_HEAD_GAP(0.3) = 2.4375, not 1.95. The stale literal put
// live-agent bubbles at head height instead of above the head (confirmed on
// bench-live-agents-0038.png). Now genuinely DERIVED from the same imported
// SetKit.tsx constants Agent.tsx itself uses, so the two can never drift
// apart again.
const ULTRA_HEAD_Y = CHARACTER_TARGET_HEIGHT * CHARACTER_SCALE * 0.95;
const BUBBLE_HEAD_GAP = 0.3;
const BUBBLE_HEAD_Y = ULTRA_HEAD_Y + BUBBLE_HEAD_GAP;
const BUBBLE_FADE_DISTANCE = 80; // same floor Agent.tsx's own bubble fade uses
// DEFECT 2 fix, defense in depth: a hard ceiling on how long an avatar may
// stay in "leaving" without despawning. liveAgentWalk.ts#decideNextWalk's
// own fix (leaving is now decided independently of the ordinary-retargeting
// latch) should make this unreachable in practice -- this is a second,
// independent backstop so no OTHER, yet-undiscovered stall can strand an
// avatar in the world forever (this codebase's own "no silent stuck state"
// convention -- see CLAUDE.md's OP-25/failure-honesty rules).
const LEAVE_HARD_TIMEOUT_S = 12;

// ─── Diagnostics (task's own contract: window.__hqLiveAgents, <=4x/s) ──────

export interface LiveAgentDiagEntry {
  id: string;
  label: string;
  state: "spawning" | "walking" | "working" | "leaving";
  pos: [number, number];
  target: string;
  bubble: string;
  /** BUBBLE-FIX (2026-09-15): the full, un-classified, un-truncated row
   * text (lib/hq-agents.ts's own `rawDetail` field) -- kept here purely for
   * debugging so the classified `bubble` text above can always be checked
   * against what pulse.py actually recorded. */
  rawDetail: string;
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
  rawDetail: string;
  walkGraph: WalkGraph;
  targetNodeId: string;
  serverState: LiveAgentState;
  leaving: boolean;
  reducedMotion: boolean;
  /** DEFECT 1 fix: this avatar's own [x,z] nudge off the bare node position,
   * and its stable slot index within the group of agents sharing that same
   * destination -- see liveAgentWalk.ts#computeStandSlot. Recomputed by the
   * parent every time the roster/leaving-set changes; read fresh each time
   * a walk is (re)decided, never snapshotted early. */
  standOffset: [number, number];
  standIndex: number;
  onDespawned: () => void;
}

function nodePosition(walkGraph: WalkGraph, id: string, fallback: [number, number, number]): [number, number, number] {
  return (walkGraph.nodes.get(id)?.position as [number, number, number] | undefined) ?? fallback;
}

function LiveAgentAvatar({
  liveAgentId, label, accentColor, bubble, rawDetail, walkGraph, targetNodeId, serverState, leaving, reducedMotion,
  standOffset, standIndex, onDespawned,
}: AvatarProps) {
  const group = useRef<THREE.Group>(null);
  const bubbleWrapRef = useRef<HTMLDivElement>(null);
  const bubbleDelta = useMemo(() => new THREE.Vector3(), []);
  const entryPos = useMemo<[number, number, number]>(
    () => nodePosition(walkGraph, ENTRY_NODE_ID, [0, 0, 0]),
    [walkGraph],
  );

  const currentNode = useRef(ENTRY_NODE_ID);
  const path = useRef<[number, number, number][]>([entryPos, entryPos]);
  const walkDest = useRef(ENTRY_NODE_ID);
  const walkDespawnsOnArrival = useRef(false);
  const walkDuration = useRef(MIN_WALK_S);
  const needsWalkStart = useRef(true); // first frame: begin the spawn->zone walk
  const walkStartT = useRef(0);
  const phase = useRef<"walking" | "working">("walking");
  const [animState, setAnimState] = useState<KitAnimState>(WALK_ANIM);
  const [walkable, setWalkable] = useState(true);
  const despawned = useRef(false);

  // DEFECT 2 fix: `seenTarget` is used ONLY for ordinary (non-leaving)
  // retargeting; `leaveTriggered` is a wholly separate one-shot latch for
  // the final leave-to-entry walk, so the two can never collide on a
  // coincidental shared string value -- see liveAgentWalk.ts's own header.
  const seenTarget = useRef<string | null>(null);
  const leaveTriggered = useRef(false);
  const leavingRef = useRef(leaving);
  leavingRef.current = leaving;
  const leaveStartedAtT = useRef<number | null>(null);
  const onDespawnedRef = useRef(onDespawned);
  onDespawnedRef.current = onDespawned;
  const standOffsetRef = useRef(standOffset);
  standOffsetRef.current = standOffset;

  useEffect(() => {
    group.current?.position.set(...entryPos);
  }, [entryPos]);

  function fireDespawn(): void {
    if (despawned.current) return;
    despawned.current = true;
    onDespawnedRef.current();
  }

  /** Resolves a walk-graph node id to its actual STAND point -- the bare
   * node position plus this avatar's own current ring offset (DEFECT 1
   * fix). Reads `standOffsetRef` live (not a snapshot) so a mid-walk group
   * change (another agent arriving/leaving the same zone) still lands this
   * avatar on its most current slot once it actually arrives. */
  function standPointFor(nodeId: string): [number, number, number] {
    const base = nodePosition(walkGraph, nodeId, entryPos);
    const [ox, oz] = standOffsetRef.current;
    return [base[0] + ox, base[1], base[2] + oz];
  }

  // Kicks a new walk whenever the destination genuinely changes (a fresh
  // zone from a new tool call, or the server dropping this agent -> leaving
  // flips true). Uses liveAgentWalk.ts#decideNextWalk (pure, unit-tested)
  // for the actual decision -- this effect only carries out whatever that
  // function says.
  useEffect(() => {
    if (reducedMotion) {
      const dest = leaving ? ENTRY_NODE_ID : targetNodeId;
      currentNode.current = dest;
      group.current?.position.set(...standPointFor(dest));
      phase.current = "working";
      setAnimState(WORK_DWELL_ANIM);
      if (leaving) fireDespawn();
      return;
    }

    const decision = decideNextWalk({
      leaving,
      targetNodeId,
      currentNode: currentNode.current,
      seenTarget: seenTarget.current,
      leaveTriggered: leaveTriggered.current,
    });
    if (decision.action === "none") return;
    if (leaving) {
      leaveTriggered.current = true;
      if (leaveStartedAtT.current === null) leaveStartedAtT.current = performance.now() / 1000;
    } else {
      seenTarget.current = targetNodeId;
    }

    if (decision.action === "settle") {
      currentNode.current = decision.dest;
      group.current?.position.set(...standPointFor(decision.dest));
      phase.current = "working";
      setAnimState(WORK_DWELL_ANIM);
      if (decision.despawn) fireDespawn();
      return;
    }

    // decision.action === "walk"
    const found = findWalkPath(walkGraph, currentNode.current, decision.dest);
    setWalkable(found !== null);
    const rawPath: [number, number, number][] = found ?? [
      nodePosition(walkGraph, currentNode.current, entryPos),
      nodePosition(walkGraph, decision.dest, entryPos),
    ];
    // Only the FINAL waypoint gets the stand-offset nudge -- every earlier
    // corridor/doorway waypoint stays exactly on the real walk-graph node so
    // the route itself is unaffected, and only the arrival point spreads
    // agents apart (DEFECT 1's own fix target).
    const wp = rawPath.length > 0
      ? [...rawPath.slice(0, -1), standPointFor(decision.dest)]
      : [standPointFor(decision.dest)];
    path.current = wp;
    walkDest.current = decision.dest;
    walkDespawnsOnArrival.current = decision.despawn;
    walkDuration.current = Math.max(MIN_WALK_S, pathDistance(wp) / WALK_SPEED);
    needsWalkStart.current = true;
    phase.current = "walking";
    setAnimState(WALK_ANIM);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leaving, targetNodeId, reducedMotion, walkGraph]);

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
        currentNode.current = walkDest.current;
        if (walkDespawnsOnArrival.current) {
          fireDespawn();
        } else {
          phase.current = "working";
          setAnimState(WORK_DWELL_ANIM);
        }
      }
    }

    // Hard backstop (see LEAVE_HARD_TIMEOUT_S's own comment): if this avatar
    // has been leaving for too long without despawning -- any mechanism,
    // known or not -- force it out rather than stranding it in the world.
    if (leavingRef.current && !despawned.current && leaveStartedAtT.current !== null) {
      if (performance.now() / 1000 - leaveStartedAtT.current > LEAVE_HARD_TIMEOUT_S) {
        fireDespawn();
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
      target: leaving ? ENTRY_NODE_ID : targetNodeId,
      bubble,
      rawDetail,
      bubbleOpacity,
      onWalkable: walkable,
    });
  });

  const bubbleTrunc = truncateOneLine(bubble, 44);
  // DEFECT 1 fix (bubble half): a small per-slot Y stagger on top of the
  // shared head height so 2+ overlapping bubbles read as a short stack
  // instead of one illegible smear of text.
  const bubbleY = BUBBLE_HEAD_Y + standIndex * STAND_BUBBLE_Y_STEP;
  // DECLUTTER pass: registers with the SHARED screen-space resolver (this
  // avatar's own group ref moves every frame -- see Agent.tsx's identical
  // "pure Y-offset survives Y-axis rotation exactly" reasoning for why
  // group.position + [0, bubbleY, 0] is the real Html world position, not
  // an approximation). Live agents + Gamma are the top declutter tier per
  // the brief ("live-agent bubbles and Gamma > persona bubbles > plaque >
  // lane labels").
  const declutterWorldPos = useMemo(
    () => (): [number, number, number] => {
      const g = group.current;
      return g ? [g.position.x, g.position.y + bubbleY, g.position.z] : [0, bubbleY, 0];
    },
    [bubbleY],
  );
  const declutterRef = useLabelDeclutter(`live:${liveAgentId}`, PRIORITY.LIVE_AGENT, declutterWorldPos);

  return (
    <group ref={group}>
      <Suspense fallback={null}>
        <KitAgentBody laneSeed={liveAgentId} animState={animState} accentColor={accentColor} />
      </Suspense>
      <Html position={[0, bubbleY, 0]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
        {/* DECLUTTER pass: outer wrapper the shared resolver owns, kept
            separate from `bubbleWrapRef`'s own camera-distance fade/scale --
            see Agent.tsx's identical convention/comment. */}
        <div ref={declutterRef} style={{ transformOrigin: "50% 100%" }}>
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
  rawDetail: string;
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

  // BUBBLE-FIX (2026-09-15): the actual diff/mark-leaving logic now lives in
  // liveAgentWalk.ts#reconcileLiveAgentRoster (pure, unit-tested against the
  // exact "one id replaced by another in the same poll" scenario the
  // coordinator's live-browser review flagged) -- this effect only supplies
  // the per-agent display-record builder (color assignment + bubble text
  // are side-effecting/component-local, so they stay here).
  useEffect(() => {
    setDisplayed((prev) =>
      reconcileLiveAgentRoster(prev, agents, (a) => {
        const bubble = `${a.state === "spawning" ? "arrived" : a.state === "cooling" ? "wrapping up" : "working"} · ${a.lastDetail}`;
        if (!colorIdx.current.has(a.id)) {
          colorIdx.current.set(a.id, nextColorIdx.current);
          nextColorIdx.current += 1;
        }
        const accentColor = ACCENT_PALETTE[colorIdx.current.get(a.id)! % ACCENT_PALETTE.length];
        return {
          id: a.id,
          label: a.label,
          serverState: a.state,
          bubble,
          rawDetail: a.rawDetail,
          targetNodeId: a.targetZone,
          leaving: false,
          accentColor,
        };
      }),
    );
  }, [agents]);

  // DEFECT 1 fix: group every currently-displayed agent by its EFFECTIVE
  // destination (the entry gate while leaving, its zone otherwise) and hand
  // each one a stable ring slot -- see liveAgentWalk.ts#computeStandSlot.
  // Recomputed whenever the displayed set (or any agent's leaving flag)
  // changes; cheap at this roster's own 8-agent cap.
  const standSlots = useMemo(() => {
    const groups = new Map<string, string[]>();
    for (const d of displayed.values()) {
      const key = d.leaving ? "hub-center" : d.targetNodeId;
      const ids = groups.get(key) ?? [];
      ids.push(d.id);
      groups.set(key, ids);
    }
    const out = new Map<string, { offset: [number, number]; index: number }>();
    for (const ids of groups.values()) {
      for (const id of ids) {
        out.set(id, computeStandSlot(ids, id, STAND_RING_RADIUS));
      }
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [displayed]);

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
      {Array.from(displayed.values()).map((d) => {
        const slot = standSlots.get(d.id) ?? { offset: [0, 0] as [number, number], index: 0 };
        return (
          <LiveAgentAvatar
            key={d.id}
            liveAgentId={d.id}
            label={d.label}
            accentColor={d.accentColor}
            bubble={d.bubble}
            rawDetail={d.rawDetail}
            walkGraph={walkGraph}
            targetNodeId={d.targetNodeId}
            serverState={d.serverState}
            leaving={d.leaving}
            reducedMotion={reducedMotion}
            standOffset={slot.offset}
            standIndex={slot.index}
            onDespawned={() => handleDespawned(d.id)}
          />
        );
      })}
    </>
  );
}
