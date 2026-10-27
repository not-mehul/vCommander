// Set up a new camera: Devices → camera → Set Up → Site, Location (first
// address suggestion), analytics switches that are enabled → Apply.
// Args: camera name ("HQ CD62"), site ("HQ"), address.
module.exports = async (s, ui, name = 'HQ CD62', site = 'HQ', address = '406 E 3rd Ave, San Mateo') => {
  await ui.go(s, '/devices');
  await ui.click(s.page, new RegExp(`^${name}\\b`), { wait: 3000 });
  await ui.click(s.page, 'Set Up', { wait: 3000 });
  const dlg = s.page.getByRole('dialog').filter({ has: s.page.getByRole('button', { name: 'Apply' }) });
  await dlg.getByRole('button', { name: 'Open menu of options for Site' }).click();
  await s.page.waitForTimeout(1000);
  // The first match is a greyed group header; the selectable site comes last.
  await s.page.getByRole('menuitem', { name: site, exact: true }).last().click();
  await s.page.waitForTimeout(1500);
  // Location opens a map picker: search the address, take the first Google
  // Places suggestion, Save.
  await dlg.getByRole('textbox', { name: 'Select Location' }).click();
  await s.page.waitForTimeout(3000);
  const picker = s.page.getByRole('dialog', { name: 'Select Location' });
  const search = picker.locator('input[type=text], input:not([type])').first();
  if (await search.count()) {
    await search.click();
    await s.page.keyboard.type(address, { delay: 40 });
    await s.page.waitForTimeout(3000);
    const sugg = s.page.locator('.pac-item').first();
    if (await sugg.count()) await sugg.click(); else await s.page.keyboard.press('Enter');
    await s.page.waitForTimeout(2500);
  } else console.log('no address search box; saving the map default');
  await ui.click(s.page, 'Save', { within: picker, wait: 2500 });
  for (const sw of ['People History', 'Person Appearance & Attributes', 'Face Detection']) {
    const t = dlg.getByRole('switch', { name: sw });
    // The switch input is visually hidden; its parent is the clickable toggle.
    if (await t.isEnabled() && !(await t.isChecked())) { await t.locator('xpath=..').click(); await s.page.waitForTimeout(800); }
  }
  console.log(s.red(await dlg.ariaSnapshot()).split('\n').filter(l => /switch|textbox|Apply/.test(l)).join('\n'));
  ui.mark(s, `camera setup ${name}`);
  await ui.clickLast(s.page, 'Apply', { wait: 8000 });
};
