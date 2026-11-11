#pragma once
// ============================================================================
//  Uživatelské rozhraní: tlačítka, bzučák, LED, OLED displej
// ============================================================================
#include <Arduino.h>

#include "laser.h"

class Button {
 public:
  enum Event : uint8_t { None, Short, Long, VeryLong };
  void begin(int pin);
  Event update();               // volat často z loop()
  bool isDown() const { return down; }
 private:
  int pin = -1;
  bool down = false, longSent = false, veryLongSent = false;
  uint32_t tChange = 0, tDown = 0;
  bool raw = false;
};

namespace buzzer {
void begin();
void ok();          // krátké pípnutí – úspěšné měření
void error();       // dvojité hluboké – chyba
void click();       // klik tlačítka
void hello();       // start / připojení
void loop();
}  // namespace buzzer

namespace led {
void begin();
void loop(bool connected);
}  // namespace led

struct DisplayData {
  float lastMm = NAN;           // poslední platné měření (s offsetem)
  float prevMm[3] = {NAN, NAN, NAN};
  LaserStatus lastStatus = LaserStatus::Ok;
  bool rear = true;             // reference zadní hrana
  bool connected = false;
  bool usb = false;
  uint8_t battery = 0;
  uint8_t units = 0;            // 0 m, 1 ft-in
  Laser::State laser = Laser::State::Off;
  const char* name = "";
  const char* message = nullptr;  // krátká hláška (např. "Kalibrace")
};

namespace display {
bool begin();
void render(const DisplayData& d);
void sleep();
}  // namespace display

// Formátování (sdíleno se sériovou konzolí)
void formatDistance(float mm, uint8_t units, char* out, size_t n);
