// Grant or revoke org-level roles on a user from User Management → user →
// Roles → Manage (each Manage dialog lists one group of roles) → tick/untick
// → Save. Only for test users, never the session's own user.
// Args: user name ("VC Test1"), "grant" | "revoke", role names...
// (e.g. "Access System Admin" "Access User Admin").
module.exports = async (s, ui, user, mode, ...roles) => {
  await ui.go(s, '/admin/users');
  await ui.click(s.page, user, { wait: 6000 });
  const want = mode === 'grant';
  const manage = s.page.getByRole('button', { name: 'Manage' });
  const todo = new Set(roles);
  for (let i = 0; i < await manage.count() && todo.size; i++) {
    await manage.nth(i).click();
    await s.page.waitForTimeout(2000);
    let changed = false;
    for (const role of [...todo]) {
      const cb = s.page.getByRole('checkbox', { name: new RegExp(`^${role} `) });
      if (!(await cb.count())) continue;
      todo.delete(role);
      if ((await cb.isChecked()) === want) continue;
      ui.mark(s, `${mode} ${role}`);
      await cb.locator('xpath=..').click();
      await s.page.waitForTimeout(600);
      changed = true;
    }
    if (changed) {
      let saved = false;
      for (const b of ['Save', 'Apply', 'Update', 'Done']) { try { await ui.clickLast(s.page, b, { wait: 4000 }); saved = true; break; } catch {} }
      if (!saved) throw new Error('no Save button');
      await ui.confirm(s.page, ['Confirm', 'Yes', 'Save']).catch(() => {});
    } else {
      await ui.clickLast(s.page, 'Cancel', { wait: 1500 }).catch(() => s.page.keyboard.press('Escape'));
    }
  }
  if (todo.size) throw new Error(`roles not found: ${[...todo].join(', ')}`);
};
