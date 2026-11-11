// ============================================================================
//  Ovladače laserových modulů
//
//  POZNÁMKA: Protokoly vycházejí z dokumentace modulů Chengdu JRT (binární)
//  a z běžných "TTL laser rangefinder" modulů (ASCII). Výrobci je občas mírně
//  mění – pokud tvůj modul neodpovídá, zapni ladicí výpis (příkaz "raw 1"
//  v sériové konzoli) a porovnej s datasheetem modulu.
// ============================================================================
#include "laser.h"

#include "config.h"

static JrtLaser g_jrt;
static AsciiLaser g_ascii;
static SimLaser g_sim;

bool g_laserRawDebug = false;

static void dumpTx(const uint8_t* d, size_t n) {
  if (!g_laserRawDebug) return;
  Serial.print("[laser TX]");
  for (size_t i = 0; i < n; i++) Serial.printf(" %02X", d[i]);
  Serial.println();
}

// ----------------------------------------------------------------------------
//  JRT
// ----------------------------------------------------------------------------
//  Rámec: AA | adresa | reg(2) | počet slov(2) | data(2*n) | checksum
//  checksum = součet bajtů od adresy po konec dat (mod 256)
//  adresa 0x00 = zápis, 0x80 = čtení
void JrtLaser::writeReg(uint16_t reg, uint16_t value) {
  uint8_t f[9] = {0xAA, 0x00, (uint8_t)(reg >> 8), (uint8_t)reg, 0x00, 0x01,
                  (uint8_t)(value >> 8), (uint8_t)value, 0};
  uint8_t cs = 0;
  for (int i = 1; i < 8; i++) cs += f[i];
  f[8] = cs;
  ser->write(f, sizeof f);
  dumpTx(f, sizeof f);
}

bool JrtLaser::probe(HardwareSerial& s) {
  ser = &s;
  static const uint32_t bauds[] = {115200, 19200, 9600};
  for (uint32_t b : bauds) {
    s.updateBaudRate(b);
    delay(20);
    while (s.available()) s.read();
    s.write((uint8_t)0x55);           // automatická detekce rychlosti
    delay(60);
    while (s.available()) s.read();
    const uint8_t rd[] = {0xAA, 0x80, 0x00, 0x00, 0x80};  // čti stav
    s.write(rd, sizeof rd);
    uint32_t t0 = millis();
    n = 0;
    while (millis() - t0 < 300) {
      LaserResult r;
      bool isResult = false;
      if (parse(r, isResult)) {
        Serial.printf("[laser] JRT modul nalezen @ %lu Bd\n", (unsigned long)b);
        return true;
      }
      delay(2);
    }
  }
  return false;
}

void JrtLaser::pointer(bool on) { writeReg(0x01BE, on ? 1 : 0); }
void JrtLaser::startSingle() { writeReg(0x0020, 0x0000); }       // jedno, auto
void JrtLaser::startContinuous() { writeReg(0x0020, 0x0004); }   // průběžně, auto
void JrtLaser::stop() {
  uint8_t b = 0x58;                                               // "X" = stop
  ser->write(&b, 1);
  dumpTx(&b, 1);
  delay(5);
  pointer(false);
}

// Vrací true, pokud byl přijat platný rámec. isResult = výsledek měření/chyba.
bool JrtLaser::parse(LaserResult& out, bool& isResult) {
  while (ser && ser->available()) {
    uint8_t c = ser->read();
    if (n == 0 && c != 0xAA) continue;
    if (n < sizeof buf) buf[n++] = c;
    if (n < 6) continue;
    size_t words = ((size_t)buf[4] << 8) | buf[5];
    size_t len = 6 + words * 2 + 1;
    if (len > sizeof buf) { n = 0; continue; }       // nesmysl – resync
    if (n < len) continue;
    uint8_t cs = 0;
    for (size_t i = 1; i < len - 1; i++) cs += buf[i];
    if (g_laserRawDebug) {
      Serial.print("[laser RX]");
      for (size_t i = 0; i < len; i++) Serial.printf(" %02X", buf[i]);
      Serial.println(cs == buf[len - 1] ? " (OK)" : " (CS!)");
    }
    n = 0;
    if (cs != buf[len - 1]) continue;
    uint16_t reg = ((uint16_t)buf[2] << 8) | buf[3];
    isResult = false;
    if (reg == 0x0022 && words >= 3) {
      uint32_t d = ((uint32_t)buf[6] << 24) | ((uint32_t)buf[7] << 16) |
                   ((uint32_t)buf[8] << 8) | buf[9];
      out.mm = (float)d;
      out.quality = ((uint16_t)buf[10] << 8) | buf[11];
      out.status = LaserStatus::Ok;
      out.errCode = 0;
      isResult = true;
    } else if (reg == 0x0000 && words >= 1 && (buf[1] & 0x80)) {
      uint16_t code = ((uint16_t)buf[6] << 8) | buf[7];
      if (code != 0) {
        out.errCode = code;
        // kódy dle dokumentace JRT: 5 = mimo rozsah, 8 = slabý signál
        out.status = code == 0x0005 ? LaserStatus::OutOfRange
                   : code == 0x0008 ? LaserStatus::WeakSignal
                                    : LaserStatus::Error;
        isResult = true;
      }
    }
    return true;
  }
  return false;
}

bool JrtLaser::poll(LaserResult& out) {
  bool isResult = false;
  while (parse(out, isResult)) {
    if (isResult) return true;
  }
  return false;
}

// ----------------------------------------------------------------------------
//  ASCII ("O" = laser zap, "C" = vyp, "D" = měř, "F" = rychle měř)
//  Typická odpověď:  "D: 1.234m,0079"   nebo   "12.345m,0123"
//  Chyba:            "D: Er08!"
// ----------------------------------------------------------------------------
bool AsciiLaser::probe(HardwareSerial& s) {
  ser = &s;
  static const uint32_t bauds[] = {9600, 19200, 115200};
  for (uint32_t b : bauds) {
    s.updateBaudRate(b);
    delay(20);
    while (s.available()) s.read();
    s.print("C");
    uint32_t t0 = millis();
    String resp;
    while (millis() - t0 < 400) {
      while (s.available()) resp += (char)s.read();
      if (resp.indexOf("OK") >= 0 || resp.indexOf("C,") >= 0) {
        Serial.printf("[laser] ASCII modul nalezen @ %lu Bd\n", (unsigned long)b);
        return true;
      }
      delay(5);
    }
  }
  return false;
}

void AsciiLaser::pointer(bool on) { ser->print(on ? "O" : "C"); }
void AsciiLaser::startSingle() { continuous = false; ser->print("D"); }
void AsciiLaser::startContinuous() { continuous = true; ser->print("F"); }
void AsciiLaser::stop() { continuous = false; ser->print("C"); }

bool AsciiLaser::parseLine(const char* l, LaserResult& out) {
  const char* er = strstr(l, "Er");
  if (!er) er = strstr(l, "ER");
  if (er) {
    out.errCode = (uint16_t)atoi(er + 2);
    out.status = out.errCode == 8 ? LaserStatus::WeakSignal : LaserStatus::Error;
    return true;
  }
  // najdi číslo následované 'm'
  const char* m = strchr(l, 'm');
  if (!m) return false;
  const char* p = m;
  while (p > l && (isdigit((unsigned char)p[-1]) || p[-1] == '.')) p--;
  if (p == m) return false;
  out.mm = atof(p) * 1000.0f;
  out.quality = 0;
  const char* comma = strchr(m, ',');
  if (comma) out.quality = (uint16_t)atoi(comma + 1);
  out.status = LaserStatus::Ok;
  out.errCode = 0;
  return true;
}

bool AsciiLaser::poll(LaserResult& out) {
  while (ser && ser->available()) {
    char c = (char)ser->read();
    if (c == '\r' || c == '\n') {
      if (n == 0) continue;
      line[n] = 0;
      n = 0;
      if (g_laserRawDebug) Serial.printf("[laser RX] %s\n", line);
      if (parseLine(line, out)) {
        if (continuous) ser->print("F");
        return true;
      }
    } else if (n < sizeof(line) - 1) {
      line[n++] = c;
    }
  }
  return false;
}

// ----------------------------------------------------------------------------
//  Simulace
// ----------------------------------------------------------------------------
bool SimLaser::poll(LaserResult& out) {
  static const float room[] = {4523.4f, 3637.2f, 2541.0f, 1094.8f, 1982.4f, 2542.2f};
  if (!pending || (int32_t)(millis() - due) < 0) return false;
  out.status = LaserStatus::Ok;
  out.mm = room[idx++ % 6] + (float)random(-15, 16) / 10.0f;
  out.quality = 900;
  if (continuous) due = millis() + 350;
  else pending = false;
  return true;
}

// ============================================================================
//  Správce laseru
// ============================================================================
static HardwareSerial& laserSerial() { return Serial1; }

void Laser::begin(uint8_t preferredDriver) {
  preferred = preferredDriver;
  pinMode(PIN_LASER_EN, OUTPUT);
  digitalWrite(PIN_LASER_EN, LOW);
  pinMode(PIN_LASER_AUX, OUTPUT);
  digitalWrite(PIN_LASER_AUX, LOW);
  pinMode(PIN_LASER_TX, INPUT);
  if (preferred == 3) {
    drv = &g_sim;
    detected = true;
  }
}

void Laser::power(bool on) {
  if (on == isPowered) return;
  static uint32_t baud = 115200;
  if (on) {
    laserSerial().begin(baud, SERIAL_8N1, PIN_LASER_RX, PIN_LASER_TX);
    digitalWrite(PIN_LASER_EN, HIGH);
    digitalWrite(PIN_LASER_AUX, HIGH);
    isPowered = true;
    delay(400);                      // start modulu
  } else {
    baud = laserSerial().baudRate();
    laserSerial().end();
    // TX do vstupu, aby se vypnutý modul "nenapájel" přes svůj RX pin
    pinMode(PIN_LASER_TX, INPUT);
    digitalWrite(PIN_LASER_EN, LOW);
    digitalWrite(PIN_LASER_AUX, LOW);
    isPowered = false;
    st = State::Off;
  }
}

LaserDriver* Laser::detect() {
  HardwareSerial& s = laserSerial();
  if (preferred == 1) { if (g_jrt.probe(s)) return &g_jrt; }
  if (preferred == 2) { if (g_ascii.probe(s)) return &g_ascii; }
  if (preferred == 0) {
    if (g_jrt.probe(s)) return &g_jrt;
    if (g_ascii.probe(s)) return &g_ascii;
  }
  return nullptr;
}

bool Laser::ensureReady() {
  tActivity = millis();
  if (drv == &g_sim) { if (st == State::Off) st = State::Idle; return true; }
  if (!isPowered) {
    power(true);
    st = State::Idle;
  }
  if (!detected || !drv) {
    drv = detect();
    detected = drv != nullptr;
    if (!drv) {
      Serial.println("[laser] modul nenalezen – zkontroluj zapojení TX/RX a napájení");
      power(false);
      return false;
    }
  }
  drv->begin(laserSerial());
  return true;
}

void Laser::measure() {
  if (!ensureReady()) { failedNoModule = true; return; }
  drv->startSingle();
  st = State::Measuring;
  tState = millis();
}

void Laser::pointer(bool on) {
  if (on) {
    if (!ensureReady()) { failedNoModule = true; return; }
    drv->pointer(true);
    st = State::Pointer;
    tState = millis();
  } else if (drv && isPowered) {
    drv->pointer(false);
    st = State::Idle;
  }
}

void Laser::togglePointer() { pointer(st != State::Pointer); }

void Laser::continuous(bool on) {
  if (on) {
    if (!ensureReady()) { failedNoModule = true; return; }
    drv->startContinuous();
    st = State::Continuous;
    tState = millis();
  } else if (drv) {
    drv->stop();
    st = isPowered || drv == &g_sim ? State::Idle : State::Off;
  }
}

void Laser::off() {
  if (drv && isPowered) drv->stop();
  power(false);
  st = State::Off;
}

bool Laser::poll(LaserResult& out) {
  if (failedNoModule) {
    failedNoModule = false;
    out = LaserResult();
    out.status = LaserStatus::NoModule;
    return true;
  }
  if (!drv) return false;
  if (drv->poll(out)) {
    tActivity = millis();
    if (st == State::Measuring) st = State::Idle;
    return true;
  }
  if (st == State::Measuring && millis() - tState > LASER_MEASURE_TIMEOUT_MS) {
    st = State::Idle;
    drv->stop();
    out = LaserResult();
    out.status = LaserStatus::Timeout;
    return true;
  }
  return false;
}

void Laser::loop() {
  uint32_t now = millis();
  if (st == State::Pointer && now - tState > LASER_POINTER_TIMEOUT_MS) pointer(false);
  if (isPowered && st == State::Idle && now - tActivity > LASER_IDLE_POWER_OFF_MS) off();
}
