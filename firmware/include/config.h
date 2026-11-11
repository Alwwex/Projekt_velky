#pragma once
// ============================================================================
//  LaserPlan – konfigurace pinů a výchozích hodnot
// ============================================================================
#include <Arduino.h>

#define LP_FW_VERSION "1.0.0"
#define LP_MODEL      "LaserPlan BLE"

// ---------------------------------------------------------------- piny
// Stejné zapojení platí pro vlastní DPS i pro ESP32-C3 SuperMini/DevKitM-1.
static constexpr int PIN_BAT_ADC    = 0;   // dělič 100k/100k z baterie (ADC1_CH0)
static constexpr int PIN_VBUS_SENSE = 1;   // dělič 47k/68k z USB 5 V
static constexpr int PIN_LASER_AUX  = 2;   // volitelný pin modulu (PWR/EN), strap – pull-up
static constexpr int PIN_LASER_EN   = 3;   // 1 = napájení laser modulu zapnuto
static constexpr int PIN_BTN_MODE   = 4;   // tlačítko REŽIM (aktivní v nule, budí z režimu spánku)
static constexpr int PIN_I2C_SDA    = 5;   // OLED
static constexpr int PIN_I2C_SCL    = 6;   // OLED
static constexpr int PIN_BUZZER     = 10;  // pasivní bzučák přes MOSFET
static constexpr int PIN_BTN_MEAS   = 9;   // tlačítko MĚŘIT (= BOOT)
static constexpr int PIN_LASER_RX   = 20;  // ESP RX  <- TX modulu
static constexpr int PIN_LASER_TX   = 21;  // ESP TX  -> RX modulu

#if defined(LP_BOARD_DEVKIT)
static constexpr int  PIN_LED        = 8;     // modrá LED na SuperMini
static constexpr bool LED_ACTIVE_LOW = true;
#else
static constexpr int  PIN_LED        = 7;     // modrá LED "BT" na DPS
static constexpr bool LED_ACTIVE_LOW = false;
#endif

// ---------------------------------------------------------------- laser
// Typ modulu: 0 = automatická detekce, 1 = JRT binární protokol,
//             2 = ASCII protokol ("D"/"O"/"C"), 3 = simulace (bez modulu)
static constexpr uint8_t LASER_DRIVER_DEFAULT = 0;

// Vzdálenost (mm) od nulového bodu modulu k ZADNÍ hraně krabičky.
// Přesně se nastaví kalibrací v aplikaci (Nastavení -> Kalibrace).
static constexpr float REAR_OFFSET_MM_DEFAULT  = 93.0f;   // krabicka.scad: 93 mm
// Korekce pro měření od PŘEDNÍ hrany (obvykle 0).
static constexpr float FRONT_OFFSET_MM_DEFAULT = -2.0f;  // přední stěna 2 mm

static constexpr uint32_t LASER_MEASURE_TIMEOUT_MS = 4000;
static constexpr uint32_t LASER_POINTER_TIMEOUT_MS = 30000;  // zaměřovací paprsek
static constexpr uint32_t LASER_IDLE_POWER_OFF_MS  = 60000;  // vypnout modul

// ---------------------------------------------------------------- napájení
static constexpr float    BAT_DIVIDER          = 2.0f;     // 100k/100k
static constexpr uint32_t SLEEP_AFTER_MS       = 10UL * 60UL * 1000UL;  // 10 min
static constexpr uint32_t STATUS_PERIOD_MS     = 5000;

// ---------------------------------------------------------------- OLED
// Na DPS je záhlaví OLED směrem DOZADU (k uživateli), proto je obraz
// otočený o 180° (hodnota 2). Pokud máš text vzhůru nohama, dej 0.
static constexpr uint8_t OLED_ROTATION = 2;
static constexpr uint8_t OLED_I2C_ADDR = 0x3C;

// ---------------------------------------------------------------- BLE
// Vlastní služba "LaserPlan" (viz docs/ble-protokol.md)
#define LP_SERVICE_UUID     "4c500001-6c61-7365-7270-6c616e000000"
#define LP_MEASUREMENT_UUID "4c500002-6c61-7365-7270-6c616e000000"
#define LP_CONTROL_UUID     "4c500003-6c61-7365-7270-6c616e000000"
#define LP_STATUS_UUID      "4c500004-6c61-7365-7270-6c616e000000"
