"use client";

import type { ReactNode } from "react";
import * as Collapsible from "@radix-ui/react-collapsible";
import { ChevronDown, type LucideIcon } from "lucide-react";
import { useTileState } from "@/lib/use-tile-state";

export type TileId = "activity" | "money" | "wants" | "thisweek";

interface TileBadgeProps {
  text: string;
  tone?: "up" | "down" | "warning" | "neutral";
}

const BADGE_COLOR: Record<NonNullable<TileBadgeProps["tone"]>, string> = {
  up: "var(--up)",
  down: "var(--down)",
  warning: "var(--amber)",
  neutral: "var(--text-3)",
};

function TileBadge({ text, tone = "neutral" }: TileBadgeProps) {
  const color = BADGE_COLOR[tone];
  return (
    <span
      className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold"
      style={{ color, background: "rgba(255,255,255,0.04)", border: `1px solid ${color}33` }}
    >
      {text}
    </span>
  );
}

interface TileProps {
  id: TileId;
  icon: LucideIcon;
  title: string;
  badge?: TileBadgeProps;
  /** One-line summary shown only while the tile is collapsed. */
  summary: ReactNode;
  defaultOpen: boolean;
  children: ReactNode;
}

/** A collapsible tile: the shared shell for every non-Presence section of the
 * Gamma App. Height animation is Radix's own `--radix-collapsible-content-height`
 * CSS var (see the `.tile-content` keyframes in globals.css) -- no JS
 * measuring, no animation library. Content stays MOUNTED when closed (Radix
 * toggles height/visibility only), so find-in-page and screen readers still
 * reach a collapsed tile's content. Open/closed state persists per-tile to
 * localStorage via useTileState, so a background 20s poll can never re-close
 * a tile the user opened. */
export default function Tile({ id, icon: Icon, title, badge, summary, defaultOpen, children }: TileProps) {
  const [open, setOpen] = useTileState(id, defaultOpen);
  return (
    <Collapsible.Root
      open={open}
      onOpenChange={setOpen}
      className="overflow-hidden rounded-[var(--radius-lg)] border"
      style={{ background: "var(--bg-card)", borderColor: "var(--border)", boxShadow: "var(--shadow-sm)" }}
    >
      <Collapsible.Trigger
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
        style={{ minHeight: 52 }}
      >
        <Icon size={16} style={{ color: "var(--text-3)" }} aria-hidden />
        <span
          className="text-[11px] font-semibold uppercase tracking-[0.16em]"
          style={{ color: "var(--text-3)" }}
        >
          {title}
        </span>
        {badge && <TileBadge {...badge} />}
        {!open && (
          <span className="ml-auto min-w-0 truncate text-[13px]" style={{ color: "var(--text-2)" }}>
            {summary}
          </span>
        )}
        <ChevronDown
          size={16}
          className="tile-chevron ml-2 shrink-0"
          data-state={open ? "open" : "closed"}
          style={{ color: "var(--text-4)" }}
          aria-hidden
        />
      </Collapsible.Trigger>
      <Collapsible.Content className="tile-content px-4 pb-4" data-state={open ? "open" : "closed"}>
        {children}
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
