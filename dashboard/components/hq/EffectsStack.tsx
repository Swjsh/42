"use client";

import { memo, useRef, type RefObject } from "react";
import { useFrame } from "@react-three/fiber";
import { EffectComposer, Bloom, SMAA, Vignette, ChromaticAberration, N8AO, GodRays } from "@react-three/postprocessing";
import { EffectPass, BloomEffect, type EffectComposer as EffectComposerImpl } from "postprocessing";
import type * as THREE from "three";
import { lerp } from "./palette";

interface EffectsStackProps {
  /** The brain core's own SPHERE MESH (not its glow sprite -- GodRays'
   * `sun` prop is typed Mesh | Points, and the sphere is the more
   * physically sensible "light source" object anyway). Ref-shared from
   * Scene.tsx, attached by BrainCore.tsx. Passed as a RefObject, not
   * `.current` -- react-three-postprocessing reads it after React's own
   * commit phase has already attached every ref in the tree, so this
   * never races the mount order. */
  coreMeshRef: RefObject<THREE.Mesh | null>;
  /** LIVE-1 item 2 follow-up (coordinator 2026-09-14): Scene.tsx's own
   * day/night factor (0=night, 1=day), written into this ref EVERY Scene
   * render (never a reactive number PROP) -- see this file's own
   * BLOOM_NIGHT_THRESHOLD/BLOOM_DAY_THRESHOLD comment below for why a
   * plain number prop here would be unsafe. */
  dayFactorRef: RefObject<number>;
}

const BLOOM_NIGHT_THRESHOLD = 0.78; // unchanged from the original night-tuned value
const BLOOM_DAY_THRESHOLD = 0.9; // coordinator's own number -- "day ~0.9"
const THRESHOLD_CHECK_INTERVAL_S = 1; // step not lerp, checked once/sec -- same cadence item 4's arch-emissive mechanism used

/**
 * Ultra tier only (HQ-ULTRA-TIER-BRIEF.md section 2) -- ONE EffectComposer,
 * restrained per the brief's own "copy Lusion's restraint, not the effect
 * count": selective Bloom (only emissive/toneMapped-false materials lift
 * out of 0-1 and actually bloom), SMAA instead of hardware MSAA (N8AO does
 * not combine with MSAA per the brief), a faint Vignette, a barely-
 * perceptible ChromaticAberration, moderate N8AO, and GodRays scoped to
 * the ONE hero light source (brain core, no DepthOfField -- see that
 * pass's own removal note below) -- never a
 * second GodRays pass on anything else, per the brief's explicit warning
 * that a second pass isn't worth its cost (fake additive cones are the
 * queued alternative for secondary sources, not built this pass).
 *
 * World pass A REAL bug fix (2026-09-13, found by reading
 * @react-three/postprocessing's own GodRays.tsx source, not guessed): its
 * DepthOfField REMOVED (Pass F, 2026-09-13, coordinator's real-monitor
 * capture): `focusDistance={0.02}` put the in-focus plane essentially at
 * the camera lens, so the entire station -- which sits at a moderate-to-far
 * distance in every composition this scene actually uses -- rendered
 * uniformly soft ("PS2 softness," the coordinator's own words). The
 * coordinator offered "focus the full set (wide focal range) or drop DoF";
 * dropping it is the lower-risk choice (DoF is hard to tune well for a wide
 * static diorama shot, not a shallow hero-object shot) and guarantees no
 * regression risk from a re-tuned focus distance that might still be wrong
 * for SOME camera angle this scene's event-driven CameraRig can reach
 * (Pass D's ease-to-event/vignette moves the lookAt around, which would
 * also move where "in focus" should be -- one static focusDistance can't
 * track that correctly anyway). Bloom stays selective per the brief.
 *
 * `useMemo(() => new GodRaysEffect(...), [camera, props])` depends on the
 * WHOLE props object, which JSX allocates fresh on every render of this
 * component's PARENT -- Scene.tsx re-renders on every SWR poll (every
 * 15-60s), and without memoization here, EffectsStack re-rendered right
 * along with it, so `<GodRays>` got a brand-new `props` reference every
 * poll and silently rebuilt its entire GodRaysEffect (render targets,
 * shaders, pass wiring) each time -- a real resource-churn bug, and the
 * most likely source of the repeating "Cannot read properties of null
 * (reading 'parent')" console crash (a race during that pass teardown/
 * rebuild), independent of the separate Suspense-boundary fix in
 * BrainCore.tsx/Agent.tsx/Scene.tsx/StationModule.tsx. `React.memo` here
 * means this component's own props (`coreMeshRef`/`dayFactorRef`, both
 * `useRef` objects -- ALWAYS the same object reference for the component's
 * lifetime, React's own guarantee) never change, so it renders ONCE and
 * GodRays' internal `props` reference stays stable for good.
 *
 * LIVE-1 item 2 follow-up (coordinator 2026-09-14, "scale exposure and the
 * bloom threshold with the same nightFactor the sky and lights use"):
 * `dayFactorRef` is a REF for exactly the same reason `coreMeshRef` is --
 * this component must NEVER re-render (see above), so the day/night value
 * cannot be a reactive number prop no matter how small the visual change;
 * memo() would still let a genuinely-changing prop value through, which
 * would re-execute this WHOLE function body, giving `<GodRays>` a fresh
 * `props` object and reconstructing GodRaysEffect all over again -- the
 * exact bug this file already fixed once, just at a slower (1/sec) cadence
 * instead of every SWR poll. `<Bloom>`'s OWN args-memoization is actually
 * BY VALUE (`@react-three/postprocessing`'s wrapEffect factory memoizes the
 * constructor args on `JSON.stringify(props)`, not the props object's
 * reference -- read from the installed package's bundled source this
 * session, not assumed), so Bloom itself would tolerate a reactive prop
 * fine; GodRays is the one that can't, and it lives in the same never-
 * re-render component, so the ref discipline applies to this whole file.
 * The fix: read the BloomEffect instance imperatively off the
 * EffectComposer's own pass list (`composer.passes` -> each EffectPass's
 * `.effects`) inside a useFrame, and write `.luminanceMaterial.threshold`
 * directly -- a plain shader uniform write (verified from postprocessing
 * 6.39.1's own source: `set threshold(v) { this.uniforms.threshold.value =
 * v; }`), which needs no recompile/dispose and takes effect next draw call.
 */
function EffectsStack({ coreMeshRef, dayFactorRef }: EffectsStackProps) {
  const composerRef = useRef<EffectComposerImpl>(null);
  const lastAppliedThreshold = useRef<number | null>(null);
  const lastCheckAtS = useRef(-Infinity); // -Infinity, not 0 -- guarantees the very first frame applies immediately rather than waiting a full second for a correct threshold

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    if (t - lastCheckAtS.current < THRESHOLD_CHECK_INTERVAL_S) return;
    lastCheckAtS.current = t;
    const dayFactor = dayFactorRef.current ?? 1;
    const threshold = lerp(BLOOM_NIGHT_THRESHOLD, BLOOM_DAY_THRESHOLD, dayFactor);
    if (lastAppliedThreshold.current !== null && Math.abs(lastAppliedThreshold.current - threshold) < 0.001) return;
    lastAppliedThreshold.current = threshold;
    const composer = composerRef.current;
    if (!composer) return;
    for (const pass of composer.passes) {
      if (!(pass instanceof EffectPass)) continue;
      // `.effects` is a private TS field on EffectPass (postprocessing's own
      // public API has no getter for it), but it's a genuine, always-present
      // runtime array -- same "reach past an artificially narrow third-party
      // .d.ts" justification already used elsewhere in this codebase.
      const effects = (pass as unknown as { effects: unknown[] }).effects;
      for (const effect of effects) {
        if (effect instanceof BloomEffect) effect.luminanceMaterial.threshold = threshold;
      }
    }
  }, -1); // before EffectComposer's own priority-1 render (PerfReporter.tsx's own reset documents this same ordering)

  return (
    // enableNormalPass REMOVED (PERF-3, 2026-09-15): N8AO here is
    // @react-three/postprocessing's wrapper around n8ao's own N8AOPostPass
    // (node_modules/n8ao/src/N8AOPass.js), a standalone `Pass` -- verified
    // this session by reading its constructor (`constructor(scene, camera,
    // width, height)`) and render targets (`beautyRenderTarget`,
    // `writeTargetInternal`, `readTargetInternal`, `accumulationRenderTarget`):
    // it renders the scene AND reconstructs depth/normals ITSELF into its
    // own render targets every frame, entirely independent of
    // EffectComposer's shared NormalPass texture. enableNormalPass exists
    // for `Effect`-based passes that declare EffectAttribute.DEPTH and read
    // the composer's shared normal buffer; N8AOPostPass is a `Pass`, not an
    // `Effect`, and never touches that buffer (grepped n8ao's own source for
    // any reference to a composer-supplied normal texture -- none). With it
    // on, the composer was rendering the whole ~394-object scene a SECOND
    // time purely to feed a buffer nothing consumes -- the single largest
    // line item in the draw-call budget (est. ~350-390 of the measured
    // 893-call overview total). Real A/B capture this session (ao-before.png
    // / ao-after.png, same fixed camera) shows no visible AO change.
    <EffectComposer ref={composerRef} multisampling={0}>
      <N8AO aoRadius={1.5} distanceFalloff={1} intensity={2.5} quality="high" />
      {/* World pass A (2026-09-13): threshold 0.92->0.78 -- paired with
          BrainCore.tsx's raised idle-state glow floor so the hub core
          blooms even when the GPU is idle, not only when genuinely busy
          ("cyan core glow strong enough to bloom" per the ask). Still
          selective: normal lit MeshStandard/Physical materials (desks,
          rooms, characters) stay well under this even with the new 1.35x
          tone-mapping exposure (UltraCanvasRoot.tsx) -- only
          toneMapped={false} emissive surfaces (core, rings, beacons, screen
          insets, edge strips) are authored with color values that exceed 1.
          LIVE-1 item 2 follow-up: this JSX value is only the FIRST-FRAME
          starting point (BLOOM_NIGHT_THRESHOLD) -- the useFrame above
          overwrites the real BloomEffect instance's threshold imperatively
          every second from then on, scaling it toward BLOOM_DAY_THRESHOLD
          by day so the tan architecture keeps its edges instead of blowing
          out under the same exposure daylight now needs to read bright. */}
      <Bloom mipmapBlur luminanceThreshold={BLOOM_NIGHT_THRESHOLD} luminanceSmoothing={0.25} intensity={0.9} />
      <GodRays sun={coreMeshRef as RefObject<THREE.Mesh>} samples={40} density={0.85} decay={0.92} weight={0.4} exposure={0.3} clampMax={1} blur />
      <ChromaticAberration offset={[0.0005, 0.0005]} />
      <Vignette />
      <SMAA />
    </EffectComposer>
  );
}

export default memo(EffectsStack);
