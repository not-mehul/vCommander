// Add a license plate credential to the session's own access user: Access →
// Users → user → Profile → Add License Plate → number → ✓ (Done, an icon
// button). With "remove", remove that plate instead (Remove License Plate on
// its row → confirm). Args: plate ("VCTEST1"), ["remove"].
module.exports = async (s, ui, plate = 'VCTEST1', remove) => {
  await ui.go(s, `/access/users/${process.env.X_VERKADA_USER_ID}/recent`);
  await ui.click(s.page, 'Profile', { wait: 3000 });
  if (remove) {
    // Rows show the plate masked (***1); match on its last character.
    const row = s.page.locator('div').filter({ hasText: new RegExp(`^\\*+${plate.slice(-1)}$`) }).last().locator('xpath=..');
    ui.mark(s, `license_plate.remove ${plate}`);
    await row.getByRole('button', { name: 'Remove License Plate' }).click();
    await s.page.waitForTimeout(1500);
    await ui.confirm(s.page, ['Remove', 'Delete', 'Confirm', 'Yes']).catch(() => {});
    return;
  }
  await ui.click(s.page, 'Add License Plate', { wait: 1500 });
  const box = s.page.getByRole('textbox', { name: 'New License Plate Number' });
  await box.click();
  await box.pressSequentially(plate, { delay: 60 }); // fill() doesn't enable ✓
  await s.page.waitForTimeout(1000);
  ui.mark(s, `license_plate.add ${plate}`);
  await s.page.getByRole('button', { name: 'Done' }).click();
  await s.page.waitForTimeout(4000);
};
