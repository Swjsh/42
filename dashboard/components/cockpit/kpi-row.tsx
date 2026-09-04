"use client";

import * as React from "react";
import { Line, LineChart, ResponsiveContainer } from "recharts";
import { Wallet, ShieldCheck, Users, ChefHat, Ghost, Gauge } from "lucide-react";
import { MagicCard } from "@/components/ui/magic-card";
import { Badge } from "@/components/ui/badge";
import { AnimatedCircularProgressBar } from "@/components/ui/animated-circular-progress-bar";
import { NumberTicker } from "@/components/ui/number-ticker";
import { BlurFade } from "@/components/ui/blur-fade";
import { ageLabel, fmtUsd, type CockpitPayload } from "@/lib/cockpit-data";
import { cn } from "@/lib/utils";

interface KpiRowProps {
  data: CockpitPayload;
}

function Sparkline({ points }: { points: number[] }) {
  if (!points.length) return null;
  const chartData = points.map((v, i) => ({ i, v }));
  return (
    <div className="h-10 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <defs>
            <linearGradient id="kpi-spark" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="var(--gc-indigo)" />
              <stop offset="55%" stopColor="var(--gc-violet)" />
              <stop offset="100%" stopColor="var(--gc-cyan)" />
            </linearGradient>
          </defs>
          <Line
            type="monotone"
            dataKey="v"
            stroke="url(#kpi-spark)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** AnimatedCircularProgressBar always renders its own rounded `value%` as the
 *  inner label -- there is no prop for custom inner text. Rather than fork
 *  that shared ui/ component (out of scope for this pass), mask its number
 *  with an opaque patch in the card's own background and paint our own
 *  label on top, in the same spot. */
function RingWithLabel({
  value,
  color,
  label,
}: {
  value: number
  color: string
  label: string
}) {
  return (
    <div className="relative size-16 shrink-0">
      <AnimatedCircularProgressBar
        value={value}
        max={100}
        gaugePrimaryColor={color}
        gaugeSecondaryColor="var(--gc-line)"
        className="size-16 text-[13px]"
      />
      <span
        className="absolute inset-0 m-auto flex size-9 items-center justify-center rounded-full bg-[var(--gc-panel-solid)] text-[12px] font-semibold text-[var(--gc-text)]"
        aria-hidden="true"
      >
        {label}
      </span>
      <span className="sr-only">{label}</span>
    </div>
  )
}

function DeltaChip({
  text,
  tone,
}: {
  text: string
  tone: "good" | "bad" | "info" | "amber"
}) {
  const toneClass =
    tone === "good"
      ? "bg-[var(--gc-good)]/20 text-[var(--gc-good)] border-[var(--gc-good)]/40"
      : tone === "bad"
        ? "bg-[var(--gc-bad)]/20 text-[var(--gc-bad)] border-[var(--gc-bad)]/40"
        : tone === "amber"
          ? "bg-[var(--gc-warn)]/20 text-[var(--gc-warn)] border-[var(--gc-warn)]/40"
          : "bg-[var(--gc-indigo)]/20 text-[var(--gc-text)] border-[var(--gc-indigo)]/40"
  return <Badge className={cn("text-[13px] px-2 py-0.5 shrink-0", toneClass)}>{text}</Badge>
}

function StatShell({
  icon: Icon,
  label,
  note,
  delay,
  children,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string;
  note: string;
  delay: number;
  children: React.ReactNode;
}) {
  return (
    <BlurFade delay={delay} inView>
      <MagicCard
        className="rounded-2xl gc-glass p-4 flex flex-col gap-3 h-full transition-transform hover:-translate-y-0.5"
        gradientColor="oklch(0.4 0.08 275)"
        gradientOpacity={0.35}
      >
        <div className="flex items-center gap-2">
          <div className="gc-icon-tile flex h-8 w-8 items-center justify-center rounded-lg shrink-0">
            <Icon size={16} className="text-white" />
          </div>
          <span className="text-[13px] font-medium text-[var(--gc-text-2)] truncate">
            {label}
          </span>
        </div>
        <div className="flex-1 flex flex-col justify-center gap-2 min-h-[3.5rem]">
          {children}
        </div>
        <p className="text-[13px] text-[var(--gc-text-3)] leading-snug">{note}</p>
      </MagicCard>
    </BlurFade>
  );
}

export function KpiRow({ data }: KpiRowProps) {
  // ---- Book ----
  const bookTotal: number | undefined = data?.glass?.equity?.total;
  const pnlSeries: Array<{ cum?: number }> = Array.isArray(data?.glass?.pnl?.series)
    ? data.glass.pnl.series
    : [];
  const sparkPoints = pnlSeries
    .slice(-30)
    .map((p) => (typeof p?.cum === "number" ? p.cum : null))
    .filter((v): v is number => v !== null);
  const week: number | undefined = data?.glass?.pnl?.week;
  const month: number | undefined = data?.glass?.pnl?.month;
  const bookDelta = typeof week === "number" ? week : undefined;

  // ---- Gate ----
  const gateVerdict: string | undefined = data?.gate?.overall_verdict ?? data?.gate?.verdict;
  const isLive = typeof gateVerdict === "string" && gateVerdict.toUpperCase() === "GREEN";
  const perArm: Array<{ ci_lower?: number }> = Array.isArray(data?.gate?.per_arm)
    ? data.gate.per_arm
    : [];
  const ciLowers = perArm
    .map((a) => a?.ci_lower)
    .filter((v): v is number => typeof v === "number");
  const worstCiLower =
    ciLowers.length > 0
      ? Math.min(...ciLowers)
      : typeof data?.gate?.ci?.as_traded?.ci_lower === "number"
        ? data.gate.ci.as_traded.ci_lower
        : undefined;
  const gateRingValue =
    typeof worstCiLower === "number" ? Math.max(0, Math.min(worstCiLower, 1)) * 100 : 0;
  const nDays: number | undefined = data?.gate?.n_days;

  // ---- Agents ----
  const sessions: Array<Record<string, any>> = Array.isArray(data?.army?.sessions)
    ? data.army.sessions
    : [];
  const aliveCount = sessions.filter((s) => s?.alive).length;
  const runningCount = sessions.filter((s) => s?.alive && s?.activity !== "stale").length;
  const totalSessions = sessions.length;
  const agentRingValue = totalSessions > 0 ? (aliveCount / totalSessions) * 100 : 0;
  const peak24h: number | undefined = data?.army?.peak_24h_sessions;

  // ---- Kitchen ----
  const lanes: Array<Record<string, any>> = Array.isArray(data?.lanes?.lanes)
    ? data.lanes.lanes
    : [];
  const kitchenLane = lanes.find((l) => l?.id === "kitchen");
  const kitchenPendingMatch = /(\d+)\s*pending/.exec(String(kitchenLane?.detail ?? ""));
  const kitchenPending: number | undefined = kitchenPendingMatch
    ? Number(kitchenPendingMatch[1])
    : undefined;

  // ---- Shadow ----
  const shadowLive: Array<Record<string, any>> = Array.isArray(data?.shadow?.live)
    ? data.shadow.live
    : [];
  const shadowHeat: string[] = Array.isArray(data?.shadow?.heat) ? data.shadow.heat : [];
  const heatColor = (v: string) =>
    v === "green" ? "var(--gc-good)" : v === "red" ? "var(--gc-bad)" : "var(--gc-line-strong)";
  const shadowPrevCount: number | undefined = data?.shadow?.live_count_7d_ago;
  const shadowDelta =
    typeof shadowPrevCount === "number" ? shadowLive.length - shadowPrevCount : undefined;

  // ---- Budget ----
  const budget = data?.autonomy?.budget;
  const spentUsd: number | undefined = budget?.spent_usd;
  const capUsd: number | undefined = budget?.cap_usd;
  const haveBudgetRing =
    typeof spentUsd === "number" && typeof capUsd === "number" && capUsd > 0;
  const budgetPct = haveBudgetRing ? Math.min(100, (spentUsd! / capUsd!) * 100) : 0;
  const budgetPctRaw = haveBudgetRing ? (spentUsd! / capUsd!) * 100 : undefined;

  return (
    <div className="grid gap-4 grid-cols-2 sm:grid-cols-2 md:grid-cols-3 [@media(min-width:1500px)]:grid-cols-6">
      <StatShell icon={Wallet} label="Book" note={`Updated ${ageLabel(data?.glass?.generated_at)}`} delay={0.02}>
        <div className="flex items-baseline gap-2">
          {typeof bookTotal === "number" ? (
            <span className="flex items-baseline">
              <span className="text-2xl font-semibold gc-grad-text">$</span>
              <NumberTicker value={bookTotal} decimalPlaces={2} className="text-2xl font-semibold gc-grad-text" />
            </span>
          ) : (
            <span className="text-2xl font-semibold text-[var(--gc-text-3)]">NO DATA</span>
          )}
        </div>
        <div className="flex items-center justify-between gap-2">
          {sparkPoints.length > 1 ? (
            <div className="flex-1"><Sparkline points={sparkPoints} /></div>
          ) : (
            <span className="text-[13px] text-[var(--gc-text-3)]">NO DATA</span>
          )}
          {typeof bookDelta === "number" && (
            <Badge
              className={cn(
                "text-[13px] px-2 py-0.5 shrink-0",
                bookDelta >= 0
                  ? "bg-[var(--gc-good)]/20 text-[var(--gc-good)] border-[var(--gc-good)]/40"
                  : "bg-[var(--gc-bad)]/20 text-[var(--gc-bad)] border-[var(--gc-bad)]/40"
              )}
            >
              {fmtUsd(bookDelta)}/wk
            </Badge>
          )}
        </div>
      </StatShell>

      <StatShell
        icon={ShieldCheck}
        label="Gate"
        note={
          typeof worstCiLower === "number" && typeof nDays === "number"
            ? `PF CI-lower ${worstCiLower.toFixed(2)} vs 1.0 bar, ${nDays} days`
            : "NO DATA"
        }
        delay={0.06}
      >
        <div className="flex items-center gap-3">
          <RingWithLabel
            value={gateRingValue}
            color={isLive ? "var(--gc-good)" : "var(--gc-bad)"}
            label={typeof worstCiLower === "number" ? worstCiLower.toFixed(2) : "—"}
          />
          <div className="flex flex-col gap-1.5 items-start">
            <Badge
              className={cn(
                "text-[13px] px-2 py-0.5",
                isLive
                  ? "bg-[var(--gc-good)]/20 text-[var(--gc-good)] border-[var(--gc-good)]/40"
                  : "bg-[var(--gc-bad)]/20 text-[var(--gc-bad)] border-[var(--gc-bad)]/40"
              )}
            >
              {gateVerdict ? (isLive ? "LIVE" : "NOT LIVE") : "NO DATA"}
            </Badge>
            {typeof worstCiLower === "number" && (
              <DeltaChip
                text={`${worstCiLower >= 1.0 ? "+" : ""}${(worstCiLower - 1.0).toFixed(2)} vs 1.0 bar`}
                tone={worstCiLower >= 1.0 ? "good" : "bad"}
              />
            )}
          </div>
        </div>
      </StatShell>

      <StatShell
        icon={Users}
        label="Agents"
        note={totalSessions > 0 ? `${aliveCount} of ${totalSessions} workers active` : "NO DATA"}
        delay={0.1}
      >
        <div className="flex items-center gap-3">
          <RingWithLabel
            value={agentRingValue}
            color="var(--gc-violet)"
            label={totalSessions > 0 ? `${aliveCount}/${totalSessions}` : "—"}
          />
          <div className="flex flex-col gap-1.5 items-start">
            <span className="text-2xl font-semibold text-[var(--gc-text)]">
              {totalSessions > 0 ? `${aliveCount}/${totalSessions}` : "NO DATA"}
            </span>
            {typeof peak24h === "number" && (
              <DeltaChip text={`${runningCount} vs 24h peak ${peak24h}`} tone="info" />
            )}
          </div>
        </div>
      </StatShell>

      <StatShell
        icon={ChefHat}
        label="Kitchen"
        note={kitchenLane?.detail ? String(kitchenLane.detail) : "NO DATA"}
        delay={0.14}
      >
        {kitchenLane ? (
          <div className="flex flex-col gap-1.5">
            <span className="text-2xl font-semibold text-[var(--gc-text)]">
              {kitchenLane.metric ?? "NO DATA"}
            </span>
            <span className="text-[13px] text-[var(--gc-text-3)]">
              {kitchenLane.metric_label ?? "NO DATA"}
            </span>
            {typeof kitchenPending === "number" && (
              <DeltaChip text={`${kitchenPending} pending`} tone="info" />
            )}
          </div>
        ) : (
          <span className="text-2xl font-semibold text-[var(--gc-text-3)]">NO DATA</span>
        )}
      </StatShell>

      <StatShell
        icon={Ghost}
        label="Shadow"
        note={typeof data?.shadow?.say === "string" ? data.shadow.say : "NO DATA"}
        delay={0.18}
      >
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <span className="text-2xl font-semibold text-[var(--gc-text)]">
              {shadowLive.length > 0 ? shadowLive.length : "NO DATA"}
            </span>
            {typeof shadowDelta === "number" && (
              <DeltaChip
                text={`${shadowDelta >= 0 ? "+" : ""}${shadowDelta} vs last week`}
                tone={shadowDelta > 0 ? "good" : shadowDelta < 0 ? "bad" : "info"}
              />
            )}
          </div>
          {shadowHeat.length > 0 ? (
            <div className="flex gap-1">
              {shadowHeat.slice(0, 8).map((h, i) => (
                <span
                  key={i}
                  className="h-2 flex-1 rounded-full"
                  style={{ background: heatColor(h) }}
                />
              ))}
            </div>
          ) : (
            <span className="text-[13px] text-[var(--gc-text-3)]">NO DATA</span>
          )}
        </div>
      </StatShell>

      <StatShell
        icon={Gauge}
        label="Budget"
        note={
          typeof budget?.fires_used === "number" && typeof budget?.fires_cap === "number"
            ? `${budget.fires_used}/${budget.fires_cap} fires used`
            : "NO DATA"
        }
        delay={0.22}
      >
        <div className="flex items-center gap-3">
          <AnimatedCircularProgressBar
            value={budgetPct}
            max={100}
            gaugePrimaryColor="var(--gc-cyan)"
            gaugeSecondaryColor="var(--gc-line)"
            className="size-16 text-[13px] shrink-0"
          />
          <div className="flex flex-col gap-1.5 items-start">
            <span className="text-[15px] font-semibold text-[var(--gc-text)] leading-tight">
              {typeof spentUsd === "number" && typeof capUsd === "number"
                ? `${fmtUsd(spentUsd)} / ${fmtUsd(capUsd, 0)}`
                : "NO DATA"}
            </span>
            {typeof budgetPctRaw === "number" && (
              <DeltaChip
                text={`${budgetPctRaw.toFixed(0)}% of cap`}
                tone={budgetPctRaw >= 75 ? "amber" : "good"}
              />
            )}
          </div>
        </div>
      </StatShell>
    </div>
  );
}
