// Create the Access Station Pro's own door: Access → Devices → AF64 → Door
// lock connected to AF64 → Add new door → I/Os to AF64 → name, building /
// floor → through to the end of the wizard. Each step is printed.
// Args: controller ("HQ AF64"), door ("HQ Door"), building / floor
// ("HQ / G"; the building is the only one, so only the floor is picked).
module.exports = async (s, ui, ctrl = 'HQ AF64', door = 'HQ Door', floor = 'HQ / G') => {
  await ui.go(s, '/access');
  await ui.click(s.page, 'Devices', { wait: 4000 });
  await ui.click(s.page, ctrl, { wait: 6000 });
  await s.page.getByRole('button', { name: 'Select' }).first().click();
  await s.page.waitForTimeout(2500);
  await s.page.getByText('Add new door', { exact: true }).click();
  await ui.clickLast(s.page, 'Select', { wait: 3000 });
  ui.mark(s, `door.create ${door}`);
  for (let step = 0; step < 6; step++) {
    const dlg = s.page.getByRole('dialog').last();
    if (!(await dlg.count()) || !(await dlg.isVisible())) break;
    console.log(`step ${step}:`, s.red(await dlg.ariaSnapshot()).split('\n').filter(l => /textbox|button|switch|heading|radio|combobox/.test(l)).join(' | ').slice(0, 700));
    const name = dlg.getByRole('textbox', { name: /door name|^name/i });
    if (await name.count()) await name.first().fill(door);
    const fl = dlg.getByRole('button', { name: 'Unknown Floor' });
    if (await fl.count()) {
      // Picker: Open (the building) → the floor's label (not its Delete
      // button, nor "Delete Building") → Apply.
      const [bld, fname] = floor.split(' / ');
      await fl.click();
      await s.page.waitForTimeout(2500);
      const picker = s.page.getByRole('dialog').filter({ hasText: 'Select Building & Floor' }).last();
      await picker.getByRole('button', { name: 'Open' }).click();
      await s.page.waitForTimeout(2000);
      await picker.getByText(fname, { exact: true }).click();
      await s.page.waitForTimeout(1000);
      await ui.click(s.page, 'Apply', { within: picker, wait: 2000 });
      console.log('  building', bld, 'floor', fname, 'set');
    }
    let clicked = false;
    for (const b of ['Next', 'Create Door', 'Create', 'Add Door', 'Save', 'Done', 'Finish']) {
      try { await ui.clickLast(s.page, b, { wait: 4000 }); clicked = true; break; } catch {}
    }
    if (!clicked) break;
  }
};
