"use client";

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
 */
export default function PmremEnvironment() {
  return <Environment files={KIT_PATHS.hdri} background={false} />;
}
