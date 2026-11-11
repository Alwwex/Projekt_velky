// End-to-end test aplikace v Chromiu (Playwright):
//   cd app && python3 -m http.server 8765 &   node tests/e2e.mjs
// Nakreslí L-místnost myší, připojí demo laser a "změří" všechny stěny.
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const URL = process.env.APP_URL || 'http://127.0.0.1:8765/index.html';
const OUT = process.env.OUT_DIR || '.';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1180, height: 820 }, deviceScaleFactor: 1 });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

await page.goto(URL);
await page.waitForSelector('#dlgHelp[open]');
await page.screenshot({ path: `${OUT}/e2e-0-help.png` });
await page.click('#dlgHelp button[value="close"]');

// L-tvar roztřeseným tahem
const box = await page.locator('#canvas').boundingBox();
const ox = box.x + 330; const oy = box.y + 170;
const path = [[0, 0], [480, 0], [480, 240], [300, 240], [300, 420], [0, 420], [0, 10]];
await page.mouse.move(ox, oy);
await page.mouse.down();
for (let i = 0; i < path.length - 1; i++) {
  const [x0, y0] = path[i]; const [x1, y1] = path[i + 1];
  for (let t = 0; t <= 1; t += 0.08) {
    const j = () => (Math.random() - 0.5) * 8;
    await page.mouse.move(ox + x0 + (x1 - x0) * t + j(), oy + y0 + (y1 - y0) * t + j());
  }
}
await page.mouse.up();
await page.waitForTimeout(300);

const walls = await page.evaluate(() => window.laserplan.state.plan.rooms[0]?.walls.map((w) => w.ang));
console.log('rozpoznané stěny (úhly):', walls);
if (!walls || walls.length !== 6) throw new Error(`čekal jsem 6 stěn, mám ${walls?.length}`);
await page.screenshot({ path: `${OUT}/e2e-1-sketch.png` });

// demo laser
await page.click('#btnDevice');
await page.click('#btnDemo');
await page.waitForFunction(() => document.querySelector('#btnDevice').classList.contains('connected'));

// měř, dokud aplikace sama vybírá další stěnu
for (let i = 0; i < 8; i++) {
  const sel = await page.evaluate(() => window.laserplan.state.selWall);
  if (!sel) break;
  await page.click('#btnMeasure');
  await page.waitForTimeout(500);
  if (i === 1) await page.screenshot({ path: `${OUT}/e2e-2-measuring.png` });
}
const res = await page.evaluate(() => {
  const r = window.laserplan.state.plan.rooms[0];
  return { states: r.walls.map((w) => w.state), info: document.querySelector('#roomInfo').innerText };
});
console.log('stavy stěn:', res.states.join(', '));
console.log('info:', res.info.replace(/\n/g, ' | '));
await page.screenshot({ path: `${OUT}/e2e-3-done.png` });

// telefon na výšku
await page.setViewportSize({ width: 390, height: 780 });
await page.click('#btnFit');
await page.waitForTimeout(200);
await page.screenshot({ path: `${OUT}/e2e-4-phone.png` });

// export SVG (stažení)
await page.setViewportSize({ width: 1180, height: 820 });
await page.click('#btnMenu');
const [dl] = await Promise.all([page.waitForEvent('download'), page.click('[data-act="svg"]')]);
console.log('export:', dl.suggestedFilename());

await browser.close();
if (errors.length) { console.error('CHYBY V KONZOLI:', errors); process.exit(1); }
if (!/hotovo/.test(res.info)) { console.error('místnost není hotová'); process.exit(1); }
console.log('E2E OK');
