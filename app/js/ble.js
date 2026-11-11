// Komunikace s laserem LaserPlan přes Web Bluetooth (+ demo simulátor).
// Protokol je popsán v docs/ble-protokol.md.

export const SERVICE = '4c500001-6c61-7365-7270-6c616e000000';
export const CH_MEAS = '4c500002-6c61-7365-7270-6c616e000000';
export const CH_CTRL = '4c500003-6c61-7365-7270-6c616e000000';
export const CH_STATUS = '4c500004-6c61-7365-7270-6c616e000000';

export const CMD = {
  MEASURE: 0x01, POINTER_ON: 0x02, POINTER_OFF: 0x03, CONT_ON: 0x04, CONT_OFF: 0x05,
  SET_REFERENCE: 0x06, SET_REAR_OFS: 0x07, BEEP: 0x08, SET_UNITS: 0x09,
  SET_FRONT_OFS: 0x0a, SET_DRIVER: 0x0b, LASER_OFF: 0x0c, SET_QUICK: 0x0d,
};

export const STATUS_TEXT = {
  0: 'OK', 1: 'Chyba měření', 2: 'Slabý signál', 3: 'Mimo rozsah', 4: 'Bez odpovědi modulu', 5: 'Laser modul nenalezen',
};

export function parseMeasurement(dv) {
  return {
    seq: dv.getUint16(0, true),
    mm: dv.getInt32(2, true) / 10,
    quality: dv.getUint16(6, true),
    status: dv.getUint8(8),
    rear: !!(dv.getUint8(9) & 1),
    continuous: !!(dv.getUint8(9) & 2),
    errCode: dv.byteLength >= 12 ? dv.getUint16(10, true) : 0,
  };
}

export function parseStatus(dv) {
  const f = dv.getUint8(3);
  return {
    battery: dv.getUint8(0),
    batteryMv: dv.getUint16(1, true),
    usb: !!(f & 1), laserPowered: !!(f & 2), pointer: !!(f & 4), continuous: !!(f & 8),
    rear: !!(f & 16), quick: !!(f & 32),
    rearOffset: dv.getInt32(4, true) / 100,
    frontOffset: dv.getInt32(8, true) / 100,
    units: dv.getUint8(12),
    driver: dv.getUint8(13),
    fw: `${dv.getUint8(14)}.${dv.getUint8(15)}`,
  };
}

const i32 = (v) => { const b = new Uint8Array(4); new DataView(b.buffer).setInt32(0, v, true); return [...b]; };

/** Společné rozhraní pro skutečné i demo zařízení. */
class Emitter {
  constructor() { this.handlers = {}; }
  on(ev, fn) { (this.handlers[ev] ||= []).push(fn); return this; }
  emit(ev, data) { (this.handlers[ev] || []).forEach((f) => f(data)); }
}

export class LaserDevice extends Emitter {
  static supported() { return typeof navigator !== 'undefined' && !!navigator.bluetooth; }

  constructor() {
    super();
    this.device = null; this.ctrl = null; this.status = null; this.name = '';
    this.wantConnected = false;
    this.queue = Promise.resolve();
  }

  get connected() { return !!this.device?.gatt?.connected; }

  async connect() {
    this.device = await navigator.bluetooth.requestDevice({
      filters: [{ services: [SERVICE] }, { namePrefix: 'LaserPlan' }],
      optionalServices: [SERVICE, 'battery_service', 'device_information'],
    });
    this.name = this.device.name || 'LaserPlan';
    this.device.addEventListener('gattserverdisconnected', () => this._onDisconnect());
    this.wantConnected = true;
    await this._setup();
  }

  async _setup() {
    this.emit('state', 'connecting');
    const server = await this.device.gatt.connect();
    const svc = await server.getPrimaryService(SERVICE);
    const meas = await svc.getCharacteristic(CH_MEAS);
    this.ctrl = await svc.getCharacteristic(CH_CTRL);
    const st = await svc.getCharacteristic(CH_STATUS);
    meas.addEventListener('characteristicvaluechanged', (e) => this.emit('measurement', parseMeasurement(e.target.value)));
    st.addEventListener('characteristicvaluechanged', (e) => {
      this.status = parseStatus(e.target.value);
      this.emit('status', this.status);
    });
    await meas.startNotifications();
    await st.startNotifications();
    try {
      this.status = parseStatus(await st.readValue());
      this.emit('status', this.status);
    } catch { /* nevadí */ }
    this.emit('state', 'connected');
  }

  async _onDisconnect() {
    this.emit('state', 'disconnected');
    // automatické znovupřipojení (např. po krátkém výpadku)
    for (let i = 0; i < 5 && this.wantConnected; i++) {
      await new Promise((r) => setTimeout(r, 1000 * (i + 1)));
      try { await this._setup(); return; } catch { /* další pokus */ }
    }
  }

  disconnect() {
    this.wantConnected = false;
    if (this.device?.gatt?.connected) this.device.gatt.disconnect();
  }

  send(op, payload = []) {
    // zápisy řadíme za sebe – GATT nesnese paralelní operace
    this.queue = this.queue.then(async () => {
      if (!this.ctrl) return;
      const data = new Uint8Array([op, ...payload]);
      if (this.ctrl.writeValueWithResponse) await this.ctrl.writeValueWithResponse(data);
      else await this.ctrl.writeValue(data);
    }).catch((e) => this.emit('error', e));
    return this.queue;
  }

  measure() { return this.send(CMD.MEASURE); }
  pointer(on) { return this.send(on ? CMD.POINTER_ON : CMD.POINTER_OFF); }
  continuous(on) { return this.send(on ? CMD.CONT_ON : CMD.CONT_OFF); }
  setReference(rear) { return this.send(CMD.SET_REFERENCE, [rear ? 1 : 0]); }
  setQuick(on) { return this.send(CMD.SET_QUICK, [on ? 1 : 0]); }
  setRearOffset(mm) { return this.send(CMD.SET_REAR_OFS, i32(Math.round(mm * 100))); }
  setFrontOffset(mm) { return this.send(CMD.SET_FRONT_OFS, i32(Math.round(mm * 100))); }
  beep() { return this.send(CMD.BEEP); }
}

/**
 * Demo zařízení – pro vyzkoušení aplikace bez hardwaru.
 * "Měří" délku právě vybrané stěny s malou náhodnou odchylkou.
 */
export class DemoDevice extends Emitter {
  constructor(getTarget) {
    super();
    this.getTarget = getTarget;
    this.name = 'Demo laser';
    this.seq = 0;
    this.status = {
      battery: 87, batteryMv: 3950, usb: false, laserPowered: false, pointer: false, continuous: false,
      rear: true, quick: true, rearOffset: 93, frontOffset: -2, units: 0, driver: 3, fw: '1.0',
    };
    this.connected = false;
  }

  async connect() {
    this.emit('state', 'connecting');
    await new Promise((r) => setTimeout(r, 300));
    this.connected = true;
    this.emit('state', 'connected');
    this.emit('status', this.status);
  }

  disconnect() { this.connected = false; this.emit('state', 'disconnected'); }

  measure() {
    const target = this.getTarget?.();
    const base = target ?? 1500 + Math.random() * 3000;
    const mm = Math.round((base + (Math.random() - 0.5) * 2) * 10) / 10;
    setTimeout(() => this.emit('measurement', {
      seq: ++this.seq, mm, quality: 800, status: 0, rear: this.status.rear, continuous: false, errCode: 0,
    }), 350);
  }

  pointer(on) { this.status.pointer = on; this.emit('status', this.status); }
  continuous() {}
  setReference(rear) { this.status.rear = rear; this.emit('status', this.status); }
  setQuick(on) { this.status.quick = on; this.emit('status', this.status); }
  setRearOffset(mm) { this.status.rearOffset = mm; this.emit('status', this.status); }
  setFrontOffset(mm) { this.status.frontOffset = mm; this.emit('status', this.status); }
  beep() {}
}
