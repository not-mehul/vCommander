// Add a partition: Alarms → site → Partitions → Add partition → name →
// through the dialog (cameras ticked; steps printed). Args: site ("HQ"), name ("Web Partition").
module.exports = async (s, ui, site = 'HQ', name = 'Web Partition') => {
  await ui.go(s, '/new-alarms');
  await ui.click(s.page, 'Search', { wait: 3000 });
  await ui.click(s.page, site, { wait: 6000 });
  await s.page.getByRole('link', { name: 'Partitions' }).first().click();
  await s.page.waitForTimeout(5000);
  await ui.click(s.page, 'Add partition', { wait: 2500 });
  ui.mark(s, `alarm.partition.create ${name}`);
  for (let step = 0; step < 5; step++) {
    const d = s.page.getByRole('dialog').last();
    const scope = (await d.count()) && (await d.isVisible()) ? d : s.page.locator('main');
    // Camera step: tick every camera offered.
    for (const cb of await scope.getByRole('checkbox').all()) if (!(await cb.isChecked())) await cb.locator('xpath=..').click().catch(() => {});
    const nm = scope.getByRole('textbox', { name: /name/i }).or(scope.getByRole('textbox').first());
    if (await nm.count() && !(await nm.first().inputValue())) await nm.first().fill(name);
    console.log(`step ${step}:`, s.red(await scope.ariaSnapshot()).split('\n').filter(l => /heading|textbox|switch|checkbox|button "(Next|Save|Create|Add|Done)/.test(l)).join(' | ').slice(0, 500));
    let clicked = false;
    for (const b of ['Next Step', 'Next', 'Create Partition', 'Create', 'Save', 'Add', 'Done']) { try { await ui.clickLast(s.page, b, { wait: 3500 }); clicked = true; break; } catch {} }
    if (!clicked) break;
  }
};
