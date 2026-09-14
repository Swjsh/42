"use client";

import { useEffect, useMemo } from "react";
import { useGLTF } from "@react-three/drei";
import * as THREE from "three";
import { createScreenCanvas, drawScreenLines, type ScreenLine } from "./palette";

interface DeskScreenProps {
  /** The screen GLB's path -- passed in (never imported from SetKit.tsx
   * here) specifically to avoid a circular import: SetKit.tsx's own
   * DeskCluster is this component's main caller, so SetKit -> DeskScreen ->
   * SetKit would form a cycle that breaks `KIT_PATHS`' top-level
   * initialization order (ESM resolves imports before any module body runs
   * -- a real, verified failure mode, not a style preference). Every
   * current caller passes `KIT_PATHS.furniture.computerScreen`; preloading
   * is SetKit.tsx's job (it already preloads that exact path). */
  path: string;
  position: [number, number, number];
  rotation?: [number, number, number];
  scale?: number;
  title: string | null;
  lines: ScreenLine[];
}

/**
 * A real `computer-screen.glb` mesh (Kenney Space Station Kit) with a LIVE
 * canvas-rendered texture instead of the flat atlas tint every other
 * KitProp instance gets (SetKit.tsx#tintObjectMaterials) -- Pass B's own
 * ask: "real canvas-rendered textures (256x160, regenerated on data change
 * only) on kit computer-screen meshes". Safe to replace this mesh's
 * material wholesale (a plain emissive `MeshBasicMaterial`+`map`, matching
 * every other "active display" surface in this scene -- StationModule's
 * screen-wall, BrainCore's rings -- rather than the imported PBR material,
 * which would read dim/lighting-dependent for something meant to look like
 * an active display): `computer-screen.glb` was parsed directly this
 * session (its raw JSON chunk, not assumed) and is ONE mesh / ONE primitive
 * / ONE material, so this never touches any other kit piece's shared
 * cached material -- each mounted instance clones the scene first, same
 * discipline as tintObjectMaterials.
 *
 * The canvas only redraws when `title`+`lines`' CONTENT changes (the
 * effect's own dep array below is a joined content string, not the `lines`
 * array reference -- a fresh array with identical text every render, which
 * `sceneData`'s stable-reference discipline does NOT guarantee down to this
 * prop, still produces the SAME string and skips the redraw). Never
 * per-frame -- real 2D canvas drawing is not free even on an idle GPU.
 */
export default function DeskScreen({ path, position, rotation = [0, Math.PI, 0], scale = 1, title, lines }: DeskScreenProps) {
  const { scene } = useGLTF(path, false);
  const cloned = useMemo(() => scene.clone(true), [scene]);
  const { canvas, texture } = useMemo(() => createScreenCanvas(), []);
  const material = useMemo(() => new THREE.MeshBasicMaterial({ map: texture, toneMapped: false }), [texture]);

  useEffect(() => {
    cloned.traverse((obj) => {
      if (obj instanceof THREE.Mesh) obj.material = material;
    });
  }, [cloned, material]);

  const contentKey = `${title ?? ""}::${lines.map((l) => `${l.text}|${l.color ?? ""}|${l.size ?? ""}`).join("~")}`;
  useEffect(() => {
    drawScreenLines(canvas, texture, title, lines);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canvas, texture, contentKey]);

  useEffect(() => () => {
    texture.dispose();
    material.dispose();
  }, [texture, material]);

  return <primitive object={cloned} position={position} rotation={rotation} scale={scale} />;
}
