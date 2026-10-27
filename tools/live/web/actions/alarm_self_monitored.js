// Pick the Self-Monitored response level: Alarms → Search → site → Response
// → Response Level dropdown → Self-Monitored. Never selects any other level
// (owner's rule); options are only printed. Arg: site ("HQ").
module.exports = async (s, ui, site = 'HQ') => {
  await ui.go(s, '/new-alarms');
  await ui.click(s.page, 'Search', { wait: 3000 });
  await ui.click(s.page, site, { wait: 6000 });
  await s.page.getByRole('link', { name: 'Response' }).first().click();
  await s.page.waitForTimeout(8000);
  const current = s.page.getByText('Self-Monitored', { exact: true }).first();
  await current.click();
  await s.page.waitForTimeout(2000);
  // The option is the card that says "No Verkada monitoring"; the button
  // showing the current level has the same label.
  const pick = s.page.locator('div').filter({ hasText: /^Self-MonitoredNo Verkada monitoring/ }).last();
  if (!(await pick.count())) throw new Error('Self-Monitored option not found; nothing selected');
  ui.mark(s, 'alarm.site.set_self_monitored');
  await pick.click();
  await s.page.waitForTimeout(3000);
  for (const b of ['Confirm', 'Save', 'Yes']) { try { await ui.clickLast(s.page, b, { wait: 3000 }); break; } catch {} }
  console.log('now:', s.red(await s.page.locator('main').first().innerText()).match(/Response Level\s+(\S+)/)?.[1]);
};
