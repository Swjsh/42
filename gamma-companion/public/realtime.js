"use strict";

// OpenAI Realtime voice client (WebRTC). gpt-realtime-2 is the voice; when it
// needs real work it calls the ask_gamma tool, which we route into Gamma's brain
// (/api/chat -> free face -> Claude SDK). The model speaks the answer back.
//
// The real OpenAI key never touches the browser: /api/realtime-token mints a
// short-lived ephemeral token server-side, and we connect with that.
//
// The status callback emits: connecting | listening | user_speaking | speaking |
// stopped | error:<msg> -- the UI uses these to animate the robot.

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
      const tok = await fetch("/api/realtime-token").then((r) => r.json());
      const ephemeral = tok && tok.value;
      if (!ephemeral) throw new Error((tok && tok.error) || "no token");

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
            ? "Voice isn't enabled on this OpenAI key yet — everything else works, just type to me."
            : "Voice service is unavailable right now (" + sdpRes.status + ") — type to me instead."
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

  async function onEvent(ev) {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    const t = msg.type || "";

    if (t === "input_audio_buffer.speech_started") { onStatus("user_speaking"); return; }
    if (t === "input_audio_buffer.speech_stopped") { onStatus("listening"); return; }
    if (t === "response.output_audio.delta" || t === "response.audio.delta") { onStatus("speaking"); return; }
    if (t === "response.done" || t === "response.output_audio.done" || t === "response.audio.done") { onStatus("listening"); return; }

    if (t === "response.function_call_arguments.done") {
      let args = {};
      try { args = JSON.parse(msg.arguments || "{}"); } catch {}
      const request = args.request || args.task || args.question || "";
      let answer = "(no answer)";
      try {
        const r = await fetch("/api/chat", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ message: request, voice: true }),
        }).then((x) => x.json());
        answer = r.reply || answer;
        if (r.escalate) answer += " I've put Claude on it; the full result lands in the feed.";
      } catch (e) {
        answer = "I couldn't reach my brain just then.";
      }
      try {
        dc.send(JSON.stringify({ type: "conversation.item.create", item: { type: "function_call_output", call_id: msg.call_id, output: answer } }));
        dc.send(JSON.stringify({ type: "response.create" }));
      } catch (e) { /* channel closed */ }
    }
  }

  function stop(silent) {
    active = false;
    try { if (dc) dc.close(); } catch {}
    try { if (pc) pc.close(); } catch {}
    try { if (micStream) micStream.getTracks().forEach((tr) => tr.stop()); } catch {}
    try {
      if (audioEl) {
        audioEl.pause();
        audioEl.srcObject = null;
        if (audioEl.parentNode) audioEl.parentNode.removeChild(audioEl);
      }
    } catch {}
    dc = null; pc = null; micStream = null; audioEl = null;
    // When stop() is the teardown after a failed start(), DON'T emit "stopped" —
    // it would clobber the just-shown "error:<reason>" with "Tap the mic to talk".
    if (!silent) onStatus("stopped");
  }

  return { start: start, stop: stop, isActive: function () { return active; } };
})();
