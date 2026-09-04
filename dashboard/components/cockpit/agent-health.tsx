"use client"

import * as React from "react"
import { Activity, Bot, CircleDashed, Cpu, Zap } from "lucide-react"

import { ageLabel, type CockpitPayload } from "@/lib/cockpit-data"
import { Badge } from "@/components/ui/badge"
import { AnimatedCircularProgressBar } from "@/components/ui/animated-circular-progress-bar"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

type Lane = {
  id: string
  label: string
  kind?: string
  state?: string
  detail?: string
  doing?: string
  last_at?: string
  metric?: string
  metric_label?: string
  tasks?: Record<string, string>
}

const STATE_COLOR: Record<string, string> = {
  WORKING: "var(--gc-good)",
  BROKEN: "var(--gc-bad)",
  IDLE: "var(--gc-text-3)",
  STALE: "var(--gc-warn)",
}

function stateColor(state?: string): string {
  return STATE_COLOR[(state || "").toUpperCase()] ?? "var(--gc-warn)"
}

function kindIcon(kind?: string) {
  const k = (kind || "").toLowerCase()
  if (k.includes("live") || k.includes("engine")) return Zap
  if (k.includes("shadow")) return CircleDashed
  if (k.includes("research") || k.includes("kitchen")) return Cpu
  return Bot
}

/** Ready/total from a lane's tasks map -- {name: "Ready" | ...}. */
function readyFraction(tasks?: Record<string, string>): { ready: number; total: number } {
  if (!tasks) return { ready: 0, total: 0 }
  const entries = Object.values(tasks)
  const ready = entries.filter((v) => v === "Ready").length
  return { ready, total: entries.length }
}

function LaneRow({ lane }: { lane: Lane }) {
  const Icon = kindIcon(lane.kind)
  const color = stateColor(lane.state)
  const { ready, total } = readyFraction(lane.tasks)
  const pct = total > 0 ? Math.round((ready / total) * 100) : 0

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <div className="flex items-center gap-3 rounded-xl border border-[var(--gc-line)] p-2.5 transition-colors hover:border-[var(--gc-line-strong)]" />
        }
      >
        <div
          className="gc-icon-tile flex size-8 shrink-0 items-center justify-center rounded-lg"
          aria-hidden
        >
          <Icon className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <p className="min-w-0 flex-1 truncate text-[13px] font-medium text-[var(--gc-text)]">{lane.label}</p>
            <Badge
              variant="outline"
              style={{ borderColor: color, color }}
              className="shrink-0"
            >
              {lane.state || "NO DATA"}
            </Badge>
          </div>
          <p className="truncate text-[13px] text-[var(--gc-text-3)]">
            {lane.detail || "NO DATA"}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-center gap-0.5">
          <AnimatedCircularProgressBar
            value={pct}
            gaugePrimaryColor="var(--gc-cyan)"
            gaugeSecondaryColor="var(--gc-line)"
            className="size-9 text-[10px]"
          />
          <span className="text-[13px] text-[var(--gc-text-3)]">
            {total > 0 ? `${ready}/${total}` : "NO DATA"}
          </span>
        </div>
        {lane.metric && (
          <div className="flex shrink-0 flex-col items-end text-right">
            <span className="text-[13px] font-medium text-[var(--gc-text)]">{lane.metric}</span>
            <span className="text-[13px] text-[var(--gc-text-3)]">{lane.metric_label || ""}</span>
          </div>
        )}
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-left">
        <p className="font-medium">{lane.doing || "NO DATA"}</p>
        <p className="text-[var(--gc-text-3)]">{ageLabel(lane.last_at)}</p>
      </TooltipContent>
    </Tooltip>
  )
}

export function AgentHealth({ data }: { data: CockpitPayload }) {
  const lanes: Lane[] = Array.isArray(data?.lanes?.lanes) ? data.lanes.lanes : []

  return (
    <section className="cockpit gc-glass gc-glow rounded-2xl p-4">
      <div className="mb-3 flex items-center gap-2">
        <Activity className="size-4 text-[var(--gc-cyan)]" />
        <h2 className="gc-grad-text text-[15px] font-semibold">Agent health</h2>
      </div>
      {lanes.length === 0 ? (
        <p className="text-[13px] text-[var(--gc-text-3)]">NO DATA</p>
      ) : (
        <div className="space-y-2">
          {lanes.map((lane) => (
            <LaneRow key={lane.id} lane={lane} />
          ))}
        </div>
      )}
    </section>
  )
}
