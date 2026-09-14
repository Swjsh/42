"use client";

import { memo, type RefObject } from "react";
import { EffectComposer, Bloom, SMAA, Vignette, ChromaticAberration, N8AO, GodRays } from "@react-three/postprocessing";
import type * as THREE from "three";

interface EffectsStackProps {
  /** The brain core's own SPHERE MESH (not its glow sprite -- GodRays'
   * `sun` prop is typed Mesh | Points, and the sphere is the more
   * physically sensible "light source" object anyway). Ref-shared from
   * Scene.tsx, attached by BrainCore.tsx. Passed as a RefObject, not
   * `.current` -- react-three-postprocessing reads it after React's own
   * commit phase has already attached every ref in the tree, so this
   * never races the mount order. */
  coreMeshRef: RefObject<THREE.Mesh | null>;
}

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
 * means this component's own props (`coreMeshRef`, a `useRef` -- ALWAYS the
 * same object reference for the component's lifetime, React's own
 * guarantee) never change, so it renders ONCE and GodRays' internal
 * `props` reference stays stable for good.
 */
function EffectsStack({ coreMeshRef }: EffectsStackProps) {
  return (
    <EffectComposer enableNormalPass multisampling={0}>
      <N8AO aoRadius={1.5} distanceFalloff={1} intensity={2.5} quality="high" />
      {/* World pass A (2026-09-13): threshold 0.92->0.78 -- paired with
          BrainCore.tsx's raised idle-state glow floor so the hub core
          blooms even when the GPU is idle, not only when genuinely busy
          ("cyan core glow strong enough to bloom" per the ask). Still
          selective: normal lit MeshStandard/Physical materials (desks,
          rooms, characters) stay well under this even with the new 1.35x
          tone-mapping exposure (UltraCanvasRoot.tsx) -- only
          toneMapped={false} emissive surfaces (core, rings, beacons, screen
          insets, edge strips) are authored with color values that exceed 1. */}
      <Bloom mipmapBlur luminanceThreshold={0.78} luminanceSmoothing={0.25} intensity={0.9} />
      <GodRays sun={coreMeshRef as RefObject<THREE.Mesh>} samples={40} density={0.85} decay={0.92} weight={0.4} exposure={0.3} clampMax={1} blur />
      <ChromaticAberration offset={[0.0005, 0.0005]} />
      <Vignette />
      <SMAA />
    </EffectComposer>
  );
}

export default memo(EffectsStack);
