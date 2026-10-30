// Create, then delete, an API key: Org Settings → API & Integrations → API
// Keys → Add → name, type Cameras + first permission → Generate API; close the
// dialog showing the secret (never read), then delete the key from the list.
// run.js api_key_delete deletes a leftover key only.
module.exports = async (s, ui, name = 'vc-live-web') => {
  await ui.go(s, '/admin/settings/api-integrations/api-keys');
  await ui.click(s.page, 'Add', { wait: 2500 });
  const dlg = s.page.getByRole('dialog').last();
  await dlg.getByRole('textbox', { name: 'Name' }).fill(name);
  await dlg.getByRole('button', { name: 'Open menu of options for Select Type' }).click();
  await s.page.waitForTimeout(1200);
  await s.page.getByRole('menuitem', { name: 'Cameras', exact: true }).last().click();
  await s.page.waitForTimeout(1200);
  await dlg.getByRole('button', { name: 'Open menu of options for Permissions' }).click();
  await s.page.waitForTimeout(1200);
  const perms = s.page.getByRole('menuitem').filter({ hasText: /read/i });
  console.log('permissions offered:', (await perms.allInnerTexts()).join(' | '));
  await perms.last().click();
  await s.page.waitForTimeout(1000);
  ui.mark(s, 'org.api_key.create');
  await ui.clickLast(s.page, 'Generate API', { wait: 5000 });
  for (const b of ['Done', 'Close', 'OK']) { try { await ui.clickLast(s.page, b, { wait: 2000 }); break; } catch {} }
  await s.page.keyboard.press('Escape');
  await ui.go(s, '/admin/settings/api-integrations/api-keys');
  await module.exports.remove(s, ui, name, true);
};

// Delete the named key ("Delete <name>" button) and confirm.
module.exports.remove = async (s, ui, name = 'vc-live-web', loaded = false) => {
  if (!loaded) await ui.go(s, '/admin/settings/api-integrations/api-keys');
  await s.page.getByRole('button', { name: `Delete ${name}` }).click();
  await s.page.waitForTimeout(1500);
  ui.mark(s, 'org.api_key.delete');
  await ui.confirm(s.page, ['Delete', 'Confirm', 'Remove', 'Revoke', 'Yes']);
};
