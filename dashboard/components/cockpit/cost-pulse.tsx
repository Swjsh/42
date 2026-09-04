"use client";

import * as React from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Dot,
  ResponsiveContainer,
  XAxis,
} from "recharts";
import { Badge } from "@/components/ui/badge";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { NumberTicker } from "@/components/ui/number-ticker";
import { ageLabel, fmtUsd, type CockpitPayload } from "@/lib/cockpit-data";

type CostDay = { day: string; cost_usd: number; fires: number; drained: number; regressions: number };
type CostPulseData = {
  ok?: boolean;
  days?: CostDay[];
  total_usd?: number;
  last?: { day: string; cost_usd: number; fires: number };
  say?: string;
  stamp_et?: string;
};
type Budget = {
  verdict?: string;
  reason?: string;
  fires_used?: number;
  fires_cap?: number;
  spent_usd?: number;
  cap_usd?: number;
  checked_at?: string;
};

const chartConfig = {
  cost_usd: { label: "Cost", color: "var(--gc-cyan)" },
};

function shortDay(iso: string): string {
  const t = new Date(iso + "T00:00:00");
  if (Number.isNaN(t.getTime())) return iso;
  return t.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function CostPulse({ data }: { data: CockpitPayload }) {
  const costpulse = data?.costpulse as CostPulseData | undefined;
  const budget = data?.autonomy?.budget as Budget | undefined;

  const hasChart = !!costpulse?.ok && !!costpulse.days?.length;
  const days = React.useMemo(() => (hasChart ? costpulse!.days!.slice(-14) : []), [hasChart, costpulse]);

  const total14 = days.reduce((acc, d) => acc + (d.cost_usd ?? 0), 0);
  const avgPerDay = days.length ? total14 / days.length : 0;
  const regressions14 = days.reduce((acc, d) => acc + (d.regressions ?? 0), 0);

  const spent = budget?.spent_usd;
  const cap = budget?.cap_usd;
  const verdict = budget?.verdict;
  const proceed = verdict === "PROCEED";

  const lastDay = days.length ? days[days.length - 1] : undefined;

  return (
    <div className="cockpit gc-glass gc-glow relative flex h-full flex-col rounded-2xl p-4">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="gc-icon-tile flex h-7 w-7 items-center justify-center rounded-lg text-[13px] font-semibold">
            $
          </span>
          <h3 className="text-[14px] font-semibold" style={{ color: "var(--gc-text)" }}>
            Cost pulse
          </h3>
        </div>
        {verdict ? (
          <Badge
            variant="outline"
            className="text-[13px]"
            style={{
              color: proceed ? "var(--gc-good)" : "var(--gc-warn)",
              borderColor: proceed ? "var(--gc-good)" : "var(--gc-warn)",
            }}
          >
            {verdict}
          </Badge>
        ) : (
          <Badge variant="outline" className="text-[13px]" style={{ color: "var(--gc-text-3)" }}>
            NO DATA
          </Badge>
        )}
      </div>

      <div className="mb-1 flex items-baseline gap-2">
        {spent !== undefined && cap !== undefined ? (
          <>
            <span className="gc-grad-text text-[26px] font-semibold tabular-nums">
              $<NumberTicker value={spent} decimalPlaces={2} className="gc-grad-text" />
            </span>
            <span className="text-[14px]" style={{ color: "var(--gc-text-3)" }}>
              / {fmtUsd(cap, 0)}
            </span>
          </>
        ) : (
          <span className="text-[26px] font-semibold" style={{ color: "var(--gc-text-3)" }}>
            NO DATA
          </span>
        )}
        {budget?.fires_used !== undefined && budget?.fires_cap !== undefined && (
          <Badge variant="secondary" className="ml-1 text-[13px]" style={{ color: "var(--gc-text-2)" }}>
            {budget.fires_used}/{budget.fires_cap} fires
          </Badge>
        )}
      </div>

      <div className="min-h-0 flex-1">
        {hasChart ? (
          <ChartContainer config={chartConfig} className="h-full w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={days} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="gc-cost-fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--gc-violet)" stopOpacity={0.55} />
                    <stop offset="100%" stopColor="var(--gc-violet)" stopOpacity={0} />
                  </linearGradient>
                  <filter id="gc-line-glow" x="-40%" y="-100%" width="180%" height="300%">
                    <feGaussianBlur stdDeviation="2.4" result="blur" />
                    <feMerge>
                      <feMergeNode in="blur" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>
                </defs>
                <CartesianGrid stroke="var(--gc-line)" vertical={false} />
                <XAxis
                  dataKey="day"
                  tickFormatter={shortDay}
                  stroke="var(--gc-text-3)"
                  tickLine={false}
                  axisLine={false}
                  fontSize={13}
                  minTickGap={24}
                />
                <ChartTooltip
                  content={
                    <ChartTooltipContent
                      labelFormatter={(v) => shortDay(String(v))}
                      formatter={(value, name) => {
                        if (name === "cost_usd") return [fmtUsd(Number(value)), "Cost"];
                        return [String(value), String(name)];
                      }}
                    />
                  }
                />
                <Area
                  type="monotone"
                  dataKey="cost_usd"
                  stroke="var(--gc-cyan)"
                  strokeWidth={2.5}
                  fill="url(#gc-cost-fill)"
                  filter="url(#gc-line-glow)"
                  dot={false}
                  activeDot={{ r: 4, fill: "var(--gc-cyan)", stroke: "var(--gc-panel-solid)", strokeWidth: 2 }}
                />
                {lastDay && (
                  <Area
                    type="monotone"
                    dataKey="cost_usd"
                    stroke="none"
                    fill="none"
                    dot={(props: { cx?: number; cy?: number; index?: number }) => {
                      if (props.index !== days.length - 1 || props.cx === undefined || props.cy === undefined) {
                        return <React.Fragment key={`d-${props.index}`} />;
                      }
                      return (
                        <g key="last-point">
                          <circle cx={props.cx} cy={props.cy} r={7} fill="var(--gc-cyan)" opacity={0.25}>
                            <animate attributeName="r" values="7;12;7" dur="1.8s" repeatCount="indefinite" />
                            <animate attributeName="opacity" values="0.3;0;0.3" dur="1.8s" repeatCount="indefinite" />
                          </circle>
                          <Dot cx={props.cx} cy={props.cy} r={4} fill="var(--gc-cyan)" stroke="var(--gc-panel-solid)" strokeWidth={2} />
                        </g>
                      );
                    }}
                  />
                )}
              </AreaChart>
            </ResponsiveContainer>
          </ChartContainer>
        ) : (
          <div className="flex h-full items-center justify-center text-[14px]" style={{ color: "var(--gc-text-3)" }}>
            NO DATA
          </div>
        )}
      </div>

      <div className="mt-2 grid grid-cols-3 gap-2 border-t pt-2 text-[13px]" style={{ borderColor: "var(--gc-line)" }}>
        <Stat label="14d total" value={hasChart ? fmtUsd(total14) : "NO DATA"} />
        <Stat label="Avg/day" value={hasChart ? fmtUsd(avgPerDay) : "NO DATA"} />
        <Stat label="Regressions" value={hasChart ? String(regressions14) : "NO DATA"} />
      </div>

      <div className="mt-2 flex items-center justify-between gap-3 text-[13px]" style={{ color: "var(--gc-text-3)" }}>
        <span className="truncate">{costpulse?.say ?? budget?.reason ?? "NO DATA"}</span>
        <span className="shrink-0">{ageLabel(costpulse?.stamp_et ?? budget?.checked_at)}</span>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span style={{ color: "var(--gc-text-3)" }}>{label}</span>
      <span className="font-semibold tabular-nums" style={{ color: "var(--gc-text)" }}>
        {value}
      </span>
    </div>
  );
}
