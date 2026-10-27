// Remove a Guest site: Guest Settings → site → Remove Site → Remove → confirm.
// Arg: site name (default "HQ").
module.exports = async (s, ui, name = 'HQ') => {
  await ui.go(s, '/guest/settings');
  await ui.click(s.page, new RegExp(`^${name} `), { wait: 5000 });
  await ui.click(s.page, 'Remove', { wait: 2500 });
  ui.mark(s, `guest site remove ${name}`);
  await ui.confirm(s.page, ['Remove Site', 'Remove', 'Delete', 'Confirm']);
};
