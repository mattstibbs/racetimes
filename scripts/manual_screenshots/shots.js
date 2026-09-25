// Takes the user manual's screenshots from a running copy of the app seeded by
// seed.py. Run it with run.sh, which sets everything up and tears it down.
const { chromium } = require('playwright');
const path = require('path');

const BASE = process.env.BASE_URL;
const OUT = process.env.OUT_DIR;
const PASSWORD = 'manual-screenshots-only';

async function logIn(browser, email, viewport = { width: 1000, height: 700 }) {
  const page = await (await browser.newContext({ viewport, locale: 'en-GB' })).newPage();
  await page.goto(`${BASE}/accounts/login/`);
  await page.fill('#id_username', email);
  await page.fill('#id_password', PASSWORD);
  await page.click('form.stacked button[type=submit]');
  await page.waitForLoadState('networkidle');
  return page;
}

const shot = (target, name) => target.screenshot({ path: path.join(OUT, name) });
// A race on the public results page: its heading down to the start of its table.
// The page is at the top, so these boxes are page coordinates; fullPage lets
// the clip reach below the window.
const raceHeader = async (page, number, name) => {
  const top = await page.locator(`#race-${number}`).boundingBox();
  const table = await page.locator(`#race-${number} ~ .table-scroll`).first().boundingBox();
  const clip = { x: 0, y: top.y - 8, width: 1000, height: table.y - top.y + 8 };
  await page.screenshot({ path: path.join(OUT, name), clip, fullPage: true });
};
const card = (page, text) => page.locator('section.card', { hasText: text }).first();

(async () => {
  const browser = await chromium.launch();

  // The committee's view.
  const officer = await logIn(browser, 'officer@example.com');
  await officer.goto(`${BASE}/admin/`);
  await shot(officer.locator('#content'), 'front-page-committee.png');
  await officer.goto(`${BASE}/requests/`);
  await shot(card(officer, 'Register a boat'), 'request-register.png');
  await shot(card(officer, 'Change a boat'), 'request-change.png');
  await shot(card(officer, 'Own a boat on record'), 'request-claim.png');
  await shot(card(officer, 'Enter GBR 42'), 'request-entry.png');

  // Approving the change without a reason, then rejecting the registration.
  // HTMX swaps each card for its updated version, so wait for the new one.
  await card(officer, 'Change a boat').locator('button[value=approve]').click();
  const reasonNeeded = officer.locator('section.card.has-errors', { hasText: 'Change a boat' });
  await reasonNeeded.waitFor();
  await shot(reasonNeeded, 'request-reason-needed.png');
  const register = card(officer, 'Register a boat');
  await register.locator('input[name=note]').fill('Base number does not match the RYA list; please check your certificate.');
  await register.locator('button[value=reject]').click();
  const rejected = officer.locator('section.card.saved', { hasText: 'Register a boat' });
  await rejected.waitFor();
  await shot(rejected, 'request-rejected.png');

  // Finding results, on a phone, as anyone can.
  const phone = await (await browser.newContext({ viewport: { width: 375, height: 700 }, locale: 'en-GB' })).newPage();
  await phone.goto(`${BASE}/`);
  await shot(phone.locator('body'), 'results-home.png');
  await phone.locator('#boat-search').pressSequentially('gbr1234', { delay: 40 });
  await phone.locator('#boat-matches li').first().waitFor();
  await phone.locator('#boat-matches').screenshot({ path: path.join(OUT, 'results-search.png') });
  await phone.goto(`${BASE}/boats/1/`);
  await shot(phone.locator('body'), 'results-boat.png');
  await phone.goto(`${BASE}/series/1/?race=3&boat=1`);
  await shot(phone.locator('body'), 'results-series.png');

  // Publishing results: provisional, then published, then amended by a correction.
  const publicPage = await (await browser.newContext({ viewport: { width: 1000, height: 700 }, locale: 'en-GB' })).newPage();
  await publicPage.goto(`${BASE}/series/1/?race=1`);
  await raceHeader(publicPage, 1, 'results-provisional.png');
  await officer.goto(`${BASE}/series/1/?race=1`);
  await officer.click('#race-1 ~ p.muted >> text=Race day page');
  await officer.waitForLoadState('networkidle');
  await shot(officer.locator('#publishing'), 'publish-provisional.png');
  await officer.click('#publishing button');
  await officer.waitForLoadState('networkidle');
  await shot(officer.locator('.messages'), 'publish-sent.png');
  await publicPage.goto(`${BASE}/series/1/?race=1`);
  await raceHeader(publicPage, 1, 'results-published.png');
  const row = officer.locator('.finished-row', { hasText: 'GBR 42' });
  await row.locator('summary', { hasText: 'Edit' }).click();
  await row.locator('input[type=time]').fill('19:32:10');
  await row.locator('input[name$="-reason"]').fill('Misread the finish sheet');
  await row.locator('button', { hasText: 'Save' }).click();
  const amended = officer.locator('#publishing', { hasText: 'Amended since results were sent' });
  await amended.waitFor();
  await shot(amended, 'publish-amended.png');
  await publicPage.goto(`${BASE}/series/1/?race=1`);
  await raceHeader(publicPage, 1, 'results-amended-since-published.png');

  // Race day for race 4, which seed.py dates today, on a tablet: the start
  // sheet, then tapping Finished, a typed code, and a refused take-off.
  const tablet = await logIn(browser, 'officer@example.com', { width: 768, height: 1024 });
  await tablet.goto(`${BASE}/races/4/?view=start`);
  await tablet.locator('form.start-row', { hasText: 'GBR 7' }).locator('input[type=checkbox]').check();
  await tablet.locator('form.start-row.saved', { hasText: 'GBR 7' }).waitFor();
  await shot(tablet.locator('body'), 'race-day-start-sheet.png');
  await tablet.goto(`${BASE}/races/4/?view=finish`);
  for (const boat of ['GBR 42', 'GBR 1234']) {
    await tablet.locator('.racing-row', { hasText: boat }).locator('button.finished').click();
    await tablet.locator('.finished-row.saved', { hasText: boat }).waitFor();
    await tablet.waitForTimeout(3000);  // boats seconds apart, as on the water
  }
  await shot(tablet.locator('body'), 'race-day-finishing.png');
  const tern = tablet.locator('.racing-row', { hasText: 'GBR 7' });
  await tern.locator('summary').click();
  await tern.locator('select').selectOption('DNF');
  await shot(tern, 'race-day-typed.png');
  await tablet.goto(`${BASE}/races/4/?view=start`);
  await tablet.locator('form.start-row', { hasText: 'GBR 42' }).locator('input[type=checkbox]').uncheck();
  const refused = tablet.locator('form.start-row.has-errors', { hasText: 'GBR 42' });
  await refused.waitFor();
  await shot(refused, 'start-sheet-has-result.png');

  // Ending a series: the Autumn series isn't ready; the Summer one is, and is declared final.
  await officer.goto(`${BASE}/series/1/final/`);
  await shot(officer.locator('#final-state'), 'final-not-ready.png');
  await officer.goto(`${BASE}/series/3/final/`);
  await shot(officer.locator('main'), 'final-ready.png');
  await officer.click('#final-state button');
  await officer.waitForLoadState('networkidle');
  await shot(officer.locator('main'), 'final-declared.png');
  // The public series page, from its title to the end of the final standings.
  await publicPage.goto(`${BASE}/series/3/`);
  const title = await publicPage.locator('main h1').boundingBox();
  const standings = await publicPage.locator('#series-body .table-scroll').first().boundingBox();
  await publicPage.screenshot({
    path: path.join(OUT, 'results-final.png'), fullPage: true,
    clip: { x: 0, y: title.y - 8, width: 1000, height: standings.y + standings.height - title.y + 16 },
  });

  // Forgotten passwords.
  await publicPage.goto(`${BASE}/accounts/password-reset/`);
  await shot(publicPage.locator('body'), 'password-reset.png');

  // What the member sees.
  const sam = await logIn(browser, 'sam@example.com');
  await sam.goto(`${BASE}/my/boats/`);
  await shot(sam.locator('table').first(), 'member-request-status.png');

  // The administrator's view.
  const admin = await logIn(browser, 'admin@example.com');
  await admin.goto(`${BASE}/admin/`);
  await shot(admin.locator('.messagelist'), 'front-page-administrator.png');
  await admin.goto(`${BASE}/admin/auth/user/?approval=waiting`);
  await shot(admin.locator('#content'), 'accounts-waiting.png');

  await browser.close();
  console.log(`Screenshots written to ${OUT}`);
})().catch((error) => { console.error(error); process.exit(1); });
