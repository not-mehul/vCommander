// Set up a claimed alarm device: Devices → device → Set Up → Site, Name →
// Apply. For a panel this creates the site's alarm system.
// Args: listed name ("Unnamed Device"), new name ("HQ Alarm Panel"), site.
module.exports = async (s, ui, listed = 'Unnamed Device', name = 'HQ Alarm Panel', site = 'HQ') => {
  await ui.go(s, '/devices');
  await ui.click(s.page, new RegExp(`^${listed}\\b`), { wait: 3000 });
  await ui.click(s.page, 'Set Up', { wait: 3000 });
  const dlg = s.page.getByRole('dialog').filter({ has: s.page.getByRole('button', { name: 'Apply' }) });
  // The site list opens by itself (the field is focused on open).
  const item = s.page.getByRole('listitem').filter({ hasText: new RegExp(`^${site}$`) }).last();
  if (!(await item.isVisible())) await dlg.getByRole('textbox', { name: 'Site' }).click({ force: true });
  await item.click();
  await s.page.waitForTimeout(1500);
  await dlg.getByRole('textbox', { name: 'Name' }).fill(name);
  console.log(s.red(await dlg.ariaSnapshot()).split('\n').filter(l => /textbox|button/.test(l)).join('\n'));
  ui.mark(s, `alarm device setup ${name}`);
  await ui.clickLast(s.page, 'Apply', { wait: 10000 });
};
