"use client"

import * as React from "react"
import { AlertTriangle, ArrowRight, ChevronDown, Flame, Radio, Target } from "lucide-react"

import { COMPANION, ageLabel, type CockpitPayload } from "@/lib/cockpit-data"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { MagicCard } from "@/components/ui/magic-card"
import { cn } from "@/lib/utils"

type Card = {
  id: string
  rank?: number
  title: string
  why?: string[]
  source_path?: string
  source_age_h?: number
  model?: string
  gated?: boolean
  autofire_safe?: boolean
  autofire_reason?: string
  prompt?: string
}

type Chip = "RED" | "AMBER" | "GOAL" | "QUEUE"

/** Infer a severity chip from the fields the payload actually carries --
 *  there is no explicit severity/kind field on a card (verified against
 *  the live payload sample), so we read title + why text for signal words. */
function inferChip(card: Card): Chip {
  const hay = `${card.title} ${(card.why || []).join(" ")}`.toLowerCase()
  if (card.id?.toLowerCase().includes("goal") || hay.includes("goal-")) return "GOAL"
  if (hay.includes("red") || hay.includes("broken") || hay.includes("failed") || hay.includes("error"))
    return "RED"
  if (hay.includes("amber") || hay.includes("stale") || hay.includes("yellow")) return "AMBER"
  return "QUEUE"
}

const CHIP_META: Record<
  Chip,
  { label: string; icon: React.ComponentType<{ className?: string }>; bg: string }
> = {
  RED: { label: "Broken", icon: AlertTriangle, bg: "linear-gradient(135deg, var(--gc-bad), var(--gc-violet))" },
  AMBER: { label: "Amber", icon: Radio, bg: "linear-gradient(135deg, var(--gc-warn), var(--gc-indigo))" },
  GOAL: { label: "Goal", icon: Target, bg: "var(--gc-grad)" },
  QUEUE: { label: "Queue", icon: Flame, bg: "var(--gc-grad)" },
}

/** Acronyms that stay upper-case when the rest of a shouty run gets
 *  Title-cased -- the domain vocabulary J actually reads by its initials. */
const KNOWN_ACRONYMS = new Set([
  "SPY", "EOD", "RTH", "PF", "CI", "TP", "ET", "VIX",
])

/** Title-case a single ALL-CAPS token (letters only, underscores/hyphens
 *  become spaces), preserving known acronyms verbatim. */
function titleCaseToken(token: string): string {
  if (KNOWN_ACRONYMS.has(token)) return token
  const words = token.split(/[_\-]+/).filter(Boolean)
  if (!words.length) return token
  return words
    .map((w) =>
      KNOWN_ACRONYMS.has(w) ? w : w.charAt(0) + w.slice(1).toLowerCase()
    )
    .join(" ")
}

/** Convert every ALL-CAPS run longer than 3 letters (ignoring underscores/
 *  hyphens inside the run) to Title case, leaving known acronyms and
 *  short/mixed-case text untouched. */
function deShout(text: string): string {
  return text.replace(/\b[A-Z][A-Z0-9_\-]{2,}\b/g, (token) => {
    const letters = token.replace(/[^A-Z]/g, "")
    if (letters.length <= 3) return token
    return titleCaseToken(token)
  })
}

/** Clip a string at a word boundary to at most `max` chars, appending an
 *  ellipsis when it was actually cut. */
function clipAtWord(text: string, max: number): string {
  if (text.length <= max) return text
  const cut = text.slice(0, max)
  const lastSpace = cut.lastIndexOf(" ")
  const base = lastSpace > max * 0.4 ? cut.slice(0, lastSpace) : cut
  return `${base.trimEnd()}…`
}

/** Turn a raw producer line -- bracketed timestamp, markdown emphasis,
 *  shouty tokens, `--` dashes, bare filenames -- into a sentence fit for
 *  the glass. Never fabricates content; only reformats what's there. */
function humanise(line: string): string {
  let s = line.replace(/^\[[0-9T:.\-]+\]\s*/, "")
  s = s.replace(/\*\*(.*?)\*\*/g, "$1")
  s = s.replace(/`([^`]*)`/g, "$1")
  s = s.replace(/\s+--\s+/g, " — ")
  s = s.replace(/\s--\s/g, " — ")
  // Bare filenames (path/to/file.ext or file.ext) -- drop the name; keep
  // "the file" only when removing it would otherwise leave a dangling verb
  // ("reads `x.json`" -> "reads the file"), else drop it outright.
  s = s.replace(
    /(\breads?|\bwrites?|\bupdated?|\bsees?)\s+\S*\/?[\w.\-]+\.(py|md|json|jsonl|csv|ts|tsx)\b/gi,
    "$1 the file"
  )
  s = s.replace(/\S*\/?[\w.\-]+\.(py|md|json|jsonl|csv|ts|tsx)\b/g, "")
  s = deShout(s)
  s = s.replace(/\s{2,}/g, " ").trim()
  s = s.replace(/\s+([,.;:])/g, "$1")
  if (!s) return "No detail recorded."
  return clipAtWord(s, 110)
}

function clipTitle(title: string, max = 44): string {
  return clipAtWord(deShout(title), max)
}

function isRthNow(data?: CockpitPayload): boolean {
  if (data?.cards?.rth_now) return true
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      hour: "numeric",
      minute: "numeric",
      hour12: false,
    }).formatToParts(new Date())
    const h = Number(parts.find((p) => p.type === "hour")?.value ?? 0)
    const m = Number(parts.find((p) => p.type === "minute")?.value ?? 0)
    const mins = h * 60 + m
    return mins >= 9 * 60 + 30 && mins <= 15 * 60 + 55
  } catch {
    return false
  }
}

function getToken(): string {
  if (typeof document === "undefined") return ""
  return document.querySelector('meta[name="gamma-token"]')?.getAttribute("content") ?? ""
}

type FireState = "idle" | "pending" | "done"

/** Fire logic shared by NeedsYou rows and the shell's "Fire top card" CTA.
 *  Ports the wiring in setup/scripts/gamma_cockpit_cards_js.py 1:1. */
export function useFireCard() {
  const [states, setStates] = React.useState<Record<string, FireState>>({})
  const [messages, setMessages] = React.useState<Record<string, string>>({})
  const [streamUrl, setStreamUrl] = React.useState<string | null>(null)
  const [streamTitle, setStreamTitle] = React.useState<string>("")

  const fire = React.useCallback(async (card: Card) => {
    if (isRthNow()) {
      setMessages((m) => ({ ...m, [card.id]: "Fire is disabled 09:30-15:55 ET." }))
      return
    }
    setStates((s) => ({ ...s, [card.id]: "pending" }))
    setMessages((m) => ({ ...m, [card.id]: "" }))
    try {
      const r = await fetch(`${COMPANION}/api/approve`, {
        method: "POST",
        headers: { "content-type": "application/json", "x-gamma-token": getToken() },
        body: JSON.stringify({
          id: card.id,
          decision: "approve",
          action: { type: "escalate", model: card.model, task: card.prompt },
        }),
      })
      const j = await r.json().catch(() => null)
      if (!j || j.ok === false) {
        setStates((s) => ({ ...s, [card.id]: "idle" }))
        setMessages((m) => ({ ...m, [card.id]: (j && j.error) || "Fire failed" }))
        return
      }
      if (!j.escalated) {
        setStates((s) => ({ ...s, [card.id]: "done" }))
        setMessages((m) => ({ ...m, [card.id]: "Already fired" }))
        return
      }
      setStates((s) => ({ ...s, [card.id]: "done" }))
      setMessages((m) => ({ ...m, [card.id]: "Fired — watching…" }))
      if (j.stream_token) {
        const url = `${COMPANION}/api/ask-stream?id=${encodeURIComponent(j.escalated)}&tok=${encodeURIComponent(j.stream_token)}`
        setStreamTitle(card.title)
        setStreamUrl(url)
      }
    } catch {
      setStates((s) => ({ ...s, [card.id]: "idle" }))
      setMessages((m) => ({ ...m, [card.id]: "Network error" }))
    }
  }, [])

  return { fire, states, messages, streamUrl, streamTitle, closeStream: () => setStreamUrl(null) }
}

function StreamDrawer({
  url,
  title,
  onOpenChange,
}: {
  url: string | null
  title: string
  onOpenChange: (open: boolean) => void
}) {
  const [lines, setLines] = React.useState<string[]>([])

  React.useEffect(() => {
    if (!url) return
    setLines([])
    let es: EventSource | null = null
    try {
      es = new EventSource(url)
    } catch {
      return
    }
    es.onmessage = (ev) => {
      try {
        const d = JSON.parse(ev.data)
        const line = frameLine(d)
        if (line) setLines((prev) => [...prev, line])
      } catch {
        // ignore malformed frames
      }
    }
    return () => es?.close()
  }, [url])

  return (
    <Sheet open={!!url} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="cockpit gc-glass w-full sm:max-w-md">
        <SheetHeader>
          <SheetTitle className="text-[var(--gc-text)]">{title} — live build</SheetTitle>
        </SheetHeader>
        <div className="mt-2 max-h-[70vh] overflow-y-auto rounded-lg border border-[var(--gc-line)] bg-black/20 p-3 text-[13px] leading-relaxed text-[var(--gc-text-2)]">
          {lines.length === 0 ? (
            <p className="text-[var(--gc-text-3)]">Waiting for the first step…</p>
          ) : (
            lines.map((l, i) => (
              <div key={i} className="whitespace-pre-wrap py-0.5">
                {l}
              </div>
            ))
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}

function frameLine(d: any): string {
  if (!d || !d.step) return ""
  switch (d.step) {
    case "queued":
      return `Queued: ${d.task || ""} (${d.model || ""})`
    case "session":
      return `Session started (${d.model || ""})`
    case "tool_start":
    case "tool":
      return `${d.label || d.name || "tool"}…`
    case "tool_result":
      return `  -> ${d.preview || (d.ok ? "ok" : "error")}`
    case "text":
    case "delta":
      return d.text || ""
    case "thinking":
      return d.text || ""
    case "result":
      return `${d.ok === false ? "FAILED: " : "DONE: "}${d.summary || ""}`
    default:
      return ""
  }
}

function CardRow({
  card,
  fire,
  state,
  message,
  rth,
}: {
  card: Card
  fire: (c: Card) => void
  state: FireState
  message?: string
  rth: boolean
}) {
  const chip = inferChip(card)
  const meta = CHIP_META[chip]
  const Icon = meta.icon
  const firstWhy = (card.why || [])[0]
  const clause = firstWhy ? humanise(firstWhy) : "No detail recorded."
  const [open, setOpen] = React.useState(false)

  const disabled = rth || state === "pending"
  const label = state === "pending" ? "Firing…" : state === "done" ? "Fired" : rth ? "Locked 09:30–15:55" : "Fire"

  return (
    <MagicCard
      className="rounded-xl border border-[var(--gc-line)]"
      gradientColor="var(--gc-violet)"
      gradientOpacity={0.15}
    >
      <div className="flex items-start gap-3 p-3">
        <div
          className="gc-icon-tile flex size-9 shrink-0 items-center justify-center rounded-lg"
          style={{ background: meta.bg }}
          aria-hidden
        >
          <Icon className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Tooltip>
              <TooltipTrigger
                render={
                  <p className="truncate text-[13px] font-medium text-[var(--gc-text)]" />
                }
              >
                {clipTitle(card.title)}
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">{card.title}</TooltipContent>
            </Tooltip>
            {card.gated && (
              <Badge variant="outline" className="border-[var(--gc-warn)] text-[var(--gc-warn)]">
                J-gated
              </Badge>
            )}
          </div>
          <p className="mt-0.5 line-clamp-2 text-[13px] text-[var(--gc-text-2)]">{clause}</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <Badge variant="secondary" className="text-[var(--gc-text-2)]">
              {meta.label}
            </Badge>
            <Badge variant="outline" className="text-[var(--gc-text-3)]">
              {card.model || "sonnet"}
            </Badge>
            <span className="text-[13px] text-[var(--gc-text-3)]">{ageLabel_h(card.source_age_h)}</span>
          </div>
          {message && <p className="mt-1 text-[13px] text-[var(--gc-text-3)]">{message}</p>}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <Button
            size="sm"
            disabled={disabled}
            onClick={() => fire(card)}
            className="border-0 text-white disabled:opacity-40"
            style={{ background: "var(--gc-grad)" }}
          >
            {label}
          </Button>
          <button
            type="button"
            aria-label="Expand"
            onClick={() => setOpen((v) => !v)}
            className="text-[var(--gc-text-3)] transition-transform hover:text-[var(--gc-text)]"
          >
            <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
          </button>
        </div>
      </div>
      {open && (
        <div className="border-t border-[var(--gc-line)] px-3 pb-3 pt-2 text-[13px] text-[var(--gc-text-2)]">
          <p className="mb-1 font-medium text-[var(--gc-text-3)]">Full detail</p>
          <ul className="space-y-1">
            {(card.why || []).map((w, i) => (
              <li key={i}>{humanise(w)}</li>
            ))}
          </ul>
          {card.prompt && (
            <p className="mt-2 text-[var(--gc-text-3)]">Objective: {firstSentence(card.prompt)}</p>
          )}
          <p className="mt-2 text-[var(--gc-text-3)]">Source age: {ageLabel_h(card.source_age_h)}</p>
        </div>
      )}
    </MagicCard>
  )
}

function ageLabel_h(hours?: number): string {
  if (hours === undefined || hours === null || Number.isNaN(hours)) return "NO DATA"
  const mins = Math.round(hours * 60)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins} min ago`
  const h = Math.round(mins / 60)
  if (h < 48) return `${h} h ago`
  return `${Math.round(h / 24)} d ago`
}

function firstSentence(s: string): string {
  const idx = s.indexOf("\n")
  const line = idx > -1 ? s.slice(0, idx) : s
  return line.replace(/^OBJECTIVE:\s*/i, "").slice(0, 160)
}

export function NeedsYou({ data, limit = 5 }: { data: CockpitPayload; limit?: number }) {
  const cards: Card[] = data?.cards?.cards ?? []
  const rth = isRthNow(data)
  const { fire, states, messages, streamUrl, streamTitle, closeStream } = useFireCard()
  const [viewAll, setViewAll] = React.useState(false)

  const visible = cards.slice(0, limit)

  return (
    <section className="cockpit gc-glass gc-glow rounded-2xl p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="gc-grad-text text-[15px] font-semibold">Needs you ({cards.length})</h2>
        <Sheet open={viewAll} onOpenChange={setViewAll}>
          <SheetTrigger
            render={<Button variant="ghost" size="sm" className="gap-1 text-[var(--gc-text-2)]" />}
          >
            View all
            <ArrowRight className="size-3.5" />
          </SheetTrigger>
          <SheetContent side="right" className="cockpit gc-glass w-full sm:max-w-lg">
            <SheetHeader>
              <SheetTitle className="text-[var(--gc-text)]">
                Needs you — full queue ({cards.length})
              </SheetTitle>
            </SheetHeader>
            <div className="mt-3 max-h-[80vh] space-y-2 overflow-y-auto pr-1">
              {cards.length === 0 ? (
                <p className="text-[13px] text-[var(--gc-text-3)]">NO DATA</p>
              ) : (
                cards.map((c) => (
                  <CardRow
                    key={c.id}
                    card={c}
                    fire={fire}
                    state={states[c.id] ?? "idle"}
                    message={messages[c.id]}
                    rth={rth}
                  />
                ))
              )}
            </div>
          </SheetContent>
        </Sheet>
      </div>

      {cards.length === 0 ? (
        <p className="text-[13px] text-[var(--gc-text-3)]">NO DATA</p>
      ) : (
        <div className="space-y-2">
          {visible.map((c) => (
            <CardRow
              key={c.id}
              card={c}
              fire={fire}
              state={states[c.id] ?? "idle"}
              message={messages[c.id]}
              rth={rth}
            />
          ))}
        </div>
      )}

      {data?.cards?.legend && (
        <p className="mt-3 text-[13px] text-[var(--gc-text-3)]">{data.cards.legend}</p>
      )}

      <StreamDrawer url={streamUrl} title={streamTitle} onOpenChange={(open) => !open && closeStream()} />
    </section>
  )
}
