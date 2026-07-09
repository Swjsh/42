"use strict";

// PCM plumbing between the two audio worlds:
//   Discord voice  = 48 kHz, 16-bit signed LE, STEREO (via opus decode)
//   OpenAI Realtime = 24 kHz, 16-bit signed LE, MONO
// Naive 2:1 resampling (average pairs down, linear-interp up) is fine for speech.

const { Readable } = require("stream");

// 20ms of silence in each world.
const SILENCE_24K_MONO_20MS = Buffer.alloc(24000 * 2 * 0.02); // 960 bytes
const SILENCE_48K_STEREO_20MS = Buffer.alloc(48000 * 2 * 2 * 0.02); // 3840 bytes

// Discord -> OpenAI: interleaved stereo 48k -> mono 24k.
// Each output sample = mean of one 4-sample group (L0,R0,L1,R1): downmix + decimate
// with a crude 2-tap low-pass in one pass.
function stereo48ToMono24(buf) {
  const inSamples = buf.length >> 1; // int16 count
  const groups = inSamples >> 2;
  const out = Buffer.allocUnsafe(groups * 2);
  for (let g = 0; g < groups; g++) {
    const i = g << 3; // byte offset of the 4-sample group
    const v =
      (buf.readInt16LE(i) + buf.readInt16LE(i + 2) + buf.readInt16LE(i + 4) + buf.readInt16LE(i + 6)) >> 2;
    out.writeInt16LE(v, g << 1);
  }
  return out;
}

// OpenAI -> Discord: mono 24k -> interleaved stereo 48k.
// Each input sample emits two stereo frames: [s, s] then [mid, mid] where mid
// linearly interpolates toward the next sample.
function mono24ToStereo48(buf) {
  const n = buf.length >> 1;
  const out = Buffer.allocUnsafe(n * 8);
  for (let i = 0; i < n; i++) {
    const s = buf.readInt16LE(i << 1);
    const next = i + 1 < n ? buf.readInt16LE((i + 1) << 1) : s;
    const mid = (s + next) >> 1;
    const o = i << 3;
    out.writeInt16LE(s, o);
    out.writeInt16LE(s, o + 2);
    out.writeInt16LE(mid, o + 4);
    out.writeInt16LE(mid, o + 6);
  }
  return out;
}

// The speaker side: an INFINITE raw-PCM stream for @discordjs/voice. It never
// ends and never starves -- when the queue is empty it feeds silence, so the
// AudioPlayer stays busy and newly-arriving model audio plays with no resource
// juggling. flush() is barge-in: J starts talking -> drop every queued byte.
// Small highWaterMark keeps the silence cushion (added latency) tight.
class PcmSpeakerStream extends Readable {
  constructor() {
    super({ highWaterMark: SILENCE_48K_STEREO_20MS.length * 2 });
    this.queue = [];
  }
  _read() {
    this.push(this.queue.length ? this.queue.shift() : SILENCE_48K_STEREO_20MS);
  }
  enqueue(buf) {
    this.queue.push(buf);
  }
  flush() {
    this.queue = [];
  }
  get queuedBytes() {
    return this.queue.reduce((a, b) => a + b.length, 0);
  }
}

module.exports = {
  stereo48ToMono24,
  mono24ToStereo48,
  PcmSpeakerStream,
  SILENCE_24K_MONO_20MS,
  SILENCE_48K_STEREO_20MS,
};
