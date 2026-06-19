"use client";

import React, { useEffect, useState } from "react";
import type {
  LoopState,
  TodayBias,
  CurrentPosition,
  CircuitBreaker,
  KitchenStatus,
  DecisionTick,
  DialogueFile,
} from "@/lib/state";

interface StateData {
  fetched_at?: string;
  today?: string;
  loopState?: LoopState | null;
  loopStateBold?: LoopState | null;
  todayBias?: TodayBias | null;
  positionSafe?: CurrentPosition | null;
  positionBold?: CurrentPosition | null;
  circuitBreaker?: CircuitBreaker | null;
  circuitBreakerBold?: CircuitBreaker | null;
  kitchenStatus?: KitchenStatus | null;
  dialogue?: DialogueFile | null;
  recentTicks?: DecisionTick[];
  tradesToday?: number;
}

interface Props {
  data: StateData | undefined;
}

// ─── Design tokens ────────────────────────────────────────────────────────────
const MONO = "'JetBrains Mono','IBM Plex Mono',ui-monospace,Menlo,monospace";
const G = {
  bg: "#020c05",
  card: "rgba(4,18,9,0.96)",
  border: "rgba(0,180,70,0.18)",
  borderHover: "rgba(0,200,80,0.35)",
  green: "#00d46a",
  greenDim: "#00a852",
  red: "#ff4455",
  redDim: "#c93040",
  yellow: "#ffc340",
  purple: "#a78bfa",
  dim: "#2a4a35",
  label: "#3d6b4d",
  text: "#d8f0e0",
  textBright: "#edfaef",
};

// ─── Helpers ──────────────────────────────────────────────────────────────────
function pnlColor(v: number | null) {
  if (v === null) return G.dim;
  return v > 0 ? G.green : v < 0 ? G.red : G.dim;
}
function fmt$(v: number | null, dec = 0) {
  if (v === null) return "—";
  return `${v >= 0 ? "+" : "−"}$${Math.abs(v).toFixed(dec)}`;
}
function fmtPct(v: number | null) {
  if (v === null) return "";
  return `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(1)}%`;
}

const LBL: React.CSSProperties = {
  fontFamily: MONO,
  fontSize: "clamp(9px, 0.62vw, 11px)",
  fontWeight: 700,
  letterSpacing: "0.20em",
  textTransform: "uppercase",
  color: G.label,
};

// ─── Root ─────────────────────────────────────────────────────────────────────
export default function TradingFloor({ data }: Props) {
  return (
    <div style={{
      position: "relative",
      width: "100%",
      height: "100%",
      backgroundColor: G.bg,
      backgroundImage: "url(/trade-floor.png)",
      backgroundSize: "100% 100%",
      fontFamily: MONO,
    }}>
      <div style={{ position: "absolute", inset: 0, background: "rgba(1,6,3,0.88)", zIndex: 1 }} />
      <div style={{
        position: "absolute", inset: 0, zIndex: 2,
        display: "flex", flexDirection: "column",
        padding: "1% 1.5%", gap: "0.8%",
      }}>
        <Header data={data} />
        <MainCards data={data} />
        <Footer data={data} />
      </div>
    </div>
  );
}

// ─── Header ───────────────────────────────────────────────────────────────────
function Header({ data }: Props) {
  const ls = data?.loopState;
  const dialogue = data?.dialogue;
  const hbActive = dialogue?.agents?.heartbeat?.active ?? false;
  const anyActive = Object.values(dialogue?.agents ?? {}).some((a) => a.active);
  const dot = hbActive ? G.green : anyActive ? G.yellow : G.dim;
  const label = hbActive ? "LIVE" : anyActive ? "ACTIVE" : "IDLE";

  const spy = ls?.spy?.last ?? null;
  const vix = ls?.vix_cache?.value ?? null;
  const vixDir = ls?.vix_cache?.dir;
  const vixArrow = vixDir === "rising" ? " ↑" : vixDir === "falling" ? " ↓" : "";
  const vixCol = vixDir === "rising" ? G.red : vixDir === "falling" ? G.green : G.yellow;
  const ribbon = ls?.ribbon;
  const rbCol = ribbon?.stack === "BULL" ? G.green : ribbon?.stack === "BEAR" ? G.red : G.yellow;
  const mode = ls?.current_mode;
  const modeCol = mode === "HOT" ? G.red : mode === "BASE" ? G.yellow : G.dim;

  const [time, setTime] = useState("--:--:--");
  useEffect(() => {
    const tick = () => setTime(
      new Date().toLocaleTimeString("en-US", { hour12: false, timeZone: "America/New_York" })
    );
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{
      display: "flex", alignItems: "center",
      padding: "0 1.2em",
      height: "clamp(36px, 9%, 52px)",
      background: "rgba(3,14,7,0.95)",
      border: `1px solid ${G.border}`,
      borderRadius: 6,
      flexShrink: 0,
      gap: "1.6em",
    }}>
      {/* Status */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.5em" }}>
        <span style={{ color: dot, fontSize: "0.7em", filter: hbActive ? `drop-shadow(0 0 4px ${G.green})` : "none" }}>●</span>
        <span style={{ ...LBL, color: dot, letterSpacing: "0.14em" }}>{label}</span>
      </div>

      <Divider />

      {/* SPY */}
      <Metric label="SPY" value={spy !== null ? spy.toFixed(2) : "—"} valueStyle={{ fontSize: "clamp(18px, 1.6vw, 26px)", fontWeight: 900, color: G.textBright, fontVariantNumeric: "tabular-nums" }} />

      <Divider />

      {/* VIX */}
      <Metric label="VIX" value={vix !== null ? `${vix.toFixed(2)}${vixArrow}` : "—"} valueStyle={{ fontSize: "clamp(16px, 1.4vw, 22px)", fontWeight: 800, color: vixCol, fontVariantNumeric: "tabular-nums" }} />

      <Divider />

      {/* Ribbon */}
      {ribbon && (
        <>
          <Metric
            label="RIBBON"
            value={ribbon.stack}
            valueStyle={{ fontSize: "clamp(14px, 1.25vw, 20px)", fontWeight: 900, color: rbCol, letterSpacing: "0.04em" }}
            sub={`${ribbon.spread_cents}¢`}
          />
          <Divider />
        </>
      )}

      {/* Mode */}
      {mode && (
        <>
          <Metric label="MODE" value={mode} valueStyle={{ fontSize: "clamp(13px, 1.1vw, 18px)", fontWeight: 800, color: modeCol }} />
          <Divider />
        </>
      )}

      {/* Clock */}
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "baseline", gap: "0.5em" }}>
        <span style={{ ...LBL }}>ET</span>
        <span style={{ fontSize: "clamp(18px, 1.6vw, 26px)", fontWeight: 900, color: G.yellow, fontVariantNumeric: "tabular-nums", letterSpacing: "0.03em" }}>
          {time}
        </span>
      </div>
    </div>
  );
}

function Divider() {
  return <span style={{ width: 1, height: "55%", background: "rgba(0,160,60,0.18)", flexShrink: 0 }} />;
}

function Metric({ label, value, valueStyle, sub }: { label: string; value: string; valueStyle: React.CSSProperties; sub?: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
      <span style={LBL}>{label}</span>
      <div style={{ display: "flex", alignItems: "baseline", gap: "0.35em" }}>
        <span style={{ fontFamily: MONO, ...valueStyle }}>{value}</span>
        {sub && <span style={{ fontFamily: MONO, fontSize: "clamp(9px, 0.62vw, 11px)", color: G.dim }}>{sub}</span>}
      </div>
    </div>
  );
}

// ─── Main Cards ───────────────────────────────────────────────────────────────
function MainCards({ data }: Props) {
  return (
    <div style={{ flex: 1, display: "flex", gap: "1%", minHeight: 0 }}>
      <MarketCard data={data} />
      <AccountCard
        label="GAMMA-SAFE"
        accentColor={G.green}
        cb={data?.circuitBreaker}
        pos={data?.positionSafe}
        bodPending={data?.circuitBreaker?.SAFE_EQUITY_BOD_PENDING}
      />
      <AccountCard
        label="GAMMA-BOLD"
        accentColor={G.purple}
        cb={data?.circuitBreakerBold}
        pos={data?.positionBold}
      />
    </div>
  );
}

// ─── Market Card ──────────────────────────────────────────────────────────────
function MarketCard({ data }: Props) {
  // Live ribbon state — updates every heartbeat tick
  const ribbon = data?.loopState?.ribbon ?? null;
  const ribbonStack = ribbon?.stack ?? null;
  const ribbonSpread = ribbon?.spread_cents ?? null;
  const isRibBull = ribbonStack === "BULL";
  const isRibBear = ribbonStack === "BEAR";
  const liveColor = isRibBull ? G.green : isRibBear ? G.red : G.yellow;
  const liveLabel = ribbonStack ?? "—";
  const liveArrow = isRibBull ? "▲" : isRibBear ? "▼" : "◆";
  const spreadThin = ribbonSpread !== null && ribbonSpread < 15;
  const spreadColor = ribbonSpread === null ? G.dim : ribbonSpread >= 30 ? G.green : ribbonSpread >= 15 ? G.yellow : G.red;

  // Premarket bias — static morning assessment, context only
  const bias = data?.todayBias?.bias ?? null;
  const biasLabel = bias ? bias.toUpperCase() : "PENDING";
  const biasColor = bias === "bullish" ? G.green : bias === "bearish" ? G.red : G.yellow;

  const setup = data?.loopState?.developing_setup ?? null;
  const htf = data?.loopState?.htf_15m?.stack ?? null;
  const noTradeWindows = data?.todayBias?.news_calendar?.no_trade_window ?? [];
  const events = data?.todayBias?.news_calendar?.events_today ?? [];
  const nextEvent = events.find((e) => e.severity === "high") ?? events[0] ?? null;

  return (
    <div style={{
      flex: 1,
      background: G.card,
      border: `1px solid ${G.border}`,
      borderTop: `2px solid ${liveColor}`,
      borderRadius: 6,
      display: "flex",
      flexDirection: "column",
      padding: "5% 6%",
      gap: "0.9em",
      overflow: "hidden",
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={LBL}>RIBBON — LIVE</span>
        {bias && (
          <span style={{ fontSize: "clamp(7px, 0.55vw, 9px)", color: biasColor, border: `1px solid ${biasColor}40`, background: `${biasColor}10`, padding: "1px 6px", borderRadius: 3, fontFamily: MONO, fontWeight: 700, letterSpacing: "0.08em" }}>
            BIAS {biasLabel}
          </span>
        )}
      </div>

      {/* Live ribbon display */}
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: "0.4em",
        background: `${liveColor}12`,
        border: `1px solid ${liveColor}33`,
        borderRadius: 5,
        padding: "0.5em 0.7em",
      }}>
        <span style={{ fontSize: "clamp(28px, 2.8vw, 46px)", fontWeight: 900, color: liveColor, lineHeight: 1, fontFamily: MONO }}>
          {liveArrow}
        </span>
        <span style={{ fontSize: "clamp(24px, 2.4vw, 40px)", fontWeight: 900, color: liveColor, letterSpacing: "0.02em", fontFamily: MONO }}>
          {liveLabel}
        </span>
        <div style={{ marginLeft: "auto", display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
          <span style={{ fontSize: "clamp(15px, 1.3vw, 22px)", fontWeight: 900, color: spreadColor, fontFamily: MONO, fontVariantNumeric: "tabular-nums" }}>
            {ribbonSpread !== null ? `${ribbonSpread}¢` : "—"}
          </span>
          {spreadThin && (
            <span style={{ fontSize: "clamp(7px, 0.55vw, 9px)", color: G.red, fontFamily: MONO, fontWeight: 700, letterSpacing: "0.1em" }}>
              ⚠ CHOPPY
            </span>
          )}
        </div>
      </div>

      {/* HTF context */}
      {htf && (
        <div style={{ display: "flex", alignItems: "center", gap: "0.5em" }}>
          <span style={LBL}>15M</span>
          <span style={{ fontSize: "clamp(11px, 0.95vw, 15px)", fontWeight: 700, color: htf === "BULL" ? G.green : G.red, fontFamily: MONO }}>
            {htf}
          </span>
        </div>
      )}

      <div style={{ flex: 1 }} />

      {/* Setup developing */}
      {setup ? (
        <div style={{
          padding: "0.6em 0.8em",
          background: `${G.yellow}0f`,
          border: `1px solid ${G.yellow}40`,
          borderRadius: 4,
        }}>
          <div style={{ ...LBL, color: G.yellow, marginBottom: 5 }}>⚡ SETUP DEVELOPING</div>
          <div style={{ fontSize: "clamp(11px, 0.95vw, 15px)", fontWeight: 700, color: G.yellow, fontFamily: MONO }}>
            {setup.name.replace(/_/g, " ")}
          </div>
        </div>
      ) : (
        <div style={{ fontSize: "clamp(9px, 0.72vw, 11px)", color: G.dim, fontStyle: "italic", fontFamily: MONO }}>
          no setup developing
        </div>
      )}

      {/* No-trade window */}
      {noTradeWindows.length > 0 && (
        <div style={{
          padding: "0.6em 0.8em",
          background: `${G.red}0f`,
          border: `1px solid ${G.red}40`,
          borderRadius: 4,
        }}>
          <div style={{ ...LBL, color: G.red, marginBottom: 4 }}>⛔ NO-TRADE WINDOW</div>
          <div style={{ fontSize: "clamp(12px, 1.0vw, 16px)", fontWeight: 700, color: G.red, fontFamily: MONO }}>
            {noTradeWindows[0].start_et} – {noTradeWindows[0].end_et}
          </div>
          <div style={{ fontSize: "clamp(8px, 0.62vw, 10px)", color: G.redDim, marginTop: 2, fontFamily: MONO }}>
            {noTradeWindows[0].event}
          </div>
        </div>
      )}

      {/* Next event if no block */}
      {noTradeWindows.length === 0 && nextEvent && (
        <div style={{ fontSize: "clamp(9px, 0.72vw, 11px)", color: nextEvent.severity === "high" ? G.yellow : G.dim, fontFamily: MONO }}>
          next: {nextEvent.time_et} — {nextEvent.event.slice(0, 30)}
        </div>
      )}
    </div>
  );
}

// ─── Account Card ─────────────────────────────────────────────────────────────
interface AccountCardProps {
  label: string;
  accentColor: string;
  cb?: CircuitBreaker | null;
  pos?: CurrentPosition | null;
  bodPending?: boolean;
}

function AccountCard({ label, accentColor, cb, pos, bodPending }: AccountCardProps) {
  const startEq = cb?.starting_equity_today ?? cb?.equity_start_of_day ?? null;
  const curEq = cb?.current_equity ?? cb?.equity_current ?? null;
  const pnl = startEq !== null && curEq !== null ? curEq - startEq : null;
  const pnlPct = pnl !== null && startEq ? (pnl / startEq) * 100 : null;
  const tripped = cb?.tripped ?? false;

  const drawdown = pnl !== null && pnl < 0 ? -pnl : 0;
  const limitDollars = cb?.daily_loss_limit_dollars ?? (startEq ? startEq * 0.5 : 1);
  const killPct = Math.min(drawdown / limitDollars, 1);
  const killColor = killPct >= 0.8 ? G.red : killPct >= 0.5 ? G.yellow : G.green;

  const posOpen = pos?.status === "open" || pos?.status === "open_runner";
  const pnlC = pnlColor(pnl);

  return (
    <div style={{
      flex: 1,
      background: G.card,
      border: `1px solid ${tripped ? G.red + "60" : G.border}`,
      borderTop: `2px solid ${tripped ? G.red : accentColor}`,
      borderRadius: 6,
      display: "flex",
      flexDirection: "column",
      padding: "5% 6%",
      gap: "1.1em",
    }}>
      {/* Account header */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ ...LBL, color: accentColor }}>{label}</span>
        {bodPending && <Badge color={G.yellow}>BOD PENDING</Badge>}
        {tripped && <Badge color={G.red}>TRIPPED</Badge>}
      </div>

      {/* Equity */}
      <div>
        <div style={LBL}>EQUITY</div>
        <div style={{ fontSize: "clamp(26px, 2.6vw, 44px)", fontWeight: 900, color: G.textBright, fontVariantNumeric: "tabular-nums", lineHeight: 1.1, fontFamily: MONO }}>
          ${curEq !== null ? curEq.toFixed(0) : startEq !== null ? startEq.toFixed(0) : "—"}
        </div>
      </div>

      {/* P&L */}
      <div style={{
        padding: "0.55em 0.75em",
        background: pnl === null ? "transparent" : pnl >= 0 ? `${G.green}10` : `${G.red}10`,
        border: `1px solid ${pnl === null ? G.border : pnl >= 0 ? G.green + "28" : G.red + "28"}`,
        borderRadius: 4,
      }}>
        <div style={{ ...LBL, marginBottom: 4 }}>TODAY&apos;S P&amp;L</div>
        <div style={{ display: "flex", alignItems: "baseline", gap: "0.5em" }}>
          <span style={{ fontSize: "clamp(22px, 2.1vw, 36px)", fontWeight: 900, color: pnlC, fontVariantNumeric: "tabular-nums", fontFamily: MONO, lineHeight: 1 }}>
            {fmt$(pnl)}
          </span>
          <span style={{ fontSize: "clamp(13px, 1.1vw, 18px)", fontWeight: 700, color: pnlC, opacity: 0.8, fontFamily: MONO }}>
            {fmtPct(pnlPct)}
          </span>
        </div>
      </div>

      {/* Kill switch */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
          <div style={LBL}>DAILY LIMIT</div>
          <span style={{ fontSize: "clamp(9px, 0.68vw, 11px)", color: killColor, fontFamily: MONO, fontVariantNumeric: "tabular-nums" }}>
            ${drawdown.toFixed(0)} / ${limitDollars.toFixed(0)}
          </span>
        </div>
        {/* Bar with danger zone markers */}
        <div style={{ position: "relative", height: 10, background: "rgba(255,255,255,0.06)", borderRadius: 5, overflow: "visible" }}>
          <div style={{
            height: "100%",
            width: `${(killPct * 100).toFixed(1)}%`,
            background: `linear-gradient(90deg, ${G.greenDim}, ${killColor})`,
            borderRadius: 5,
            transition: "width 0.8s ease",
          }} />
          {/* 50% marker */}
          <div style={{ position: "absolute", left: "50%", top: -2, width: 1, height: 14, background: "rgba(255,255,255,0.15)" }} />
          {/* 80% marker */}
          <div style={{ position: "absolute", left: "80%", top: -2, width: 1, height: 14, background: "rgba(255,100,80,0.35)" }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 3 }}>
          <span style={{ fontSize: "clamp(7px, 0.55vw, 9px)", color: G.dim, fontFamily: MONO }}>0%</span>
          <span style={{ fontSize: "clamp(7px, 0.55vw, 9px)", color: G.dim, fontFamily: MONO, marginLeft: "46%" }}>50%</span>
          <span style={{ fontSize: "clamp(7px, 0.55vw, 9px)", color: G.redDim, fontFamily: MONO }}>LIMIT</span>
        </div>
      </div>

      <div style={{ flex: 1 }} />

      {/* Position */}
      <div style={{ borderTop: `1px solid ${G.border}`, paddingTop: "0.8em" }}>
        <div style={{ ...LBL, marginBottom: 5 }}>POSITION</div>
        {posOpen ? (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ color: G.green, fontSize: "0.7em", filter: `drop-shadow(0 0 3px ${G.green})` }}>●</span>
            <span style={{ fontSize: "clamp(12px, 1.05vw, 17px)", fontWeight: 700, color: G.green, fontFamily: MONO }}>
              {pos?.symbol ?? "OPEN"}
            </span>
            {pos?.qty && (
              <span style={{ fontSize: "clamp(10px, 0.82vw, 13px)", color: G.dim, fontFamily: MONO }}>
                ×{pos.qty}
              </span>
            )}
          </div>
        ) : (
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <span style={{ color: G.dim, fontSize: "0.65em" }}>●</span>
            <span style={{ fontSize: "clamp(12px, 1.05vw, 17px)", fontWeight: 600, color: G.dim, fontFamily: MONO }}>
              FLAT
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

function Badge({ children, color }: { children: React.ReactNode; color: string }) {
  return (
    <span style={{
      fontSize: "clamp(7px, 0.55vw, 9px)",
      color,
      border: `1px solid ${color}50`,
      background: `${color}12`,
      padding: "2px 6px",
      borderRadius: 3,
      fontFamily: MONO,
      fontWeight: 700,
      letterSpacing: "0.1em",
    }}>
      {children}
    </span>
  );
}

// ─── Footer ───────────────────────────────────────────────────────────────────
const ACTION_COLOR: Record<string, string> = {
  ENTER_BULL: "#00d46a", ENTER_BEAR: "#ff4455",
  EXIT_TP1: "#22d3ee", EXIT_RUNNER: "#22d3ee",
  EXIT_STOP: "#ff4455", EXIT_TIME: "#f97316",
  HOLD_RUNNER: "#60a5fa", HOLD_DEV: "#ffc340",
  HOLD: "#2a4a35", SKIP_NEWS: "#ffc340",
  TRIPPED: "#ff4455",
  // Watcher-fleet observability fires (no order placed) — muted slate "observer"
  // tone, distinct from the ENTER/EXIT action palette. Legacy ORB/FBW aliases
  // are emitted in place of WATCH_ONLY for two watchers; same color.
  WATCH_ONLY: "#7c8aa0", ORB_WOULD_ENTER: "#7c8aa0", FBW_WOULD_ENTER: "#7c8aa0",
};

function Footer({ data }: Props) {
  const ticks = data?.recentTicks ?? [];
  const last = ticks[ticks.length - 1] ?? null;
  const trades = data?.tradesToday ?? 0;
  const kitchen = data?.kitchenStatus;
  const kAlive = kitchen?.daemon_alive ?? false;
  const kPending = kitchen?.queue_summary?.by_status?.pending ?? 0;
  const macroWins = data?.todayBias?.news_calendar?.no_trade_window ?? [];
  const events = data?.todayBias?.news_calendar?.events_today ?? [];
  const nextEvent = events.find((e) => e.severity === "high") ?? events[0] ?? null;

  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      padding: "0 1.2em",
      height: "clamp(34px, 9%, 50px)",
      background: "rgba(3,14,7,0.95)",
      border: `1px solid ${G.border}`,
      borderRadius: 6,
      flexShrink: 0,
      gap: 0,
    }}>
      <FooterBlock label="LAST TICK" grow>
        {last ? (
          <div style={{ display: "flex", alignItems: "center", gap: "0.6em" }}>
            <span style={{ fontSize: "clamp(9px, 0.72vw, 11px)", color: G.dim }}>{last.time_et}</span>
            <span style={{ fontSize: "clamp(9px, 0.72vw, 11px)", fontWeight: 700, color: last.account_id === "bold" ? G.purple : G.green }}>
              {last.account_id === "bold" ? "BLD" : "SAF"}
            </span>
            <span style={{ fontSize: "clamp(11px, 0.96vw, 15px)", fontWeight: 800, color: ACTION_COLOR[last.action] ?? G.text }}>
              {last.action}
            </span>
          </div>
        ) : (
          <span style={{ fontSize: "clamp(10px, 0.82vw, 13px)", color: G.dim, fontStyle: "italic" }}>—</span>
        )}
      </FooterBlock>

      <FooterDivider />

      <FooterBlock label="TRADES TODAY">
        <span style={{ fontSize: "clamp(16px, 1.4vw, 22px)", fontWeight: 900, color: trades > 0 ? G.green : G.dim, fontVariantNumeric: "tabular-nums" }}>
          {trades}
        </span>
      </FooterBlock>

      <FooterDivider />

      <FooterBlock label="KITCHEN">
        <div style={{ display: "flex", alignItems: "center", gap: "0.5em" }}>
          <span style={{ color: kAlive ? G.green : G.red, fontSize: "0.65em", filter: kAlive ? `drop-shadow(0 0 3px ${G.green})` : "none" }}>●</span>
          <span style={{ fontSize: "clamp(14px, 1.2vw, 19px)", fontWeight: 800, color: G.text, fontVariantNumeric: "tabular-nums" }}>
            {kPending}
          </span>
          <span style={{ fontSize: "clamp(9px, 0.72vw, 11px)", color: G.dim }}>pending</span>
        </div>
      </FooterBlock>

      <FooterDivider />

      <FooterBlock label="MACRO" grow>
        {macroWins.length > 0 ? (
          <div style={{
            display: "inline-flex", alignItems: "center", gap: "0.4em",
            background: `${G.red}12`, border: `1px solid ${G.red}45`,
            padding: "2px 10px", borderRadius: 4,
          }}>
            <span style={{ fontSize: "clamp(11px, 0.92vw, 14px)", fontWeight: 800, color: G.red }}>
              ⛔ {macroWins[0].start_et}–{macroWins[0].end_et} BLOCKED
            </span>
          </div>
        ) : nextEvent ? (
          <span style={{ fontSize: "clamp(10px, 0.82vw, 13px)", color: nextEvent.severity === "high" ? G.yellow : G.dim }}>
            {nextEvent.time_et} — {nextEvent.event.slice(0, 32)}
          </span>
        ) : (
          <span style={{ fontSize: "clamp(10px, 0.82vw, 13px)", color: G.dim }}>clear</span>
        )}
      </FooterBlock>
    </div>
  );
}

function FooterDivider() {
  return <div style={{ width: 1, height: "55%", background: "rgba(0,160,60,0.15)", flexShrink: 0, margin: "0 1.2em" }} />;
}

function FooterBlock({ label, children, grow }: { label: string; children: React.ReactNode; grow?: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 3, flex: grow ? 1 : "0 0 auto", overflow: "hidden" }}>
      <span style={LBL}>{label}</span>
      {children}
    </div>
  );
}
