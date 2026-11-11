// Testy jádra aplikace:  node --test app/tests
import assert from 'node:assert/strict';
import test from 'node:test';

import {
  area, closureError, createRoom, nextWallToMeasure, setWallLength, solveRoom,
} from '../js/plan.js';
import { recognizeStroke, snapAngle } from '../js/sketch.js';
import { formatFeetInches, formatLength, parseLength } from '../js/units.js';

const near = (a, b, tol = 0.5) => assert.ok(Math.abs(a - b) <= tol, `${a} != ${b} (±${tol})`);

// Ručně "roztřesený" obdélník 4 × 3 m s nepřesným uzavřením
function wobblyRect() {
  const pts = [];
  const push = (x, y) => pts.push({ x: x + (Math.random() - 0.5) * 40, y: y + (Math.random() - 0.5) * 40 });
  for (let t = 0; t <= 1; t += 0.05) push(t * 4000, 0);
  for (let t = 0; t <= 1; t += 0.05) push(4000, t * 3000);
  for (let t = 0; t <= 1; t += 0.05) push(4000 - t * 4000, 3000);
  for (let t = 0; t <= 0.97; t += 0.05) push(0, 3000 - t * 3000);
  return pts;
}

test('snapAngle preferuje pravé úhly', () => {
  assert.equal(snapAngle(5), 0);
  assert.equal(snapAngle(88), 90);
  assert.equal(snapAngle(-91), 270);
  assert.equal(snapAngle(40), 45);
  assert.equal(snapAngle(40, { allow45: false }), 0);
});

test('rozpozná roztřesený obdélník jako 4 stěny a uzavře ho', () => {
  const r = recognizeStroke(wobblyRect(), 0.1);
  assert.ok(r, 'rozpoznáno');
  assert.equal(r.closed, true);
  assert.equal(r.walls.length, 4);
  assert.deepEqual(r.walls.map((w) => w.ang), [0, 90, 180, 270]);
  const room = createRoom(r);
  solveRoom(room);
  near(closureError(room), 0, 1e-6);
});

test('L-místnost: změřené stěny + dopočet zbytku', () => {
  // L tvar: 0→4000, dolů 2000, doleva 1500, dolů 1500, doleva 2500, nahoru 3500
  const room = createRoom({
    origin: { x: 0, y: 0 },
    closed: true,
    walls: [
      { ang: 0, len: 4100 }, { ang: 90, len: 1900 }, { ang: 180, len: 1400 },
      { ang: 90, len: 1600 }, { ang: 180, len: 2600 }, { ang: 270, len: 3600 },
    ],
  });
  solveRoom(room);
  near(closureError(room), 0, 1e-6);
  const w = room.walls;
  setWallLength(room, w[0].id, 4000);
  setWallLength(room, w[1].id, 2000);
  setWallLength(room, w[2].id, 1500);
  setWallLength(room, w[3].id, 1500);
  // zbývají w[4] (vodorovná) a w[5] (svislá) -> obě jednoznačně určené
  assert.equal(w[4].state, 'computed');
  assert.equal(w[5].state, 'computed');
  near(w[4].len, 2500);
  near(w[5].len, 3500);
  near(area(room), 4000 * 2000 + 2500 * 1500);
  assert.equal(nextWallToMeasure(room, w[3].id), null);
});

test('první měření přeškáluje celý náčrt', () => {
  const room = createRoom({
    origin: { x: 0, y: 0 }, closed: true,
    walls: [{ ang: 0, len: 2000 }, { ang: 90, len: 1000 }, { ang: 180, len: 2000 }, { ang: 270, len: 1000 }],
  });
  setWallLength(room, room.walls[0].id, 4000);
  near(room.walls[1].len, 2000);          // proporce zachována
  near(room.walls[2].len, 4000);
  assert.equal(room.walls[2].state, 'computed');
});

test('chyba uzavření, když nesedí všechna měření', () => {
  const room = createRoom({
    origin: { x: 0, y: 0 }, closed: true,
    walls: [{ ang: 0, len: 2000 }, { ang: 90, len: 1000 }, { ang: 180, len: 2000 }, { ang: 270, len: 1000 }],
  });
  room.walls.forEach((w, i) => setWallLength(room, w.id, [3000, 2000, 3012, 2000][i]));
  near(closureError(room), 12, 0.01);
});

test('jednotky', () => {
  assert.equal(parseLength('3,452'), 3452);
  assert.equal(parseLength('345 cm'), 3450);
  assert.equal(parseLength('120mm', 'm'), 120);
  near(parseLength('11\' 4 3/8"'), 3464.0, 0.1);
  assert.equal(formatFeetInches(3464), '11\' 4 3/8"');
  assert.equal(formatLength(3452.4, 'm').replace(/\s/g, ' '), '3,452 m');
});
