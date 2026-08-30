/* humanize.js — every event on the glass becomes a plain-English sentence.
 *
 * J (2026-08-30, after a day of asking): "everything needs to be human readable,
 * intuitive, layman's terms, broken down, so it's easy to see at a glance."
 *
 * The activity feed was piping raw `git log` subjects, guard codes and scheduler
 * notes straight onto the page — "fix(quiet-mode): the weekend was a 30-hour…",
 * "ROSTER-LIVENESS: 1 lane(s) permanently DEAD (404/archived)". Nobody's product
 * does that. The W3C Activity Streams model (dossier R2) is the law here: every
 * line is ACTOR + VERB + OBJECT + relative time, GENERATED from the event by
 * construction rules — never the raw record. The raw record survives in the
 * row's title attribute, one hover away; the glass gets the sentence.
 *
 * Pure functions, no DOM, no fetch. Renderers esc() the output — nothing here
 * is trusted as HTML. */
(function (G) {
  'use strict';

  /* Strip the machine out of a sentence: absolute paths, long hashes, backtick
     quoting. Filenames survive as their bare stem ("quiet_mode.py" → "quiet mode")
     when they ARE the object of the sentence. */
  function scrub(s) {
    return String(s || '')
      // windows + posix absolute paths → gone (the hover title keeps them)
      .replace(/[A-Za-z]:\\[^\s,;)]+/g, '')
      .replace(/(?:^|\s)\/[\w./-]{6,}/g, ' ')
      // repo-relative paths: keep only the file stem, de-snaked
      .replace(/(?:[\w-]+\/)+([\w-]+)\.\w{1,5}/g, function (_, stem) {
        return stem.replace(/[_-]+/g, ' ');
      })
      // `code ticks` → bare words
      .replace(/`([^`]+)`/g, '$1')
      // commit-hash noise
      .replace(/\b[0-9a-f]{7,40}\b/g, '')
      .replace(/\s{2,}/g, ' ')
      .replace(/\s+([,.;:])/g, '$1')
      .trim();
  }

  function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

  /* Gamma_SelfCheck → "Self check". The scheduler's names are camel-cased code;
     the glass speaks English. */
  function deCode(name) {
    return cap(String(name || '')
      .replace(/^Gamma[_-]?/i, '')
      .replace(/[_-]+/g, ' ')
      .replace(/([a-z])([A-Z])/g, '$1 $2')
      .toLowerCase()
      .trim());
  }

  /* ---- commits: "fix(quiet-mode): the weekend was…" → verb chip + sentence ---- */
  var VERB = {
    feat: 'built', fix: 'fixed', docs: 'wrote up', chore: 'tidied',
    refactor: 'reworked', test: 'added guards', perf: 'sped up',
    ci: 'wired up', style: 'polished', revert: 'rolled back',
  };
  function commit(subject) {
    var raw = String(subject || '');
    var m = /^(\w+)(?:\(([^)]*)\))?!?:\s*(.+)$/.exec(raw);
    // `|| raw` was the leak: when scrub() emptied a subject that was nothing BUT a
    // path, the unscrubbed original went straight to the glass. Fall back to a
    // generic label instead -- the raw text still lives in the row's title.
    if (!m) return { verb: 'shipped', text: cap(scrub(raw)) || 'a change', raw: raw };
    var verb = VERB[m[1].toLowerCase()] || 'shipped';
    var scope = (m[2] || '').replace(/[_-]+/g, ' ').trim();
    var text = cap(scrub(m[3]));
    // The scope only earns a place when it adds meaning the sentence lacks.
    if (scope && text.toLowerCase().indexOf(scope.toLowerCase()) === -1) {
      text = text + ' (' + scope + ')';
    }
    return { verb: verb, text: text, raw: raw };
  }

  /* ---- guard codes: "ROSTER-LIVENESS: 1 lane(s) permanently DEAD (…)" ---- */
  function broken(text) {
    var raw = String(text || '');
    // Two shapes reach this, and the first cut only handled one:
    //   "ROSTER-LIVENESS: 1 lane(s) permanently DEAD"          <- code, colon, rest
    //   "EARNINGS-CALENDAR STALE (RED): the file is 53h old"   <- code, WORDS, (sev), colon
    // The second leaked straight onto the decision cards. The severity parenthetical
    // is dropped rather than translated: the row already carries its own tone, and
    // "(RED)" inside a sentence is the machine talking.
    var m = /^([A-Z][A-Z0-9-]{3,})((?:\s+[A-Z][A-Z0-9-]*)*)\s*(?:\((?:RED|YELLOW|GREEN|WARN)\))?\s*:\s*(.*)$/
      .exec(raw);
    if (m) {
      m = [m[0], m[1] + (m[2] || ''), m[3]];
    }
    var name = m ? deCode(m[1]) : '';
    var rest = scrub(m ? m[2] : raw)
      .replace(/\b(\d+)\s*lane\(s\)/gi, '$1 lane')
      .replace(/\bDEAD\b/g, 'dead')
      .replace(/\s*\((?:[^()]*\/[^()]*|[A-Z0-9_]{6,})\)\s*/g, ' ')  // tech parentheticals
      // NOTE: a bare filename is deliberately KEPT. An earlier version replaced it
      // with "that file", which reads more human and is strictly less useful:
      // "earnings-blackout.json is 53h old" tells J what to go look at; "that file
      // is 53h old" tells him nothing. Scrubbing is for machine SYNTAX (codes,
      // paths, hashes), never for the nouns a sentence is actually about.
      .trim();
    var s = name ? name + ' — ' + rest : cap(rest);
    return { text: cap(s), raw: raw };
  }

  /* ---- autonomy-fire notes: the conductor's own log lines ---- */
  var FIRE_RULES = [
    [/budget gate EXHAUSTED/i, 'Skipped its run — the day’s self-run budget was already spent'],
    [/quiet[- ]?mode|quiet window/i, 'Held back — quiet hours were on'],
    [/closed duplicate .*queue/i, 'Cleaned a duplicate task out of the queue'],
    [/root-?caused/i, 'Diagnosed a broken check and shipped the fix'],
    [/new app shipped/i, 'Shipped a new version of this app'],
    [/no (open|pending) (item|task|card)/i, 'Checked in — nothing was waiting'],
  ];
  function fire(note) {
    var raw = String(note || '');
    for (var i = 0; i < FIRE_RULES.length; i++) {
      if (FIRE_RULES[i][0].test(raw)) return { text: FIRE_RULES[i][1], raw: raw };
    }
    // generic: first clause, scrubbed, sentence-cased
    var first = scrub(raw.split(/[;(]|\s--\s/)[0]);
    return { text: cap(first).slice(0, 120) || 'Ran a pass', raw: raw };
  }

  /* ---- scheduled-task rows: "Gamma_SelfCheck — failed" ---- */
  function task(name, status) {
    return { text: deCode(name) + (status ? ' — ' + String(status).toLowerCase() : ''),
             raw: String(name || '') + ' ' + String(status || '') };
  }

  /* ---- live pulses: the real agent↔orchestrator traffic ----
     A row is {ts, event, session_id, agent_id, to, detail}. The sentence is the
     actor + what KIND of thing happened; the raw detail (often a full command
     line) is hover-only. */
  function pulse(row, actorName) {
    var d = String((row && row.detail) || '');
    var ev = String((row && row.event) || '');
    var who = actorName || 'an agent';
    var did;
    if (/^ran:?\s/i.test(d)) did = 'ran a check';
    else if (/^read/i.test(d)) did = 'read through the code';
    else if (/^(edit|writ)/i.test(d)) did = 'edited code';
    else if (/^search|^grep|^glob/i.test(d)) did = 'searched the repo';
    else if (ev === 'spawn') did = 'sent out an agent';
    else if (ev === 'done' || ev === 'result') did = 'reported back';
    else if (ev === 'say') did = 'sent a message';
    else did = 'did some work';

    /* A FAILURE MUST NEVER READ AS PROGRESS. The generic fallback above turned a
       real, repeated tool error into "did some work" in the live wire -- the feed
       reassuring J while the agent was stuck in a loop. Failure signatures are
       checked FIRST and win over the verb, and the row is tagged so the renderer
       can tone it. (Found by an adversarial review, 2026-08-30.) */
    if (/\b(error|failed|failure|traceback|exception|denied|refused|timed out|timeout)\b/i.test(d)) {
      return { text: who + ' hit an error', bad: true,
               raw: (ev ? ev + ': ' : '') + d };
    }
    return { text: who + ' ' + did, raw: (ev ? ev + ': ' : '') + d };
  }

  /* "5m" — relative time for feed rows; absolute time is hover detail. */
  function ago(iso) {
    /* The rig writes naive ET stamps ("2026-08-30T14:12:02") with no offset, and
       Date.parse treats those as the VIEWER's local time. This box runs Mountain,
       so every relative age was off by the ET-local delta -- "2h ago" for something
       that just happened. If there is no offset in the string, pin it to ET (-04:00
       EDT / -05:00 EST) rather than letting the browser guess. */
    var raw = String(iso || '');
    if (raw && !/(Z|[+-]\d{2}:?\d{2})$/.test(raw)) {
      var mo = Number(raw.slice(5, 7));
      raw += (mo >= 3 && mo <= 11) ? '-04:00' : '-05:00';
    }
    var t = Date.parse(raw);
    if (!isFinite(t)) return '';
    var m = Math.round((Date.now() - t) / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return m + 'm ago';
    var h = Math.round(m / 60);
    return h < 48 ? h + 'h ago' : Math.round(h / 24) + 'd ago';
  }

  G.human = { commit: commit, broken: broken, fire: fire, task: task,
              pulse: pulse, scrub: scrub, deCode: deCode, ago: ago, cap: cap };
})(window.G = window.G || {});
