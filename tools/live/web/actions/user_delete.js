// Delete a test user: User Management → user → User Actions → Delete User
// → confirm. Refuses any user whose name doesn't start with "VC Test", so the
// owner's and the session's accounts can't be touched. Arg: user name.
module.exports = async (s, ui, user) => {
  if (!/^VC Test/.test(user || '')) throw new Error('only "VC Test…" users may be deleted');
  await ui.go(s, '/admin/users');
  await ui.click(s.page, user, { wait: 6000 });
  await ui.click(s.page, 'User Actions', { wait: 1500 });
  console.log((await ui.tree(s, { lines: 600 })).split('\n').filter(l => /menuitem/.test(l)).join('\n'));
  await ui.click(s.page, 'Delete User', { within: s.page.getByRole('menu').or(s.page.getByRole('dialog')).last(), wait: 2000 });
  ui.mark(s, `user.delete ${user}`);
  await ui.confirm(s.page, ['Delete', 'Delete User', 'Remove', 'Confirm', 'Yes']);
};
