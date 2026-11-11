// Model půdorysu a geometrický "řešič".
//
// Místnost = posloupnost stěn. Každá stěna má pevný SMĚR (úhel ve stupních,
// osa y míří dolů) a DÉLKU v mm. Délka je buď:
//   measured  – naměřená laserem / zadaná ručně (pevná),
//   computed  – jednoznačně dopočítaná z uzavření obrysu,
//   estimate  – odhad z náčrtu (mění se, aby obrys "seděl").
//
// Uzavřená místnost musí splnit  Σ Lᵢ·dᵢ = 0.  Neznámé délky hledáme tak,
// aby se co nejméně (relativně) lišily od náčrtu – řešení přes Lagrangeovy
// multiplikátory (2×2 soustava).

let _id = 1;
export const uid = (p = 'id') => `${p}${Date.now().toString(36)}${(_id++).toString(36)}`;

export const rad = (deg) => (deg * Math.PI) / 180;
export const dirOf = (ang) => ({ x: Math.cos(rad(ang)), y: Math.sin(rad(ang)) });

export function createPlan(name = 'Nový půdorys') {
  return { version: 1, id: uid('p'), name, created: Date.now(), modified: Date.now(), rooms: [] };
}

export function createRoom({ origin, walls, closed = true, name }) {
  return {
    id: uid('r'),
    name: name || '',
    closed,
    origin: { ...origin },
    walls: walls.map((w) => ({
      id: uid('w'),
      ang: w.ang,
      sketch: w.len,          // délka z náčrtu (mm) – referenční proporce
      len: w.len,             // aktuální délka (mm)
      state: w.state || 'estimate',
    })),
  };
}

/** Vrcholy místnosti (mm). Pro uzavřenou n stěn -> n+1 bodů (poslední ≈ první). */
export function vertices(room) {
  const pts = [{ ...room.origin }];
  let { x, y } = room.origin;
  for (const w of room.walls) {
    const d = dirOf(w.ang);
    x += d.x * w.len;
    y += d.y * w.len;
    pts.push({ x, y });
  }
  return pts;
}

export function closureError(room) {
  const v = vertices(room);
  const a = v[0];
  const b = v[v.length - 1];
  return Math.hypot(b.x - a.x, b.y - a.y);
}

/** Povolená chyba uzavření: 10 mm nebo 0,2 % obvodu (reálné zdi nejsou přesně kolmé). */
export function closureTolerance(room) {
  return Math.max(10, 0.002 * room.walls.reduce((s, w) => s + w.len, 0));
}

export function area(room) {
  if (!room.closed) return 0;
  const v = vertices(room);
  let s = 0;
  for (let i = 0; i < v.length - 1; i++) s += v[i].x * v[i + 1].y - v[i + 1].x * v[i].y;
  return Math.abs(s) / 2;
}

export function perimeter(room) {
  return room.walls.reduce((s, w) => s + w.len, 0);
}

export function centroid(room) {
  const v = vertices(room).slice(0, -1);
  let a = 0; let cx = 0; let cy = 0;
  for (let i = 0; i < v.length; i++) {
    const p = v[i]; const q = v[(i + 1) % v.length];
    const c = p.x * q.y - q.x * p.y;
    a += c; cx += (p.x + q.x) * c; cy += (p.y + q.y) * c;
  }
  if (Math.abs(a) < 1e-6) {
    const n = v.length || 1;
    return { x: v.reduce((s, p) => s + p.x, 0) / n, y: v.reduce((s, p) => s + p.y, 0) / n };
  }
  return { x: cx / (3 * a), y: cy / (3 * a) };
}

/** +1 = vrcholy po směru hodinových ručiček na obrazovce (y dolů), -1 = proti. */
export function orientation(room) {
  const v = vertices(room).slice(0, -1);
  let s = 0;
  for (let i = 0; i < v.length; i++) {
    const p = v[i]; const q = v[(i + 1) % v.length];
    s += p.x * q.y - q.x * p.y;
  }
  return s >= 0 ? 1 : -1;
}

const isFixed = (w) => w.state === 'measured';

/**
 * Přepočítá délky odhadovaných stěn.
 * 1) Globální měřítko: odhady se přeškálují podle poměru naměřené/náčrt.
 * 2) Uzavření obrysu s minimální relativní změnou odhadů.
 * 3) Označí stěny, jejichž délka je uzavřením určena jednoznačně ("computed").
 * Vrací { error } – zbytková chyba uzavření v mm (0 = sedí).
 */
export function solveRoom(room) {
  const walls = room.walls;
  const fixed = walls.filter(isFixed);
  // 1) měřítko
  let scale = 1;
  if (fixed.length) {
    let num = 0; let den = 0;
    for (const w of fixed) { num += w.len * w.sketch; den += w.sketch * w.sketch; }
    if (den > 0) scale = num / den;
  }
  const free = walls.filter((w) => !isFixed(w));
  for (const w of free) { w.len = w.sketch * scale; w.state = 'estimate'; }
  if (!room.closed || !free.length) {
    return { error: room.closed ? closureError(room) : 0 };
  }
  // 2) uzavření:  Σ_free Lᵢ dᵢ = r,  r = -Σ_fixed Lᵢ dᵢ
  let rx = 0; let ry = 0;
  for (const w of fixed) { const d = dirOf(w.ang); rx -= w.len * d.x; ry -= w.len * d.y; }
  // váha 1/L⁰ -> Lᵢ = L⁰ᵢ + L⁰ᵢ (dᵢ·λ)
  let a = 0; let b = 0; let c = 0; let ex = rx; let ey = ry;
  for (const w of free) {
    const d = dirOf(w.ang);
    const L0 = Math.max(w.len, 1);
    a += L0 * d.x * d.x; b += L0 * d.x * d.y; c += L0 * d.y * d.y;
    ex -= w.len * d.x; ey -= w.len * d.y;
  }
  const det = a * c - b * b;
  let lx; let ly;
  if (Math.abs(det) > 1e-9 * (a * c + 1)) {
    lx = (c * ex - b * ey) / det;
    ly = (-b * ex + a * ey) / det;
  } else {
    // všechny volné stěny rovnoběžné – řešíme jen ve směru stěn (nejmenší čtverce)
    const d = dirOf(free[0].ang);
    const proj = (ex * d.x + ey * d.y) / (a + c || 1);
    lx = proj * d.x; ly = proj * d.y;
  }
  for (const w of free) {
    const d = dirOf(w.ang);
    const L0 = Math.max(w.len, 1);
    w.len = Math.max(1, L0 + L0 * (d.x * lx + d.y * ly));
  }
  // 3) jednoznačně určené stěny
  markComputed(room, free);
  return { error: closureError(room) };
}

function markComputed(room, free) {
  const axisAligned = free.every((w) => Math.abs(Math.sin(rad(w.ang * 2))) < 1e-6);
  if (axisAligned) {
    const horiz = free.filter((w) => Math.abs(Math.cos(rad(w.ang))) > 0.5);
    const vert = free.filter((w) => Math.abs(Math.sin(rad(w.ang))) > 0.5);
    if (horiz.length === 1) horiz[0].state = 'computed';
    if (vert.length === 1) vert[0].state = 'computed';
  } else if (free.length === 1) {
    free[0].state = 'computed';
  } else if (free.length === 2) {
    const d0 = dirOf(free[0].ang); const d1 = dirOf(free[1].ang);
    if (Math.abs(d0.x * d1.y - d0.y * d1.x) > 1e-3) { free[0].state = 'computed'; free[1].state = 'computed'; }
  }
}

/** Nastaví naměřenou délku stěny a přepočítá místnost. */
export function setWallLength(room, wallId, mm) {
  const w = room.walls.find((x) => x.id === wallId);
  if (!w || !(mm > 0)) return null;
  w.len = mm;
  w.state = 'measured';
  return solveRoom(room);
}

export function clearWallLength(room, wallId) {
  const w = room.walls.find((x) => x.id === wallId);
  if (!w) return null;
  w.state = 'estimate';
  return solveRoom(room);
}

/** Další stěna k měření (po směru kreslení), přeskočí změřené a dopočítané. */
export function nextWallToMeasure(room, fromWallId) {
  const n = room.walls.length;
  const start = Math.max(0, room.walls.findIndex((w) => w.id === fromWallId));
  for (let k = 1; k <= n; k++) {
    const w = room.walls[(start + k) % n];
    if (w.state === 'estimate') return w;
  }
  return null;
}

export function roomBounds(room) {
  const v = vertices(room);
  const xs = v.map((p) => p.x); const ys = v.map((p) => p.y);
  return { x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) };
}

export function planBounds(plan) {
  if (!plan.rooms.length) return null;
  const bs = plan.rooms.map(roomBounds);
  return {
    x0: Math.min(...bs.map((b) => b.x0)), y0: Math.min(...bs.map((b) => b.y0)),
    x1: Math.max(...bs.map((b) => b.x1)), y1: Math.max(...bs.map((b) => b.y1)),
  };
}

/** Vzdálenost bodu od úsečky. */
export function distToSeg(p, a, b) {
  const dx = b.x - a.x; const dy = b.y - a.y;
  const l2 = dx * dx + dy * dy;
  let t = l2 ? ((p.x - a.x) * dx + (p.y - a.y) * dy) / l2 : 0;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}

/** Najde stěnu nejblíž bodu (mm). Vrací {room, wall, index, dist}. */
export function hitWall(plan, p, maxDist) {
  let best = null;
  for (const room of plan.rooms) {
    const v = vertices(room);
    room.walls.forEach((wall, i) => {
      const d = distToSeg(p, v[i], v[i + 1]);
      if (d <= maxDist && (!best || d < best.dist)) best = { room, wall, index: i, dist: d };
    });
  }
  return best;
}

export function pointInRoom(room, p) {
  if (!room.closed) return false;
  const v = vertices(room);
  let inside = false;
  for (let i = 0, j = v.length - 2; i < v.length - 1; j = i++) {
    const a = v[i]; const b = v[j];
    if ((a.y > p.y) !== (b.y > p.y) && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}
