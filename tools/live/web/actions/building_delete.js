// Delete a building's floor, then the building: Access → Settings → Buildings
// → building → Delete (floor) → confirm; back → Delete (building) → confirm.
// Arg: building name (default "HQ").
module.exports = async (s, ui, name = 'HQ') => {
  await ui.go(s, '/access/admin/buildings');
  await ui.click(s.page, new RegExp(`Terms \\(opens in new tab\\) ${name} `), { wait: 6000 });
  await ui.click(s.page, 'Delete', { wait: 2500 });
  ui.mark(s, 'floor.delete');
  await ui.confirm(s.page, ['Delete', 'Confirm']).catch(e => console.log('floor delete:', e.message));
  await ui.go(s, '/access/admin/buildings');
  await ui.click(s.page, 'Delete', { wait: 2500 });
  ui.mark(s, 'building.delete');
  await ui.confirm(s.page, ['Delete', 'Confirm']);
};
