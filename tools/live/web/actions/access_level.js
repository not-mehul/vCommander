// Create, then delete, an access level: Access → Access Levels → Add Access
// Level → name, group, site, door (default all-week schedule) → Save; then
// the row's Delete Access Level (on hover) → confirm. DELETE_ONLY=1 skips
// the create.
// Args: name ("VCE Web Level"), group ("VCE Access Group"), site ("HQ"),
// door ("Garage Door", the VSSL door).
module.exports = async (s, ui, name = 'VCE Web Level', group = 'VCE Access Group', site = 'HQ', door = 'Garage Door') => {
  if (process.env.DELETE_ONLY) return module.exports.remove(s, ui, name);
  await ui.go(s, '/access');
  await ui.click(s.page, 'Access Levels', { wait: 4000 });
  await ui.click(s.page, 'Add Access Level', { wait: 3000 });
  const dlg = s.page.getByRole('dialog').last();
  await dlg.getByRole('textbox', { name: 'Access Level Name*' }).fill(name);
  // Each picker is a checklist dropdown with its own Apply button.
  const pick = async (box, text) => {
    await box.click({ force: true });
    await s.page.waitForTimeout(2000);
    await s.page.getByText(text, { exact: true }).last().click();
    await s.page.waitForTimeout(800);
    await ui.clickLast(s.page, 'Apply', { wait: 1500 });
  };
  await pick(dlg.getByRole('textbox', { name: 'Add Groups...' }), group);
  await pick(dlg.getByRole('textbox', { name: 'Select Sites...' }), site);
  await pick(dlg.getByPlaceholder('Search Doors'), door);
  console.log(s.red(await dlg.ariaSnapshot()).split('\n').filter(l => /textbox|searchbox|Save|listitem/.test(l)).slice(0, 14).join('\n'));
  ui.mark(s, `access_level.create ${name}`);
  await ui.click(s.page, 'Save', { within: dlg, wait: 5000 });
  await module.exports.remove(s, ui, name);
};

module.exports.remove = async (s, ui, name) => {
  await ui.go(s, '/access');
  await ui.click(s.page, 'Access Levels', { wait: 4000 });
  const item = s.page.getByRole('listitem').filter({ hasText: name }).first();
  // The row's actions (Clone / Delete Access Level) appear on hover.
  await item.hover();
  await s.page.waitForTimeout(800);
  await item.getByRole('button', { name: 'Delete Access Level' }).click();
  await s.page.waitForTimeout(2000);
  ui.mark(s, `access_level.delete ${name}`);
  await ui.confirm(s.page, ['Delete', 'Confirm', 'Yes']);
};
