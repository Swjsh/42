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

const PORT = 4500;
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

function getPrevDate(dateStr, n) {
  const d = new Date(dateStr + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() - n);
  return d.toISOString().slice(0, 10);
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

  // Serve main HTML
  if (url.pathname === '/' || url.pathname === '/index.html') {
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
