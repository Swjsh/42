"use client";

import type { RefObject } from "react";
import { EffectComposer, Bloom, SMAA, Vignette, ChromaticAberration, N8AO, DepthOfField, GodRays } from "@react-three/postprocessing";
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
 * perceptible ChromaticAberration, moderate N8AO, subtle DepthOfField, and
 * GodRays scoped to the ONE hero light source (brain core) -- never a
 * second GodRays pass on anything else, per the brief's explicit warning
 * that a second pass isn't worth its cost (fake additive cones are the
 * queued alternative for secondary sources, not built this pass).
 */
export default function EffectsStack({ coreMeshRef }: EffectsStackProps) {
  return (
    <EffectComposer enableNormalPass multisampling={0}>
      <N8AO aoRadius={1.5} distanceFalloff={1} intensity={2.5} quality="high" />
      <Bloom mipmapBlur luminanceThreshold={0.92} luminanceSmoothing={0.2} intensity={0.8} />
      <DepthOfField focusDistance={0.02} focalLength={0.05} bokehScale={2.5} />
      <GodRays sun={coreMeshRef as RefObject<THREE.Mesh>} samples={40} density={0.85} decay={0.92} weight={0.4} exposure={0.3} clampMax={1} blur />
      <ChromaticAberration offset={[0.0005, 0.0005]} />
      <Vignette />
      <SMAA />
    </EffectComposer>
  );
}
