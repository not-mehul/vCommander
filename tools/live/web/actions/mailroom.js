// Mailroom: activate the trial if offered, then create a mailroom site
// (location: the Command site if offered, else the address; name
// "<site> Mailroom"). Arg: site ("HQ").
module.exports = async (s, ui, site = 'HQ') => {
  await ui.go(s, '/mailroom');
  const trial = s.page.getByRole('button', { name: 'Activate your 60-day trial' });
  if (await trial.count()) {
    ui.mark(s, 'mailroom.activate_trial');
    await trial.click();
    await s.page.waitForTimeout(4000);
    for (const b of ['Activate', 'Start Trial', 'Confirm', 'Continue', 'Get Started']) { try { await ui.clickLast(s.page, b, { wait: 4000 }); break; } catch {} }
    await s.page.waitForTimeout(4000);
  }
  const where = s.page.getByRole('textbox', { name: 'Where is this site located?' });
  if (await where.count()) {
    await where.click();
    await s.page.waitForTimeout(1500);
    const opts = s.page.getByRole('option').or(s.page.getByRole('menuitem'));
    console.log('locations offered:', (await opts.allInnerTexts()).join(' | ').slice(0, 300));
    if (await opts.count()) await opts.filter({ hasText: site }).first().click();
    else await ui.pickAddress(s.page, '406 E 3rd Ave, San Mateo, CA 94401');
    await s.page.getByRole('textbox', { name: 'Please name this site.' }).fill(`${site} Mailroom`);
    ui.mark(s, `mailroom.create ${site}`);
    await ui.clickLast(s.page, 'Create', { wait: 6000 });
  }
  console.log((await ui.tree(s, { root: 'body', lines: 600 })).split('\n').filter(l => /heading|button|dialog|textbox/.test(l) && !/@/.test(l)).slice(-15).join('\n'));
};
