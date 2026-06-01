// Capture documentation screenshots of the running IPForge UI.
//
// Prerequisites (not part of the app's deps — install on demand):
//   npm i -D playwright && npx playwright install chromium
//
// Then, with the demo API (scripts/serve_demo.py) on :8000 and the Vite dev
// server (npm run dev) on :5173:
//   node capture_screenshots.mjs
//
// Logs in via the API, injects the JWT into localStorage, forces the light
// theme, and screenshots each target page into ../docs/screenshots/.
// See docs/screenshots/README.md for the full regeneration procedure.
import { chromium } from 'playwright';
import { mkdirSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT = join(__dirname, '..', 'docs', 'screenshots');
const BASE = 'http://localhost:5173';
const API = 'http://127.0.0.1:8000';

mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 2,
});

// Authenticate via the API and grab a JWT.
const res = await context.request.post(`${API}/api/auth/login`, {
  form: { username: 'admin', password: 'admin' },
});
const { access_token } = await res.json();

// Inject token + light theme before any app script runs, on every navigation.
await context.addInitScript(([token]) => {
  localStorage.setItem('ipam_token', token);
  localStorage.setItem('ipam_user', JSON.stringify({ username: 'admin', role: 'admin' }));
  localStorage.setItem('theme', 'light');
}, [access_token]);

const page = await context.newPage();

async function shot(path, name, { fullPage = true, wait = 900, click = null } = {}) {
  await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(wait);
  if (click) {
    await click(page);
    await page.waitForTimeout(1200);
  }
  await page.screenshot({ path: join(OUT, `${name}.png`), fullPage });
  console.log(`captured ${name}.png`);
}

await shot('/', '01-dashboard', { fullPage: false });            // hero, above-the-fold
await shot('/subnets', '02-subnets', {});
await shot('/subnets', '03-subnet-map', {
  fullPage: false,
  click: async (p) => { await p.locator('tr.clickable', { hasText: 'Servers' }).first().click(); },
});
await shot('/addresses', '04-addresses', { fullPage: false });
await shot('/drift', '05-drift', {});
await shot('/settings', '06-settings-providers', {});
await shot('/security', '07-security', { fullPage: false });
await shot('/gitops', '08-gitops', {});

await browser.close();
console.log(`\nDone -> ${OUT}`);
