/* auth.js — Firebase sign-in, via the REST identity toolkit rather than the SDK.
 *
 * WHY REST AND NOT THE FIREBASE SDK: the SDK ships from gstatic, and this repo
 * forbids CDN imports (the page has to work with no network to anywhere but this
 * box). Firebase's Identity Toolkit is a plain HTTPS JSON API, so email/password
 * and token refresh are ordinary fetches with no dependency at all.
 *
 * WHAT IS DELIBERATELY ABSENT: any credential. The web API key and project id
 * come from the companion at /api/auth-config, which reads a GITIGNORED file.
 * Until that file exists this module reports notConfigured() and the sign-in view
 * says so plainly — a login box that accepts anything and lets you in is worse
 * than no login box, and this repo is public.
 *
 * MULTI-USER LATER: J wants friends on this eventually, with an admin portal and
 * per-user broker connections while the engine keeps running on its own. Nothing
 * here assumes a single user — the ID token is kept per-browser and every future
 * server call is expected to carry it. What does NOT exist yet is any server-side
 * verification of that token, so this is an identity surface, not an authorization
 * boundary. Do not gate anything that matters on it until the companion verifies
 * the token against Google's public keys. */
(function (G) {
  'use strict';

  const IDT = 'https://identitytoolkit.googleapis.com/v1/accounts:';
  const KEY = 'gamma-auth';
  let cfg = null;

  async function config() {
    if (cfg !== null) return cfg;
    try {
      const r = await fetch('/api/auth-config', { cache: 'no-store' });
      const j = await r.json();
      cfg = (j && j.ok && j.apiKey) ? j : false;
    } catch (_) { cfg = false; }
    return cfg;
  }

  function session() {
    try { return JSON.parse(localStorage.getItem(KEY) || 'null'); }
    catch (_) { return null; }
  }
  function setSession(s) {
    try {
      if (s) localStorage.setItem(KEY, JSON.stringify(s));
      else localStorage.removeItem(KEY);
    } catch (_) { /* private window: signed in for this tab only */ }
  }

  /* Errors come back as Google's SCREAMING_SNAKE codes. Showing a user
     "INVALID_LOGIN_CREDENTIALS" is showing them our stack trace. */
  const HUMAN = {
    EMAIL_NOT_FOUND: 'No account with that email.',
    INVALID_PASSWORD: 'That password does not match.',
    INVALID_LOGIN_CREDENTIALS: 'That email and password do not match.',
    USER_DISABLED: 'That account has been disabled.',
    TOO_MANY_ATTEMPTS_TRY_LATER: 'Too many attempts. Wait a minute and try again.',
    INVALID_EMAIL: 'That does not look like an email address.',
    MISSING_PASSWORD: 'Enter your password.',
  };
  const human = (code) => HUMAN[String(code || '').split(' :')[0]] ||
    'Sign-in failed (' + String(code || 'unknown') + ').';

  async function signIn(email, password) {
    const c = await config();
    if (!c) return { ok: false, notConfigured: true };
    try {
      const r = await fetch(IDT + 'signInWithPassword?key=' + encodeURIComponent(c.apiKey), {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ email, password, returnSecureToken: true }),
      });
      const j = await r.json();
      if (!r.ok) return { ok: false, error: human((j.error || {}).message) };
      setSession({
        uid: j.localId, email: j.email, token: j.idToken, refresh: j.refreshToken,
        // expiresIn is SECONDS as a string; storing an absolute ms deadline means
        // a reload can tell a live token from a dead one without a round trip.
        expires: Date.now() + (Number(j.expiresIn || 3600) * 1000),
      });
      return { ok: true, email: j.email };
    } catch (e) {
      return { ok: false, error: 'Could not reach the identity service.' };
    }
  }

  function signOut() { setSession(null); }

  function isSignedIn() {
    const s = session();
    return !!(s && s.token && s.expires > Date.now());
  }

  /* OAuth (Google/GitHub) needs a redirect flow and an authorized domain, which
     only works once the project exists. Reporting that honestly beats opening a
     popup that lands on a Firebase error page. */
  async function oauth(provider) {
    const c = await config();
    if (!c) return { ok: false, notConfigured: true };
    return {
      ok: false,
      error: provider.replace(/^./, (x) => x.toUpperCase()) + ' sign-in needs "' +
        location.host + '" added to Firebase Auth → Settings → Authorized domains, ' +
        'and the ' + provider + ' provider enabled.',
    };
  }

  G.auth = { config, signIn, signOut, isSignedIn, session, oauth };
})(window.G = window.G || {});
