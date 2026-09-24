// Takes the user manual's screenshots from a running copy of the app seeded by
// seed.py. Run it with run.sh, which sets everything up and tears it down.
const { chromium } = require('playwright');
const path = require('path');

const BASE = process.env.BASE_URL;
const OUT = process.env.OUT_DIR;
const PASSWORD = 'manual-screenshots-only';

async function logIn(browser, email) {
  const page = await (await browser.newContext({ viewport: { width: 1000, height: 700 }, locale: 'en-GB' })).newPage();
  await page.goto(`${BASE}/accounts/login/`);
  await page.fill('#id_username', email);
  await page.fill('#id_password', PASSWORD);
  await page.click('form.stacked button[type=submit]');
  await page.waitForLoadState('networkidle');
  return page;
}

const shot = (target, name) => target.screenshot({ path: path.join(OUT, name) });
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

  // Publishing results: provisional, then published, then amended by a correction.
  const publicPage = await (await browser.newContext({ viewport: { width: 1000, height: 700 }, locale: 'en-GB' })).newPage();
  await publicPage.goto(`${BASE}/series/1/`);
  await shot(publicPage.locator('#race-1'), 'results-provisional.png');
  await officer.goto(`${BASE}/series/1/`);
  await officer.click('#race-1 + p >> text=Enter finishes');
  await officer.waitForLoadState('networkidle');
  await shot(officer.locator('#publishing'), 'publish-provisional.png');
  await officer.click('#publishing button');
  await officer.waitForLoadState('networkidle');
  await shot(officer.locator('.messages'), 'publish-sent.png');
  const row = officer.locator('form.finish-row', { hasText: 'GBR 42' });
  await row.locator('input[type=time]').fill('19:32:10');
  await row.locator('input[name$="-reason"]').fill('Misread the finish sheet');
  await row.locator('button').click();
  const amended = officer.locator('#publishing', { hasText: 'Amended since results were sent' });
  await amended.waitFor();
  await shot(amended, 'publish-amended.png');

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
