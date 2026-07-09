"use strict";

// Gamma Discord voice bot -- GAMMA-WORKER Layer 1b, P2 MVP.
//
//   J joins the HQ voice channel (or types "gamma join")  -> bot joins and opens
//   ONE OpenAI Realtime session (the mouth). Rig-state questions route through
//   THREE read-only tools (lib/tools.js) -- the model never answers state from
//   memory. "gamma leave", J leaving, or 5 idle minutes tears the session down
//   (an open session runs a paid meter; auto-leave is mandatory). Every session
//   appends a usage row to automation/state/voice-bot-usage.jsonl.
//
// Security: the bot answers ONLY J (user_id from .discord-config.json), joins
// only for J, and subscribes ONLY to J's audio. Tools are read-only. No order
// placement. The only writes are the usage meter and the log.
//
// Run:  node bot.js            (long-running)
//       node bot.js --selftest-join   (join the voice channel, prove Ready, leave, exit)

const {
  Client,
  GatewayIntentBits,
  Events,
  ChannelType,
} = require("discord.js");
const {
  joinVoiceChannel,
  entersState,
  VoiceConnectionStatus,
  createAudioPlayer,
  createAudioResource,
  StreamType,
  NoSubscriberBehavior,
  EndBehaviorType,
  generateDependencyReport,
} = require("@discordjs/voice");
const prism = require("prism-media");

const config = require("./lib/config");
const { makeLogger } = require("./lib/log");
const { buildInstructions } = require("./lib/persona");
const { toolSchemas } = require("./lib/tools");
const { RealtimeSession } = require("./lib/realtime");
const { stereo48ToMono24, mono24ToStereo48, PcmSpeakerStream } = require("./lib/audio");

const SELFTEST_JOIN = process.argv.includes("--selftest-join");

const cfg = config.load();
const log = makeLogger(cfg.root);

// ── CRASH GUARD (companion pattern -- load-bearing) ─────────────────────────
// One bad tool spawn / WS hiccup must never take the whole bot down silently.
process.on("uncaughtException", (e) => log("SURVIVED uncaughtException: " + (e && e.stack ? e.stack : e)));
process.on("unhandledRejection", (e) => log("SURVIVED unhandledRejection: " + (e && e.stack ? e.stack : e)));

if (!cfg.openaiKey) {
  log("FATAL: no OpenAI key (env OPENAI_API_KEY or automation/state/.openai.key) -- voice cannot start");
  process.exit(1);
}

const J_ID = String(cfg.discord.user_id);
const HQ_GUILD = String(cfg.discord.guild_id);
const HQ_TEXT_CHANNEL = String(cfg.discord.channel_id);
const CMD_RE = /^(?:<@!?\d+>[\s,:]*)?gamma[\s,!:]+(join|leave)\b/i;

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildVoiceStates,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
  ],
});

// ── the voice rig: one active channel connection + one Realtime session ─────
let rig = null; // { channelId, connection, player, speaker, session, subscription, timers }

async function notify(text) {
  try {
    const ch = await client.channels.fetch(HQ_TEXT_CHANNEL);
    if (ch && ch.isTextBased()) await ch.send(text);
  } catch (e) {
    log("notify failed: " + e.message);
  }
}

function teardownRig(reason) {
  if (!rig) return;
  const r = rig;
  rig = null;
  log("tearing down voice rig: " + reason);
  for (const t of r.timers) clearInterval(t);
  try {
    if (r.subscription) r.subscription.destroy();
  } catch {
    /* noop */
  }
  try {
    r.player.stop(true);
  } catch {
    /* noop */
  }
  try {
    r.connection.destroy();
  } catch {
    /* already gone */
  }
  if (r.session) r.session.stop(reason); // writes the usage row
}

async function startRig(voiceChannel, origin) {
  if (rig) {
    if (rig.channelId === voiceChannel.id) return; // already there
    teardownRig("moving_channel");
  }
  log("joining voice channel '" + voiceChannel.name + "' (" + voiceChannel.id + ") origin=" + origin);

  const connection = joinVoiceChannel({
    channelId: voiceChannel.id,
    guildId: voiceChannel.guild.id,
    adapterCreator: voiceChannel.guild.voiceAdapterCreator,
    selfDeaf: false,
    selfMute: false,
  });
  try {
    await entersState(connection, VoiceConnectionStatus.Ready, 20000);
  } catch (e) {
    try {
      connection.destroy();
    } catch {
      /* noop */
    }
    log("voice join FAILED: " + e.message);
    await notify("⚠️ voice: couldn't join **" + voiceChannel.name + "** -- " + e.message);
    return;
  }
  log("voice connection READY in '" + voiceChannel.name + "'");

  // Speaker: infinite raw 48k-stereo stream; model audio is enqueued into it.
  const speaker = new PcmSpeakerStream();
  const player = createAudioPlayer({ behaviors: { noSubscriber: NoSubscriberBehavior.Play } });
  player.on("error", (e) => log("player error: " + e.message));
  connection.subscribe(player);
  player.play(createAudioResource(speaker, { inputType: StreamType.Raw }));

  let lastActivity = Date.now();
  let lastRealAudioToOpenAI = 0;

  const session = new RealtimeSession({
    root: cfg.root,
    key: cfg.openaiKey,
    model: cfg.model,
    instructions: buildInstructions(cfg.root),
    tools: toolSchemas,
    origin,
    log,
    onReady: () => {
      lastActivity = Date.now();
      session.say("You just joined the voice channel where J is. Greet him in ONE short sentence.");
    },
    onAudio: (pcm24) => {
      lastActivity = Date.now();
      speaker.enqueue(mono24ToStereo48(pcm24));
    },
    onBargeIn: () => {
      speaker.flush(); // J is talking -- shut up instantly
    },
    onActivity: () => {
      lastActivity = Date.now();
    },
    onEnd: () => {
      // Session died underneath us (WS drop / error): fold the rig too.
      if (rig && rig.session === session) teardownRig("session_ended");
    },
  });

  try {
    await session.start();
  } catch (e) {
    log("realtime session FAILED to start: " + e.message);
    await notify("⚠️ voice: joined **" + voiceChannel.name + "** but the Realtime session failed (" + e.message + "). Leaving -- no meter left running.");
    try {
      connection.destroy();
    } catch {
      /* noop */
    }
    return;
  }

  // Listening: subscribe ONLY J's audio, decode opus 48k stereo -> mono 24k -> session.
  const receiver = connection.receiver;
  const rigState = {
    channelId: voiceChannel.id,
    connection,
    player,
    speaker,
    session,
    subscription: null,
    timers: [],
  };
  receiver.speaking.on("start", (userId) => {
    if (userId !== J_ID || !rig || rig.subscription) return;
    const opus = receiver.subscribe(J_ID, {
      end: { behavior: EndBehaviorType.AfterSilence, duration: 1000 },
    });
    const decoder = new prism.opus.Decoder({ rate: 48000, channels: 2, frameSize: 960 });
    opus.pipe(decoder);
    decoder.on("data", (pcm48) => {
      lastActivity = Date.now();
      lastRealAudioToOpenAI = Date.now();
      session.sendAudio(stereo48ToMono24(pcm48));
    });
    decoder.on("error", (e) => log("opus decode error: " + e.message));
    opus.once("end", () => {
      try {
        decoder.destroy();
      } catch {
        /* noop */
      }
      if (rig) rig.subscription = null;
    });
    rigState.subscription = opus;
  });

  // Discord sends packets only WHILE J talks; server VAD needs trailing quiet to
  // close a turn. Pad silence for up to 10s after the last real packet.
  const SILENCE_100MS = Buffer.alloc(24000 * 2 * 0.1);
  rigState.timers.push(
    setInterval(() => {
      const since = Date.now() - lastRealAudioToOpenAI;
      if (lastRealAudioToOpenAI && since > 150 && since < 10000) session.sendAudio(SILENCE_100MS);
    }, 100)
  );

  // Auto-leave on idle -- MANDATORY: an open session runs a paid meter.
  rigState.timers.push(
    setInterval(() => {
      if (Date.now() - lastActivity > cfg.idleTimeoutMs) {
        notify("🕐 voice: idle " + Math.round(cfg.idleTimeoutMs / 60000) + " min -- left the channel, meter closed.");
        teardownRig("idle_timeout");
      }
    }, 15000)
  );

  connection.on(VoiceConnectionStatus.Disconnected, () => {
    if (rig && rig.connection === connection) teardownRig("voice_disconnected");
  });

  rig = rigState;
}

// ── channel resolution ──────────────────────────────────────────────────────

async function designatedVoiceChannel(guild) {
  if (cfg.voiceChannelId) {
    const ch = await guild.channels.fetch(cfg.voiceChannelId).catch(() => null);
    if (ch && ch.type === ChannelType.GuildVoice) return ch;
    log("pinned voice_channel_id " + cfg.voiceChannelId + " not found/not voice -- falling back to discovery");
  }
  const all = await guild.channels.fetch();
  const voice = [...all.values()].filter((c) => c && c.type === ChannelType.GuildVoice);
  return voice[0] || null;
}

// ── discord events ──────────────────────────────────────────────────────────

client.once(Events.ClientReady, async (c) => {
  log("discord ONLINE as " + c.user.tag + " (id " + c.user.id + ")");
  const guild = await client.guilds.fetch(HQ_GUILD).catch(() => null);
  if (!guild) {
    log("FATAL: bot cannot see HQ guild " + HQ_GUILD);
    process.exit(1);
  }
  const vc = await designatedVoiceChannel(guild);
  if (!vc) {
    log("NO voice channel exists in HQ -- J must create one (right-click server -> Create Channel -> Voice)");
    if (SELFTEST_JOIN) process.exit(1);
    return;
  }
  log("designated voice channel: '" + vc.name + "' (" + vc.id + ")");

  if (SELFTEST_JOIN) {
    log("SELFTEST: joining voice (no Realtime session will be opened)...");
    const connection = joinVoiceChannel({
      channelId: vc.id,
      guildId: guild.id,
      adapterCreator: guild.voiceAdapterCreator,
      selfDeaf: false,
      selfMute: false,
    });
    try {
      await entersState(connection, VoiceConnectionStatus.Ready, 20000);
      log("SELFTEST VOICE_JOIN_OK -- connection reached Ready");
      await new Promise((r) => setTimeout(r, 2000));
      connection.destroy();
      log("SELFTEST left cleanly");
      process.exit(0);
    } catch (e) {
      log("SELFTEST VOICE_JOIN_FAILED: " + e.message);
      try {
        connection.destroy();
      } catch {
        /* noop */
      }
      process.exit(1);
    }
  }

  // If J is already sitting in the voice channel when the bot boots, join him.
  try {
    const member = await guild.members.fetch(J_ID);
    if (member.voice && member.voice.channelId === vc.id) {
      log("J is already in the voice channel at boot -- joining");
      await startRig(vc, "boot_j_present");
    }
  } catch {
    /* J not fetchable -> nothing to do */
  }
});

client.on(Events.MessageCreate, async (msg) => {
  try {
    if (!msg.guildId || msg.guildId !== HQ_GUILD) return;
    if (String(msg.author.id) !== J_ID) return; // J only -- everyone else is ignored
    const m = CMD_RE.exec(msg.content || "");
    if (!m) return;
    const cmd = m[1].toLowerCase();
    if (cmd === "leave") {
      if (rig) {
        teardownRig("command_leave");
        await msg.reply("👋 left voice, meter closed.");
      } else {
        await msg.reply("not in a voice channel.");
      }
      return;
    }
    // join: prefer the voice channel J is in right now, else the designated one.
    const guild = await client.guilds.fetch(HQ_GUILD);
    const member = await guild.members.fetch(J_ID);
    let target = member.voice && member.voice.channel ? member.voice.channel : null;
    if (!target) target = await designatedVoiceChannel(guild);
    if (!target) {
      await msg.reply("no voice channel exists in HQ -- create one first.");
      return;
    }
    await msg.reply("🎙️ joining **" + target.name + "** -- start talking when you see me in the channel.");
    await startRig(target, "command_join");
  } catch (e) {
    log("messageCreate handler error: " + e.message);
  }
});

client.on(Events.VoiceStateUpdate, async (oldState, newState) => {
  try {
    const uid = String((newState.member && newState.member.id) || (oldState.member && oldState.member.id) || "");
    if (uid !== J_ID) return;

    // J left (or moved out of) the channel the bot is in -> leave, close meter.
    if (rig && oldState.channelId === rig.channelId && newState.channelId !== rig.channelId) {
      notify("👋 J left voice -- following, meter closed.");
      teardownRig("j_left");
      return;
    }
    // J joined the designated channel -> join him.
    if (newState.channelId && newState.channelId !== oldState.channelId) {
      const guild = await client.guilds.fetch(HQ_GUILD);
      const vc = await designatedVoiceChannel(guild);
      if (vc && newState.channelId === vc.id) {
        log("J joined the designated voice channel");
        await startRig(vc, "j_joined_voice");
      }
    }
  } catch (e) {
    log("voiceStateUpdate handler error: " + e.message);
  }
});

// ── clean exit: never leave a paid session open ─────────────────────────────
function shutdown(sig) {
  log("shutdown on " + sig);
  teardownRig("process_" + sig);
  client.destroy().finally(() => process.exit(0));
  setTimeout(() => process.exit(0), 3000).unref();
}
process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));

log("starting -- model=" + cfg.model + " idle_timeout=" + cfg.idleTimeoutMs + "ms root=" + cfg.root);
log("voice dependency report:\n" + generateDependencyReport());
client.login(cfg.discord.bot_token).catch((e) => {
  log("FATAL discord login failed: " + e.message);
  if (/disallowed intents/i.test(String(e.message))) {
    log("-> J must enable 'Message Content Intent' (and keep 'Server Members'/'Presence' as-is) " +
        "under https://discord.com/developers/applications -> Chief -> Bot -> Privileged Gateway Intents");
  }
  process.exit(1);
});
