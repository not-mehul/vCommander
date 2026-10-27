// Create an alarm site with a software trial: Alarms → Get Started / Add
// Site → site, alarm admin contact (first user offered), business name,
// address (first suggestion) → Start a trial.
// Args: site ("HQ"), business name ("Verkada"), address.
module.exports = async (s, ui, site = 'HQ', business = 'Verkada', address = '406 E 3rd Ave, San Mateo, CA 94401') => {
  await ui.go(s, '/new-alarms/onboarding/site');
  await s.page.getByRole('textbox', { name: 'Select a Site' }).click();
  await s.page.waitForTimeout(1500);
  await s.page.getByRole('menuitem', { name: site, exact: true }).click();
  await s.page.waitForTimeout(2500);
  await s.page.getByRole('textbox', { name: 'Alarm admin contact' }).click();
  await s.page.waitForTimeout(2000);
  await s.page.getByRole('menuitem').or(s.page.getByRole('option')).first().click();
  await s.page.waitForTimeout(1000);
  await s.page.getByRole('textbox', { name: 'Business name' }).fill(business);
  await s.page.getByRole('textbox', { name: 'Add an address' }).click();
  await ui.pickAddress(s.page, address);
  console.log((await ui.tree(s, { lines: 400 })).split('\n').filter(l => /textbox|Start a trial/.test(l) && !/admin contact/.test(l)).join('\n'));
  ui.mark(s, `alarm.site.create ${site}`);
  await ui.click(s.page, 'Start a trial', { wait: 10000 });
  console.log((await ui.tree(s, { root: 'main', lines: 40 })));
};
