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
// existing AgentWalkKind: it spawns at the campus gate (CAMPUS-GATE pass,
// 2026-09-15 -- see liveAgentWalk.ts#ENTRY_NODE_ID's own header; this
// comment used to say "entry gate" while the actual entry node was
// hub-center, the middle of the building, not a gate at all -- now true),
// walks to whichever
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
import { mergeRefs, useLabelDeclutter } from "./useLabelDeclutter";
import { liveAgentIdentity } from "./liveAgentIdentity";
import { CHARACTER_SCALE, CHARACTER_TARGET_HEIGHT } from "./SetKit";
import type { LiveAgent } from "./types";
import type { LiveAgentState } from "@/lib/hq-agents";
import {
  applyFollowCap, applyLaneOffsets, computeBatchOrder, computeBatchStaggerDelays, computeMaxPathDurationS,
  computeSidestepPlan, computeWaitPoint, decideNextWalk, ENTRY_NODE_ID, findCarAhead, LEAVE_TIMEOUT_MARGIN_S,
  pathDistance, poseAlongPath, rampSidestepOffset, reconcileLiveAgentRoster, rightOf, shouldWriteLiveAgentDiag,
  stableSlotOffset, STAND_BUBBLE_Y_STEP, updateStableSlotAssignments, type WalkerSnapshot,
} from "./liveAgentWalk";

// AGENT-IDENTITY pass (2026-09-15): color used to cycle by ARRIVAL ORDER
// (an 8-hue palette indexed by a per-mount counter) -- deliberately replaced
// with liveAgentIdentity.ts's own TYPE-keyed tint so the look means "what
// kind of agent this is" (main session / general-purpose worker / Explore /
// other), not "which Nth agent joined" -- still deliberately NOT
// HEALTH_COLOR/PERSONA_STATUS_COLOR (palette.ts's own orthogonal-axes rule:
// a live agent's color must never get mistaken for a health/status glow or
// a persona's own color).

// AGENT-IDENTITY pass: hover tooltip visibility -- same hostname/`?kiosk=1`
// check app/hq/page.tsx's own `lanKiosk`/`kiosk` derive from, kept as a
// self-contained hook here rather than threading a `kiosk` prop through
// Scene.tsx/CanvasRoot.tsx/UltraCanvasRoot.tsx (out of this task's touch
// list, and the TV kiosk has no pointer anyway -- onMouseEnter below would
// simply never fire there; this is belt-and-suspenders so a tooltip box
// can never appear on a LAN glance screen even if some future input method
// did fire a hover event). Decided after mount (useEffect, not read at
// render time) so the server-rendered HTML never mismatches on hydration --
// same convention as page.tsx's own `lanKiosk` state.
function useIsKiosk(): boolean {
  const [kiosk, setKiosk] = useState(false);
  useEffect(() => {
    try {
      const host = window.location.hostname;
      const lan = !(host === "localhost" || host === "127.0.0.1" || host === "::1");
      const param = new URLSearchParams(window.location.search).get("kiosk") === "1";
      setKiosk(param || lan);
    } catch {
      // best-effort -- default false (tooltip enabled) if location is ever unavailable
    }
  }, []);
  return kiosk;
}

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
//
// CAMPUS-GATE pass (2026-09-15): this USED to be a bare literal 12 -- never
// re-derived when the entry node was hub-center (dead center of the
// building, every real walk-out short) and left stale as this pass moves
// the entry node out to campus-gate (every walk-out now longer, per-arm).
// Replaced below (see LiveAgentAvatar's own `leaveHardTimeoutS`) with a
// value computed from the REAL walk graph each avatar actually receives as
// a prop (liveAgentWalk.ts#computeMaxPathDurationS: longest real walk-graph
// distance from any node back to ENTRY_NODE_ID, at the real WALK_SPEED,
// plus LEAVE_TIMEOUT_MARGIN_S) -- see that function's own header for why it
// sweeps every graph node rather than a hand-picked zone list.

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

// FOLLOW DISTANCE / car-following (CONVOY-STACK v6, 2026-09-15) -- a
// module-level shared registry, same convention as `diagStore` above: every
// ACTIVELY WALKING (not waiting, not despawned) avatar publishes its own
// pose here each frame, and reads every OTHER avatar's LAST frame's entry
// to find a "car ahead" (liveAgentWalk.ts#findCarAhead) before committing
// this frame's own position. Reading last frame's values (rather than this
// frame's, which may or may not have been written yet depending on sibling
// mount/render order) is intentional -- it removes any same-frame
// write/read ordering dependency between sibling avatar components; one
// frame of staleness (~16ms) is imperceptible against the 0.8u gap this
// mechanism maintains. Scoped to WALKING avatars only (never a resting or
// waiting one) -- the reported bug (probe 20260915T101532Z) was walker-vs-
// walker on a shared corridor; a resting avatar's own stand-slot separation
// is CONVOY-STACK v5's job, not this one's.
const walkerFollowRegistry = new Map<string, WalkerSnapshot>();

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
  /** AGENT-IDENTITY pass: short human name (liveAgentIdentity.ts) shown in
   * the bubble header instead of the raw server `label` string. */
  displayName: string;
  accentColor: string;
  bubble: string;
  rawDetail: string;
  /** AGENT-IDENTITY pass: full, leak-sanitized task text for the hover
   * tooltip (lib/hq-agents.ts#sanitizeTaskText, server-computed). */
  taskDetail: string;
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
  /** CONVOY-STACK v2 (2026-09-15): this avatar's own stable-order stagger
   * delay (seconds) before its VERY FIRST walk (spawn) / its LEAVE walk may
   * begin moving -- see liveAgentWalk.ts#computeBatchStaggerDelays. Computed
   * once by the parent at the moment this avatar is created / flips to
   * leaving, and never recomputed afterward (a later sibling joining the
   * same batch must never retroactively change an already-decided delay). */
  spawnDelayS: number;
  leaveDelayS: number;
  /** CONVOY-STACK v3 (2026-09-15): this avatar's own 0-based order within
   * its spawn/leave batch (liveAgentWalk.ts#computeBatchOrder) -- used only
   * to derive its WAIT POINT (computeWaitPoint), independently of
   * spawnDelayS/leaveDelayS's own timing role. Kept as a separate prop
   * rather than re-derived from the delay (delay / STAGGER_DELAY_S) so the
   * two can never drift if either constant changes. */
  spawnIndex: number;
  leaveIndex: number;
  onDespawned: () => void;
}

function nodePosition(walkGraph: WalkGraph, id: string, fallback: [number, number, number]): [number, number, number] {
  return (walkGraph.nodes.get(id)?.position as [number, number, number] | undefined) ?? fallback;
}

function LiveAgentAvatar({
  liveAgentId, label, displayName, accentColor, bubble, rawDetail, taskDetail, walkGraph, targetNodeId, serverState, leaving, reducedMotion,
  standOffset, standIndex, spawnDelayS, leaveDelayS, spawnIndex, leaveIndex, onDespawned,
}: AvatarProps) {
  const group = useRef<THREE.Group>(null);
  const bubbleWrapRef = useRef<HTMLDivElement>(null);
  const bubbleDelta = useMemo(() => new THREE.Vector3(), []);
  // AGENT-IDENTITY pass: hover -> full-task tooltip. A plain useState (not
  // a ref) -- hover start/stop are discrete pointer events and the tooltip
  // itself must re-render when this flips, same "state for discrete
  // moments" convention Scene.tsx's own hoveredTarget comment documents.
  const [hovered, setHovered] = useState(false);
  const isKiosk = useIsKiosk();
  const entryPos = useMemo<[number, number, number]>(
    () => nodePosition(walkGraph, ENTRY_NODE_ID, [0, 0, 0]),
    [walkGraph],
  );
  // CAMPUS-GATE pass (2026-09-15): derived from the real walkGraph prop --
  // see this file's own leaveHardTimeoutS comment above for why a bare
  // literal is no longer correct once the entry node is campus-gate instead
  // of hub-center. CONVOY-STACK v2 (same day): `+ leaveDelayS` -- a
  // staggered leave doesn't start MOVING until leaveDelayS has elapsed (see
  // `pendingStartDelayS` below), but `leaveStartedAtT` (the hard-backstop's
  // own clock) starts counting from the moment `leaving` flips true, not
  // from when the walk visually begins. Without this term the backstop
  // could fire before a legitimately-staggered walk had even started
  // moving -- additive only, per the coordinator's own "add it to the
  // timeout, never shrink" requirement.
  const leaveHardTimeoutS = useMemo(
    () => computeMaxPathDurationS(walkGraph, ENTRY_NODE_ID, WALK_SPEED) + LEAVE_TIMEOUT_MARGIN_S + leaveDelayS,
    [walkGraph, leaveDelayS],
  );

  const currentNode = useRef(ENTRY_NODE_ID);
  const path = useRef<[number, number, number][]>([entryPos, entryPos]);
  const walkDest = useRef(ENTRY_NODE_ID);
  const walkDespawnsOnArrival = useRef(false);
  const needsWalkStart = useRef(true); // first frame: begin the spawn->zone walk
  const walkStartT = useRef(0);
  const phase = useRef<"walking" | "working">("walking");
  // CONVOY-STACK v2 (2026-09-15): the delay to apply the NEXT time
  // `needsWalkStart` fires -- seeded with this avatar's own spawn-batch
  // delay (its very first walk), overwritten with `leaveDelayS` right
  // before the leave walk kicks off (see the decision effect below), and
  // zeroed the instant it is consumed so every ORDINARY mid-life retarget
  // (no batch to stagger against) starts moving immediately, same as
  // before this pass.
  const pendingStartDelayS = useRef(spawnDelayS);
  // CONVOY-STACK v3: the batch-order INDEX to feed computeWaitPoint the NEXT
  // time a wait point is computed -- mirrors pendingStartDelayS's own
  // seed/overwrite pattern (spawnIndex at mount, leaveIndex right before the
  // leave walk kicks off), but is never zeroed after use: unlike the delay
  // (which must never bleed into a later undelayed walk), re-reading a stale
  // index for an ordinary retarget is harmless -- that walk's own
  // pendingStartDelayS is 0, so `elapsed` is never negative and
  // `waitPoint.current` is simply never rendered.
  const pendingWaitIndex = useRef(spawnIndex);
  // TELEPORT-ON-LEAVE fix (2026-09-15, probe 20260915T094248Z): whether the
  // NEXT wait (elapsed < 0, see useFrame below) should render at a
  // computeWaitPoint-derived gate lane (true, spawn only) or simply HOLD the
  // avatar's actual current pose (false, leave). Seeded true for this
  // avatar's very first walk (a brand-new avatar is being CREATED at the
  // entry node right now -- there is no prior visible pose to jump away
  // from, so nudging it onto a gate lane is invisible and correctly
  // separates same-batch spawns). Set false right before the leave walk
  // kicks off (see the decision effect below): a leaving avatar is already
  // RESTING at its own distinct stand-slot position (CONVOY-STACK v3's own
  // continuous per-frame correction), so relocating it onto a gate-shaped
  // lane before it even starts walking is a real, visible teleport -- see
  // this file's own CONVOY-STACK v4 header below the leaving branch for the
  // full root-cause writeup.
  const pendingWaitUsesGateLane = useRef(true);
  // The point to render this avatar AT while it is still waiting out its
  // own stagger delay (elapsed < 0, see useFrame below) -- its own batch-
  // order-derived lane/row offset off the true origin (liveAgentWalk.ts
  // #computeWaitPoint), so same-batch avatars waiting for their turn don't
  // stack exactly on the shared spawn/leave node either. Recomputed every
  // time a new walk is kicked off; unused while `elapsed >= 0`.
  const waitPoint = useRef<[number, number, number]>(entryPos);
  // Set true/false each frame by the walking branch below, purely so the
  // diag-state classification at the bottom of useFrame can report
  // "spawning" (still waiting for its stagger slot) instead of "walking"
  // (visibly progressing) -- cosmetic/diagnostic only, does not affect any
  // position math.
  const waitingForSlot = useRef(false);
  // FOLLOW DISTANCE (v6): this avatar's own cumulative distance-traveled AS
  // ACTUALLY APPLIED (i.e. post-follow-cap) for its CURRENT walk -- the
  // "never reverse" floor liveAgentWalk.ts#applyFollowCap needs every
  // frame. Reset to 0 whenever a new walk is kicked off (see the decision
  // effect below); never touched while resting/waiting.
  const appliedDistanceRef = useRef(0);
  // LEAVE-TIMEOUT EXTENSION guardrail (v6): cumulative extra seconds to add
  // on top of leaveHardTimeoutS -- incremented by this frame's own delta
  // every frame this avatar's forward advance was actually reduced by
  // following (see useFrame below), so a leaving avatar that's slowed
  // behind another leaver is never despawned mid-corridor just because
  // following made its walk take longer than the un-crowded estimate.
  const leaveTimeoutExtensionS = useRef(0);
  // KEEP-RIGHT PASSING (v8): this avatar's own current lateral offset
  // (toward its own right, perpendicular to its CURRENT heading), ramped
  // every frame toward whatever liveAgentWalk.ts#computeSidestepPlan says
  // this frame (0 when no head-on conflict, SIDESTEP_TARGET_U when one is
  // detected) via rampSidestepOffset's own bounded rate -- never reset
  // between walks the way appliedDistanceRef is, since drifting smoothly
  // back to 0 (rather than snapping) is exactly the point when a walk ends
  // mid-sidestep.
  const sidestepOffsetRef = useRef(0);
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

  // FOLLOW DISTANCE (v6): defensive unmount cleanup -- the normal despawn
  // path already frees this id via fireDespawn's own registry delete, but
  // an unmount that bypasses that (a dev-mode remount, a future code path)
  // must never leave a stale, frozen-in-place entry for another avatar to
  // read as a permanent "car ahead".
  useEffect(() => {
    return () => {
      walkerFollowRegistry.delete(liveAgentId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function fireDespawn(): void {
    if (despawned.current) return;
    despawned.current = true;
    // FOLLOW DISTANCE (v6): a single choke point for leaving the walker
    // registry, regardless of WHICH path triggered despawn (normal
    // arrival, the leave hard-timeout backstop, or reduced-motion's
    // immediate settle) -- a stale entry here would otherwise freeze in
    // place and get read as a permanent "car ahead" by whoever's actually
    // still walking.
    walkerFollowRegistry.delete(liveAgentId);
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

  /** DESPAWN-SCATTER FIX (2026-09-15, probe 20260915T081521Z/20260915T082114Z):
   * a despawning avatar's final position must be the RAW gate node, never
   * `standPointFor`'s own stand-slot ring nudge. Root cause: LiveAgents.tsx's
   * `standSlots` memo groups every currently-leaving agent under one shared
   * key (`ENTRY_NODE_ID`, see this file's own `standSlots` comment below) so
   * `computeStandSlot` spreads them around a `STAND_RING_RADIUS` (0.9u) ring
   * centered on the gate -- correct for agents genuinely RESTING/working in a
   * shared zone (that's this offset's whole purpose), but wrong for a
   * despawn: the avatar is about to vanish, not stand there, so scattering it
   * around the gate instead of AT it is pure bug, not a feature. This
   * explains the probe's observed last-diag positions before disappearing
   * ([21.30,0] 0.30u short, [20.655,0] 0.94u short, [22.393,0] 0.79u past --
   * every one of them within/around the exact 0.9u ring radius, in whatever
   * direction that avatar's own ring angle happened to point that poll,
   * including PAST the gate when the angle pointed outward). Using the bare
   * node position for any despawning destination collapses every
   * simultaneously-leaving avatar onto the same exact gate point right
   * before they vanish, which is fine -- they are about to disappear, never
   * stand there, so there is nothing left to separate. */
  function destinationPointFor(nodeId: string, despawn: boolean): [number, number, number] {
    return despawn ? nodePosition(walkGraph, nodeId, entryPos) : standPointFor(nodeId);
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
      group.current?.position.set(...destinationPointFor(dest, leaving));
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
      // TELEPORT FIX (2026-09-15): `currentNode.current` only advances on
      // arrival, so while `phase.current === "walking"` it still names the
      // ORIGIN of the in-flight walk, not where the avatar physically is.
      // Passing that through tells decideNextWalk it must never take the
      // instant-settle shortcut for a still-in-flight avatar -- see
      // liveAgentWalk.ts#WalkDecisionInput.isWalking for the tick-by-tick
      // probe evidence.
      isWalking: phase.current === "walking",
    });
    if (decision.action === "none") return;
    if (leaving) {
      leaveTriggered.current = true;
      if (leaveStartedAtT.current === null) leaveStartedAtT.current = performance.now() / 1000;
      // CONVOY-STACK v2/v3: this avatar's leave walk (if one is about to be
      // kicked off below) uses the LEAVE batch's own stagger delay and
      // batch-order index, not whatever spawn delay/index may already have
      // been consumed by now.
      pendingStartDelayS.current = leaveDelayS;
      pendingWaitIndex.current = leaveIndex;
      // TELEPORT-ON-LEAVE fix (CONVOY-STACK v4): a leave wait must HOLD this
      // avatar's actual current pose, never a gate-shaped lane -- see this
      // avatar's own `pendingWaitUsesGateLane` declaration above.
      pendingWaitUsesGateLane.current = false;
    } else {
      seenTarget.current = targetNodeId;
    }

    if (decision.action === "settle") {
      currentNode.current = decision.dest;
      group.current?.position.set(...destinationPointFor(decision.dest, decision.despawn));
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
    // TELEPORT FIX: the FIRST waypoint used to always be
    // `nodePosition(currentNode.current)` -- correct when starting a walk
    // from rest, but WRONG when this walk supersedes one already in flight
    // (retargeting mid-walk, or a target that flapped back to the walk's
    // own origin before arrival): `currentNode.current` still names that
    // stale origin node, not wherever the avatar has actually walked to
    // since. Starting the new path from the avatar's real, live position
    // (its current rendered group position) instead means the walk always
    // continues smoothly from wherever it visually is, never snaps across
    // the map. Only the FINAL waypoint gets the stand-offset nudge -- every
    // corridor/doorway waypoint in between stays exactly on the real
    // walk-graph node so the route itself is unaffected (DEFECT 1's own fix
    // target).
    const livePos: [number, number, number] = group.current
      ? [group.current.position.x, group.current.position.y, group.current.position.z]
      : nodePosition(walkGraph, currentNode.current, entryPos);
    const finalPoint = destinationPointFor(decision.dest, decision.despawn);
    // CONVOY-STACK FIX (2026-09-15): nudge every INTERIOR hallway waypoint
    // sideways by this avatar's own deterministic lane offset, so two agents
    // sharing a corridor leg (the common case: every walk leaves campus-gate
    // through the same first hallway) walk in separate lanes instead of
    // occupying the exact same XZ point for the whole shared segment -- see
    // liveAgentWalk.ts#applyLaneOffsets for the full root-cause writeup. The
    // first waypoint (this avatar's real live position) and the last
    // (finalPoint, already correctly nudged or not by destinationPointFor
    // above) are left untouched by design.
    const rawWp = applyLaneOffsets(
      rawPath.length > 0 ? [livePos, ...rawPath.slice(1, -1), finalPoint] : [livePos, finalPoint],
      liveAgentId,
    );
    // CONVOY-STACK v2/v4/v5: while this walk's own start delay
    // (pendingStartDelayS, seeded above) hasn't elapsed yet, useFrame
    // renders this avatar at `waitPoint` instead of progressing along `wp`.
    //
    // TELEPORT-ON-LEAVE fix (v4, probe 20260915T094248Z): a SPAWN wait uses
    // a computeWaitPoint gate lane (correctly separates same-batch spawns,
    // and is invisible -- the avatar is being CREATED right now, so there is
    // no prior on-screen pose to jump away from). A LEAVE wait must instead
    // HOLD this avatar's own real `livePos` exactly -- v3 applied the SAME
    // gate-lane math to a leaving avatar's CURRENT zone position, instantly
    // relocating a RESTING avatar (already on its own distinct stand slot --
    // no additional separation needed) the instant `leaving` flipped true.
    //
    // TELEPORT-ON-SPAWN fix (v5, probe 20260915T095436Z, coordinator's own
    // pose_jump audit): a SPAWN wait's first rendered pose IS `waitPoint`
    // (the gate lane), but `rawWp[0]` above is always `livePos` (the raw,
    // un-offset origin) -- so the walk used to resume from a DIFFERENT point
    // than the one the avatar had actually been sitting at for its whole
    // wait, producing a snap the instant the delay elapsed (reported: 1.5u
    // at a spawning->walking transition). Only a walk that actually HAS a
    // delay (`pendingStartDelayS.current > 0`) is affected -- an ordinary,
    // undelayed retarget must keep starting from the avatar's true
    // `livePos`, never a stale gate-lane value left over from an earlier
    // spawn/leave. Fix: when this walk DOES have a delay, replace the
    // path's own first waypoint with `waitPoint` itself, so the two can
    // never disagree -- the walk always resumes from EXACTLY where the
    // avatar was rendered a moment before.
    const hasDelay = pendingStartDelayS.current > 0;
    waitPoint.current = hasDelay
      ? (pendingWaitUsesGateLane.current
          ? computeWaitPoint(livePos, rawWp[1] ?? finalPoint, pendingWaitIndex.current)
          : livePos)
      : livePos;
    const wp: [number, number, number][] = hasDelay ? [waitPoint.current, ...rawWp.slice(1)] : rawWp;
    path.current = wp;
    walkDest.current = decision.dest;
    walkDespawnsOnArrival.current = decision.despawn;
    // FOLLOW DISTANCE (v6): a brand-new walk starts its own distance
    // accounting fresh -- never carries over a "never reverse" floor from
    // whatever walk (if any) preceded it.
    appliedDistanceRef.current = 0;
    needsWalkStart.current = true;
    phase.current = "walking";
    setAnimState(WALK_ANIM);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leaving, targetNodeId, reducedMotion, walkGraph]);

  // STAND-SLOT COLLISION fix (2026-09-15, coordinator probe 20260915T070024Z,
  // recurred at probe 20260915T085943Z after the first "STACK FIX" attempt
  // below -- kept verbatim, struck through in spirit, as the documented
  // reason this pass replaces it rather than patching it again):
  //
  // ORIGINAL "STACK FIX" (2026-09-14/15): an effect that re-applied
  // standPointFor(currentNode.current) whenever THIS avatar's own
  // `standOffset` prop changed value relative to its immediately-preceding
  // render (`useEffect(..., [standOffset[0], standOffset[1]])`).
  //
  // WHY IT RECURRED (verified root cause, this pass): this is an
  // EDGE-TRIGGERED correction -- it only runs when React's own dependency
  // diff sees THIS avatar's offset change between two CONSECUTIVE renders of
  // THIS avatar. Two gaps that leaves open: (1) the walk-ARRIVAL branch
  // above (`progress >= 1`) never calls standPointFor at all -- an arriving
  // avatar simply stays wherever `poseAlongPath` left it, i.e. the FINAL
  // waypoint that was baked into `path.current` back at walk-DECISION time
  // (LiveAgents.tsx's own decision effect, `finalPoint = destinationPointFor
  // (decision.dest, decision.despawn)`); if the group composition changes
  // again during the walk -- now a much wider window than before, since the
  // CONVOY-STACK v2 stagger can add up to (roster cap - 1) * STAGGER_DELAY_S
  // of pure WAITING before the avatar even starts moving, on top of the
  // travel time itself -- the avatar settles at a stale offset and nothing
  // re-corrects it unless its OWN prop changes AGAIN afterward. (2) an
  // edge-triggered mechanism has no notion of "I am currently wrong" -- only
  // "my prop just changed" -- so any sequence of group-membership churn that
  // leaves two avatars' actually-applied positions both resolved from a
  // groupSize-1 view (each independently believing itself alone in the
  // group at the moment its own position was last set, whether via the
  // uncorrected arrival above or a reslot that fired against a
  // since-superseded value) reproduces the exact collision this effect was
  // meant to prevent -- which is exactly what recurred (a1b95546df7c4703f
  // arrived long after a7195e62a4dda3d05 had already settled, and the two
  // sat at the IDENTICAL point for ~60s).
  //
  // FIX: stop relying on edge-triggered correction. `useFrame` below now
  // unconditionally re-applies `standPointFor(currentNode.current)` to every
  // RESTING (phase.current === "working", not yet despawned) avatar, EVERY
  // FRAME, reading `standOffsetRef.current` live. This is provably correct
  // regardless of the exact React-scheduling mechanism that let the old
  // effect miss an update: a per-frame read of the CURRENT offset can never
  // be "stale" by construction -- there is no prior value to diff against,
  // only "what is the right position right now". A despawning avatar is
  // excluded (`!despawned.current`) so this can never fight the
  // DESPAWN-SCATTER fix's own raw-node destination (destinationPointFor's
  // `despawn: true` branch, which intentionally has NO stand-slot ring
  // offset at all -- see that function's own doc above).

  useFrame((state, delta) => {
    const g = group.current;
    if (!g) return;
    const t = state.clock.elapsedTime;
    if (needsWalkStart.current) {
      needsWalkStart.current = false;
      // CONVOY-STACK v2: push the walk's own start time into the future by
      // this walk's queued delay (spawn-batch delay for the very first
      // walk, leave-batch delay for the leave walk, 0 for every ordinary
      // mid-life retarget) -- consumed exactly once, then zeroed, so it can
      // never bleed into a LATER, undelayed walk decision.
      walkStartT.current = t + pendingStartDelayS.current;
      pendingStartDelayS.current = 0;
    }
    if (phase.current === "walking") {
      const elapsed = t - walkStartT.current;
      if (elapsed < 0) {
        // CONVOY-STACK v2: still waiting for this avatar's own stagger
        // slot -- render it standing at its lane-offset wait point (see
        // liveAgentWalk.ts#computeWaitPoint) rather than progressing along
        // `path.current` (which would clamp to the unoffset origin,
        // stacking every same-batch sibling that is ALSO still waiting).
        g.position.set(waitPoint.current[0], waitPoint.current[1], waitPoint.current[2]);
        waitingForSlot.current = true;
        // FOLLOW DISTANCE (v6): a waiting avatar isn't actively walking --
        // out of scope for this pass (see walkerFollowRegistry's own
        // header) -- so make sure a STALE entry from an earlier walk never
        // lingers and gets read as "a car ahead" by someone else.
        walkerFollowRegistry.delete(liveAgentId);
      } else {
        waitingForSlot.current = false;
        // MID-WALK SLOT DRIFT fix (v5 addendum, probe 20260915T095436Z's
        // own pose_jump audit): even with STABLE slot assignment (this
        // avatar's own index no longer changes while it stays assigned to
        // the same zone), a walk's baked-in FINAL waypoint was still only
        // ever computed ONCE, at decision time -- if this avatar's own
        // assignment somehow drifts before arrival (a target-zone flap that
        // drops and re-adds it, or any other future edge case), the old
        // behavior let poseAlongPath arrive at a now-STALE point and then
        // relied on the continuous stand-slot correction below to snap it
        // to the CORRECT one the very next frame (exactly the "arrival,
        // walking->working" jumps the probe caught, 1.07-1.10u). Instead,
        // every frame of an active (non-despawning) walk smoothly retargets
        // the path's own FINAL waypoint to whatever standPointFor currently
        // says, so this can only ever shift WHERE the remaining walk
        // interpolates TOWARD, never where the avatar is rendered THIS
        // frame -- eliminating the snap at its root rather than patching
        // the symptom on arrival. A despawning walk is exempt (its raw-node
        // destination never carries a stand offset at all -- see
        // destinationPointFor's own `despawn: true` branch above).
        //
        // DISTANCE-BASED PROGRESS (v5 addendum, same pass): swapping the
        // endpoint changes the path's OWN total length -- a progress
        // fraction computed against a duration baked from the ORIGINAL
        // total would then feed poseAlongPath a fraction of a DIFFERENT
        // total than the one it was measured against, producing exactly
        // the kind of discontinuity this fix exists to remove. Deriving
        // `progress` fresh, every frame, from actual DISTANCE TRAVELED
        // divided by the CURRENT path's own live length keeps the avatar's
        // physical walking speed constant and continuous regardless of when
        // or how much the endpoint moves. `MIN_WALK_S` still floors the
        // effective total so a near-zero-length path doesn't "arrive"
        // instantly within a single frame.
        //
        // INCREMENTAL distance accumulation (v6, found while building the
        // follow-distance fix's own 3-deep-chain test): v5 computed this
        // distance as `elapsed * WALK_SPEED` -- an ABSOLUTE value that
        // grows with wall-clock time regardless of what actually happened
        // in between. That is exactly wrong once an avatar can be held
        // back by CONVOY-STACK v6's own follow-cap below: an avatar slowed
        // behind a car ahead accumulates "debt" between its actual
        // (capped) position and where the absolute formula says it should
        // be: the INSTANT the car ahead pulls away and the cap releases,
        // the absolute formula would try to pay off that whole debt in one
        // frame -- a real snap, the same class of bug this whole pass
        // exists to remove. Accumulating INCREMENTALLY instead --
        // `appliedDistanceRef.current + WALK_SPEED * delta`, at most one
        // frame's worth of travel from wherever this avatar ACTUALLY is --
        // makes a stretch of following simply cost that much real time,
        // with no debt to ever snap-repay. `elapsed` is still used above,
        // unchanged, to gate the stagger WAIT itself (elapsed < 0).
        if (!walkDespawnsOnArrival.current) {
          const liveFinal = standPointFor(walkDest.current);
          const wpNow = path.current;
          const lastIdx = wpNow.length - 1;
          const cur = wpNow[lastIdx];
          if (lastIdx >= 0 && (cur[0] !== liveFinal[0] || cur[2] !== liveFinal[2])) {
            path.current = [...wpNow.slice(0, lastIdx), liveFinal];
          }
        }
        const distanceTraveled = appliedDistanceRef.current + WALK_SPEED * delta;
        const liveTotal = Math.max(MIN_WALK_S * WALK_SPEED, pathDistance(path.current));

        // FOLLOW DISTANCE / car-following (CONVOY-STACK v6, probe
        // 20260915T101532Z): before committing to this frame's advance,
        // check whether another currently-walking avatar is a "car ahead"
        // on the same shared corridor (liveAgentWalk.ts#findCarAhead --
        // same destination, near-parallel heading, small lateral offset)
        // and, if the gap is under FOLLOW_GAP_U, cap this frame's forward
        // advance so the gap never drops below it.
        //
        // SELF POSITION SOURCE: deliberately `g.position`/`g.rotation.y` AS
        // THEY STAND right now -- i.e. LAST FRAME's actual rendered pose,
        // not a fresh "candidate" computed from this frame's UNCAPPED
        // distance. Using the uncapped candidate here would compare THIS
        // avatar's fastest-possible, not-yet-applied position against
        // every OTHER avatar's own one-frame-stale (already-applied)
        // registry entry -- an asymmetric comparison that can let a
        // fast-closing avatar's candidate momentarily read as "ahead" of a
        // slower one it hasn't actually reached yet, disengaging the cap
        // at exactly the wrong moment (a real failure mode found while
        // building this fix's own 3-deep-chain test). Reading the avatar's
        // OWN last-rendered pose keeps both sides of every comparison on
        // the same one-frame-stale footing.
        const selfSnapshot: WalkerSnapshot = {
          id: liveAgentId,
          position: [g.position.x, g.position.z],
          heading: [Math.sin(g.rotation.y), Math.cos(g.rotation.y)],
          destKey: walkDest.current,
        };
        const others = Array.from(walkerFollowRegistry.values());
        const carAhead = findCarAhead(selfSnapshot, others);
        let appliedDistance = applyFollowCap(distanceTraveled, appliedDistanceRef.current, carAhead);
        // KEEP-RIGHT PASSING (CONVOY-STACK v8, probe 20260915T114713Z):
        // findCarAhead/applyFollowCap above only ever engage for SAME-
        // direction traffic (FOLLOW_HEADING_COS_MIN) -- correctly excluding
        // head-on pairs so they can never deadlock each other, but that
        // also means nothing previously made two opposite-direction
        // walkers avoid each other at all (observed: two walkers in the
        // same lane passing straight through one another, 0.07u apart).
        // liveAgentWalk.ts#computeSidestepPlan decides, independently: (a)
        // a gradual lateral offset toward THIS avatar's own right when a
        // head-on conflict is detected on a TRUSTED corridor (`walkable`,
        // this avatar's own already-computed state -- see that function's
        // own header for why a real per-edge width figure isn't available
        // here), or (b) in the untrusted/narrow-corridor fallback, the
        // lexicographically LOWER id pausing its forward advance instead of
        // risking a sidestep off walkable floor.
        const sidestepPlan = computeSidestepPlan(selfSnapshot, others, walkable);
        if (sidestepPlan.pauseForOncoming) {
          appliedDistance = appliedDistanceRef.current;
        }
        appliedDistanceRef.current = appliedDistance;
        // LEAVE-TIMEOUT EXTENSION guardrail: this frame's advance fell
        // short of what an un-crowded walk would have covered -- extend
        // the hard-timeout backstop by exactly the time this frame cost,
        // so a leaving avatar slowed behind another leaver (following OR
        // pausing for an oncoming pass) is never despawned mid-corridor
        // purely because either mechanism made its walk take longer than
        // the solo estimate.
        if (leavingRef.current && appliedDistance < distanceTraveled - 1e-6) {
          leaveTimeoutExtensionS.current += delta;
        }

        const progress = Math.min(1, appliedDistance / liveTotal);
        const { position, facing } = poseAlongPath(path.current, progress);
        // KEEP-RIGHT PASSING, continued: ramp this avatar's own lateral
        // offset toward the plan's target (0 when clear, SIDESTEP_TARGET_U
        // while passing) at a bounded rate -- never a snap, in either
        // direction. Forced back toward 0 in the final approach to THIS
        // avatar's own destination (progress >= 0.95) regardless of any
        // still-detected oncoming walker: the stand-slot correction that
        // takes over on arrival (CONVOY-STACK v5) has no notion of a
        // sidestep offset at all, so arriving with a non-zero one would
        // itself be a snap the instant phase flips to "working". A few
        // tenths of a unit of remaining walk is comfortably enough time
        // (SIDESTEP_TARGET_U / SIDESTEP_RATE_U_PER_S ~= 0.67s) for the ramp
        // to settle back to 0 first.
        const sidestepTarget = progress >= 0.95 ? 0 : sidestepPlan.offsetTargetU;
        sidestepOffsetRef.current = rampSidestepOffset(sidestepOffsetRef.current, sidestepTarget, undefined, delta);
        const right = rightOf([Math.sin(facing), Math.cos(facing)]);
        const renderedX = position[0] + right[0] * sidestepOffsetRef.current;
        const renderedZ = position[2] + right[1] * sidestepOffsetRef.current;
        g.position.set(renderedX, position[1], renderedZ);
        g.rotation.y = facing;
        // Publish THIS frame's own final (possibly capped, possibly
        // sidestepped) pose for other avatars' NEXT frame -- see
        // walkerFollowRegistry's own header for why this is deliberately
        // one-frame-stale from a reader's perspective.
        walkerFollowRegistry.set(liveAgentId, {
          id: liveAgentId,
          position: [renderedX, renderedZ],
          heading: [Math.sin(facing), Math.cos(facing)],
          destKey: walkDest.current,
        });
        if (progress >= 1) {
          currentNode.current = walkDest.current;
          walkerFollowRegistry.delete(liveAgentId); // no longer actively walking
          if (walkDespawnsOnArrival.current) {
            fireDespawn();
          } else {
            phase.current = "working";
            setAnimState(WORK_DWELL_ANIM);
          }
        }
      }
    }

    // STAND-SLOT COLLISION fix (see this file's own header above the reslot
    // effect this replaces): a RESTING avatar's position is re-derived from
    // its LIVE stand-slot offset every single frame, not just when an effect
    // happens to see its own prop change. `despawned.current` is checked so
    // this can never re-apply a ring offset to an avatar whose despawn
    // destination is deliberately the RAW node (no ring nudge) -- see
    // destinationPointFor's own `despawn: true` branch above.
    //
    // LEAVE-FLIP TELEPORT fix (CONVOY-STACK v9, 2026-09-15, probe
    // 20260915T120533Z): `!leavingRef.current` -- ROOT CAUSE, verified:
    // `leavingRef.current = leaving;` (this file, render body, above) is
    // updated the INSTANT this avatar's `leaving` prop flips true --
    // strictly earlier than the "decision effect" (the `useEffect` with
    // `[leaving, targetNodeId, ...]` deps, below) actually RUNS for that
    // same render, since React effects fire after commit while a `useFrame`
    // tick can land in between. Before this fix, THIS block had no
    // `leaving` check at all: on that in-between frame, `phase.current` was
    // still "working" (the decision effect hadn't yet flipped it to
    // "walking"), so this correction still fired -- reading
    // `currentNode.current` (this avatar's OWN ref, still the OLD
    // pre-leaving zone node; only updated on walk ARRIVAL, untouched by a
    // leaving flip) together with `standOffsetRef.current` (fed from the
    // `standOffset` PROP, which the PARENT had ALREADY recomputed for this
    // avatar's NEW leaving-group membership under ENTRY_NODE_ID, since
    // props update before this avatar's own effects run). The result: OLD
    // zone's node position + a stand-slot offset computed for a DIFFERENT
    // group -- a real position, just the WRONG one, sized like any other
    // valid slot offset (probe's own observed 0.73-1.34u jumps, with
    // a4a43059 landing EXACTLY on a1495f14's own prior slot -- both groups'
    // sorted-index assignment happened to collide on the same index,
    // `stableSlotOffset` returning the identical [x,z] offset for both).
    // Skipping this correction the instant `leaving` flips also fixes the
    // v4 hold-livePos mechanism "one layer up" for free: the decision
    // effect's own `livePos = group.current.position` read now always sees
    // the avatar's TRUE last-good resting pose, never a transiently
    // corrupted one, because nothing overwrote `g.position` in between.
    if (phase.current === "working" && !despawned.current && !leavingRef.current) {
      const p = standPointFor(currentNode.current);
      g.position.set(p[0], p[1], p[2]);
    }

    // Hard backstop (see this file's own leaveHardTimeoutS comment above):
    // if this avatar has been leaving for too long without despawning -- any
    // mechanism, known or not -- force it out rather than stranding it in
    // the world. LEAVE-TIMEOUT EXTENSION guardrail (v6): `+
    // leaveTimeoutExtensionS.current` -- additive only, accumulated above
    // whenever following actually slowed this avatar's own advance -- so a
    // leaver that's legitimately still progressing, just more slowly than
    // the solo estimate assumed, is never despawned mid-corridor.
    if (leavingRef.current && !despawned.current && leaveStartedAtT.current !== null) {
      if (performance.now() / 1000 - leaveStartedAtT.current > leaveHardTimeoutS + leaveTimeoutExtensionS.current) {
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

    // DIAG-GHOST FIX (2026-09-15, coordinator probe 20260915T072901Z, RTX
    // 5080 hardware run): fireDespawn() above (arrival check or the hard
    // backstop) may have fired THIS SAME frame, synchronously deleting this
    // avatar's diagStore entry via onDespawned -- but React's actual unmount
    // (which would stop this useFrame from running again) only lands on a
    // later render. Without this guard, the write below ran unconditionally
    // every frame in between and resurrected the just-deleted entry; the
    // LAST such write, from the final frame before unmount, was never
    // cleaned up again, leaving a permanent ghost row in
    // window.__hqLiveAgents forever (see liveAgentWalk.ts#shouldWriteLiveAgentDiag
    // for the full root-cause writeup + probe evidence). Once despawned,
    // this avatar must never publish another diag snapshot.
    if (!shouldWriteLiveAgentDiag(despawned.current)) return;

    // CONVOY-STACK v2: `waitingForSlot` reports "spawning" (standing,
    // stagger-delayed) instead of "walking" (visibly progressing) while
    // this avatar's own start delay hasn't elapsed yet -- diagnostic only.
    const diagState: LiveAgentDiagEntry["state"] =
      leavingRef.current
        ? "leaving"
        : phase.current === "walking" && !waitingForSlot.current
          ? "walking"
          : serverState === "spawning" || waitingForSlot.current
            ? "spawning"
            : "working";
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
  const { wrapperRef: declutterRef, measureRef: declutterMeasureRef } = useLabelDeclutter(`live:${liveAgentId}`, PRIORITY.LIVE_AGENT, declutterWorldPos);

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
        <div
          ref={mergeRefs(bubbleWrapRef, declutterMeasureRef)}
          style={{ position: "relative", transformOrigin: "50% 100%", pointerEvents: isKiosk ? "none" : "auto" }}
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
        >
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
              <b style={{ fontWeight: 800 }}>{displayName}</b>
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
          {/* AGENT-IDENTITY pass: hover tooltip -- the FULL, un-truncated
              (vs. bubbleTrunc's 44-char cut) sanitized task text
              (taskDetail, server-computed by lib/hq-agents.ts#sanitizeTaskText).
              Kiosk-hidden (pointerEvents "none" above means onMouseEnter can
              never fire there anyway; `hovered` also just never becomes true
              on a kiosk with no pointer -- this `!isKiosk` check is
              belt-and-suspenders, matching this file's existing "no silent
              stuck state" convention). `position: absolute` and therefore
              taken out of flow -- appearing/disappearing on hover can never
              change declutterMeasureRef's own getBoundingClientRect() (an
              absolutely-positioned child never contributes to its static-
              positioned parent's layout box), so a hover never perturbs the
              declutter collision box the manager already computed for the
              bubble. pointerEvents "none" so the tooltip itself can never
              steal the mouseleave that should close it. */}
          {hovered && !isKiosk && taskDetail ? (
            <div
              style={{
                position: "absolute", left: "50%", bottom: "calc(100% + 10px)",
                transform: "translateX(-50%)", pointerEvents: "none",
                maxWidth: 340, width: "max-content",
                fontFamily: "system-ui, sans-serif", color: "#dff3ff", fontSize: 20,
                background: "rgba(3,4,10,0.92)", border: `1px solid ${accentColor}`,
                borderRadius: 6, padding: "6px 10px",
                whiteSpace: "normal", wordBreak: "break-word", lineHeight: 1.35,
              }}
            >
              {taskDetail}
            </div>
          ) : null}
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
  /** AGENT-IDENTITY pass: short human name for the bubble header (see
   * liveAgentIdentity.ts) -- replaces the raw server `label` string so the
   * header and any future name label can never show two different things
   * for the same agent. */
  displayName: string;
  /** AGENT-IDENTITY pass: full, leak-sanitized task text for the hover
   * tooltip (lib/hq-agents.ts#sanitizeTaskText, computed server-side --
   * see that field's own doc comment for why). */
  taskDetail: string;
  /** CONVOY-STACK v2 (2026-09-15): this id's own stable-order stagger delay
   * (seconds) -- assigned ONCE, the moment this id is first added
   * (spawnDelayS) or first flips to leaving (leaveDelayS), and preserved
   * unchanged on every later poll (see the roster-reconcile effect below).
   * A later sibling joining the same batch must never retroactively change
   * an id's already-decided delay. */
  spawnDelayS: number;
  leaveDelayS: number;
  /** CONVOY-STACK v3 (2026-09-15): the same batch, same "assign once" rule
   * as spawnDelayS/leaveDelayS above, but the raw 0-based batch ORDER
   * (liveAgentWalk.ts#computeBatchOrder) rather than a seconds value -- used
   * only to derive this avatar's WAIT POINT (computeWaitPoint), never its
   * timing. */
  spawnIndex: number;
  leaveIndex: number;
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
 * spawns at the campus gate (ENTRY_NODE_ID = "campus-gate", CAMPUS-GATE
 * pass 2026-09-15) and walks to its zone; an id whose targetZone
 * changed -> walks to the new zone; an id that dropped out of the incoming
 * list (server-side idle timeout) -> walks back out and unmounts itself
 * once that walk completes (LiveAgentAvatar's own onDespawned callback).
 * Ultra tier only -- see this file's own header for why (real rigged
 * characters, same tier gate as every other KitAgentBody render).
 */
export default function LiveAgents({ agents, walkGraph, ultra, reducedMotion }: LiveAgentsProps) {
  const [displayed, setDisplayed] = useState<Map<string, DisplayedAgent>>(new Map());
  // STAND-SLOT SHUFFLE-SNAP fix (CONVOY-STACK v5, 2026-09-15, all-state
  // displacement audit on probe 20260915T095436Z): persistent, STABLE
  // per-zone slot assignment (liveAgentWalk.ts#updateStableSlotAssignments)
  // -- a ref, not React state, because it must be the "previous" input to
  // its own next update on every reconcile (see that function's own doc for
  // the full stability contract this replaces computeStandSlot with: an
  // id's index never changes while it stays assigned to the SAME zone, no
  // matter who else joins or leaves). Updated synchronously inside the
  // reconcile effect below, immediately after `next` (the new `displayed`
  // map) is built, so the VERY NEXT render's `standSlots` memo already sees
  // the correct assignment -- never a render where a child's props are
  // stale relative to this ref.
  const slotAssignmentsRef = useRef<Map<string, Map<string, number>>>(new Map());

  useEffect(() => {
    ensureDiagInterval();
  }, []);

  // BUBBLE-FIX (2026-09-15): the actual diff/mark-leaving logic now lives in
  // liveAgentWalk.ts#reconcileLiveAgentRoster (pure, unit-tested against the
  // exact "one id replaced by another in the same poll" scenario the
  // coordinator's live-browser review flagged) -- this effect only supplies
  // the per-agent display-record builder (color assignment + bubble text
  // are side-effecting/component-local, so they stay here).
  //
  // CONVOY-STACK v2/v3 (2026-09-15): layered on top, not inside
  // reconcileLiveAgentRoster itself (kept untouched -- its own existing
  // tests stay valid) -- every id genuinely NEW this poll (not in `prev` at
  // all) gets a spawn-batch stagger delay + batch-order index via
  // liveAgentWalk.ts#computeBatchStaggerDelays/computeBatchOrder, sorted by
  // id among just that batch; every id that flips `leaving` true THIS poll
  // (was not already leaving in `prev`) separately gets a leave-batch delay
  // + index the same way. An id already displayed keeps its ORIGINAL
  // spawnDelayS/spawnIndex/leaveDelayS/leaveIndex forever (an id's batch
  // position is decided once, at the exact moment its walk is about to be
  // kicked off, never retroactively by a later sibling joining the same
  // target).
  useEffect(() => {
    setDisplayed((prev) => {
      const newIds = agents.map((a) => a.id).filter((id) => !prev.has(id));
      const spawnDelays = computeBatchStaggerDelays(newIds);
      const spawnOrder = computeBatchOrder(newIds);

      const next = reconcileLiveAgentRoster(prev, agents, (a, existing) => {
        const bubble = `${a.state === "spawning" ? "arrived" : a.state === "cooling" ? "wrapping up" : "working"} · ${a.lastDetail}`;
        const identity = liveAgentIdentity(a.label, a.id);
        return {
          id: a.id,
          label: a.label,
          serverState: a.state,
          bubble,
          rawDetail: a.rawDetail,
          targetNodeId: a.targetZone,
          leaving: false,
          accentColor: identity.tint,
          displayName: identity.displayName,
          taskDetail: a.taskDetail || bubble,
          spawnDelayS: existing ? existing.spawnDelayS : (spawnDelays.get(a.id) ?? 0),
          leaveDelayS: existing ? existing.leaveDelayS : 0,
          spawnIndex: existing ? existing.spawnIndex : (spawnOrder.get(a.id) ?? 0),
          leaveIndex: existing ? existing.leaveIndex : 0,
        };
      });

      const newlyLeavingIds = Array.from(next.entries())
        .filter(([id, d]) => d.leaving && !(prev.get(id)?.leaving ?? false))
        .map(([id]) => id);
      if (newlyLeavingIds.length > 0) {
        const leaveDelays = computeBatchStaggerDelays(newlyLeavingIds);
        const leaveOrder = computeBatchOrder(newlyLeavingIds);
        for (const id of newlyLeavingIds) {
          const d = next.get(id)!;
          next.set(id, { ...d, leaveDelayS: leaveDelays.get(id) ?? 0, leaveIndex: leaveOrder.get(id) ?? 0 });
        }
      }

      // CONVOY-STACK v5: update the STABLE per-zone slot assignment from
      // THIS round's fresh membership (grouped the same way standSlots
      // itself groups -- by EFFECTIVE destination) -- see
      // slotAssignmentsRef's own declaration above for why this must happen
      // here, synchronously, rather than in a separate effect.
      const membership = new Map<string, string[]>();
      for (const [id, d] of next) {
        const zoneKey = d.leaving ? ENTRY_NODE_ID : d.targetNodeId;
        const ids = membership.get(zoneKey) ?? [];
        ids.push(id);
        membership.set(zoneKey, ids);
      }
      slotAssignmentsRef.current = updateStableSlotAssignments(slotAssignmentsRef.current, membership);

      return next;
    });
  }, [agents]);

  // STAND-SLOT SHUFFLE-SNAP fix (CONVOY-STACK v5): derive each displayed
  // agent's on-screen offset from its STABLE assignment
  // (slotAssignmentsRef, updated above) rather than recomputing an index +
  // angle from the CURRENT group every render -- the old `computeStandSlot`
  // approach moved an existing resident whenever ANY sibling in the same
  // zone joined or left, which is exactly the reported "0.90u == the OLD
  // STAND_RING_RADIUS" shuffle-snap. `stableSlotOffset`'s own denominator
  // (STAND_SLOT_CAPACITY) is FIXED, never the current occupant count, so an
  // id's offset can only ever recompute to the SAME value it already had.
  const standSlots = useMemo(() => {
    const out = new Map<string, { offset: [number, number]; index: number }>();
    for (const d of displayed.values()) {
      const zoneKey = d.leaving ? ENTRY_NODE_ID : d.targetNodeId;
      const index = slotAssignmentsRef.current.get(zoneKey)?.get(d.id) ?? 0;
      out.set(d.id, { offset: stableSlotOffset(index), index });
    }
    return out;
  }, [displayed]);

  const handleDespawned = (id: string) => {
    diagStore.delete(id);
    // CONVOY-STACK v5: free this id's stable stand-slot immediately, rather
    // than waiting for the next reconcile poll to notice it's gone -- purely
    // an efficiency nicety (a departed id's slot is a no-op reservation
    // either way, since nobody renders there and updateStableSlotAssignments
    // would drop it on the very next poll regardless), but it lets a
    // newcomer reuse the freed index right away instead of a poll interval
    // later. Refs are this tree's own accepted mutable-bookkeeping
    // convention (see diagStore.delete just above).
    for (const zoneAssign of slotAssignmentsRef.current.values()) {
      zoneAssign.delete(id);
    }
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
            displayName={d.displayName}
            accentColor={d.accentColor}
            bubble={d.bubble}
            rawDetail={d.rawDetail}
            taskDetail={d.taskDetail}
            walkGraph={walkGraph}
            targetNodeId={d.targetNodeId}
            serverState={d.serverState}
            leaving={d.leaving}
            reducedMotion={reducedMotion}
            standOffset={slot.offset}
            standIndex={slot.index}
            spawnDelayS={d.spawnDelayS}
            leaveDelayS={d.leaveDelayS}
            spawnIndex={d.spawnIndex}
            leaveIndex={d.leaveIndex}
            onDespawned={() => handleDespawned(d.id)}
          />
        );
      })}
    </>
  );
}
