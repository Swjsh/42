"use strict";

// Web Push (VAPID) leaf module for the Gamma companion.
//
// Zero npm dependencies -- RFC8291 (aes128gcm payload encryption) + RFC8292
// (VAPID, ES256 JWT) are implemented on Node's built-in `crypto`. This mirrors
// activity.js's house rule: this is BEST-EFFORT telemetry-grade notification.
// It must NEVER throw and must NEVER block the caller's critical path. Every
// public function swallows its own errors and degrades to a safe no-op.
//
// $0 cost: there is no service. Web Push delivers straight to the browser
// vendor's push endpoint (FCM / Mozilla autopush / Apple), which is free.
//
// SECURITY: if automation/state/.vapid.json is ABSENT, push is silently
// disabled -- every sendPush becomes a no-op. The VAPID private key and the
// approve-HMAC key are born on J's machine, are gitignored, and are in the
// guard's DENY_WRITE set so an escalated Claude can never exfiltrate them.
//
// Public surface:
//   loadVapid(root)                 -> { publicKey, privateKey, subject } | null
//   loadSubs(root)                  -> [ subscription, ... ]
//   saveSub(root, sub)              -> bool      (dedupes by endpoint)
//   sendPush(root, payload)         -> void      (fire-and-forget, prunes 404/410)
//   mintApproveToken(root, id, dec) -> token|null (HMAC over id|decision|exp|jti)
//   verifyApproveToken(root, tok)   -> { ok, id, decision } (single-use)

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const https = require("https");

// ── paths ──────────────────────────────────────────────────────────────────
function statePath(root, name) {
  return path.join(root, "automation", "state", name);
}
function vapidPath(root) {
  return statePath(root, ".vapid.json");
}
function subsPath(root) {
  return statePath(root, "push-subscriptions.json");
}
function hmacKeyPath(root) {
  return statePath(root, ".approve-hmac.key");
}
function consumedPath(root) {
  return statePath(root, ".approve-consumed.json");
}

// ── base64url helpers ───────────────────────────────────────────────────────
function b64urlEncode(buf) {
  return Buffer.from(buf).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function b64urlDecode(str) {
  const s = String(str || "").replace(/-/g, "+").replace(/_/g, "/");
  return Buffer.from(s + "===".slice((s.length + 3) % 4), "base64");
}

// ── VAPID keys ──────────────────────────────────────────────────────────────
// Returns the parsed .vapid.json or null. A null return means "push disabled".
function loadVapid(root) {
  try {
    const raw = JSON.parse(fs.readFileSync(vapidPath(root), "utf8"));
    if (raw && raw.publicKey && raw.privateKey) return raw;
    return null;
  } catch {
    return null;
  }
}

// ── subscriptions (atomic tmp+rename write) ─────────────────────────────────
function loadSubs(root) {
  try {
    const raw = JSON.parse(fs.readFileSync(subsPath(root), "utf8"));
    if (Array.isArray(raw)) return raw.filter((s) => s && s.endpoint);
    if (raw && Array.isArray(raw.subscriptions)) return raw.subscriptions.filter((s) => s && s.endpoint);
    return [];
  } catch {
    return [];
  }
}

function writeSubs(root, subs) {
  try {
    const tmp = subsPath(root) + ".tmp." + process.pid;
    fs.writeFileSync(tmp, JSON.stringify(subs, null, 2));
    fs.renameSync(tmp, subsPath(root));
    return true;
  } catch {
    return false;
  }
}

// Save one PushSubscription (browser shape: { endpoint, keys:{p256dh,auth} }).
// Dedupes by endpoint. Never throws.
function saveSub(root, sub) {
  try {
    if (!sub || !sub.endpoint || !sub.keys || !sub.keys.p256dh || !sub.keys.auth) return false;
    const subs = loadSubs(root).filter((s) => s.endpoint !== sub.endpoint);
    subs.push({ endpoint: String(sub.endpoint), keys: { p256dh: String(sub.keys.p256dh), auth: String(sub.keys.auth) } });
    return writeSubs(root, subs);
  } catch {
    return false;
  }
}

// ── RFC8291 aes128gcm payload encryption ────────────────────────────────────
// Encrypts `payload` (Buffer) for a subscription's p256dh/auth keys. Returns the
// full aes128gcm body Buffer (header + ciphertext), or null on any failure.
function encryptPayload(subscription, payload) {
  try {
    const userPublicKey = b64urlDecode(subscription.keys.p256dh); // 65 bytes, uncompressed P-256 point
    const userAuth = b64urlDecode(subscription.keys.auth); // 16 bytes

    // Ephemeral ECDH (server) keypair on P-256.
    const localKeys = crypto.createECDH("prime256v1");
    const localPublicKey = localKeys.generateKeys(); // 65 bytes uncompressed
    const sharedSecret = localKeys.computeSecret(userPublicKey);

    const salt = crypto.randomBytes(16);

    // HKDF per RFC8291 §3.4.
    const hmac = (key, info) => crypto.createHmac("sha256", key).update(info).digest();
    const hkdf = (s, ikm, info, length) => {
      const prk = hmac(s, ikm);
      return hmac(prk, Buffer.concat([info, Buffer.from([1])])).slice(0, length);
    };

    // PRK_key = HKDF(auth_secret, ecdh_secret, "WebPush: info\0" || ua_public || as_public, 32)
    const keyInfo = Buffer.concat([
      Buffer.from("WebPush: info\0", "utf8"),
      userPublicKey,
      localPublicKey,
    ]);
    const ikm = hkdf(userAuth, sharedSecret, keyInfo, 32);

    // CEK = HKDF(salt, IKM, "Content-Encoding: aes128gcm\0", 16)
    const cek = hkdf(salt, ikm, Buffer.from("Content-Encoding: aes128gcm\0", "utf8"), 16);
    // NONCE = HKDF(salt, IKM, "Content-Encoding: nonce\0", 12)
    const nonce = hkdf(salt, ikm, Buffer.from("Content-Encoding: nonce\0", "utf8"), 12);

    // Content = payload || 0x02 (last-record delimiter) -- single record.
    const recordWithPadding = Buffer.concat([payload, Buffer.from([2])]);

    const cipher = crypto.createCipheriv("aes-128-gcm", cek, nonce);
    const encrypted = Buffer.concat([cipher.update(recordWithPadding), cipher.final()]);
    const authTag = cipher.getAuthTag();

    // aes128gcm header: salt(16) || rs(4, big-endian) || idlen(1) || keyid(localPublicKey).
    const rs = Buffer.alloc(4);
    rs.writeUInt32BE(4096, 0);
    const idlen = Buffer.from([localPublicKey.length]);
    const header = Buffer.concat([salt, rs, idlen, localPublicKey]);

    return Buffer.concat([header, encrypted, authTag]);
  } catch {
    return null;
  }
}

// ── RFC8292 VAPID JWT (ES256) ───────────────────────────────────────────────
// DER ECDSA signature -> raw 64-byte (r||s) JOSE form.
function derToJose(der) {
  // der: SEQUENCE { INTEGER r, INTEGER s }
  let offset = 2;
  if (der[1] & 0x80) offset = 2 + (der[1] & 0x7f); // long-form length (won't happen for P-256 but be safe)
  // r
  const rLen = der[offset + 1];
  let r = der.slice(offset + 2, offset + 2 + rLen);
  offset = offset + 2 + rLen;
  // s
  const sLen = der[offset + 1];
  let s = der.slice(offset + 2, offset + 2 + sLen);

  const pad = (b) => {
    if (b.length > 32) b = b.slice(b.length - 32); // strip leading zero byte
    if (b.length < 32) b = Buffer.concat([Buffer.alloc(32 - b.length), b]);
    return b;
  };
  return Buffer.concat([pad(r), pad(s)]);
}

// Convert a raw 32-byte P-256 private scalar (base64url) into a PEM private key
// usable by crypto.sign. We build the EC private key via createPrivateKey from a
// PKCS8 wrapper, deriving the public point from the private scalar with ECDH.
function privateKeyToPem(privBytes) {
  const ecdh = crypto.createECDH("prime256v1");
  ecdh.setPrivateKey(privBytes);
  const pub = ecdh.getPublicKey(); // 65 bytes uncompressed

  // Build a minimal SEC1 ECPrivateKey then wrap in PKCS8 so createPrivateKey accepts it.
  // ECPrivateKey ::= SEQUENCE { version(1), privateKey OCTET STRING(32),
  //   [0] parameters (named curve OID prime256v1), [1] publicKey BIT STRING }
  const oidP256 = Buffer.from([0x06, 0x08, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x03, 0x01, 0x07]);
  const params = Buffer.concat([Buffer.from([0xa0, oidP256.length]), oidP256]);
  const pubBitStr = Buffer.concat([Buffer.from([0x03, pub.length + 1, 0x00]), pub]);
  const pubTagged = Buffer.concat([Buffer.from([0xa1, pubBitStr.length]), pubBitStr]);
  const privOctet = Buffer.concat([Buffer.from([0x04, 0x20]), privBytes]);
  const version = Buffer.from([0x02, 0x01, 0x01]);
  const ecBody = Buffer.concat([version, privOctet, params, pubTagged]);
  const ecPrivateKey = Buffer.concat([Buffer.from([0x30, ecBody.length]), ecBody]);

  // PKCS8: SEQUENCE { version(0), AlgorithmIdentifier{ ecPublicKey, prime256v1 },
  //   privateKey OCTET STRING(ECPrivateKey) }
  const oidEcPublicKey = Buffer.from([0x06, 0x07, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x02, 0x01]);
  const algId = Buffer.concat([
    Buffer.from([0x30, oidEcPublicKey.length + oidP256.length]),
    oidEcPublicKey,
    oidP256,
  ]);
  const pkcs8Octet = Buffer.concat([
    Buffer.from([0x04]),
    derLen(ecPrivateKey.length),
    ecPrivateKey,
  ]);
  const pkcs8Ver = Buffer.from([0x02, 0x01, 0x00]);
  const pkcs8Body = Buffer.concat([pkcs8Ver, algId, pkcs8Octet]);
  const pkcs8 = Buffer.concat([Buffer.from([0x30]), derLen(pkcs8Body.length), pkcs8Body]);

  const pem =
    "-----BEGIN PRIVATE KEY-----\n" +
    pkcs8.toString("base64").replace(/(.{64})/g, "$1\n") +
    "\n-----END PRIVATE KEY-----\n";
  return crypto.createPrivateKey(pem);
}

// DER length encoding (handles the 0x81 long-form for lengths >127).
function derLen(n) {
  if (n < 0x80) return Buffer.from([n]);
  if (n < 0x100) return Buffer.from([0x81, n]);
  return Buffer.from([0x82, (n >> 8) & 0xff, n & 0xff]);
}

// Build the VAPID Authorization + Crypto-Key headers for a given push endpoint.
function vapidHeaders(vapid, endpoint) {
  const url = new URL(endpoint);
  const aud = url.origin;
  const exp = Math.floor(Date.now() / 1000) + 12 * 60 * 60; // 12h
  const sub = vapid.subject || "mailto:jack.watergun@gmail.com";

  const header = b64urlEncode(Buffer.from(JSON.stringify({ typ: "JWT", alg: "ES256" })));
  const body = b64urlEncode(Buffer.from(JSON.stringify({ aud, exp, sub })));
  const signingInput = header + "." + body;

  const privBytes = b64urlDecode(vapid.privateKey);
  const keyObj = privateKeyToPem(privBytes);
  const derSig = crypto.sign("sha256", Buffer.from(signingInput), { key: keyObj, dsaEncoding: "der" });
  const joseSig = b64urlEncode(derToJose(derSig));
  const jwt = signingInput + "." + joseSig;

  return {
    Authorization: "vapid t=" + jwt + ", k=" + vapid.publicKey,
  };
}

// ── send one push to one subscription. Resolves to { ok, statusCode, gone }. ─
function postToEndpoint(vapid, subscription, payload) {
  return new Promise((resolve) => {
    try {
      const body = encryptPayload(subscription, payload);
      if (!body) return resolve({ ok: false, statusCode: 0, gone: false });
      const url = new URL(subscription.endpoint);
      const headers = Object.assign(
        {
          "Content-Encoding": "aes128gcm",
          "Content-Type": "application/octet-stream",
          "Content-Length": body.length,
          TTL: "86400",
          Urgency: "high",
        },
        vapidHeaders(vapid, subscription.endpoint)
      );
      const req = https.request(
        {
          method: "POST",
          hostname: url.hostname,
          port: url.port || 443,
          path: url.pathname + url.search,
          headers,
          timeout: 10000,
        },
        (res) => {
          res.on("data", () => {});
          res.on("end", () => {
            const code = res.statusCode || 0;
            resolve({ ok: code >= 200 && code < 300, statusCode: code, gone: code === 404 || code === 410 });
          });
        }
      );
      req.on("error", () => resolve({ ok: false, statusCode: 0, gone: false }));
      req.on("timeout", () => {
        try { req.destroy(); } catch {}
        resolve({ ok: false, statusCode: 0, gone: false });
      });
      req.write(body);
      req.end();
    } catch {
      resolve({ ok: false, statusCode: 0, gone: false });
    }
  });
}

// Fire-and-forget. Pushes `payload` ({title, body, tag, url, actions:[{action,title,url}]})
// to every saved subscription. Prunes any that return 404/410. Never throws,
// never awaited on a critical path. Silent $0 no-op when .vapid.json is absent.
function sendPush(root, payload) {
  try {
    const vapid = loadVapid(root);
    if (!vapid) return; // push disabled -> $0 no-op
    const subs = loadSubs(root);
    if (!subs.length) return;
    const data = Buffer.from(JSON.stringify(payload || {}), "utf8");
    Promise.all(subs.map((s) => postToEndpoint(vapid, s, data)))
      .then((results) => {
        const gone = new Set();
        results.forEach((r, i) => {
          if (r && r.gone) gone.add(subs[i].endpoint);
        });
        if (gone.size) {
          const kept = loadSubs(root).filter((s) => !gone.has(s.endpoint));
          writeSubs(root, kept);
        }
      })
      .catch(() => {});
  } catch {
    /* push is best-effort -- swallow */
  }
}

// ── signed one-time approve tokens (HMAC-SHA256) ─────────────────────────────
// Keyed off a persisted .approve-hmac.key so in-flight notification tokens
// survive a server restart within their exp. Token payload is `id|decision|exp|jti`,
// HMAC appended. Constant-time verify, single-use jti tracked in a consumed set.

function loadHmacKey(root) {
  try {
    const raw = fs.readFileSync(hmacKeyPath(root));
    if (raw && raw.length >= 16) return raw;
    return null;
  } catch {
    return null;
  }
}

function loadConsumed(root) {
  try {
    const raw = JSON.parse(fs.readFileSync(consumedPath(root), "utf8"));
    if (raw && Array.isArray(raw.jti)) return raw;
    return { jti: [] };
  } catch {
    return { jti: [] };
  }
}

function saveConsumed(root, state) {
  try {
    const now = Math.floor(Date.now() / 1000);
    // Prune entries whose exp has passed so the file never grows unbounded.
    const jti = (state.jti || []).filter((e) => e && Number(e.exp) > now).slice(-500);
    const tmp = consumedPath(root) + ".tmp." + process.pid;
    fs.writeFileSync(tmp, JSON.stringify({ jti }, null, 2));
    fs.renameSync(tmp, consumedPath(root));
    return true;
  } catch {
    return false;
  }
}

// Mint a token for (id, decision). Valid ~15 min. Returns base64url token or null
// (null when no HMAC key exists -> approve-signed simply won't be offered).
function mintApproveToken(root, id, decision) {
  try {
    const key = loadHmacKey(root);
    if (!key) return null;
    if (!id || (decision !== "approve" && decision !== "reject")) return null;
    const exp = Math.floor(Date.now() / 1000) + 15 * 60;
    const jti = crypto.randomBytes(9).toString("hex");
    const payload = String(id) + "|" + decision + "|" + exp + "|" + jti;
    const mac = crypto.createHmac("sha256", key).update(payload).digest();
    const token = b64urlEncode(Buffer.from(payload, "utf8")) + "." + b64urlEncode(mac);
    return token;
  } catch {
    return null;
  }
}

// Verify + CONSUME a token. Returns { ok, id, decision } or { ok:false, error }.
// Enforces: signature (constant-time), exp, single-use (jti not already consumed).
function verifyApproveToken(root, tok) {
  try {
    const key = loadHmacKey(root);
    if (!key) return { ok: false, error: "no-key" };
    const parts = String(tok || "").split(".");
    if (parts.length !== 2) return { ok: false, error: "malformed" };
    const payload = b64urlDecode(parts[0]);
    const givenMac = b64urlDecode(parts[1]);
    const expectMac = crypto.createHmac("sha256", key).update(payload).digest();
    if (givenMac.length !== expectMac.length || !crypto.timingSafeEqual(givenMac, expectMac)) {
      return { ok: false, error: "bad-signature" };
    }
    const fields = payload.toString("utf8").split("|");
    if (fields.length !== 4) return { ok: false, error: "bad-payload" };
    const [id, decision, expStr, jti] = fields;
    if (decision !== "approve" && decision !== "reject") return { ok: false, error: "bad-decision" };
    const exp = Number(expStr);
    const now = Math.floor(Date.now() / 1000);
    if (!Number.isFinite(exp) || exp < now) return { ok: false, error: "expired" };

    const consumed = loadConsumed(root);
    if ((consumed.jti || []).some((e) => e && e.jti === jti)) {
      return { ok: false, error: "already-used" };
    }
    consumed.jti = (consumed.jti || []).concat([{ jti, exp }]);
    saveConsumed(root, consumed);

    return { ok: true, id, decision };
  } catch {
    return { ok: false, error: "exception" };
  }
}

// ── signed per-ask STREAM tokens (HMAC-SHA256) ───────────────────────────────
// EventSource cannot send an x-gamma-token header, so the SSE telemetry stream
// is authed with a short-lived HMAC token minted for ONE ask id. This is the
// same key + crypto as the approve tokens but a SEPARATE payload shape (no
// decision field, domain-separated by a "stream|" prefix) so a stream token can
// NEVER be replayed as an approve token or vice-versa. It is read-only telemetry
// (the SSE stream replays a build's step feed) -- it grants NO write/approve power.
// Not single-use (an SSE client may reconnect within the window) -- it only
// gates which ask id's read-only feed you may watch on a 127.0.0.1 server.
function mintStreamToken(root, id) {
  try {
    const key = loadHmacKey(root);
    if (!key) return null;
    if (!id) return null;
    const exp = Math.floor(Date.now() / 1000) + 5 * 60 * 60; // 5h -- long builds outlive 60min; a page reload mid-build needs the token still valid. Read-only 127.0.0.1 telemetry, grants no write power.
    const payload = "stream|" + String(id) + "|" + exp;
    const mac = crypto.createHmac("sha256", key).update(payload).digest();
    return b64urlEncode(Buffer.from(payload, "utf8")) + "." + b64urlEncode(mac);
  } catch {
    return null;
  }
}

// Verify a stream token. Returns { ok, id } or { ok:false, error }. Constant-time
// signature check + expiry. (No jti/single-use -- reconnects are expected.)
function verifyStreamToken(root, tok) {
  try {
    const key = loadHmacKey(root);
    if (!key) return { ok: false, error: "no-key" };
    const parts = String(tok || "").split(".");
    if (parts.length !== 2) return { ok: false, error: "malformed" };
    const payload = b64urlDecode(parts[0]);
    const givenMac = b64urlDecode(parts[1]);
    const expectMac = crypto.createHmac("sha256", key).update(payload).digest();
    if (givenMac.length !== expectMac.length || !crypto.timingSafeEqual(givenMac, expectMac)) {
      return { ok: false, error: "bad-signature" };
    }
    const fields = payload.toString("utf8").split("|");
    if (fields.length !== 3 || fields[0] !== "stream") return { ok: false, error: "bad-payload" };
    const id = fields[1];
    const exp = Number(fields[2]);
    const now = Math.floor(Date.now() / 1000);
    if (!Number.isFinite(exp) || exp < now) return { ok: false, error: "expired" };
    return { ok: true, id };
  } catch {
    return { ok: false, error: "exception" };
  }
}

module.exports = {
  loadVapid,
  loadSubs,
  saveSub,
  sendPush,
  mintApproveToken,
  verifyApproveToken,
  mintStreamToken,
  verifyStreamToken,
  // exported for tests / potential reuse
  vapidPath,
  subsPath,
};
