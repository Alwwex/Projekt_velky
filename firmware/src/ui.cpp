#include "ui.h"

#include <U8g2lib.h>
#include <Wire.h>

#include "config.h"

// ============================================================================
//  Tlačítka (odrušení, krátký / dlouhý / velmi dlouhý stisk)
// ============================================================================
void Button::begin(int p) {
  pin = p;
  pinMode(pin, INPUT_PULLUP);
}

Button::Event Button::update() {
  bool r = digitalRead(pin) == LOW;
  uint32_t now = millis();
  if (r != raw) {
    raw = r;
    tChange = now;
  }
  if (now - tChange < 25) return None;          // odrušení zákmitů
  if (raw && !down) {
    down = true;
    tDown = now;
    longSent = veryLongSent = false;
  } else if (!raw && down) {
    down = false;
    if (!longSent) return Short;
  } else if (down) {
    if (!longSent && now - tDown > 700) { longSent = true; return Long; }
    if (!veryLongSent && now - tDown > 3000) { veryLongSent = true; return VeryLong; }
  }
  return None;
}

// ============================================================================
//  Bzučák (pasivní – generujeme tón PWM)
// ============================================================================
namespace buzzer {
struct Note { uint16_t f, ms; };
static Note seq[6];
static uint8_t len = 0, pos = 0;
static uint32_t tNext = 0;
static bool active = false;

static void play(std::initializer_list<Note> notes) {
  len = 0;
  for (auto n : notes) if (len < 6) seq[len++] = n;
  pos = 0;
  tNext = millis();
  active = true;
}

void begin() {
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
}
void ok() { play({{2700, 70}}); }
void error() { play({{900, 120}, {0, 60}, {700, 180}}); }
void click() { play({{3200, 15}}); }
void hello() { play({{1800, 60}, {0, 30}, {2400, 60}, {0, 30}, {3000, 80}}); }

void loop() {
  if (!active) return;
  uint32_t now = millis();
  if ((int32_t)(now - tNext) < 0) return;
  noTone(PIN_BUZZER);
  if (pos >= len) { active = false; return; }
  Note n = seq[pos++];
  if (n.f) tone(PIN_BUZZER, n.f);
  tNext = now + n.ms;
}
}  // namespace buzzer

// ============================================================================
//  Stavová LED – bliká při čekání na spojení, svítí při připojení
// ============================================================================
namespace led {
static void set(bool on) { digitalWrite(PIN_LED, (on ^ LED_ACTIVE_LOW) ? HIGH : LOW); }
void begin() {
  pinMode(PIN_LED, OUTPUT);
  set(false);
}
void loop(bool connected) {
  if (connected) { set(true); return; }
  set((millis() % 2000) < 60);
}
}  // namespace led

// ============================================================================
//  Formátování vzdálenosti
// ============================================================================
void formatDistance(float mm, uint8_t units, char* out, size_t n) {
  if (isnan(mm)) { snprintf(out, n, "---"); return; }
  if (units == 1) {
    // stopy a palce s přesností 1/16"
    float inches = mm / 25.4f;
    int sixteenths = (int)lroundf(inches * 16.0f);
    int ft = sixteenths / (12 * 16);
    sixteenths -= ft * 12 * 16;
    int in = sixteenths / 16;
    int frac = sixteenths % 16;
    int den = 16;
    while (frac && (frac % 2 == 0)) { frac /= 2; den /= 2; }
    if (frac) snprintf(out, n, "%d' %d %d/%d\"", ft, in, frac, den);
    else snprintf(out, n, "%d' %d\"", ft, in);
  } else {
    snprintf(out, n, "%.3f", mm / 1000.0f);
  }
}

// ============================================================================
//  OLED SSD1306 128x64 (I2C)
// ============================================================================
namespace display {
static U8G2_SSD1306_128X64_NONAME_F_HW_I2C* u8g2 = nullptr;
static bool present = false;

bool begin() {
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 400000);
  Wire.beginTransmission(OLED_I2C_ADDR);
  present = Wire.endTransmission() == 0;
  if (!present) {
    Serial.println("[oled] displej nenalezen (to nevadí, funguje i bez něj)");
    return false;
  }
  const u8g2_cb_t* rot = OLED_ROTATION == 2 ? U8G2_R2 : U8G2_R0;
  u8g2 = new U8G2_SSD1306_128X64_NONAME_F_HW_I2C(rot, U8X8_PIN_NONE, PIN_I2C_SCL, PIN_I2C_SDA);
  u8g2->setI2CAddress(OLED_I2C_ADDR << 1);
  u8g2->begin();
  u8g2->setContrast(200);
  return true;
}

static void battery(int x, int y, uint8_t pct, bool usb) {
  u8g2->drawFrame(x, y, 18, 9);
  u8g2->drawBox(x + 18, y + 2, 2, 5);
  int w = (pct * 14 + 50) / 100;
  u8g2->drawBox(x + 2, y + 2, w, 5);
  if (usb) {
    u8g2->setFont(u8g2_font_5x7_tr);
    u8g2->drawStr(x - 16, y + 8, "USB");
  }
}

static const char* statusText(LaserStatus s) {
  switch (s) {
    case LaserStatus::Ok: return "";
    case LaserStatus::WeakSignal: return "Slaby signal";
    case LaserStatus::OutOfRange: return "Mimo rozsah";
    case LaserStatus::Timeout: return "Bez odpovedi";
    case LaserStatus::NoModule: return "Laser nenalezen";
    default: return "Chyba mereni";
  }
}

void render(const DisplayData& d) {
  if (!present) return;
  char buf[24];
  u8g2->clearBuffer();

  // --- horní lišta
  u8g2->setFont(u8g2_font_5x7_tr);
  u8g2->drawStr(0, 7, d.connected ? "BT *" : "BT -");
  const char* las = d.laser == Laser::State::Pointer ? "LASER" :
                    d.laser == Laser::State::Continuous ? "SCAN" :
                    d.laser == Laser::State::Measuring ? "MERIM" : "";
  u8g2->drawStr(28, 7, las);
  battery(106, 0, d.battery, d.usb);
  u8g2->drawHLine(0, 10, 128);

  // --- hlavní hodnota
  if (d.message) {
    u8g2->setFont(u8g2_font_7x14B_tr);
    u8g2->drawStr(0, 34, d.message);
  } else if (d.lastStatus != LaserStatus::Ok) {
    u8g2->setFont(u8g2_font_7x14B_tr);
    u8g2->drawStr(0, 34, statusText(d.lastStatus));
  } else {
    formatDistance(d.lastMm, d.units, buf, sizeof buf);
    if (d.units == 1) {
      u8g2->setFont(u8g2_font_logisoso16_tr);
      u8g2->drawStr(0, 38, buf);
    } else {
      u8g2->setFont(u8g2_font_logisoso24_tn);
      int w = u8g2->drawStr(0, 40, buf);
      u8g2->setFont(u8g2_font_7x14B_tr);
      u8g2->drawStr(w + 4, 40, "m");
    }
  }

  // --- reference (symbol přístroje s tečkou vpředu/vzadu)
  int rx = 108, ry = 26;
  u8g2->drawFrame(rx, ry, 18, 8);
  if (d.rear) u8g2->drawBox(rx + 14, ry - 2, 4, 12);   // zadní hrana
  else u8g2->drawBox(rx, ry - 2, 4, 12);               // přední hrana

  // --- předchozí měření
  u8g2->drawHLine(0, 46, 128);
  u8g2->setFont(u8g2_font_5x7_tr);
  int x = 0;
  for (int i = 0; i < 3; i++) {
    formatDistance(d.prevMm[i], d.units, buf, sizeof buf);
    u8g2->drawStr(x, 55, buf);
    x += 43;
  }
  u8g2->drawStr(0, 64, d.name);
  u8g2->sendBuffer();
}

void sleep() {
  if (present) u8g2->setPowerSave(1);
}
}  // namespace display
