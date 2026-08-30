/* md.js — a small, deliberately incomplete markdown renderer for agent replies.
 *
 * WHY NOT A LIBRARY: every markdown library worth using arrives over a CDN, which
 * this repo forbids. Vendoring one is thousands of lines to review for a page that
 * renders one author's output.
 *
 * SECURITY POSTURE: the input is a model's reply, which can contain anything a user
 * pasted into the conversation. So the ONLY safe order is escape-then-format:
 * everything is HTML-escaped first, and formatting is applied to the escaped text
 * afterwards. No raw HTML from the source ever reaches innerHTML, and no rule here
 * emits an attribute whose value comes from the input except href, which is
 * scheme-checked. Do not "improve" this by allowing inline HTML through. */
(function (G) {
  'use strict';

  const esc = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

  /* Only http(s) links survive. javascript:, data: and friends are dropped to
     plain text — a model reply is untrusted input. */
  function link(href, text) {
    if (!/^https?:\/\//i.test(href)) return esc(text);
    return '<a href="' + esc(href) + '" target="_blank" rel="noopener noreferrer">' +
      esc(text) + '</a>';
  }

  function inline(t) {
    // t is ALREADY escaped here.
    return t
      .replace(/`([^`\n]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<em>$2</em>')
      .replace(/\[([^\]\n]+)\]\(([^)\s]+)\)/g, (m, txt, href) => {
        // txt/href arrive escaped; unescape only for the scheme test.
        const raw = href.replace(/&amp;/g, '&');
        return /^https?:\/\//i.test(raw)
          ? '<a href="' + href + '" target="_blank" rel="noopener noreferrer">' + txt + '</a>'
          : m;
      });
  }

  function render(src) {
    const lines = String(src == null ? '' : src).split('\n');
    let out = '', inCode = false, lang = '', buf = [], list = null;

    const closeList = () => { if (list) { out += '</' + list + '>'; list = null; } };

    for (let i = 0; i < lines.length; i++) {
      const ln = lines[i];
      const fence = ln.match(/^\s*```(\w+)?\s*$/);
      if (fence) {
        if (inCode) {
          out += '<pre class="cb"' + (lang ? ' data-l="' + esc(lang) + '"' : '') + '><code>' +
            esc(buf.join('\n')) + '</code></pre>';
          inCode = false; buf = []; lang = '';
        } else {
          closeList(); inCode = true; lang = fence[1] || '';
        }
        continue;
      }
      if (inCode) { buf.push(ln); continue; }

      if (!ln.trim()) { closeList(); continue; }

      const h = ln.match(/^(#{1,4})\s+(.*)$/);
      if (h) {
        closeList();
        const lvl = Math.min(6, h[1].length + 2);
        out += '<h' + lvl + '>' + inline(esc(h[2])) + '</h' + lvl + '>';
        continue;
      }
      const ul = ln.match(/^\s*[-*+]\s+(.*)$/);
      const ol = ln.match(/^\s*\d+[.)]\s+(.*)$/);
      if (ul || ol) {
        const want = ul ? 'ul' : 'ol';
        if (list !== want) { closeList(); out += '<' + want + '>'; list = want; }
        out += '<li>' + inline(esc((ul || ol)[1])) + '</li>';
        continue;
      }
      if (/^\s*>\s?/.test(ln)) {
        closeList();
        out += '<blockquote>' + inline(esc(ln.replace(/^\s*>\s?/, ''))) + '</blockquote>';
        continue;
      }
      if (/^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/.test(ln)) { closeList(); out += '<hr>'; continue; }

      closeList();
      out += '<p>' + inline(esc(ln)) + '</p>';
    }
    // An unterminated fence still has to render — the stream may be mid-block.
    if (inCode && buf.length) {
      out += '<pre class="cb"' + (lang ? ' data-l="' + esc(lang) + '"' : '') + '><code>' +
        esc(buf.join('\n')) + '</code></pre>';
    }
    closeList();
    return out;
  }

  G.md = { render, esc, link };
})(window.G = window.G || {});
