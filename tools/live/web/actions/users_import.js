// Import users from a CSV: Access → Users → Import → Import Users → upload →
// Configure ("No, do not overwrite existing users") / Review Columns /
// Review Rows → Import. Steps printed.
// Arg: path to the CSV (firstName,lastName,email; keep it outside the repo).
module.exports = async (s, ui, csv) => {
  await ui.go(s, '/access/users');
  await ui.click(s.page, 'Import', { wait: 1500 });
  await ui.click(s.page, 'Import Users', { wait: 3000 });
  await s.page.locator('input[type=file]').first().setInputFiles(csv);
  await s.page.waitForTimeout(3000);
  ui.mark(s, 'users import');
  for (let step = 0; step < 8; step++) {
    const text = s.red(await s.page.locator('body').innerText()).replace(/[\w.+-]+@[\w.-]+/g, '<email>');
    const heading = (text.match(/(Upload|Configure|Review Columns|Review Rows|Import)[^\n]*\n/g) || []).slice(0, 1).join('');
    const buttons = (await s.page.getByRole('button').allInnerTexts()).filter(b => /Continue|Next|Import|Confirm|Done|Finish/.test(b));
    console.log(`step ${step}:`, heading.trim(), '| buttons:', buttons.join(', '));
    // Configure: never overwrite existing users.
    const noOverwrite = s.page.getByText('No, do not overwrite existing users', { exact: true });
    if (await noOverwrite.count()) { await noOverwrite.click(); await s.page.waitForTimeout(800); }
    let clicked = false;
    for (const b of ['Continue', 'Next[\\w, ]*', 'Proceed with Import', 'Import Users', 'Import[\\w ]*', 'Confirm', 'Done', 'Finish']) {
      try { await ui.clickLast(s.page, b, { wait: 4000 }); clicked = true; break; } catch {}
    }
    if (!clicked) break;
  }
};
