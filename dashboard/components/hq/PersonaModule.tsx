"use client";

import type { CSSProperties } from "react";
import { Html } from "@react-three/drei";
import type { PersonaState } from "@/lib/personas";
import type { AgentBehavior } from "./Agent";
import type { PersonaAudit } from "./types";
import { auditVerdictColor, personaStatusColor, rosterEvidenceText } from "./palette";

interface PersonaModuleProps {
  position: [number, number, number];
  persona: PersonaState;
  behavior: AgentBehavior;
  /** Company audit row (commit 58d0b9c6, coordinator 2026-09-13: "the
   * roster must show ghosts as ghosts") -- undefined when /api/hq predates
   * the audit or the audit script failed for this persona; renders no
   * badge rather than a fake one. */
  audit?: PersonaAudit;
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
export default function PersonaModule({ position, persona, behavior, audit }: PersonaModuleProps) {
  const color = personaStatusColor(persona.status);
  const auditColor = auditVerdictColor(audit?.verdict);

  // Pass F (2026-09-13, coordinator's real-monitor capture, item 4:
  // "persona plaques should hang above their bay, lane labels lower"): y
  // 1.05->1.9 -- was sitting near ground/desk level, close enough to other
  // near-camera content (lane bay labels, the core's own plaques) to read
  // as colliding in screen-space from the ring's typical camera angle. 1.9
  // clears a standing 1.8-unit-tall character's own head, closer to
  // StationModule's own doorway-nameplate convention (2.3) without
  // matching it exactly -- personas are the CLOSER inner ring, so a
  // slightly lower plaque than the outer bay labels still reads as "above
  // its own desk" while staying visually separated by height from the
  // outer ring.
  return (
    <Html position={[position[0], 1.9, position[2]]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
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
          <div style={{ fontSize: 28, fontWeight: 800, lineHeight: 1.2, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
            <span>{persona.emoji} {persona.name}</span>
            {/* Audit badge (coordinator 2026-09-13) -- a second, SEPARATE
                verdict from the status dot the plaque's own beam-color
                already carries: status is "is it firing," audit is "is the
                work real," and they can disagree (a ghost). No hover in-
                scene (Html here has pointerEvents:none, matching every
                other in-scene label) -- the full works-evidence line lives
                on Hud.tsx's roster panel's own badge title instead. */}
            {audit && (
              <span style={{ fontSize: 15, fontWeight: 800, color: "#03040a", background: auditColor, borderRadius: 4, padding: "1px 5px" }}>
                {audit.verdict[0]}
              </span>
            )}
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
