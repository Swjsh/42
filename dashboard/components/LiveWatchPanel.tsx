"use client";

import React from "react";
import useSWR from "swr";
import type {
  LiveWatchFile,
  LiveWatchArm,
  LiveWatchPosition,
  TrendlineWatchFile,
} from "@/app/api/live-watch/route";

// ─── WS7 LIVE WATCH panel ─────────────────────────────────────────────────────
// "J should never have to ask: are we in a trade / what's it doing."
// Renders automation/state/live-watch.json via /api/live-watch. Read-only.
// Design tokens mirror KitchenPanel/TradingFloor's pixel-art palette.
const MONO = "'JetBrains Mono','IBM Plex Mono',ui-monospace,Menlo,monospace";
const G = {
  card: "rgba(4,18,9,0.96)",
  border: "rgba(0,180,70,0.18)",
  green: "#00d46a",
  greenDim: "#00a852",
  red: "#ff4455",
  yellow: "#ffc340",
  cyan: "#22d3ee",
  dim: "#2a4a35",
  label: "#3d6b4d",
  text: "#d8f0e0",
  textBright: "#edfaef",
};

const LBL: React.CSSProperties = {
  fontFamily: MONO,
  fontSize: 9,
  fontWeight: 700,
  letterSpacing: "0.20em",
  textTransform: "uppercase",
  color: G.label,
};

interface ApiResponse {
  fetched_at: string;
  available: boolean;
  watch: LiveWatchFile | null;
}

const fetcher = (url: string): Promise<ApiResponse> =>
  fetch(url, { cache: "no-store" }).then((r) => r.json());

function minutesSince(isoEt: string | null | undefined): number | null {
  if (!isoEt) return null;
  const t = Date.parse(isoEt);
  if (Number.isNaN(t)) return null;
  return Math.floor((Date.now() - t) / 60000);
}

function pct(v: number | null | undefined): string {
  return typeof v === "number" ? `${v > 0 ? "+" : ""}${v.toFixed(1)}%` : "—";
}

function usd(v: number | null | undefined): string {
  return typeof v === "number" ? `${v >= 0 ? "+" : "-"}$${Math.abs(v).toFixed(0)}` : "—";
}

function num(v: number | null | undefined): string {
  return typeof v === "number" ? String(v) : "—";
}

function firstPosition(p: LiveWatchArm["position"]): LiveWatchPosition | null {
  if (Array.isArray(p)) return p[0] ?? null;
  return p ?? null;
}

function PositionBlock({ pos }: { pos: LiveWatchPosition }) {
  const pnl = pos.unrealized_pnl_pct;
  const pnlColor = typeof pnl === "number" ? (pnl >= 0 ? G.green : G.red) : G.dim;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <div style={{ fontFamily: MONO, fontSize: 10, color: G.textBright }}>
        {pos.symbol ?? "?"} <span style={{ color: G.cyan }}>x{num(pos.qty)}</span>
      </div>
      <div style={{ fontFamily: MONO, fontSize: 10, color: G.text }}>
        @{num(pos.entry_premium)} → {num(pos.mid)}{" "}
        <span style={{ color: pnlColor, fontWeight: 700 }}>
          {pct(pnl)} / {usd(pos.unrealized_pnl_usd)}
        </span>
      </div>
      <div style={{ fontFamily: MONO, fontSize: 9, color: G.text }}>
        stop {num(pos.stop_premium)} ({pct(pos.dist_to_stop_pct)} away
        {pos.stop_mode === "structure" && typeof pos.dist_to_stop_level_pts === "number"
          ? `, lvl ${pos.dist_to_stop_level_pts > 0 ? "+" : ""}${pos.dist_to_stop_level_pts}pt`
          : ""}
        , {pos.stop_mode ?? "?"})
      </div>
      <div style={{ fontFamily: MONO, fontSize: 9, color: G.text }}>
        {pos.tp_phase ?? "TP"} {num(pos.tp_target_premium)} ({pct(pos.dist_to_tp_pct)} away)
        {" · "}HWM {num(pos.hwm_premium)} ({pct(pos.hwm_gain_pct)})
        {pos.profit_lock_armed ? " · LOCK" : ""}
      </div>
      <div style={{ fontFamily: MONO, fontSize: 9, color: G.label }}>
        {typeof pos.time_in_trade_min === "number"
          ? `${pos.time_in_trade_min.toFixed(0)}m in trade`
          : "time in trade unknown"}
      </div>
    </div>
  );
}

function ArmRow({ armId, arm }: { armId: string; arm: LiveWatchArm }) {
  const pos = firstPosition(arm.position);
  const inTrade = arm.in_trade === true && pos !== null;
  const ksTripped = arm.kill_switch?.tripped === true;
  const degraded = (arm.status ?? "ok") !== "ok";
  const dec = arm.last_decision;
  return (
    <div
      style={{
        border: `1px solid ${ksTripped ? G.red : G.border}`,
        background: G.card,
        borderRadius: 4,
        padding: "5px 7px",
        display: "flex",
        flexDirection: "column",
        gap: 3,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ ...LBL, color: G.text }}>{arm.display_name ?? armId}</span>
        <span
          style={{
            fontFamily: MONO,
            fontSize: 8,
            fontWeight: 700,
            padding: "1px 5px",
            borderRadius: 3,
            color: inTrade ? "#04120a" : G.label,
            background: inTrade ? G.green : "transparent",
            border: inTrade ? "none" : `1px solid ${G.dim}`,
          }}
        >
          {inTrade ? "IN TRADE" : "FLAT"}
        </span>
      </div>
      {inTrade && pos ? (
        <PositionBlock pos={pos} />
      ) : (
        <div style={{ fontFamily: MONO, fontSize: 9, color: G.text }}>
          {dec?.verdict ?? "no decision yet"}
          {typeof dec?.age_min === "number" ? (
            <span style={{ color: G.label }}> · {dec.age_min.toFixed(0)}m ago</span>
          ) : null}
          {dec?.reason ? (
            <div style={{ color: G.label, fontSize: 8, marginTop: 1 }}>
              {String(dec.reason).slice(0, 70)}
            </div>
          ) : null}
        </div>
      )}
      {ksTripped ? (
        <div style={{ fontFamily: MONO, fontSize: 9, color: G.red, fontWeight: 700 }}>
          KILL SWITCH TRIPPED{arm.kill_switch?.reason ? `: ${arm.kill_switch.reason}` : ""}
        </div>
      ) : null}
      {degraded ? (
        <div style={{ fontFamily: MONO, fontSize: 8, color: G.yellow }}>
          {String(arm.status).slice(0, 80)}
        </div>
      ) : null}
    </div>
  );
}

// ─── WS8→WS7 read-side merge: trendline context (2026-08-01, Next-Twelve #11) ─────────
// Read-only render of watch.trendlines, injected additively by /api/live-watch (never
// part of live-watch.json on disk, never touches setup/scripts/live_watch.py — see that
// route's WS8→WS7 READ-SIDE MERGE comment). Doctrine: visibility-only (WS8 closed both
// entry-path NULLs 2026-08-01) — this section informs, never gates a trade decision.
function TrendlinesBlock({ tl }: { tl: TrendlineWatchFile | null | undefined }) {
  if (!tl || (tl.n_active ?? 0) === 0) return null;
  const near = tl.nearest_active;
  const brk = tl.last_break;
  return (
    <div
      style={{
        border: `1px solid ${G.border}`,
        background: G.card,
        borderRadius: 4,
        padding: "5px 7px",
        display: "flex",
        flexDirection: "column",
        gap: 2,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={LBL}>TRENDLINES</span>
        <span style={{ fontFamily: MONO, fontSize: 8, color: G.label }}>
          {tl.n_active}/{tl.n_total ?? "?"} active
        </span>
      </div>
      {near ? (
        <div style={{ fontFamily: MONO, fontSize: 9, color: G.text }}>
          nearest: {near.kind ?? "?"} [{near.flavor ?? "?"}] {num(near.current_value)}
          {typeof near.distance_dollars === "number"
            ? ` (${near.distance_dollars.toFixed(2)} ${near.side ?? ""})`
            : ""}
          {near.status ? ` · ${near.status}` : ""}
        </div>
      ) : null}
      {brk?.summary || brk?.level ? (
        <div style={{ fontFamily: MONO, fontSize: 8, color: G.yellow }}>
          last break: {brk.kind ?? "?"} [{brk.flavor ?? "?"}] {num(brk.level)}
          {brk.ts_et ? ` @ ${brk.ts_et.slice(11, 16)}` : ""}
        </div>
      ) : null}
    </div>
  );
}

export default function LiveWatchPanel() {
  const { data } = useSWR<ApiResponse>("/api/live-watch", fetcher, {
    refreshInterval: 5000,
    revalidateOnFocus: true,
  });

  const watch = data?.watch ?? null;
  const closed = watch?.market_state === "CLOSED";
  const ageMin = minutesSince(watch?.written_at_et);
  // The watcher rewrites every minute during RTH — an RTH snapshot older than 3 min
  // means the watcher itself is down. Visibility honesty: say so, loudly.
  const stale = !closed && watch !== null && ageMin !== null && ageMin > 3;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 5,
        border: `1px solid ${G.border}`,
        background: "rgba(3,14,7,0.9)",
        borderRadius: 6,
        padding: 8,
        overflowY: "auto",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={LBL}>LIVE WATCH</span>
        <span
          style={{
            fontFamily: MONO,
            fontSize: 8,
            fontWeight: 700,
            color: stale ? G.red : closed ? G.label : G.green,
          }}
        >
          {watch === null
            ? "NO DATA"
            : stale
              ? `STALE ${ageMin}m`
              : closed
                ? "CLOSED"
                : `RTH${typeof watch.spy?.last === "number" ? ` · SPY ${watch.spy.last}` : ""}`}
        </span>
      </div>
      {watch === null ? (
        <div style={{ fontFamily: MONO, fontSize: 9, color: G.label }}>
          live-watch.json not written yet (watcher runs 09:25–16:05 ET weekdays)
        </div>
      ) : closed ? (
        <div style={{ fontFamily: MONO, fontSize: 9, color: G.label }}>
          market closed — all quiet · last write {watch.written_at_et?.slice(11, 16) ?? "?"} ET
        </div>
      ) : (
        Object.entries(watch.arms ?? {}).map(([armId, arm]) => (
          <ArmRow key={armId} armId={armId} arm={arm} />
        ))
      )}
      {watch ? <TrendlinesBlock tl={watch.trendlines} /> : null}
      {watch && !closed && (watch.errors?.length ?? 0) > 0 ? (
        <div style={{ fontFamily: MONO, fontSize: 8, color: G.yellow }}>
          {watch.errors!.slice(0, 3).join(" · ").slice(0, 120)}
        </div>
      ) : null}
    </div>
  );
}
