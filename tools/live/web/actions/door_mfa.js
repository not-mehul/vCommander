// Door two-factor modes: Access → door → Settings → Two-Factor (2FA) Entry →
// Manage → untick Card + Code → Save, then tick all → Save (records the
// disable/enable calls; Save stays disabled with nothing ticked).
// Arg: door ("HQ Door").
module.exports = async (s, ui, door = 'HQ Door') => {
  await ui.go(s, '/access');
  await ui.click(s.page, door, { wait: 6000 });
  await ui.click(s.page, 'Settings', { wait: 5000 });
  const sec = s.page.getByText('Two-Factor (2FA) Entry', { exact: true });
  for (const want of [false, true]) {
    await sec.scrollIntoViewIfNeeded();
    await sec.locator('xpath=following::button[normalize-space()="Manage"][1]').click();
    await s.page.waitForTimeout(2000);
    const dlg = s.page.getByRole('dialog', { name: 'Select Two-Factor (2FA) Entry Credentials' });
    ui.mark(s, `door.mfa ${want ? 'on' : 'off'}`);
    for (const cb of (await dlg.getByRole('checkbox').all()).slice(0, want ? 3 : 1)) {
      if ((await cb.isChecked()) !== want) await cb.locator('xpath=..').click();
      await s.page.waitForTimeout(300);
    }
    await ui.click(s.page, 'Save', { within: dlg, wait: 4000 });
  }
};
