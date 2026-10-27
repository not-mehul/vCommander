// Create a building with one floor: Access → Settings → Buildings → Add
// Building → name, address (first suggestion), floor → Create.
// Args: name ("HQ"), address, floor ("G").
module.exports = async (s, ui, name = 'HQ', address = '406 E 3rd Ave, San Mateo, CA 94401', floor = 'G') => {
  await ui.go(s, '/access/admin/buildings');
  await ui.click(s.page, 'Add Building', { wait: 2000 });
  const dlg = s.page.getByRole('dialog').filter({ hasText: 'Create Building and Floor' });
  await dlg.getByRole('textbox', { name: 'Building Name*' }).fill(name);
  await dlg.getByRole('textbox', { name: 'Address*' }).click();
  await ui.pickAddress(s.page, address);
  await dlg.getByRole('textbox', { name: 'Floor Name*' }).fill(floor);
  console.log(s.red(await dlg.ariaSnapshot()).split('\n').filter(l => /textbox|button/.test(l)).join('\n'));
  ui.mark(s, `building.create ${name}`);
  await ui.click(s.page, 'Create', { within: dlg, wait: 6000 });
};
