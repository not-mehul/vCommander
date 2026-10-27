// Read-only: open a Command page, optionally click through elements that only
// open menus, panels or dialogs (never a submit), then print the aria tree
// and save a screenshot, to discover selectors for action scripts.
// Usage: NODE_PATH=$(npm root -g) node tools/live/web/explore.js /admin [shot-name] [CLICK...]
// A CLICK of the form /regex/ matches names by pattern.
const { open } = require('./session');
const { go, click, tree, shot } = require('./ui');
(async () => {
  const [route = '/', name = 'explore', ...clicks] = process.argv.slice(2);
  const s = await open();
  try {
    await go(s, route);
    for (const c of clicks) {
      const m = c.match(/^\/(.*)\/$/);
      await click(s.page, m ? new RegExp(m[1], 'i') : c, { wait: 4000 }).catch(e => console.log('click failed:', e.message));
    }
    console.log('url:', s.red(s.page.url()));
    console.log(await tree(s, { root: process.env.ROOT || 'body' }));
    await shot(s, name);
    s.save(`${name}.json`);
  } finally {
    await s.browser.close();
  }
})();
