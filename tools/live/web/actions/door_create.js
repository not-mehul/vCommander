// Add a door to a standard access controller: Access → Devices → controller
// → Add → Door → name (building/floor pre-filled) → through the wizard
// (Next … Done), printing each step. Args: controller ("HQ Controller"),
// door ("Garage Door").
module.exports = async (s, ui, ctrl = 'HQ Controller', door = 'Garage Door') => {
  await ui.go(s, '/access');
  await ui.click(s.page, 'Devices', { wait: 4000 });
  await ui.click(s.page, ctrl, { wait: 6000 });
  await ui.click(s.page, 'Add', { wait: 2000 });
  await ui.click(s.page, /^Door Allows/, { wait: 3000 });
  const dlg = s.page.getByRole('dialog').last();
  await dlg.getByRole('textbox', { name: 'Door Name' }).fill(door);
  ui.mark(s, `door.create ${door}`);
  for (let step = 0; step < 6; step++) {
    const d = s.page.getByRole('dialog').last();
    if (!(await d.count()) || !(await d.isVisible())) break;
    console.log(`step ${step}:`, s.red(await d.ariaSnapshot()).split('\n').filter(l => /heading|textbox|switch|radio|combobox|button "(Next|Done|Create|Save)/.test(l)).join(' | ').slice(0, 700));
    let clicked = false;
    for (const b of ['Next', 'Create Door', 'Create', 'Save', 'Done']) { try { await ui.clickLast(s.page, b, { wait: 4000 }); clicked = true; break; } catch {} }
    if (!clicked) break;
  }
};
