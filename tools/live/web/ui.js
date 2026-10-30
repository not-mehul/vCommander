// UI helpers for action scripts: navigate, close Command's pop-ups, click
// and fill by accessible role/name, and print the aria tree (redacted).
const path = require('path');

const base = s => `https://${s.ORG}.command.verkada.com`;

// Close modals that cover the page on first visit (e.g. "Enable local access
// for faster video"). Only the dialog's close button is used.
async function closeModals(page) {
  for (let i = 0; i < 3; i++) {
    const dlg = page.getByRole('dialog').filter({ hasText: /Enable local access|What's new|Welcome/i });
    if (!(await dlg.count())) return;
    const close = dlg.first().getByRole('button', { name: /close/i });
    if (await close.count()) await close.first().click().catch(() => {});
    else await page.keyboard.press('Escape');
    await page.waitForTimeout(800);
  }
}

async function go(s, route, wait = +(process.env.WAIT || 15000)) {
  await s.page.goto(base(s) + route, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await s.page.waitForTimeout(wait);
  await closeModals(s.page);
}

const ROLES = ['button', 'link', 'menuitem', 'menuitemradio', 'tab', 'option', 'radio', 'checkbox', 'switch', 'combobox'];

// Click the first visible element whose accessible name matches (string =
// exact, RegExp = pattern), trying the common roles, then plain text.
async function click(page, name, { within = page, timeout = 10000, wait = 1500 } = {}) {
  const exact = typeof name === 'string';
  const cands = ROLES.map(r => within.getByRole(r, { name, exact })).concat([within.getByText(name, { exact })]);
  for (const l of cands) {
    const n = await l.count();
    for (let i = 0; i < n; i++) {
      const el = l.nth(i);
      if (await el.isVisible().catch(() => false)) {
        await el.click({ timeout });
        await page.waitForTimeout(wait);
        return el;
      }
    }
  }
  throw new Error(`click: nothing visible named ${name}`);
}

async function fill(page, label, value, { within = page } = {}) {
  const cands = [within.getByRole('textbox', { name: label }), within.getByLabel(label), within.getByPlaceholder(label)];
  for (const l of cands) {
    if (await l.count() && await l.first().isVisible().catch(() => false)) {
      await l.first().fill(value);
      return;
    }
  }
  throw new Error(`fill: no field ${label}`);
}

// Redacted aria tree without decorative nodes.
async function tree(s, { root = 'body', lines = +(process.env.LINES || 250) } = {}) {
  const snap = await s.page.locator(root).first().ariaSnapshot().catch(e => `(no ${root}: ${e.message})`);
  return s.red(snap).split('\n').filter(l => !/^\s*- (img|text|generic)\b/.test(l)).slice(0, lines).join('\n');
}

async function shot(s, name) {
  await s.page.screenshot({ path: path.join(s.OUT, `${name}.png`) });
}

// Mark the start of a step in the recording (a synthetic entry, status
// 'mark'), so per-action diffs can slice the log.
function mark(s, label) {
  s.log.push({ t: Date.now(), method: 'MARK', host: '', path: label, body: '', status: 'mark', resp: '' });
  console.log('--', label);
}

module.exports = { base, go, closeModals, click, fill, tree, shot, mark };

// Confirm a "type the verification code" dialog (device decommission/delete):
// read the code shown in the dialog, type it, and press the confirm button.
// Two widgets exist: a hidden "Verification code" input behind one box per
// digit (access controllers), and one "Verification Code Input N" textbox per
// digit (cameras).
async function confirmCode(page, { button = 'Confirm', wait = 6000 } = {}) {
  const input = page.locator('input[aria-label^="Verification code" i]').first();
  const code = await input.evaluate(el => {
    for (let n = el.parentElement; n; n = n.parentElement) {
      const m = n.innerText.replace(/\s+/g, '').match(/(\d{6})/);
      if (m) return m[1];
    }
    return null;
  });
  if (!code) throw new Error('confirmCode: no code found');
  const boxes = page.locator('.CharArrayInput .char');
  const perDigit = !(await boxes.count());
  await (perDigit ? input : boxes.first()).click();
  await page.keyboard.type(code, { delay: 80 });
  await page.waitForTimeout(500);
  const typed = perDigit
    ? (await page.locator('input[aria-label^="Verification Code Input"]').evaluateAll(els => els.map(e => e.value))).join('')
    : (await boxes.allInnerTexts()).join('');
  if (typed !== code) throw new Error('confirmCode: code not entered');
  await clickLast(page, button, { wait });
}

// Click the last visible, enabled button showing that text: a modal is
// rendered after the page, which may have a button of the same text behind
// it. Matched by text, since some modal buttons carry a different aria-label
// (camera delete: "Delete selected devices").
async function clickLast(page, text, { wait = 3000 } = {}) {
  const btns = page.locator('button').filter({ hasText: new RegExp(`^\\s*${text}\\s*$`) });
  for (let i = (await btns.count()) - 1; i >= 0; i--) {
    const b = btns.nth(i);
    if (await b.isVisible() && await b.isEnabled()) {
      // Some modal buttons never count as "stable" (a running transition).
      await b.click({ timeout: 5000 }).catch(() => b.click({ force: true }));
      await page.waitForTimeout(wait);
      return b;
    }
  }
  throw new Error(`clickLast: no enabled button ${text}`);
}

module.exports.confirmCode = confirmCode;
module.exports.clickLast = clickLast;

// Confirm whatever confirmation follows a destructive click: a verification
// code dialog, or a plain one (last visible button named like `buttons`).
async function confirm(page, buttons = ['Delete', 'Confirm', 'Remove', 'Decommission', 'Yes']) {
  // 'Type "HQ" to confirm' dialogs (alarm system delete).
  const typeIt = page.getByText(/^Type ".+" to confirm$/).last();
  if (await typeIt.count()) {
    const word = (await typeIt.innerText()).match(/"(.+)"/)[1];
    await typeIt.locator('xpath=following::input[1]').fill(word);
    await page.waitForTimeout(500);
    for (const b of [...buttons, 'Delete[\\w ]*']) {
      try { return await clickLast(page, b, { wait: 8000 }); } catch {}
    }
    throw new Error('confirm: no confirm button');
  }
  if (await page.locator('input[aria-label^="Verification code" i]').count()) {
    for (const b of buttons) {
      if (await page.locator('button').filter({ hasText: new RegExp(`^\\s*${b}\\s*$`) }).count()) return confirmCode(page, { button: b });
    }
  }
  for (const b of buttons) {
    try { return await clickLast(page, b, { wait: 6000 }); } catch {}
  }
  throw new Error('confirm: no confirm button');
}
module.exports.confirm = confirm;

// Type an address into the focused field and pick the first suggestion
// (Google Places .pac-item, an option, or a custom list entry ending ", USA").
async function pickAddress(page, address) {
  await page.keyboard.type(address, { delay: 40 });
  await page.waitForTimeout(3000);
  const sugg = page.locator('.pac-item').or(page.getByRole('option'))
    .or(page.getByText(new RegExp(`^${address.split(',')[0]}.*USA$`))).first();
  if (await sugg.count()) await sugg.click(); else await page.keyboard.press('Enter');
  await page.waitForTimeout(2500);
}
module.exports.pickAddress = pickAddress;
