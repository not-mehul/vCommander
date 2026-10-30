// Set up several unassigned devices at once: Devices → My Unassigned Devices
// → Batch Setup → the device-type group (e.g. "4 Cameras") → Site, Location,
// analytics → Apply. Args: group label (/Cameras/), site ("HQ"), address.
const { fillAndApply } = require('./camera_setup');
module.exports = async (s, ui, group = 'Cameras', site = 'HQ', address = '406 E 3rd Ave, San Mateo') => {
  await ui.go(s, '/devices');
  await ui.click(s.page, 'Batch Setup', { wait: 3000 });
  await ui.click(s.page, new RegExp(`^\\d+ ${group}$`), { wait: 3000 });
  await fillAndApply(s, ui, `batch ${group}`, site, address);
};
