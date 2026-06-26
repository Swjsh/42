"use strict";

// Approval queue for the Gamma companion.
//
// Contract (companion-approvals.json):
//   { schema, updated_at, pending: [ { id, severity, title, detail, created_at } ] }
//
// When J clicks Approve/Reject in the companion, the item is removed from the
// queue and an immutable line is appended to companion-decisions.jsonl. A
// future step wires the engine (heartbeat / conductor) to WRITE items here and
// READ companion-decisions.jsonl back -- until then this is the companion's own
// honest outbox, not a faked engine contract.

const fs = require("fs");
const path = require("path");
const { logActivity } = require("./activity");
// push is a never-throws leaf (no .vapid.json -> $0 no-op). Requiring it here is
// acyclic: push.js depends on NOTHING in this lib, and approvals.js must NEVER
// require ./state (state.js already requires ./approvals -> would be a cycle).
const push = require("./push");

function approvalsPath(root) {
  return path.join(root, "automation", "state", "companion-approvals.json");
}

function decisionsPath(root) {
  return path.join(root, "automation", "state", "companion-decisions.jsonl");
}

// ── synthetic-card ack/snooze store ──────────────────────────────────────────
// Obligation / derived cards (ids "oblig-*" / "act-*") are NOT in
// companion-approvals.json -- they are regenerated from live state every poll,
// so resolveApproval has nothing to remove and they bounce straight back. The
// ack store records, per synthetic card id, { until_iso, evidence_sig }: a tapped
// card is SNOOZED for ~45 min, and fullState() suppresses it WHILE acked AND the
// evidence signature is unchanged. It auto-re-surfaces when the snooze lapses OR
// the evidence genuinely changes -- so we never permanently hide a real red.
const ACK_SNOOZE_MIN = 45;

function cardAcksPath(root) {
  return path.join(root, "automation", "state", "companion-card-acks.json");
}

function isSyntheticCardId(id) {
  return /^(oblig|act)-/.test(String(id || ""));
}

// Normalize a synthetic card's evidence signature so age-bearing tokens in the
// detail ("201m old", "stale: 12m", ISO timestamps) don't tick every poll and
// churn the stored vs compared key -- which re-surfaced a just-approved card ~60s
// later and re-fired duplicate builds. Strips the moving parts to stable
// placeholders so the sig is stable while the underlying evidence is unchanged.
function cardEvidenceSig(id, detail) {
  const d = String(detail == null ? "" : detail);
  const norm = d
    .replace(/\d+(?:\.\d+)?\s*m\s+(?:old|ago)/gi, "<age>")
    .replace(/\bstale:\s*\d+(?:\.\d+)?m\b/gi, "stale:<age>")
    .replace(/\d{4}-\d{2}-\d{2}T[\d:.]+Z?/g, "<ts>");
  return String(id || "") + "|" + norm;
}

function readCardAcks(root) {
  try {
    const raw = JSON.parse(fs.readFileSync(cardAcksPath(root), "utf8"));
    return raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  } catch {
    return {};
  }
}

function writeCardAcks(root, obj) {
  try {
    const tmp = cardAcksPath(root) + ".tmp." + process.pid;
    fs.writeFileSync(tmp, JSON.stringify(obj, null, 2));
    fs.renameSync(tmp, cardAcksPath(root));
    return true;
  } catch {
    return false;
  }
}

// Snooze a synthetic card. evidenceSig is the card's current detail (or null when
// unknown, e.g. the headerless signed-approve path). Best-effort; never throws.
function snoozeCard(root, id, evidenceSig, minutes) {
  try {
    if (!isSyntheticCardId(id)) return false;
    const acks = readCardAcks(root);
    const mins = typeof minutes === "number" && minutes > 0 ? minutes : ACK_SNOOZE_MIN;
    acks[id] = {
      until_iso: new Date(Date.now() + mins * 60 * 1000).toISOString(),
      evidence_sig: evidenceSig == null ? null : cardEvidenceSig(id, evidenceSig).slice(0, 500),
    };
    // Prune lapsed entries so the file never grows unbounded.
    const now = Date.now();
    for (const k of Object.keys(acks)) {
      const u = Date.parse(acks[k] && acks[k].until_iso);
      if (Number.isFinite(u) && u < now) delete acks[k];
    }
    return writeCardAcks(root, acks);
  } catch {
    return false;
  }
}

// Clear a synthetic card's snooze so it re-surfaces on the next poll. Used by the
// escalation completion callback when a build did NOT satisfy the card (fail-green:
// an unmet obligation / failed analysis must come back, not stay hidden the full
// grace). Best-effort; never throws.
function unsnoozeCard(root, id) {
  try {
    if (!isSyntheticCardId(id)) return false;
    const acks = readCardAcks(root);
    if (!(id in acks)) return true;
    delete acks[id];
    return writeCardAcks(root, acks);
  } catch {
    return false;
  }
}

// Is this synthetic card currently snoozed for THIS evidence? True only when an
// unexpired ack exists AND its evidence_sig matches the current evidence (a null
// stored sig matches by time alone -- the signed-approve path had no detail). A
// changed evidence_sig => not suppressed => the red correctly re-surfaces.
function isCardSnoozed(root, id, currentSig) {
  try {
    const acks = readCardAcks(root);
    const a = acks[id];
    if (!a) return false;
    const until = Date.parse(a.until_iso);
    if (!Number.isFinite(until) || until < Date.now()) return false;
    if (a.evidence_sig == null) return true; // time-only snooze
    return a.evidence_sig === (currentSig == null ? null : cardEvidenceSig(id, currentSig).slice(0, 500));
  } catch {
    return false;
  }
}

function loadPending(root) {
  try {
    const raw = JSON.parse(fs.readFileSync(approvalsPath(root), "utf8"));
    if (Array.isArray(raw)) return raw;
    if (raw && Array.isArray(raw.pending)) return raw.pending;
    return [];
  } catch {
    return [];
  }
}

function readApprovals(root) {
  return loadPending(root).filter((x) => x && x.id && !x.resolved);
}

function writeApprovals(root, pending) {
  const payload = {
    schema: "gamma-companion-approvals@1",
    updated_at: new Date().toISOString(),
    pending,
  };
  // Atomic tmp+rename (mirrors writeCardAcks / writeSubs). enqueueApproval
  // (engine) and resolveApproval (http) both load->mutate->write and can race;
  // a plain writeFileSync that crashed mid-write left a TORN file that
  // loadPending swallows -> every pending real approval silently vanished. The
  // rename is atomic on the same volume, so a reader sees old-or-new, never torn.
  const tmp = approvalsPath(root) + ".tmp." + process.pid;
  fs.writeFileSync(tmp, JSON.stringify(payload, null, 2));
  fs.renameSync(tmp, approvalsPath(root));
}

// The grace snooze (minutes) for an escalating approve: hide the card for the
// WHOLE possible build (just past the 15-min wall-clock kill) so it can't re-surface
// mid-build and provoke a duplicate re-tap. The escalation completion callback then
// resolves it deterministically: snooze LONG (45m) if the work succeeded/cleared, or
// unsnooze (re-surface now) if it failed — fail-green, never hide a still-unmet card.
const ESCALATE_GRACE_MIN = 16;

// Append ONE approval card to the queue and (best-effort) push it to J's wrist
// with Approve/Reject action buttons carrying signed one-time tokens. This is
// the missing queue WRITER -- the engine/conductor calls this instead of only
// editing dashboard-dialogue.json, so a real approval reaches the phone+watch.
//
// `item` shape: { id, severity?, title, detail?, created_at? }. The id MUST be
// unique+nonced by the caller (e.g. "oblig-<id>-<rand>") so a token minted for
// one card can never be replayed against a later card that reuses a base id.
// Never throws -- a push failure must never block the queue write.
function enqueueApproval(root, item) {
  const card = Object.assign(
    { severity: "info", created_at: new Date().toISOString() },
    item || {}
  );
  if (!card.id || !card.title) {
    return { ok: false, error: "enqueueApproval needs at least { id, title }" };
  }

  // Dedupe by id, then append. writeApprovals is plain fs (atomic enough for a
  // single-writer companion).
  const pending = loadPending(root).filter((x) => x && x.id !== card.id);
  pending.push(card);
  writeApprovals(root, pending);

  logActivity(root, {
    source: "approvals",
    origin: "engine",
    tier: "approval",
    model: null,
    cost_usd: 0,
    action: "queued approval " + card.id,
    outcome: card.title,
  });

  // Fire-and-forget wrist push with two signed-token actions. mintApproveToken
  // returns null when there is no .approve-hmac.key, in which case we simply
  // omit the action URLs (the in-app queue is still authoritative).
  try {
    const approveTok = push.mintApproveToken(root, card.id, "approve");
    const rejectTok = push.mintApproveToken(root, card.id, "reject");
    const actions = [];
    if (approveTok) actions.push({ action: "approve", title: "Approve", url: "/api/approve-signed?tok=" + encodeURIComponent(approveTok) });
    if (rejectTok) actions.push({ action: "reject", title: "Reject", url: "/api/approve-signed?tok=" + encodeURIComponent(rejectTok) });
    push.sendPush(root, {
      title: card.title,
      body: card.detail || "Tap Approve or Reject.",
      tag: "approval-" + card.id,
      url: "/",
      requireInteraction: true,
      actions,
    });
  } catch {
    /* push is best-effort -- the queue write already succeeded */
  }

  return { ok: true, queued: card.id, pending: pending.length };
}

function resolveApproval(root, id, decision, note, evidenceSig, opts) {
  const skipLongSnooze = !!(opts && opts.skipLongSnooze);
  const pending = loadPending(root);
  const found = pending.find((x) => x && x.id === id);
  const item = found || { id };
  const synthetic = isSyntheticCardId(id);

  // Idempotency: a double-tap / retried fetch / app-then-wrist can POST the same
  // id twice. For a REAL queued card, if it's already gone from the queue (and
  // not synthetic), the first decision already won — no-op the second so we don't
  // write a duplicate decision line or fire a duplicate escalation downstream.
  if (!synthetic && !found) {
    return { resolved: id, decision, remaining: pending.length, already: true };
  }
  // For a SYNTHETIC card, an unexpired snooze for the SAME evidence means it was
  // already resolved this cycle — no-op the duplicate (the caller already skips
  // re-escalating when this returns already:true).
  if (synthetic) {
    const sig = evidenceSig != null ? evidenceSig : item.detail;
    if (isCardSnoozed(root, id, sig)) {
      return { resolved: id, decision, remaining: pending.length, already: true };
    }
  }

  const remaining = pending.filter((x) => x && x.id !== id);
  writeApprovals(root, remaining);

  // Synthetic obligation/derived cards aren't in the queue (nothing was removed
  // above), so they would bounce straight back on the next poll. SNOOZE them so
  // a tapped card clears AND stays cleared until the snooze lapses or the
  // evidence changes. Real queued cards are removed above and need no snooze.
  // FAIL-GREEN: when this approve KICKS OFF an escalation (skipLongSnooze), write
  // only a SHORT grace snooze — the escalation completion callback then snoozes
  // LONG only if the obligation actually cleared, so a failed rerun re-surfaces
  // the card instead of hiding it ~45 min unconditionally.
  if (synthetic) {
    const minutes = skipLongSnooze ? ESCALATE_GRACE_MIN : ACK_SNOOZE_MIN;
    snoozeCard(root, id, evidenceSig != null ? evidenceSig : item.detail, minutes);
  }

  const record = {
    ts: new Date().toISOString(),
    id,
    decision,
    note: note || null,
    title: item.title || null,
  };
  fs.appendFileSync(decisionsPath(root), JSON.stringify(record) + "\n");

  logActivity(root, {
    source: "approvals",
    origin: "card",
    tier: "approval",
    model: null,
    cost_usd: 0,
    action: "resolved approval " + id,
    outcome: decision,
  });

  // Fire-and-forget "resolved" push with the SAME tag (approval-<id>) so the OS
  // replaces/clears the still-pinned notification on every device (phone+watch).
  try {
    push.sendPush(root, {
      title: "Resolved: " + (item.title || id),
      body: decision === "approve" ? "Approved." : "Rejected.",
      tag: "approval-" + id,
      url: "/",
      actions: [],
    });
  } catch {
    /* best-effort -- the decision is already durably logged */
  }

  return { resolved: id, decision, remaining: remaining.length };
}

module.exports = {
  readApprovals,
  enqueueApproval,
  resolveApproval,
  writeApprovals,
  approvalsPath,
  decisionsPath,
  // synthetic-card ack/snooze (obligation/derived cards)
  snoozeCard,
  unsnoozeCard,
  isCardSnoozed,
  isSyntheticCardId,
  cardEvidenceSig,
  readCardAcks,
  cardAcksPath,
};
