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
const SECRETS = [ORG, process.env.VERKADA_EMAIL, ...['Access_Controller','Access_Station_Pro','Alarm_Panel','Bullet','Command_Connector','Dome','Fisheye','Keypad','PTZ'].map(k => process.env[k])].filter(Boolean);
function red(s) {
  for (const v of SECRETS) s = s.split(v).join('<redacted>');
  return s.replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi, '{id}');
}
async function open({ record } = {}) {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addCookies(process.env.COOKIE.split(';').map(p => p.trim()).filter(p => p.includes('='))
    .map(p => ({ name: p.slice(0, p.indexOf('=')), value: p.slice(p.indexOf('=') + 1), domain: '.verkada.com', path: '/', secure: true })));
  // Never let the web app end the session: a logout here revokes the token
  // server-side (it revoked the first session we were given).
  await ctx.route(/logout|sign_?out/i, route => { console.log('BLOCKED', route.request().method(), new URL(route.request().url()).pathname.replace(ORG, '<org>')); route.abort(); });
  await ctx.route(/https:\/\/[a-z0-9.-]+\.verkada\.com\/__v\//, route => {
    if (/logout|sign_?out/i.test(route.request().url())) return route.abort();
    const h = route.request().headers();
    h['x-verkada-organization-id'] ||= process.env.X_VERKADA_ORGANIZATION_ID;
    h['x-verkada-user-id'] ||= process.env.X_VERKADA_USER_ID;
    h['x-verkada-token'] ||= process.env.X_VERKADA_TOKEN;
    route.continue({ headers: h });
  });
  const page = await ctx.newPage();
  const log = [];
  page.on('requestfinished', async q => {
    const u = new URL(q.url());
    if (!u.pathname.startsWith('/__v/') && !u.hostname.startsWith('api.')) return;
    let status = 0, resp = '';
    try { const r = await q.response(); status = r.status(); resp = await r.text(); } catch {}
    log.push({ t: Date.now(), method: q.method(), host: red(u.hostname), path: red(u.pathname + u.search),
               body: red(q.postData() || ''), status, resp: red(resp).slice(0, 4000) });
  });
  page.on('dialog', d => d.dismiss().catch(() => {}));
  const OUT = process.env.LIVE_OUT || require('path').join(require('os').homedir(), '.vcommander-live');
  fs.mkdirSync(OUT, { recursive: true });
  const save = name => { const f = require('path').join(OUT, name); fs.writeFileSync(f, JSON.stringify(log, null, 1)); return f; };
  return { browser, ctx, page, log, save, red, ORG, OUT };
}
module.exports = { open };
