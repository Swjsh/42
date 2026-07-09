"use strict";

// One OpenAI Realtime session over WebSocket (server-side twin of the
// companion's browser WebRTC client in gamma-companion/public/realtime.js).
//
// Same ephemeral-token pattern as gamma-companion/server.js#/api/realtime-token:
// the real key mints a short-lived client secret bound to the full session
// config (model, instructions, tools, VAD, voice); the WS connects with that
// ephemeral value. The real key is used for exactly one HTTPS call.
//
// Audio in/out is 24 kHz mono PCM16 base64. The caller wires Discord audio into
// sendAudio() and receives model audio via onAudio(). Tool calls dispatch through
// lib/tools.js -- the same contract the companion uses (function_call_output +
// response.create).

const WebSocket = require("ws");
const { runTool } = require("./tools");
const { appendUsage } = require("./usage");

const MINT_URL = "https://api.openai.com/v1/realtime/client_secrets";
const WS_URL = "wss://api.openai.com/v1/realtime";

class RealtimeSession {
  // opts: { root, key, model, instructions, voice, maxOutputTokens, log, origin,
  //         onReady(id), onAudio(pcm24kMonoBuffer), onBargeIn(), onActivity(),
  //         onTranscript(gammaText), onUserTranscript(jText), onEnd(reason, row) }
  constructor(opts) {
    this.o = opts;
    this.ws = null;
    this.sessionId = null;
    this.startedAt = null;
    this.activeResponse = false;
    this.ended = false;
    this.usageTotals = { input_tokens: 0, output_tokens: 0, responses: 0 };
    this.log = opts.log || (() => {});
  }

  sessionConfig() {
    return {
      session: {
        type: "realtime",
        model: this.o.model,
        instructions: this.o.instructions,
        // Hard brevity backstop: the model rambled in paragraphs on v1. The
        // instructions do the real work; this cap makes a runaway answer
        // physically impossible (~2-3 spoken sentences). Not so tight it clips
        // a normal reply mid-word.
        max_output_tokens: this.o.maxOutputTokens || 220,
        audio: {
          input: {
            format: { type: "audio/pcm", rate: 24000 },
            // Transcribe J's side too, so the audit transcript is TWO-sided
            // (v1 only captured Gamma). Cheap transcription model.
            transcription: { model: "gpt-4o-mini-transcribe" },
            turn_detection: { type: "semantic_vad" },
          },
          output: {
            format: { type: "audio/pcm", rate: 24000 },
            voice: this.o.voice || "marin",
          },
        },
        tools: this.o.tools,
      },
    };
  }

  async mintEphemeral() {
    const r = await fetch(MINT_URL, {
      method: "POST",
      headers: { Authorization: "Bearer " + this.o.key, "Content-Type": "application/json" },
      body: JSON.stringify(this.sessionConfig()),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok || !data.value) {
      throw new Error(
        "ephemeral mint failed: " + ((data.error && data.error.message) || r.status)
      );
    }
    return data.value;
  }

  async start() {
    const ephemeral = await this.mintEphemeral();
    await new Promise((resolve, reject) => {
      const url = WS_URL + "?model=" + encodeURIComponent(this.o.model);
      this.ws = new WebSocket(url, { headers: { Authorization: "Bearer " + ephemeral } });
      const to = setTimeout(() => reject(new Error("realtime WS connect timeout")), 15000);
      this.ws.on("open", () => {
        clearTimeout(to);
        this.startedAt = new Date();
        resolve();
      });
      this.ws.on("error", (e) => {
        clearTimeout(to);
        reject(e);
      });
    });
    this.ws.on("message", (d) => this.onMessage(d));
    this.ws.on("close", () => this.stop("ws_closed"));
    this.ws.on("error", (e) => {
      this.log("realtime WS error: " + e.message);
      this.stop("ws_error");
    });
  }

  send(obj) {
    try {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(obj));
    } catch (e) {
      this.log("realtime send failed: " + e.message);
    }
  }

  // pcm: Buffer of 24 kHz mono s16le
  sendAudio(pcm) {
    this.send({ type: "input_audio_buffer.append", audio: pcm.toString("base64") });
  }

  // Ask the model to speak unprompted (greeting on join).
  say(prompt) {
    this.send({ type: "response.create", response: { instructions: prompt } });
  }

  // Inject a typed user turn (used by the test harness -- no audio needed).
  sendUserText(text) {
    this.send({
      type: "conversation.item.create",
      item: { type: "message", role: "user", content: [{ type: "input_text", text }] },
    });
    this.send({ type: "response.create" });
  }

  async onMessage(raw) {
    let msg;
    try {
      msg = JSON.parse(raw.toString());
    } catch {
      return;
    }
    const t = msg.type || "";

    if (t === "session.created") {
      this.sessionId = (msg.session && msg.session.id) || null;
      this.log("realtime session OPEN id=" + this.sessionId + " model=" + this.o.model);
      if (this.o.onReady) this.o.onReady(this.sessionId);
      return;
    }
    if (t === "input_audio_buffer.speech_started") {
      // Barge-in: J started talking -- kill local playback and cancel any active response.
      if (this.o.onBargeIn) this.o.onBargeIn();
      if (this.activeResponse) this.send({ type: "response.cancel" });
      if (this.o.onActivity) this.o.onActivity();
      return;
    }
    // J's transcribed speech (input transcription) -- the OTHER half of the audit
    // trail. Fires when the transcription model finishes a user turn.
    if (t === "conversation.item.input_audio_transcription.completed") {
      const said = String(msg.transcript || "").trim();
      if (said) {
        this.log('J said: "' + said.slice(0, 300) + '"');
        if (this.o.onUserTranscript) this.o.onUserTranscript(said);
      }
      return;
    }
    if (t === "response.created") {
      this.activeResponse = true;
      return;
    }
    if (t === "response.done") {
      this.activeResponse = false;
      const u = (msg.response && msg.response.usage) || {};
      this.usageTotals.input_tokens += u.input_tokens || 0;
      this.usageTotals.output_tokens += u.output_tokens || 0;
      this.usageTotals.responses += 1;
      if (this.o.onResponseDone) this.o.onResponseDone(msg);
      return;
    }
    if (t === "response.output_audio.delta" || t === "response.audio.delta") {
      if (this.o.onAudio && msg.delta) this.o.onAudio(Buffer.from(msg.delta, "base64"));
      if (this.o.onActivity) this.o.onActivity();
      return;
    }
    if (t === "response.output_audio_transcript.done" || t === "response.audio_transcript.done") {
      if (msg.transcript) this.log('gamma said: "' + String(msg.transcript).slice(0, 300) + '"');
      if (this.o.onTranscript) this.o.onTranscript(String(msg.transcript || ""));
      return;
    }
    if (t === "response.function_call_arguments.done") {
      const name = msg.name || "";
      this.log("tool call: " + name);
      const started = Date.now();
      const output = await runTool(this.o.root, name);
      this.log("tool " + name + " answered in " + (Date.now() - started) + "ms (" + output.length + " chars)");
      this.send({
        type: "conversation.item.create",
        item: { type: "function_call_output", call_id: msg.call_id, output },
      });
      this.send({ type: "response.create" });
      return;
    }
    if (t === "error") {
      // response.cancel with nothing active is benign; log everything else.
      const m = (msg.error && msg.error.message) || JSON.stringify(msg).slice(0, 200);
      if (!/no active response/i.test(m)) this.log("realtime error event: " + m);
    }
  }

  // Idempotent teardown + THE usage row (the cost meter is non-negotiable).
  stop(reason) {
    if (this.ended) return;
    this.ended = true;
    const end = new Date();
    const start = this.startedAt || end;
    const row = {
      ts_start: start.toISOString(),
      ts_end: end.toISOString(),
      seconds: Math.round((end - start) / 1000),
      model: this.o.model,
      session_id: this.sessionId,
      origin: this.o.origin || "discord",
      end_reason: reason,
      usage: this.usageTotals,
    };
    const ok = appendUsage(this.o.root, row);
    this.log(
      "realtime session CLOSED (" + reason + ") after " + row.seconds + "s, " +
        "tokens in/out=" + row.usage.input_tokens + "/" + row.usage.output_tokens +
        (ok ? " -- usage row written" : " -- USAGE ROW WRITE FAILED")
    );
    try {
      if (this.ws) this.ws.close();
    } catch {
      /* noop */
    }
    this.ws = null;
    if (this.o.onEnd) this.o.onEnd(reason, row);
  }
}

module.exports = { RealtimeSession };
