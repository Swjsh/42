"use client";

// ─── WORLD-6 (2026-09-14, W1) -- "the signature piece": a holographic SPY
// intraday chart floating above the hub's round table. ─────────────────────
//
// Reference-first (J's standing design rule -- external references BEFORE
// writing scene code, same rule ENVIRONMENT-PLAN.md's own passes already
// follow). 3 real references looked at this session (WebSearch + WebFetch,
// not assumed from memory):
//
//   1. https://threejs-journey.com/lessons/hologram-shader -- the canonical
//      three.js "holographic material" technique: a Fresnel term drives rim
//      brightness (brighter at grazing angles, the SAME "glows at the edges,
//      reads through at the face" look this file leans on), plus flat unlit
//      coloring. This component does NOT port the lesson's custom vertex-
//      glitch shader verbatim (this codebase has ZERO ShaderMaterial usage
//      anywhere -- grepped this session -- and every other "glowing" surface
//      in this tree, e.g. BrainCore's core sphere / Planet.tsx's rim glow,
//      achieves it with a plain unlit MeshBasicMaterial + this scene's own
//      selective Bloom pass, not a custom shader) -- the Fresnel-rim IDEA is
//      reused via Planet.tsx's own already-proven cheap technique (an
//      additive BackSide glow shell drawn behind the opaque body), applied
//      here to the base plate's edge ring instead of a shader.
//   2. https://codepen.io/peterhry/pen/egzjGR ("Holographic Projection") --
//      confirms the genre convention this component follows: a flat glowing
//      EMISSION PLANE at the projector's own base, with the projected
//      content rising from it, rather than a free-floating chart with no
//      visible source -- hence BASE_PLATE below (the round table reads as
//      the projector; this plate is its visible emission surface).
//   3. https://www.behance.net/gallery/11334149/3D-Stock-Market-Candlestick-Trading-Chart
//      -- real 3D candlestick-chart composition reference: filled body when
//      the bar closed UP, hollow/outline when DOWN. Adapted (not copied) to
//      this scene's own established green/red convention (already used by
//      BayInterior.tsx's P&L gauge and HEALTH_COLOR) rather than a fill/
//      hollow distinction, which would be unreadable at hologram scale from
//      preset-0 camera distance.
//
// DATA: own SWR fetch of /api/hq-chart every 60s (this component owns its
// data -- no Scene.tsx/route.ts edits, per this task's own file-ownership
// rule). Real SPY 5-minute bars (backtest/data/spy_5m_*.csv -- the finest
// resolution that exists locally; no spy_1m_*.csv file exists in this repo,
// checked this session), the engine's real key levels
// (automation/state/key-levels.json), and today's REAL fills
// (journal/trades.csv) -- see lib/hq-chart-data.ts's own header for the full
// per-source provenance and why trades.csv (not core-decisions.jsonl) is the
// entries/exits source of truth.
//
// ANIMATION RULE (HQ face rule, hard -- "the spinning color radar looking
// things can go... the traveling orbs can go too... motion must be EVENT- or
// DATA-driven and mean something"): NOTHING in this file spins, orbits,
// drifts, or pulses on a decorative timer. The only three motions that exist
// are all direct consequences of a REAL state change:
//   - a bar's own body grows in (Y-scale 0->1, ~450ms) exactly once, the
//     first render after `bars.length` genuinely increases (a new 5-minute
//     bar actually landed) -- see growState below;
//   - a level plane flashes to white exactly once, only when the NEWEST bar's
//     own [low,high] range crosses/touches that level's price where the
//     PREVIOUS newest bar's range did not -- see checkLevelTouches below;
//   - the last-price marker's brightness reflects the live sight-beacon's
//     own freshness (dims if stale), a data readout, not a loop.
// Everything else (candle bodies, wicks, level planes, the base plate, every
// label) is drawn once per data change and then sits still.

import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import useSWR from "swr";
import { PALETTE } from "./palette";
import type { HoloChartData, HoloLevel, HoloTradeMarker } from "@/lib/hq-chart-data";
import type { ChartBar } from "@/lib/chart-data";

const FETCH_INTERVAL_MS = 60_000;

// ─── layout constants (local space: +X = time axis oldest->newest, +Y =
//     price, +Z = depth toward the viewer) ─────────────────────────────────
const RIBBON_WIDTH = 4.4;
// Real-capture-driven fix (2026-09-14, this session -- world6-hub-zoom3.png/
// world6-chart-closeup2.png): the chart mounts at TABLE_TOP_Y+0.03 (world Y
// ~0.71, HubInterior.tsx) and BrainCore's own "BRAIN · wrote brief" plaque
// sits at world Y ~2.01 (its local y=1.75 inside BrainCore's own
// `scale={1.15}` group, 1.75*1.15=2.01) -- 1.3 of height landed the
// ribbon's own top almost EXACTLY at that same Y, so from the default
// preset-0 camera (whose azimuth 38.66deg sits close enough to the table's
// own 45deg that everything along that line stacks in screen space) the
// chart's tallest bars visually collided with BrainCore's plaque text.
// 0.8 keeps the ribbon's top at ~1.51, comfortably under 2.01.
const RIBBON_MAX_HEIGHT = 0.8;
const BODY_DEPTH = 0.09;
const WICK_SIZE = 0.02;
const BASE_PLATE_MARGIN = 0.4;
const MAX_BARS = 90; // headroom above a full 78-bar RTH session
const MAX_LEVELS = 14; // headroom above the 8 levels typically Active
const GROW_MS = 450;
const FLASH_MS = 1300;

const COLOR_UP = new THREE.Color("#22ff88");
const COLOR_DOWN = new THREE.Color("#ff3b3b");
const COLOR_SUPPORT = new THREE.Color(PALETTE.hubCore); // cyan -- "floor", cold
const COLOR_RESISTANCE = new THREE.Color(PALETTE.warmAccent); // amber -- "ceiling", warm
const COLOR_FLASH = new THREE.Color("#ffffff");

const _matrix = new THREE.Matrix4();
const _pos = new THREE.Vector3();
const _quat = new THREE.Quaternion();
const _scale = new THREE.Vector3();
const _euler = new THREE.Euler();
const IDENTITY_QUAT = new THREE.Quaternion();

function fetcher(url: string): Promise<HoloChartData> {
  return fetch(url).then((r) => r.json());
}

/** Domain the ribbon's whole vertical axis maps to -- session [low,high]
 * widened to also cover every VISIBLE level (server already dropped levels
 * far outside the session range, see lib/hq-chart-data.ts#filterLevelsNearRange),
 * so a level plane is never drawn above/below the ribbon's own physical
 * extent. */
function computeDomain(data: HoloChartData): { low: number; high: number } | null {
  if (!data.priceRange) return null;
  let { low, high } = data.priceRange;
  for (const l of data.levels) {
    if (l.price < low) low = l.price;
    if (l.price > high) high = l.price;
  }
  if (high - low < 0.5) {
    // Guards against a near-zero range (a near-flat session) producing a
    // huge/undefined height scale -- widens symmetrically, never fabricates
    // a price, just gives the mapping room to work with.
    const mid = (low + high) / 2;
    low = mid - 0.5;
    high = mid + 0.5;
  }
  return { low, high };
}

function xForBarIndex(index: number, count: number): number {
  if (count <= 1) return 0;
  return (index / (count - 1) - 0.5) * RIBBON_WIDTH;
}

function yForPrice(price: number, domain: { low: number; high: number }): number {
  return ((price - domain.low) / (domain.high - domain.low)) * RIBBON_MAX_HEIGHT;
}

interface GrowState {
  index: number;
  startMs: number;
}

/** One-shot flash bookkeeping per level index -- see checkLevelTouches. Plain
 * arrays (not React state): this only ever gets read/written inside
 * useFrame/useEffect, and turning it into state would re-render the whole
 * component every flash tick for zero benefit (mirrors BrainCore.tsx's own
 * `pulsing` ref-first reasoning, just without even the one React re-render
 * BrainCore accepts, since here NOTHING else needs to know). */
function checkLevelTouches(
  prevLast: ChartBar | null, newLast: ChartBar, levels: HoloLevel[], flashUntilMs: Float64Array, nowMs: number,
): void {
  for (let i = 0; i < levels.length; i++) {
    const price = levels[i].price;
    const touchedNow = price >= newLast.low && price <= newLast.high;
    const touchedBefore = prevLast ? price >= prevLast.low && price <= prevLast.high : false;
    if (touchedNow && !touchedBefore) flashUntilMs[i] = nowMs + FLASH_MS;
  }
}

interface BarsRibbonProps {
  bars: ChartBar[];
  domain: { low: number; high: number };
  /** "GPU RESERVED -- J IS GAMING" dim state (the SAME dimFactor BrainCore's
   * own glow sprite / IdeasWall's content face already fade under) -- a real
   * data readout, not a decorative fade. */
  opacity: number;
}

/** Candle bodies + wicks -- two InstancedMesh draw calls total regardless of
 * bar count (`mesh.count` trims how many of the MAX_BARS pre-allocated
 * instances actually draw, three.js's own standard technique -- no
 * reallocation on a normal 60s data refresh). Matrices are rebuilt on every
 * data change (cheap: <=78 instances, not a per-frame cost) except the
 * newest bar when it just appeared, which grows in over GROW_MS via
 * useFrame -- see the module header's ANIMATION RULE. */
function BarsRibbon({ bars, domain, opacity }: BarsRibbonProps) {
  const bodyRef = useRef<THREE.InstancedMesh>(null);
  const wickRef = useRef<THREE.InstancedMesh>(null);
  const prevBarsRef = useRef<ChartBar[]>([]);
  const growRef = useRef<GrowState | null>(null);

  const bodyGeo = useMemo(() => new THREE.BoxGeometry(1, 1, BODY_DEPTH), []);
  const wickGeo = useMemo(() => new THREE.BoxGeometry(WICK_SIZE, 1, WICK_SIZE), []);

  const writeBodyInstance = (i: number, bar: ChartBar, growT: number) => {
    const body = bodyRef.current;
    const wick = wickRef.current;
    if (!body || !wick) return;
    const x = xForBarIndex(i, bars.length);
    const up = bar.close >= bar.open;
    const top = yForPrice(Math.max(bar.open, bar.close), domain);
    const bottom = yForPrice(Math.min(bar.open, bar.close), domain);
    const bodyHeight = Math.max(0.01, (top - bottom)) * growT;
    const bodyWidth = Math.max(0.012, (RIBBON_WIDTH / bars.length) * 0.62);

    _pos.set(x, bottom + bodyHeight / 2, 0);
    _scale.set(bodyWidth, bodyHeight, 1);
    _matrix.compose(_pos, IDENTITY_QUAT, _scale);
    body.setMatrixAt(i, _matrix);
    body.setColorAt(i, up ? COLOR_UP : COLOR_DOWN);

    const wickTop = yForPrice(bar.high, domain) * growT;
    const wickBottom = yForPrice(bar.low, domain) * growT;
    const wickHeight = Math.max(0.005, wickTop - wickBottom);
    _pos.set(x, wickBottom + wickHeight / 2, 0);
    _scale.set(1, wickHeight, 1);
    _matrix.compose(_pos, IDENTITY_QUAT, _scale);
    wick.setMatrixAt(i, _matrix);
    wick.setColorAt(i, up ? COLOR_UP : COLOR_DOWN);
  };

  useEffect(() => {
    const body = bodyRef.current;
    const wick = wickRef.current;
    if (!body || !wick) return;
    body.count = bars.length;
    wick.count = bars.length;

    const prev = prevBarsRef.current;
    // "A new bar landed" -- count grew AND the new tail bar's own chartTime
    // is genuinely later than what was there before (never a spurious
    // reorder/shrink triggering a grow animation).
    const grew = bars.length > prev.length && (prev.length === 0 || bars[bars.length - 1].time > prev[prev.length - 1].time);

    for (let i = 0; i < bars.length; i++) {
      const isNewest = grew && i === bars.length - 1;
      writeBodyInstance(i, bars[i], isNewest ? 0 : 1);
    }
    body.instanceMatrix.needsUpdate = true;
    wick.instanceMatrix.needsUpdate = true;
    if (body.instanceColor) body.instanceColor.needsUpdate = true;
    if (wick.instanceColor) wick.instanceColor.needsUpdate = true;

    growRef.current = grew ? { index: bars.length - 1, startMs: performance.now() } : null;
    prevBarsRef.current = bars;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bars, domain.low, domain.high]);

  useFrame(() => {
    const grow = growRef.current;
    if (!grow) return;
    const t = Math.min(1, (performance.now() - grow.startMs) / GROW_MS);
    const eased = 1 - (1 - t) * (1 - t); // ease-out, matches this tree's general preference for soft arrivals
    writeBodyInstance(grow.index, bars[grow.index], eased);
    const body = bodyRef.current;
    const wick = wickRef.current;
    if (body) body.instanceMatrix.needsUpdate = true;
    if (wick) wick.instanceMatrix.needsUpdate = true;
    if (t >= 1) growRef.current = null;
  });

  return (
    <>
      <instancedMesh ref={bodyRef} args={[bodyGeo, undefined, MAX_BARS]} frustumCulled={false}>
        <meshBasicMaterial toneMapped={false} transparent opacity={0.92 * opacity} />
      </instancedMesh>
      <instancedMesh ref={wickRef} args={[wickGeo, undefined, MAX_BARS]} frustumCulled={false}>
        <meshBasicMaterial toneMapped={false} transparent opacity={0.75 * opacity} />
      </instancedMesh>
    </>
  );
}

interface LevelPlanesProps {
  levels: HoloLevel[];
  domain: { low: number; high: number };
  bars: ChartBar[];
  opacity: number;
}

/** Thin glowing horizontal planes, one per real key level -- ONE
 * InstancedMesh draw call regardless of level count. Flashes white once when
 * the session's newest bar crosses/touches a level it wasn't already
 * touching (see checkLevelTouches) -- inert (no-op every frame) whenever no
 * flash is active, which is the steady-state case. */
function LevelPlanes({ levels, domain, bars, opacity }: LevelPlanesProps) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const flashUntilRef = useRef<Float64Array>(new Float64Array(MAX_LEVELS));
  const prevLastBarRef = useRef<ChartBar | null>(null);
  const geo = useMemo(() => new THREE.BoxGeometry(RIBBON_WIDTH + BASE_PLATE_MARGIN * 0.6, 0.012, 0.012), []);

  const writeColor = (i: number, base: THREE.Color, nowMs: number) => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const flashing = flashUntilRef.current[i] > nowMs;
    mesh.setColorAt(i, flashing ? COLOR_FLASH : base);
  };

  useEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    mesh.count = levels.length;
    for (let i = 0; i < levels.length; i++) {
      _pos.set(0, yForPrice(levels[i].price, domain), 0);
      _matrix.compose(_pos, IDENTITY_QUAT, _scale.set(1, 1, 1));
      mesh.setMatrixAt(i, _matrix);
      writeColor(i, levels[i].type === "support" ? COLOR_SUPPORT : COLOR_RESISTANCE, performance.now());
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;

    const newLast = bars.length > 0 ? bars[bars.length - 1] : null;
    const prevLast = prevLastBarRef.current;
    if (newLast && (!prevLast || newLast.time > prevLast.time)) {
      checkLevelTouches(prevLast, newLast, levels, flashUntilRef.current, performance.now());
    }
    prevLastBarRef.current = newLast;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [levels, domain.low, domain.high, bars]);

  useFrame(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const now = performance.now();
    let anyActive = false;
    for (let i = 0; i < levels.length; i++) {
      if (flashUntilRef.current[i] > now) anyActive = true;
    }
    if (!anyActive) return; // steady state -- zero-cost past the loop above
    for (let i = 0; i < levels.length; i++) {
      writeColor(i, levels[i].type === "support" ? COLOR_SUPPORT : COLOR_RESISTANCE, now);
    }
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  });

  return (
    <instancedMesh ref={meshRef} args={[geo, undefined, MAX_LEVELS]} frustumCulled={false}>
      <meshBasicMaterial toneMapped={false} transparent opacity={0.85 * opacity} />
    </instancedMesh>
  );
}

// Real-capture-driven fix (world6-chart-closeup2.png, this session): today's
// real key levels cluster tightly (757.44/757.77/757.93 within $0.49 of each
// other) and their PRICE-true Y positions overlapped into an unreadable
// stack of text. Labels (not the level planes themselves, which stay at
// their real price height) get nudged apart with a minimum world-Y gap,
// lowest price first -- the same "declutter the label, keep the data
// honest" technique real charting UIs use, never a fabricated price.
const MIN_LABEL_GAP = 0.075;

function layoutLabelYs(levels: HoloLevel[], domain: { low: number; high: number }): number[] {
  const rawY = levels.map((l) => yForPrice(l.price, domain));
  const order = rawY.map((_, i) => i).sort((a, b) => rawY[a] - rawY[b]);
  const displayY = [...rawY];
  for (let k = 1; k < order.length; k++) {
    const prev = order[k - 1];
    const cur = order[k];
    if (displayY[cur] - displayY[prev] < MIN_LABEL_GAP) displayY[cur] = displayY[prev] + MIN_LABEL_GAP;
  }
  return displayY;
}

function LevelLabels({ levels, domain, dimFactor }: { levels: HoloLevel[]; domain: { low: number; high: number }; dimFactor: number }) {
  const labelYs = useMemo(() => layoutLabelYs(levels, domain), [levels, domain]);
  return (
    <>
      {levels.map((l, i) => (
        <Html
          key={`${l.type}-${l.price}`}
          position={[RIBBON_WIDTH / 2 + BASE_PLATE_MARGIN * 0.55, labelYs[i], 0]}
          center
          distanceFactor={7}
          style={{ pointerEvents: "none" }}
        >
          <div
            style={{
              fontFamily: "system-ui, sans-serif", whiteSpace: "nowrap",
              color: l.type === "support" ? PALETTE.hubCore : PALETTE.warmAccent,
              background: "rgba(3,4,10,0.72)", padding: "2px 8px", borderRadius: 5,
              fontSize: 15, fontWeight: 700, letterSpacing: 0.3, opacity: dimFactor,
            }}
          >
            {l.price.toFixed(2)} <span style={{ opacity: 0.75, fontWeight: 600 }}>{l.tag}</span>
          </div>
        </Html>
      ))}
    </>
  );
}

const MAX_TRADES = 24; // headroom above any realistic single-session trade-marker count

interface PositionedTrade {
  trade: HoloTradeMarker;
  x: number;
  y: number;
}

/** ONE InstancedMesh draw call for every entry/exit marker cone, regardless
 * of trade count -- coordinator draw-call-budget flag (2026-09-14, real
 * capture hq-20260914-1725.png: 1093/1100 calls) explicitly called out
 * "never one mesh per bar" for the ribbon and the identical principle
 * applies here: a per-trade `<mesh>` was fine at today's 2-marker count but
 * would scale linearly on a heavier trading day. Html tooltips stay
 * per-marker (DOM, zero WebGL draw-call cost either way). */
function TradeMarkers({
  trades, bars, domain, dimFactor,
}: { trades: HoloTradeMarker[]; bars: ChartBar[]; domain: { low: number; high: number }; dimFactor: number }) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const geo = useMemo(() => new THREE.ConeGeometry(0.045, 0.11, 5), []);

  const positioned: PositionedTrade[] = useMemo(
    () => trades
      .filter((t) => t.barIndex !== null && bars[t.barIndex])
      .map((t) => {
        const bar = bars[t.barIndex as number];
        const x = xForBarIndex(t.barIndex as number, bars.length);
        const y = yForPrice(t.side === "entry" ? bar.high : bar.low, domain) + (t.side === "entry" ? 0.14 : -0.1);
        return { trade: t, x, y };
      }),
    [trades, bars, domain],
  );

  useEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    mesh.count = positioned.length;
    positioned.forEach((p, i) => {
      _pos.set(p.x, p.y, 0);
      _euler.set(p.trade.side === "entry" ? Math.PI : 0, 0, 0);
      _quat.setFromEuler(_euler);
      _matrix.compose(_pos, _quat, _scale.set(1, 1, 1));
      mesh.setMatrixAt(i, _matrix);
      mesh.setColorAt(i, p.trade.direction === "call" ? COLOR_UP : COLOR_DOWN);
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [positioned]);

  return (
    <>
      <instancedMesh ref={meshRef} args={[geo, undefined, MAX_TRADES]} frustumCulled={false}>
        <meshBasicMaterial toneMapped={false} transparent opacity={0.95 * dimFactor} />
      </instancedMesh>
      {positioned.map(({ trade: t, x, y }) => {
        const color = t.direction === "call" ? "#22ff88" : "#ff3b3b";
        return (
          <Html
            key={`${t.side}-${t.atIso}-${t.price}`}
            position={[x, y + (t.side === "entry" ? 0.16 : -0.16), 0]}
            center distanceFactor={7} style={{ pointerEvents: "none" }}
          >
            <div
              style={{
                fontFamily: "system-ui, sans-serif", whiteSpace: "nowrap", color: "#dff3ff",
                background: "rgba(3,4,10,0.78)", padding: "2px 7px", borderRadius: 5,
                fontSize: 13, fontWeight: 600, border: `1px solid ${color}`, opacity: dimFactor,
              }}
            >
              {t.side === "entry" ? "ENTER" : "EXIT"} {t.setup} ${t.price.toFixed(2)}
              {t.count > 1 ? ` ×${t.count}` : ""}
              {t.pnl !== null ? ` (${t.pnl >= 0 ? "+" : ""}${t.pnl.toFixed(0)})` : ""}
            </div>
          </Html>
        );
      })}
    </>
  );
}

/** The projector's own visible emission surface -- see the module header's
 * reference #2 (CodePen "Holographic Projection") for why a floating chart
 * needs a visible source plane, not just bars hanging in empty space. Static
 * (no motion), a flat ring + faint disc, unlit cyan. */
function BasePlate({ dimFactor }: { dimFactor: number }) {
  return (
    <group position={[0, -0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <mesh>
        <ringGeometry args={[0.02, RIBBON_WIDTH / 2 + BASE_PLATE_MARGIN, 48]} />
        <meshBasicMaterial color={PALETTE.hubCore} toneMapped={false} transparent opacity={0.06 * dimFactor} side={THREE.DoubleSide} />
      </mesh>
      <mesh>
        <ringGeometry args={[RIBBON_WIDTH / 2 + BASE_PLATE_MARGIN - 0.03, RIBBON_WIDTH / 2 + BASE_PLATE_MARGIN, 48]} />
        <meshBasicMaterial color={PALETTE.hubCore} toneMapped={false} transparent opacity={0.55 * dimFactor} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

/** Bright "you are here" marker at the newest close -- brightness reflects
 * the live sight-beacon's own freshness (a data readout: dim = stale, bright
 * = fresh), never a decorative pulse. */
function LastPriceMarker({
  data, domain, dimFactor,
}: { data: HoloChartData; domain: { low: number; high: number }; dimFactor: number }) {
  const matRef = useRef<THREE.MeshBasicMaterial>(null);
  useFrame(() => {
    if (matRef.current) matRef.current.opacity = (data.live ? 1 : 0.55) * dimFactor;
  });
  if (!data.lastClose || data.bars.length === 0) return null;
  const x = xForBarIndex(data.bars.length - 1, data.bars.length) + RIBBON_WIDTH / (data.bars.length * 2) + 0.16;
  const y = yForPrice(data.lastClose.price, domain);
  const priceText = data.live ? `${data.live.price.toFixed(2)} · LIVE` : `${data.lastClose.price.toFixed(2)} · last close`;
  return (
    <group position={[x, y, 0]}>
      <mesh>
        <octahedronGeometry args={[0.07, 0]} />
        <meshBasicMaterial ref={matRef} color="#ffffff" toneMapped={false} transparent opacity={1} />
      </mesh>
      <Html position={[0.18, 0, 0]} distanceFactor={7} style={{ pointerEvents: "none" }}>
        <div className="hq-beam" style={{ ["--beam-color" as string]: PALETTE.hubCore, borderRadius: 6, opacity: dimFactor }}>
          <div
            style={{
              fontFamily: "system-ui, sans-serif", whiteSpace: "nowrap", color: "#dff3ff",
              background: "rgba(3,4,10,0.8)", padding: "3px 9px", borderRadius: 5,
              fontSize: 16, fontWeight: 700,
            }}
          >
            {priceText}
          </div>
        </div>
      </Html>
    </group>
  );
}

export interface HoloChartProps {
  /** World-space position of the ribbon's own local origin -- the round
   * table's top surface, passed in by HubInterior.tsx (which already
   * computes TABLE_CENTER + the table's real top height, see that file's own
   * comment on table-large.glb's parsed bounds). */
  origin: [number, number, number];
  /** Yaw so local +X reads left-right from the default/preset-1 camera --
   * HubInterior.tsx's own facingHubRotationY(TABLE_CENTER), passed in rather
   * than recomputed here (single source of truth for the table's own
   * orientation math). */
  facingYaw: number;
  dimFactor: number;
}

export default function HoloChart({ origin, facingYaw, dimFactor }: HoloChartProps) {
  const { data } = useSWR<HoloChartData>("/api/hq-chart", fetcher, {
    refreshInterval: FETCH_INTERVAL_MS,
    revalidateOnFocus: false,
    dedupingInterval: FETCH_INTERVAL_MS,
  });

  const domain = data ? computeDomain(data) : null;

  return (
    <group position={origin} rotation={[0, facingYaw, 0]}>
      <BasePlate dimFactor={dimFactor} />
      {!data ? (
        <Html position={[0, 0.5, 0]} center distanceFactor={7} style={{ pointerEvents: "none" }}>
          <div style={{ color: PALETTE.textDim, fontFamily: "system-ui, sans-serif", fontSize: 14 }}>loading chart…</div>
        </Html>
      ) : !data.ok || data.bars.length === 0 || !domain ? (
        <Html position={[0, 0.5, 0]} center distanceFactor={7} style={{ pointerEvents: "none" }}>
          <div
            style={{
              color: PALETTE.textDim, fontFamily: "system-ui, sans-serif", fontSize: 15, textAlign: "center",
              background: "rgba(3,4,10,0.7)", padding: "6px 14px", borderRadius: 6, whiteSpace: "nowrap",
            }}
          >
            {data.session.label}
            <div style={{ fontSize: 12, marginTop: 2, opacity: 0.8 }}>{data.error ?? "no bar data"}</div>
          </div>
        </Html>
      ) : (
        <group position={[0, 0.02, 0]} visible={dimFactor > 0.02}>
          <BarsRibbon bars={data.bars} domain={domain} opacity={dimFactor} />
          <LevelPlanes levels={data.levels} domain={domain} bars={data.bars} opacity={dimFactor} />
          <LevelLabels levels={data.levels} domain={domain} dimFactor={dimFactor} />
          <TradeMarkers trades={data.trades} bars={data.bars} domain={domain} dimFactor={dimFactor} />
          <LastPriceMarker data={data} domain={domain} dimFactor={dimFactor} />
          <Html position={[0, -0.22, 0]} center distanceFactor={7} style={{ pointerEvents: "none" }}>
            <div
              style={{
                color: PALETTE.textDim, fontFamily: "system-ui, sans-serif", fontSize: 13, fontWeight: 600,
                background: "rgba(3,4,10,0.65)", padding: "2px 10px", borderRadius: 5, whiteSpace: "nowrap",
                letterSpacing: 0.4, opacity: dimFactor,
              }}
            >
              {data.session.label}
            </div>
          </Html>
        </group>
      )}
    </group>
  );
}
