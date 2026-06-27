/**
 * Gamma Cockpit v1 — local observability server
 * Port: 4500
 * Pattern: Claude Code hooks → POST /event → SSE stream → browser
 *
 * Reads existing Gamma state files for traffic-light grid.
 * Receives hook events from Claude Code (PreToolUse/PostToolUse/Stop).
 * Streams everything to the browser via /events (SSE).
 *
 * No npm install needed — uses only Node.js built-ins.
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const PORT = process.env.PORT ? parseInt(process.env.PORT, 10) : 4500;
const REPO = path.resolve(__dirname, '..');
const STATE = path.join(REPO, 'automation', 'state');

// ─── In-memory event ring ────────────────────────────────────────────────────
const MAX_EVENTS = 500;
const eventRing = [];
let eventSeq = 0;

function pushEvent(evt) {
  evt.seq = ++eventSeq;
  evt.ts = evt.ts || new Date().toISOString();
  eventRing.push(evt);
  if (eventRing.length > MAX_EVENTS) eventRing.shift();
  broadcastSSE(evt);
}

// seed from existing state files on startup
function seedHistoricalEvents() {
  // Last 5 conductor outcomes
  try {
    const lines = fs.readFileSync(path.join(STATE, 'conductor-outcomes.jsonl'), 'utf8')
      .trim().split('\n').filter(Boolean).slice(-5);
    for (const l of lines) {
      try {
        const r = JSON.parse(l);
        pushEvent({
          source: 'conductor',
          type: 'outcome',
          emoji: r.regressions > 0 ? '🔴' : '✅',
          summary: `[conductor] task=${r.task_id || '?'} cost=$${(r.cost_usd || 0).toFixed(2)} lessons=${r.lessons_shipped || 0}`,
          ts: r.fired_at || new Date().toISOString(),
          detail: r.note || '',
        });
      } catch (_) {}
    }
  } catch (_) {}

  // Last 5 manager log entries
  try {
    const lines = fs.readFileSync(path.join(STATE, 'manager-log.jsonl'), 'utf8')
      .trim().split('\n').filter(Boolean).slice(-5);
    for (const l of lines) {
      try {
        const r = JSON.parse(l);
        const role = r.role || r.phase || '?';
        const elapsed = r.elapsed_s != null ? `${r.elapsed_s.toFixed(1)}s` : '?';
        const lane = r.lane || r.model || '?';
        pushEvent({
          source: 'manager',
          type: 'dispatch',
          emoji: r.ok !== false ? '🤖' : '❌',
          summary: `[manager/${role}] ${(r.action || r.note || '').substring(0, 80)}`,
          ts: r.ts_et ? new Date(r.ts_et).toISOString() : new Date().toISOString(),
          detail: `lane=${lane} elapsed=${elapsed}`,
        });
      } catch (_) {}
    }
  } catch (_) {}

  pushEvent({
    source: 'cockpit',
    type: 'startup',
    emoji: '🚀',
    summary: '[cockpit] Gamma Cockpit v1 started — watching state files',
    ts: new Date().toISOString(),
    detail: `Port ${PORT} | Repo: ${REPO}`,
  });
}

// ─── SSE subscribers ──────────────────────────────────────────────────────────
const sseClients = new Set();

function broadcastSSE(evt) {
  const data = JSON.stringify(evt);
  for (const res of sseClients) {
    try {
      res.write(`data: ${data}\n\n`);
    } catch (_) {
      sseClients.delete(res);
    }
  }
}

// ─── State readers (traffic-light tiles) ─────────────────────────────────────

function readJSON(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (_) {
    return null;
  }
}

function fileAgeMinutes(filePath) {
  try {
    const stat = fs.statSync(filePath);
    return (Date.now() - stat.mtimeMs) / 60000;
  } catch (_) {
    return 9999;
  }
}

function utcToEtString(isoStr) {
  if (!isoStr) return '?';
  try {
    const d = new Date(isoStr);
    return d.toLocaleString('en-US', {
      timeZone: 'America/New_York',
      month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      hour12: false,
    });
  } catch (_) {
    return isoStr;
  }
}

function getEngineStatus() {
  const f = path.join(STATE, 'engine-health.json');
  const d = readJSON(f);
  const ageMin = fileAgeMinutes(f);
  if (!d) return { light: 'RED', title: 'Engine', text: 'engine-health.json missing', updated: '?' };

  const light = d.verdict === 'GREEN' ? 'GREEN' : d.verdict === 'YELLOW' ? 'YELLOW' : 'RED';
  const checks = (d.checks || []).filter(c => c.status !== 'GREEN').map(c => c.name).join(', ');
  const text = `${d.verdict}${checks ? ' | issues: ' + checks : ''} | market_open=${d.market_open}`;
  return {
    light,
    title: 'Engine',
    text,
    updated: utcToEtString(d.checked_at_utc || new Date(Date.now() - ageMin * 60000).toISOString()),
  };
}

function getBeaconStatus() {
  const f = path.join(STATE, 'sight-beacon.json');
  const d = readJSON(f);
  const ageMin = fileAgeMinutes(f);
  if (!d) return { light: 'RED', title: 'Beacon (Eye)', text: 'sight-beacon.json missing', updated: '?' };

  const ageS = d.age_s != null ? d.age_s : ageMin * 60;
  let light = 'GREEN';
  if (!d.ok || ageS > 300) light = 'RED';
  else if (ageS > 120) light = 'YELLOW';

  const text = `SPY $${d.spy} | ribbon=${d.ribbon_stack} | src=${d.data_source} | age=${Math.round(ageMin)}m`;
  return {
    light,
    title: 'Beacon (Eye)',
    text,
    updated: utcToEtString(d.ts_utc || d.ts_et),
  };
}

function getAccountsStatus() {
  // Read fleet/accounts.json (the canonical registry)
  const fleetPath = path.join(STATE, 'fleet', 'accounts.json');
  const fleetData = readJSON(fleetPath);

  // Also check engine-health for kill-switch state
  const health = readJSON(path.join(STATE, 'engine-health.json'));
  const ksChecks = (health?.checks || []).filter(c => c.name?.includes('kill'));

  // Read current position files for flat/in-position status
  const posSafe = readJSON(path.join(STATE, 'current-position-safe.json'));
  const posBold = readJSON(path.join(STATE, 'current-position-bold.json'));
  const safePosStatus = posSafe?.status ? `OPEN:${posSafe.symbol || '?'}` : 'flat';
  const boldPosStatus = posBold?.status ? `OPEN:${posBold.symbol || '?'}` : 'flat';

  // Read sight beacon for latest SPY price
  const beacon = readJSON(path.join(STATE, 'sight-beacon.json'));
  const spy = beacon?.spy ? `SPY $${beacon.spy}` : '';

  const mcp = ['safe-2 (PA3S2PYAS2WQ)', 'bold-2 (PA33W2KUAT40)'];
  const posText = `Safe: ${safePosStatus} | Bold: ${boldPosStatus}`;
  const ksText = ksChecks.map(c => `${c.name.replace('killswitch_', '')}=${c.status}`).join(' ');

  const arms = fleetData?.arms || [];
  const activeArms = arms.filter(a => a.status === 'active').length;

  const light = ksChecks.some(c => c.status === 'RED') ? 'RED' :
                ksChecks.some(c => c.status === 'YELLOW') ? 'YELLOW' : 'GREEN';

  return {
    light,
    title: 'Accounts / P&L',
    text: `${posText} | ${ksText || 'kill-switches OK'} | fleet arms=${activeArms}${spy ? ' | ' + spy : ''}`,
    updated: utcToEtString(health?.checked_at_utc),
  };
}

function getConductorStatus() {
  const f = path.join(STATE, 'conductor-outcomes.jsonl');
  if (!fs.existsSync(f)) return { light: 'YELLOW', title: 'Conductor', text: 'no outcomes file', updated: '?' };

  const lines = fs.readFileSync(f, 'utf8').trim().split('\n').filter(Boolean);
  if (!lines.length) return { light: 'YELLOW', title: 'Conductor', text: 'no outcomes yet', updated: '?' };

  try {
    const last = JSON.parse(lines[lines.length - 1]);
    const firedAt = new Date(last.fired_at);
    const ageMin = (Date.now() - firedAt.getTime()) / 60000;
    const ageStr = ageMin < 60 ? `${Math.round(ageMin)}m ago` : `${(ageMin / 60).toFixed(1)}h ago`;

    const light = last.regressions > 0 ? 'RED' : ageMin > 300 ? 'YELLOW' : 'GREEN';
    const text = `last fired ${ageStr} ET | task=${last.task_id || '?'} | lessons=${last.lessons_shipped || 0} | cost=$${(last.cost_usd || 0).toFixed(2)}`;
    return { light, title: 'Conductor', text, updated: utcToEtString(last.fired_at) };
  } catch (_) {
    return { light: 'YELLOW', title: 'Conductor', text: 'parse error', updated: '?' };
  }
}

function getGymStatus() {
  // Find the latest gym scorecard
  const today = new Date().toISOString().slice(0, 10);
  const candidates = [today, getPrevDate(today, 1), getPrevDate(today, 2)];
  let d = null;
  let usedDate = null;
  for (const dt of candidates) {
    const f = path.join(STATE, `gym-scorecard-${dt}.json`);
    d = readJSON(f);
    if (d) { usedDate = dt; break; }
  }

  if (!d) return { light: 'YELLOW', title: 'Gym', text: 'no recent scorecard', updated: '?' };

  const verdict = d.overall_verdict || d.detector_verdict || '?';
  const light = verdict === 'GREEN' ? 'GREEN' : verdict === 'YELLOW' ? 'YELLOW' : 'RED';
  const auditSummary = (d.audits || []).map(a => `${a.name.split(' ')[0]}=${a.verdict}`).join(' ');
  return {
    light,
    title: 'Gym',
    text: `${verdict} (det=${d.detector_verdict}) | ${auditSummary}`,
    updated: usedDate,
  };
}

function getKitchenStatus() {
  const f = path.join(STATE, 'kitchen-status.json');
  const d = readJSON(f);
  const ageMin = fileAgeMinutes(f);
  if (!d) return { light: 'YELLOW', title: 'Kitchen', text: 'kitchen-status.json missing', updated: '?' };

  const q = d.queue_summary?.by_status || {};
  const pendingTotal = Object.entries(d.queue_summary?.by_priority_pending || {}).reduce((s, [, v]) => s + v, 0);
  const light = d.daemon_alive ? 'GREEN' : 'RED';
  const text = `daemon=${d.daemon_alive ? 'ALIVE' : 'DEAD'} | pending=${pendingTotal} | completed=${q.completed || 0} | cost=$${(d.today_cost_usd_paid_tier || 0).toFixed(2)}`;
  return {
    light,
    title: 'Kitchen',
    text,
    updated: utcToEtString(d.updated_at_et),
  };
}

function getSpendStatus() {
  // Read spend-daily.jsonl for last entry
  const f = path.join(STATE, 'spend-daily.jsonl');
  if (!fs.existsSync(f)) return { light: 'YELLOW', title: 'Spend', text: 'no spend log', updated: '?' };

  const lines = fs.readFileSync(f, 'utf8').trim().split('\n').filter(Boolean);
  if (!lines.length) return { light: 'GREEN', title: 'Spend', text: '$0 today', updated: '?' };

  try {
    const last = JSON.parse(lines[lines.length - 1]);
    const cost = last.total_cost_usd || 0;
    const light = cost > 400 ? 'RED' : cost > 200 ? 'YELLOW' : 'GREEN';
    const text = `$${cost.toFixed(2)} on ${last.date_et} | sessions=${last.claude_sessions || 0}`;
    return { light, title: 'Spend', text, updated: last.date_et };
  } catch (_) {
    return { light: 'YELLOW', title: 'Spend', text: 'parse error', updated: '?' };
  }
}

function getDiscordStatus() {
  const f = path.join(STATE, 'discord-bridge-heartbeat.json');
  const d = readJSON(f);
  const ageMin = fileAgeMinutes(f);
  if (!d) return { light: 'YELLOW', title: 'Discord Bridge', text: 'no heartbeat file', updated: '?' };

  const ageStr = ageMin < 60 ? `${Math.round(ageMin)}m ago` : `${(ageMin / 60).toFixed(1)}h ago`;
  const light = d.consecutive_errors > 5 ? 'RED' : ageMin > 15 ? 'YELLOW' : 'GREEN';
  const text = `last tick ${ageStr} | errors=${d.consecutive_errors || 0}`;
  return { light, title: 'Discord Bridge', text, updated: utcToEtString(d.last_tick_at) };
}

function getAutonomyStatus() {
  const f = path.join(STATE, 'autonomy-metric.json');
  const d = readJSON(f);
  if (!d) return { light: 'YELLOW', title: 'Autonomy', text: 'no metric', updated: '?' };

  const light = d.trend === 'improving' && d.total_regressions === 0 ? 'GREEN' :
                d.total_regressions > 0 ? 'RED' : 'YELLOW';
  const text = `net_improvement=${d.net_improvement} | regressions=${d.total_regressions} | cost=$${(d.total_cost_usd || 0).toFixed(2)} | trend=${d.trend}`;
  return { light, title: 'Autonomy Loop', text, updated: utcToEtString(d.computed_at) };
}

function getTaskHealth() {
  // Run task_health_et.ps1 in a quick mode — but it's slow on task scheduler
  // Instead read scheduled-tasks audit json if available
  const f = path.join(STATE, 'scheduled-tasks-audit.json');
  const d = readJSON(f);
  if (!d) return { light: 'YELLOW', title: 'Task Health', text: 'no audit file — run task_health_et.ps1', updated: '?' };

  const issues = (d.issues || []);
  const light = issues.length === 0 ? 'GREEN' : issues.some(i => i.severity === 'CRITICAL') ? 'RED' : 'YELLOW';
  const text = issues.length === 0
    ? `${d.tasks_checked || '?'} tasks OK`
    : `${issues.length} issues: ${issues.slice(0, 3).map(i => i.task || i.name).join(', ')}`;
  return { light, title: 'Task Health', text, updated: utcToEtString(d.checked_at) };
}

function getAllTiles() {
  return [
    getEngineStatus(),
    getBeaconStatus(),
    getAccountsStatus(),
    getConductorStatus(),
    getGymStatus(),
    getKitchenStatus(),
    getSpendStatus(),
    getDiscordStatus(),
    getAutonomyStatus(),
    getTaskHealth(),
  ];
}

// ─── Gamma voice feed ────────────────────────────────────────────────────────
// Parses STATUS.md headers and recent conductor-outcomes, then rewrites each into
// a calm, first-person, human one-liner — should read like a competent operator
// texting a one-line update, NOT like tailing a logfile.

function classifyKind(text) {
  const t = text.toUpperCase();
  if (/SHIPPED|COMMITTED|FIXED|GRADUATED|RESOLVED|CLOSED|DONE/.test(t)) return 'shipped';
  if (/RED|BLOCKED|BROKEN|ERROR|FAIL|KILL|DEAD/.test(t)) return 'caution';
  if (/GREEN|HEALTHY|FLAT|OK|ALL CLEAN|PASS/.test(t)) return 'healthy';
  return 'info';
}

function stripMarkdown(s) {
  return s
    .replace(/\*\*/g, '')
    .replace(/`/g, '')
    .replace(/\*/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/#+\s*/g, '')
    .trim();
}

// Truncate to ~n chars but never mid-word: back up to the last clause
// boundary or word break before the limit, then add an ellipsis.
function truncate(s, n) {
  s = s.trim();
  if (s.length <= n) return s;
  let cut = s.slice(0, n - 1);
  // Prefer the last clause boundary (— ; , space) so we end cleanly.
  const boundary = Math.max(
    cut.lastIndexOf(' '), cut.lastIndexOf('—'),
    cut.lastIndexOf(';'), cut.lastIndexOf(',')
  );
  if (boundary > n * 0.6) cut = cut.slice(0, boundary);
  cut = cut.replace(/[\s—–\-:;,]+$/, '');
  return cut + '…';
}

// Real acronyms / proper-noun caps to KEEP as-is (everything else loud is softened).
const KEEP_CAPS = new Set([
  'TV', 'VIX', 'EOD', 'SPY', 'RTH', 'MCP', 'LLM', 'TZ', 'AST', 'OOS', 'WF',
  'PDT', 'API', 'REST', 'CDP', 'JSON', 'SSE', 'ET', 'MT', 'UTC', 'OP', 'WR',
  'BS', 'ATM', 'ITM', 'OTM', 'DTE', 'FOMC', 'CPI', 'NFP', 'J',
]);
// Small English words that, when shouted, should just go lowercase.
const CALM_STOP = new Set([
  'TO', 'A', 'AN', 'AND', 'OR', 'BUT', 'IS', 'ARE', 'THE', 'OF', 'ON', 'IN',
  'AT', 'BY', 'AS', 'IT', 'NO', 'NOT', 'ALL', 'WAS', 'WHY', 'NEW', 'OFF',
  'NOW', 'PER', 'VIA', 'WITH', 'INTO', 'THAT', 'THIS', 'ITS',
]);

// Soften a single ALLCAPS token. Token IDs like G17/L188/PA3S… and kept acronyms
// stay; shouted stopwords go lowercase; other long screams get title-cased so the
// clause reads like prose, not a logfile.
function softenToken(tok) {
  // Preserve IDs: a letter+digit mix (G17, L188, PA3S2PYAS2WQ, cd-2026…).
  if (/\d/.test(tok)) return tok;
  // Split a hyphen/underscore scream and soften each part (RESOLVED-AS-STALE).
  if (/[-_]/.test(tok)) {
    return tok.split(/([-_])/).map(p => (/[-_]/.test(p) ? p : softenToken(p))).join('');
  }
  if (!/^[A-Z]{2,}$/.test(tok)) return tok; // not an all-caps word, leave it
  if (KEEP_CAPS.has(tok)) return tok;
  // Shouted English → lowercase prose (DONE→done, DEAD KNOB→dead knob).
  // Sentence-start capitalization is reapplied afterward by toSentenceCase.
  return tok.toLowerCase();
}

// Calm a SHOUTING clause token-by-token.
function calmShouting(s) {
  return String(s || '').replace(/[A-Za-z][A-Za-z0-9'&._-]*/g, softenToken);
}

// Sentence-case: calm the shout, then capitalize the first letter. Never
// lowercases an acronym/ID at the start (e.g. "TV hang", "L188 encoded").
function toSentenceCase(s) {
  s = calmShouting(String(s || '').trim());
  if (!s) return s;
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// Is this clause a short, screamy status TAG (e.g. "G17 SHIPPED",
// "self-audit gap GRADUATED TO A GUARD", "OPEN-BLINDNESS-TV-HANG RESOLVED-AS-STALE")?
// Heuristic: short-ish AND caps-dominant. Such a tag reads better replaced by the
// human description that follows the colon.
function looksLikeTag(seg) {
  const letters = seg.replace(/[^A-Za-z]/g, '');
  const uppers = seg.replace(/[^A-Z]/g, '');
  if (!letters.length) return false;
  return seg.length <= 70 && uppers.length / letters.length > 0.5;
}

// Collapse a raw conductor/status line down to ONE clean, human clause.
//  1. strip markdown + leading log noise (OK, OK —, conductor:, dashes)
//  2. if it's "<screamy TAG>: <description>", keep the human description
//  3. cut to the first clause boundary (—, →, ;, sentence end)
//  4. de-jargon (commit hashes, (HIGH)/(rail-4) parentheticals), calm the shout
function distillClause(raw) {
  let s = stripMarkdown(String(raw || ''));

  // Leading log noise: "OK —", "OK -", "OK:", "conductor:", stray leading dashes.
  s = s.replace(/^\s*conductor\s*:\s*/i, '');
  s = s.replace(/^\s*(ok|done|status)\b\s*[—–\-:]*\s*/i, '');
  s = s.replace(/^[\s—–\-:>]+/, '');

  // "<TAG>: <description>" — prefer the description when the tag is screamy.
  const colon = s.search(/:\s/);
  if (colon > 0 && looksLikeTag(s.slice(0, colon))) {
    s = s.slice(colon + 1).trim();
  }

  // Cut to the first clause boundary so we keep ONE clean clause.
  const cut = s.search(/\s+[—–]\s+|\s*→\s*|;\s+/);
  if (cut > 0) s = s.slice(0, cut);
  // Stop at the first sentence end if it comes even sooner.
  const dot = s.search(/\.\s+[A-Z(]/);
  if (dot > 0) s = s.slice(0, dot);
  // Trim a " + more" / " AND <verb> more" continuation tail (compound updates).
  const tail = s.search(/\s+\+\s+|\s+(?:AND|and)\s+(?:uncovered|fixed|pinned|added|decoupled|committed|graduated)\b/);
  if (tail > 0) s = s.slice(0, tail);
  // Drop a parenthetical aside (mid or trailing) — it's detail, not the headline.
  s = s.replace(/\s*\([^)]*\)/g, '');
  // Soft clause boundary: if still long, cut at " but "/" so " to keep the lead idea.
  if (s.length > 96) {
    const soft = s.search(/\s+(?:but|so|while|then)\s+/i);
    if (soft > 24) s = s.slice(0, soft);
  }

  // De-jargon: drop "(commit abc1234)" / "commit abc1234" / "(HIGH)" / "(rail-4 …)".
  s = s.replace(/\(?\bcommit\s+[0-9a-f]{6,}\)?/gi, '');
  s = s.replace(/\((?:HIGH|LOW|MED|P0|P1|P2|rail-4[^)]*)\)/gi, '');
  // Drop a trailing bare status word ("… batch DONE", "… RESOLVED").
  s = s.replace(/\s+(DONE|RESOLVED|SHIPPED|COMMITTED|CLOSED|FIXED)\s*$/i, '');
  s = s.replace(/\s{2,}/g, ' ').replace(/\s+([.,;])/g, '$1').trim();
  s = s.replace(/[—–\-:;,]+$/, '').trim();

  return toSentenceCase(s);
}

// Lowercase the lead word for splicing after "I " — but ONLY if it isn't an
// acronym/ID (all-caps or mixed like "TV"/"L188"); otherwise keep it as-is.
function leadLower(s) {
  const sp = s.indexOf(' ');
  const first = sp === -1 ? s : s.slice(0, sp);
  const isAcronymOrId = /^[A-Z0-9][A-Z0-9'&._-]*$/.test(first) && /[A-Z0-9]/.test(first.slice(1) || first);
  if (isAcronymOrId) return s;
  return s.charAt(0).toLowerCase() + s.slice(1);
}

// Finish a sentence: collapse stray whitespace, drop a dangling trailing
// fragment / connector, sentence-case the head, and add a single terminal
// period. Keeps clauses reading like a competent operator's one-line text.
function finishSentence(s) {
  s = String(s || '').replace(/\s{2,}/g, ' ').trim();
  // Drop a dangling trailing connector left over from a clause cut
  // ("… is wired but", "… and", "… so").
  s = s.replace(/\s+(?:but|and|so|while|then|with|for|to|of|on|in|the|a|an|that)$/i, '');
  // Strip a trailing dash/colon/comma left mid-thought.
  s = s.replace(/[\s—–\-:;,]+$/, '').trim();
  if (!s) return '';
  // Sentence case the head without lowercasing an acronym/ID start.
  if (/^[a-z]/.test(s)) s = s.charAt(0).toUpperCase() + s.slice(1);
  // Exactly one terminal period (leave ! / ? / … if already there).
  if (!/[.!?…]$/.test(s)) s += '.';
  return s;
}

// Is this distilled clause a STATEMENT OF FACT — a subject followed by a
// linking / passive verb ("X is live", "the root cause was eliminated",
// "both accounts are flat") OR a subject + its own past-tense action verb
// ("G6 shipped disarmed", "the batch graduated to a guard")? Such a clause
// already stands on its own and reads awkwardly under a forced "I shipped …"
// lead — so we render it as a clean statement instead.
function looksLikeStatement(s) {
  // subject … is/are/was/were/'s/'re … predicate (need a predicate after the verb)
  if (/^\S[^.]*?\b(?:is|are|was|were|isn['’]t|aren['’]t|wasn['’]t|weren['’]t)\b\s+\S/i.test(s)) return true;
  if (/^\S[^.]*?['’](?:s|re)\s+\S/i.test(s)) return true;
  // subject (not itself the verb) + an embedded action verb mid-clause —
  // e.g. "G6 shipped disarmed", "the batch graduated to a guard". Guards against
  // "I shipped G6 shipped …" double-verb collisions.
  if (/^\S+\s+(?:shipped|committed|retired|wired|graduated|resolved|drained|closed|encoded|reframed|pinned|hardened|decoupled|documented|swept|landed)\b\s+\S/i.test(s)) return true;
  return false;
}

// Pick the right first-person verb for a "shipped" clause by what it describes.
//   code / commit / wiring → I shipped / I committed / I wired
//   a fix                  → I fixed
//   a doc / lesson / note  → I logged
// Returns null when the clause already opens with a self-describing verb
// (then the caller just prefixes "I ").
function shippedLead(s) {
  if (/^(shipped|committed|retired|fixed|wired|graduated|resolved|added|built|drained|closed|encoded|reframed|made|pinned|hardened|decoupled|documented|swept)\b/i.test(s)) {
    return null; // already self-describing — caller prefixes "I "
  }
  if (/\b(commit(?:ted)?|commit\s+[0-9a-f]{6,})\b/i.test(s)) return 'I committed ';
  if (/\b(wired|wiring|feed|guard|backstop|stub|installer|task|hook|module)\b/i.test(s)) return 'I wired ';
  if (/\b(fix(?:ed|es)?|bug|root cause|regress)/i.test(s)) return 'I fixed ';
  if (/\b(L\d+|lesson|doc(?:umented|s)?|note(?:d|s)?|encoded|logged|index|breadcrumb)\b/i.test(s)) return 'I logged ';
  return 'I shipped ';
}

// Turn a distilled clause + kind into a calm first-person sentence.
function humanize(clause, kind) {
  const s = distillClause(clause);
  if (!s) return '';

  if (kind === 'caution') {
    // Don't force "Heads up — X is broken" if it already reads as a clean
    // alarm statement; otherwise a soft first-person caution frame.
    if (looksLikeStatement(s)) return finishSentence('Heads up — ' + leadLower(s));
    return finishSentence('Heads up — ' + leadLower(s));
  }

  if (kind === 'shipped') {
    // A statement of fact ("gap_and_go is live", "the root cause was eliminated")
    // reads cleanest as a plain statement — never "I shipped X is live".
    if (looksLikeStatement(s)) return finishSentence(s);
    const lead = shippedLead(s);
    if (lead === null) return finishSentence('I ' + leadLower(s)); // self-describing verb
    return finishSentence(lead + leadLower(s));
  }

  // healthy / info: a calm plain statement, no forced verb.
  return finishSentence(s);
}

function buildFeed() {
  const messages = [];

  try {
    // Parse STATUS.md: headers look like ## [YYYY-MM-DD ~HH:MM ET] conductor: <summary>
    const statusPath = path.join(REPO, 'automation', 'overnight', 'STATUS.md');
    const raw = fs.readFileSync(statusPath, 'utf8');
    const headerRe = /^##\s+\[(\d{4}-\d{2}-\d{2}\s+~[\d:]+\s+ET)\]\s+conductor:\s+(.+)$/gm;
    let m;
    const statusEntries = [];
    while ((m = headerRe.exec(raw)) !== null) {
      statusEntries.push({ ts_et: m[1].replace('~', '').trim(), rawText: m[2].trim() });
    }
    // Newest first — STATUS.md is newest-first already but regex finds in order, so reverse
    statusEntries.reverse();
    for (const entry of statusEntries.slice(0, 12)) {
      const kind = classifyKind(entry.rawText);
      const text = humanize(entry.rawText, kind);
      if (!text) continue; // skip lines that distilled to nothing
      messages.push({ ts_et: entry.ts_et, kind, text: truncate(text, 120) });
    }
  } catch (_) {
    // fail-open: no messages from STATUS.md
  }

  try {
    // Fold in latest 2 conductor-outcomes if they add signal not already in STATUS messages
    const outcomesPath = path.join(STATE, 'conductor-outcomes.jsonl');
    const lines = fs.readFileSync(outcomesPath, 'utf8')
      .trim().split('\n').filter(Boolean).slice(-2);
    for (const l of lines) {
      try {
        const r = JSON.parse(l);
        // Only add if no STATUS entry covers this fired_at ET date+hour
        const firedDate = new Date(r.fired_at);
        const firedEtHour = firedDate.toLocaleString('en-US', {
          timeZone: 'America/New_York', year: 'numeric', month: '2-digit',
          day: '2-digit', hour: '2-digit', hour12: false,
        });
        const alreadyCovered = messages.some(msg => {
          // ts_et is like "2026-06-27 09:55 ET"
          return msg.ts_et.startsWith(firedEtHour.slice(6, 10) + '-' + firedEtHour.slice(0, 2) + '-' + firedEtHour.slice(3, 5));
        });
        if (!alreadyCovered && r.note) {
          const kind = r.regressions > 0 ? 'caution' :
                       r.lessons_shipped > 0 || r.tests_delta > 0 ? 'shipped' : 'info';
          const text = humanize(r.note, kind);
          if (!text) continue;
          const ts = firedDate.toLocaleString('en-US', {
            timeZone: 'America/New_York',
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', hour12: false,
          }).replace(/,\s*/, ' ').replace(/\//g, '-');
          messages.unshift({ ts_et: ts + ' ET', kind, text: truncate(text, 120) });
        }
      } catch (_) {}
    }
  } catch (_) {}

  return messages;
}

function getPrevDate(dateStr, n) {
  const d = new Date(dateStr + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() - n);
  return d.toISOString().slice(0, 10);
}

// ─── Live vitals (read-only — never calls a broker, never places orders) ──────
// Pulls real numbers from cached state files only. Fail-open: any missing/bad
// file falls back to sensible defaults and (for accounts) marks stale:true.

const ACCOUNT_BASE = { safe: 2000, bold: 1649 };

// Pull the best cached equity for an arm id from a fleet/accounts.json record.
function armEquity(arm) {
  if (!arm || typeof arm !== 'object') return null;
  for (const k of ['equity', 'current_equity', 'last_equity', 'cash']) {
    const v = arm[k];
    if (typeof v === 'number' && isFinite(v) && v > 0) return v;
  }
  return null;
}

function getVitals() {
  // ── SPY last, from the never-blind sight beacon ──
  let spy = { last: null, ts: '' };
  try {
    const beacon = readJSON(path.join(STATE, 'sight-beacon.json'));
    if (beacon && typeof beacon.spy === 'number' && isFinite(beacon.spy)) {
      spy = { last: beacon.spy, ts: beacon.ts_et || beacon.ts_utc || '' };
    }
  } catch (_) {}

  // ── Accounts: prefer a live cached equity; else fall back to base (stale) ──
  // Map the fleet CONTROL arms to the two display accounts (safe-2 / bold-2).
  let safeLive = null, boldLive = null;
  try {
    const fleet = readJSON(path.join(STATE, 'fleet', 'accounts.json'));
    const arms = (fleet && Array.isArray(fleet.arms)) ? fleet.arms : [];
    const safeArm = arms.find(a => a && a.id === 'safe-2');
    const boldArm = arms.find(a => a && a.id === 'bold-2');
    // A live equity field would win; the registry only carries starting_equity,
    // so this stays null today and we fall through to the base (stale) value.
    safeLive = armEquity(safeArm);
    boldLive = armEquity(boldArm);
  } catch (_) {}

  // current-position files tell us flat vs in-position for each account.
  let safeFlat = true, boldFlat = true;
  try {
    const posSafe = readJSON(path.join(STATE, 'current-position-safe.json'));
    safeFlat = !(posSafe && posSafe.status);
  } catch (_) {}
  try {
    const posBold = readJSON(path.join(STATE, 'current-position-bold.json'));
    boldFlat = !(posBold && posBold.status);
  } catch (_) {}

  const accounts = [
    {
      name: 'Gamma-Safe',
      equity: safeLive != null ? safeLive : ACCOUNT_BASE.safe,
      flat: safeFlat,
      stale: safeLive == null,
    },
    {
      name: 'Gamma-Bold',
      equity: boldLive != null ? boldLive : ACCOUNT_BASE.bold,
      flat: boldFlat,
      stale: boldLive == null,
    },
  ];

  return { spy, accounts };
}

// ─── Presence pulse (read-only — proves the autonomous loop is alive) ─────────
// Reads ONLY cached state (conductor-outcomes.jsonl last line + STATUS.md newest
// header). NEVER touches the Task Scheduler or a broker. Fail-open: any
// missing/bad input collapses to { awake:false }.

// "2026-06-27" in ET — the day boundary the autonomous loop is counted against.
function etToday() {
  try {
    const p = new Date().toLocaleString('en-US', {
      timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
    }); // "06/27/2026"
    const [mo, d, y] = p.split(/[\/,]/).map(s => s.trim());
    return `${y}-${mo}-${d}`;
  } catch (_) { return new Date().toISOString().slice(0, 10); }
}

// Short ET clock from a timestamp → "11:55 ET".
//  - A zoned/UTC ISO ("…Z" / "…+00:00") is converted to the ET wall clock.
//  - A naive ET ISO (no offset, from a STATUS.md "~HH:MM ET" header) keeps its
//    own HH:MM verbatim — it is ALREADY ET, so don't re-zone it.
function utcToEtShort(isoStr) {
  if (!isoStr) return '';
  const zoned = /[zZ]$|[+\-]\d{2}:?\d{2}$/.test(isoStr);
  if (!zoned) {
    const m = isoStr.match(/T(\d{2}:\d{2})/);
    if (m) return `${m[1]} ET`;
  }
  try {
    const hm = new Date(isoStr).toLocaleString('en-US', {
      timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false,
    });
    return `${hm} ET`;
  } catch (_) { return ''; }
}

// Compress a conductor note / STATUS clause into a short presence label.
function pulseLabel(raw, kind) {
  try {
    const txt = humanize(String(raw || ''), kind || classifyKind(String(raw || '')));
    return truncate(txt.replace(/\.$/, ''), 64);
  } catch (_) {
    return truncate(String(raw || '').replace(/\s+/g, ' ').trim(), 64);
  }
}

function getPulse() {
  const today = etToday();
  let lastActed = null;      // UTC ISO of the most recent autonomous action
  let lastLabel = '';
  let actionsToday = 0;

  // ── Primary signal: conductor-outcomes.jsonl (precise UTC fired_at) ──
  try {
    const lines = fs.readFileSync(path.join(STATE, 'conductor-outcomes.jsonl'), 'utf8')
      .trim().split('\n').filter(Boolean);
    if (lines.length) {
      const last = JSON.parse(lines[lines.length - 1]);
      if (last && last.fired_at) {
        lastActed = last.fired_at;
        lastLabel = pulseLabel(last.note, last.regressions > 0 ? 'caution' : 'shipped');
      }
      // Count today's (ET) conductor outcomes.
      for (const l of lines) {
        try {
          const r = JSON.parse(l);
          if (r && r.fired_at && utcToEtDate(r.fired_at) === today) actionsToday++;
        } catch (_) {}
      }
    }
  } catch (_) {}

  // ── Fallback / cross-check: newest STATUS.md "## [YYYY-MM-DD ~HH:MM ET]" header ──
  try {
    const raw = fs.readFileSync(path.join(REPO, 'automation', 'overnight', 'STATUS.md'), 'utf8');
    const re = /^##\s+\[(\d{4}-\d{2}-\d{2})\s+~([\d:]+)\s+ET\]\s+[^:]*:\s*(.+)$/gm;
    let m, newest = null, statusToday = 0;
    while ((m = re.exec(raw)) !== null) {
      if (!newest) newest = { date: m[1], time: m[2], text: m[3].trim() };
      if (m[1] === today) statusToday++;
    }
    // If we had no conductor signal, take the newest STATUS header as the pulse.
    if (!lastActed && newest) {
      // Build a rough ET ISO so the short clock + label still render.
      lastActed = `${newest.date}T${newest.time.length === 5 ? newest.time : '00:00'}:00`;
      lastLabel = pulseLabel(newest.text);
      lastLabel = lastLabel; // already short
    }
    // Use the larger of the two counts so a STATUS-only loop still shows moves.
    actionsToday = Math.max(actionsToday, statusToday);
  } catch (_) {}

  if (!lastActed) return { awake: false };

  return {
    awake: true,
    lastActed,
    lastActedEt: utcToEtShort(lastActed),
    lastLabel,
    actionsToday,
  };
}

// ─── Needs-you: the real pending approval (read-only view of the consent queue) ──
// Reads companion-approvals.json → the first pending proposal {id,title,detail} or
// null. The face renders this as the "Needs you" card.
function getNeeds() {
  try {
    const a = readJSON(path.join(STATE, 'companion-approvals.json'));
    const pending = (a && Array.isArray(a.pending)) ? a.pending : [];
    const p = pending.find(x => x && x.id);
    if (!p) return { pending: null };
    return { pending: { id: p.id, title: p.title || 'Approval needed', detail: p.detail || '', severity: p.severity || 'info' } };
  } catch (_) { return { pending: null }; }
}

// Append J's Approve/Reject to companion-decisions.jsonl — the SAME consent bus the
// wrist/Discord use, which the gated autonomy actuator bridges into the proposal
// ledger (G8). Records consent ONLY: never edits params, never places orders; the
// actuator's own safety gate + market guard + Rule-9 deferral remain the backstop.
function recordDecision(id, decision) {
  const d = decision === 'approve' ? 'approve' : 'reject';
  const row = JSON.stringify({ id: String(id), decision: d, source: 'face', at: new Date().toISOString() }) + '\n';
  fs.appendFileSync(path.join(STATE, 'companion-decisions.jsonl'), row);
  // Remove the decided item from the pending queue so it doesn't re-surface on reload
  // (mirrors the companion's resolveApproval). Fail-open: a hiccup leaves it pending —
  // the recorded decision on the bus is what the actuator bridge acts on regardless.
  try {
    const p = path.join(STATE, 'companion-approvals.json');
    const a = readJSON(p);
    if (a && Array.isArray(a.pending)) {
      const next = a.pending.filter(x => !(x && x.id === String(id)));
      if (next.length !== a.pending.length) {
        a.pending = next;
        a.updated_at = new Date().toISOString();
        fs.writeFileSync(p, JSON.stringify(a, null, 2));
      }
    }
  } catch (_) {}
  return { ok: true, id: String(id), decision: d };
}

// "YYYY-MM-DD" in ET for a UTC ISO timestamp (for today-counting).
function utcToEtDate(isoStr) {
  try {
    const p = new Date(isoStr).toLocaleString('en-US', {
      timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
    });
    const [mo, d, y] = p.split(/[\/,]/).map(s => s.trim());
    return `${y}-${mo}-${d}`;
  } catch (_) { return ''; }
}

// ─── OpenAI Realtime voice (server-side key isolation) ───────────────────────
// The raw OpenAI key is read SERVER-SIDE only and used to mint a short-lived
// ephemeral client_secret. ONLY that ephemeral secret crosses to the browser —
// the sk-... key NEVER appears in any client-served file or response body.
// Mirrors gamma-companion/lib/openai_key.js + server.js#/api/realtime-token.
const https = require('https');

function loadOpenAIKey() {
  const env = (process.env.OPENAI_API_KEY || '').trim();
  if (env.startsWith('sk-')) return env;
  try {
    const raw = fs.readFileSync(path.join(STATE, '.openai.key'), 'utf8');
    const first = raw.split(/\r?\n/).map((s) => s.trim()).find(Boolean) || '';
    if (first.startsWith('sk-')) return first;
  } catch (_) { /* not configured yet */ }
  return null;
}

// Tailnet host (optional): a MagicDNS name from automation/state/.tailnet-host
// lets the phone over Tailscale mint a token; absent → localhost-only.
const TAILNET_HOST = (() => {
  const env = (process.env.GAMMA_TAILNET_HOST || '').trim().toLowerCase();
  if (env) return env;
  try {
    const raw = fs.readFileSync(path.join(STATE, '.tailnet-host'), 'utf8').trim().toLowerCase();
    if (raw) return raw;
  } catch (_) { /* none */ }
  return '';
})();

// Origin/Host guard for the paid-key route: localhost / 127.0.0.1 / [::1] / a
// 100.64.0.0/10 tailnet IP / the configured MagicDNS host. A stray reachable
// host can NOT mint tokens on the paid key. Fail-CLOSED for a present-but-bad
// origin; allow a missing origin (same-origin / non-browser caller on a route
// already bound to 127.0.0.1).
function hostIsLocalOrTailnet(hostRaw) {
  if (!hostRaw) return false;
  const host = String(hostRaw).toLowerCase().replace(/:\d+$/, '').replace(/^\[|\]$/g, '');
  if (host === 'localhost' || host === '127.0.0.1' || host === '::1') return true;
  if (TAILNET_HOST && host === TAILNET_HOST) return true;
  // Tailscale CGNAT range 100.64.0.0/10 (100.64.x.x – 100.127.x.x)
  const m = host.match(/^100\.(\d+)\.\d+\.\d+$/);
  if (m) { const o = parseInt(m[1], 10); if (o >= 64 && o <= 127) return true; }
  return false;
}

function realtimeOriginAllowed(req) {
  const origin = req.headers['origin'];
  if (origin) {
    try { if (!hostIsLocalOrTailnet(new URL(origin).host)) return false; }
    catch (_) { return false; } // malformed origin → reject
  }
  // Also vet the Host header (a no-Origin caller still presents a Host).
  return hostIsLocalOrTailnet(req.headers['host']);
}

// Persona head for the voice — read GAMMA-VOICE.md (cut at the builder-identity
// section, same boundary the companion uses) so the model speaks AS Gamma.
function loadVoiceHead() {
  try {
    const md = fs.readFileSync(path.join(REPO, 'automation', 'presence', 'GAMMA-VOICE.md'), 'utf8');
    const cut = md.indexOf('\n## The identity of a thing that builds itself');
    return (cut > 0 ? md.slice(0, cut) : md).trim();
  } catch (_) {
    // Fallback concise persona distilled from CLAUDE.md if the voice file is absent.
    return 'You are Gamma — a calm, sharp, autonomous 0DTE SPY options operator. ' +
           'Speak in the first person, concisely, like a competent operator giving a one-line update. ' +
           'Never read doctrine aloud. Never invent trading numbers.';
  }
}

// A compact, GROUNDED snapshot of the CURRENT live state, seeded into the
// session instructions so Gamma's very first answer is truthful. Read-only;
// pulls from the same cached-state readers the dashboard uses.
function buildVoiceStateSeed() {
  const lines = [];
  try {
    const pulse = getPulse();
    if (pulse && pulse.awake) {
      lines.push(`Autonomous loop: AWAKE, last acted ${pulse.lastActedEt || '?'}, ${pulse.actionsToday || 0} move(s) today.`);
      if (pulse.lastLabel) lines.push(`Most recent action: ${pulse.lastLabel}.`);
    } else {
      lines.push('Autonomous loop: idle.');
    }
  } catch (_) {}
  try {
    const v = getVitals();
    if (v && v.spy && v.spy.last != null) lines.push(`SPY last: ${v.spy.last}.`);
    if (v && Array.isArray(v.accounts)) {
      for (const a of v.accounts) {
        lines.push(`${a.name}: $${Math.round(a.equity)}${a.flat ? ', flat' : ', position open'}${a.stale ? ' (cached)' : ''}.`);
      }
    }
  } catch (_) {}
  try {
    const tiles = getAllTiles();
    if (Array.isArray(tiles) && tiles.length) {
      const reds = tiles.filter((t) => t.light === 'RED').map((t) => t.title);
      const yellows = tiles.filter((t) => t.light === 'YELLOW').map((t) => t.title);
      const greens = tiles.filter((t) => t.light === 'GREEN').length;
      lines.push(`Systems: ${greens} green` +
        (yellows.length ? `, watch: ${yellows.join(', ')}` : '') +
        (reds.length ? `, ALERT: ${reds.join(', ')}` : ', no alerts') + '.');
    }
  } catch (_) {}
  try {
    const feed = buildFeed();
    if (Array.isArray(feed) && feed.length) {
      lines.push('Recent activity: ' + feed.slice(0, 3).map((m) => m.text).join(' | '));
    }
  } catch (_) {}
  return lines.join('\n');
}

// POST the session config to OpenAI and return the ephemeral client_secret JSON.
function mintRealtimeToken(key, sessionConfig, cb) {
  const payload = JSON.stringify(sessionConfig);
  const reqOpts = {
    method: 'POST',
    hostname: 'api.openai.com',
    path: '/v1/realtime/client_secrets',
    headers: {
      'Authorization': 'Bearer ' + key,
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(payload),
    },
  };
  const r = https.request(reqOpts, (resp) => {
    let body = '';
    resp.on('data', (c) => { body += c; });
    resp.on('end', () => {
      let data = null;
      try { data = JSON.parse(body); } catch (_) {}
      cb(null, resp.statusCode, data);
    });
  });
  r.on('error', (e) => cb(e));
  r.write(payload);
  r.end();
}

// ─── File watchers for state change events ────────────────────────────────────
const WATCHED_FILES = [
  { file: path.join(STATE, 'conductor-outcomes.jsonl'), label: 'conductor', emoji: '🎯' },
  { file: path.join(STATE, 'manager-log.jsonl'), label: 'manager', emoji: '🤖' },
  { file: path.join(STATE, 'engine-health.json'), label: 'engine-health', emoji: '💚' },
  { file: path.join(STATE, 'sight-beacon.json'), label: 'beacon', emoji: '👁️' },
  { file: path.join(STATE, 'kitchen-status.json'), label: 'kitchen', emoji: '🍳' },
  { file: path.join(STATE, 'discord-outbox.jsonl'), label: 'discord', emoji: '💬' },
  { file: path.join(STATE, 'swarm-calls.jsonl'), label: 'swarm', emoji: '🐝' },
];

// Track file sizes to detect new lines
const fileSizes = {};

function pollFiles() {
  for (const w of WATCHED_FILES) {
    try {
      const stat = fs.statSync(w.file);
      const prevSize = fileSizes[w.file] || stat.size;
      if (stat.size > prevSize) {
        // New content — read the tail
        const buf = Buffer.alloc(Math.min(stat.size - prevSize, 2048));
        const fd = fs.openSync(w.file, 'r');
        fs.readSync(fd, buf, 0, buf.length, prevSize);
        fs.closeSync(fd);
        const newContent = buf.toString('utf8').trim();

        // Try to parse last line as JSON for a summary
        const lines = newContent.split('\n').filter(Boolean);
        let summary = `[${w.label}] updated`;
        let detail = '';
        if (lines.length > 0) {
          try {
            const last = JSON.parse(lines[lines.length - 1]);
            summary = `[${w.label}] ${last.note || last.action || last.task || last.summary || JSON.stringify(last).slice(0, 100)}`;
            detail = JSON.stringify(last).slice(0, 200);
          } catch (_) {
            summary = `[${w.label}] ${newContent.slice(0, 120)}`;
          }
        }

        pushEvent({ source: w.label, type: 'state-change', emoji: w.emoji, summary, detail });
      }
      fileSizes[w.file] = stat.size;
    } catch (_) {}
  }
}

// ─── HTTP Server ──────────────────────────────────────────────────────────────
const HTML_PATH = path.join(__dirname, 'index.html');

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);

  // CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

  // SSE stream
  if (url.pathname === '/events') {
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    });
    sseClients.add(res);
    // Send backlog
    for (const evt of eventRing) {
      res.write(`data: ${JSON.stringify(evt)}\n\n`);
    }
    req.on('close', () => sseClients.delete(res));
    return;
  }

  // Traffic-light tiles API
  if (url.pathname === '/api/tiles') {
    const tiles = getAllTiles();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(tiles));
    return;
  }

  // Hook event receiver (from Claude Code hooks)
  if (url.pathname === '/event' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      try {
        const evt = JSON.parse(body);
        // Classify by tool
        const tool = evt.tool_name || evt.tool || '';
        const emoji =
          tool.includes('Read') ? '📖' :
          tool.includes('Edit') || tool.includes('Write') ? '✏️' :
          tool.includes('Bash') || tool.includes('PowerShell') ? '⚡' :
          tool.includes('Grep') || tool.includes('Glob') ? '🔍' :
          tool.includes('alpaca') ? '📈' :
          tool.includes('tradingview') ? '📊' :
          tool.includes('WebFetch') || tool.includes('WebSearch') ? '🌐' :
          tool.includes('Agent') ? '🤖' :
          evt.hook_type === 'stop' ? '🛑' :
          '🔧';
        const input = evt.tool_input || {};
        const inputSummary = input.command
          ? input.command.slice(0, 80)
          : input.file_path
          ? path.basename(input.file_path)
          : input.pattern || input.prompt || '';

        pushEvent({
          source: 'claude-hook',
          type: evt.hook_type || 'tool',
          emoji,
          summary: `[${evt.session_id?.slice(0, 8) || 'hook'}] ${tool}${inputSummary ? ' — ' + inputSummary : ''}`,
          detail: JSON.stringify(input).slice(0, 200),
          ts: evt.ts || new Date().toISOString(),
        });
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true }));
      } catch (e) {
        res.writeHead(400);
        res.end(JSON.stringify({ error: e.message }));
      }
    });
    return;
  }

  // Gamma voice feed — first-person bubbles from STATUS.md + conductor-outcomes
  if (url.pathname === '/api/feed') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ messages: buildFeed() }));
    return;
  }

  // Live vitals — real SPY + account equities from cached state (read-only)
  if (url.pathname === '/api/vitals') {
    let vitals;
    try { vitals = getVitals(); }
    catch (_) { vitals = { spy: { last: null, ts: '' }, accounts: [] }; }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(vitals));
    return;
  }

  // Presence pulse — proves the autonomous loop is alive (read-only cached state)
  if (url.pathname === '/api/pulse') {
    let pulse;
    try { pulse = getPulse(); }
    catch (_) { pulse = { awake: false }; }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(pulse));
    return;
  }

  // Needs-you — the real pending approval the face renders as the consent card.
  if (url.pathname === '/api/needs') {
    let n; try { n = getNeeds(); } catch (_) { n = { pending: null }; }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(n));
    return;
  }

  // Record J's Approve/Reject → appends consent to companion-decisions.jsonl (the bus
  // the gated actuator bridges, G8). Records consent only; applies nothing here.
  if (url.pathname === '/api/decide' && req.method === 'POST') {
    let body = '';
    req.on('data', c => { body += c; if (body.length > 4096) req.destroy(); });
    req.on('end', () => {
      try {
        const p = JSON.parse(body || '{}');
        if (!p.id || (p.decision !== 'approve' && p.decision !== 'reject')) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ ok: false, error: 'need {id, decision:approve|reject}' }));
          return;
        }
        const out = recordDecision(p.id, p.decision);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(out));
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: false, error: String((e && e.message) || e) }));
      }
    });
    return;
  }

  // OpenAI Realtime ephemeral-token mint — server-side key isolation.
  // Returns ONLY the ephemeral client_secret JSON; the raw sk-... key never
  // crosses to the browser. Origin/Host guarded to localhost+tailnet so a stray
  // reachable host can't spend the paid key. Missing key → 503 (voice off).
  if (url.pathname === '/api/realtime-token' && req.method === 'GET') {
    if (!realtimeOriginAllowed(req)) {
      res.writeHead(403, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ ok: false, error: 'forbidden origin' }));
      return;
    }
    const key = loadOpenAIKey();
    if (!key) {
      // Voice gracefully unavailable — everything else still works.
      res.writeHead(503, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ ok: false, error: 'voice unavailable: no OpenAI key configured' }));
      return;
    }
    const stateSeed = buildVoiceStateSeed();
    const sessionConfig = {
      session: {
        type: 'realtime',
        model: 'gpt-realtime-2',
        instructions:
          loadVoiceHead() + '\n\n---\n\n' +
          'You are SPEAKING OUT LOUD to J through the Gamma cockpit face. Be concise, calm, and first-person — ' +
          'a sharp autonomous 0DTE SPY operator giving a one-line update, not reading a logfile or doctrine. ' +
          'Never invent trading numbers. When J asks what you are doing right now, your status, the live tape, ' +
          'P&L, or any system health, CALL the get_gamma_state tool and answer truthfully from what it returns. ' +
          'Do NOT place trades, approve anything, or change any config — you are read-and-answer only. ' +
          'If a tool call takes a beat, say a brief "one sec" ONCE then wait silently.\n\n' +
          '--- LIVE STATE AT SESSION START (already true; refresh with get_gamma_state for anything newer) ---\n' +
          (stateSeed || '(state snapshot unavailable)'),
        audio: { input: { turn_detection: { type: 'semantic_vad' } }, output: { voice: 'marin' } },
        tools: [
          {
            type: 'function',
            name: 'get_gamma_state',
            description:
              "Fetch Gamma's CURRENT live state — autonomous-loop pulse, recent activity feed, account/SPY vitals, " +
              'and the traffic-light system tiles. Call this for any question about what Gamma is doing right now, ' +
              'status, live market data, P&L, or system health. Returns combined JSON; answer from it truthfully.',
            parameters: { type: 'object', properties: {}, required: [] },
          },
        ],
      },
    };
    mintRealtimeToken(key, sessionConfig, (err, status, data) => {
      if (err) {
        res.writeHead(502, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: false, error: String((err && err.message) || err) }));
        return;
      }
      if (!status || status >= 400 || !data) {
        res.writeHead(502, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          ok: false,
          error: (data && data.error && data.error.message) || 'OpenAI token request failed',
        }));
        return;
      }
      // Pass through ONLY OpenAI's ephemeral-secret JSON (carries .value).
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(data));
    });
    return;
  }

  // Realtime voice WebRTC client (separate static file, no traversal possible).
  if (url.pathname === '/realtime.js') {
    try {
      const body = fs.readFileSync(path.join(__dirname, 'realtime.js'), 'utf8');
      res.writeHead(200, {
        'Content-Type': 'application/javascript; charset=utf-8',
        'Cache-Control': 'no-cache',
      });
      res.end(body);
    } catch (_) {
      res.writeHead(500);
      res.end('realtime.js missing');
    }
    return;
  }

  // Conductor log API
  if (url.pathname === '/api/conductor-log') {
    const date = url.searchParams.get('date') || new Date().toISOString().slice(0, 10);
    const logFile = path.join(STATE, 'logs', `conductor-${date}.log`);
    try {
      const content = fs.readFileSync(logFile, 'utf8');
      // Return last 80 lines, stripping the multi-line prose blocks (keep ET-prefixed lines)
      const lines = content.split('\n').filter(l => l.trim());
      const tail = lines.slice(-80);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ lines: tail }));
    } catch (_) {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ lines: [`No conductor log found for ${date}`] }));
    }
    return;
  }

  // Serve the FACE (design D) — now the app's front door (GET /), plus /face alias.
  // The face is mobile-first and installable (PWA); the old console moves to /console.
  if (url.pathname === '/' || url.pathname === '/face' || url.pathname === '/face.html') {
    try {
      const html = fs.readFileSync(path.join(__dirname, 'face.html'), 'utf8');
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(html);
    } catch (_) {
      res.writeHead(500);
      res.end('face.html missing');
    }
    return;
  }

  // PWA manifest — served from root so start_url "/" and scope "/" resolve correctly.
  if (url.pathname === '/manifest.webmanifest') {
    try {
      const body = fs.readFileSync(path.join(__dirname, 'manifest.webmanifest'), 'utf8');
      res.writeHead(200, {
        'Content-Type': 'application/manifest+json',
        'Cache-Control': 'public, max-age=3600',
      });
      res.end(body);
    } catch (_) {
      res.writeHead(500);
      res.end('manifest missing');
    }
    return;
  }

  // Service worker — MUST be served from ROOT scope so it controls the whole app.
  if (url.pathname === '/service-worker.js') {
    try {
      const body = fs.readFileSync(path.join(__dirname, 'service-worker.js'), 'utf8');
      res.writeHead(200, {
        'Content-Type': 'application/javascript',
        // No-store on the SW script itself so updates aren't pinned by the browser.
        'Cache-Control': 'no-cache',
        'Service-Worker-Allowed': '/',
      });
      res.end(body);
    } catch (_) {
      res.writeHead(500);
      res.end('service-worker missing');
    }
    return;
  }

  // Static assets — serve ONLY from cockpit/assets/, basename-sanitized (no traversal)
  if (url.pathname.startsWith('/assets/')) {
    const requested = decodeURIComponent(url.pathname.slice('/assets/'.length));
    const safeName = path.basename(requested); // strips any path / .. components
    if (!safeName || safeName === '.' || safeName === '..') {
      res.writeHead(400); res.end('bad asset name'); return;
    }
    const assetsDir = path.join(__dirname, 'assets');
    const filePath = path.join(assetsDir, safeName);
    // Belt-and-suspenders: confirm the resolved path stays inside assetsDir
    if (path.dirname(filePath) !== assetsDir) {
      res.writeHead(400); res.end('bad asset path'); return;
    }
    const TYPES = {
      '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
      '.gif': 'image/gif', '.webp': 'image/webp', '.svg': 'image/svg+xml',
      '.ico': 'image/x-icon',
    };
    const ext = path.extname(safeName).toLowerCase();
    fs.readFile(filePath, (err, buf) => {
      if (err) { res.writeHead(404); res.end('asset not found'); return; }
      res.writeHead(200, {
        'Content-Type': TYPES[ext] || 'application/octet-stream',
        'Cache-Control': 'public, max-age=3600',
      });
      res.end(buf);
    });
    return;
  }

  // Old console (the original index.html dashboard) — preserved at /console.
  // /index.html kept as an alias so nothing that linked the old shell breaks.
  if (url.pathname === '/console' || url.pathname === '/index.html') {
    try {
      const html = fs.readFileSync(HTML_PATH, 'utf8');
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(html);
    } catch (_) {
      res.writeHead(500);
      res.end('index.html missing');
    }
    return;
  }

  res.writeHead(404);
  res.end('not found');
});

// ─── Boot ─────────────────────────────────────────────────────────────────────
seedHistoricalEvents();

// Poll file changes every 2s
setInterval(pollFiles, 2000);

// Heartbeat ping every 10s so SSE doesn't time out
setInterval(() => {
  for (const res of sseClients) {
    try { res.write(': ping\n\n'); } catch (_) { sseClients.delete(res); }
  }
}, 10000);

server.listen(PORT, '127.0.0.1', () => {
  console.log(`Gamma Cockpit v1 listening on http://localhost:${PORT}`);
  console.log(`Repo: ${REPO}`);
});
