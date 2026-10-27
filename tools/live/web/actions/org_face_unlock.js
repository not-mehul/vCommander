// Org-wide face unlock: Access → Settings → Enable Face Unlock. Turns it off
// (if on, confirming any dialog) and back on, to record the enable call.
module.exports = async (s, ui) => {
  await ui.go(s, '/access/settings');
  const sw = s.page.getByText('Enable Face Unlock', { exact: true }).locator('xpath=following::input[@role="switch" or @type="checkbox"][1]');
  const toggle = async label => {
    ui.mark(s, label);
    await sw.locator('xpath=..').click();
    await s.page.waitForTimeout(2500);
    for (const b of ['Yes', 'Disable', 'Turn Off', 'Enable', 'Confirm', 'Continue', 'Save']) {
      try { await ui.clickLast(s.page, b, { wait: 3000 }); break; } catch {}
    }
    console.log(label, '-> checked:', await sw.isChecked());
  };
  if (await sw.isChecked()) await toggle('face unlock off');
  await toggle('org.allow_face_unlock on');
};
