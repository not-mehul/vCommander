// Delete an alarm device (panel, keypad, expander, sensor) from its page in
// Alarms: Devices → device → Go to Device Details Page → ⋯ → Delete → confirm.
// Arg: device name as listed on /devices (e.g. "HQ Alarm Panel").
module.exports = async (s, ui, name) => {
  await ui.go(s, '/devices');
  await ui.click(s.page, new RegExp(`^${name}\\b`), { wait: 4000 });
  await ui.click(s.page, 'Go to Device Details Page', { wait: 8000 });
  await s.page.getByRole('combobox').locator('button').first().click();
  await s.page.waitForTimeout(1500);
  await ui.click(s.page, 'Delete', { within: s.page.getByRole('menu'), wait: 2500 });
  ui.mark(s, `alarm device delete ${name}`);
  await ui.confirm(s.page);
};
