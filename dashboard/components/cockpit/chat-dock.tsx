"use client";

/**
 * ChatDock -- bottom-right docked chat with the Gamma orchestrator.
 *
 * Protocol ported EXACTLY from setup/scripts/gamma_cockpit_chat_js.py (CHAT_JS):
 *   POST /companion/api/orchestrator-chat  { message, model, resume?, fresh? }
 *     -> { ok, ask_id, stream_token, resumed, resumed_from }
 *   EventSource /companion/api/ask-stream?id=<ask_id>&tok=<stream_token>
 *     step shapes handled: "session" (sessionId -> resume next turn),
 *     "delta" (streamed text), "text" (fallback full text, only if no delta seen),
 *     "thinking", "tool"/"tool_start", "tool_result", "result" (ok/summary, closes stream).
 *
 * Persistence mirrors the old localStorage key "gamma-chat-v1": {session, model, messages}.
 * Token comes from <meta name="gamma-token">; empty token disables send.
 */

import * as React from "react";
import { Sparkles, Send, X, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ShimmerButton } from "@/components/ui/shimmer-button";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "gamma-chat-v1";
const MODELS = ["opus", "sonnet", "haiku"] as const;
type GammaModel = (typeof MODELS)[number];

type StepStatus = "info" | "ok" | "bad" | "dim";

interface ChatStep {
  id: string;
  label: string;
  status: StepStatus;
}

interface ChatMessage {
  id: string;
  role: "user" | "gamma";
  text: string;
  model?: string;
  steps?: ChatStep[];
  sawDelta?: boolean;
}

interface PersistedState {
  session: string | null;
  model: GammaModel;
  messages: { role: "user" | "gamma"; text: string; model?: string }[];
}

function uid(): string {
  return "t" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

function getGammaToken(): string {
  if (typeof document === "undefined") return "";
  const meta = document.querySelector('meta[name="gamma-token"]');
  return meta?.getAttribute("content") ?? "";
}

function loadPersisted(): PersistedState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed) return null;
    return parsed as PersistedState;
  } catch {
    return null;
  }
}

function savePersisted(session: string | null, model: GammaModel, messages: ChatMessage[]) {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        session,
        model,
        messages: messages.slice(-40).map((m) => ({ role: m.role, text: m.text, model: m.model })),
      }),
    );
  } catch {
    // private window / cleared storage -- degrade silently
  }
}

export function ChatDock() {
  const [open, setOpen] = React.useState(false);
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [input, setInput] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [model, setModel] = React.useState<GammaModel>("opus");
  const [restored, setRestored] = React.useState(false);

  const sessionRef = React.useRef<string | null>(null);
  const freshNextRef = React.useRef(false);
  const esRef = React.useRef<EventSource | null>(null);
  const scrollBottomRef = React.useRef<HTMLDivElement | null>(null);
  const tokenRef = React.useRef<string>("");

  React.useEffect(() => {
    tokenRef.current = getGammaToken();
    const saved = loadPersisted();
    if (saved) {
      if (saved.session) sessionRef.current = saved.session;
      if (saved.model && MODELS.includes(saved.model)) setModel(saved.model);
      if (Array.isArray(saved.messages) && saved.messages.length) {
        setMessages(
          saved.messages
            .filter((m) => m && m.text)
            .map((m) => ({ id: uid(), role: m.role, text: m.text, model: m.model })),
        );
        setRestored(true);
      }
    }
  }, []);

  React.useEffect(() => {
    if (!open) return;
    scrollBottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages, open]);

  React.useEffect(() => {
    return () => {
      esRef.current?.close();
    };
  }, []);

  function appendStep(msgId: string, label: string, status: StepStatus) {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === msgId ? { ...m, steps: [...(m.steps ?? []), { id: uid(), label, status }] } : m,
      ),
    );
  }

  function appendText(msgId: string, chunk: string) {
    setMessages((prev) =>
      prev.map((m) => (m.id === msgId ? { ...m, text: m.text + chunk, sawDelta: true } : m)),
    );
  }

  function setTextIfNoDelta(msgId: string, text: string) {
    setMessages((prev) =>
      prev.map((m) => (m.id === msgId && !m.sawDelta ? { ...m, text: m.text + text } : m)),
    );
  }

  function stopStream() {
    esRef.current?.close();
    esRef.current = null;
    setBusy(false);
  }

  function newSession() {
    esRef.current?.close();
    esRef.current = null;
    sessionRef.current = null;
    freshNextRef.current = true;
    setBusy(false);
    setMessages([]);
    savePersisted(null, model, []);
  }

  function handleModelChange(next: GammaModel) {
    setModel(next);
    sessionRef.current = null;
    freshNextRef.current = true;
    savePersisted(null, next, messages);
  }

  async function send() {
    const token = tokenRef.current;
    const text = input.trim();
    if (!text || busy || !token) return;
    setInput("");

    const userMsg: ChatMessage = { id: uid(), role: "user", text };
    const gammaMsg: ChatMessage = { id: uid(), role: "gamma", text: "", model, steps: [] };
    setMessages((prev) => {
      const next = [...prev, userMsg, gammaMsg];
      savePersisted(sessionRef.current, model, next);
      return next;
    });
    setBusy(true);

    try {
      const res = await fetch("/companion/api/orchestrator-chat", {
        method: "POST",
        headers: { "content-type": "application/json", "x-gamma-token": token },
        body: JSON.stringify({
          message: text,
          model,
          resume: sessionRef.current || undefined,
          fresh: freshNextRef.current || undefined,
        }),
      });
      const j = await res.json();
      if (!j || j.ok === false) {
        appendStep(gammaMsg.id, "✕ " + ((j && j.error) || "failed"), "bad");
        setBusy(false);
        return;
      }
      freshNextRef.current = false;
      if (j.resumed_from === "store") appendStep(gammaMsg.id, "↻ continuing the stored session", "dim");

      const url =
        "/companion/api/ask-stream?id=" +
        encodeURIComponent(j.ask_id) +
        "&tok=" +
        encodeURIComponent(j.stream_token);

      let es: EventSource;
      try {
        es = new EventSource(url);
      } catch {
        appendStep(gammaMsg.id, "✕ stream unavailable", "bad");
        setBusy(false);
        return;
      }
      esRef.current = es;

      es.onmessage = (ev) => {
        let d: any = null;
        try {
          d = JSON.parse(ev.data);
        } catch {
          return;
        }
        if (!d || !d.step) return;

        if (d.step === "session" && d.sessionId) {
          sessionRef.current = d.sessionId;
          savePersisted(sessionRef.current, model, messages);
          appendStep(
            gammaMsg.id,
            (j.resumed ? "↻ resumed" : "● session") + " " + String(d.sessionId).slice(0, 8),
            "dim",
          );
        } else if (d.step === "delta") {
          appendText(gammaMsg.id, d.text || "");
        } else if (d.step === "text") {
          setTextIfNoDelta(gammaMsg.id, d.text || "");
        } else if (d.step === "thinking") {
          appendStep(gammaMsg.id, "thinking…", "dim");
        } else if (d.step === "tool" || d.step === "tool_start") {
          appendStep(gammaMsg.id, "▸ " + (d.label || d.name || "tool"), "info");
        } else if (d.step === "tool_result") {
          appendStep(gammaMsg.id, "   " + (d.preview || (d.ok ? "ok" : "error")), "dim");
        } else if (d.step === "result") {
          appendStep(gammaMsg.id, (d.ok === false ? "✕ " : "✓ ") + (d.summary || ""), d.ok === false ? "bad" : "ok");
          if (d.ok === false && /error|timeout/.test(d.subtype || "") && j.resumed) {
            sessionRef.current = null;
            freshNextRef.current = true;
          }
          setMessages((prev) => {
            savePersisted(sessionRef.current, model, prev);
            return prev;
          });
          stopStream();
        }
      };
      es.onerror = () => {
        // EventSource retries on its own; the durable feed replays on reconnect
      };
    } catch {
      appendStep(gammaMsg.id, "✕ network error", "bad");
      setBusy(false);
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  }

  const hasToken = tokenRef.current !== "" || (typeof document !== "undefined" && getGammaToken() !== "");

  if (!open) {
    return (
      <div className="cockpit fixed bottom-5 right-5 z-50">
        <ShimmerButton
          onClick={() => setOpen(true)}
          background="var(--gc-grad)"
          shimmerColor="#ffffff"
          className="gc-glow gap-2 px-4 py-2.5 text-sm font-medium"
        >
          <Sparkles className="size-4" />
          Chat with Gamma
        </ShimmerButton>
      </div>
    );
  }

  return (
    <div className="cockpit fixed bottom-5 right-5 z-50 flex h-[560px] w-[400px] flex-col overflow-hidden rounded-2xl gc-glass gc-glow">
      {/* header */}
      <div className="flex items-center gap-2 border-b px-3 py-2.5" style={{ borderColor: "var(--gc-line)" }}>
        <Avatar className="size-7 shrink-0">
          <AvatarFallback className="gc-grad-text text-xs font-bold" style={{ background: "var(--gc-grad)", color: "white" }}>
            &Gamma;
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-medium" style={{ color: "var(--gc-text)" }}>
            Gamma orchestrator
          </div>
        </div>
        <select
          aria-label="model"
          value={model}
          disabled={busy}
          onChange={(e) => handleModelChange(e.target.value as GammaModel)}
          className="h-6 rounded-md border bg-transparent px-1.5 text-[11px] outline-none disabled:opacity-50"
          style={{ borderColor: "var(--gc-line-strong)", color: "var(--gc-text-2)" }}
        >
          {MODELS.map((m) => (
            <option key={m} value={m} style={{ background: "var(--gc-panel-solid)" }}>
              {m}
            </option>
          ))}
        </select>
        <Badge variant="outline" className="hidden shrink-0 text-[11px] sm:inline-flex">
          {model}
        </Badge>
        <Button
          variant="ghost"
          size="icon"
          className="size-7 shrink-0"
          onClick={newSession}
          title="new session"
        >
          <RotateCcw className="size-3.5" />
        </Button>
        <Button variant="ghost" size="icon" className="size-7 shrink-0" onClick={() => setOpen(false)}>
          <X className="size-3.5" />
        </Button>
      </div>

      {/* messages */}
      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-3 p-3">
          {restored && (
            <div className="text-center text-[11px]" style={{ color: "var(--gc-text-3)" }}>
              -- restored, same session continues --
            </div>
          )}
          {messages.length === 0 && (
            <div className="mt-8 flex flex-col items-center gap-1 text-center">
              <div className="text-[13px] font-medium" style={{ color: "var(--gc-text-2)" }}>
                Talk to the orchestrator
              </div>
              <div className="max-w-[280px] text-[12px]" style={{ color: "var(--gc-text-3)" }}>
                A real Claude session that runs in this page and remembers the conversation.
              </div>
            </div>
          )}
          {messages.map((m) => (
            <div key={m.id} className={cn("flex flex-col gap-1", m.role === "user" ? "items-end" : "items-start")}>
              <div
                className={cn(
                  "max-w-[85%] rounded-xl px-3 py-2 text-[13px] leading-relaxed whitespace-pre-wrap break-words",
                  m.role === "user" ? "bg-muted" : "gc-glass",
                )}
                style={
                  m.role === "user"
                    ? { background: "var(--gc-line-strong)", color: "var(--gc-text)" }
                    : { color: "var(--gc-text)" }
                }
              >
                {m.text || (m.role === "gamma" && busy ? "…" : "")}
              </div>
              {m.role === "gamma" && m.steps && m.steps.length > 0 && (
                <div className="flex max-w-[85%] flex-col gap-0.5 pl-1">
                  {m.steps.map((s) => (
                    <div key={s.id} className="flex items-center gap-1.5 text-[11px]" style={{ color: "var(--gc-text-3)" }}>
                      <span
                        className="inline-block size-1.5 shrink-0 rounded-full"
                        style={{
                          background:
                            s.status === "ok"
                              ? "var(--gc-good)"
                              : s.status === "bad"
                                ? "var(--gc-bad)"
                                : s.status === "info"
                                  ? "var(--gc-cyan)"
                                  : "var(--gc-text-3)",
                        }}
                      />
                      <span className="truncate">{s.label}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
          <div ref={scrollBottomRef} />
        </div>
      </ScrollArea>

      {/* footer */}
      <div className="flex flex-col gap-1.5 border-t p-2.5" style={{ borderColor: "var(--gc-line)" }}>
        {!hasToken && (
          <div className="text-[11px]" style={{ color: "var(--gc-warn)" }}>
            Companion offline — chat unavailable
          </div>
        )}
        <div className="flex items-end gap-2">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={busy || !hasToken}
            placeholder="Ask the orchestrator… (Enter to send, Shift+Enter for newline)"
            rows={1}
            className="max-h-40 min-h-9 flex-1 resize-none text-[13px]"
          />
          <Button
            size="icon"
            className="size-9 shrink-0"
            disabled={busy || !hasToken || !input.trim()}
            onClick={() => void send()}
          >
            <Send className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
