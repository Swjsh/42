"use client";

import * as React from "react";
import { motion, useReducedMotion } from "motion/react";
import { Badge } from "@/components/ui/badge";
import { ageLabel, type CockpitPayload } from "@/lib/cockpit-data";

type FunnelStage = { id: string; label: string; n: number };
type FunnelLink = { from: string; to: string; n: number; tone: string };
type FunnelData = {
  ok?: boolean;
  live?: boolean;
  session_label?: string | null;
  verdict?: string;
  say?: string;
  stages?: FunnelStage[];
  links?: FunnelLink[];
  cause_counts?: Record<string, number>;
  accounts?: Record<string, Record<string, number>>;
  stamp_et?: string;
};

const W = 720;
const COL_PAD_X = 56;
const NODE_W = 16;
const MIN_RIBBON_W = 6;
const QUIET_LABEL = "Quiet";

/** Track container size so the viewBox aspect matches the panel — no letterbox dead space. */
function useContainerAspect(defaultH: number) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [h, setH] = React.useState(defaultH);
  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const { width, height } = el.getBoundingClientRect();
      if (width > 0 && height > 0) setH(Math.max(180, (height / width) * W));
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, h };
}

/** log-scale ribbon thickness so a 1300-wide link doesn't crush a 2-wide one. */
function scaleN(n: number): number {
  return Math.log10(Math.max(0, n) + 1);
}

function toneStroke(tone: string): string {
  switch (tone) {
    case "accepted":
      return "url(#gc-grad-accept)";
    case "refused":
      return "var(--gc-bad)";
    case "quiet":
      return "var(--gc-line-strong)";
    default:
      return "url(#gc-grad-flow)";
  }
}

/** Ribbon stroke width: log-scaled against the biggest link, but any real (n>0) link
 *  gets at least MIN_RIBBON_W so small-but-real flows stay visible next to a huge quiet sink. */
function ribbonWidth(n: number, maxScale: number): number {
  if (n <= 0) return 0;
  const scaled = (scaleN(n) / maxScale) * 26;
  return Math.max(MIN_RIBBON_W, scaled);
}

function ribbonPath(x1: number, y1: number, x2: number, y2: number): string {
  const mx = (x1 + x2) / 2;
  return `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
}

export function RoutingMap({ data }: { data: CockpitPayload }) {
  const funnel = data?.funnel as FunnelData | undefined;
  const reduceMotion = useReducedMotion();
  const [hoverKey, setHoverKey] = React.useState<string | null>(null);
  const { ref: svgWrapRef, h: H } = useContainerAspect(320);

  const hasData = !!funnel?.ok && !!funnel.stages?.length;

  const stages = React.useMemo<FunnelStage[]>(
    () =>
      hasData
        ? funnel!.stages!
        : [
            { id: "ticks", label: "Ticks", n: 0 },
            { id: "signals", label: "Signals", n: 0 },
            { id: "enter", label: "Enter", n: 0 },
            { id: "accepted", label: "Accepted", n: 0 },
            { id: "filled", label: "Filled", n: 0 },
            { id: "exited", label: "Exited", n: 0 },
          ],
    [hasData, funnel]
  );

  const links = React.useMemo<FunnelLink[]>(
    () => (hasData ? funnel!.links ?? [] : []),
    [hasData, funnel]
  );

  // Column x position per stage id, plus a shared "quiet" sink column offset per source column.
  const colX = new Map<string, number>();
  const n = stages.length;
  stages.forEach((s, i) => {
    colX.set(s.id, COL_PAD_X + (i * (W - 2 * COL_PAD_X)) / Math.max(1, n - 1));
  });

  const nodeTop = 56;
  const nodeH = H - nodeTop - 64;

  // node y-center is fixed mid-column; quiet sinks per-column sit slightly below.
  const nodeCy = nodeTop + nodeH / 2;

  const maxLinkScale = Math.max(1e-6, ...links.map((l) => scaleN(l.n)));

  function linkY(stageId: string, isQuiet: boolean): number {
    if (isQuiet) return nodeCy + nodeH / 2 + 34;
    return nodeCy;
  }

  const sourceTotals = new Map<string, number>();
  links.forEach((l) => {
    sourceTotals.set(l.from, (sourceTotals.get(l.from) ?? 0) + l.n);
  });

  return (
    <div className="cockpit gc-glass gc-glow relative flex h-full flex-col rounded-2xl p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="gc-icon-tile flex h-7 w-7 items-center justify-center rounded-lg text-[13px] font-semibold">
            R
          </span>
          <h3 className="text-[14px] font-semibold" style={{ color: "var(--gc-text)" }}>
            Routing map
          </h3>
        </div>
        <div className="flex items-center gap-2">
          <div
            className="flex items-center gap-1.5 text-[13px]"
            style={{ color: "var(--gc-text-3)" }}
            title="Ribbon width is log-scaled; labels show real counts."
          >
            <LegendDot color="url(#gc-grad-flow-legend)" />
            <span>Accepted flow</span>
            <LegendDot color="var(--gc-bad)" />
            <span>Refused</span>
            <LegendDot color="var(--gc-line-strong)" />
            <span>Quiet</span>
          </div>
          {funnel?.live ? (
            <Badge className="relative overflow-hidden border-0 bg-[var(--gc-good)]/20 text-[13px]" style={{ color: "var(--gc-good)" }}>
              <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full" style={{ background: "var(--gc-good)" }} />
              Live
            </Badge>
          ) : (
            <Badge variant="outline" className="text-[13px]" style={{ color: "var(--gc-text-3)" }}>
              {funnel?.session_label ?? "Today · closed"}
            </Badge>
          )}
        </div>
      </div>

      <div ref={svgWrapRef} className="relative min-h-0 flex-1">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          className="h-full w-full"
          role="img"
          aria-label="Decision routing funnel"
        >
          <defs>
            {/* userSpaceOnUse: ribbons are often perfectly horizontal (zero-height bbox), and
                per SVG spec an objectBoundingBox gradient does not paint at all in that case. */}
            <linearGradient id="gc-grad-flow" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2={W} y2="0">
              <stop offset="0%" stopColor="var(--gc-indigo)" />
              <stop offset="100%" stopColor="var(--gc-cyan)" />
            </linearGradient>
            <linearGradient id="gc-grad-flow-legend" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="var(--gc-indigo)" />
              <stop offset="100%" stopColor="var(--gc-cyan)" />
            </linearGradient>
            <linearGradient id="gc-grad-accept" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2={W} y2="0">
              <stop offset="0%" stopColor="var(--gc-violet)" />
              <stop offset="100%" stopColor="var(--gc-cyan)" />
            </linearGradient>
            <linearGradient id="gc-grad-node" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--gc-indigo)" />
              <stop offset="55%" stopColor="var(--gc-violet)" />
              <stop offset="100%" stopColor="var(--gc-cyan)" />
            </linearGradient>
            {/* userSpaceOnUse + fixed padding: a horizontal ribbon has a zero-height bbox, and
                a percentage/objectBoundingBox filter region degenerates to nothing in that case. */}
            <filter id="gc-ribbon-glow" filterUnits="userSpaceOnUse" x={-40} y={-200} width={W + 80} height={800}>
              <feGaussianBlur stdDeviation="3.2" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id="gc-node-glow" x="-80%" y="-80%" width="260%" height="260%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* ribbons */}
          {links.filter((l) => l.n > 0).map((l, i) => {
            const isQuiet = l.to === "quiet" || l.to === QUIET_LABEL.toLowerCase();
            const x1 = (colX.get(l.from) ?? 0) + NODE_W / 2;
            const x2 = isQuiet
              ? (colX.get(l.from) ?? 0) + (W - 2 * COL_PAD_X) / Math.max(1, n - 1) * 0.42
              : (colX.get(l.to) ?? 0) - NODE_W / 2;
            const y1 = linkY(l.from, false);
            const y2 = isQuiet ? linkY(l.from, true) : linkY(l.to, false);
            const strokeW = ribbonWidth(l.n, maxLinkScale);
            const key = `${l.from}->${l.to}-${i}`;
            const dimmed = hoverKey !== null && hoverKey !== key;
            const pct =
              sourceTotals.get(l.from) && sourceTotals.get(l.from)! > 0
                ? Math.round((l.n / sourceTotals.get(l.from)!) * 100)
                : 0;

            const ribbon = (
              <path
                d={ribbonPath(x1, y1, x2, y2)}
                fill="none"
                stroke={toneStroke(l.tone)}
                strokeWidth={strokeW}
                strokeLinecap="round"
                opacity={dimmed ? 0.14 : l.tone === "quiet" ? 0.35 : 0.85}
                filter="url(#gc-ribbon-glow)"
                strokeDasharray={funnel?.live && !reduceMotion && l.tone !== "quiet" ? "10 8" : undefined}
                style={{ transition: "opacity 160ms ease" }}
              >
                {funnel?.live && !reduceMotion && l.tone !== "quiet" && (
                  <animate
                    attributeName="stroke-dashoffset"
                    from="0"
                    to="-36"
                    dur="1.6s"
                    repeatCount="indefinite"
                  />
                )}
              </path>
            );

            return (
              <g
                key={key}
                onMouseEnter={() => setHoverKey(key)}
                onMouseLeave={() => setHoverKey(null)}
                style={{ cursor: "default" }}
              >
                <title>
                  {l.from} &rarr; {isQuiet ? "quiet" : l.to}: {l.n.toLocaleString()} ({pct}% of {l.from})
                </title>
                {ribbon}
              </g>
            );
          })}

          {/* stage nodes */}
          {stages.map((s) => {
            const x = colX.get(s.id) ?? 0;
            const dimmedNode = hoverKey !== null && !hoverKey.startsWith(`${s.id}->`) && !hoverKey.includes(`->${s.id}-`);
            return (
              <g key={s.id}>
                <rect
                  x={x - NODE_W / 2}
                  y={nodeCy - nodeH / 2}
                  width={NODE_W}
                  height={nodeH}
                  rx={7}
                  fill="url(#gc-grad-node)"
                  filter="url(#gc-node-glow)"
                  opacity={dimmedNode ? 0.45 : 0.95}
                  style={{ transition: "opacity 160ms ease" }}
                />
                <text
                  x={x}
                  y={nodeCy - nodeH / 2 - 12}
                  textAnchor="middle"
                  fontSize={13}
                  fill="var(--gc-text-2)"
                >
                  {s.label}
                </text>
                <text
                  x={x}
                  y={nodeCy + nodeH / 2 + 20}
                  textAnchor="middle"
                  fontSize={13}
                  fontWeight={600}
                  fill="var(--gc-text)"
                >
                  {s.n.toLocaleString()}
                </text>
              </g>
            );
          })}

          {/* quiet sink label */}
          {hasData && (
            <text
              x={W / 2}
              y={nodeCy + nodeH / 2 + 46}
              textAnchor="middle"
              fontSize={13}
              fill="var(--gc-text-3)"
            >
              {QUIET_LABEL} (no trigger / gate skip)
            </text>
          )}

          {!hasData && (
            <text x={W / 2} y={H / 2} textAnchor="middle" fontSize={14} fill="var(--gc-text-3)">
              NO DATA
            </text>
          )}
        </svg>
      </div>

      <div
        className="mt-2 flex items-center justify-between gap-3 border-t pt-2 text-[13px]"
        style={{ borderColor: "var(--gc-line)", color: "var(--gc-text-3)" }}
      >
        <span className="truncate">{hasData ? funnel!.say : "NO DATA"}</span>
        <span className="shrink-0">{ageLabel(funnel?.stamp_et)}</span>
      </div>
    </div>
  );
}

function LegendDot({ color }: { color: string }) {
  return (
    <span
      className="inline-block h-2 w-2 rounded-full"
      style={{ background: color.startsWith("url") ? "var(--gc-cyan)" : color }}
    />
  );
}
