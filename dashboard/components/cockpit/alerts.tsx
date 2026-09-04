"use client"

import * as React from "react"
import { AlertOctagon, CheckCircle2, ShieldAlert, TriangleAlert } from "lucide-react"

import { ageLabel, type CockpitPayload } from "@/lib/cockpit-data"
import { Badge } from "@/components/ui/badge"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"

type Severity = "bad" | "warn"

type Alert = {
  id: string
  text: string
  severity: Severity
  age?: string
  detail: string
}

const GREEN_VERDICTS = new Set(["GREEN", "OK", "green", "ok"])

function clip2(s: string): string {
  const parts = s.split(/\.\s+|\n/).filter(Boolean)
  const out = parts.slice(0, 2).join(". ")
  return out.length > 180 ? `${out.slice(0, 180)}…` : out
}

/** Assemble alerts from guards.problems, tasks (say when not-green),
 *  answers with a non-green verdict, and lanes reporting BROKEN. Every
 *  field is read defensively -- the payload is a loose, mostly-optional
 *  shape per lib/cockpit-data.ts. */
function buildAlerts(data: CockpitPayload): Alert[] {
  const out: Alert[] = []

  const problems: any[] = Array.isArray(data?.guards?.problems) ? data.guards.problems : []
  problems.forEach((p, i) => {
    const text = typeof p === "string" ? p : p?.text || p?.name || JSON.stringify(p)
    out.push({
      id: `guard-${i}`,
      text: clip2(text),
      severity: "bad",
      age: ageLabel(data?.guards?.ts_et),
      detail: typeof p === "string" ? p : JSON.stringify(p, null, 2),
    })
  })

  const tasksVerdict = data?.tasks?.verdict
  if (tasksVerdict && !GREEN_VERDICTS.has(String(tasksVerdict))) {
    out.push({
      id: "tasks-verdict",
      text: clip2(data?.tasks?.say || "Scheduled tasks are not green."),
      severity: String(tasksVerdict).toLowerCase() === "red" ? "bad" : "warn",
      age: ageLabel(data?.tasks?.stamp_et),
      detail: data?.tasks?.say || "No detail recorded.",
    })
  }

  const answers: any[] = Array.isArray(data?.answers) ? data.answers : []
  answers.forEach((a, i) => {
    const v = String(a?.verdict || "").toUpperCase()
    if (v && !GREEN_VERDICTS.has(v) && v !== "INFO") {
      out.push({
        id: `answer-${i}`,
        text: clip2(a?.answer || a?.q || "Unresolved question."),
        severity: v === "RED" ? "bad" : "warn",
        age: ageLabel(a?.sources?.[0]?.mtime_et),
        detail: a?.detail || a?.answer || "No detail recorded.",
      })
    }
  })

  const lanes: any[] = Array.isArray(data?.lanes?.lanes) ? data.lanes.lanes : []
  lanes.forEach((l) => {
    if (String(l?.state || "").toUpperCase() === "BROKEN") {
      out.push({
        id: `lane-${l.id}`,
        text: clip2(`${l.label || l.id} is broken — ${l.detail || "no detail recorded"}`),
        severity: "bad",
        age: ageLabel(l.last_at),
        detail: l.detail || "No detail recorded.",
      })
    }
  })

  return out
}

function AlertRow({ alert }: { alert: Alert }) {
  const [open, setOpen] = React.useState(false)
  const Icon = alert.severity === "bad" ? AlertOctagon : TriangleAlert
  const bg =
    alert.severity === "bad"
      ? "linear-gradient(135deg, var(--gc-bad), var(--gc-violet))"
      : "linear-gradient(135deg, var(--gc-warn), var(--gc-indigo))"

  return (
    <div className="flex items-start gap-3 rounded-xl border border-[var(--gc-line)] p-2.5">
      <div
        className="gc-icon-tile flex size-8 shrink-0 items-center justify-center rounded-lg"
        style={{ background: bg }}
        aria-hidden
      >
        <Icon className="size-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="line-clamp-2 text-[13px] text-[var(--gc-text)]">{alert.text}</p>
        <div className="mt-1 flex items-center gap-2">
          <Badge variant="outline" className="text-[var(--gc-text-3)]">
            {alert.severity === "bad" ? "Critical" : "Warning"}
          </Badge>
          <span className="text-[13px] text-[var(--gc-text-3)]">{alert.age || "NO DATA"}</span>
        </div>
      </div>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger
          render={
            <button
              type="button"
              className="shrink-0 text-[13px] text-[var(--gc-cyan)] hover:underline"
            />
          }
        >
          Open
        </SheetTrigger>
        <SheetContent side="right" className="cockpit gc-glass w-full sm:max-w-md">
          <SheetHeader>
            <SheetTitle className="text-[var(--gc-text)]">Alert detail</SheetTitle>
          </SheetHeader>
          <pre className="mt-3 max-h-[70vh] overflow-y-auto whitespace-pre-wrap rounded-lg border border-[var(--gc-line)] bg-black/20 p-3 text-[13px] leading-relaxed text-[var(--gc-text-2)]">
            {alert.detail}
          </pre>
        </SheetContent>
      </Sheet>
    </div>
  )
}

export function SystemAlerts({ data }: { data: CockpitPayload }) {
  const alerts = React.useMemo(() => buildAlerts(data), [data])

  return (
    <section className="cockpit gc-glass gc-glow rounded-2xl p-4">
      <div className="mb-3 flex items-center gap-2">
        <ShieldAlert className="size-4 text-[var(--gc-cyan)]" />
        <h2 className="gc-grad-text text-[15px] font-semibold">System alerts ({alerts.length})</h2>
      </div>
      {alerts.length === 0 ? (
        <div className="flex items-center gap-2 rounded-xl border border-[var(--gc-line)] p-3 text-[13px] text-[var(--gc-text-2)]">
          <CheckCircle2 className="size-4 text-[var(--gc-good)]" />
          All quiet
        </div>
      ) : (
        <div className="space-y-2">
          {alerts.map((a) => (
            <AlertRow key={a.id} alert={a} />
          ))}
        </div>
      )}
    </section>
  )
}
