"use client";

import { useEffect, useRef, useState } from "react";

interface RegistryRow {
  combo_id: string;
  dims: {
    structure?: string;
    strike?: string;
    sizing?: string;
    direction?: string;
    gates?: string;
    exit?: string;
    conditions?: string;
  };
  result?: Record<string, unknown>;
  verdict: string;
  account?: string | null;
  tested_at?: string;
  source?: string;
  notes?: string;
}

interface GrindSummary {
  tested: number;
  PROMOTE: number;
  HOLD: number;
  DEAD: number;
}

interface GrindBanger {
  label: string;
  edge_capture: number;
  wf: number;
  expectancy: number | null;
  n: number | null;
}

interface GrindMatrixCell {
  strike: string;
  stop: string;
  best_ec: number | null;
  verdict: string;
  tested: number;
}

interface FunnelSummary {
  reviewed: number;
  elite: number;
  strong: number;
  robust: number;
  stop: number;
}

interface FunnelElite {
  label: string;
  expectancy: number;
  edge_capture: number;
  qpf: number;
  null_max: number | null;
  edge_over_null: number | null;
}

interface ApiResponse {
  fetched_at: string;
  available: boolean;
  rows: RegistryRow[];
  summary: Record<string, number>;
  grind: GrindSummary;
  grind_total: number;
  grind_bangers: GrindBanger[];
  grind_matrix: GrindMatrixCell[];
  funnel: FunnelSummary;
  funnel_elites: FunnelElite[];
  error?: string;
}

const STRIKES = ["OTM-3", "OTM-2", "OTM-1", "ATM", "ITM-1", "ITM-2"];
const GRIND_STRIKES = ["OTM-4", "OTM-3", "OTM-2", "OTM-1", "ATM", "ITM-1", "ITM-2"];
const GRIND_STOPS = ["-8", "-20", "-50"];

const VERDICT_ORDER = ["PROMOTE", "HOLD", "CHALLENGER", "TO_TEST", "CROSSED_OFF", "DEAD"];

const VERDICT_COLOR: Record<string, string> = {
  PROMOTE: "#1d9e75",
  HOLD: "#ba7517",
  CHALLENGER: "#185fa5",
  TO_TEST: "#7f77dd",
  CROSSED_OFF: "#444441",
  DEAD: "#a32d2d",
};

const VERDICT_RANK: Record<string, number> = {
  PROMOTE: 5,
  HOLD: 4,
  CHALLENGER: 3,
  CROSSED_OFF: 2,
  DEAD: 1,
  TO_TEST: 0,
};

function colKey(r: RegistryRow): string {
  return `${r.dims.gates ?? "?"} · ${r.dims.exit ?? "?"}`;
}

function formatCountdown(ms: number | null): string {
  if (ms === null) return "estimating…";
  if (ms <= 0) return "00:00:00";
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

export default function StrategySpacePage() {
  const [data, setData] = useState<ApiResponse | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string>("");
  const [nowMs, setNowMs] = useState<number>(0);
  // Rate anchor (first observed reviewed count + time) → smoothed ETA to full validation.
  const etaAnchor = useRef<{ reviewed: number; t: number } | null>(null);
  const etaTarget = useRef<number | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const res = await fetch("/api/strategy-space", { cache: "no-store" });
        const json = (await res.json()) as ApiResponse;
        if (active) {
          setData(json);
          setUpdatedAt(new Date().toLocaleTimeString());
        }
      } catch {
        /* keep last good */
      }
    };
    load();
    const t = setInterval(load, 15000);
    return () => {
      active = false;
      clearInterval(t);
    };
  }, []);

  // 1-second ticker so the countdown clock visibly decrements between data polls.
  useEffect(() => {
    setNowMs(Date.now());
    const t = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  // Re-project the funnel-completion target each time fresh data arrives, using the
  // average review rate measured since the first observation (stabilises over time).
  useEffect(() => {
    if (!data?.funnel) return;
    const reviewed = data.funnel.reviewed;
    const total = data.grind_bangers?.length ?? 0;
    if (total <= 0) return;
    if (reviewed >= total) { etaTarget.current = Date.now(); return; }
    const t = Date.now();
    if (!etaAnchor.current || reviewed < etaAnchor.current.reviewed) {
      etaAnchor.current = { reviewed, t };
      return;
    }
    const dRev = reviewed - etaAnchor.current.reviewed;
    const dT = (t - etaAnchor.current.t) / 1000;
    if (dRev > 0 && dT > 5) {
      const rate = dRev / dT; // bangers per second
      etaTarget.current = t + ((total - reviewed) / rate) * 1000;
    }
  }, [data]);

  const funnelDone = !!data?.funnel && (data.grind_bangers?.length ?? 0) > 0
    && data.funnel.reviewed >= (data.grind_bangers?.length ?? 0);
  const countdown = funnelDone
    ? "00:00:00"
    : formatCountdown(etaTarget.current && nowMs ? etaTarget.current - nowMs : null);

  const rows = data?.rows ?? [];
  const gridRows = rows.filter((r) => r.dims.strike && STRIKES.includes(r.dims.strike) && r.dims.exit);
  const cols = Array.from(new Set(gridRows.map(colKey))).sort();
  const newest = rows.reduce((m, r) => (r.tested_at && r.tested_at > m ? r.tested_at : m), "");

  const cell = (strike: string, col: string): RegistryRow | undefined => {
    const matches = gridRows.filter((r) => r.dims.strike === strike && colKey(r) === col);
    return matches.sort((a, b) => (VERDICT_RANK[b.verdict] ?? 0) - (VERDICT_RANK[a.verdict] ?? 0))[0];
  };

  const notable = rows
    .filter((r) => r.verdict === "PROMOTE" || r.verdict === "CHALLENGER" || r.verdict === "TO_TEST")
    .sort((a, b) => (b.tested_at ?? "").localeCompare(a.tested_at ?? ""));

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "#0f1115",
        color: "#e6e6e6",
        fontFamily: "ui-sans-serif, system-ui, sans-serif",
        padding: "24px 28px",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 22, fontWeight: 500, margin: 0 }}>Strategy space</h1>
        <span style={{ fontSize: 13, color: "#8a8d93" }}>
          gates × strike × sizing × structure × conditions — {rows.length} curated · 6 accounts
        </span>
        <div style={{ marginLeft: "auto", textAlign: "right" }}>
          <div style={{ fontSize: 11, color: "#8a8d93", letterSpacing: 0.3 }}>
            {funnelDone ? "validation complete" : "full validation in"}
          </div>
          <div
            style={{
              fontSize: 22,
              fontWeight: 600,
              fontFamily: "ui-monospace, SFMono-Regular, monospace",
              color: funnelDone ? "#1d9e75" : "#d4af37",
              letterSpacing: 1.5,
              lineHeight: 1.1,
            }}
          >
            {funnelDone ? "✓ done" : `⏱ ${countdown}`}
          </div>
          <div style={{ fontSize: 11, color: "#6b6e74", marginTop: 2 }}>
            live · updated {updatedAt || "…"}
          </div>
        </div>
      </div>

      {data?.grind && data.grind.tested > 0 ? (
        <div style={{ background: "#13161c", borderRadius: 8, padding: "12px 16px", margin: "14px 0 4px" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap", fontSize: 13 }}>
            <span style={{ color: "#7f77dd", fontWeight: 500 }}>
              grinding {data.grind.tested.toLocaleString()} / {(data.grind_total ?? 3360).toLocaleString()} combos
            </span>
            <span style={{ marginLeft: "auto", color: "#6b6e74", fontSize: 12 }}>
              {Math.round((data.grind.tested / (data.grind_total ?? 3360)) * 100)}%
            </span>
          </div>
          <div style={{ height: 6, background: "#23262e", borderRadius: 4, marginTop: 10, overflow: "hidden" }}>
            <div
              style={{
                height: "100%",
                width: `${Math.min(100, (data.grind.tested / (data.grind_total ?? 3360)) * 100)}%`,
                background: "#7f77dd",
                transition: "width 0.4s",
              }}
            />
          </div>
        </div>
      ) : null}

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", margin: "18px 0 24px" }}>
        {VERDICT_ORDER.map((v) => (
          <div
            key={v}
            style={{
              background: "#171a20",
              borderRadius: 8,
              padding: "10px 14px",
              minWidth: 96,
              borderLeft: `3px solid ${VERDICT_COLOR[v]}`,
            }}
          >
            <div style={{ fontSize: 11, color: "#8a8d93", letterSpacing: 0.3 }}>{v.replace("_", " ")}</div>
            <div style={{ fontSize: 24, fontWeight: 500 }}>
              {(
                (data?.summary?.[v] ?? 0) +
                (data?.grind && (v === "PROMOTE" || v === "HOLD" || v === "DEAD")
                  ? data.grind[v as "PROMOTE" | "HOLD" | "DEAD"] ?? 0
                  : 0)
              ).toLocaleString()}
            </div>
            {data?.grind && (v === "PROMOTE" || v === "HOLD" || v === "DEAD") && data.grind[v as "PROMOTE" | "HOLD" | "DEAD"] > 0 && (
              <div style={{ fontSize: 10, color: "#6b6e74", marginTop: 2 }}>
                {data?.summary?.[v] ?? 0} curated · {data.grind[v as "PROMOTE" | "HOLD" | "DEAD"]} live
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Live grind matrix: strike × stop, best EC per cell */}
      {data?.grind_matrix && data.grind_matrix.length > 0 && data.grind.tested > 0 && (
        <div style={{ margin: "0 0 24px" }}>
          <h2 style={{ fontSize: 15, fontWeight: 500, margin: "0 0 10px", color: "#c8cace" }}>
            live grind: strike × stop (best edge_capture)
          </h2>
          <div style={{ overflowX: "auto" }}>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: `72px repeat(${GRIND_STOPS.length}, minmax(88px, 1fr))`,
                gap: 4,
              }}
            >
              <div />
              {GRIND_STOPS.map((s) => (
                <div key={s} style={{ fontSize: 11, color: "#8a8d93", textAlign: "center", padding: "2px 4px" }}>
                  stop {s}%
                </div>
              ))}
              {GRIND_STRIKES.map((strike) => (
                <GrindMatrixRow
                  key={strike}
                  strike={strike}
                  stops={GRIND_STOPS}
                  matrix={data.grind_matrix}
                />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Live grind bangers */}
      {data?.grind_bangers && data.grind_bangers.length > 0 && (
        <div style={{ margin: "0 0 24px" }}>
          <h2 style={{ fontSize: 15, fontWeight: 500, margin: "0 0 10px", color: "#1d9e75" }}>
            🔥 bangers ({data.grind_bangers.length})
          </h2>
          <div style={{ display: "grid", gap: 6 }}>
            {data.grind_bangers.slice(0, 8).map((b) => (
              <div
                key={b.label}
                style={{
                  background: "#0d1f16",
                  borderRadius: 8,
                  padding: "10px 14px",
                  borderLeft: "3px solid #1d9e75",
                  display: "flex",
                  gap: 12,
                  alignItems: "baseline",
                  flexWrap: "wrap",
                }}
              >
                <span style={{ fontSize: 10, fontWeight: 600, color: "#1d9e75", minWidth: 64 }}>PROMOTE</span>
                <span style={{ fontSize: 13, fontWeight: 500, fontFamily: "monospace" }}>{b.label}</span>
                <span style={{ fontSize: 12, color: "#6b9fd4" }}>EC={b.edge_capture.toFixed(0)}</span>
                <span style={{ fontSize: 12, color: "#8a8d93" }}>WF={b.wf.toFixed(2)}</span>
                {b.expectancy !== null && (
                  <span style={{ fontSize: 12, color: "#8a8d93" }}>exp=${b.expectancy.toFixed(0)}/tr</span>
                )}
                {b.n !== null && (
                  <span style={{ fontSize: 12, color: "#6b6e74" }}>n={b.n}</span>
                )}
              </div>
            ))}
            {data.grind_bangers.length > 8 && (
              <div style={{ fontSize: 11, color: "#6b6e74", paddingLeft: 4 }}>
                + {data.grind_bangers.length - 8} more bangers (validating below ↓)
              </div>
            )}
          </div>
        </div>
      )}

      {/* Validation funnel: phase 2 → 3 → 4 */}
      {data?.funnel && data.funnel.reviewed > 0 && (
        <div style={{ margin: "0 0 24px" }}>
          <h2 style={{ fontSize: 15, fontWeight: 500, margin: "0 0 10px", color: "#c8cace" }}>
            validation funnel — phase 2 → 3 → 4 ({data.funnel.reviewed.toLocaleString()} of {data.grind_bangers?.length ?? 0} bangers reviewed)
          </h2>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
            {([
              { key: "elite", label: "P4 · ELITE", sub: "beats the null", color: "#d4af37", n: data.funnel.elite },
              { key: "strong", label: "P3 · STRONG", sub: "live-placeable", color: "#1d9e75", n: data.funnel.strong },
              { key: "robust", label: "P2 · ROBUST", sub: "holds quarters", color: "#185fa5", n: data.funnel.robust },
              { key: "stop", label: "STOPPED", sub: "failed P2", color: "#a32d2d", n: data.funnel.stop },
            ] as const).map((t) => (
              <div
                key={t.key}
                style={{
                  background: "#171a20",
                  borderRadius: 8,
                  padding: "10px 16px",
                  minWidth: 120,
                  borderTop: `3px solid ${t.color}`,
                }}
              >
                <div style={{ fontSize: 11, color: t.color, fontWeight: 600, letterSpacing: 0.3 }}>{t.label}</div>
                <div style={{ fontSize: 26, fontWeight: 600 }}>{t.n.toLocaleString()}</div>
                <div style={{ fontSize: 10, color: "#6b6e74", marginTop: 1 }}>{t.sub}</div>
              </div>
            ))}
          </div>
          {data.funnel_elites && data.funnel_elites.length > 0 && (
            <div style={{ display: "grid", gap: 6 }}>
              <div style={{ fontSize: 12, color: "#d4af37", fontWeight: 600, margin: "2px 0 4px" }}>
                🏆 proven elites — beat a coin-flip null even after dropping their 5 best days
              </div>
              {data.funnel_elites.slice(0, 12).map((e) => (
                <div
                  key={e.label}
                  style={{
                    background: "#1c1a10",
                    borderRadius: 8,
                    padding: "10px 14px",
                    borderLeft: "3px solid #d4af37",
                    display: "flex",
                    gap: 12,
                    alignItems: "baseline",
                    flexWrap: "wrap",
                  }}
                >
                  <span style={{ fontSize: 10, fontWeight: 600, color: "#d4af37", minWidth: 56 }}>ELITE</span>
                  <span style={{ fontSize: 13, fontWeight: 500, fontFamily: "monospace" }}>{e.label}</span>
                  <span style={{ fontSize: 12, color: "#1d9e75" }}>exp=${e.expectancy.toFixed(0)}/tr</span>
                  {e.null_max !== null && (
                    <span style={{ fontSize: 12, color: "#8a8d93" }}>
                      vs null max ${e.null_max.toFixed(1)}
                    </span>
                  )}
                  {e.edge_over_null !== null && (
                    <span style={{ fontSize: 12, color: "#6b9fd4" }}>+${e.edge_over_null.toFixed(0)} edge</span>
                  )}
                  <span style={{ fontSize: 11, color: "#6b6e74" }}>EC={e.edge_capture.toFixed(0)}</span>
                </div>
              ))}
              {data.funnel_elites.length > 12 && (
                <div style={{ fontSize: 11, color: "#6b6e74", paddingLeft: 4 }}>
                  + {data.funnel_elites.length - 12} more elites
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <h2 style={{ fontSize: 15, fontWeight: 500, margin: "0 0 10px", color: "#c8cace" }}>
        strike × gate · stop
      </h2>
      {cols.length === 0 ? (
        <p style={{ fontSize: 13, color: "#8a8d93" }}>No grid cells yet — the next grind will populate this.</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: `72px repeat(${cols.length}, minmax(96px, 1fr))`,
              gap: 4,
              minWidth: 72 + cols.length * 100,
            }}
          >
            <div />
            {cols.map((c) => (
              <div key={c} style={{ fontSize: 11, color: "#8a8d93", textAlign: "center", padding: "2px 4px", lineHeight: 1.3 }}>
                {c}
              </div>
            ))}
            {STRIKES.map((s) => (
              <RowCells key={s} strike={s} cols={cols} cell={cell} newest={newest} />
            ))}
          </div>
        </div>
      )}

      <h2 style={{ fontSize: 15, fontWeight: 500, margin: "28px 0 10px", color: "#c8cace" }}>
        live edges &amp; challengers
      </h2>
      <div style={{ display: "grid", gap: 8 }}>
        {notable.map((r) => (
          <div
            key={r.combo_id}
            style={{
              background: "#171a20",
              borderRadius: 8,
              padding: "10px 14px",
              borderLeft: `3px solid ${VERDICT_COLOR[r.verdict]}`,
              display: "flex",
              gap: 12,
              alignItems: "baseline",
              flexWrap: "wrap",
            }}
          >
            <span
              style={{
                fontSize: 10,
                fontWeight: 500,
                color: VERDICT_COLOR[r.verdict],
                minWidth: 78,
              }}
            >
              {r.verdict}
            </span>
            <span style={{ fontSize: 13, fontWeight: 500 }}>{r.combo_id}</span>
            {r.account ? <span style={{ fontSize: 11, color: "#6b9fd4" }}>{r.account}</span> : null}
            <span style={{ fontSize: 12, color: "#8a8d93", flex: "1 1 240px" }}>{r.notes}</span>
          </div>
        ))}
      </div>
    </main>
  );
}

interface GrindMatrixRowProps {
  strike: string;
  stops: string[];
  matrix: GrindMatrixCell[];
}

function GrindMatrixRow({ strike, stops, matrix }: GrindMatrixRowProps) {
  return (
    <>
      <div style={{ display: "flex", alignItems: "center", fontWeight: 500, fontSize: 12 }}>{strike}</div>
      {stops.map((stop) => {
        const cell = matrix.find((c) => c.strike === strike && c.stop === stop);
        const v = cell?.verdict ?? "UNTESTED";
        const ec = cell?.best_ec;
        const tested = cell?.tested ?? 0;
        const bg =
          v === "PROMOTE" ? "#1d9e75" :
          v === "HOLD" ? "#ba7517" :
          v === "DEAD" ? "#a32d2d" :
          "#15171c";
        return (
          <div
            key={stop}
            title={`${strike} stop${stop}% — best EC=${ec?.toFixed(0) ?? "?"} (${tested} tested)`}
            style={{
              background: bg,
              color: v === "UNTESTED" ? "#3a3d43" : "#ffffff",
              borderRadius: 8,
              padding: "10px 4px",
              textAlign: "center",
              fontSize: 12,
              fontWeight: 500,
              position: "relative",
            }}
          >
            {ec !== null && ec !== undefined ? (ec > 0 ? "+" : "") + Math.round(ec) : tested > 0 ? "−" : ""}
            {tested > 0 && (
              <div style={{ fontSize: 9, opacity: 0.7, marginTop: 2 }}>{tested}t</div>
            )}
          </div>
        );
      })}
    </>
  );
}

interface RowCellsProps {
  strike: string;
  cols: string[];
  cell: (strike: string, col: string) => RegistryRow | undefined;
  newest: string;
}

function RowCells({ strike, cols, cell, newest }: RowCellsProps) {
  return (
    <>
      <div style={{ display: "flex", alignItems: "center", fontWeight: 500, fontSize: 13 }}>{strike}</div>
      {cols.map((c) => {
        const r = cell(strike, c);
        const v = r?.verdict;
        const ec = r?.result?.["edge_capture"];
        const isNew = !!r?.tested_at && r.tested_at === newest;
        return (
          <div
            key={c}
            title={r ? `${r.combo_id} — ${v}` : "untested"}
            style={{
              background: v ? VERDICT_COLOR[v] : "#15171c",
              color: v ? "#ffffff" : "#3a3d43",
              borderRadius: 8,
              padding: "12px 4px",
              textAlign: "center",
              fontSize: 12,
              fontWeight: 500,
              outline: isNew ? "2px solid #e6e6e6" : "none",
              outlineOffset: -2,
            }}
          >
            {typeof ec === "number" ? (ec > 0 ? "+" : "") + Math.round(ec) : v ? "·" : ""}
          </div>
        );
      })}
    </>
  );
}
