// A headless Command session from the COOKIE env var, plus a redacted
// recorder of every Verkada API request (method, host, path, payload).
//
// - The web app's login flow normally supplies the x-verkada-organization-id
//   and x-verkada-user-id headers; a cookie-only session doesn't have them, so
//   they are added from X_VERKADA_* when missing (without them
//   feature_flags/init answers 401 and the app logs out).
// - Logout requests are always aborted: a logout from here revokes the token
//   server-side, ending the session the cookies came from.
const { chromium } = require('playwright');
const fs = require('fs');
const ORG = process.env.VERKADA_ORG;
const SECRETS = [ORG, process.env.VERKADA_EMAIL, ...['Access_Controller','Access_Controller2','Access_Station_Pro','Alarm_Panel','Bullet','Command_Connector','Dome','Dome2','Fisheye','Keypad','PTZ'].map(k => process.env[k])].filter(Boolean);
// A secret as a case-insensitive pattern; serials also match with or
// without dashes ("ABCD-EFGH" == "ABCDEFGH"), as Command shows them dashed.
function secretRx(v) {
  const plain = v.replace(/-/g, '');
  return new RegExp(plain.split('').map(c => c.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('-?'), 'gi');
}
// Blank credential values (API key secrets, tokens) in JSON bodies.
const SECRET_KEY = /(api_?key|secret|token|password|cookie)(?!.*(name|id|expir))/i;
function scrub(v) {
  if (Array.isArray(v)) return v.map(scrub);
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, SECRET_KEY.test(k) && typeof x === 'string' ? '<secret>' : scrub(x)]));
  return v;
}
function red(s) {
  try { s = JSON.stringify(scrub(JSON.parse(s))); } catch {}
  for (const v of SECRETS) s = s.replace(secretRx(v), '<redacted>');
  return s.replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi, '{id}');
}
async function open({ record } = {}) {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addCookies(process.env.COOKIE.split(';').map(p => p.trim()).filter(p => p.includes('='))
    .map(p => ({ name: p.slice(0, p.indexOf('=')), value: p.slice(p.indexOf('=') + 1), domain: '.verkada.com', path: '/', secure: true })));
  // Never let the web app end the session: a logout here revokes the token
  // server-side (it revoked the first session we were given).
  const log = [];
  const block = route => {
    const q = route.request(), u = new URL(q.url());
    console.log('BLOCKED', q.method(), red(u.pathname));
    log.push({ t: Date.now(), t0: started.get(q), method: q.method(), host: red(u.hostname), path: red(u.pathname), body: '', status: 'blocked', resp: '' });
    return route.abort();
  };
  await ctx.route(/logout|sign_?out/i, block);
  await ctx.route(/https:\/\/[a-z0-9.-]+\.verkada\.com\/__v\//, route => {
    if (/logout|sign_?out/i.test(route.request().url())) return block(route);
    const h = route.request().headers();
    h['x-verkada-organization-id'] ||= process.env.X_VERKADA_ORGANIZATION_ID;
    h['x-verkada-user-id'] ||= process.env.X_VERKADA_USER_ID;
    h['x-verkada-token'] ||= process.env.X_VERKADA_TOKEN;
    route.continue({ headers: h });
  });
  const page = await ctx.newPage();
  // Start time of each request, to tell parallel calls from sequential ones.
  const started = new WeakMap();
  page.on('request', q => started.set(q, Date.now()));
  page.on('requestfinished', async q => {
    const u = new URL(q.url());
    if (!u.pathname.startsWith('/__v/') && !u.hostname.startsWith('api.')) return;
    let status = 0, resp = '';
    try { const r = await q.response(); status = r.status(); resp = await r.text(); } catch {}
    log.push({ t: Date.now(), t0: started.get(q), method: q.method(), host: red(u.hostname), path: red(u.pathname + u.search),
               body: red(q.postData() || ''), status, resp: red(resp).slice(0, 4000) });
  });
  page.on('dialog', d => d.dismiss().catch(() => {}));
  const OUT = process.env.LIVE_OUT || require('path').join(require('os').homedir(), '.vcommander-live');
  fs.mkdirSync(OUT, { recursive: true });
  const save = name => { const f = require('path').join(OUT, name); fs.writeFileSync(f, JSON.stringify(log, null, 1)); return f; };
  return { browser, ctx, page, log, save, red, ORG, OUT };
}
module.exports = { open, red };
