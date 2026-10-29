// Show, and with SELECT=1 grant, a site role: user → Roles → Site Roles
// Manage → type → the site's role → Save. Only for test users.
// Args: user ("VC Test 4"), type ("Command"), site ("HQ"), role ("Site Admin").
module.exports = async (s, ui, user = 'VC Test 4', type = 'Command', site = 'HQ', role = 'Site Admin') => {
  await ui.go(s, '/admin/users');
  await ui.click(s.page, user, { wait: 6000 });
  await s.page.getByRole('button', { name: 'Manage' }).nth(2).click();
  await s.page.waitForTimeout(2500);
  await ui.click(s.page, 'Select type', { wait: 1500 }).catch(() => {});
  await ui.click(s.page, type, { wait: 3000 });
  console.log(s.red((await s.page.locator('main').first().ariaSnapshot()).split('\n')
    .filter(l => /row|cell|combobox|option|checkbox|radio|button|Site|Admin|Viewer|Manager/.test(l)).slice(0, 60).join('\n')));
  await ui.shot(s, 'user_site_role-before');
  if (!process.env.SELECT) return;
  const row = s.page.getByRole('row').filter({ hasText: site }).first();
  await row.getByRole('button').last().click();  // the role ("None")
  await s.page.waitForTimeout(1500);
  console.log(s.red((await s.page.locator('body').ariaSnapshot()).split('\n')
    .filter(l => /option|menuitem|radio|Admin|Viewer|Manager|Live|Responder/.test(l)).slice(0, 30).join('\n')));
  ui.mark(s, `grant site ${type} ${role} on ${site}`);
  await s.page.getByText(role, { exact: true }).last().click();
  await s.page.waitForTimeout(1000);
  for (const b of ['Save', 'Apply', 'Update', 'Done']) { try { await ui.clickLast(s.page, b, { wait: 4000 }); break; } catch {} }
  await ui.confirm(s.page, ['Confirm', 'Yes', 'Save']).catch(() => {});
};
