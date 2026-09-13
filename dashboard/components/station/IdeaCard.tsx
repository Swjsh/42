"use client";

import { useState } from "react";
import { Flame, Skull, MessageCircleQuestion, ChevronDown } from "lucide-react";
import type { StationIdeaCard } from "@/lib/station";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

function ageLabel(tsEt: string): string {
  // ts_et is "YYYY-MM-DD HH:MM:SS ET" -- parseable as a plain wall-clock
  // string; treating it as local-ish for a coarse "Xh ago" badge is fine
  // here (unlike a trade fill, a rough idea-card age needs no DST precision).
  const cleaned = tsEt.replace(" ET", "").replace(" ", "T");
  const t = Date.parse(cleaned);
  if (Number.isNaN(t)) return tsEt;
  const hours = (Date.now() - t) / 3.6e6;
  if (hours < 0) return "just now";
  if (hours < 1) return `${Math.round(hours * 60)}m ago`;
  if (hours < 48) return `${hours.toFixed(1)}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

const CONFIDENCE_TONE: Record<string, "default" | "secondary" | "outline"> = {
  high: "default",
  med: "secondary",
  low: "outline",
};

const STATUS_LABEL: Record<string, string> = {
  proposed: "Proposed",
  testing: "Testing",
  killed: "Killed",
  shipped: "Shipped",
  supported: "Supported",
  refuted: "Refuted",
};

// Amendment 5b (2026-09-13): supported = green (the hypothesis held up),
// refuted = grey (settled, dead -- not an error/red, just closed). A separate
// builder writes these statuses once a card's shadow test actually runs;
// this component only ever renders the status it's given.
const STATUS_BADGE_VARIANT: Record<string, "default" | "destructive" | "outline" | "secondary"> = {
  shipped: "default",
  supported: "default",
  killed: "destructive",
  refuted: "secondary",
};

export type CardAction = "test" | "kill" | "ask";

interface IdeaCardProps {
  card: StationIdeaCard;
  kiosk: boolean;
  onAction: (cardId: string, action: CardAction, note: string) => Promise<void>;
}

export default function IdeaCard({ card, kiosk, onAction }: IdeaCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [asking, setAsking] = useState(false);
  const [note, setNote] = useState("");
  const [pending, setPending] = useState<CardAction | null>(null);
  const [message, setMessage] = useState<string>("");
  const dead = card.status === "killed";

  async function fire(action: CardAction, noteText = "") {
    setPending(action);
    setMessage("");
    try {
      await onAction(card.id, action, noteText);
      setMessage(action === "ask" ? "Sent -- Gamma will answer in the next brief." : "Done.");
      if (action === "ask") {
        setAsking(false);
        setNote("");
      }
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Action failed.");
    } finally {
      setPending(null);
    }
  }

  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-card p-3 text-sm",
        dead && "opacity-50",
      )}
    >
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium text-foreground">{card.title}</p>
          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{card.mechanism}</p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-1">
          <Badge variant={CONFIDENCE_TONE[card.confidence] ?? "outline"}>{card.confidence || "?"}</Badge>
          <Badge variant={STATUS_BADGE_VARIANT[card.status] ?? "outline"}>
            {STATUS_LABEL[card.status] ?? card.status}
          </Badge>
        </div>
      </div>

      {card.verdict && (
        <p className="mt-1.5 text-xs text-muted-foreground">
          verdict: <span className="font-medium text-foreground">{card.verdict}</span>
          {card.verdict_n_pre != null && ` · in-sample n=${card.verdict_n_pre}`}
          {card.verdict_n_post != null && ` · post-registration n=${card.verdict_n_post}`}
        </p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>{ageLabel(card.ts_et)}</span>
        <span>&middot;</span>
        <span>{card.cost_line || "cost unknown"}</span>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="ml-auto flex items-center gap-1 text-foreground/70 hover:text-foreground"
        >
          Detail
          <ChevronDown className={cn("size-3.5 transition-transform", expanded && "rotate-180")} />
        </button>
      </div>

      {expanded && (
        <div className="mt-2 space-y-2 border-t border-border pt-2 text-xs text-muted-foreground">
          {card.evidence.length > 0 && (
            <ul className="list-disc space-y-1 pl-4">
              {card.evidence.slice(0, 8).map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          )}
          {card.proposed_shadow_test && (
            <p>
              <span className="font-medium text-foreground/80">Shadow test: </span>
              {card.proposed_shadow_test}
            </p>
          )}
        </div>
      )}

      {!kiosk && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={dead || pending !== null}
            onClick={() => fire("test")}
          >
            <Flame className="size-3.5" />
            {pending === "test" ? "Marking..." : "Test"}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={dead || pending !== null}
            onClick={() => fire("kill")}
          >
            <Skull className="size-3.5" />
            {pending === "kill" ? "Killing..." : "Kill"}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={pending !== null}
            onClick={() => setAsking((v) => !v)}
          >
            <MessageCircleQuestion className="size-3.5" />
            Ask
          </Button>
          {message && <span className="text-xs text-muted-foreground">{message}</span>}
        </div>
      )}

      {!kiosk && asking && (
        <div className="mt-2 flex flex-col gap-2">
          <Textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="What do you want Gamma to answer about this card?"
            className="min-h-16 text-sm"
          />
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setAsking(false)}>
              Cancel
            </Button>
            <Button size="sm" disabled={!note.trim() || pending !== null} onClick={() => fire("ask", note.trim())}>
              {pending === "ask" ? "Sending..." : "Send"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
