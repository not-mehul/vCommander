// Add a wired output on the panel: Alarms → site → Devices → Configure →
// Configure wired device to panel → type (an Output), pin (the given one) →
// Next → Generic Output → name → through the wizard. Steps are printed.
// Args: site ("HQ"), name ("Web Strobe"), index of the free pin to take
// ("0"), kind ("Output" or "Input").
module.exports = async (s, ui, site = 'HQ', name = 'Web Strobe', pinIdx = '0', kind = 'Output') => {
  await ui.go(s, '/new-alarms');
  await ui.click(s.page, 'Search', { wait: 3000 });
  await ui.click(s.page, site, { wait: 6000 });
  await ui.click(s.page, 'Devices', { wait: 5000 });
  await ui.click(s.page, 'Configure', { wait: 1500 });
  await ui.click(s.page, 'Configure wired device to panel', { wait: 5000 });
  const choose = async (field, pickFn) => {
    await s.page.getByRole('button', { name: `Open menu of options for ${field}` }).click();
    await s.page.waitForTimeout(1500);
    const items = s.page.getByRole('menuitem').or(s.page.getByRole('option'));
    const texts = await items.allInnerTexts();
    console.log(`${field}:`, texts.map(t => t.replace(/\s+/g, ' ')).join(' | ').slice(0, 400));
    await items.nth(pickFn(texts)).click();
    await s.page.waitForTimeout(1500);
  };
  await choose('Choose type', t => Math.max(0, t.findIndex(x => new RegExp(kind, 'i').test(x))));
  await choose('Choose Pin', () => +pinIdx);
  ui.mark(s, `alarm.wired_${kind.toLowerCase()} ${name}`);
  for (let step = 0; step < 5; step++) {
    const generic = s.page.getByText(`Generic ${kind}`, { exact: true }).or(s.page.getByText(/^(Door Contact|Motion Sensor|Generic Input)$/)).first();
    if (await generic.count() && await generic.first().isVisible()) { await generic.first().click(); await s.page.waitForTimeout(2500); }
    const nm = s.page.getByRole('textbox', { name: /name/i });
    if (await nm.count() && await nm.first().isVisible()) await nm.first().fill(name);
    console.log(`step ${step}:`, (await ui.tree(s, { root: 'main', lines: 200 })).split('\n').filter(l => /heading|textbox|button "(Next|Save|Add|Done|Create|Generic)/.test(l)).join(' | ').slice(0, 500));
    let clicked = false;
    for (const b of ['Next', 'Create Device', 'Save', 'Add', 'Create', 'Done']) { try { await ui.clickLast(s.page, b, { wait: 3500 }); clicked = true; break; } catch {} }
    if (!clicked) break;
  }
};
