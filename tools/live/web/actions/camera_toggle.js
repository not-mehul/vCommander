// Toggle a camera setting off and back to its current state, recording both
// calls: Devices → camera → Go to Device Details Page → Settings → the switch
// after the given label text (confirming any dialog).
// Args: camera name, label text (e.g. "HQ PTZ" "Installation Mode"), and
// "once" to flip it once. Only for labels followed by their own switch (LPR
// mode has an Enable link instead: camera_lpr_enable.js).
module.exports = async (s, ui, name, label, once) => {
  await ui.go(s, '/devices');
  await ui.click(s.page, new RegExp(`^${name}\\b`), { wait: 3000 });
  await ui.click(s.page, 'Go to Device Details Page', { wait: 8000 });
  await ui.click(s.page, 'Settings', { wait: 6000 });
  const sw = s.page.getByText(label, { exact: true }).first().locator('xpath=following::input[@role="switch" or @type="checkbox"][1]');
  await sw.scrollIntoViewIfNeeded();
  const start = await sw.isChecked();
  for (const want of once ? [!start] : [!start, start]) {
    ui.mark(s, `${label} -> ${want}`);
    await sw.locator('xpath=..').click();
    await s.page.waitForTimeout(2500);
    for (const b of ['Yes', 'Enable', 'Disable', 'Confirm', 'Continue', 'Accept', 'Agree']) {
      try { await ui.clickLast(s.page, b, { wait: 3000 }); break; } catch {}
    }
    console.log(`${label}: ${await sw.isChecked()} (wanted ${want})`);
  }
};
