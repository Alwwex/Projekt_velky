// LaserPlan – hlavní logika aplikace
import { DemoDevice, LaserDevice, STATUS_TEXT } from './ble.js';
import {
  exportDXF, exportJSON, exportPNG, exportSVG,
} from './export.js';
import {
  area, clearWallLength, closureError, closureTolerance, createPlan, createRoom, hitWall, nextWallToMeasure,
  perimeter, pointInRoom, setWallLength, solveRoom,
} from './plan.js';
import { recognizeStroke } from './sketch.js';
import { formatArea, formatLength, parseLength } from './units.js';
import { View } from './view.js';

const $ = (id) => document.getElementById(id);
const LS_CURRENT = 'laserplan.current';
const LS_PROJECTS = 'laserplan.projects';
const LS_SETTINGS = 'laserplan.settings';

// ----------------------------------------------------------------- stav
const state = {
  plan: createPlan(),
  tool: 'draw',
  selRoom: null,
  selWall: null,
  stroke: null,
  units: 'm',
  pending: null,            // poslední měření, které ještě nebylo přiřazeno
  last: null,
};
const settings = { autoAdvance: true, allow45: true, penOnly: false, quick: false };
let device = null;
const demoTruth = new Map();       // demo režim: "skutečné" rozměry místností
const undoStack = []; const redoStack = [];

const canvas = $('canvas');
const view = new View(canvas);

// ----------------------------------------------------------------- pomocné
const storage = {
  get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* plná / zakázaná */ } },
};

let toastTimer;
function toast(msg, kind = '') {
  const t = $('toast');
  t.textContent = msg;
  t.className = `toast show ${kind}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.className = 'toast'; }, 2600);
}

function snapshot() {
  undoStack.push(JSON.stringify(state.plan));
  if (undoStack.length > 80) undoStack.shift();
  redoStack.length = 0;
}

function undo() {
  if (!undoStack.length) return;
  redoStack.push(JSON.stringify(state.plan));
  state.plan = JSON.parse(undoStack.pop());
  validateSelection();
  changed(false);
}

function redo() {
  if (!redoStack.length) return;
  undoStack.push(JSON.stringify(state.plan));
  state.plan = JSON.parse(redoStack.pop());
  validateSelection();
  changed(false);
}

function validateSelection() {
  const room = findRoom(state.selRoom);
  if (!room) { state.selRoom = null; state.selWall = null; return; }
  if (state.selWall && !room.walls.some((w) => w.id === state.selWall)) state.selWall = null;
}

const findRoom = (id) => state.plan.rooms.find((r) => r.id === id);
const selected = () => {
  const room = findRoom(state.selRoom);
  const wall = room?.walls.find((w) => w.id === state.selWall);
  return { room, wall };
};

let raf = 0;
function draw() {
  if (raf) return;
  raf = requestAnimationFrame(() => { raf = 0; view.render(state); });
}

function changed(save = true) {
  state.plan.modified = Date.now();
  if (save) storage.set(LS_CURRENT, state.plan);
  updateUI();
  draw();
}

// ----------------------------------------------------------------- UI
function updateUI() {
  $('btnUndo').disabled = !undoStack.length;
  $('btnRedo').disabled = !redoStack.length;
  $('btnDelete').disabled = !state.selRoom;
  $('hint').classList.toggle('hidden', state.plan.rooms.length > 0);
  document.querySelectorAll('.tool[data-tool]').forEach((b) => b.classList.toggle('active', b.dataset.tool === state.tool));
  if ($('projectName') !== document.activeElement) $('projectName').value = state.plan.name;

  // panel stěny
  const { room, wall } = selected();
  const wp = $('wallPanel');
  if (wall) {
    wp.hidden = false;
    const idx = room.walls.indexOf(wall) + 1;
    $('wpTitle').textContent = `${room.name || 'Místnost'} · stěna ${idx}/${room.walls.length}`;
    $('wpValue').textContent = formatLength(wall.len, state.units);
    const st = $('wpState');
    st.className = `wp-state ${wall.state}`;
    st.textContent = {
      measured: 'Naměřeno ✓',
      computed: 'Dopočteno z ostatních stěn – měřit nemusíš',
      estimate: 'Odhad z náčrtu – změř laserem',
    }[wall.state];
    $('wpClear').disabled = wall.state !== 'measured';
    const up = $('wpUsePending');
    up.hidden = !state.pending;
    if (state.pending) up.textContent = `Použít poslední měření ${formatLength(state.pending.mm, state.units)}`;
  } else {
    wp.hidden = true;
  }

  // info o místnosti
  const ri = $('roomInfo');
  const r = room || (state.plan.rooms.length === 1 ? state.plan.rooms[0] : null);
  if (r && r.closed) {
    const todo = r.walls.filter((w) => w.state === 'estimate').length;
    const err = closureError(r);
    let status;
    if (todo) status = `zbývá změřit <b>${todo}</b> ${todo === 1 ? 'stěnu' : todo < 5 ? 'stěny' : 'stěn'}`;
    else if (err > closureTolerance(r)) status = `<span class="bad">obrys nesedí o ${formatLength(err, state.units === 'ft' ? 'ft' : 'mm')}</span>`;
    else status = `<span class="good">hotovo ✓</span>${err >= 0.5 ? ` (odchylka ${formatLength(err, 'mm')})` : ''}`;
    ri.innerHTML = `Plocha <b>${formatArea(area(r), state.units)}</b> · obvod <b>${formatLength(perimeter(r), state.units, { short: true })}</b><br>${status}`;
    ri.hidden = false;
  } else {
    ri.hidden = true;
  }

  // zařízení
  const chip = $('btnDevice');
  const conn = device?.connected;
  chip.classList.toggle('connected', !!conn);
  $('devName').textContent = conn ? device.name : 'Připojit laser';
  const st = device?.status;
  $('devBatt').hidden = !(conn && st);
  if (conn && st) $('devBatt').textContent = `${st.battery} %${st.usb ? ' ⚡' : ''}`;
  const rear = st ? st.rear : true;
  $('refText').textContent = rear ? 'zadní hrana' : 'přední hrana';
  $('refMark').setAttribute('x', rear ? '26' : '2');
  $('btnPointer').classList.toggle('on', !!st?.pointer);
  $('devSettings').disabled = !conn;
  $('optQuick').checked = !!st?.quick;
  $('btnDisconnect').hidden = !conn;
  $('devInfo').innerHTML = conn
    ? `<b>${device.name}</b> · baterie ${st ? `${st.battery} % (${(st.batteryMv / 1000).toFixed(2)} V)` : '?'}${st?.usb ? ' · nabíjí se' : ''}<br>`
      + `reference: ${rear ? 'zadní' : 'přední'} hrana · offset zadní ${st ? st.rearOffset.toFixed(1) : '?'} mm · firmware ${st?.fw || '?'}`
    : 'Nepřipojeno';

  // poslední měření
  if (state.last) {
    $('lastValue').textContent = state.last.status === 0 ? formatLength(state.last.mm, state.units) : '⚠';
    $('lastInfo').textContent = state.last.status === 0
      ? `#${state.last.seq} · ${state.last.rear ? 'od zadní hrany' : 'od přední hrany'}`
      : STATUS_TEXT[state.last.status] || 'Chyba';
  }
}

function setTool(t) {
  state.tool = t;
  canvas.style.cursor = t === 'draw' ? 'crosshair' : t === 'move' ? 'grab' : 'default';
  updateUI();
}

function selectWall(room, wall) {
  state.selRoom = room?.id || null;
  state.selWall = wall?.id || null;
  updateUI();
  draw();
}

// ----------------------------------------------------------------- měření
function applyLength(room, wall, mm, source) {
  snapshot();
  const res = setWallLength(room, wall.id, mm);
  if (!res) return;
  const todo = room.walls.filter((w) => w.state === 'estimate').length;
  if (!todo && room.closed) {
    if (res.error > closureTolerance(room)) toast(`Všechno změřeno, ale obrys nesedí o ${formatLength(res.error, 'mm')} – zkontroluj měření`, 'error');
    else toast(`Místnost hotová ✓  ${formatArea(area(room), state.units)}`, 'ok');
  } else {
    toast(`${source === 'laser' ? 'Naměřeno' : 'Zadáno'}: ${formatLength(mm, state.units)}`, 'ok');
  }
  if (settings.autoAdvance) {
    const next = nextWallToMeasure(room, wall.id);
    state.selWall = next ? next.id : null;
  }
  changed();
}

function onMeasurement(m) {
  state.last = m;
  if (m.continuous) { updateUI(); return; }
  if (m.status !== 0) {
    toast(STATUS_TEXT[m.status] || 'Chyba měření', 'error');
    updateUI();
    return;
  }
  const { room, wall } = selected();
  if (room && wall) {
    state.pending = null;
    applyLength(room, wall, m.mm, 'laser');
  } else {
    state.pending = m;
    toast(`${formatLength(m.mm, state.units)} – ťukni na stěnu, kam to patří`);
    updateUI();
  }
}

function measure() {
  if (!device?.connected) { openDevice(); return; }
  device.measure();
}

// ----------------------------------------------------------------- zařízení
function attachDevice(dev) {
  device = dev;
  dev.on('state', (s) => {
    $('btnDevice').classList.toggle('connecting', s === 'connecting');
    if (s === 'connected') toast(`Připojeno: ${dev.name}`, 'ok');
    if (s === 'disconnected') toast('Laser odpojen', 'error');
    updateUI();
  });
  dev.on('status', () => updateUI());
  dev.on('measurement', onMeasurement);
  dev.on('error', (e) => toast(`Bluetooth: ${e.message || e}`, 'error'));
}

function openDevice() {
  $('bleUnsupported').hidden = LaserDevice.supported();
  $('btnConnect').disabled = !LaserDevice.supported();
  updateUI();
  $('dlgDevice').showModal();
}

async function connectReal() {
  try {
    device?.disconnect?.();
    const dev = new LaserDevice();
    attachDevice(dev);
    await dev.connect();
    $('dlgDevice').close();
  } catch (e) {
    if (e?.name !== 'NotFoundError') toast(`Nepodařilo se připojit: ${e.message || e}`, 'error');
  }
}

async function connectDemo() {
  device?.disconnect?.();
  const dev = new DemoDevice(() => {
    const { room, wall } = selected();
    if (!wall) return null;
    // demo "skutečnost": uzavřený obrys z náčrtu, náhodně přeškálovaný a zaokrouhlený na 5 mm
    if (!demoTruth.has(room.id)) {
      const k = 0.85 + Math.random() * 0.3;
      demoTruth.set(room.id, new Map(room.walls.map((w) => [w.id, Math.round((w.len * k) / 5) * 5])));
    }
    return demoTruth.get(room.id).get(wall.id) ?? wall.len;
  });
  attachDevice(dev);
  await dev.connect();
  $('dlgDevice').close();
}

// ----------------------------------------------------------------- dialog ruční délky
function manualInput(room, wall) {
  const dlg = $('dlgInput');
  $('inputTitle').textContent = `Délka stěny ${room.walls.indexOf(wall) + 1}`;
  const inp = $('inputValue');
  inp.value = wall.state === 'measured' ? formatLength(wall.len, state.units).replace(/[^\d,.'" /]/g, '').trim() : '';
  dlg.returnValue = '';
  dlg.showModal();
  setTimeout(() => inp.focus(), 50);
  dlg.onclose = () => {
    if (dlg.returnValue !== 'ok') return;
    const mm = parseLength(inp.value, state.units);
    if (!(mm > 0)) { toast('Neplatná délka', 'error'); return; }
    applyLength(room, wall, mm, 'manual');
  };
}

// ----------------------------------------------------------------- ovládání plátna
const pointers = new Map();
let gesture = null;          // {type:'pan'|'pinch'|'draw'|'move', ...}
let lastTap = { t: 0, x: 0, y: 0 };

function localPos(e) {
  const r = canvas.getBoundingClientRect();
  return { x: e.clientX - r.left, y: e.clientY - r.top };
}

canvas.addEventListener('pointerdown', (e) => {
  canvas.setPointerCapture(e.pointerId);
  const p = localPos(e);
  pointers.set(e.pointerId, p);
  if (pointers.size === 2) {
    // dva prsty -> zoom/posun (zruší rozkreslený tah)
    state.stroke = null;
    const [a, b] = [...pointers.values()];
    gesture = { type: 'pinch', dist: Math.hypot(a.x - b.x, a.y - b.y), cx: (a.x + b.x) / 2, cy: (a.y + b.y) / 2 };
    draw();
    return;
  }
  if (pointers.size > 2) return;
  const panButton = e.button === 1 || e.button === 2;
  const touchPan = settings.penOnly && e.pointerType === 'touch' && state.tool === 'draw';
  if (panButton || touchPan) {
    gesture = { type: 'pan', x: p.x, y: p.y };
    return;
  }
  const w = view.toWorld(p);
  if (state.tool === 'draw') {
    gesture = { type: 'draw', start: p, moved: false };
    state.stroke = [w];
  } else if (state.tool === 'move') {
    const room = state.plan.rooms.find((r) => pointInRoom(r, w)) || hitWall(state.plan, w, 14 / view.scale)?.room;
    if (room) {
      snapshot();
      gesture = { type: 'move', room, last: w };
      selectWall(room, null);
      canvas.style.cursor = 'grabbing';
    } else gesture = { type: 'pan', x: p.x, y: p.y };
  } else {
    gesture = { type: 'tap-or-pan', x: p.x, y: p.y, start: p, moved: false };
  }
});

canvas.addEventListener('pointermove', (e) => {
  if (!pointers.has(e.pointerId)) return;
  const p = localPos(e);
  pointers.set(e.pointerId, p);
  if (!gesture) return;
  if (gesture.type === 'pinch' && pointers.size >= 2) {
    const [a, b] = [...pointers.values()];
    const dist = Math.hypot(a.x - b.x, a.y - b.y);
    const cx = (a.x + b.x) / 2; const cy = (a.y + b.y) / 2;
    view.ox += cx - gesture.cx; view.oy += cy - gesture.cy;
    if (gesture.dist > 0) view.zoomAt(cx, cy, dist / gesture.dist);
    Object.assign(gesture, { dist, cx, cy });
    draw();
  } else if (gesture.type === 'pan' || (gesture.type === 'tap-or-pan' && Math.hypot(p.x - gesture.start.x, p.y - gesture.start.y) > 6)) {
    if (gesture.type === 'tap-or-pan') { gesture.type = 'pan'; }
    view.ox += p.x - gesture.x; view.oy += p.y - gesture.y;
    gesture.x = p.x; gesture.y = p.y;
    draw();
  } else if (gesture.type === 'draw') {
    // u pera zpracuj i mezilehlé body
    const evs = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];
    for (const ce of evs) state.stroke.push(view.toWorld(localPos(ce)));
    gesture.moved = true;
    draw();
  } else if (gesture.type === 'move') {
    const w = view.toWorld(p);
    gesture.room.origin.x += w.x - gesture.last.x;
    gesture.room.origin.y += w.y - gesture.last.y;
    gesture.last = w;
    draw();
  }
});

function endPointer(e) {
  if (!pointers.has(e.pointerId)) return;
  const p = localPos(e);
  pointers.delete(e.pointerId);
  if (!gesture) return;
  if (gesture.type === 'pinch') {
    if (pointers.size === 0) gesture = null;
    return;
  }
  if (gesture.type === 'draw') {
    const stroke = state.stroke || [];
    state.stroke = null;
    const rec = recognizeStroke(stroke, view.scale, { allow45: settings.allow45 });
    if (rec) {
      snapshot();
      const room = createRoom(rec);
      room.name = `Místnost ${state.plan.rooms.length + 1}`;
      solveRoom(room);
      state.plan.rooms.push(room);
      selectWall(room, room.walls[0]);
      toast(rec.closed ? `Místnost: ${room.walls.length} stěn – změř označenou stěnu` : `Stěna: ${room.walls.length} úseků`);
      changed();
    } else {
      tap(p, e);
    }
  } else if (gesture.type === 'tap-or-pan') {
    tap(p, e);
  } else if (gesture.type === 'move') {
    canvas.style.cursor = 'grab';
    changed();
  }
  gesture = null;
  draw();
}
canvas.addEventListener('pointerup', endPointer);
canvas.addEventListener('pointercancel', (e) => { pointers.delete(e.pointerId); gesture = null; state.stroke = null; draw(); });
canvas.addEventListener('contextmenu', (e) => e.preventDefault());

function tap(p) {
  const w = view.toWorld(p);
  const label = view.hitLabel(p.x, p.y);
  const hit = label ? { room: label.room, wall: label.wall } : hitWall(state.plan, w, 18 / view.scale);
  const now = performance.now();
  const dbl = now - lastTap.t < 380 && Math.hypot(p.x - lastTap.x, p.y - lastTap.y) < 24;
  lastTap = { t: now, x: p.x, y: p.y };
  if (hit) {
    if (state.pending && !dbl) {
      // čekající měření -> přiřadit hned na ťuknutou stěnu
      const m = state.pending;
      state.pending = null;
      selectWall(hit.room, hit.wall);
      applyLength(hit.room, hit.wall, m.mm, 'laser');
      return;
    }
    selectWall(hit.room, hit.wall);
    if (dbl) manualInput(hit.room, hit.wall);
    return;
  }
  const room = state.plan.rooms.find((r) => pointInRoom(r, w));
  if (room) {
    if (dbl) {
      const name = prompt('Název místnosti', room.name);
      if (name != null) { snapshot(); room.name = name.trim(); changed(); }
    }
    selectWall(room, null);
    return;
  }
  selectWall(null, null);
}

canvas.addEventListener('wheel', (e) => {
  e.preventDefault();
  const p = localPos(e);
  if (e.ctrlKey || Math.abs(e.deltaY) >= Math.abs(e.deltaX)) view.zoomAt(p.x, p.y, Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015)));
  else { view.ox -= e.deltaX; }
  draw();
}, { passive: false });

window.addEventListener('resize', () => { view.resize(); draw(); });

// ----------------------------------------------------------------- tlačítka
document.querySelectorAll('.tool[data-tool]').forEach((b) => b.addEventListener('click', () => setTool(b.dataset.tool)));
$('btnUndo').onclick = undo;
$('btnRedo').onclick = redo;
$('btnFit').onclick = () => { view.fit(state.plan); draw(); };
$('btnDelete').onclick = () => {
  const room = findRoom(state.selRoom);
  if (!room) return;
  snapshot();
  state.plan.rooms = state.plan.rooms.filter((r) => r !== room);
  selectWall(null, null);
  changed();
  toast('Místnost smazána – Zpět ji vrátí');
};
$('btnMeasure').onclick = measure;
$('btnPointer').onclick = () => {
  if (!device?.connected) { openDevice(); return; }
  device.pointer(!device.status?.pointer);
};
$('btnRef').onclick = () => {
  if (!device?.connected) { toast('Nejdřív připoj laser'); return; }
  device.setReference(!(device.status?.rear ?? true));
};
$('btnDevice').onclick = openDevice;
$('btnConnect').onclick = connectReal;
$('btnDemo').onclick = connectDemo;
$('btnDisconnect').onclick = () => { device?.disconnect(); updateUI(); };
$('optQuick').onchange = (e) => device?.setQuick(e.target.checked);
$('btnCalib').onclick = () => {
  const real = parseLength($('calibValue').value, state.units);
  const m = state.last;
  if (!(real > 0) || !m || m.status !== 0) { $('calibInfo').textContent = 'Nejdřív změř a zadej skutečnou vzdálenost.'; return; }
  const st = device.status;
  const delta = real - m.mm;
  if (m.rear) device.setRearOffset(st.rearOffset + delta);
  else device.setFrontOffset(st.frontOffset + delta);
  $('calibInfo').textContent = `Korekce ${delta >= 0 ? '+' : ''}${delta.toFixed(1)} mm uložena do přístroje.`;
};

$('wpClose').onclick = () => selectWall(null, null);
$('wpManual').onclick = () => { const { room, wall } = selected(); if (wall) manualInput(room, wall); };
$('wpClear').onclick = () => {
  const { room, wall } = selected();
  if (!wall) return;
  snapshot(); clearWallLength(room, wall.id); changed();
};
$('wpNext').onclick = () => {
  const { room, wall } = selected();
  if (!room) return;
  const i = room.walls.indexOf(wall);
  selectWall(room, room.walls[(i + 1) % room.walls.length]);
};
$('wpUsePending').onclick = () => {
  const { room, wall } = selected();
  if (!wall || !state.pending) return;
  const m = state.pending; state.pending = null;
  applyLength(room, wall, m.mm, 'laser');
};

$('units').onchange = (e) => {
  state.units = e.target.value;
  storage.set(LS_SETTINGS, { ...settings, units: state.units });
  updateUI(); draw();
};
$('projectName').onchange = (e) => { state.plan.name = e.target.value.trim() || 'Bez názvu'; changed(); };
$('projectName').addEventListener('keydown', (e) => { if (e.key === 'Enter') e.target.blur(); });

// ----------------------------------------------------------------- menu / projekty
function renderProjects() {
  const list = $('projectList');
  const projects = storage.get(LS_PROJECTS, {});
  const items = Object.values(projects).sort((a, b) => b.modified - a.modified);
  list.innerHTML = '';
  if (!items.length) { list.innerHTML = '<li class="empty">Zatím nic uloženo</li>'; return; }
  for (const p of items) {
    const li = document.createElement('li');
    const name = document.createElement('span');
    name.textContent = p.name;
    const date = document.createElement('small');
    date.textContent = new Date(p.modified).toLocaleString('cs-CZ', { dateStyle: 'short', timeStyle: 'short' });
    const open = document.createElement('button'); open.className = 'btn'; open.type = 'button'; open.textContent = 'Otevřít';
    open.onclick = () => {
      snapshot(); state.plan = JSON.parse(JSON.stringify(p)); selectWall(null, null);
      view.fit(state.plan); changed(); $('dlgMenu').close();
    };
    const del = document.createElement('button'); del.className = 'btn ghost'; del.type = 'button'; del.textContent = '✕';
    del.setAttribute('aria-label', `Smazat ${p.name}`);
    del.onclick = () => {
      if (!confirm(`Smazat projekt „${p.name}“?`)) return;
      const all = storage.get(LS_PROJECTS, {}); delete all[p.id]; storage.set(LS_PROJECTS, all); renderProjects();
    };
    li.append(name, date, open, del);
    list.append(li);
  }
}

$('btnMenu').onclick = () => {
  $('optAdvance').checked = settings.autoAdvance;
  $('opt45').checked = settings.allow45;
  $('optPenOnly').checked = settings.penOnly;
  renderProjects();
  $('dlgMenu').showModal();
};
['optAdvance', 'opt45', 'optPenOnly'].forEach((id) => {
  $(id).onchange = () => {
    settings.autoAdvance = $('optAdvance').checked;
    settings.allow45 = $('opt45').checked;
    settings.penOnly = $('optPenOnly').checked;
    storage.set(LS_SETTINGS, { ...settings, units: state.units });
  };
});
document.querySelectorAll('#dlgMenu [data-act]').forEach((b) => {
  b.onclick = async () => {
    const act = b.dataset.act;
    if (act === 'new') {
      if (state.plan.rooms.length && !confirm('Začít nový půdorys? (aktuální zůstane v historii Zpět)')) return;
      snapshot(); state.plan = createPlan(); selectWall(null, null); changed(); $('dlgMenu').close();
    } else if (act === 'save') {
      const all = storage.get(LS_PROJECTS, {});
      all[state.plan.id] = { ...state.plan, modified: Date.now() };
      storage.set(LS_PROJECTS, all); renderProjects(); toast('Uloženo do projektů', 'ok');
    } else if (act === 'png') await exportPNG(state.plan, state.units);
    else if (act === 'svg') exportSVG(state.plan, state.units);
    else if (act === 'dxf') exportDXF(state.plan, state.units);
    else if (act === 'json') exportJSON(state.plan);
    else if (act === 'import') $('fileImport').click();
    else if (act === 'help') { $('dlgMenu').close(); $('dlgHelp').showModal(); }
  };
});
$('fileImport').onchange = async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  try {
    const p = JSON.parse(await f.text());
    if (!Array.isArray(p.rooms)) throw new Error('není to půdorys LaserPlan');
    snapshot(); state.plan = p; selectWall(null, null); view.fit(p); changed(); $('dlgMenu').close();
    toast('Načteno', 'ok');
  } catch (err) { toast(`Import selhal: ${err.message}`, 'error'); }
  e.target.value = '';
};

// ----------------------------------------------------------------- klávesy
window.addEventListener('keydown', (e) => {
  if (e.target.closest('input, select, dialog[open]')) return;
  const k = e.key.toLowerCase();
  if ((e.ctrlKey || e.metaKey) && k === 'z') { e.preventDefault(); if (e.shiftKey) redo(); else undo(); return; }
  if ((e.ctrlKey || e.metaKey) && k === 'y') { e.preventDefault(); redo(); return; }
  if (k === 'm' || k === ' ') { e.preventDefault(); measure(); }
  else if (k === 'd') setTool('draw');
  else if (k === 'v') setTool('select');
  else if (k === 'p') setTool('move');
  else if (k === 'f') { view.fit(state.plan); draw(); }
  else if (k === 'escape') selectWall(null, null);
  else if (k === 'delete' || k === 'backspace') $('btnDelete').click();
  else if (k === 'tab') { e.preventDefault(); $('wpNext').click(); }
  else if (k === 'enter') $('wpManual').click();
});

// ----------------------------------------------------------------- start
(function init() {
  const s = storage.get(LS_SETTINGS, {});
  Object.assign(settings, { autoAdvance: s.autoAdvance ?? true, allow45: s.allow45 ?? true, penOnly: !!s.penOnly });
  state.units = s.units || 'm';
  $('units').value = state.units;
  const saved = storage.get(LS_CURRENT, null);
  if (saved?.rooms) state.plan = saved;
  view.resize();
  if (state.plan.rooms.length) view.fit(state.plan);
  setTool('draw');
  changed(false);
  if (!storage.get('laserplan.seenHelp', false)) {
    storage.set('laserplan.seenHelp', true);
    $('dlgHelp').showModal();
  }
  if ('serviceWorker' in navigator && location.protocol !== 'file:') {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }
}());

// pro testy a ladění
window.laserplan = { state, view, settings, onMeasurement, area };
