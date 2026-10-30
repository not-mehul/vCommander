// Show, and with SELECT=1 pick, the output devices a response activates:
// Alarms → Search → site → Response → output devices → the strobe → Save.
// Never changes the response level. Args: site ("HQ"), output ("Strobe Light").
module.exports = async (s, ui, site = 'HQ', output = 'Strobe Light') => {
  await ui.go(s, '/new-alarms');
  await ui.click(s.page, 'Search', { wait: 3000 });
  await ui.click(s.page, site, { wait: 6000 });
  await s.page.getByRole('link', { name: 'Response' }).first().click();
  await s.page.waitForTimeout(8000);
  await ui.click(s.page, 'Automated Alarm Actions', { wait: 5000 });
  await ui.click(s.page, 'Output devices will be activated', { wait: 5000 });
  console.log(s.red((await s.page.locator('body').ariaSnapshot()).split('\n').filter(l => /output|strobe|siren|checkbox|switch|Save|Apply|Done|Edit|Add|dialog|heading/i.test(l)).slice(0, 40).join('\n')));
  await ui.shot(s, 'alarm_response_output-before');
  if (!process.env.SELECT) return;
  // The output's row holds its name and a "Toggle output device" switch.
  const row = s.page.locator('div').filter({ hasText: new RegExp(`^${output}`) })
    .filter({ has: s.page.getByRole('button', { name: 'Toggle output device' }) }).last();
  ui.mark(s, `alarm.response.outputs ${output}`);
  await row.getByRole('button', { name: 'Toggle output device' }).click();
  await s.page.waitForTimeout(4000);
  for (const b of ['Save', 'Apply', 'Done', 'Confirm']) { try { await ui.clickLast(s.page, b, { wait: 4000 }); break; } catch {} }
  await s.page.waitForTimeout(3000);
  await ui.go(s, s.page.url().replace(/^https:\/\/[^/]+/, ''));
  await ui.click(s.page, 'Automated Alarm Actions', { wait: 5000 });
  console.log('after:', s.red((await s.page.locator('main').first().innerText()).replace(/\s+/g, ' ').slice(0, 300)));
};
