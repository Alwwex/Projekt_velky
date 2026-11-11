#pragma once
// ============================================================================
//  Ovladače laserových dálkoměrných modulů (UART)
// ============================================================================
#include <Arduino.h>

enum class LaserStatus : uint8_t {
  Ok = 0,
  Error = 1,        // obecná chyba modulu
  WeakSignal = 2,   // slabý odraz (tmavý/lesklý povrch, moc daleko)
  OutOfRange = 3,   // mimo rozsah
  Timeout = 4,      // modul neodpověděl
  NoModule = 5,     // modul nenalezen
};

struct LaserResult {
  LaserStatus status = LaserStatus::Timeout;
  float mm = 0;           // vzdálenost od nuly modulu (mm)
  uint16_t quality = 0;   // kvalita signálu (dle modulu)
  uint16_t errCode = 0;   // surový kód chyby z modulu
};

class LaserDriver {
 public:
  virtual ~LaserDriver() {}
  virtual const char* name() const = 0;
  virtual uint8_t id() const = 0;
  // Pokus o detekci modulu (smí blokovat, volá se jen při startu).
  virtual bool probe(HardwareSerial& s) = 0;
  virtual void begin(HardwareSerial& s) { ser = &s; }
  virtual void pointer(bool on) = 0;          // zaměřovací paprsek
  virtual void startSingle() = 0;             // jedno měření
  virtual void startContinuous() = 0;         // průběžné měření
  virtual void stop() = 0;                    // zastavit + vypnout paprsek
  virtual bool poll(LaserResult& out) = 0;    // true = máme výsledek
 protected:
  HardwareSerial* ser = nullptr;
};

// --- JRT (Chengdu JRT Meter) binární protokol: 0xAA ... checksum
class JrtLaser : public LaserDriver {
 public:
  const char* name() const override { return "JRT"; }
  uint8_t id() const override { return 1; }
  bool probe(HardwareSerial& s) override;
  void pointer(bool on) override;
  void startSingle() override;
  void startContinuous() override;
  void stop() override;
  bool poll(LaserResult& out) override;
 private:
  void writeReg(uint16_t reg, uint16_t value);
  bool parse(LaserResult& out, bool& isResult);
  uint8_t buf[40];
  size_t n = 0;
};

// --- ASCII protokol (moduly ovládané znaky "O", "C", "D", "F")
class AsciiLaser : public LaserDriver {
 public:
  const char* name() const override { return "ASCII"; }
  uint8_t id() const override { return 2; }
  bool probe(HardwareSerial& s) override;
  void pointer(bool on) override;
  void startSingle() override;
  void startContinuous() override;
  void stop() override;
  bool poll(LaserResult& out) override;
 private:
  bool parseLine(const char* line, LaserResult& out);
  char line[64];
  size_t n = 0;
  bool continuous = false;
};

// --- Simulace (pro test bez modulu – vrací rozměry "typického pokoje")
class SimLaser : public LaserDriver {
 public:
  const char* name() const override { return "SIM"; }
  uint8_t id() const override { return 3; }
  bool probe(HardwareSerial&) override { return true; }
  void pointer(bool) override {}
  void startSingle() override { due = millis() + 450; pending = true; continuous = false; }
  void startContinuous() override { startSingle(); continuous = true; }
  void stop() override { pending = false; continuous = false; }
  bool poll(LaserResult& out) override;
 private:
  uint32_t due = 0;
  bool pending = false, continuous = false;
  uint8_t idx = 0;
};

// ============================================================================
//  Správce laseru – napájení, výběr ovladače, stav, časové limity
// ============================================================================
class Laser {
 public:
  enum class State : uint8_t { Off, Idle, Pointer, Measuring, Continuous };

  void begin(uint8_t preferredDriver);
  void loop();
  bool poll(LaserResult& out);     // true = nový výsledek k odeslání

  void measure();                  // jedno měření
  void togglePointer();
  void pointer(bool on);
  void continuous(bool on);
  void off();

  State state() const { return st; }
  bool powered() const { return isPowered; }
  const char* driverName() const { return drv ? drv->name() : "-"; }
  uint8_t driverId() const { return drv ? drv->id() : 0; }

 private:
  void power(bool on);
  bool ensureReady();
  LaserDriver* detect();

  LaserDriver* drv = nullptr;
  uint8_t preferred = 0;
  State st = State::Off;
  bool isPowered = false;
  bool detected = false;
  bool failedNoModule = false;
  uint32_t tState = 0;       // čas posledního přechodu
  uint32_t tActivity = 0;    // poslední aktivita (pro vypnutí modulu)
};
