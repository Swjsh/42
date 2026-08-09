"use client";

import { useState, type ReactNode } from "react";
import * as Collapsible from "@radix-ui/react-collapsible";
import { ChevronDown } from "lucide-react";

interface ExpandableCardProps {
  icon?: ReactNode;
  headline: ReactNode;
  /** One clean supporting line, always visible under the headline. */
  description?: ReactNode;
  /** Right-aligned, always-visible slot OUTSIDE the click target (e.g. a
   * relative-time label with its own hover tooltip, a priority chip) -- its
   * own interactions never fight the card's expand/collapse click. */
  aside?: ReactNode;
  toneColor?: string;
  /** The full breakdown, revealed only on expand. A card with no breakdown
   * renders as a plain, non-interactive card (no chevron, no click) --
   * never a fake affordance for content that doesn't exist. */
  breakdown?: ReactNode;
  animateIn?: boolean;
}

/** A single "ad tile": a short plain-English headline + one description
 * line, always visible -- click anywhere on the card to reveal the full
 * technical breakdown underneath. Shared by the Live Activity feed and the
 * This Week plan, so the whole app teaches one interaction pattern once.
 * Height animation reuses the top-level Tile's own `.tile-content` /
 * `--radix-collapsible-content-height` CSS (globals.css) -- no separate
 * animation logic, and each card's Collapsible.Content scopes that CSS var
 * to itself, so many independent cards animate correctly side by side. */
export default function ExpandableCard({
  icon,
  headline,
  description,
  aside,
  toneColor,
  breakdown,
  animateIn,
}: ExpandableCardProps) {
  const [open, setOpen] = useState(false);
  const hasBreakdown = Boolean(breakdown);

  return (
    <Collapsible.Root
      open={hasBreakdown && open}
      onOpenChange={hasBreakdown ? setOpen : () => {}}
      className={`rounded-[var(--radius)] border${animateIn ? " activity-row-in" : ""}`}
      style={{
        background: "var(--bg-card)",
        borderColor: open && hasBreakdown ? "var(--border-mid)" : "var(--border)",
      }}
    >
      <div className="flex items-start gap-3 px-3 py-2.5">
        <Collapsible.Trigger
          disabled={!hasBreakdown}
          className="flex min-w-0 flex-1 items-start gap-3 text-left"
          style={{ cursor: hasBreakdown ? "pointer" : "default" }}
        >
          {icon}
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium leading-snug" style={{ color: toneColor ?? "var(--text-1)" }}>
              {headline}
            </p>
            {description && (
              <p className="mt-0.5 truncate text-xs" style={{ color: "var(--text-3)" }}>
                {description}
              </p>
            )}
          </div>
          {hasBreakdown && (
            <ChevronDown
              size={14}
              className="tile-chevron mt-1 shrink-0"
              data-state={open ? "open" : "closed"}
              style={{ color: "var(--text-4)" }}
              aria-hidden
            />
          )}
        </Collapsible.Trigger>
        {aside}
      </div>
      {hasBreakdown && (
        <Collapsible.Content className="tile-content px-3 pb-3" data-state={open ? "open" : "closed"}>
          <div
            className="ml-7 whitespace-pre-line border-l pl-3 text-xs leading-relaxed"
            style={{ borderColor: "var(--border)", color: "var(--text-3)" }}
          >
            {breakdown}
          </div>
        </Collapsible.Content>
      )}
    </Collapsible.Root>
  );
}
