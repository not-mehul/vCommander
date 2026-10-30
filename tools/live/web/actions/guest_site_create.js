// Enable Guest on an existing site: Guest Settings → Add Site → site → follow
// the dialog to its end (address suggestion if asked, then the last
// Add/Save/Create/Next/Done/Start Trial button each step).
// Arg: site name ("HQ").
module.exports = async (s, ui, site = 'HQ', address = '406 E 3rd Ave, San Mateo, CA 94401') => {
  await ui.go(s, '/guest/settings');
  await ui.click(s.page, 'Add Site', { wait: 2000 });
  ui.mark(s, `guest.create ${site}`);
  await ui.click(s.page, site, { within: s.page.getByRole('dialog'), wait: 4000 });
  for (let step = 0; step < 4; step++) {
    const dlg = s.page.getByRole('dialog').last();
    if (!(await dlg.count())) break;
    console.log(`step ${step}:`, s.red(await dlg.ariaSnapshot()).split('\n').filter(l => /textbox|button|switch|heading|radio|checkbox/.test(l)).join(' | ').slice(0, 600));
    const addr = dlg.getByRole('textbox', { name: /address/i });
    if (await addr.count() && !(await addr.first().inputValue())) { await addr.first().click(); await ui.pickAddress(s.page, address); }
    let clicked = false;
    for (const b of ['Start Trial', 'Start a trial', 'Create', 'Add', 'Save', 'Next', 'Done', 'Continue']) {
      try { await ui.clickLast(s.page, b, { wait: 5000 }); clicked = true; break; } catch {}
    }
    if (!clicked) break;
  }
};
