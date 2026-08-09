"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import useSWR from "swr";
import { Send } from "lucide-react";
import type { LatestSpeech } from "@/lib/dialogue";

const SPEECH_REFRESH_MS = 30_000;
const MAX_LOG = 8;

interface SpeechResponse {
  ok: boolean;
  speech: LatestSpeech | null;
}

interface ChatResponse {
  ok: boolean;
  offline?: boolean;
  reply: string;
  escalating?: boolean;
  error?: string;
}

interface ChatTurn {
  role: "user" | "gamma";
  text: string;
  escalating?: boolean;
}

async function fetchSpeech(url: string): Promise<SpeechResponse> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as SpeechResponse;
}

function relativeTime(iso: string, nowMs: number): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const diffSec = Math.max(0, Math.round((nowMs - then) / 1000));
  if (diffSec < 60) return "just now";
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  return `${diffDay}d ago`;
}

// Agent keys that represent Gamma flagging something for J vs routine
// narration -- purely cosmetic (orb color), never gates any action.
const URGENT_AGENTS = new Set(["entry_block_watch"]);

/**
 * THE GAMMA PRESENCE UNIT -- an avatar + real speech bubble + a compact chat
 * input. Two independent data sources, both real:
 *
 *  1. The speech bubble (top) shows automation/state/dashboard-dialogue.json's
 *     freshest agent narration via GET /api/gamma-chat -- this is REAL
 *     production speech already written by the daily personas, not invented
 *     copy. Polls every 30s; fails open to a quiet placeholder when there is
 *     none / it's stale beyond 24h.
 *
 *  2. The chat (bottom) POSTs to /api/gamma-chat, which proxies to the
 *     ALREADY-RUNNING gamma-companion server (127.0.0.1:4317). A reply is a
 *     REAL round trip through the companion's free-model face (which may
 *     escalate to Claude) -- never a mock. If the companion is unreachable,
 *     the honest offline copy from the API is shown as-is, never hidden or
 *     replaced with a fabricated answer.
 *
 * There is no reused mascot graphic in this repo (the pixel sprites under
 * gamma-companion/public/assets are a generic office scene, not a Gamma
 * character) -- the avatar is an animated orb whose pulse state reflects
 * real activity (idle / thinking / flagging something urgent) rather than an
 * invented cartoon.
 */
export default function GammaPresence() {
  const [nowMs, setNowMs] = useState<number>(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 15_000);
    return () => clearInterval(id);
  }, []);

  const { data: speechData } = useSWR<SpeechResponse>("/api/gamma-chat", fetchSpeech, {
    refreshInterval: SPEECH_REFRESH_MS,
    keepPreviousData: true,
  });
  const speech = speechData?.speech ?? null;

  const [log, setLog] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  const logEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ block: "end" });
  }, [log, isThinking]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const message = input.trim();
    if (!message || isThinking) return;

    setLog((prev) => [...prev.slice(-(MAX_LOG - 1)), { role: "user", text: message }]);
    setInput("");
    setIsThinking(true);

    try {
      const res = await fetch("/api/gamma-chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ message }),
      });
      const data = (await res.json()) as ChatResponse;
      setLog((prev) => [
        ...prev.slice(-(MAX_LOG - 1)),
        { role: "gamma", text: data.reply || "(no reply)", escalating: !!data.escalating },
      ]);
    } catch {
      setLog((prev) => [
        ...prev.slice(-(MAX_LOG - 1)),
        { role: "gamma", text: "Couldn't reach Gamma's voice brain — try again in a moment." },
      ]);
    } finally {
      setIsThinking(false);
    }
  }

  const isUrgent = !!speech && URGENT_AGENTS.has(speech.agent);
  const orbAccent = isThinking ? "var(--violet)" : isUrgent ? "var(--amber)" : "var(--cyan)";
  const orbGlow = isThinking ? "var(--violet-soft)" : isUrgent ? "var(--amber-soft)" : "var(--cyan-glow)";
  const pulseDuration = isThinking ? "0.9s" : "2.6s";

  return (
    <div
      className="flex flex-col gap-4 rounded-[var(--radius-lg)] border p-4"
      style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
    >
      <div className="flex items-start gap-3">
        <div
          className="relative h-11 w-11 shrink-0 rounded-full"
          style={{
            background: `radial-gradient(circle at 35% 30%, ${orbGlow}, ${orbAccent} 75%)`,
            boxShadow: `0 0 18px ${orbGlow}`,
            animation: `pulse ${pulseDuration} ease-in-out infinite`,
          }}
          aria-hidden
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold" style={{ color: "var(--text-1)" }}>
              Gamma
            </span>
            {speech && (
              <span className="text-[11px]" style={{ color: "var(--text-4)" }}>
                {speech.agent} · {relativeTime(speech.lastActiveAt, nowMs)}
              </span>
            )}
          </div>
          <p
            className="mt-1 rounded-[var(--radius)] border px-3 py-2 text-sm leading-snug"
            style={{
              borderColor: isUrgent ? "rgba(245, 158, 11, 0.3)" : "var(--border)",
              background: isUrgent ? "var(--amber-soft)" : "var(--bg-overlay)",
              color: "var(--text-1)",
            }}
          >
            {speech ? speech.speech : "No recent word from the floor — quiet right now."}
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        {log.length > 0 && (
          <div className="flex max-h-40 flex-col gap-1.5 overflow-y-auto pr-1">
            {log.map((turn, i) => (
              <div
                key={i}
                className="rounded-[var(--radius-sm)] px-2.5 py-1.5 text-xs leading-snug"
                style={{
                  alignSelf: turn.role === "user" ? "flex-end" : "flex-start",
                  maxWidth: "88%",
                  background: turn.role === "user" ? "var(--bg-overlay)" : "var(--cyan-soft)",
                  color: "var(--text-1)",
                }}
              >
                {turn.text}
                {turn.escalating && (
                  <span className="ml-1.5 text-[10px]" style={{ color: "var(--text-4)" }}>
                    (started a background task)
                  </span>
                )}
              </div>
            ))}
            {isThinking && (
              <div
                className="self-start rounded-[var(--radius-sm)] px-2.5 py-1.5 text-xs italic"
                style={{ background: "var(--cyan-soft)", color: "var(--text-3)" }}
              >
                thinking…
              </div>
            )}
            <div ref={logEndRef} />
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex items-center gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Talk to Gamma…"
            disabled={isThinking}
            className="flex-1 rounded-[var(--radius)] border bg-transparent px-3 py-1.5 text-sm outline-none"
            style={{ borderColor: "var(--border-mid)", color: "var(--text-1)" }}
          />
          <button
            type="submit"
            disabled={isThinking || !input.trim()}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius)] border disabled:opacity-40"
            style={{ borderColor: "var(--border-mid)", color: "var(--cyan)" }}
            aria-label="Send"
          >
            <Send size={14} />
          </button>
        </form>
      </div>
    </div>
  );
}
