// Vykreslení půdorysu na <canvas> (zoom, posun, mřížka, kóty).
import {
  area, centroid, closureError, closureTolerance, orientation, planBounds, vertices,
} from './plan.js';
import { formatArea, formatLength } from './units.js';

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export class View {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.scale = 0.12;            // px na mm (1 m = 120 px)
    this.ox = 0; this.oy = 0;     // posun (px)
    this.dpr = 1;
    this.w = 0; this.h = 0;
    this.labelBoxes = [];         // pro klepnutí na kótu
    this.resize();
  }

  resize() {
    const r = this.canvas.getBoundingClientRect();
    this.dpr = window.devicePixelRatio || 1;
    this.w = r.width; this.h = r.height;
    this.canvas.width = Math.round(r.width * this.dpr);
    this.canvas.height = Math.round(r.height * this.dpr);
    if (!this.inited) { this.ox = this.w / 2; this.oy = this.h / 2; this.inited = true; }
  }

  toScreen(p) { return { x: p.x * this.scale + this.ox, y: p.y * this.scale + this.oy }; }
  toWorld(p) { return { x: (p.x - this.ox) / this.scale, y: (p.y - this.oy) / this.scale }; }

  zoomAt(sx, sy, factor) {
    const s = Math.min(3, Math.max(0.005, this.scale * factor));
    const k = s / this.scale;
    this.ox = sx - (sx - this.ox) * k;
    this.oy = sy - (sy - this.oy) * k;
    this.scale = s;
  }

  fit(plan) {
    const b = planBounds(plan);
    if (!b) return;
    const pad = Math.min(90, Math.max(44, Math.min(this.w, this.h) * 0.12));
    const bw = Math.max(b.x1 - b.x0, 500); const bh = Math.max(b.y1 - b.y0, 500);
    const leftPad = this.w < 720 ? 56 : 80;
    this.scale = Math.min((this.w - pad * 2 - leftPad) / bw, (this.h - pad * 2) / bh, 1.5);
    this.ox = leftPad / 2 + this.w / 2 - ((b.x0 + b.x1) / 2) * this.scale;
    this.oy = this.h / 2 - ((b.y0 + b.y1) / 2) * this.scale;
  }

  render(state) {
    const { ctx } = this;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, this.w, this.h);
    this.colors = {
      grid: css('--grid'), major: css('--grid-major'), wall: css('--wall'), fill: css('--room-fill'),
      accent: css('--accent'), measured: css('--measured'), computed: css('--computed'),
      muted: css('--muted'), text: css('--text'), panel: css('--panel'), danger: css('--danger'), bg: css('--bg'),
    };
    this.drawGrid();
    this.labelBoxes = [];
    for (const room of state.plan.rooms) this.drawRoom(room, state);
    if (state.stroke?.length > 1) this.drawStroke(state.stroke);
  }

  drawGrid() {
    const { ctx, scale } = this;
    const steps = [10, 50, 100, 500, 1000, 5000, 10000];
    const minor = steps.find((s) => s * scale >= 14) || 10000;
    const major = minor * (minor === 50 || minor === 500 || minor === 5000 ? 2 : 10);
    const a = this.toWorld({ x: 0, y: 0 }); const b = this.toWorld({ x: this.w, y: this.h });
    for (const [step, color] of [[minor, this.colors.grid], [major, this.colors.major]]) {
      ctx.beginPath();
      for (let x = Math.floor(a.x / step) * step; x <= b.x; x += step) {
        const sx = Math.round(x * scale + this.ox) + 0.5; ctx.moveTo(sx, 0); ctx.lineTo(sx, this.h);
      }
      for (let y = Math.floor(a.y / step) * step; y <= b.y; y += step) {
        const sy = Math.round(y * scale + this.oy) + 0.5; ctx.moveTo(0, sy); ctx.lineTo(this.w, sy);
      }
      ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.stroke();
    }
    // měřítko vlevo dole
    const len = major * scale;
    const x0 = 86; const y0 = this.h - 18;
    ctx.strokeStyle = this.colors.muted; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(x0, y0 - 5); ctx.lineTo(x0, y0); ctx.lineTo(x0 + len, y0); ctx.lineTo(x0 + len, y0 - 5); ctx.stroke();
    ctx.fillStyle = this.colors.muted; ctx.font = '12px system-ui'; ctx.textAlign = 'left'; ctx.textBaseline = 'bottom';
    ctx.fillText(major >= 1000 ? `${major / 1000} m` : `${major / 10} cm`, x0 + len + 6, y0 + 2);
  }

  drawStroke(pts) {
    const { ctx } = this;
    ctx.beginPath();
    pts.forEach((p, i) => { const s = this.toScreen(p); if (i) ctx.lineTo(s.x, s.y); else ctx.moveTo(s.x, s.y); });
    ctx.strokeStyle = this.colors.accent; ctx.lineWidth = 3; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.setLineDash([]); ctx.stroke();
  }

  drawRoom(room, state) {
    const { ctx } = this;
    const v = vertices(room).map((p) => this.toScreen(p));
    const selectedRoom = state.selRoom === room.id;
    // výplň
    if (room.closed) {
      ctx.beginPath();
      v.slice(0, -1).forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
      ctx.closePath();
      ctx.fillStyle = this.colors.fill; ctx.fill();
      if (selectedRoom) { ctx.strokeStyle = this.colors.accent; ctx.globalAlpha = 0.35; ctx.lineWidth = 10; ctx.stroke(); ctx.globalAlpha = 1; }
    }
    // stěny
    room.walls.forEach((w, i) => {
      const a = v[i]; const b = v[i + 1];
      const sel = state.selWall === w.id;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
      ctx.lineCap = 'round';
      ctx.strokeStyle = sel ? this.colors.accent : this.colors.wall;
      ctx.lineWidth = sel ? 6 : 3;
      ctx.stroke();
    });
    // chyba uzavření
    const err = room.closed ? closureError(room) : 0;
    if (room.closed && err > closureTolerance(room)) {
      const a = v[v.length - 1]; const b = v[0];
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
      ctx.setLineDash([6, 5]); ctx.strokeStyle = this.colors.danger; ctx.lineWidth = 2; ctx.stroke(); ctx.setLineDash([]);
    }
    // vrcholy
    ctx.fillStyle = this.colors.wall;
    v.slice(0, room.closed ? -1 : undefined).forEach((p) => { ctx.beginPath(); ctx.arc(p.x, p.y, 3.2, 0, Math.PI * 2); ctx.fill(); });
    // kóty
    const orient = room.closed ? orientation(room) : 1;
    room.walls.forEach((w, i) => this.drawDim(room, w, v[i], v[i + 1], orient, state));
    // plocha
    if (room.closed && room.walls.length >= 3) {
      const c = this.toScreen(centroid(room));
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.font = '600 15px system-ui'; ctx.fillStyle = this.colors.text;
      if (room.name) ctx.fillText(room.name, c.x, c.y - 12);
      ctx.font = '13px system-ui'; ctx.fillStyle = this.colors.muted;
      ctx.fillText(formatArea(area(room), state.units), c.x, c.y + (room.name ? 8 : 0));
    }
  }

  drawDim(room, w, a, b, orient, state) {
    const { ctx } = this;
    const L = Math.hypot(b.x - a.x, b.y - a.y);
    if (L < 4) return;
    const mx = (a.x + b.x) / 2; const my = (a.y + b.y) / 2;
    // vnější normála (pro obrazovku s osou y dolů)
    let nx = (b.y - a.y) / L; let ny = -(b.x - a.x) / L;
    if (orient < 0) { nx = -nx; ny = -ny; }
    const off = 20;
    const x = mx + nx * off; const y = my + ny * off;
    let text = formatLength(w.len, state.units, { short: w.state === 'estimate' });
    if (w.state === 'estimate') text = `≈ ${text}`;
    if (w.state === 'computed') text = `= ${text}`;
    const sel = state.selWall === w.id;
    ctx.font = w.state === 'measured' ? '700 14px system-ui' : '600 13px system-ui';
    const tw = ctx.measureText(text).width;
    const bw = tw + 14; const bh = 24;
    const bx = x - bw / 2; const by = y - bh / 2;
    ctx.beginPath(); roundRect(ctx, bx, by, bw, bh, 6);
    if (w.state === 'measured') {
      ctx.fillStyle = this.colors.measured; ctx.fill();
      ctx.fillStyle = '#fff';
    } else if (w.state === 'computed') {
      ctx.fillStyle = this.colors.panel; ctx.fill();
      ctx.strokeStyle = this.colors.computed; ctx.lineWidth = 1.5; ctx.stroke();
      ctx.fillStyle = this.colors.computed;
    } else {
      ctx.fillStyle = this.colors.panel; ctx.globalAlpha = 0.85; ctx.fill(); ctx.globalAlpha = 1;
      ctx.fillStyle = this.colors.muted;
    }
    if (sel) { ctx.strokeStyle = this.colors.accent; ctx.lineWidth = 2.5; ctx.stroke(); }
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(text, x, y + 0.5);
    this.labelBoxes.push({ room, wall: w, x0: bx, y0: by, x1: bx + bw, y1: by + bh });
  }

  hitLabel(sx, sy) {
    for (let i = this.labelBoxes.length - 1; i >= 0; i--) {
      const b = this.labelBoxes[i];
      if (sx >= b.x0 - 4 && sx <= b.x1 + 4 && sy >= b.y0 - 4 && sy <= b.y1 + 4) return b;
    }
    return null;
  }
}

export function roundRect(ctx, x, y, w, h, r) {
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
