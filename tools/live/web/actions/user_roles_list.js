// Read-only: open each Manage panel on a user's Roles tab (Organization,
// User Management, Site roles) and print the roles it offers, then go
// "Back to all roles". Arg: user name ("VC Test 1").
module.exports = async (s, ui, user = 'VC Test 1') => {
  await ui.go(s, '/admin/users');
  await ui.click(s.page, user, { wait: 6000 });
  const manage = s.page.getByRole('button', { name: 'Manage' });
  const n = await manage.count();
  for (let i = 0; i < n; i++) {
    await manage.nth(i).click();
    await s.page.waitForTimeout(2500);
    const text = await s.page.locator('main').first().innerText().catch(() => '');
    console.log(`== Manage #${i + 1}\n` + s.red(text.split('\n').filter(Boolean).slice(0, 80).join(' | ')));
    await ui.shot(s, `user_roles_list-${i + 1}`);
    await ui.click(s.page, 'Back to all roles', { wait: 3000 });
  }
};
