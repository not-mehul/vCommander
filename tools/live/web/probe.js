// Open Command's home page and report failed or logout calls; saves a
// screenshot and the recording to $LIVE_OUT. Read-only.
// Usage: NODE_PATH=$(npm root -g) node tools/live/web/probe.js
const path = require('path');
const { open } = require('./session');
(async () => {
  const s = await open();
  await s.page.goto(`https://${s.ORG}.command.verkada.com/`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await s.page.waitForTimeout(15000);
  console.log('url:', s.red(s.page.url()));
  const bad = s.log.filter(x => x.status >= 400);
  console.log(s.log.length, 'API calls,', bad.length, 'failed:', bad.map(x => `${x.method} ${x.path} ${x.status}`).slice(0, 10));
  console.log('recording:', s.save('probe.json'));
  await s.page.screenshot({ path: path.join(process.env.LIVE_OUT || path.join(require('os').homedir(), '.vcommander-live'), 'probe.png') });
  await s.browser.close();
})();
