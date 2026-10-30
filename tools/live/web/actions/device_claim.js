// Claim devices: Devices → Add Devices → type each serial + Enter → set the
// device name → Add N Devices, then report what the follow-up screen shows.
// Args: VAR=Name pairs, VAR being the env variable holding the serial
// (e.g. Dome="HQ CD62"). Serials are read from the environment, never printed.
module.exports = async (s, ui, ...pairs) => {
  await ui.go(s, '/devices/add');
  const tb = s.page.getByRole('textbox', { name: 'Enter serial, trial, or order number' });
  for (const p of pairs) {
    const [v, name] = p.split('=');
    const serial = process.env[v].trim();
    await tb.fill(serial);
    await s.page.keyboard.press('Enter');
    await s.page.waitForTimeout(5000);
    const nameBox = s.page.getByRole('textbox', { name: new RegExp(`^Device name for ${serial}$`, 'i') });
    await nameBox.fill(name);
  }
  ui.mark(s, `org.add_device x${pairs.length}`);
  await ui.click(s.page, /^Add \d+ Devices?$/, { wait: 12000 });
  console.log(await ui.tree(s, { root: 'main', lines: 60 }));
};
