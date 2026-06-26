"use strict";

// One-time generator for the companion push secrets, zero npm deps (Node crypto):
//   automation/state/.vapid.json      { publicKey, privateKey, subject }  (Web Push VAPID, base64url raw P-256)
//   automation/state/.approve-hmac.key  32 random bytes (signs wrist Approve/Reject tokens)
//
// Both are gitignored. Idempotent: refuses to overwrite existing keys unless --force
// (regenerating VAPID would invalidate every phone's existing push subscription).
//
//   node tools/gen-vapid.js            # generate if absent
//   node tools/gen-vapid.js --force    # regenerate (re-subscribe all devices after)

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const ROOT = path.resolve(__dirname, "..", "..");
const STATE = path.join(ROOT, "automation", "state");
const VAPID = path.join(STATE, ".vapid.json");
const HMAC = path.join(STATE, ".approve-hmac.key");
const force = process.argv.includes("--force");
const SUBJECT = "mailto:jack.watergun@gmail.com";

const b64url = (buf) => buf.toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
function b64urlToBuf(s) {
  s = String(s).replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  return Buffer.from(s, "base64");
}

fs.mkdirSync(STATE, { recursive: true });

if (fs.existsSync(VAPID) && !force) {
  console.log("vapid: exists, kept (use --force to regenerate):", VAPID);
} else {
  // EC P-256 keypair -> VAPID format: publicKey = base64url(0x04 || X || Y),
  // privateKey = the base64url 32-byte private scalar (JWK 'd').
  const { publicKey, privateKey } = crypto.generateKeyPairSync("ec", { namedCurve: "prime256v1" });
  const jpub = publicKey.export({ format: "jwk" });
  const jpriv = privateKey.export({ format: "jwk" });
  const pub = b64url(Buffer.concat([Buffer.from([4]), b64urlToBuf(jpub.x), b64urlToBuf(jpub.y)]));
  const obj = { publicKey: pub, privateKey: jpriv.d, subject: SUBJECT };
  fs.writeFileSync(VAPID, JSON.stringify(obj, null, 2));
  console.log("vapid: wrote", VAPID, "| publicKey", pub.slice(0, 18) + "…");
}

if (fs.existsSync(HMAC) && !force) {
  console.log("hmac:  exists, kept:", HMAC);
} else {
  fs.writeFileSync(HMAC, crypto.randomBytes(32));
  console.log("hmac:  wrote", HMAC, "(32 random bytes)");
}
