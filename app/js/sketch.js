// Rozpoznání ručně kresleného tahu -> rovné stěny s "chytrými" úhly.
//
//   body tahu  ->  zjednodušení (Ramer–Douglas–Peucker)
//              ->  přichycení směrů na 90° (nebo 45°)
//              ->  sloučení navazujících stejných směrů
//              ->  uzavření obrysu (pokud konec je blízko začátku)

export function rdp(points, eps) {
  if (points.length < 3) return points.slice();
  const keep = new Uint8Array(points.length);
  keep[0] = 1; keep[points.length - 1] = 1;
  const stack = [[0, points.length - 1]];
  while (stack.length) {
    const [s, e] = stack.pop();
    const a = points[s]; const b = points[e];
    let idx = -1; let dmax = 0;
    for (let i = s + 1; i < e; i++) {
      const d = perpDist(points[i], a, b);
      if (d > dmax) { dmax = d; idx = i; }
    }
    if (dmax > eps && idx > 0) {
      keep[idx] = 1;
      stack.push([s, idx], [idx, e]);
    }
  }
  return points.filter((_, i) => keep[i]);
}

function perpDist(p, a, b) {
  const dx = b.x - a.x; const dy = b.y - a.y;
  const L = Math.hypot(dx, dy);
  if (L < 1e-9) return Math.hypot(p.x - a.x, p.y - a.y);
  return Math.abs((p.x - a.x) * dy - (p.y - a.y) * dx) / L;
}

/** Přichytí úhel (°) – přednost mají násobky 90°, jinak 45°. */
export function snapAngle(deg, { allow45 = true, tol90 = 22 } = {}) {
  const norm = ((deg % 360) + 360) % 360;
  const n90 = Math.round(norm / 90) * 90;
  if (!allow45 || Math.abs(norm - n90) <= tol90) return n90 % 360;
  return (Math.round(norm / 45) * 45) % 360;
}

const angDiff = (a, b) => Math.abs(((a - b + 540) % 360) - 180);

/**
 * Převede tah (body ve světových mm) na stěny.
 * @param {Array<{x,y}>} pts  body tahu (mm)
 * @param {number} pxPerMm    aktuální měřítko zobrazení (kvůli tolerancím v px)
 * @returns {null | {origin, walls:[{ang,len}], closed}}
 */
export function recognizeStroke(pts, pxPerMm, opts = {}) {
  if (pts.length < 2) return null;
  const toPx = (mm) => mm * pxPerMm;
  // velikost tahu
  const xs = pts.map((p) => p.x); const ys = pts.map((p) => p.y);
  const diag = Math.hypot(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
  if (toPx(diag) < 25) return null;                       // jen ťuknutí
  const epsPx = Math.max(9, Math.min(28, toPx(diag) * 0.045));
  let poly = rdp(pts, epsPx / pxPerMm);
  // uzavřený?
  const first = pts[0]; const last = pts[pts.length - 1];
  const gap = Math.hypot(last.x - first.x, last.y - first.y);
  let closed = toPx(gap) < Math.max(36, toPx(diag) * 0.18) && poly.length >= 4;
  if (closed) {
    poly = poly.slice(0, -1);
    poly.push({ ...poly[0] });
  }
  // segmenty
  let segs = [];
  for (let i = 0; i < poly.length - 1; i++) {
    const a = poly[i]; const b = poly[i + 1];
    const dx = b.x - a.x; const dy = b.y - a.y;
    const L = Math.hypot(dx, dy);
    if (L < 1e-6) continue;
    const raw = (Math.atan2(dy, dx) * 180) / Math.PI;
    const ang = snapAngle(raw, opts);
    const r = (ang * Math.PI) / 180;
    segs.push({ ang, len: dx * Math.cos(r) + dy * Math.sin(r) });
  }
  const total = segs.reduce((s, x) => s + Math.abs(x.len), 0);
  // odstranit drobnosti a sloučit stejné směry
  for (let pass = 0; pass < 4; pass++) {
    segs = segs.filter((s) => Math.abs(s.len) > total * 0.03);
    const merged = [];
    for (const s of segs) {
      const prev = merged[merged.length - 1];
      if (prev && angDiff(prev.ang, s.ang) < 1) prev.len += s.len;
      else if (prev && angDiff(prev.ang, s.ang) > 179) prev.len -= s.len;   // vratný tah
      else merged.push({ ...s });
    }
    if (closed && merged.length > 1 && angDiff(merged[0].ang, merged[merged.length - 1].ang) < 1) {
      merged[0].len += merged.pop().len;
    }
    segs = merged.map((s) => (s.len < 0 ? { ang: (s.ang + 180) % 360, len: -s.len } : s));
  }
  if (closed && segs.length < 3) closed = false;
  if (!segs.length) return null;
  return {
    origin: { x: poly[0].x, y: poly[0].y },
    walls: segs.map((s) => ({ ang: s.ang, len: s.len })),
    closed,
  };
}
