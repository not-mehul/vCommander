// Run a recorded web action: tools/live/web/actions/<action>.js exports
// async (s, ui, ...args). The recording goes to $LIVE_OUT/<action>[-tag].web.json
// and a screenshot of the end state to <action>.png.
// CHANGES THE ORG for every action that creates or deletes something.
// Usage: NODE_PATH=$(npm root -g) node tools/live/web/run.js <action> [args...]
// Env: TAG=<suffix> to keep several recordings of one action.
const { open } = require('./session');
const ui = require('./ui');
(async () => {
  const [action, ...args] = process.argv.slice(2);
  const fn = require(`./actions/${action}`);
  const name = action + (process.env.TAG ? `-${process.env.TAG}` : '');
  const s = await open();
  let code = 0;
  try {
    await fn(s, ui, ...args);
  } catch (e) {
    code = 1;
    console.log('FAILED:', s.red(e.message.split('\n').slice(0, 6).join(' | ')));
  } finally {
    await ui.shot(s, name).catch(() => {});
    console.log('recording:', s.save(`${name}.web.json`).replace(s.OUT, '$LIVE_OUT'));
    // Print the likely writes made after the first mark (reads filtered out).
    const first = s.log.findIndex(x => x.method === 'MARK');
    const READ = /log|heartbeat|init|metrics|track|search|list|validate|check_auth|retrieve_keys|get|status|permissions|history|entities|fetch|query|count|summary/i;
    for (const x of first < 0 ? [] : s.log.slice(first)) {
      if (x.method === 'MARK') console.log('  --', x.path);
      else if (!['GET', 'OPTIONS'].includes(x.method) && !READ.test(x.path.replace(/\?.*/, ''))) console.log('  ', x.method, x.host.split('.')[0], x.path.replace(/^\/__v\/[^/]+\//, ''), x.status, x.body.slice(0, 300));
    }
    await s.browser.close();
    process.exit(code);
  }
})();
