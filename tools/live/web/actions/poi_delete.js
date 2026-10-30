// Remove a person of interest: Cameras → People → People of Interest →
// person → ⋯ (Menu) → Remove this person → confirm. Arg: label ("VC Test POI").
module.exports = async (s, ui, label = 'VC Test POI') => {
  await ui.go(s, '/cameras/people/all');
  await ui.click(s.page, 'People of Interest', { wait: 4000 });
  await ui.click(s.page, label, { wait: 5000 });
  await ui.click(s.page, 'Menu', { wait: 1500 });
  await ui.click(s.page, 'Remove this person', { wait: 2000 });
  ui.mark(s, `poi.delete ${label}`);
  await ui.confirm(s.page, ['Remove', 'Delete', 'Confirm', 'Yes']);
};
