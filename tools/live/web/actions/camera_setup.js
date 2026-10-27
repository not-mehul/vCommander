// Set up a new camera, Command Connector or Access Station Pro (same dialog;
// connectors have no location, non-cameras no analytics):
// Devices → device → Set Up → Site, Location (first address suggestion),
// analytics switches that are enabled → Apply.
// Args: device name ("HQ CD62"), site ("HQ"), address.
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
  // Location (cameras, controllers) opens a map picker: search the address,
  // take the first suggestion, Save. Command Connectors have no location.
  const loc = dlg.getByRole('textbox', { name: 'Select Location' });
  // Once the site has a location, choosing the site fills this in.
  if (await loc.isVisible().catch(() => false) && !(await loc.inputValue())) {
    await loc.click({ timeout: 5000 }).catch(() => loc.click({ force: true }));
    await s.page.waitForTimeout(3000);
    const picker = s.page.getByRole('dialog', { name: 'Select Location' });
    if (await picker.count()) {
      const search = picker.locator('input[type=text], input:not([type])').first();
      if (await search.count()) {
        await search.click();
        await ui.pickAddress(s.page, address);
      } else console.log('no address search box; saving the map default');
      await ui.clickLast(s.page, 'Save', { wait: 2500 });
    } else console.log('location filled from the site');
  } else console.log('location: none or filled from the site');
  for (const sw of ['People History', 'Person Appearance & Attributes', 'Face Detection']) {
    const t = dlg.getByRole('switch', { name: sw });
    // The switch input is visually hidden; its parent is the clickable toggle.
    if (await t.count() && await t.isEnabled() && !(await t.isChecked())) { await t.locator('xpath=..').click(); await s.page.waitForTimeout(800); }
  }
  console.log(s.red(await dlg.ariaSnapshot()).split('\n').filter(l => /switch|textbox|Apply/.test(l)).join('\n'));
  ui.mark(s, `camera setup ${name}`);
  await ui.clickLast(s.page, 'Apply', { wait: 8000 });
};
