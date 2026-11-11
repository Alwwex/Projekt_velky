"""
LaserPlan – zapojení desky (jediný zdroj pravdy).

Z tohoto souboru se generuje:
  * schéma KiCad   (gen_schematic.py)
  * plošný spoj    (gen_pcb.py)
  * kusovník / BOM (gen_bom.py)

Každá součástka:  ref, symbol (knihovna:jméno), hodnota, footprint,
                  výrobce, MPN, popis, blok (pro rozložení schématu),
                  pins = {číslo pinu: síť}
"""

# ---------------------------------------------------------------------------
# Footprinty, které se opakují
# ---------------------------------------------------------------------------
R0805 = "Resistor_SMD:R_0805_2012Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
LED0805 = "LED_SMD:LED_0805_2012Metric"
SOT23 = "Package_TO_SOT_SMD:SOT-23"
SOT235 = "Package_TO_SOT_SMD:SOT-23-5"
SOT236 = "Package_TO_SOT_SMD:SOT-23-6"
SOD123 = "Diode_SMD:D_SOD-123"


def R(ref, value, a, b, block, desc="", mpn=None):
    return dict(ref=ref, symbol="Device:R", value=value, footprint=R0805,
                manufacturer="UNI-ROYAL / Yageo", mpn=mpn or f"0805 {value} 1%",
                desc=desc or "Rezistor 0805", block=block, pins={"1": a, "2": b}, smd=True)


def C(ref, value, a, b, block, desc="", mpn=None):
    return dict(ref=ref, symbol="Device:C", value=value, footprint=C0805,
                manufacturer="Samsung / Murata", mpn=mpn or f"0805 {value} X5R/X7R ≥10V",
                desc=desc or "Kondenzátor MLCC 0805", block=block, pins={"1": a, "2": b}, smd=True)


def LED(ref, color, anode, cathode, block, desc=""):
    return dict(ref=ref, symbol="Device:LED", value=f"LED {color}", footprint=LED0805,
                manufacturer="Everlight / Hubei", mpn=f"LED 0805 {color}",
                desc=desc, block=block, pins={"1": cathode, "2": anode}, smd=True)


PARTS = [
    # ---------------------------------------------------------------- USB-C
    dict(ref="J1", symbol="Connector:USB_C_Receptacle_USB2.0_14P", value="USB-C",
         footprint="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
         manufacturer="Korean Hroparts", mpn="TYPE-C-31-M-12",
         desc="USB-C konektor (nabíjení + programování)", block="usb", smd=True,
         pins={"A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND", "S1": "GND",
               "A4": "VBUS", "A9": "VBUS", "B4": "VBUS", "B9": "VBUS",
               "A5": "CC1", "B5": "CC2",
               "A6": "USB_DP", "B6": "USB_DP", "A7": "USB_DN", "B7": "USB_DN"}),
    R("R1", "5.1k", "CC1", "GND", "usb", "CC1 – identifikace zařízení pro USB-C nabíječku"),
    R("R2", "5.1k", "CC2", "GND", "usb", "CC2 – identifikace zařízení pro USB-C nabíječku"),
    dict(ref="U1", symbol="Power_Protection:USBLC6-2SC6", value="USBLC6-2SC6",
         footprint=SOT236, manufacturer="STMicroelectronics", mpn="USBLC6-2SC6",
         desc="ESD ochrana USB datových linek", block="usb", smd=True,
         pins={"1": "USB_DP", "6": "USB_DP", "3": "USB_DN", "4": "USB_DN",
               "2": "GND", "5": "VBUS"}),

    # ---------------------------------------------------------------- nabíječka Li-Ion
    dict(ref="U2", symbol="Battery_Management:MCP73831-2-OT", value="MCP73831-2-OT",
         footprint=SOT235, manufacturer="Microchip", mpn="MCP73831T-2ACI/OT",
         desc="Nabíječka 1článku Li-Ion/LiPo 4,2 V", block="charger", smd=True,
         pins={"1": "CHG_STAT", "2": "GND", "3": "VBAT", "4": "VBUS", "5": "CHG_PROG"}),
    R("R3", "2.2k", "CHG_PROG", "GND", "charger", "Nabíjecí proud ≈ 450 mA (1000/R)"),
    C("C1", "10u", "VBUS", "GND", "charger", "Vstupní kondenzátor nabíječky"),
    C("C2", "10u", "VBAT", "GND", "charger", "Výstupní kondenzátor nabíječky"),
    R("R4", "1k", "VBUS", "LED_CHG_A", "charger", "Rezistor LED nabíjení"),
    LED("D2", "červená", "LED_CHG_A", "CHG_STAT", "charger", "Svítí = nabíjí se"),
    LED("D3", "zelená", "CHG_STAT", "LED_FULL_K", "charger", "Svítí = nabito"),
    R("R5", "1k", "LED_FULL_K", "GND", "charger", "Rezistor LED nabito"),
    dict(ref="J4", symbol="Connector_Generic:Conn_01x02", value="BATERIE",
         footprint="Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical",
         manufacturer="JST", mpn="B2B-PH-K-S",
         desc="Konektor LiPo baterie (JST-PH 2,0 mm) – POZOR NA POLARITU", block="charger",
         smd=False, pins={"1": "VBAT", "2": "GND"}),

    # ---------------------------------------------------------------- napájecí cesta
    dict(ref="D1", symbol="Device:D_Schottky", value="B5819W",
         footprint=SOD123, manufacturer="Diodes / SL", mpn="B5819W",
         desc="Schottky – napájení z USB", block="power", smd=True,
         pins={"1": "VSYS", "2": "VBUS"}),           # 1 = K, 2 = A
    dict(ref="Q1", symbol="Transistor_FET:AO3401A", value="AO3401A",
         footprint=SOT23, manufacturer="Alpha & Omega", mpn="AO3401A",
         desc="P-MOSFET – přepínání baterie/USB (load sharing)", block="power", smd=True,
         pins={"1": "VBUS", "2": "VSYS", "3": "VBAT"}),  # G, S, D
    R("R6", "100k", "VBUS", "GND", "power", "Stahuje gate Q1 bez USB"),
    dict(ref="SW1", symbol="Switch:SW_SPDT", value="ON/OFF",
         footprint="Button_Switch_THT:SW_Slide_SPDT_Angled_CK_OS102011MA1Q",
         manufacturer="C&K", mpn="OS102011MA1QN1",
         desc="Hlavní vypínač (posuvný, úhlový – ovládá se z boku krabičky)", block="power", smd=False,
         pins={"1": "VSYS", "2": "VIN", "3": "NC_SW1"}),
    C("C3", "10u", "VIN", "GND", "power", "Vstup LDO"),
    dict(ref="U3", symbol="Regulator_Linear:AP2112K-3.3", value="AP2112K-3.3",
         footprint=SOT235, manufacturer="Diodes Inc.", mpn="AP2112K-3.3TRG1",
         desc="LDO stabilizátor 3,3 V / 600 mA", block="power", smd=True,
         pins={"1": "VIN", "2": "GND", "3": "VIN", "4": "NC_U3", "5": "+3V3"}),
    C("C4", "10u", "+3V3", "GND", "power", "Výstup LDO"),
    R("R11", "100k", "VBAT", "BAT_ADC", "power", "Dělič měření baterie (horní)"),
    R("R12", "100k", "BAT_ADC", "GND", "power", "Dělič měření baterie (dolní)"),
    C("C8", "100n", "BAT_ADC", "GND", "power", "Filtr ADC baterie"),
    R("R13", "47k", "VBUS", "VBUS_SENSE", "power", "Detekce USB (horní)"),
    R("R14", "68k", "VBUS_SENSE", "GND", "power", "Detekce USB (dolní)"),

    # ---------------------------------------------------------------- ESP32-C3
    dict(ref="U4", symbol="LaserPlan:ESP32-C3-WROOM-02", value="ESP32-C3-WROOM-02-N4",
         footprint="RF_Module:ESP32-C3-WROOM-02", manufacturer="Espressif",
         mpn="ESP32-C3-WROOM-02-N4", desc="Mikrokontrolér s Bluetooth LE 5.0",
         block="mcu", smd=True,
         # IO4 REŽIM | IO5 SDA | IO6 SCL | IO7 LED | IO8 strap | IO9 MĚŘIT/BOOT
         # IO10 bzučák | IO20 RX<-laser | IO21 TX->laser | IO18/19 USB
         # IO3 laser EN | IO2 laser AUX | IO1 detekce USB | IO0 baterie (ADC)
         pins={"1": "+3V3", "2": "EN", "3": "BTN_MODE", "4": "I2C_SDA",
               "5": "I2C_SCL", "6": "LED_STATUS", "7": "IO8_STRAP", "8": "BTN_MEAS",
               "9": "GND", "10": "BUZZER", "11": "LASER_TX", "12": "LASER_RX",
               "13": "USB_DN", "14": "USB_DP", "15": "LASER_EN", "16": "LASER_AUX",
               "17": "VBUS_SENSE", "18": "BAT_ADC", "19": "GND"}),
    C("C5", "10u", "+3V3", "GND", "mcu", "Blokování napájení ESP32"),
    C("C6", "100n", "+3V3", "GND", "mcu", "Blokování napájení ESP32"),
    R("R7", "10k", "+3V3", "EN", "mcu", "Pull-up EN (reset)"),
    C("C7", "1u", "EN", "GND", "mcu", "Zpoždění resetu"),
    R("R8", "10k", "+3V3", "BTN_MEAS", "mcu", "Pull-up IO9 (BOOT)"),
    R("R9", "10k", "+3V3", "LASER_AUX", "mcu", "Pull-up IO2 (strap)"),
    R("R20", "10k", "+3V3", "BTN_MODE", "mcu", "Pull-up tlačítka REŽIM"),
    R("R10", "10k", "+3V3", "IO8_STRAP", "mcu", "Pull-up IO8 (strap)"),
    dict(ref="SW2", symbol="Switch:SW_Push", value="MĚŘIT",
         footprint="Button_Switch_THT:SW_PUSH_6mm_H13mm", manufacturer="XKB / Omron",
         mpn="TS-1187A / B3F-1070 (6×6 mm, výška 13 mm)",
         desc="Tlačítko MĚŘIT (zároveň BOOT)", block="ui", smd=False,
         pins={"1": "BTN_MEAS", "2": "GND"}),
    dict(ref="SW3", symbol="Switch:SW_Push", value="REŽIM",
         footprint="Button_Switch_THT:SW_PUSH_6mm_H13mm", manufacturer="XKB / Omron",
         mpn="TS-1187A / B3F-1070 (6×6 mm, výška 13 mm)",
         desc="Tlačítko REŽIM / laser zap", block="ui", smd=False,
         pins={"1": "BTN_MODE", "2": "GND"}),
    R("R19", "1k", "LED_STATUS", "LED_BLE_A", "ui", "Rezistor stavové LED"),
    LED("D5", "modrá", "LED_BLE_A", "GND", "ui", "Stav Bluetooth"),

    # ---------------------------------------------------------------- bzučák
    dict(ref="BZ1", symbol="Device:Buzzer", value="Bzučák 3V",
         footprint="Buzzer_Beeper:Buzzer_12x9.5RM7.6", manufacturer="Generic",
         mpn="Pasivní magnetický bzučák 12×9,5 mm, 3 V (např. HYT-1205)",
         desc="Akustická signalizace měření", block="ui", smd=False,
         pins={"1": "+3V3", "2": "BUZ_DRV"}),
    dict(ref="Q4", symbol="Transistor_FET:AO3400A", value="AO3400A",
         footprint=SOT23, manufacturer="Alpha & Omega", mpn="AO3400A",
         desc="Spínač bzučáku", block="ui", smd=True,
         pins={"1": "BUZZER", "2": "GND", "3": "BUZ_DRV"}),
    R("R18", "100k", "BUZZER", "GND", "ui", "Gate pull-down"),
    dict(ref="D4", symbol="Device:D", value="1N4148W",
         footprint=SOD123, manufacturer="Diodes / SL", mpn="1N4148W",
         desc="Ochranná dioda bzučáku", block="ui", smd=True,
         pins={"1": "+3V3", "2": "BUZ_DRV"}),         # K, A

    # ---------------------------------------------------------------- laser modul
    dict(ref="JP1", symbol="Jumper:SolderJumper_3_Bridged12", value="LASER_V",
         footprint="Jumper:SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm",
         manufacturer="-", mpn="(pájecí propojka na DPS)",
         desc="Volba napájení laseru: 1-2 = 3,3 V (výchozí), 2-3 = baterie", block="laser",
         smd=True, no_bom=True,
         pins={"1": "+3V3", "2": "LASER_VSRC", "3": "VIN"}),
    dict(ref="Q2", symbol="Transistor_FET:AO3401A", value="AO3401A",
         footprint=SOT23, manufacturer="Alpha & Omega", mpn="AO3401A",
         desc="Spínač napájení laser modulu", block="laser", smd=True,
         pins={"1": "LASER_G", "2": "LASER_VSRC", "3": "LASER_VCC"}),
    R("R15", "100k", "LASER_VSRC", "LASER_G", "laser", "Gate pull-up (laser vyp.)"),
    C("C10", "10n", "LASER_VSRC", "LASER_G", "laser", "Měkký start laseru"),
    R("R17", "10k", "LASER_G", "LASER_GD", "laser", "Omezení rychlosti sepnutí"),
    dict(ref="Q3", symbol="Transistor_FET:AO3400A", value="AO3400A",
         footprint=SOT23, manufacturer="Alpha & Omega", mpn="AO3400A",
         desc="Budič spínače laseru", block="laser", smd=True,
         pins={"1": "LASER_EN", "2": "GND", "3": "LASER_GD"}),
    R("R16", "100k", "LASER_EN", "GND", "laser", "Laser vypnutý po resetu"),
    C("C9", "10u", "LASER_VCC", "GND", "laser", "Blokování napájení laseru"),
    dict(ref="J2", symbol="Connector_Generic:Conn_01x05", value="LASER",
         footprint="Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical",
         manufacturer="Generic", mpn="Kolíková lišta 1×5, 2,54 mm",
         desc="Laser modul: 1 VCC, 2 GND, 3 TX modulu, 4 RX modulu, 5 AUX", block="laser",
         smd=False,
         pins={"1": "LASER_VCC", "2": "GND", "3": "LASER_TX", "4": "LASER_RX", "5": "LASER_AUX"}),

    # ---------------------------------------------------------------- displej
    dict(ref="J3", symbol="Connector_Generic:Conn_01x04", value="OLED",
         footprint="Connector_PinSocket_2.54mm:PinSocket_1x04_P2.54mm_Vertical",
         manufacturer="Generic", mpn="Dutinková lišta 1×4, 2,54 mm",
         desc="OLED 0,96\" SSD1306 I2C: GND, VCC, SCL, SDA", block="ui", smd=False,
         pins={"1": "GND", "2": "+3V3", "3": "I2C_SCL", "4": "I2C_SDA"}),
]

# Díry pro šrouby M2.5 (jen na DPS, ne ve schématu)
MOUNTING_HOLES = ["H1", "H2", "H3", "H4"]

# Sítě, které jsou záměrně nezapojené (vývod bez připojení)
NO_CONNECT_NETS = {"NC_SW1", "NC_U3"}

# Šířky cest (mm). Silové sítě širší, USB-C (rozteč 0,5 mm) užší. Ostatní 0,25 mm.
NET_WIDTH = {"GND": 0.35, "VBUS": 0.6, "VBAT": 0.6, "VSYS": 0.6, "VIN": 0.6,
             "+3V3": 0.5, "LASER_VCC": 0.5, "LASER_VSRC": 0.5, "BUZ_DRV": 0.4,
             "USB_DP": 0.2, "USB_DN": 0.2, "CC1": 0.2, "CC2": 0.2}


def nets():
    """Vrátí {síť: [(ref, pin), ...]}"""
    out = {}
    for p in PARTS:
        for pin, net in p["pins"].items():
            out.setdefault(net, []).append((p["ref"], pin))
    return out


if __name__ == "__main__":
    for n, conns in sorted(nets().items()):
        print(f"{n:12s} {len(conns):2d}  " + " ".join(f"{r}.{p}" for r, p in conns))
