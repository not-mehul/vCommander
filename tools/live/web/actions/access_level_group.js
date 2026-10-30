// Show, and with SELECT=1 add, an access group on an existing access level:
// Access → Access Levels → the level → Groups picker → the group → Apply →
// Save → Confirm. Args: level ("HQ 24/7 Access"), group ("All Participants").
module.exports = async (s, ui, level = 'HQ 24/7 Access', group = 'All Participants') => {
  await ui.go(s, '/access');
  await ui.click(s.page, 'Access Levels', { wait: 4000 });
  await s.page.getByRole('listitem').filter({ hasText: level }).first().click();
  await s.page.waitForTimeout(5000);
  console.log(s.red((await s.page.locator('body').ariaSnapshot()).split('\n').filter(l => /group|textbox|Save|Edit|dialog|heading|Apply/i.test(l)).slice(0, 30).join('\n')));
  await ui.shot(s, 'access_level_group-before');
  if (!process.env.SELECT) return;
  const box = s.page.getByRole('textbox', { name: 'Add Groups...' }).last();
  await box.click({ force: true });
  await s.page.waitForTimeout(2000);
  await s.page.getByText(group, { exact: true }).last().click();
  await s.page.waitForTimeout(800);
  await ui.clickLast(s.page, 'Apply', { wait: 1500 });
  ui.mark(s, `access_level.update groups +${group}`);
  await ui.clickLast(s.page, 'Save', { wait: 3000 });
  // "Confirm Access Level Changes: Add 1 access group".
  await ui.clickLast(s.page, 'Confirm', { wait: 5000 });
};
