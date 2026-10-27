// Remove an alarm site: Alarms → Search → site → Settings → Remove Site →
// confirm. Arg: site name (default "HQ").
module.exports = async (s, ui, name = 'HQ') => {
  await ui.go(s, '/new-alarms');
  await ui.click(s.page, 'Search', { wait: 3000 });
  await ui.click(s.page, name, { wait: 6000 });
  await ui.click(s.page, 'Settings', { wait: 6000 });
  await ui.click(s.page, 'Remove Site', { wait: 2500 });
  ui.mark(s, `alarm site remove ${name}`);
  await ui.confirm(s.page, ['Confirm']);
};
