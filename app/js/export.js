// Export půdorysu: SVG, PNG, DXF (R12), JSON
import {
  area, centroid, orientation, planBounds, vertices,
} from './plan.js';
import { formatArea, formatLength } from './units.js';

function download(name, blob) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  // kotvu nepřidáváme do <body> – při otevřeném modálním dialogu je body "inert"
  (document.querySelector('dialog[open]') || document.body).appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

// název souboru bez diakritiky (některé prohlížeče jinak soubor přejmenují na "download")
const safeName = (s) => (s || 'pudorys').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
  .replace(/[^A-Za-z0-9_-]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 50) || 'pudorys';
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/** SVG v měřítku (1 jednotka = 1 mm), světlý vzhled pro tisk. */
export function toSVG(plan, units) {
  const b = planBounds(plan) || { x0: 0, y0: 0, x1: 1000, y1: 1000 };
  const size = Math.max(b.x1 - b.x0, b.y1 - b.y0);
  const pad = size * 0.12 + 400;
  const x0 = b.x0 - pad; const y0 = b.y0 - pad - size * 0.06;
  const W = b.x1 - b.x0 + pad * 2; const H = b.y1 - b.y0 + pad * 2 + size * 0.06;
  const fs = Math.max(90, size / 45);
  const out = [];
  out.push(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="${x0} ${y0} ${W} ${H}" width="${Math.round(W / 10)}mm" height="${Math.round(H / 10)}mm">`);
  out.push(`<rect x="${x0}" y="${y0}" width="${W}" height="${H}" fill="#fff"/>`);
  out.push(`<text x="${x0 + pad / 3}" y="${y0 + fs * 1.6}" font-family="sans-serif" font-size="${fs * 1.3}" font-weight="700" fill="#111">${esc(plan.name)}</text>`);
  for (const room of plan.rooms) {
    const v = vertices(room);
    const pts = v.slice(0, room.closed ? -1 : undefined).map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
    out.push(room.closed
      ? `<polygon points="${pts}" fill="#eef2ff" stroke="#111" stroke-width="${fs / 5}" stroke-linejoin="round"/>`
      : `<polyline points="${pts}" fill="none" stroke="#111" stroke-width="${fs / 5}" stroke-linejoin="round"/>`);
    const orient = room.closed ? orientation(room) : 1;
    room.walls.forEach((w, i) => {
      const a = v[i]; const c = v[i + 1];
      const L = Math.hypot(c.x - a.x, c.y - a.y);
      if (L < 1) return;
      let nx = (c.y - a.y) / L; let ny = -(c.x - a.x) / L;
      if (orient < 0) { nx = -nx; ny = -ny; }
      const off = fs * 1.2;
      const mx = (a.x + c.x) / 2 + nx * off; const my = (a.y + c.y) / 2 + ny * off;
      let ang = (Math.atan2(c.y - a.y, c.x - a.x) * 180) / Math.PI;
      if (ang > 90 || ang < -90) ang += 180;
      const col = w.state === 'measured' ? '#1d3fd8' : w.state === 'computed' ? '#5570e0' : '#888';
      const pre = w.state === 'estimate' ? '≈ ' : w.state === 'computed' ? '= ' : '';
      out.push(`<text x="${mx}" y="${my}" transform="rotate(${ang} ${mx} ${my})" text-anchor="middle" dominant-baseline="middle" font-family="sans-serif" font-size="${fs}" font-weight="600" fill="${col}">${esc(pre + formatLength(w.len, units))}</text>`);
    });
    if (room.closed) {
      const c = centroid(room);
      if (room.name) out.push(`<text x="${c.x}" y="${c.y - fs * 0.8}" text-anchor="middle" font-family="sans-serif" font-size="${fs * 1.1}" font-weight="700" fill="#111">${esc(room.name)}</text>`);
      out.push(`<text x="${c.x}" y="${c.y + fs * 0.6}" text-anchor="middle" font-family="sans-serif" font-size="${fs}" fill="#444">${esc(formatArea(area(room), units))}</text>`);
    }
  }
  out.push(`<text x="${x0 + pad / 3}" y="${y0 + H - fs}" font-family="sans-serif" font-size="${fs * 0.7}" fill="#888">LaserPlan · ${new Date().toLocaleDateString('cs-CZ')} · modře = naměřeno, = dopočteno, ≈ odhad</text>`);
  out.push('</svg>');
  return out.join('\n');
}

export function exportSVG(plan, units) {
  download(`${safeName(plan.name)}.svg`, new Blob([toSVG(plan, units)], { type: 'image/svg+xml' }));
}

export async function exportPNG(plan, units) {
  const svg = toSVG(plan, units);
  const img = new Image();
  const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
  await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = url; });
  const vb = svg.match(/viewBox="([^"]+)"/)[1].split(' ').map(Number);
  const scale = 2400 / Math.max(vb[2], vb[3]);
  const c = document.createElement('canvas');
  c.width = Math.round(vb[2] * scale); c.height = Math.round(vb[3] * scale);
  c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
  URL.revokeObjectURL(url);
  c.toBlob((b) => download(`${safeName(plan.name)}.png`, b), 'image/png');
}

/** DXF R12 – stěny jako LINE (mm, osa Y nahoru), kóty jako TEXT. */
export function toDXF(plan, units) {
  const L = ['0', 'SECTION', '2', 'HEADER', '9', '$INSUNITS', '70', '4', '0', 'ENDSEC',
    '0', 'SECTION', '2', 'ENTITIES'];
  for (const room of plan.rooms) {
    const v = vertices(room);
    room.walls.forEach((w, i) => {
      const a = v[i]; const b = v[i + 1];
      L.push('0', 'LINE', '8', 'STENY', '10', a.x.toFixed(2), '20', (-a.y).toFixed(2), '30', '0',
        '11', b.x.toFixed(2), '21', (-b.y).toFixed(2), '31', '0');
      const mx = (a.x + b.x) / 2; const my = -(a.y + b.y) / 2;
      L.push('0', 'TEXT', '8', 'KOTY', '10', mx.toFixed(2), '20', my.toFixed(2), '30', '0', '40', '80',
        '1', formatLength(w.len, units).replace('≈', '~'));
    });
  }
  L.push('0', 'ENDSEC', '0', 'EOF');
  return L.join('\r\n');
}

export function exportDXF(plan, units) {
  download(`${safeName(plan.name)}.dxf`, new Blob([toDXF(plan, units)], { type: 'application/dxf' }));
}

export function exportJSON(plan) {
  download(`${safeName(plan.name)}.json`, new Blob([JSON.stringify(plan, null, 2)], { type: 'application/json' }));
}
