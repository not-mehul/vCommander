// Invite a user: User Management → Add User → first/last name, email →
// Next → through the wizard (steps printed; roles left at their defaults
// unless ROLE names a checkbox/radio to tick) → the final Invite/Add/Save.
// Args: first, last, email. Env: ROLE (optional, e.g. "Org Admin").
module.exports = async (s, ui, first, last, email) => {
  await ui.go(s, '/admin/users');
  await ui.click(s.page, 'Add User', { wait: 2500 });
  const dlg = s.page.getByRole('dialog').last();
  await dlg.getByRole('textbox', { name: 'First Name*' }).fill(first);
  await dlg.getByRole('textbox', { name: 'Last Name*' }).fill(last);
  await dlg.getByRole('textbox', { name: 'Email Address*' }).fill(email);
  ui.mark(s, `user.create ${first} ${last}`);
  for (let step = 0; step < 6; step++) {
    const d = s.page.getByRole('dialog').last();
    if (!(await d.count()) || !(await d.isVisible())) break;
    const snap = s.red(await d.ariaSnapshot()).split('\n').filter(l => /heading|checkbox|radio|switch|combobox|textbox|button/.test(l) && !/@/.test(l));
    console.log(`step ${step}:`, snap.join(' | ').slice(0, 900));
    if (process.env.ROLE) {
      const r = d.getByRole('checkbox', { name: new RegExp(`^${process.env.ROLE}\\b`) }).or(d.getByRole('radio', { name: new RegExp(`^${process.env.ROLE}\\b`) }));
      if (await r.count() && !(await r.first().isChecked())) await r.first().locator('xpath=..').click();
    }
    // Verkada-employee emails default to a Temporary User; choose a full user
    // and tick the acknowledgement once.
    const ack = d.getByRole('checkbox', { name: /^I acknowledge/ });
    const full = d.getByRole('button', { name: /^Add as a full user/ });
    if (await ack.count()) {
      if (!(await ack.isChecked())) await ack.locator('xpath=..').click();
      const temp = d.getByRole('switch', { name: 'Temporary User' });
      if (await temp.count() && await temp.isChecked()) await temp.locator('xpath=..').click();
      await s.page.waitForTimeout(800);
    } else if (await full.count() && step === 0) {
      await full.click();
      await s.page.waitForTimeout(2500);
      continue;
    }
    let clicked = false;
    for (const b of ['Next', 'Create New User', 'Send Invite', 'Invite', 'Add User', 'Create User', 'Save', 'Done']) {
      try { await ui.clickLast(s.page, b, { wait: 3500 }); clicked = true; break; } catch {}
    }
    if (!clicked) break;
  }
};
