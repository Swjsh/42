"use client";

import { memo } from "react";
import { Environment } from "@react-three/drei";
import { KIT_PATHS } from "./SetKit";

/**
 * Ultra tier only (HQ-ULTRA-TIER-BRIEF.md section 3): a real environment map
 * so MeshStandard/MeshPhysical materials get real reflections instead of
 * flat unlit color. drei's `<Environment preset="...">` was explicitly
 * ruled out (fetches an HDRI from a pmndrs CDN at runtime, violating the
 * standing no-network-requests rule) -- `files=` loads LOCAL bytes only, so
 * the bundled CC0 Poly Haven HDRI (public/hq-assets/, 20938f4c) is
 * compliant: zero network requests, and (per the ultra-tier brief's own
 * "bundled upgrade" note) a real starfield reflection beats the earlier
 * procedural `RoomEnvironment` (a JS-built empty box -- fine as a stopgap,
 * but there is no reason to keep faking it once the real asset is on disk).
 * `background={false}` is load-bearing -- SkyDome stays the only visible
 * backdrop; this component only ever feeds `scene.environment` (reflections/
 * lighting response), matching the file's own prior contract. Suspends
 * while the 1.7MB file loads -- caught by <Canvas>'s own built-in internal
 * Suspense boundary (confirmed by reading react-three-fiber's shipped
 * source this session, not assumed), so no extra boundary is needed here.
 *
 * World pass A REAL bug fix (2026-09-13, root-caused via mechanical
 * bisection + reading drei's own Environment.js source, not guessed): its
 * internal `EnvironmentCube`/`EnvironmentMap` components run
 * `React.useLayoutEffect(() => setEnvProps(...))` with NO DEPENDENCY ARRAY
 * -- it tears down (`scene.environment = oldenv`) and reapplies on EVERY
 * single re-render of this component's parent, unconditionally. Scene.tsx
 * re-renders on every SWR poll (~60s in kiosk mode); without memoization
 * here, that's a full environment-texture teardown/reapply cycle every
 * poll, racing the SAME class of "component reads a ref/scene-graph node
 * mid-teardown" crash this task already found and fixed once in
 * EffectsStack.tsx (GodRays). Confirmed via mechanical bisection this
 * session: a clean single-tab load stays crash-free for ~50-60s, then the
 * "Cannot read properties of null (reading 'parent')" error starts
 * repeating every frame -- the timing lines up exactly with kiosk mode's
 * first SWR poll, not with initial asset loading. `React.memo` here is
 * trivially safe (this component's props -- none, `files`/`background` are
 * both file-local constants -- never change), and stops the churn outright.
 */
function PmremEnvironment() {
  return <Environment files={KIT_PATHS.hdri} background={false} />;
}

export default memo(PmremEnvironment);
