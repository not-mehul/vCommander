// Delete a door schedule: Access → Schedules → the row's Delete Schedule
// (trash) button → confirm. Arg: a fragment of the schedule name ("AF64 2FA").
module.exports = async (s, ui, name = 'AF64 2FA') => {
  await ui.go(s, '/access/schedules');
  const row = s.page.getByRole('row').filter({ hasText: name }).first();
  await row.getByRole('button', { name: 'Delete Schedule' }).click();
  await s.page.waitForTimeout(2000);
  console.log((await ui.tree(s, { lines: 600 })).split('\n').filter(l => /dialog|heading|button "(Delete|Cancel|Confirm|Yes)/.test(l)).slice(-8).join('\n'));
  ui.mark(s, `schedule.delete ${name}`);
  await ui.confirm(s.page, ['Delete', 'Confirm', 'Yes']);
};
