"use client";

import { useEffect } from "react";
import { useThree } from "@react-three/fiber";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

/**
 * Ultra tier only (HQ-ULTRA-TIER-BRIEF.md section 3): a procedural PMREM
 * environment so MeshStandard/MeshPhysical materials get real reflections
 * instead of flat unlit color. `RoomEnvironment` is a JS-BUILT room (a
 * handful of emissive planes arranged in a box, from three's own examples)
 * -- not an image file, so this is zero bundled bytes and zero network
 * requests. drei's `<Environment preset="...">` was explicitly ruled out
 * (fetches an HDRI from a pmndrs CDN at runtime, violating the standing
 * no-network-requests rule); this is the compliant procedural alternative
 * the brief names. Sets `scene.environment` only, never
 * `scene.background` -- the SkyDome stays the visible backdrop, this just
 * feeds reflections/lighting response on physical materials.
 */
export default function PmremEnvironment() {
  const { gl, scene } = useThree();

  useEffect(() => {
    const pmrem = new THREE.PMREMGenerator(gl);
    const envTexture = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = envTexture;
    pmrem.dispose();
    return () => {
      if (scene.environment === envTexture) scene.environment = null;
      envTexture.dispose();
    };
  }, [gl, scene]);

  return null;
}
