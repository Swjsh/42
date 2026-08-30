/* palette.js — Ctrl/Cmd-K. The keyboard route to everywhere, because a daily
 * driver that needs the mouse to change screens is a website, not a tool.
 *
 * It carries two kinds of entry:
 *   · GO — switch view. Instant, no side effects.
 *   · ASK — put a question to the console. These do NOT fire on selection; they
 *     land in the composer for J to edit and send. A palette entry that silently
 *     starts a Claude run on the shared Max pool is a footgun, and one keystroke
 *     away from being pressed by accident. */
(function (G) {
  'use strict';

  const ITEMS = [
    { k: 'go', label: 'Home', hint: 'hero', to: '#/' },
    { k: 'go', label: 'Total profit — the calendar', hint: 'profit', to: '#/profit' },
    { k: 'go', label: 'The desk', hint: 'desk', to: '#/desk' },
    { k: 'go', label: 'P&L by session — every arm, every day', hint: 'pnl', to: '#/pnl' },
    { k: 'go', label: 'Needs a decision — action cards', hint: 'cards', to: '#/cards' },
    { k: 'go', label: 'The orchestrator', hint: 'console', to: '#/chat' },
    { k: 'go', label: 'Sign in', hint: 'auth', to: '#/signin' },
    { k: 'ask', label: 'What changed while I was away?' },
    { k: 'ask', label: 'How did the desk do this week, honestly?' },
    { k: 'ask', label: 'What is the single most broken thing right now?' },
    { k: 'ask', label: 'Is anything blocking the September scoring window?' },
    { k: 'ask', label: 'Show me every rule break in the last ten trading days.' },
    { k: 'ask', label: 'What did the engine do at the open today?' },
  ];

  let open = false, sel = 0, shown = ITEMS.slice();

  function score(item, q) {
    if (!q) return 1;
    const l = item.label.toLowerCase();
    if (l.startsWith(q)) return 3;
    if (l.includes(q)) return 2;
    // subsequence: "tp" should still find "Total profit"
    let i = 0;
    for (const c of l) { if (c === q[i]) i++; if (i === q.length) return 1; }
    return 0;
  }

  function paint(root, q) {
    const list = root.querySelector('.pal__list');
    shown = ITEMS.map((it) => [it, score(it, q)]).filter((p) => p[1] > 0)
      .sort((a, b) => b[1] - a[1]).map((p) => p[0]);
    if (sel >= shown.length) sel = Math.max(0, shown.length - 1);
    if (!shown.length) { list.innerHTML = '<div class="pal__none">Nothing matches that.</div>'; return; }
    list.innerHTML = shown.map((it, i) =>
      '<button class="pal__i" type="button" role="option" data-i="' + i + '"' +
      (i === sel ? ' aria-selected="true"' : '') + '>' +
      (it.k === 'go' ? '→ ' : '? ') + G.md.esc(it.label) +
      '<small>' + (it.k === 'go' ? G.md.esc(it.hint) : 'ask') + '</small></button>').join('');
    [...list.querySelectorAll('.pal__i')].forEach((b) => {
      b.onmouseenter = () => { sel = +b.dataset.i; paint(root, q); };
      b.onclick = () => choose(root, shown[+b.dataset.i]);
    });
    const cur = list.querySelector('[aria-selected="true"]');
    if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: 'nearest' });
  }

  function choose(root, item) {
    if (!item) return;
    close(root);
    if (item.k === 'go') { location.hash = item.to; return; }
    /* Deliberately does NOT send. It loads the composer so the question can be
       edited first -- one keystroke should never start a run on its own. */
    location.hash = '#/chat';
    setTimeout(() => {
      const i = document.getElementById('cin');
      if (i) { i.value = item.label; i.focus(); i.dispatchEvent(new Event('input')); }
    }, 220);
  }

  function close(root) { open = false; if (root && root.parentNode) root.remove(); }

  function show() {
    if (open) return;
    open = true; sel = 0;
    const root = document.createElement('div');
    root.className = 'pal'; root.setAttribute('role', 'dialog'); root.setAttribute('aria-modal', 'true');
    root.innerHTML = '<div class="pal__box"><input class="pal__in" id="palin" ' +
      'placeholder="Go somewhere, or ask the orchestrator…" aria-label="Command palette">' +
      '<div class="pal__list" role="listbox"></div></div>';
    document.body.appendChild(root);
    paint(root, '');
    const inp = root.querySelector('#palin');
    inp.focus();
    inp.oninput = () => { sel = 0; paint(root, inp.value.trim().toLowerCase()); };
    inp.onkeydown = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); close(root); }
      else if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(shown.length - 1, sel + 1); paint(root, inp.value.trim().toLowerCase()); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(0, sel - 1); paint(root, inp.value.trim().toLowerCase()); }
      else if (e.key === 'Enter') { e.preventDefault(); choose(root, shown[sel]); }
    };
    root.onclick = (e) => { if (e.target === root) close(root); };
  }

  addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      const cur = document.querySelector('.pal');
      if (cur) close(cur); else show();
      return;
    }
    /* Escape at the WINDOW, not only on the input. The input's own handler covers
       the normal case (it has focus on open), but the moment focus moved anywhere
       else the palette became uncloseable by keyboard -- found by driving it with
       focus on the body. The P&L sheet already listens at this level; this makes
       the two modal surfaces behave the same way. */
    if (e.key === 'Escape') {
      const cur = document.querySelector('.pal');
      if (cur) { e.preventDefault(); close(cur); }
    }
  });

  G.palette = { show };
})(window.G = window.G || {});
