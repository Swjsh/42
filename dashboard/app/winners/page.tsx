"use client";

import { useEffect, useState } from "react";

interface WinnerSetup {
  setup: string;
  best_label: string;
  n_variations: number;
  expectancy: number;
  edge_capture: number;
  qpf: number | null;
  edge_over_null: number | null;
  null_max: number | null;
  wf: number | null;
  n_trades: number | null;
  score: number;
}

interface WinnersResponse {
  available: boolean;
  generated?: string;
  total_p4_elites?: number;
  distinct_setups?: number;
  top_setups: WinnerSetup[];
  caveats: string[];
  p5_survivors?: number | null;
  p5_total?: number | null;
  fetched_at: string;
  error?: string;
}

const GOLD = "#d4af37";
const GREEN = "#1d9e75";
const BLUE = "#6b9fd4";
const INK = "#e8e8ea";
const MUTE = "#8a8d93";

function prettySetup(s: string): { strike: string; stop: string; gate: string; trig: string } {
  // "OTM-1|stop-20|LR1|mt2"
  const [strike = "", stop = "", lr = "", mt = ""] = s.split("|");
  return {
    strike,
    stop: stop.replace("stop", "") + "% stop",
    gate: lr === "LR1" ? "level-reject gate" : "no level gate",
    trig: mt === "mt2" ? "≥2 triggers" : "≥1 trigger",
  };
}

export default function WinnersPage() {
  const [data, setData] = useState<WinnersResponse | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string>("");

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const res = await fetch("/api/winners", { cache: "no-store" });
        const json = (await res.json()) as WinnersResponse;
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

  const top = data?.top_setups ?? [];
  const champ = top[0];

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "radial-gradient(1200px 600px at 70% -10%, #1a1d27 0%, #0f1115 55%)",
        color: INK,
        fontFamily: "ui-sans-serif, system-ui, sans-serif",
        padding: "40px 32px 64px",
      }}
    >
      <div style={{ maxWidth: 960, margin: "0 auto" }}>
        {/* Hero */}
        <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, letterSpacing: 3, color: GOLD, fontWeight: 600 }}>PROJECT GAMMA</span>
          <span style={{ marginLeft: "auto", fontSize: 12, color: MUTE }}>
            {data?.available ? `generated ${data.generated?.replace("T", " ").slice(0, 16)}` : "awaiting funnel…"} · live {updatedAt || "…"}
          </span>
        </div>
        <h1 style={{ fontSize: 38, fontWeight: 700, margin: "6px 0 4px", letterSpacing: -0.5 }}>
          Grind Winners
        </h1>
        <p style={{ fontSize: 15, color: MUTE, margin: "0 0 28px", maxWidth: 640, lineHeight: 1.5 }}>
          Every config below survived all four gates — real OPRA fills, cross-quarter stability,
          live-account placeability, and <strong style={{ color: INK }}>beating a random-entry coin-flip</strong> even
          after dropping its 5 best days. Variations are collapsed to distinct setups.
        </p>

        {!data?.available && (
          <div
            style={{
              background: "#171a20",
              border: "1px dashed #2a2e38",
              borderRadius: 12,
              padding: "28px",
              textAlign: "center",
              color: MUTE,
            }}
          >
            The validation funnel is still running — this report fills in automatically the moment it
            finishes. {data?.error ? <span style={{ opacity: 0.6 }}>({data.error})</span> : null}
          </div>
        )}

        {/* Headline numbers */}
        {data?.available && (
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", margin: "0 0 28px" }}>
            {[
              { n: data.total_p4_elites ?? 0, label: "proven elites (beat null)", color: GOLD },
              { n: data.p5_survivors ?? 0, label: "deploy-grade (P5: plateau + every-Q)", color: "#e0a93a" },
              { n: data.distinct_setups ?? 0, label: "distinct setups", color: GREEN },
              { n: champ ? 1 : 0, label: "dominant edge family", color: BLUE },
            ].map((s) => (
              <div
                key={s.label}
                style={{
                  flex: "1 1 180px",
                  background: "#161922",
                  borderRadius: 12,
                  padding: "18px 20px",
                  borderTop: `3px solid ${s.color}`,
                }}
              >
                <div style={{ fontSize: 34, fontWeight: 700, color: s.color }}>{s.n.toLocaleString()}</div>
                <div style={{ fontSize: 12, color: MUTE, marginTop: 2 }}>{s.label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Deploy candidate hero card */}
        {champ && (
          <div
            style={{
              background: "linear-gradient(135deg, #211d12 0%, #15161d 60%)",
              border: `1px solid ${GOLD}55`,
              borderRadius: 16,
              padding: "24px 26px",
              marginBottom: 30,
              boxShadow: "0 0 40px -18px rgba(212,175,55,0.5)",
            }}
          >
            <div style={{ fontSize: 12, letterSpacing: 2, color: GOLD, fontWeight: 600 }}>
              ★ TOP DEPLOY CANDIDATE
            </div>
            <div style={{ fontSize: 22, fontWeight: 600, fontFamily: "ui-monospace, monospace", margin: "8px 0 4px" }}>
              {champ.best_label}
            </div>
            <div style={{ fontSize: 13, color: MUTE, marginBottom: 18 }}>
              {(() => {
                const p = prettySetup(champ.setup);
                return `${p.strike} · ${p.stop} · ${p.gate} · ${p.trig}`;
              })()}
            </div>
            <div style={{ display: "flex", gap: 26, flexWrap: "wrap" }}>
              {[
                { v: `$${champ.expectancy.toFixed(0)}`, l: "per trade", big: true },
                { v: champ.edge_over_null !== null ? `+$${champ.edge_over_null.toFixed(0)}` : "—", l: "over coin-flip", color: GREEN },
                { v: champ.null_max !== null ? `$${champ.null_max.toFixed(1)}` : "—", l: "null's best" },
                { v: champ.qpf !== null ? `${Math.round(champ.qpf * 100)}%` : "—", l: "quarters positive" },
                { v: champ.wf !== null ? champ.wf.toFixed(2) : "—", l: "walk-forward" },
                { v: champ.edge_capture.toFixed(0), l: "edge capture" },
                { v: `${champ.n_trades ?? "—"}`, l: "trades" },
              ].map((m) => (
                <div key={m.l}>
                  <div style={{ fontSize: m.big ? 32 : 22, fontWeight: 700, color: m.color ?? INK }}>{m.v}</div>
                  <div style={{ fontSize: 11, color: MUTE }}>{m.l}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* The edge family */}
        {champ && (
          <p style={{ fontSize: 14, color: "#b6b9bf", lineHeight: 1.6, margin: "0 0 28px" }}>
            <strong style={{ color: INK }}>The edge:</strong> a <strong style={{ color: INK }}>tight-stop
            directional ride</strong> — the −8%/−20% stop caps the left tail while a big runner (sell most at
            +150%) lets the right tail run. It is the same structure as the live{" "}
            <code style={{ color: BLUE }}>vwap_continuation</code> edge, extended to OTM strikes.
          </p>
        )}

        {/* Ranked table */}
        {top.length > 0 && (
          <>
            <h2 style={{ fontSize: 16, fontWeight: 600, margin: "0 0 12px" }}>
              Ranked distinct setups
            </h2>
            <div style={{ display: "grid", gap: 6, marginBottom: 30 }}>
              {top.map((s, i) => (
                <div
                  key={s.setup}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "28px 1fr auto auto auto auto",
                    gap: 14,
                    alignItems: "center",
                    background: i === 0 ? "#1c1a10" : "#161922",
                    borderLeft: `3px solid ${i === 0 ? GOLD : "#2a2e38"}`,
                    borderRadius: 8,
                    padding: "11px 16px",
                  }}
                >
                  <span style={{ fontSize: 13, color: i === 0 ? GOLD : MUTE, fontWeight: 600 }}>{i + 1}</span>
                  <span style={{ fontSize: 13, fontFamily: "ui-monospace, monospace" }}>{s.setup.replace(/\|/g, " · ")}</span>
                  <span style={{ fontSize: 13, color: GREEN, fontWeight: 600 }}>${s.expectancy.toFixed(0)}/tr</span>
                  <span style={{ fontSize: 12, color: BLUE }}>
                    {s.edge_over_null !== null ? `+$${s.edge_over_null.toFixed(0)} vs null` : ""}
                  </span>
                  <span style={{ fontSize: 12, color: MUTE }}>
                    {s.qpf !== null ? `${Math.round(s.qpf * 100)}% Q` : ""}
                  </span>
                  <span style={{ fontSize: 11, color: "#6b6e74" }}>{s.n_variations} var</span>
                </div>
              ))}
            </div>
          </>
        )}

        {/* Honest verdict */}
        {data?.caveats && data.caveats.length > 0 && (
          <div
            style={{
              background: "#1a1710",
              border: "1px solid #4a3c1a",
              borderRadius: 12,
              padding: "20px 22px",
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 600, color: "#e0a93a", marginBottom: 10 }}>
              ⚠ Before any of these go live — what they still owe
            </div>
            <ul style={{ margin: 0, paddingLeft: 18, color: "#c3b894", fontSize: 13, lineHeight: 1.7 }}>
              {data.caveats.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
            <div style={{ fontSize: 12, color: MUTE, marginTop: 12, lineHeight: 1.6 }}>
              Translation: this is a <strong style={{ color: INK }}>strong lead to forward-paper-validate</strong>,
              not a config to flip live on an in-sample search. Honest beats hopeful.
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
