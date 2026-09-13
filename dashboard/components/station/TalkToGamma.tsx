"use client";

import { useState } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface Turn {
  message: string;
  reply: string;
}

/**
 * "Talk to Gamma" -- posts to /api/station/ask, which calls Ollama server-
 * side (loopback only). The reply is rendered as PLAIN TEXT ONLY (a React
 * child string -- never dangerouslySetInnerHTML, never eval'd, never used to
 * build a URL or command) -- this component's whole job is display, nothing
 * the model says can execute anything from here.
 */
export default function TalkToGamma() {
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    const message = input.trim();
    if (!message || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/station/ask", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ message }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        setError(data.error || `HTTP ${res.status}`);
        return;
      }
      setTurns((prev) => [...prev, { message, reply: data.reply }]);
      setInput("");
    } catch {
      setError("Network error talking to the dashboard.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <p className="mb-2 text-sm font-semibold text-foreground">Talk to Gamma</p>
      {turns.length > 0 && (
        <div className="mb-3 max-h-64 space-y-3 overflow-y-auto pr-1">
          {turns.map((t, i) => (
            <div key={i} className="text-sm">
              <p className="text-muted-foreground">You: {t.message}</p>
              <p className="mt-0.5 whitespace-pre-wrap text-foreground">Gamma: {t.reply}</p>
            </div>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          placeholder="Ask Gamma about the board, a card, or what it's watching right now..."
          className="min-h-16 text-sm"
          disabled={busy}
        />
        <Button size="icon" disabled={busy || !input.trim()} onClick={() => void send()} aria-label="Send">
          <Send className="size-4" />
        </Button>
      </div>
      {busy && <p className="mt-1 text-xs text-muted-foreground">Gamma is thinking...</p>}
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  );
}
