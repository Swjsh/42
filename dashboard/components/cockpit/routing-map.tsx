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
const MIN_RIBBON_W = 4;
const H_MIN = 14;
const QUIET_LABEL = "Quiet";
const QUIET_BAR_H = 22;

/** Track container size so the viewBox aspect matches the panel — no letterbox dead space. */
function useContainerAspect(defaultH: number) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [h, setH] = React.useState(defaultH);
  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const { width, height } = el.getBoundingClientRect();
      if (width > 0 && height > 0) setH(Math.max(220, (height / width) * W));
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, h };
}

function toneFill(tone: string): string {
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

/** sqrt-scale node height so 1324 vs 2 both stay legibly distinct without one swallowing the other. */
function nodeHeight(n: number, nMax: number, hMax: number): number {
  if (nMax <= 0) return H_MIN;
  const frac = Math.sqrt(Math.max(0, n) / nMax);
  return H_MIN + (hMax - H_MIN) * frac;
}

/** Ribbon band: two cubic-bezier edges (top + bottom) plus closing verticals — a filled Sankey ribbon. */
function ribbonBandPath(x1: number, y1a: number, y1b: number, x2: number, y2a: number, y2b: number): string {
  const mx = (x1 + x2) / 2;
  return `M ${x1} ${y1a} C ${mx} ${y1a}, ${mx} ${y2a}, ${x2} ${y2a} L ${x2} ${y2b} C ${mx} ${y2b}, ${mx} ${y1b}, ${x1} ${y1b} Z`;
}

type StageBox = { id: string; x: number; top: number; bottom: number; n: number };
type RibbonGeo = FunnelLink & { key: string; x1: number; y1a: number; y1b: number; x2: number; y2a: number; y2b: number; isQuiet: boolean; pct: number };

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

  // --- layout geometry -----------------------------------------------------
  const n = stages.length;
  const rowTop = 56;
  const rowBottom = Math.max(rowTop + H_MIN + 20, H - 140);
  const hMax = rowBottom - rowTop;
  const quietTop = rowBottom + 46;
  const nMax = Math.max(1, ...stages.map((s) => s.n));

  const boxes = new Map<string, StageBox>();
  stages.forEach((s, i) => {
    const x = COL_PAD_X + (i * (W - 2 * COL_PAD_X)) / Math.max(1, n - 1);
    const h = nodeHeight(s.n, nMax, hMax);
    boxes.set(s.id, { id: s.id, x, top: rowTop, bottom: rowTop + h, n: s.n });
  });

  const quietTotal = links.reduce((acc, l) => acc + (l.tone === "quiet" || l.to === "quiet" ? l.n : 0), 0);
  const quietX = W / 2;

  // stack outgoing links top-to-bottom on the source node (non-quiet flows first, quiet last)
  const byFrom = new Map<string, FunnelLink[]>();
  links.forEach((l) => {
    if (l.n <= 0) return;
    const arr = byFrom.get(l.from) ?? [];
    arr.push(l);
    byFrom.set(l.from, arr);
  });
  byFrom.forEach((arr) =>
    arr.sort((a, b) => (a.tone === "quiet" ? 1 : 0) - (b.tone === "quiet" ? 1 : 0))
  );

  // stack incoming links top-to-bottom on the target node (quiet handled separately below)
  const byTo = new Map<string, FunnelLink[]>();
  links.forEach((l) => {
    if (l.n <= 0 || l.tone === "quiet" || l.to === "quiet") return;
    const arr = byTo.get(l.to) ?? [];
    arr.push(l);
    byTo.set(l.to, arr);
  });

  function thickness(v: number, denom: number, span: number): number {
    if (v <= 0) return 0;
    return Math.max(MIN_RIBBON_W, (v / Math.max(1, denom)) * span);
  }

  const ribbons: RibbonGeo[] = [];
  const srcCursor = new Map<string, number>();
  const tgtCursor = new Map<string, number>();

  links.forEach((l, i) => {
    if (l.n <= 0) return;
    const isQuiet = l.tone === "quiet" || l.to === "quiet" || l.to === QUIET_LABEL.toLowerCase();
    const src = boxes.get(l.from);
    if (!src) return;
    const srcSpan = src.bottom - src.top;
    const srcThick = thickness(l.n, src.n, srcSpan);
    const c1 = srcCursor.get(l.from) ?? 0;
    const y1a = src.top + c1;
    const y1b = y1a + srcThick;
    srcCursor.set(l.from, c1 + srcThick);

    const x1 = src.x + NODE_W / 2;
    const key = `${l.from}->${l.to}-${i}`;
    const sourceTotal = links.reduce((acc, o) => (o.from === l.from ? acc + o.n : acc), 0);
    const pct = sourceTotal > 0 ? Math.round((l.n / sourceTotal) * 100) : 0;

    if (isQuiet) {
      // quiet is a shared drain bar, not a per-source stacked node: keep the ribbon's own
      // taper (source-side thickness clamped to the bar) rather than sharing a cursor across sources.
      const qThick = Math.min(QUIET_BAR_H, thickness(l.n, quietTotal, QUIET_BAR_H) || MIN_RIBBON_W);
      const y2a = quietTop;
      const y2b = y2a + qThick;
      ribbons.push({ ...l, key, x1, y1a, y1b, x2: x1, y2a, y2b, isQuiet, pct });
      return;
    }

    const tgt = boxes.get(l.to);
    if (!tgt) return;
    const tgtSpan = tgt.bottom - tgt.top;
    const tgtThick = thickness(l.n, tgt.n, tgtSpan);
    const c2 = tgtCursor.get(l.to) ?? 0;
    const y2a = tgt.top + c2;
    const y2b = y2a + tgtThick;
    tgtCursor.set(l.to, c2 + tgtThick);
    const x2 = tgt.x - NODE_W / 2;
    ribbons.push({ ...l, key, x1, y1a, y1b, x2, y2a, y2b, isQuiet, pct });
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
            title="Node height = sqrt-scaled stage volume. Ribbon thickness = share of source/target height."
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
            {/* userSpaceOnUse: ribbons are often near-horizontal (zero-height bbox), and
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
              <feGaussianBlur stdDeviation="2.6" result="blur" />
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
          {ribbons.map((r) => {
            const dimmed = hoverKey !== null && hoverKey !== r.key;
            const d = ribbonBandPath(r.x1, r.y1a, r.y1b, r.x2, r.y2a, r.y2b);
            return (
              <g
                key={r.key}
                onMouseEnter={() => setHoverKey(r.key)}
                onMouseLeave={() => setHoverKey(null)}
                style={{ cursor: "default" }}
              >
                <title>
                  {r.from} &rarr; {r.isQuiet ? "quiet" : r.to}: {r.n.toLocaleString()} ({r.pct}% of {r.from})
                </title>
                <path
                  d={d}
                  fill={toneFill(r.tone)}
                  stroke="none"
                  opacity={dimmed ? 0.12 : r.isQuiet ? 0.4 : 0.88}
                  filter="url(#gc-ribbon-glow)"
                  style={{ transition: "opacity 160ms ease" }}
                />
                {funnel?.live && !reduceMotion && !r.isQuiet && (
                  <path d={d} fill="none" stroke="rgba(255,255,255,0.35)" strokeWidth={1} strokeDasharray="8 10" opacity={dimmed ? 0 : 0.5}>
                    <animate attributeName="stroke-dashoffset" from="0" to="-36" dur="1.6s" repeatCount="indefinite" />
                  </path>
                )}
              </g>
            );
          })}

          {/* quiet sink bar */}
          {hasData && (
            <g>
              <rect
                x={COL_PAD_X - NODE_W / 2}
                y={quietTop}
                width={W - 2 * COL_PAD_X + NODE_W}
                height={QUIET_BAR_H}
                rx={6}
                fill="var(--gc-line-strong)"
                opacity={hoverKey !== null && !hoverKey.includes("quiet") ? 0.18 : 0.32}
                style={{ transition: "opacity 160ms ease" }}
              />
              <text x={W / 2} y={quietTop + QUIET_BAR_H + 18} textAnchor="middle" fontSize={13} fill="var(--gc-text-3)">
                {QUIET_LABEL} — no trigger / gate skip ({quietTotal.toLocaleString()})
              </text>
            </g>
          )}

          {/* stage nodes */}
          {stages.map((s) => {
            const box = boxes.get(s.id)!;
            const dimmedNode = hoverKey !== null && !hoverKey.startsWith(`${s.id}->`) && !hoverKey.includes(`->${s.id}-`);
            return (
              <g key={s.id}>
                <rect
                  x={box.x - NODE_W / 2}
                  y={box.top}
                  width={NODE_W}
                  height={Math.max(2, box.bottom - box.top)}
                  rx={6}
                  fill="url(#gc-grad-node)"
                  filter="url(#gc-node-glow)"
                  opacity={dimmedNode ? 0.4 : 0.95}
                  style={{ transition: "opacity 160ms ease" }}
                />
                <text x={box.x} y={box.top - 12} textAnchor="middle" fontSize={13} fill="var(--gc-text-2)">
                  {s.label}
                </text>
                <text x={box.x} y={box.bottom + 20} textAnchor="middle" fontSize={13} fontWeight={600} fill="var(--gc-text)">
                  {s.n.toLocaleString()}
                </text>
              </g>
            );
          })}

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
