// Turn on LPR mode: Devices → camera → Go to Device Details Page → Settings →
// "License Plate Recognition (LPR) Mode" Enable → Yes. Arg: camera ("HQ Bullet").
module.exports = async (s, ui, name = 'HQ Bullet') => {
  await ui.go(s, '/devices');
  await ui.click(s.page, new RegExp(`^${name}\\b`), { wait: 3000 });
  await ui.click(s.page, 'Go to Device Details Page', { wait: 8000 });
  await ui.click(s.page, 'Settings', { wait: 6000 });
  const label = s.page.getByText('License Plate Recognition (LPR) Mode', { exact: true });
  await label.scrollIntoViewIfNeeded();
  ui.mark(s, 'camera LPR mode on');
  await ui.click(s.page, 'Enable', { wait: 0 });
  await s.page.waitForTimeout(2500);
  await ui.clickLast(s.page, 'Yes', { wait: 6000 });
};
