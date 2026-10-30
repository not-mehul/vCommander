// Decommission (unclaim) a device from its details page: Devices → device →
// Go to Device Details Page → Settings → Decommission (access controllers) or
// Delete (cameras) → type the verification code → Confirm / Delete.
// Arg: device name as listed on /devices (e.g. "HQ AF64").
module.exports = async (s, ui, name) => {
  await ui.go(s, '/devices');
  await ui.click(s.page, new RegExp(`^${name}\\b`), { wait: 4000 });
  await ui.click(s.page, 'Go to Device Details Page', { wait: 8000 });
  await ui.click(s.page, 'Settings', { wait: 5000 }).catch(() => {});
  const btn = await ui.click(s.page, /^(Decommission|Delete)$/, { wait: 2500 });
  const label = (await btn.innerText()).trim();
  ui.mark(s, `${label} ${name}`);
  await ui.confirmCode(s.page, { button: label === 'Delete' ? 'Delete' : 'Confirm' });
};
