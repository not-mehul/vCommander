// Delete a door from its controller's Settings tab (Access → door → Settings
// → Delete Door → Delete). Arg: door name (default "HQ Door").
module.exports = async (s, ui, door = 'HQ Door') => {
  await ui.go(s, '/access');
  await ui.click(s.page, door, { wait: 6000 });
  await ui.click(s.page, 'Settings', { wait: 5000 });
  await ui.click(s.page, 'Delete Door');
  ui.mark(s, 'door.delete');
  await ui.click(s.page, 'Delete', { wait: 6000 });
};
