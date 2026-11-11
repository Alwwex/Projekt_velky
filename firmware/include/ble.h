#pragma once
// ============================================================================
//  Bluetooth LE – GATT služba LaserPlan (viz docs/ble-protokol.md)
// ============================================================================
#include <Arduino.h>

// Příkazy zapisované do charakteristiky CONTROL (první bajt)
enum BleCmd : uint8_t {
  CMD_MEASURE        = 0x01,
  CMD_POINTER_ON     = 0x02,
  CMD_POINTER_OFF    = 0x03,
  CMD_CONTINUOUS_ON  = 0x04,
  CMD_CONTINUOUS_OFF = 0x05,
  CMD_SET_REFERENCE  = 0x06,   // + uint8 (0 = přední hrana, 1 = zadní hrana)
  CMD_SET_REAR_OFS   = 0x07,   // + int32 LE v setinách mm
  CMD_BEEP           = 0x08,
  CMD_SET_UNITS      = 0x09,   // + uint8 (0 = metry, 1 = stopy/palce) – jen OLED
  CMD_SET_FRONT_OFS  = 0x0A,   // + int32 LE v setinách mm
  CMD_SET_DRIVER     = 0x0B,   // + uint8 (0 auto, 1 JRT, 2 ASCII, 3 simulace)
  CMD_LASER_OFF      = 0x0C,   // úplně vypnout napájení modulu
  CMD_SET_QUICK      = 0x0D,   // + uint8 (1 = MĚŘIT měří hned bez zaměření)
};

struct BleCommand {
  uint8_t op;
  uint8_t len;
  uint8_t data[18];
};

// Měření – 12 bajtů, little-endian
struct __attribute__((packed)) BleMeasurement {
  uint16_t seq;          // pořadové číslo
  int32_t distance;      // v desetinách mm (0,1 mm), už s offsetem reference
  uint16_t quality;      // kvalita signálu
  uint8_t status;        // LaserStatus
  uint8_t flags;         // bit0 = zadní reference, bit1 = průběžné měření
  uint16_t errCode;      // kód chyby modulu
};

// Stav zařízení – 16 bajtů, little-endian
struct __attribute__((packed)) BleStatus {
  uint8_t battery;       // %
  uint16_t batteryMv;    // mV
  uint8_t flags;         // bit0 USB, bit1 laser napájen, bit2 paprsek, bit3 průběžně,
                         // bit4 zadní reference, bit5 rychlé měření
  int32_t rearOffset;    // setiny mm
  int32_t frontOffset;   // setiny mm
  uint8_t units;         // 0 = m, 1 = ft
  uint8_t driver;        // 0 nic, 1 JRT, 2 ASCII, 3 simulace
  uint8_t fwMajor;
  uint8_t fwMinor;
};

namespace ble {
void begin();
bool connected();
bool popCommand(BleCommand& out);
void sendMeasurement(const BleMeasurement& m);
void sendStatus(const BleStatus& s);
void setBattery(uint8_t percent);
const char* deviceName();
}  // namespace ble
