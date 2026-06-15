"use client";

interface Prediction {
  claim: string;
  confidence: number;
  outcome?: string | null;
}

interface TodayBias {
  date?: string;
  bias?: string;
  iv_regime?: string;
  falsifiable_predictions?: Prediction[];
  falsifiable_hypothesis?: string;
}

interface DialogueAgents {
  review?: { speech?: string | null };
}

interface DialogueFile {
  agents?: DialogueAgents;
  claude_reasoning?: string;
}

interface Props {
  data?: {
    todayBias?: TodayBias;
    dialogue?: DialogueFile;
  };
}

function biasColor(bias: string | undefined) {
  if (!bias) return "text-terminal-dim";
  if (bias.toLowerCase().includes("bull")) return "text-terminal-green";
  if (bias.toLowerCase().includes("bear")) return "text-red-400";
  return "text-terminal-amber";
}

function outcomeColor(outcome: string | null | undefined) {
  if (outcome === "PASS") return "text-terminal-green";
  if (outcome === "FAIL") return "text-red-400";
  if (outcome === "UNTESTED") return "text-terminal-amber";
  return "text-terminal-dim";
}

function outcomeDot(outcome: string | null | undefined) {
  if (outcome === "PASS") return "●";
  if (outcome === "FAIL") return "✕";
  if (outcome === "UNTESTED") return "○";
  return "·";
}

export default function BiasPanel({ data }: Props) {
  const todayBias = data?.todayBias;
  const dialogue = data?.dialogue;

  const tomorrowHint =
    dialogue?.agents?.review?.speech ??
    todayBias?.falsifiable_hypothesis?.slice(0, 120) ??
    null;

  const bias = todayBias?.bias;
  const ivRegime = todayBias?.iv_regime;
  const predictions = todayBias?.falsifiable_predictions ?? [];

  const passed = predictions.filter((p) => p.outcome === "PASS").length;
  const failed = predictions.filter((p) => p.outcome === "FAIL").length;
  const untested = predictions.filter((p) => p.outcome === "UNTESTED").length;
  const total = predictions.length;
  const graded = passed + failed;

  return (
    <section className="panel p-3 flex flex-col gap-2 flex-shrink-0">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div className="panel-title text-sm">▸ BIAS &amp; LEVELS</div>
        <div className="flex items-center gap-2">
          {bias && (
            <span className={`text-xs font-bold uppercase ${biasColor(bias)}`}>
              {bias}
            </span>
          )}
          {ivRegime && (
            <span className="text-[10px] font-bold text-terminal-dim bg-black/40 px-1.5 py-0.5 rounded border border-terminal-border">
              {ivRegime} IV
            </span>
          )}
        </div>
      </div>

      {/* Tomorrow hint — the key text */}
      {tomorrowHint && (
        <div className="bg-black/50 border border-terminal-green/20 rounded px-2.5 py-2">
          <div className="text-[10px] text-terminal-dim uppercase tracking-wider mb-1">
            Tomorrow
          </div>
          <div className="text-terminal-green text-xs leading-snug font-medium">
            {tomorrowHint}
          </div>
        </div>
      )}

      {/* Prediction scorecard */}
      {total > 0 && (
        <div>
          <div className="text-[10px] text-terminal-dim uppercase tracking-wider mb-1 flex items-center justify-between">
            <span>▸ Today's predictions</span>
            <span className="tabular-nums">
              {graded > 0 ? (
                <span>
                  <span className="text-terminal-green">{passed}P</span>
                  <span className="text-terminal-dim mx-0.5">/</span>
                  <span className="text-red-400">{failed}F</span>
                  {untested > 0 && (
                    <>
                      <span className="text-terminal-dim mx-0.5">/</span>
                      <span className="text-terminal-amber">{untested}U</span>
                    </>
                  )}
                  <span className="text-terminal-dim ml-1">of {total}</span>
                </span>
              ) : (
                <span className="text-terminal-dim">{total} pending</span>
              )}
            </span>
          </div>
          <div className="space-y-0.5">
            {predictions.slice(0, 4).map((p, i) => (
              <div key={i} className="flex items-start gap-1.5 text-[11px]">
                <span className={`shrink-0 font-bold w-3 ${outcomeColor(p.outcome)}`}>
                  {outcomeDot(p.outcome)}
                </span>
                <span
                  className="text-terminal-text/80 leading-tight truncate"
                  title={p.claim}
                >
                  {p.claim.length > 70 ? p.claim.slice(0, 68) + "…" : p.claim}
                </span>
                <span className="shrink-0 text-terminal-dim tabular-nums text-[10px] ml-auto">
                  {Math.round(p.confidence * 100)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
