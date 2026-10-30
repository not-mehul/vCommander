// Create a Command group with members, then delete it: User Management →
// Groups → Create Group → name, Members (pick each user) → Create Group;
// then the group's delete. Args: group name, member names...
module.exports = async (s, ui, name = 'VC Test Group', ...members) => {
  await ui.go(s, '/admin/groups');
  await ui.click(s.page, 'Create Group', { wait: 2500 });
  const dlg = s.page.getByRole('dialog').last();
  await dlg.getByRole('textbox', { name: 'Command Group Name' }).fill(name);
  if (members.length) {
    await dlg.getByRole('button', { name: /^Members/ }).click();
    await s.page.waitForTimeout(2000);
    for (const m of members) {
      const search = s.page.getByRole('searchbox').or(s.page.getByPlaceholder(/search/i)).last();
      if (await search.count()) { await search.fill(m); await s.page.waitForTimeout(1500); }
      await s.page.getByText(m, { exact: true }).last().click();
      await s.page.waitForTimeout(800);
    }
    console.log((await ui.tree(s, { lines: 600 })).split('\n').filter(l => /dialog|button "(Apply|Done|Save|Add|Confirm)|checkbox/.test(l) && !/@/.test(l)).slice(-12).join('\n'));
    for (const b of ['Apply', 'Done', 'Save', 'Add', 'Confirm']) { try { await ui.clickLast(s.page, b, { wait: 1500 }); break; } catch {} }
  }
  ui.mark(s, `group.create ${name}`);
  await ui.clickLast(s.page, 'Create Group', { wait: 5000 });
  await ui.go(s, '/admin/groups');
  const row = s.page.getByRole('row').filter({ hasText: name }).first();
  console.log('group row:', s.red((await row.innerText().catch(() => '')).replace(/\s+/g, ' ')).slice(0, 200));
  await row.click();
  await s.page.waitForTimeout(4000);
  console.log((await ui.tree(s, { root: 'main', lines: 80 })).split('\n').filter(l => /button|tab|heading/.test(l) && !/@/.test(l)).slice(0, 25).join('\n'));
};
