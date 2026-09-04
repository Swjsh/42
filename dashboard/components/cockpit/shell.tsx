"use client";

import * as React from "react";
import {
  Command as CommandIcon,
  BookOpen,
  MessagesSquare,
  Users,
  ChefHat,
  FlaskConical,
  Cpu,
  Search,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Badge } from "@/components/ui/badge";
import { ShimmerButton } from "@/components/ui/shimmer-button";
import { DotPattern } from "@/components/ui/dot-pattern";
import { fmtUsd, type CockpitPayload } from "@/lib/cockpit-data";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { id: "command", label: "Command", icon: CommandIcon },
  { id: "journal", label: "Journal", icon: BookOpen },
  { id: "answers", label: "Answers", icon: MessagesSquare },
  { id: "army", label: "Army", icon: Users },
  { id: "kitchen", label: "Kitchen", icon: ChefHat },
  { id: "research", label: "Research", icon: FlaskConical },
  { id: "rig", label: "Rig", icon: Cpu },
] as const;

/** data.generated_et is an ET wall-clock string ("YYYY-MM-DD HH:MM[:SS]",
 *  no offset/zone) -- lib's ageLabel() runs Date.parse() on it, which fails
 *  on that shape (not ISO-8601) and always falls back to "NO DATA". This
 *  parses it as America/New_York via the Intl-offset trick (build a UTC
 *  guess from the literal digits, then correct by that zone's actual offset
 *  at that instant, which absorbs DST automatically) and renders a real
 *  age. Falsy/malformed input still renders visibly rather than silently
 *  claiming "NO DATA" for a string that is actually present. */
function etStringToDate(s: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$/.exec(s.trim());
  if (!m) return null;
  const [, y, mo, d, h, mi, se] = m;
  const utcGuessMs = Date.UTC(+y, +mo - 1, +d, +h, +mi, +(se ?? 0));
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      timeZoneName: "shortOffset",
    }).formatToParts(new Date(utcGuessMs));
    const offsetStr = parts.find((p) => p.type === "timeZoneName")?.value ?? "GMT-5";
    const offsetMatch = /GMT([+-]\d+)/.exec(offsetStr);
    const offsetHours = offsetMatch ? Number(offsetMatch[1]) : -5;
    return new Date(utcGuessMs - offsetHours * 3600_000);
  } catch {
    return null;
  }
}

function payloadAgeLabel(raw?: string | null): string {
  if (!raw) return "NO DATA";
  const dt = etStringToDate(raw);
  if (!dt) return raw;
  const mins = Math.max(0, Math.round((Date.now() - dt.getTime()) / 60000));
  if (mins < 1) return "Updated just now";
  if (mins < 60) return `Updated ${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `Updated ${hours} h ago`;
  return `Updated ${Math.round(hours / 24)} d ago`;
}

function scrollToAnchor(id: string) {
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

interface CockpitShellProps {
  children: React.ReactNode;
  data: CockpitPayload;
  onFireTop?: () => void;
  /** false when the companion (127.0.0.1:4317) did not answer the token bootstrap. */
  companionOnline?: boolean;
}

export function CockpitShell({ children, data, onFireTop, companionOnline = true }: CockpitShellProps) {
  const [collapsed, setCollapsed] = React.useState(false);
  const [active, setActive] = React.useState<string>("command");
  const [paletteOpen, setPaletteOpen] = React.useState(false);

  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  React.useEffect(() => {
    const sections = NAV_ITEMS.map((n) => document.getElementById(n.id)).filter(
      (el): el is HTMLElement => !!el
    );
    if (!sections.length) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible?.target?.id) setActive(visible.target.id);
      },
      { rootMargin: "-20% 0px -60% 0px", threshold: [0.1, 0.3, 0.6] }
    );
    sections.forEach((s) => observer.observe(s));
    return () => observer.disconnect();
  }, [children]);

  const verdict: string | undefined =
    data?.gate?.overall_verdict ?? data?.gate?.verdict;
  const isLive = typeof verdict === "string" && verdict.toUpperCase() === "GREEN";
  const marketOpen: boolean | undefined = data?.glass?.market_open;

  const sessions: Array<Record<string, any>> = Array.isArray(data?.army?.sessions)
    ? data.army.sessions
    : [];
  const agentsRunning = sessions.filter(
    (s) => s?.alive && s?.activity !== "stale"
  ).length;

  const cardsList: Array<Record<string, any>> = Array.isArray(data?.cards?.cards)
    ? data.cards.cards
    : [];
  const needCount = cardsList.length;

  const bookWeek = fmtUsd(data?.glass?.pnl?.week);
  const generatedAge = payloadAgeLabel(data?.generated_et);
  const marketLabel = marketOpen === undefined ? "NO DATA" : marketOpen ? "Market open" : "After hours";

  const paletteEntries = [
    ...NAV_ITEMS.map((n) => ({ kind: "nav" as const, id: n.id, label: n.label })),
    ...cardsList.slice(0, 20).map((c, i) => ({
      kind: "card" as const,
      id: c?.id ?? `card-${i}`,
      label: typeof c?.title === "string" ? c.title : "Untitled card",
    })),
  ];

  return (
    <div className="cockpit min-h-screen flex">
      <aside
        className={cn(
          "sticky top-0 h-screen shrink-0 flex flex-col gc-glass border-r border-[var(--gc-line)] overflow-hidden transition-[width] duration-300 relative",
          collapsed ? "w-[64px]" : "w-[220px]"
        )}
      >
        <DotPattern
          className="absolute inset-0 opacity-[0.25] [mask-image:radial-gradient(ellipse_at_top,white,transparent_75%)]"
          glow
        />
        <div className="relative z-10 flex items-center gap-2 px-3 h-14 shrink-0 border-b border-[var(--gc-line)]">
          <span className="text-lg font-bold gc-grad-text shrink-0">Γ</span>
          {!collapsed && (
            <span className="text-[13px] font-semibold tracking-wide text-[var(--gc-text)] truncate">
              Gamma
            </span>
          )}
          <button
            type="button"
            aria-label={collapsed ? "Expand nav" : "Collapse nav"}
            onClick={() => setCollapsed((v) => !v)}
            className="ml-auto text-[var(--gc-text-3)] hover:text-[var(--gc-text)] transition-colors shrink-0"
          >
            {collapsed ? <ChevronsRight size={16} /> : <ChevronsLeft size={16} />}
          </button>
        </div>

        <nav className="relative z-10 flex-1 overflow-y-auto py-3 px-2 flex flex-col gap-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = active === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => scrollToAnchor(item.id)}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-2.5 py-2 text-[13px] transition-all relative",
                  isActive
                    ? "text-[var(--gc-text)] gc-glow"
                    : "text-[var(--gc-text-2)] hover:text-[var(--gc-text)] hover:bg-[var(--gc-line)]/40"
                )}
                style={isActive ? { background: "var(--gc-grad)" } : undefined}
              >
                <Icon size={16} className="shrink-0" />
                {!collapsed && <span className="truncate">{item.label}</span>}
              </button>
            );
          })}
        </nav>

        <div className="relative z-10 px-3 py-3 border-t border-[var(--gc-line)] text-[13px] text-[var(--gc-text-3)] flex flex-col gap-1">
          {!collapsed ? (
            <>
              <span>{marketLabel}</span>
              <span>{generatedAge}</span>
            </>
          ) : (
            <span title={marketLabel}>{marketOpen ? "●" : "○"}</span>
          )}
        </div>
      </aside>

      <div className="flex-1 min-w-0 flex flex-col">
        <header className="sticky top-0 z-20 gc-glass border-b border-[var(--gc-line)] px-6 py-3 flex flex-wrap items-center gap-3">
          <div className="flex flex-col min-w-0 mr-2">
            <h1 className="text-lg font-semibold text-[var(--gc-text)] leading-tight">
              Gamma Command Center
            </h1>
            <div className="flex flex-wrap items-center gap-2 mt-1">
              <Badge
                className={cn(
                  "text-[13px] px-2 py-0.5",
                  isLive
                    ? "bg-[var(--gc-good)]/20 text-[var(--gc-good)] border-[var(--gc-good)]/40"
                    : "bg-[var(--gc-bad)]/20 text-[var(--gc-bad)] border-[var(--gc-bad)]/40"
                )}
              >
                {verdict ? (isLive ? "LIVE" : "NOT LIVE") : "NO DATA"}
              </Badge>
              <Badge className="text-[13px] px-2 py-0.5 bg-[var(--gc-line)] text-[var(--gc-text-2)] border-[var(--gc-line-strong)]">
                {marketLabel}
              </Badge>
              <Badge className="text-[13px] px-2 py-0.5 bg-[var(--gc-indigo)]/20 text-[var(--gc-text)] border-[var(--gc-indigo)]/40">
                {agentsRunning} agent{agentsRunning === 1 ? "" : "s"} running
              </Badge>
              <Badge className="text-[13px] px-2 py-0.5 bg-[var(--gc-warn)]/20 text-[var(--gc-warn)] border-[var(--gc-warn)]/40">
                {needCount} need you
              </Badge>
              <Badge className="text-[13px] px-2 py-0.5 bg-[var(--gc-line)] text-[var(--gc-text-2)] border-[var(--gc-line-strong)]">
                Book week {bookWeek}
              </Badge>
              {!companionOnline && (
                <Badge className="text-[13px] px-2 py-0.5 bg-[var(--gc-bad)]/20 text-[var(--gc-bad)] border-[var(--gc-bad)]/40">
                  Companion offline
                </Badge>
              )}
            </div>
          </div>

          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPaletteOpen(true)}
              className="flex items-center gap-2 rounded-lg gc-glass px-3 py-1.5 text-[13px] text-[var(--gc-text-3)] hover:text-[var(--gc-text)] transition-colors"
            >
              <Search size={14} />
              <span>Search</span>
              <kbd className="ml-2 rounded border border-[var(--gc-line-strong)] px-1.5 py-0.5 text-[11px]">
                ⌘K
              </kbd>
            </button>
            <ShimmerButton
              onClick={() => onFireTop?.()}
              background="var(--gc-grad)"
              className="text-[13px] px-4 py-2"
            >
              Fire top card
            </ShimmerButton>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto px-6 py-6 flex flex-col gap-8">
          {children}
        </main>
      </div>

      <CommandDialog open={paletteOpen} onOpenChange={setPaletteOpen}>
        <CommandInput placeholder="Jump to a section or a card..." />
        <CommandList>
          <CommandEmpty>No matches.</CommandEmpty>
          <CommandGroup heading="Sections">
            {paletteEntries
              .filter((e) => e.kind === "nav")
              .map((e) => (
                <CommandItem
                  key={e.id}
                  value={e.label}
                  onSelect={() => {
                    scrollToAnchor(e.id);
                    setPaletteOpen(false);
                  }}
                >
                  {e.label}
                </CommandItem>
              ))}
          </CommandGroup>
          <CommandGroup heading="Cards needing you">
            {paletteEntries
              .filter((e) => e.kind === "card")
              .map((e) => (
                <CommandItem
                  key={e.id}
                  value={e.label}
                  onSelect={() => {
                    scrollToAnchor("command");
                    setPaletteOpen(false);
                  }}
                >
                  {e.label}
                </CommandItem>
              ))}
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </div>
  );
}
