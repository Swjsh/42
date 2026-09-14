"use client";

import type { CSSProperties } from "react";
import { Html } from "@react-three/drei";
import type { PersonaState } from "@/lib/personas";
import type { AgentBehavior } from "./Agent";
import { personaStatusColor, rosterEvidenceText } from "./palette";

interface PersonaModuleProps {
  position: [number, number, number];
  persona: PersonaState;
  behavior: AgentBehavior;
}

/**
 * Inner persona ring "desk" -- deliberately slim: no floor/screen/desk/
 * point-light meshes (the org-chart layer nested inside the lane
 * departments it runs shouldn't visually compete with them). Just a
 * nameplate Html + the persona's Agent (rendered as a scene-root sibling by
 * Scene.tsx, per the same positioning fix the lane modules needed -- see
 * palette.ts#localToWorld). Lit entirely by the scene's existing
 * hemisphere/directional lights -- zero new point lights (item 12 of the
 * Company Mode spec).
 */
export default function PersonaModule({ position, persona, behavior }: PersonaModuleProps) {
  const color = personaStatusColor(persona.status);

  return (
    <Html position={[position[0], 1.05, position[2]]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
      <div className="hq-beam" style={{ "--beam-color": color, borderRadius: 8 } as CSSProperties}>
        <div
          style={{
            position: "relative", overflow: "hidden",
            fontFamily: "system-ui, sans-serif", color: "#dff3ff",
            background: "rgba(3,4,10,0.75)", padding: "3px 12px", borderRadius: 7,
            whiteSpace: "nowrap", textAlign: "center",
          }}
        >
          <span key={persona.status} className="hq-shine" />
          <div style={{ fontSize: 28, fontWeight: 800, lineHeight: 1.2 }}>
            {persona.emoji} {persona.name}
          </div>
          <div style={{ fontSize: 26, color: "#7f93b0" }}>
            {rosterEvidenceText(persona.lastFireISO)}
            {behavior === "alert" && <span style={{ color: "#ff3b3b", fontWeight: 800 }}> · ⚠</span>}
          </div>
        </div>
      </div>
    </Html>
  );
}
