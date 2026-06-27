"use strict";

// Gamma cockpit — OpenAI Realtime voice client (WebRTC).
//
// Adapted from gamma-companion/public/realtime.js. The voice model is
// gpt-realtime-2; when it needs Gamma's live state it calls the get_gamma_state
// tool, which THIS client fulfills by fetching /api/pulse, /api/feed,
// /api/vitals, /api/tiles and handing back the combined JSON. The model speaks
// the grounded answer.
//
// SECURITY: the real OpenAI key never touches the browser. /api/realtime-token
// mints a short-lived ephemeral client_secret server-side; we connect with that.
//
// The status callback emits: connecting | listening | user_speaking | speaking |
// stopped | error:<msg> — the face uses these to animate the core.

window.GammaRealtime = (function () {
  let pc = null;
  let dc = null;
  let micStream = null;
  let audioEl = null;
  let active = false;
  let starting = false;
  let onStatus = function () {};

  async function start(statusCb) {
    if (active || starting) return;
    starting = true;
    onStatus = statusCb || function () {};
    onStatus("connecting");
    try {
      const res = await fetch("/api/realtime-token");
      const tok = await res.json().catch(function () { return null; });
      const ephemeral = tok && tok.value;
      if (!ephemeral) {
        if (res.status === 503) throw new Error("Voice isn't set up yet — everything else still works.");
        throw new Error((tok && tok.error) || "no token");
      }

      pc = new RTCPeerConnection();

      audioEl = document.createElement("audio");
      audioEl.autoplay = true;
      audioEl.style.display = "none";
      document.body.appendChild(audioEl);
      pc.ontrack = function (e) {
        audioEl.srcObject = e.streams[0];
        try { audioEl.play(); } catch (err) { /* autoplay; gesture already given */ }
      };

      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      pc.addTrack(micStream.getTracks()[0]);

      dc = pc.createDataChannel("oai-events");
      dc.addEventListener("message", onEvent);

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      const sdpRes = await fetch("https://api.openai.com/v1/realtime/calls", {
        method: "POST",
        body: offer.sdp,
        headers: { Authorization: "Bearer " + ephemeral, "Content-Type": "application/sdp" },
      });
      if (!sdpRes.ok) {
        throw new Error(
          sdpRes.status >= 400 && sdpRes.status < 500
            ? "Voice isn't enabled on this OpenAI key yet — the dashboard still works."
            : "Voice service is unavailable right now (" + sdpRes.status + ")."
        );
      }
      await pc.setRemoteDescription({ type: "answer", sdp: await sdpRes.text() });

      active = true;
      onStatus("listening");
    } catch (e) {
      onStatus("error:" + ((e && e.message) || e));
      stop(true); // silent teardown — keep the error message on screen
    } finally {
      starting = false;
    }
  }

  // Fulfill the get_gamma_state tool: fetch the four read-only cockpit endpoints
  // and return ONE combined JSON object the model can answer from. Read-only —
  // never places an order, never approves anything.
  async function fetchGammaState() {
    const endpoints = ["/api/pulse", "/api/feed", "/api/vitals", "/api/tiles"];
    const out = {};
    const keys = ["pulse", "feed", "vitals", "tiles"];
    await Promise.all(endpoints.map(async function (ep, i) {
      try {
        const r = await fetch(ep);
        out[keys[i]] = await r.json();
      } catch (e) {
        out[keys[i]] = { error: String((e && e.message) || e) };
      }
    }));
    return out;
  }

  async function onEvent(ev) {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    const t = msg.type || "";

    if (t === "input_audio_buffer.speech_started") { onStatus("user_speaking"); return; }
    if (t === "input_audio_buffer.speech_stopped") { onStatus("listening"); return; }
    if (t === "response.output_audio.delta" || t === "response.audio.delta") { onStatus("speaking"); return; }
    if (t === "response.done" || t === "response.output_audio.done" || t === "response.audio.done") { onStatus("listening"); return; }

    if (t === "response.function_call_arguments.done") {
      // The only registered tool is get_gamma_state (no args). Fulfill it locally.
      let output = "{}";
      try {
        const state = await fetchGammaState();
        output = JSON.stringify(state);
      } catch (e) {
        output = JSON.stringify({ error: "couldn't read live state" });
      }
      try {
        dc.send(JSON.stringify({
          type: "conversation.item.create",
          item: { type: "function_call_output", call_id: msg.call_id, output: output },
        }));
        dc.send(JSON.stringify({ type: "response.create" }));
      } catch (e) { /* channel closed */ }
    }
  }

  function stop(silent) {
    active = false;
    try { if (dc) dc.close(); } catch {}
    try { if (pc) pc.close(); } catch {}
    try { if (micStream) micStream.getTracks().forEach(function (tr) { tr.stop(); }); } catch {}
    try {
      if (audioEl) {
        audioEl.pause();
        audioEl.srcObject = null;
        if (audioEl.parentNode) audioEl.parentNode.removeChild(audioEl);
      }
    } catch {}
    dc = null; pc = null; micStream = null; audioEl = null;
    // After a failed start() teardown DON'T emit "stopped" — it would clobber the
    // just-shown "error:<reason>".
    if (!silent) onStatus("stopped");
  }

  return { start: start, stop: stop, isActive: function () { return active; } };
})();
