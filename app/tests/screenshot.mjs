// Vytvoří snímek aplikace pro dokumentaci (tmavý režim, tablet na šířku):
//   python3 -m http.server 8765 &  node tests/screenshot.mjs ../docs/img/aplikace.png
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const out = process.argv[2] || 'aplikace.png';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1180, height: 820 }, colorScheme: 'dark', deviceScaleFactor: 2 });
await p.goto(process.env.APP_URL || 'http://127.0.0.1:8765/index.html');
await p.click('#dlgHelp button[value="close"]');
const box = await p.locator('#canvas').boundingBox();
const ox = box.x + 330; const oy = box.y + 150;
const path = [[0, 0], [520, 0], [520, 250], [330, 250], [330, 460], [0, 460], [0, 8]];
await p.mouse.move(ox, oy); await p.mouse.down();
for (let i = 0; i < path.length - 1; i++) {
  const [x0, y0] = path[i]; const [x1, y1] = path[i + 1];
  for (let t = 0; t <= 1; t += 0.1) await p.mouse.move(ox + x0 + (x1 - x0) * t, oy + y0 + (y1 - y0) * t);
}
await p.mouse.up();
await p.click('#btnDevice'); await p.click('#btnDemo');
await p.waitForFunction(() => document.querySelector('#btnDevice').classList.contains('connected'));
for (let i = 0; i < 3; i++) { await p.click('#btnMeasure'); await p.waitForTimeout(500); }
await p.waitForTimeout(2800);
await p.screenshot({ path: out });
await b.close();
console.log('uloženo', out);
