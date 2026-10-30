// Set up a standard access controller: Devices → controller → Set Up →
// Device Mode, Timezone, Site, Building / Floor → Apply. Options are printed.
// Args: name ("HQ Controller"), mode ("Standard"), timezone search text
// ("Los Angeles"), site ("HQ"), floor ("G").
module.exports = async (s, ui, name = 'HQ Controller', mode = 'Standard', tz = 'Los Angeles', site = 'HQ', floor = 'G') => {
  await ui.go(s, '/devices');
  await ui.click(s.page, new RegExp(`^${name}\\b`), { wait: 3000 });
  await ui.click(s.page, 'Set Up', { wait: 3000 });
  const dlg = s.page.getByRole('dialog').filter({ has: s.page.getByRole('button', { name: 'Apply' }) });
  const items = () => s.page.getByRole('menuitem').or(s.page.getByRole('option')).or(s.page.getByRole('menuitemradio'));
  // Device Mode: the first "Not Selected" dropdown.
  await dlg.getByRole('button', { name: 'Not Selected' }).first().click();
  await s.page.waitForTimeout(1500);
  // The dropdown's entries are plain text, not menu items.
  await s.page.getByText(mode, { exact: true }).last().click();
  await s.page.waitForTimeout(1000);
  // Timezone: a searchable dropdown; type to filter, take the first match.
  await dlg.getByText('Coordinated Universal Time').first().click();
  await s.page.waitForTimeout(1000);
  await s.page.keyboard.type(tz, { delay: 40 });
  await s.page.waitForTimeout(1500);
  const tzItem = s.page.getByText(new RegExp(tz, 'i')).last();
  console.log('timezone:', await tzItem.innerText().catch(() => '(none)'));
  await tzItem.click().catch(() => s.page.keyboard.press('Enter'));
  await s.page.waitForTimeout(1000);
  await dlg.getByRole('button', { name: 'Open menu of options for Site' }).click();
  await s.page.waitForTimeout(1000);
  await s.page.getByRole('menuitem', { name: site, exact: true }).last().click();
  await s.page.waitForTimeout(1500);
  // Building / Floor: the remaining "Not Selected" button opens the picker.
  await dlg.getByRole('button', { name: 'Not Selected' }).last().click();
  await s.page.waitForTimeout(2000);
  const picker = s.page.getByRole('dialog').filter({ hasText: 'Select Building & Floor' }).last();
  if (await picker.count()) {
    await picker.getByRole('button', { name: 'Open' }).click();
    await s.page.waitForTimeout(1500);
    await picker.getByText(floor, { exact: true }).click();
    await ui.click(s.page, 'Apply', { within: picker, wait: 1500 });
  } else {
    console.log('floor options:', (await items().allInnerTexts()).join(' | ').slice(0, 300));
    await items().filter({ hasText: new RegExp(`\\b${floor}$`) }).first().click();
  }
  console.log(s.red(await dlg.ariaSnapshot()).split('\n').filter(l => /button|textbox|combobox/.test(l)).join('\n').slice(0, 800));
  ui.mark(s, `access_controller setup ${name}`);
  await ui.clickLast(s.page, 'Apply', { wait: 8000 });
};
