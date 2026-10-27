// Create a site: Admin → Sites → Add site → Name → Add. Arg: name ("HQ").
module.exports = async (s, ui, name = 'HQ') => {
  await ui.go(s, '/admin/sites');
  await ui.click(s.page, 'Add site', { wait: 1500 });
  const dlg = s.page.getByRole('dialog', { name: 'Add New Site' });
  await ui.fill(s.page, 'Name', name, { within: dlg });
  ui.mark(s, `site.create ${name}`);
  await ui.click(s.page, 'Add', { within: dlg, wait: 5000 });
};
