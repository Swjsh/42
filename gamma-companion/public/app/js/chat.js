/* chat.js — THE CONSOLE. J: "i want this to be my daily driver, only talking to
 * the orchestrator panel using full claude code capabilities, hooks for following
 * all my rules, agent orchestration etc."
 *
 * So this is not a chat bubble. It is the operating surface: a real Claude Code
 * session with the full tool set, running in the repo, with its work made visible
 * rather than hidden behind a spinner. The visual anatomy still comes from the
 * ai-assistat component J picked — tinted header, deep body, floating-glyph empty
 * state, pill composer with a round send — but everything below the surface is a
 * console.
 *
 * WHAT IT SHOWS THAT A CHAT DOES NOT
 *   · every tool call as it happens, grouped and readable ("Read gamma_home.py"),
 *     because a daily driver has to be auditable while it works;
 *   · SUBAGENTS: an Agent/Task call is promoted to its own tracked row, so an
 *     orchestration fan-out is legible instead of looking like one long pause;
 *   · a HOOK that blocks something is surfaced loudly rather than swallowed — the
 *     rules are the point, and a silently-blocked action is the failure mode J has
 *     been bitten by;
 *   · interrupt. A console you cannot stop is not a console.
 *
 * HONESTY: nothing here fakes progress. If the companion is unreachable it says so;
 * a stopped run is labelled stopped, never "done". */
(function (G) {
  'use strict';
  const D = G.data, esc = D.esc, el = D.el;

  const st = {
    turns: [], session: null, busy: false, es: null, askId: null,
    model: 'opus', pinned: true, agents: {},
  };

  const ICON = {
    spark: '<path d="M12 2l1.9 5.7a4 4 0 0 0 2.4 2.4L22 12l-5.7 1.9a4 4 0 0 0-2.4 2.4L12 22l-1.9-5.7a4 4 0 0 0-2.4-2.4L2 12l5.7-1.9a4 4 0 0 0 2.4-2.4L12 2z"/>',
  };
  const spark = (cls) => '<svg class="' + (cls || '') + '" viewBox="0 0 24 24" ' +
    'fill="currentColor" aria-hidden="true" width="100%" height="100%">' + ICON.spark + '</svg>';
  const SEND = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" width="19" height="19" aria-hidden="true">' +
    '<path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>';
  const STOPI = '<svg viewBox="0 0 24 24" fill="currentColor" width="15" height="15" ' +
    'aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';

  /* ---- persistence ------------------------------------------------------- */
  try {
    const s = JSON.parse(localStorage.getItem('gamma-console') || 'null');
    if (s) {
      st.session = s.session || null;
      st.model = s.model || 'opus';
      st.turns = (s.turns || []).filter((t) => t && t.text);
    }
  } catch (_) { /* a cleared store is an empty console, not a broken one */ }

  function save() {
    try {
      localStorage.setItem('gamma-console', JSON.stringify({
        session: st.session, model: st.model,
        turns: st.turns.slice(-40).map((t) => ({ role: t.role, text: t.text })),
      }));
    } catch (_) { /* never let persistence break the console */ }
  }

  const body = () => document.getElementById('cbody');
  function scroll() { const b = body(); if (b && st.pinned) b.scrollTop = b.scrollHeight; }

  /* ---- turns -------------------------------------------------------------- */
  /* WHO IS TALKING. J: "it said Opus then its working so idk if its orchestrator
     or a sonnet agent like i would expect". The label rendered st.model -- the
     PICKER's value -- while a sonnet CARD RUN was streaming underneath it. The
     picker is a preference; this line has to be a fact, so a turn may carry its
     own `who` and only falls back to the picker for turns the picker started. */
  /* Wire ids ("claude-sonnet-4-6") are not words. Only the family carries meaning
     in a turn label. */
  function shortModel(m) {
    const t = String(m || '').toLowerCase();
    if (t.indexOf('opus') >= 0) return 'opus';
    if (t.indexOf('sonnet') >= 0) return 'sonnet';
    if (t.indexOf('haiku') >= 0) return 'haiku';
    if (t.indexOf('fable') >= 0) return 'fable';
    return m || '';
  }

  function push(role, text, who) {
    const e = document.getElementById('cempty'); if (e) e.remove();
    const t = { id: 't' + st.turns.length + '_' + Date.now(), role, text: text || '', steps: 0 };
    st.turns.push(t);
    const b = body(); if (!b) return t;
    const n = el('div'); n.className = 'turn turn--' + role;
    const label = role === 'me' ? 'You'
      : (who
          ? esc(who.name) + ' <i>' + esc(shortModel(who.model)) + '</i>' +
            (who.kind ? '<em class="turn__k" data-t="' + esc(who.kind) + '">' +
              esc(who.kind === 'card' ? 'action card' : who.kind) + '</em>' : '')
          : 'Gamma <i>' + esc(st.model) + '</i>');
    n.innerHTML =
      '<div class="turn__w">' + label + '</div>' +
      (role === 'gamma' ? '<div class="tl" id="tl-' + t.id + '"></div>' : '') +
      '<div class="turn__b md" id="b-' + t.id + '"></div>';
    b.appendChild(n);
    if (role === 'me') document.getElementById('b-' + t.id).textContent = t.text;
    scroll();
    return t;
  }

  /* Streamed text is buffered and painted once per tick. setTimeout, not rAF:
     rAF never fires in a hidden tab, which froze replies whenever the pane was
     not visible — found the hard way on the previous surface. */
  let buf = {}, tick = null;
  function flush() {
    tick = null;
    for (const id in buf) {
      const t = st.turns.find((x) => x.id === id);
      const n = document.getElementById('b-' + id);
      if (n && t) n.innerHTML = G.md.render(t.text);
    }
    buf = {}; scroll();
  }
  function append(id, chunk) {
    const t = st.turns.find((x) => x.id === id);
    if (t) t.text += chunk;                 // the object is the copy that gets saved
    buf[id] = 1;
    if (!tick) tick = setTimeout(flush, 40);
  }

  /* ---- the tool timeline --------------------------------------------------
     Every tool call gets a row. Names are humanised because "mcp__alpaca__get_
     account_info" is the machine's word for "check the account". */
  const VERB = {
    Read: 'Read', Edit: 'Edited', Write: 'Wrote', Bash: 'Ran', Grep: 'Searched',
    Glob: 'Found', Task: 'Spawned agent', Agent: 'Spawned agent', WebFetch: 'Fetched',
    WebSearch: 'Searched the web', TodoWrite: 'Planned', Workflow: 'Ran workflow',
  };
  function human(name, input) {
    const n = String(name || 'tool');
    const i = input || {};
    const file = i.file_path || i.path || i.notebook_path;
    const short = file ? String(file).split(/[\\/]/).pop() : '';
    if (VERB[n]) {
      if (short) return VERB[n] + ' ' + short;
      if (n === 'Bash' && i.description) return 'Ran ' + i.description;
      if (n === 'Bash' && i.command) return 'Ran ' + String(i.command).slice(0, 60);
      if ((n === 'Task' || n === 'Agent') && i.description) return 'Spawned agent · ' + i.description;
      if (i.pattern) return VERB[n] + ' ' + i.pattern;
      if (i.query) return VERB[n] + ' ' + String(i.query).slice(0, 50);
      return VERB[n];
    }
    return n.replace(/^mcp__/, '').replace(/__/g, ' · ').replace(/_/g, ' ');
  }

  function step(turnId, label, kind) {
    const host = document.getElementById('tl-' + turnId);
    if (!host) return null;
    const r = el('div'); r.className = 'tl__r';
    if (kind) r.setAttribute('data-k', kind);
    r.innerHTML = '<i class="tl__d"></i><span class="tl__t">' + esc(label) + '</span>';
    host.appendChild(r);
    const t = st.turns.find((x) => x.id === turnId); if (t) t.steps++;
    scroll();
    return r;
  }

  /* The header pill. "WORKING" alone left J unable to tell an orchestrator turn
     from a card run; it now names whichever is actually streaming. */
  function setWho(who) {
    // #cstate, not .chat__state -- I wrote the latter from memory and it matched
    // nothing, which would have made this a silent no-op.
    st.who = who || null;
    const pill = document.getElementById('cstate');
    if (!pill) return;
    pill.title = who ? (who.name + ' · ' + (who.model || '')) : 'the orchestrator';
    paintPill(st.busy);
  }

  /* The pill said "working" for everything, so an orchestrator turn and a sonnet
     card run were indistinguishable at a glance -- which is exactly what J could
     not tell. It names whichever is actually streaming. */
  function paintPill(on) {
    const pill = document.getElementById('cstate');
    if (!pill) return;
    const w = st.who;
    const label = on
      ? (w ? (w.kind === 'card' ? 'card · ' + shortModel(w.model) : shortModel(w.model) || 'working')
           : st.model)
      : 'ready';
    const span = pill.querySelector('span');
    if (span) span.textContent = label;
    if (on) pill.setAttribute('data-on', ''); else pill.removeAttribute('data-on');
  }

  function busy(on) {
    st.busy = on;
    const s = document.getElementById('csend'), i = document.getElementById('cin'),
      stop = document.getElementById('cstop'), pill = document.getElementById('cstate');
    if (s) s.hidden = on;
    if (stop) stop.hidden = !on;
    if (i) i.disabled = false;              // stay typable: queue the next thought
    st.busy = on;
    if (!on) st.who = null;     // a finished run no longer owns the header
    paintPill(on);
  }

  /* ---- send / stop -------------------------------------------------------- */
  function send(preset) {
    const i = document.getElementById('cin');
    const msg = (preset != null ? preset : (i ? i.value : '')).trim();
    if (!msg || st.busy) return;
    if (location.protocol === 'file:') {
      push('gamma', 'This page was opened as a file, so it cannot reach the companion. ' +
        'Open it over 127.0.0.1:4317 to use the console.');
      return;
    }
    if (i && preset == null) { i.value = ''; i.style.height = 'auto'; }
    push('me', msg);
    const turn = push('gamma', '');
    save(); busy(true);

    const tok = (document.querySelector('meta[name="gamma-token"]') || {}).content || '';
    fetch('/api/orchestrator-chat', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-gamma-token': tok },
      body: JSON.stringify({ message: msg, model: st.model, resume: st.session || undefined }),
    }).then((r) => r.json()).then((j) => {
      if (!j || j.ok === false) {
        step(turn.id, (j && j.error) || 'the companion refused this', 'bad');
        busy(false); return;
      }
      st.askId = j.ask_id;
      if (j.resumed_from === 'store') step(turn.id, 'continuing the stored session', 'dim');
      openStream(turn, j);
    }).catch(() => {
      step(turn.id, 'could not reach the companion on :4317', 'bad');
      busy(false);
    });
  }

  function openStream(turn, j) {
    const url = '/api/ask-stream?id=' + encodeURIComponent(j.ask_id) +
      '&tok=' + encodeURIComponent(j.stream_token);
    let es;
    try { es = new EventSource(url); }
    catch (_) { step(turn.id, 'stream unavailable', 'bad'); busy(false); return; }
    st.es = es;
    let lastTool = null, pending = null;
    const running = [];   // agent rows still in flight, in call order

    es.onmessage = (ev) => {
      let d; try { d = JSON.parse(ev.data); } catch (_) { return; }
      if (!d || !d.step) return;

      if (d.step === 'session' && d.sessionId) {
        st.session = d.sessionId; save();
        step(turn.id, (j.resumed ? 'resumed ' : 'session ') + String(d.sessionId).slice(0, 8), 'dim');

      } else if (d.step === 'delta') { turn.sawDelta = true; append(turn.id, d.text || '');

      } else if (d.step === 'text') { if (!turn.sawDelta) append(turn.id, d.text || '');

      } else if (d.step === 'thinking') { step(turn.id, 'thinking', 'dim');

      } else if (d.step === 'tool' || d.step === 'tool_start') {
        /* ONE ROW PER CALL. The server emits BOTH frames for the same tool:
           `tool_start` arrives first from the token stream (fast, but its label is
           only the tool's name) and `tool` follows from the assembled message (slow,
           but it carries the arguments, so "Finding *.md" instead of "Using Glob").
           Rendering both listed every call twice — verified live 2026-08-30. Take the
           early row for responsiveness, then UPGRADE its text in place when the
           richer frame lands. */
        const isAgent = /^(Task|Agent|Workflow)$/.test(String(d.name || ''));
        /* `label` first: the server already humanised the call WITH its arguments
           ("Finding *.md"), and only the `tool` frame carries them -- `input` is not
           on the wire, so recomputing locally degraded the upgraded row back to a
           bare verb ("Found"). human() stays as the fallback for frames that carry
           input but no label. */
        const label = d.label || human(d.name, d.input);
        if (d.step === 'tool' && pending && pending.name === String(d.name || '')) {
          pending.row.querySelector('.tl__t').textContent = label;
          if (isAgent) pending.row.setAttribute('data-k', 'agent');
          pending = null;
        } else {
          lastTool = step(turn.id, label, isAgent ? 'agent' : 'tool');
          pending = (d.step === 'tool_start') ? { name: String(d.name || ''), row: lastTool } : null;
        }
        /* AGENT ORCHESTRATION, visible. A spawned agent runs for minutes; without a
           running state the row looks identical to a finished one and a fan-out reads
           as one long pause. Rows are queued in call order because tool results come
           back in that order, so the right row gets marked done. */
        if (isAgent) {
          const row = (pending && pending.row) || lastTool;
          if (row) { row.setAttribute('data-run', ''); running.push(row); }
        }

      } else if (d.step === 'tool_result') {
        /* A HOOK BLOCK arrives as a tool error. Surfacing it loudly is the whole
           point of having the rules: a silently-swallowed guard is the failure
           mode this project has been bitten by repeatedly. */
        const prev = String(d.preview || '');
        if (d.ok === false) {
          const blocked = /hook|blocked|denied|not permitted|refus/i.test(prev);
          step(turn.id, (blocked ? 'BLOCKED BY A RULE · ' : 'failed · ') + prev.slice(0, 150),
            blocked ? 'rule' : 'bad');
        } else if (lastTool && prev) {
          lastTool.setAttribute('title', prev.slice(0, 400));
        }
        const doneRow = running.shift();
        if (doneRow) doneRow.removeAttribute('data-run');

      } else if (d.step === 'result') {
        const ok = d.ok !== false;
        step(turn.id, ok ? (d.summary || 'done') : ('stopped · ' + (d.summary || d.subtype || '')),
          ok ? 'ok' : 'bad');
        if (!ok && /error|timeout/.test(d.subtype || '') && j.resumed) st.session = null;
        pending = null;
        running.splice(0).forEach((r) => r.removeAttribute('data-run'));
        save(); stop(true);
      }
    };
    es.onerror = () => { /* EventSource retries; the durable feed replays on reconnect */ };
  }


  /* ---- WATCH A RUN THAT DID NOT START HERE --------------------------------
   * J, 2026-08-30: "when i click run now on a card how do i know whats going on
   * or what the orch or agents are doing".
   *
   * He could not. fireCard() got an ask id and a stream token back from the
   * server and put the id in a TOOLTIP -- while this file already had a live
   * tool-timeline renderer for exactly that stream. Both halves existed and
   * nothing joined them.
   *
   * adopt() is that join: it opens a turn in the console with the card's title,
   * attaches the same EventSource the chat uses, and from there a fired card is
   * watched exactly like something typed. */
  function adopt(askId, streamToken, label, model) {
    if (!askId || !streamToken) return false;
    const me = push('me', label || 'Running an action card');
    const b = document.getElementById('b-' + me.id);
    if (b) b.innerHTML = '<span class="turn__card">card fired</span> ' + esc(label || '');
    /* Name the RUN, not the picker: a card fires on the card's own model, which is
       routinely sonnet while the console picker sits on opus. */
    const turn = push('gamma', '', { name: 'Card run', model: model || 'sonnet', kind: 'card' });
    step(turn.id, 'picked up the card — watching it run', 'dim');
    busy(true);
    st.askId = askId;
    setWho({ name: 'Card run', model: model || 'sonnet', kind: 'card' });
    openStream(turn, { ask_id: askId, stream_token: streamToken });
    scroll();
    return true;
  }


  /* A one-shot note in the console: the outcome of a run this page did not
     stream. Used when a card was already fired, so "Already ran" has somewhere
     to put the answer. Not a chat turn -- there was no question. */
  function note(title, text, ok) {
    const e = document.getElementById('cempty'); if (e) e.remove();
    const b = body(); if (!b) return;
    const n = el('div'); n.className = 'turn turn--note';
    if (ok === false) n.setAttribute('data-t', 'bad');
    n.innerHTML =
      '<div class="turn__w">' + (ok === false ? 'Ran — failed' : 'Earlier run') + '</div>' +
      '<div class="turn__b"><b class="turn__card">card</b>' + esc(title || '') +
      '<div class="turn__note">' + esc(text || '') + '</div></div>';
    b.appendChild(n);
    scroll();
  }

  function stop(natural) {
    if (st.es) { try { st.es.close(); } catch (_) { /* already closed */ } st.es = null; }
    if (!natural && st.askId) {
      const tok = (document.querySelector('meta[name="gamma-token"]') || {}).content || '';
      fetch('/api/cancel-task', {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'x-gamma-token': tok },
        body: JSON.stringify({ id: st.askId }),
      }).catch(() => { /* the stream is already closed; the run will time out on its own */ });
      const t = st.turns[st.turns.length - 1];
      if (t) step(t.id, 'stopped by you', 'bad');
    }
    st.askId = null;
    busy(false);
  }

  /* ---- the view ------------------------------------------------------------ */
  /* panel() returns just the console; view() wraps it in a page of its own.
     J: "orchestrator doesnt need to be its own page it can be a chat on the same
     page as the agents" -- so the Desk embeds panel() beside the agent graph, and
     the standalone route stays only as a direct link. */
  function panel() {
    const c = el('div'); c.className = 'chat';
    c.innerHTML =
      '<div class="chat__bar">' +
        '<span class="chat__spark">' + spark() + '</span>' +
        '<h3>Gamma</h3>' +
        '<select class="msel" id="cmodel" aria-label="Model">' +
          ['opus', 'sonnet', 'haiku'].map((m) =>
            '<option value="' + m + '"' + (m === st.model ? ' selected' : '') + '>' + m + '</option>').join('') +
        '</select>' +
        '<span class="pill" id="cstate"><i class="pill__dot"></i><span>ready</span></span>' +
      '</div>' +
      '<div class="chat__body" id="cbody"></div>' +
      '<div class="chat__foot">' +
        '<textarea class="chat__in" id="cin" rows="1" ' +
          'placeholder="Ask anything, or tell it what to build…"></textarea>' +
        '<button class="chat__send" id="csend" type="button" aria-label="Send">' + SEND + '</button>' +
        '<button class="chat__send chat__stop" id="cstop" type="button" hidden ' +
          'aria-label="Stop">' + STOPI + '</button>' +
      '</div>' +
      '<div class="chat__hint">' +
        '<span><kbd>Enter</kbd> send</span><span><kbd>Shift</kbd>+<kbd>Enter</kbd> newline</span>' +
        '<span><kbd>Esc</kbd> stop</span>' +
        '<span class="chat__hint-r">Runs in <span class="mono">C:\\Users\\jackw\\Desktop\\42</span> ' +
        'with your hooks enforcing the rules</span>' +
      '</div>';
    const b = c.querySelector('#cbody');
    if (st.turns.length) {
      st.turns.forEach((t) => {
        const n = el('div'); n.className = 'turn turn--' + t.role;
        n.innerHTML = '<div class="turn__w">' + (t.role === 'me' ? 'You' : 'Gamma') + '</div>' +
          '<div class="turn__b md"></div>';
        const bb = n.querySelector('.turn__b');
        if (t.role === 'me') bb.textContent = t.text; else bb.innerHTML = G.md.render(t.text);
        b.appendChild(n);
      });
      const mark = el('div', 'restored · the same session continues');
      mark.className = 'tl__r'; mark.setAttribute('data-k', 'dim');
      mark.style.justifyContent = 'center';
      b.appendChild(mark);
    } else {
      b.appendChild(emptyState());
    }

    const i = c.querySelector('#cin');
    i.oninput = () => { i.style.height = 'auto'; i.style.height = Math.min(190, i.scrollHeight) + 'px'; };
    i.onkeydown = (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
      else if (e.key === 'Escape' && st.busy) { e.preventDefault(); stop(false); }
    };
    c.querySelector('#csend').onclick = () => send();
    c.querySelector('#cstop').onclick = () => stop(false);
    c.querySelector('#cmodel').onchange = (e) => {
      st.model = e.target.value;
      /* A resumed session belongs to the model it began on; silently continuing it
         on another would be a lie about continuity. */
      st.session = null; save();
      const t = st.turns[st.turns.length - 1];
      if (t) step(t.id, 'model → ' + st.model + ' (new session)', 'dim');
    };
    b.addEventListener('wheel', () => {
      st.pinned = (b.scrollHeight - b.scrollTop - b.clientHeight) < 34;
    }, { passive: true });
    setTimeout(() => { const x = document.getElementById('cin'); if (x) x.focus(); }, 60);
    return c;
  }

  function view() {
    const s = G.views.page('The <b>orchestrator</b>',
      'A real Claude Code session, running in this repo with the full tool set. It ' +
      'remembers the conversation across reloads, and everything it touches is listed ' +
      'as it happens.');
    s.appendChild(panel());
    return s;
  }

  function emptyState() {
    const e = el('div'); e.id = 'cempty'; e.className = 'chat__empty';
    e.innerHTML = '<div class="g">' + spark() + '</div>' +
      '<h4>What are we doing?</h4>' +
      '<p>Full Claude Code, in this repo. It can read anything, run checks, edit files ' +
      'and spawn its own agents — with your hooks enforcing the rules.</p>' +
      '<div class="chips"></div>';
    const chips = e.querySelector('.chips');
    [['What changed while I was away?', 'catch me up'],
     ['How did the desk do this week, honestly?', 'the numbers'],
     ['What is the single most broken thing right now?', 'triage'],
     ['Show me what the engine did at the open today.', 'the tape']]
      .forEach(([q]) => {
        const b = document.createElement('button');
        b.className = 'chip'; b.type = 'button'; b.textContent = q;
        b.onclick = () => send(q);
        chips.appendChild(b);
      });
    return e;
  }

  /* ESC STOPS A RUN FROM ANYWHERE ON THE PAGE.
     It was bound to the textarea's own onkeydown, so it only worked while the
     input had focus -- yet the hint bar promises "Esc stop" unconditionally.
     Click a card, a lane, the calendar, then try to abort a long run and nothing
     happened. Found by driving the page rather than reading it.

     A modal wins: if the P&L sheet or the command palette is open, Escape belongs
     to whichever of those is on top, and the run keeps going. Closing the sheet
     you opened must never also kill the work you were watching. */
  addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' || !st.busy) return;
    if (document.querySelector('.gsheet') || document.querySelector('.pal')) return;
    const a = document.activeElement;
    if (a && a.id === 'cin') return;      // the input's own handler already has it
    e.preventDefault();
    stop(false);
  });

  G.chat = { view, panel, send, stop, adopt, note };
})(window.G = window.G || {});
