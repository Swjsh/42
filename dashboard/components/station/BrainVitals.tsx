"use client";

import { useState } from "react";
import { Cpu, Gauge, ChevronDown } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type {
  GpuVitals,
  OllamaPsRow,
  StationLedgerRow,
  PlannerBenchRun,
  BrainQuiz,
} from "@/lib/station";

export interface BrainVitalsData {
  model: string | null;
  mode: string;
  lastRow: StationLedgerRow | null;
  fireTimeline: StationLedgerRow[];
  gpu: GpuVitals;
  models: OllamaPsRow[];
  modelsOk: boolean;
  modelsSay: string;
  plannerSpeed: { ts_et: string; model: string; run: PlannerBenchRun } | null;
  quiz: BrainQuiz | null;
}

const STATUS_TONE: Record<string, string> = {
  ok: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  yielded: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  error: "bg-red-500/15 text-red-400 border-red-500/30",
};

function FireDot({ row }: { row: StationLedgerRow }) {
  const tone = STATUS_TONE[row.status] ?? "bg-muted text-muted-foreground border-border";
  return (
    <div
      title={`${row.ts_et} -- ${row.status}${row.reason ? ": " + row.reason : ""}`}
      className={cn("flex size-6 shrink-0 items-center justify-center rounded-full border text-[10px] font-semibold", tone)}
    >
      {row.status === "ok" ? row.cards_added || "0" : row.status === "yielded" ? "Y" : "!"}
    </div>
  );
}

function GpuGauge({ gpu }: { gpu: GpuVitals }) {
  if (!gpu.ok) {
    return <p className="text-xs text-muted-foreground">GPU: NO DATA (nvidia-smi unavailable)</p>;
  }
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      <span className="flex items-center gap-1 text-foreground">
        <Gauge className="size-3.5" />
        {gpu.util_pct != null ? `${Math.round(gpu.util_pct)}% util` : "util NO DATA"}
      </span>
      <span>
        {gpu.mem_used_mib != null && gpu.mem_total_mib != null
          ? `${Math.round(gpu.mem_used_mib)} / ${Math.round(gpu.mem_total_mib)} MiB`
          : "mem NO DATA"}
      </span>
      <span>{gpu.temp_c != null ? `${Math.round(gpu.temp_c)}C` : "temp NO DATA"}</span>
      <span>{gpu.power_w != null ? `${gpu.power_w.toFixed(0)}W` : "power NO DATA"}</span>
    </div>
  );
}

function QuizPanel({ quiz }: { quiz: BrainQuiz | null }) {
  const [open, setOpen] = useState(false);
  if (!quiz) {
    return <p className="text-xs text-muted-foreground">Smartness check: no quiz yet</p>;
  }
  return (
    <div className="text-xs">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 font-medium text-foreground hover:text-foreground/80"
      >
        Smartness check: {quiz.score}
        {quiz.gen_tok_per_s != null && ` · ${quiz.gen_tok_per_s.toFixed(0)} tok/s`}
        <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <ul className="mt-2 space-y-1.5 border-t border-border pt-2 text-muted-foreground">
          {quiz.questions.map((q, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className={cn("mt-0.5 size-1.5 shrink-0 rounded-full", q.correct ? "bg-emerald-500" : "bg-red-500")} />
              <span>
                <span className="text-foreground/80">{q.label ?? q.id ?? "question"}</span>
                {" -> "}
                {q.answer ?? "(no answer recorded)"}
                {q.gen_tok_per_s != null && ` (${q.gen_tok_per_s.toFixed(0)} tok/s)`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * "Brain vitals" panel (J amendment 4, 2026-09-13 -- "the face must SHOW the
 * brain working"): GPU load, which model(s) are actually resident, station
 * mode, a fire timeline of the last 10 loop-ledger rows, planner speed from
 * the last bench run, and the "smartness check" quiz result. Every field
 * comes straight from /api/station's brainVitals payload -- this component
 * never computes a number, only lays one out.
 */
export default function BrainVitals({ data }: { data: BrainVitalsData }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
          <Cpu className="size-4" />
          Brain vitals
        </p>
        <div className="flex items-center gap-2">
          <Badge variant={data.mode === "work" ? "default" : "secondary"}>mode: {data.mode}</Badge>
          <Badge variant="outline">{data.model ?? "no model configured"}</Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-2">
          <GpuGauge gpu={data.gpu} />
          <p className="text-xs text-muted-foreground">
            {data.modelsOk && data.models.length > 0
              ? `Loaded: ${data.models.map((m) => `${m.name} (${m.size}, ${m.processor})`).join(", ")}`
              : data.modelsSay}
          </p>
          {data.plannerSpeed && (
            <p className="text-xs text-muted-foreground">
              Planner speed ({data.plannerSpeed.model}): {data.plannerSpeed.run.gen_tok_per_s ?? "?"} tok/s gen,{" "}
              {data.plannerSpeed.run.prompt_tok_per_s ?? "?"} tok/s prompt, {data.plannerSpeed.run.processor_split ?? "NO DATA"}
            </p>
          )}
          <QuizPanel quiz={data.quiz} />
        </div>

        <div>
          <p className="mb-1.5 text-xs font-medium text-foreground/80">
            Last {data.fireTimeline.length} fire{data.fireTimeline.length === 1 ? "" : "s"}
          </p>
          <div className="flex flex-wrap gap-1">
            {data.fireTimeline.length === 0 ? (
              <span className="text-xs text-muted-foreground">NO DATA</span>
            ) : (
              data.fireTimeline.map((row, i) => <FireDot key={i} row={row} />)
            )}
          </div>
          {data.lastRow && (
            <p className="mt-2 text-xs text-muted-foreground">
              Last: {data.lastRow.ts_et} -- {data.lastRow.status}
              {data.lastRow.reason ? ` (${data.lastRow.reason})` : ""}
              {data.lastRow.duration_s != null ? `, ${data.lastRow.duration_s.toFixed(1)}s` : ""}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
