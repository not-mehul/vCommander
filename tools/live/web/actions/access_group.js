// Create an access group with members: Access → Users → Groups → Create
// Group → name, Members (pick each) → Create Group. Args: name, members...
module.exports = async (s, ui, name = 'VCE Access Group', ...members) => {
  await ui.go(s, '/access/users');
  await ui.click(s.page, 'Groups', { wait: 3000 });
  await ui.click(s.page, 'Create Group', { wait: 2500 });
  const dlg = s.page.getByRole('dialog').last();
  await dlg.getByRole('textbox', { name: 'Access Group Name' }).fill(name);
  if (members.length) {
    await dlg.getByRole('button', { name: /^Members/ }).click();
    await s.page.waitForTimeout(2000);
    for (const m of members) {
      const search = s.page.getByRole('searchbox').or(s.page.getByPlaceholder(/search/i)).last();
      if (await search.count()) { await search.fill(m); await s.page.waitForTimeout(1500); }
      await s.page.getByText(m, { exact: true }).last().click();
      await s.page.waitForTimeout(800);
    }
    for (const b of ['Done', 'Apply', 'Save', 'Add', 'Confirm']) { try { await ui.clickLast(s.page, b, { wait: 1500 }); break; } catch {} }
  }
  ui.mark(s, `access_group.create ${name}`);
  await ui.clickLast(s.page, 'Create Group', { wait: 5000 });
};
