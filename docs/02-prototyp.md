# 2. Prototyp bez vlastní desky (ESP32-C3 SuperMini)

Nejrychlejší cesta k fungujícímu měření: vývojová deska ESP32-C3 + laser modul na nepájivém poli.
Firmware je pro to připravený (prostředí `devkit`), piny jsou **stejné jako na vlastní desce**.

## Zapojení

| ESP32-C3 SuperMini | Kam | Poznámka |
|---|---|---|
| **3V3** | laser **VCC** | jen pro moduly napájené 3,3 V (zkontroluj odběr – SuperMini dá ~ 300 mA) |
| **GND** | laser **GND**, OLED GND, tlačítka, bzučák − | |
| **GPIO20** (RX) | laser **TX** | data z modulu |
| **GPIO21** (TX) | laser **RX** | příkazy do modulu |
| **GPIO3** | volitelně: spínač napájení laseru (MOSFET) | bez spínače nech laser napájený trvale |
| **GPIO2** | laser **PWR/EN** (má-li ho) | |
| **GPIO9** | tlačítko **MĚŘIT** → GND | na SuperMini je to tlačítko **BOOT** – funguje rovnou |
| **GPIO4** | tlačítko **REŽIM** → GND | interní pull-up |
| **GPIO5** | OLED **SDA** | |
| **GPIO6** | OLED **SCL** | OLED VCC na 3V3 |
| **GPIO10** | bzučák + (pasivní; ideálně přes tranzistor) | druhý vývod na GND |
| **GPIO8** | modrá LED na desce | stav Bluetooth |
| **GPIO0** | baterie přes dělič 100k/100k | volitelné (měření baterie) |

> Pokud laser modul potřebuje víc proudu nebo 5 V napájení, napájej ho z pinu **5V** (USB) –
> ale **jen pokud má UART logiku 3,3 V**. Při pochybnostech změř napětí na jeho TX pinu (musí být ≤ 3,3 V).

## Nahrání firmwaru

```bash
pip install platformio
cd firmware
pio run -e devkit -t upload
pio device monitor        # konzole 115200 Bd, napiš "help"
```

V konzoli vyzkoušej:

```
raw 1      # vypisuj surovou komunikaci s laserem
m          # změř
info       # stav: nalezený ovladač laseru, baterie, BLE
driver 3   # simulace laseru (když modul ještě nemáš)
```

Pak otevři aplikaci, **Připojit laser → Připojit přes Bluetooth** a vyber `LaserPlan-XXXX`.
