// Delete a Command group: User Management → Groups → group → Actions →
// Delete → confirm. Arg: group name.
module.exports = async (s, ui, name = 'VC Test Group') => {
  await ui.go(s, '/admin/groups');
  await s.page.getByRole('row').filter({ hasText: name }).first().click();
  await s.page.waitForTimeout(4000);
  await ui.click(s.page, 'Actions', { wait: 1500 });
  console.log((await ui.tree(s, { lines: 600 })).split('\n').filter(l => /menuitem/.test(l)).join('\n'));
  await ui.click(s.page, /^Delete/, { within: s.page.getByRole('menu').or(s.page.getByRole('dialog')).last(), wait: 2000 });
  ui.mark(s, `group.delete ${name}`);
  await ui.confirm(s.page, ['Delete', 'Delete Group', 'Confirm', 'Yes']);
};
