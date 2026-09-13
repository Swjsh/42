/**
 * Browser-side WebGL capability probe (client only -- never import from server code).
 * Used by the LAN kiosk view of /station so the TV reports WebGL1/WebGL2 + a frame
 * rate sample by itself (J 2026-09-13: "typing in the TV is a pain").
 */
export interface WebGlProbeResult {
  webgl1: boolean;
  webgl2: boolean;
  renderer: string;
  fps: number;
  width: number;
  height: number;
  dpr: number;
  ua: string;
}

function rendererOf(gl: WebGLRenderingContext | WebGL2RenderingContext | null): string {
  if (!gl) return "";
  try {
    const ext = gl.getExtension("WEBGL_debug_renderer_info");
    const r = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    return typeof r === "string" ? r : "";
  } catch {
    return "";
  }
}

/** Resolves after `sampleMs` of requestAnimationFrame ticks with the measured frame rate. */
export function probeWebGl(sampleMs = 2000): Promise<WebGlProbeResult> {
  return new Promise((resolve) => {
    const c1 = document.createElement("canvas");
    const gl1 = (c1.getContext("webgl") || c1.getContext("experimental-webgl")) as WebGLRenderingContext | null;
    const c2 = document.createElement("canvas");
    const gl2 = c2.getContext("webgl2");
    const base = {
      webgl1: !!gl1,
      webgl2: !!gl2,
      renderer: rendererOf(gl2 ?? gl1),
      width: window.innerWidth,
      height: window.innerHeight,
      dpr: window.devicePixelRatio || 1,
      ua: navigator.userAgent,
    };
    let frames = 0;
    const start = performance.now();
    const tick = (now: number) => {
      frames += 1;
      if (now - start < sampleMs) {
        requestAnimationFrame(tick);
        return;
      }
      resolve({ ...base, fps: Math.round((frames * 1000) / Math.max(1, now - start)) });
    };
    requestAnimationFrame(tick);
  });
}
