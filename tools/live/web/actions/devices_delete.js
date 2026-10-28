// Delete several devices at once: Devices → tick each device → Delete →
// confirm (verification code or plain). Args: device names as listed.
module.exports = async (s, ui, ...names) => {
  await ui.go(s, '/devices');
  for (const n of names) {
    // Row names read "<name> device status …" or "<name> New …".
    const row = s.page.getByRole('listitem').filter({ has: s.page.getByRole('row', { name: new RegExp(`^${n} (device status|New)\\b`) }) }).first();
    // The row checkbox is only visible on hover; click it in the DOM.
    await row.getByRole('checkbox').evaluate(e => e.click());
    await s.page.waitForTimeout(600);
  }
  await ui.click(s.page, 'Delete', { within: s.page.locator('main'), wait: 2500 });
  ui.mark(s, `devices delete x${names.length}`);
  await ui.confirm(s.page, ['Delete', 'Confirm', 'Decommission', 'Yes']);
};
