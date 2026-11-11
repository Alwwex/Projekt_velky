# 5. Firmware (ESP32-C3)

Zdroják je ve složce [`firmware/`](../firmware/) – projekt pro **PlatformIO** (Arduino framework,
knihovny NimBLE-Arduino a U8g2).

| Soubor | Obsah |
|---|---|
| `include/config.h` | piny, offsety reference, časové limity, UUID Bluetooth služby |
| `src/main.cpp` | hlavní smyčka: tlačítka, měření, displej, spánek, sériová konzole |
| `src/laser.cpp` | ovladače laser modulů (JRT binární, ASCII, simulace) + správa napájení modulu |
| `src/ble.cpp` | Bluetooth LE GATT služba (viz [protokol](07-ble-protokol.md)) |
| `src/ui.cpp` | tlačítka, bzučák, LED, OLED |

## Nahrání

### A) Z prohlížeče (bez instalace)
Po zapnutí GitHub Pages (viz [aplikace](06-aplikace.md)) otevři `https://<tvuj-ucet>.github.io/<repozitar>/flash.html`
v Chrome/Edge na počítači, připoj laser USB kabelem a klikni **Nahrát firmware**.
Firmware pro tuto stránku sestaví GitHub Actions automaticky.

### B) PlatformIO
```bash
pip install platformio
cd firmware
pio run -e laserplan -t upload      # vlastní deska
pio run -e devkit -t upload         # ESP32-C3 SuperMini / DevKitM-1
pio device monitor                  # sériová konzole 115200 Bd
```
Pokud se nahrání nepovede: drž **MĚŘIT** (BOOT), vypni a zapni vypínač, pusť a zkus znovu.

## Ovládání

| Tlačítko | Krátce | Dlouze (0,7 s) | 3 s |
|---|---|---|---|
| MĚŘIT | 1. paprsek, 2. měření (v rychlém režimu hned měří) | průběžné měření SCAN | – |
| REŽIM | reference zadní / přední hrana | jednotky m / ft-in | uspat (probudí REŽIM) |

- Zaměřovací paprsek zhasne sám po 30 s, modul se vypne po 60 s nečinnosti.
- Bez USB a bez Bluetooth spojení přístroj po 10 min usne (hluboký spánek, odběr jednotky µA + stabilizátor).
- Displej: nahoře stav Bluetooth, laseru a baterie; uprostřed poslední měření; vpravo symbol
  reference (tečka vzadu/vpředu); dole 3 předchozí měření.

## Sériová konzole

| Příkaz | Význam |
|---|---|
| `help` | seznam příkazů |
| `m` / `p` / `c` / `x` | změř / paprsek / průběžně / stop |
| `off` | vypnout napájení laser modulu |
| `ref r` / `ref f` | reference zadní / přední hrana |
| `rear 93.0` / `front -2.0` | offset reference v mm |
| `units m` / `units ft` | jednotky na displeji |
| `quick 1` | tlačítko MĚŘIT měří hned (bez zaměření) |
| `driver 0..3` | ovladač laseru: 0 auto, 1 JRT, 2 ASCII, 3 simulace (restart) |
| `raw 1` | vypisovat surovou komunikaci s modulem (ladění) |
| `info` | verze, ovladač, offsety, baterie, USB, Bluetooth |

Nastavení se ukládá do flash (přežije vypnutí).

## Laserové moduly

### JRT (binární protokol)
Rámec `AA | adresa | registr(2) | počet slov(2) | data | součet`, součet = bajty od adresy po data (mod 256).

| Akce | Bajty |
|---|---|
| automatická detekce rychlosti | `55` |
| čti stav | `AA 80 00 00 80` |
| paprsek zap / vyp | `AA 00 01 BE 00 01 00 01 C1` / `AA 00 01 BE 00 01 00 00 C0` |
| jedno měření | `AA 00 00 20 00 01 00 00 21` |
| průběžné měření | `AA 00 00 20 00 01 00 04 25`, stop `58` |
| výsledek | `AA 00 00 22 00 03 [vzdálenost mm, 4 B] [kvalita 2 B] CS` |

### ASCII
Znaky `O` (paprsek), `C` (vypnout), `D` (měř), `F` (rychle měř); odpověď typu `D: 1.234m,0079`,
chyba `Er08`. Rychlost 9600 / 19200 / 115200 Bd.

> Výrobci protokoly občas mírně mění. Když tvůj modul nepracuje, zapni `raw 1`, porovnej s jeho
> datasheetem a případně uprav `src/laser.cpp` – parser je napsaný tolerantně a je krátký.

## Spotřeba (odhad)

| Stav | Proud |
|---|---|
| Čekání na spojení, laser vypnutý | ~ 20–30 mA |
| Měření (laser zapnutý) | + 80–150 mA podle modulu |
| Hluboký spánek | < 0,1 mA |

Baterie 1000 mAh tak vydrží celý den práce. Nabíjení USB-C cca 450 mA (≈ 2,5 h).
