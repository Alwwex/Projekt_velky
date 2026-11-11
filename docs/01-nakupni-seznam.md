# 1. Nákupní seznam

Ceny jsou **orientační** (v Kč, bez poštovného) a hodně se liší podle obchodu a kurzu.
Elektronické součástky seženeš v **LCSC**, **TME**, **Mouser**, **GM electronic**; moduly a baterie
nejlevněji na **AliExpressu**. Kompletní kusovník desky (všechny rezistory, kondenzátory…) je
v [`hardware/vyroba/bom.md`](../hardware/vyroba/bom.md) a jako CSV v [`hardware/vyroba/bom.csv`](../hardware/vyroba/bom.csv).

## Hlavní díly

| Díl | Ks | Cena cca | Poznámka |
|---|---|---|---|
| **Laserový dálkoměrný modul s UART** (např. JRT „laser distance sensor TTL“, 40–100 m, ±1–3 mm) | 1 | 500–1 200 Kč | **Nutné:** UART (TTL) s logikou **3,3 V**, napájení 3,3 V (nebo 3,6–5 V – viz propojka JP1). Vyhni se modulům jen s PWM/I2C nebo s 5V logikou. Moduly VL53L0X/L1X a TF-Luna jsou na stavbu nepřesné (centimetry). |
| **Deska plošného spoje** (5 ks, 2 vrstvy, 90 × 44 mm) | 1 sada | 100–400 Kč | JLCPCB / PCBWay / Seeed – nahraješ [`laserplan-gerber.zip`](../hardware/vyroba/laserplan-gerber.zip) |
| **ESP32-C3-WROOM-02-N4** | 1 | 60–100 Kč | modul s Bluetooth LE 5.0 |
| **OLED 0,96" SSD1306 128×64, I2C** (4 piny) | 1 | 60–120 Kč | pozor na pořadí pinů – musí být **GND, VCC, SCL, SDA** |
| **Li-Pol 1S 3,7 V, ~1000 mAh, 8 × 30 × 40 mm** („803040“) s konektorem **JST-PH 2,0** | 1 | 120–200 Kč | s ochranným obvodem; **zkontroluj polaritu** |
| Malé součástky na desku (rezistory, kondenzátory, MCP73831, AP2112K, USBLC6, AO3400A/AO3401A, LED, diody) | sada | 150–300 Kč | podle [kusovníku](../hardware/vyroba/bom.md); 0805 se dobře pájí ručně |
| Konektor **USB-C 16pin** HRO TYPE-C-31-M-12 | 1 | 10–20 Kč | |
| Posuvný vypínač **C&K OS102011MA1QN1** (úhlový) | 1 | 15–30 Kč | |
| Tlačítka **6 × 6 mm, výška 13 mm** (THT) | 2 | 10 Kč | |
| Pasivní bzučák **12 × 9,5 mm**, 3 V | 1 | 10–20 Kč | pasivní (bez generátoru) |
| Dutinková lišta 1×4 (2,54 mm, výška 8,5 mm) | 1 | 5 Kč | pro OLED |
| Kolíková lišta 1×5 + kabel Dupont / JST k laseru | 1 | 10–30 Kč | podle konektoru tvého modulu |
| JST-PH 2pin konektor do DPS **B2B-PH-K** (svislý) | 1 | 5 Kč | baterie se do něj zasune |
| Šrouby **M2.5 × 30** (zápustná/čočková hlava) | 4 | 20 Kč | stáhnou víko + DPS + spodek |
| Filament PETG/PLA | ~60 g | 30 Kč | krabička + 2 hmatníky |
| Oboustranná lepicí páska (pěnová) | | | přichycení laseru a baterie |

**Celkem zhruba 1 200–2 500 Kč** podle laserového modulu.

## Nářadí

- mikropájka s tenkým hrotem, cín 0,5 mm, **tavidlo** (flux), pinzeta, odsávačka / knot
- pro USB-C konektor a modul ESP32 se hodí **horkovzdušná stanice** a pájecí pasta
  (jde to i mikropájkou – viz [sestavení](04-sestaveni.md)), případně si nech SMD osadit v JLCPCB
- multimetr
- USB-C kabel (data), počítač s Chrome/Edge nebo PlatformIO
- 3D tiskárna (nebo tisk v tiskové službě)

## Pokud chceš nejdřív jen vyzkoušet (bez vlastní desky)

| Díl | Cena cca |
|---|---|
| **ESP32-C3 SuperMini** (nebo ESP32-C3-DevKitM-1) | 80–150 Kč |
| laserový modul (viz výše) | 500–1 200 Kč |
| volitelně OLED 0,96", tlačítko, pasivní bzučák, nepájivé pole, kablíky | 150 Kč |

Zapojení je v [02-prototyp.md](02-prototyp.md).
