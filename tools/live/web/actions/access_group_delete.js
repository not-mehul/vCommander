// Delete an access group: Access → Users → Groups → group → Settings →
// Delete → confirm. Arg: group ("VCE Access Group").
module.exports = async (s, ui, name = 'VCE Access Group') => {
  await ui.go(s, '/access/users');
  await ui.click(s.page, 'Groups', { wait: 3000 });
  await ui.click(s.page, name, { wait: 5000 });
  await ui.click(s.page, 'Settings', { wait: 3000 });
  console.log((await ui.tree(s, { root: 'main', lines: 200 })).split('\n').filter(l => /button/.test(l) && !/@/.test(l)).slice(-10).join('\n'));
  await ui.click(s.page, /^Delete/, { wait: 2000 });
  ui.mark(s, `access_group.delete ${name}`);
  await ui.confirm(s.page, ['Delete', 'Delete Group', 'Confirm', 'Yes']);
};
