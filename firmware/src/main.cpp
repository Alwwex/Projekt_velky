// ============================================================================
//  LaserPlan – Bluetooth laserový metr pro rychlý náčrt půdorysu
//
//  Ovládání:
//    MĚŘIT  krátce   – 1. stisk zapne zaměřovací paprsek, 2. stisk změří
//                      (v režimu "rychlé měření" měří hned)
//    MĚŘIT  dlouze   – průběžné měření (SCAN), dalším stiskem stop
//    REŽIM  krátce   – přepnout referenci: zadní / přední hrana
//    REŽIM  dlouze   – přepnout jednotky m / ft-in
//    REŽIM  3 s      – vypnout laser a uspat (probudí REŽIM)
//
//  Sériová konzole (USB, 115200): napiš "help".
// ============================================================================
#include <Arduino.h>
#include <Preferences.h>
#include <esp_sleep.h>

#include "ble.h"
#include "config.h"
#include "laser.h"
#include "ui.h"

extern bool g_laserRawDebug;

static Laser laser;
static Button btnMeas, btnMode;
static Preferences prefs;
static DisplayData dd;

struct Settings {
  float rearOffsetMm = REAR_OFFSET_MM_DEFAULT;
  float frontOffsetMm = FRONT_OFFSET_MM_DEFAULT;
  bool rear = true;
  uint8_t units = 0;
  uint8_t driver = LASER_DRIVER_DEFAULT;
  bool quick = false;
} cfg;

static uint16_t seq = 0;
static uint32_t tLastActivity = 0, tStatus = 0, tMessage = 0, tRender = 0;
static uint16_t batteryMv = 0;
static uint8_t batteryPct = 0;
static bool usbPresent = false;
static bool dirty = true;

// ----------------------------------------------------------------------------
static void loadSettings() {
  prefs.begin("laserplan", false);
  cfg.rearOffsetMm = prefs.getFloat("rearOfs", REAR_OFFSET_MM_DEFAULT);
  cfg.frontOffsetMm = prefs.getFloat("frontOfs", FRONT_OFFSET_MM_DEFAULT);
  cfg.rear = prefs.getBool("rear", true);
  cfg.units = prefs.getUChar("units", 0);
  cfg.driver = prefs.getUChar("driver", LASER_DRIVER_DEFAULT);
  cfg.quick = prefs.getBool("quick", false);
}

static void saveSettings() {
  prefs.putFloat("rearOfs", cfg.rearOffsetMm);
  prefs.putFloat("frontOfs", cfg.frontOffsetMm);
  prefs.putBool("rear", cfg.rear);
  prefs.putUChar("units", cfg.units);
  prefs.putUChar("driver", cfg.driver);
  prefs.putBool("quick", cfg.quick);
}

static void message(const char* m) {
  dd.message = m;
  tMessage = millis();
  dirty = true;
}

// ----------------------------------------------------------------------------
//  Baterie – Li-Ion křivka (zjednodušená)
// ----------------------------------------------------------------------------
static uint8_t lipoPercent(uint16_t mv) {
  static const uint16_t v[] = {3300, 3500, 3600, 3700, 3750, 3800, 3850, 3900, 4000, 4100, 4200};
  static const uint8_t p[] = {0, 5, 10, 20, 30, 40, 50, 60, 75, 90, 100};
  if (mv <= v[0]) return 0;
  for (int i = 1; i < 11; i++) {
    if (mv <= v[i]) return p[i - 1] + (uint32_t)(mv - v[i - 1]) * (p[i] - p[i - 1]) / (v[i] - v[i - 1]);
  }
  return 100;
}

static void readPower() {
  uint32_t acc = 0;
  for (int i = 0; i < 8; i++) acc += analogReadMilliVolts(PIN_BAT_ADC);
  batteryMv = (uint16_t)(acc / 8 * BAT_DIVIDER);
  batteryPct = lipoPercent(batteryMv);
  usbPresent = analogReadMilliVolts(PIN_VBUS_SENSE) > 1500;
}

static void sendStatus() {
  BleStatus s{};
  s.battery = batteryPct;
  s.batteryMv = batteryMv;
  Laser::State st = laser.state();
  s.flags = (usbPresent ? 1 : 0) | (laser.powered() ? 2 : 0) |
            (st == Laser::State::Pointer ? 4 : 0) | (st == Laser::State::Continuous ? 8 : 0) |
            (cfg.rear ? 16 : 0) | (cfg.quick ? 32 : 0);
  s.rearOffset = (int32_t)lroundf(cfg.rearOffsetMm * 100);
  s.frontOffset = (int32_t)lroundf(cfg.frontOffsetMm * 100);
  s.units = cfg.units;
  s.driver = laser.driverId() ? laser.driverId() : cfg.driver;
  s.fwMajor = 1;
  s.fwMinor = 0;
  ble::sendStatus(s);
  ble::setBattery(batteryPct);
}

// ----------------------------------------------------------------------------
//  Akce
// ----------------------------------------------------------------------------
static void doMeasureButton() {
  tLastActivity = millis();
  Laser::State st = laser.state();
  if (st == Laser::State::Continuous) {
    laser.continuous(false);
  } else if (cfg.quick || st == Laser::State::Pointer) {
    laser.measure();
  } else {
    laser.pointer(true);
  }
  dirty = true;
  sendStatus();
}

static void handleResult(const LaserResult& r) {
  tLastActivity = millis();
  BleMeasurement m{};
  m.seq = ++seq;
  m.status = (uint8_t)r.status;
  m.quality = r.quality;
  m.errCode = r.errCode;
  m.flags = (cfg.rear ? 1 : 0) | (laser.state() == Laser::State::Continuous ? 2 : 0);
  dd.lastStatus = r.status;
  if (r.status == LaserStatus::Ok) {
    float mm = r.mm + (cfg.rear ? cfg.rearOffsetMm : cfg.frontOffsetMm);
    m.distance = (int32_t)lroundf(mm * 10.0f);
    if (laser.state() != Laser::State::Continuous) {
      dd.prevMm[2] = dd.prevMm[1];
      dd.prevMm[1] = dd.prevMm[0];
      dd.prevMm[0] = dd.lastMm;
      buzzer::ok();
    }
    dd.lastMm = mm;
    Serial.printf("[mereni] #%u  %.1f mm  (kvalita %u)\n", m.seq, mm, r.quality);
  } else {
    buzzer::error();
    Serial.printf("[mereni] #%u  CHYBA status=%u kod=%u\n", m.seq, m.status, r.errCode);
  }
  ble::sendMeasurement(m);
  dirty = true;
}

static int32_t rdI32(const uint8_t* d) {
  return (int32_t)((uint32_t)d[0] | ((uint32_t)d[1] << 8) | ((uint32_t)d[2] << 16) | ((uint32_t)d[3] << 24));
}

static void handleBle(const BleCommand& c) {
  tLastActivity = millis();
  switch (c.op) {
    case CMD_MEASURE: laser.measure(); break;
    case CMD_POINTER_ON: laser.pointer(true); break;
    case CMD_POINTER_OFF: laser.pointer(false); break;
    case CMD_CONTINUOUS_ON: laser.continuous(true); break;
    case CMD_CONTINUOUS_OFF: laser.continuous(false); break;
    case CMD_LASER_OFF: laser.off(); break;
    case CMD_BEEP: buzzer::ok(); break;
    case CMD_SET_REFERENCE:
      if (c.len >= 1) { cfg.rear = c.data[0] != 0; saveSettings(); }
      break;
    case CMD_SET_REAR_OFS:
      if (c.len >= 4) { cfg.rearOffsetMm = rdI32(c.data) / 100.0f; saveSettings(); message("Offset ulozen"); }
      break;
    case CMD_SET_FRONT_OFS:
      if (c.len >= 4) { cfg.frontOffsetMm = rdI32(c.data) / 100.0f; saveSettings(); message("Offset ulozen"); }
      break;
    case CMD_SET_UNITS:
      if (c.len >= 1) { cfg.units = c.data[0] ? 1 : 0; saveSettings(); }
      break;
    case CMD_SET_QUICK:
      if (c.len >= 1) { cfg.quick = c.data[0] != 0; saveSettings(); }
      break;
    case CMD_SET_DRIVER:
      if (c.len >= 1 && c.data[0] <= 3) {
        cfg.driver = c.data[0];
        saveSettings();
        message("Restart...");
        delay(300);
        ESP.restart();
      }
      break;
  }
  dirty = true;
  sendStatus();
}

static void goToSleep() {
  Serial.println("[power] usínám – probudí tlačítko REŽIM");
  laser.off();
  message("Spim... (REZIM)");
  dd.connected = ble::connected();
  display::render(dd);
  delay(800);
  display::sleep();
  // ESP32-C3 umí probouzet z deep sleep jen piny GPIO0–5 → REŽIM (GPIO4)
  esp_deep_sleep_enable_gpio_wakeup(1ULL << PIN_BTN_MODE, ESP_GPIO_WAKEUP_GPIO_LOW);
  esp_deep_sleep_start();
}

// ----------------------------------------------------------------------------
//  Sériová konzole (pro oživení a ladění)
// ----------------------------------------------------------------------------
static void console() {
  static String line;
  while (Serial.available()) {
    char ch = (char)Serial.read();
    if (ch != '\n' && ch != '\r') { line += ch; continue; }
    line.trim();
    if (!line.length()) continue;
    String cmd = line;
    line = "";
    if (cmd == "help") {
      Serial.println("prikazy: m (mer), p (paprsek), c (prubezne), x (stop), off,\n"
                     "         ref r|f, rear <mm>, front <mm>, units m|ft, quick 0|1,\n"
                     "         driver 0-3 (auto/JRT/ASCII/sim), raw 0|1, info, beep");
    } else if (cmd == "m") laser.measure();
    else if (cmd == "p") laser.togglePointer();
    else if (cmd == "c") laser.continuous(true);
    else if (cmd == "x") laser.continuous(false);
    else if (cmd == "off") laser.off();
    else if (cmd == "beep") buzzer::ok();
    else if (cmd.startsWith("ref ")) { cfg.rear = cmd.endsWith("r"); saveSettings(); }
    else if (cmd.startsWith("rear ")) { cfg.rearOffsetMm = cmd.substring(5).toFloat(); saveSettings(); }
    else if (cmd.startsWith("front ")) { cfg.frontOffsetMm = cmd.substring(6).toFloat(); saveSettings(); }
    else if (cmd.startsWith("units ")) { cfg.units = cmd.endsWith("ft") ? 1 : 0; saveSettings(); }
    else if (cmd.startsWith("quick ")) { cfg.quick = cmd.endsWith("1"); saveSettings(); }
    else if (cmd.startsWith("raw ")) g_laserRawDebug = cmd.endsWith("1");
    else if (cmd.startsWith("driver ")) {
      cfg.driver = (uint8_t)cmd.substring(7).toInt();
      saveSettings();
      ESP.restart();
    } else if (cmd == "info") {
      readPower();
      Serial.printf("%s fw %s | laser: %s | ref: %s | zadni ofs %.2f mm | predni ofs %.2f mm\n"
                    "baterie %u mV (%u %%) | USB %s | BLE %s\n",
                    ble::deviceName(), LP_FW_VERSION, laser.driverName(), cfg.rear ? "zadni" : "predni",
                    cfg.rearOffsetMm, cfg.frontOffsetMm, batteryMv, batteryPct,
                    usbPresent ? "ano" : "ne", ble::connected() ? "pripojeno" : "ceka");
    } else {
      Serial.println("neznamy prikaz – napis help");
    }
    dirty = true;
  }
}

// ----------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(50);
  Serial.printf("\nLaserPlan %s\n", LP_FW_VERSION);
  analogReadResolution(12);
  loadSettings();

  led::begin();
  buzzer::begin();
  btnMeas.begin(PIN_BTN_MEAS);
  btnMode.begin(PIN_BTN_MODE);
  display::begin();
  laser.begin(cfg.driver);
  ble::begin();
  readPower();

  dd.name = ble::deviceName();
  buzzer::hello();
  tLastActivity = millis();
  // po probuzení tlačítkem počkej na jeho uvolnění
  while (digitalRead(PIN_BTN_MODE) == LOW && millis() < 3000) delay(10);
}

void loop() {
  uint32_t now = millis();

  switch (btnMeas.update()) {
    case Button::Short: buzzer::click(); doMeasureButton(); break;
    case Button::Long:
      buzzer::click();
      laser.continuous(laser.state() != Laser::State::Continuous);
      tLastActivity = now;
      dirty = true;
      sendStatus();
      break;
    default: break;
  }
  switch (btnMode.update()) {
    case Button::Short:
      buzzer::click();
      cfg.rear = !cfg.rear;
      saveSettings();
      message(cfg.rear ? "Ref: ZADNI hrana" : "Ref: PREDNI hrana");
      tLastActivity = now;
      sendStatus();
      break;
    case Button::Long:
      cfg.units ^= 1;
      saveSettings();
      message(cfg.units ? "Jednotky: ft-in" : "Jednotky: metry");
      tLastActivity = now;
      sendStatus();
      break;
    case Button::VeryLong: goToSleep(); break;
    default: break;
  }

  BleCommand cmd;
  while (ble::popCommand(cmd)) handleBle(cmd);

  LaserResult r;
  if (laser.poll(r)) handleResult(r);
  laser.loop();

  console();
  buzzer::loop();
  led::loop(ble::connected());

  if (now - tStatus > STATUS_PERIOD_MS) {
    tStatus = now;
    readPower();
    sendStatus();
    dirty = true;
  }
  if (dd.message && now - tMessage > 1500) {
    dd.message = nullptr;
    dirty = true;
  }
  bool conn = ble::connected();
  if (conn != dd.connected) {
    dd.connected = conn;
    if (conn) buzzer::hello();
    dirty = true;
    sendStatus();
  }
  if (laser.state() != dd.laser) { dd.laser = laser.state(); dirty = true; }
  if (dirty && now - tRender > 60) {
    dd.rear = cfg.rear;
    dd.units = cfg.units;
    dd.battery = batteryPct;
    dd.usb = usbPresent;
    display::render(dd);
    tRender = now;
    dirty = false;
  }

  if (conn) tLastActivity = now;
  if (!usbPresent && now - tLastActivity > SLEEP_AFTER_MS) goToSleep();
  delay(2);
}
