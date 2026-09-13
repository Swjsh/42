import type { HqApiResponse } from "./types";
import { healthColor, ideaStatusColor } from "./palette";

interface HqFallbackProps {
  data: HqApiResponse | undefined;
  error: unknown;
}

/**
 * Readable 2D panel shown when `webgl2` comes back null/false from the
 * `document.createElement("canvas").getContext("webgl2")` gate in
 * app/hq/page.tsx. Never a blank page: this renders the same server payload
 * the 3D scene would, just as a plain table -- sectors, brain vitals, latest
 * brief, mode badge, all from the one /api/hq response already fetched.
 */
export default function HqFallback({ data, error }: HqFallbackProps) {
  const rows = data?.sectors.rows ?? [];
  const cards = data ? [...data.ideas.cards].reverse().slice(0, 6) : [];

  return (
    <div
      style={{
        minHeight: "100vh",
        width: "100%",
        background: "#03040a",
        color: "#dff3ff",
        fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
        padding: "28px 32px",
        boxSizing: "border-box",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 6 }}>
        <h1 style={{ fontSize: 26, fontWeight: 700, margin: 0, letterSpacing: 1 }}>GAMMA HQ</h1>
        <span
          style={{
            fontSize: 13, padding: "2px 10px", borderRadius: 999,
            background: data?.mode === "gaming" ? "#ffb02033" : "#22ff8833",
            color: data?.mode === "gaming" ? "#ffb020" : "#22ff88",
            border: `1px solid ${data?.mode === "gaming" ? "#ffb020" : "#22ff88"}`,
          }}
        >
          mode: {data?.mode ?? "unknown"}
        </span>
      </div>
      <p style={{ color: "#ffb020", fontSize: 13, marginTop: 0, marginBottom: 20 }}>
        WebGL2 unavailable on this browser -- 3D station disabled. Showing the same live data as a
        plain panel.
      </p>
      {error ? (
        <p style={{ color: "#ff3b3b", fontSize: 13 }}>
          Refresh failed: {error instanceof Error ? error.message : String(error)}
        </p>
      ) : null}

      <section style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 15, color: "#7f93b0", margin: "0 0 8px" }}>Sectors ({rows.length})</h2>
        <div style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "#7f93b0" }}>
                {["lane", "state", "alias", "last evidence", "window P&L", "health"].map((h) => (
                  <th key={h} style={{ padding: "4px 10px", borderBottom: "1px solid #1a2540" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: "8px 10px", color: "#7f93b0" }}>
                    {data?.sectors.say ?? "NO DATA -- sectors not loaded yet"}
                  </td>
                </tr>
              ) : (
                rows.map((r) => (
                  <tr key={r.lane}>
                    <td style={{ padding: "4px 10px", borderBottom: "1px solid #101a2e" }}>{r.lane}</td>
                    <td style={{ padding: "4px 10px", borderBottom: "1px solid #101a2e" }}>{r.state}</td>
                    <td style={{ padding: "4px 10px", borderBottom: "1px solid #101a2e" }}>{r.arm_or_acct_alias}</td>
                    <td style={{ padding: "4px 10px", borderBottom: "1px solid #101a2e" }}>{r.last_evidence_et}</td>
                    <td style={{ padding: "4px 10px", borderBottom: "1px solid #101a2e" }}>
                      {typeof r.window_pnl === "number" ? r.window_pnl.toFixed(2) : r.window_pnl}
                    </td>
                    <td style={{ padding: "4px 10px", borderBottom: "1px solid #101a2e" }}>
                      <span
                        style={{
                          display: "inline-block", width: 9, height: 9, borderRadius: 999,
                          background: healthColor(r.health), marginRight: 6,
                        }}
                      />
                      {r.health}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        <div>
          <h2 style={{ fontSize: 15, color: "#7f93b0", margin: "0 0 8px" }}>Brain vitals</h2>
          <p style={{ fontSize: 13, margin: "2px 0" }}>
            Model: {data?.brainVitals.models[0]?.name ?? "BRAIN IDLE"}
          </p>
          <p style={{ fontSize: 13, margin: "2px 0" }}>
            GPU: {data?.brainVitals.gpu.ok
              ? `${data.brainVitals.gpu.util_pct}% util, ${data.brainVitals.gpu.mem_used_mib}/${data.brainVitals.gpu.mem_total_mib} MiB`
              : "NO DATA"}
          </p>
          <p style={{ fontSize: 13, margin: "2px 0" }}>
            Futures verdict: {data?.extras.futures_verdict ?? "NO DATA"} · Crypto twin:{" "}
            {data?.extras.crypto.last_action ?? "NO DATA"} · Kitchen:{" "}
            {data?.extras.kitchen.idle === false ? "working" : "idle"}
          </p>
        </div>
        <div>
          <h2 style={{ fontSize: 15, color: "#7f93b0", margin: "0 0 8px" }}>Ideas board (newest 6)</h2>
          {cards.length === 0 ? (
            <p style={{ fontSize: 13, color: "#7f93b0" }}>NO DATA -- board is empty</p>
          ) : (
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
              {cards.map((c) => (
                <li key={c.id} style={{ marginBottom: 4, color: ideaStatusColor(c.status) }}>
                  {c.title.length > 70 ? c.title.slice(0, 67) + "..." : c.title}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section style={{ marginTop: 24 }}>
        <h2 style={{ fontSize: 15, color: "#7f93b0", margin: "0 0 8px" }}>Latest brief</h2>
        <p style={{ fontSize: 13, whiteSpace: "pre-wrap", color: "#c3d3ea" }}>
          {data?.brief.text || "NO DATA -- no brief written yet"}
        </p>
      </section>
    </div>
  );
}
