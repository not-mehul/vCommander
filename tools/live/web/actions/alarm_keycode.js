// Add a general keycode: Alarms → site → Settings → Add Keycode → name (the
// code is pre-filled) → Add Keycode. Args: site ("HQ"), name ("Web Keycode").
module.exports = async (s, ui, site = 'HQ', name = 'Web Keycode') => {
  await ui.go(s, '/new-alarms');
  await ui.click(s.page, 'Search', { wait: 3000 });
  await ui.click(s.page, site, { wait: 6000 });
  await ui.click(s.page, 'Settings', { wait: 6000 });
  await ui.click(s.page, 'Add Keycode', { wait: 2500 });
  const dlg = s.page.getByRole('dialog').filter({ hasText: 'Add Keycode' }).last();
  await dlg.getByRole('textbox', { name: 'Name' }).fill(name);
  ui.mark(s, `alarm keycode ${name}`);
  await ui.click(s.page, 'Add Keycode', { within: dlg, wait: 5000 });
};
