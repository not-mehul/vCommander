// Delete a site: Admin → Sites → site → Site Actions → Delete → confirm.
// Arg: site name (default "HQ").
module.exports = async (s, ui, name = 'HQ') => {
  await ui.go(s, '/admin/sites');
  await ui.click(s.page, name, { wait: 3000 }).catch(() => {});
  await ui.click(s.page, 'Site Actions', { wait: 1500 });
  await ui.click(s.page, 'Delete', { within: s.page.getByRole('menu'), wait: 2500 });
  ui.mark(s, `site.delete ${name}`);
  await ui.confirm(s.page, ['Delete', 'Confirm']);
};
