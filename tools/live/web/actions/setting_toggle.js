// Flip the switch that follows a label on a settings page, then flip it back
// (or only once with "once"), confirming any dialog; records both calls.
// Args: route, label, ["once"]. E.g. /admin/settings/user-permissions/
// customize-roles "Global Site Admin"; /access/settings "Enable Face Unlock".
module.exports = async (s, ui, route, label, once) => {
  await ui.go(s, route);
  const sw = s.page.getByText(label, { exact: true }).first().locator('xpath=following::input[@role="switch" or @type="checkbox"][1]');
  await sw.scrollIntoViewIfNeeded();
  const start = await sw.isChecked();
  for (const want of once ? [!start] : [!start, start]) {
    ui.mark(s, `${label} -> ${want}`);
    await sw.locator('xpath=..').click();
    await s.page.waitForTimeout(2500);
    for (const b of ['Yes', 'Enable', 'Disable', 'Confirm', 'Turn On', 'Turn Off', 'Continue', 'Save']) {
      try { await ui.clickLast(s.page, b, { wait: 3000 }); break; } catch {}
    }
    console.log(`${label}: ${await sw.isChecked()} (wanted ${want})`);
  }
};
