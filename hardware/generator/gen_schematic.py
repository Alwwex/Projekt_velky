#!/usr/bin/env python3
"""
Vygeneruje schéma LaserPlan pro KiCad 7 (kicad/laserplan.kicad_sch) z circuit.py.

Součástky jsou rozmístěné po funkčních blocích; každý vývod má krátký
přívod se jmenovkou sítě (net label) nebo napájecím symbolem. Spoje jsou tedy
dány jmény sítí – stejně jako v circuit.py, ze kterého vzniká i deska.
"""
import math
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import circuit  # noqa: E402
from sexpr import Q, dumps, find, find_all, parse  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
KDIR = os.path.normpath(os.path.join(HERE, "..", "kicad"))
SYMDIR = "/usr/share/kicad/symbols"
PROJECT = "laserplan"
ROOT_UUID = str(uuid.uuid5(uuid.NAMESPACE_URL, "laserplan/root-sheet"))

POWER_SYMBOLS = {"GND": "power:GND", "+3V3": "power:+3V3", "VBUS": "power:VBUS"}

# rozmístění ve schématu (mm, A3 na šířku); (x, y, rotace)
SCH_POS = {
    # USB-C
    "J1": (40.64, 66.04, 0), "R1": (81.28, 63.5, 0), "R2": (93.98, 63.5, 0), "U1": (73.66, 91.44, 0),
    # nabíječka
    "U2": (142.24, 63.5, 0), "R3": (124.46, 76.2, 0), "C1": (124.46, 50.8, 0), "C2": (165.1, 76.2, 0),
    "R4": (182.88, 50.8, 0), "D2": (182.88, 66.04, 0), "D3": (198.12, 81.28, 0), "R5": (198.12, 96.52, 0),
    "J4": (172.72, 96.52, 0),
    # napájení
    "D1": (233.68, 50.8, 0), "Q1": (233.68, 71.12, 0), "R6": (246.38, 88.9, 0), "SW1": (271.78, 55.88, 0),
    "C3": (292.1, 76.2, 0), "U3": (314.96, 58.42, 0), "C4": (337.82, 76.2, 0),
    "R11": (360.68, 50.8, 0), "R12": (360.68, 68.58, 0), "C8": (373.38, 68.58, 0),
    "R13": (391.16, 50.8, 0), "R14": (391.16, 68.58, 0),
    # ESP32
    "U4": (93.98, 182.88, 0), "C5": (35.56, 165.1, 0), "C6": (45.72, 165.1, 0),
    "R7": (35.56, 205.74, 0), "C7": (35.56, 223.52, 0), "R8": (144.78, 228.6, 0),
    "R9": (157.48, 228.6, 0), "R10": (170.18, 228.6, 0), "R20": (182.88, 228.6, 0),
    # ovládání
    "SW2": (213.36, 152.4, 0), "SW3": (213.36, 172.72, 0), "R19": (243.84, 154.94, 0),
    "D5": (243.84, 172.72, 0), "BZ1": (213.36, 210.82, 0), "Q4": (231.14, 228.6, 0),
    "R18": (218.44, 246.38, 0), "D4": (243.84, 205.74, 0), "J3": (264.16, 233.68, 0),
    # laser
    "JP1": (309.88, 152.4, 0), "Q2": (335.28, 165.1, 0), "R15": (322.58, 180.34, 0),
    "C10": (312.42, 180.34, 0), "R17": (335.28, 200.66, 0), "Q3": (335.28, 223.52, 0),
    "R16": (320.04, 233.68, 0), "C9": (358.14, 182.88, 0), "J2": (391.16, 172.72, 0),
}

BLOCKS = [
    ("USB-C, ESD ochrana", 25, 35, 110, 112),
    ("Nabíječka Li-Ion (MCP73831, ~450 mA)", 112, 35, 210, 112),
    ("Napájecí cesta, vypínač, LDO 3,3 V, měření baterie a USB", 212, 35, 410, 112),
    ("Mikrokontrolér ESP32-C3 (Bluetooth LE)", 25, 135, 200, 262),
    ("Ovládání: tlačítka, LED, bzučák, OLED", 202, 135, 290, 262),
    ("Laserový modul – spínané napájení a UART", 292, 135, 410, 262),
]

NOTES = [
    (30, 268, "Piny ESP32-C3: IO0 baterie ADC | IO1 detekce USB | IO2 laser AUX (strap, pull-up) | IO3 laser EN | IO4 REZIM"),
    (30, 273, "IO5 SDA | IO6 SCL | IO7 LED | IO8 strap | IO9 MERIT/BOOT | IO10 bzucak | IO20 RX<-laser TX | IO21 TX->laser RX | IO18/19 USB"),
    (30, 278, "JP1: 1-2 (vychozi) = laser z 3,3 V; 2-3 = laser z baterie (jen pro moduly 3,6-5 V s logikou 3,3 V)."),
]


def uid(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "laserplan/sch/" + "/".join(parts)))


def ref_uuid(ref):
    # stejné UUID používá gen_pcb.py (cesta footprintu) – propojení schéma <-> deska
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "laserplan/" + ref))


# ---------------------------------------------------------------------------
# Knihovny symbolů
# ---------------------------------------------------------------------------
_libcache = {}


def lib_symbols(lib):
    if lib not in _libcache:
        root = parse(open(os.path.join(SYMDIR, lib + ".kicad_sym"), encoding="utf-8").read())
        _libcache[lib] = {s[1]: s for s in find_all(root, "symbol")}
    return _libcache[lib]


def rename_units(node, old, new):
    out = []
    for x in node:
        if isinstance(x, list) and x and x[0] == "symbol" and isinstance(x[1], str) and x[1].startswith(old + "_"):
            x = ["symbol", Q(new + x[1][len(old):])] + x[2:]
        out.append(x)
    return out


def flatten(lib, name):
    """Vrátí definici symbolu s vyřešeným (extends ...) a jménem lib:name."""
    syms = lib_symbols(lib)
    s = syms[name]
    ext = find(s, "extends")
    if ext:
        parent = flatten(lib, ext[1])
        props = [x for x in s if isinstance(x, list) and x[0] == "property"]
        head = [x for x in parent[2:] if isinstance(x, list) and x[0] in ("pin_numbers", "pin_names", "in_bom", "on_board", "power")]
        units = [x for x in parent[2:] if isinstance(x, list) and x[0] == "symbol"]
        units = rename_units(units, parent[1].split(":")[1], name)
        return ["symbol", Q(f"{lib}:{name}")] + head + props + units
    return ["symbol", Q(f"{lib}:{name}")] + [x for x in s[2:]]


def esp32_symbol():
    """Vlastní symbol ESP32-C3-WROOM-02 (v KiCadu 7 chybí)."""
    left = [("1", "3V3", "power_in"), ("2", "EN", "input"), ("3", "IO4", "bidirectional"),
            ("4", "IO5", "bidirectional"), ("5", "IO6", "bidirectional"), ("6", "IO7", "bidirectional"),
            ("7", "IO8", "bidirectional"), ("8", "IO9/BOOT", "bidirectional"), ("10", "IO10", "bidirectional")]
    right = [("18", "IO0/ADC1_0", "bidirectional"), ("17", "IO1/ADC1_1", "bidirectional"),
             ("16", "IO2", "bidirectional"), ("15", "IO3", "bidirectional"), ("14", "IO19/USB_D+", "bidirectional"),
             ("13", "IO18/USB_D-", "bidirectional"), ("12", "TXD/IO21", "bidirectional"),
             ("11", "RXD/IO20", "bidirectional")]
    pins = []
    for i, (num, nm, typ) in enumerate(left):
        y = 10.16 - i * 2.54
        pins.append(["pin", typ, "line", ["at", -15.24, y, 0], ["length", 2.54],
                     ["name", Q(nm), ["effects", ["font", ["size", 1.27, 1.27]]]],
                     ["number", Q(num), ["effects", ["font", ["size", 1.27, 1.27]]]]])
    for i, (num, nm, typ) in enumerate(right):
        y = 10.16 - i * 2.54
        pins.append(["pin", typ, "line", ["at", 15.24, y, 180], ["length", 2.54],
                     ["name", Q(nm), ["effects", ["font", ["size", 1.27, 1.27]]]],
                     ["number", Q(num), ["effects", ["font", ["size", 1.27, 1.27]]]]])
    for k, num in enumerate(("9", "19")):
        pins.append(["pin", "power_in", "line", ["at", -1.27 + k * 2.54, -15.24, 90], ["length", 2.54],
                     ["name", Q("GND"), ["effects", ["font", ["size", 1.27, 1.27]]]],
                     ["number", Q(num), ["effects", ["font", ["size", 1.27, 1.27]]]]])

    def prop(k, v, x, y, hide=False):
        eff = ["effects", ["font", ["size", 1.27, 1.27]]]
        if hide:
            eff.append("hide")
        return ["property", Q(k), Q(v), ["at", x, y, 0], eff]

    return ["symbol", Q("LaserPlan:ESP32-C3-WROOM-02"), ["pin_names", ["offset", 1.016]], ["in_bom", "yes"], ["on_board", "yes"],
            prop("Reference", "U", 0, 15.24), prop("Value", "ESP32-C3-WROOM-02", 0, -19.05),
            prop("Footprint", "RF_Module:ESP32-C3-WROOM-02", 0, -21.59, True),
            prop("Datasheet", "https://www.espressif.com/sites/default/files/documentation/esp32-c3-wroom-02_datasheet_en.pdf", 0, -24.13, True),
            ["symbol", Q("ESP32-C3-WROOM-02_0_1"),
             ["rectangle", ["start", -12.7, 12.7], ["end", 12.7, -12.7],
              ["stroke", ["width", 0.254], ["type", "default"]], ["fill", ["type", "background"]]]],
            ["symbol", Q("ESP32-C3-WROOM-02_1_1")] + pins]


def get_symbol(lib_id):
    if lib_id == "LaserPlan:ESP32-C3-WROOM-02":
        return esp32_symbol()
    lib, name = lib_id.split(":")
    return flatten(lib, name)


def symbol_pins(sym):
    """[(číslo, x, y, úhel)] v souřadnicích symbolu (Y nahoru)."""
    out = []
    for unit in find_all(sym, "symbol"):
        for p in find_all(unit, "pin"):
            at = find(p, "at")
            out.append((str(find(p, "number")[1]), float(at[1]), float(at[2]), float(at[3])))
    return out


# ---------------------------------------------------------------------------
def fmt(v):
    return round(v, 4)


def effects(size=1.27, justify=None, hide=False, bold=False):
    font = ["font", ["size", size, size]]
    if bold:
        font.append("bold")
    e = ["effects", font]
    if justify:
        e.append(["justify"] + justify.split())
    if hide:
        e.append("hide")
    return e


def build():
    used = {}
    items = []
    pwr_n = [0]

    def place_symbol(lib_id, ref, value, x, y, rot, props, pins, power=False, value_at=None):
        sym = used.setdefault(lib_id, get_symbol(lib_id))
        su = ref_uuid(ref) if not power else uid("pwr", ref)
        node = ["symbol", ["lib_id", Q(lib_id)], ["at", fmt(x), fmt(y), rot], ["unit", 1],
                ["in_bom", "no" if power else "yes"], ["on_board", "no" if power else "yes"], ["dnp", "no"],
                ["uuid", Q(su)]]
        pxs = [p[1] for p in symbol_pins(sym)] or [0]
        pys = [p[2] for p in symbol_pins(sym)] or [0]
        top = y - max(pys) - 2.0
        bot = y - min(pys) + 2.0
        if power:
            node.append(["property", Q("Reference"), Q(ref), ["at", fmt(x), fmt(y + 6.35), 0], effects(hide=True)])
            va = value_at or (x, y + (3.81 if value == "GND" else -3.81))
            node.append(["property", Q("Value"), Q(value), ["at", fmt(va[0]), fmt(va[1]), 0], effects()])
        else:
            rx = x + max(pxs) + 2.0 if max(pxs) - min(pxs) < 3 else x
            node.append(["property", Q("Reference"), Q(ref),
                         ["at", fmt(rx), fmt(top if rx == x else y - 1.27), 0],
                         effects(justify=None if rx == x else "left")])
            node.append(["property", Q("Value"), Q(value),
                         ["at", fmt(rx), fmt(bot if rx == x else y + 1.27), 0],
                         effects(justify=None if rx == x else "left")])
        for k, v in props.items():
            node.append(["property", Q(k), Q(v), ["at", fmt(x), fmt(y), 0], effects(hide=True)])
        for num in pins:
            node.append(["pin", Q(num), ["uuid", Q(uid(ref, "pin", num))]])
        node.append(["instances", ["project", Q(PROJECT),
                                   ["path", Q("/" + ROOT_UUID), ["reference", Q(ref)], ["unit", 1]]]])
        items.append(node)
        return sym

    def wire(a, b):
        items.append(["wire", ["pts", ["xy", fmt(a[0]), fmt(a[1])], ["xy", fmt(b[0]), fmt(b[1])]],
                      ["stroke", ["width", 0], ["type", "default"]], ["uuid", Q(uid("w", str(a), str(b)))]])

    def label(net, at, angle):
        just = {0: "left bottom", 90: "left bottom", 180: "right bottom", 270: "right bottom"}[angle]
        items.append(["label", Q(net), ["at", fmt(at[0]), fmt(at[1]), angle], ["fields_autoplaced"],
                      effects(justify=just), ["uuid", Q(uid("l", net, str(at)))]])

    def power(net, at, out):
        """Napájecí symbol na konci přívodu, natočený směrem ven od vývodu."""
        pwr_n[0] += 1
        ref = "#PWR%03d" % pwr_n[0]
        lib_id = POWER_SYMBOLS[net]
        body = (0, 1) if net == "GND" else (0, -1)          # směr těla při rotaci 0 (obrazovka)
        rot = 0
        for r in (0, 90, 180, 270):
            rr = math.radians(r)
            bx, by = body[0], -body[1]                         # do souřadnic knihovny
            lx, ly = bx * math.cos(rr) - by * math.sin(rr), bx * math.sin(rr) + by * math.cos(rr)
            if (round(lx), -round(ly)) == out:
                rot = r
                break
        place_symbol(lib_id, ref, net, at[0], at[1], rot, {"Footprint": "", "Datasheet": ""}, ["1"],
                     power=True, value_at=(at[0] + out[0] * 5.08, at[1] + out[1] * 5.08))

    for part in circuit.PARTS:
        ref = part["ref"]
        x, y, rot = SCH_POS[ref]
        props = {"Footprint": part["footprint"], "Datasheet": "~", "MPN": part["mpn"],
                 "Výrobce": part["manufacturer"], "Popis": part["desc"]}
        sym = place_symbol(part["symbol"], ref, part["value"], x, y, rot, props, list(part["pins"].keys()))
        done = set()
        for num, px, py, ang in symbol_pins(sym):
            net = part["pins"].get(num)
            # otočení symbolu (proti směru hodinových ručiček, osa Y knihovny nahoru)
            r = math.radians(rot)
            px, py = (round(px * math.cos(r) - py * math.sin(r), 4),
                      round(px * math.sin(r) + py * math.cos(r), 4))
            ang = (ang + rot) % 360
            ex, ey = x + px, y - py
            key = (round(ex, 3), round(ey, 3))
            if key in done:
                continue
            done.add(key)
            if net is None or net in circuit.NO_CONNECT_NETS:
                items.append(["no_connect", ["at", fmt(ex), fmt(ey)], ["uuid", Q(uid("nc", ref, num))]])
                continue
            out = math.radians(ang + 180)
            dx, dy = round(math.cos(out)), -round(math.sin(out))
            L = 2.54
            sx, sy = ex + dx * L, ey + dy * L
            wire((ex, ey), (sx, sy))
            if net in POWER_SYMBOLS:
                power(net, (sx, sy), (dx, dy))
            else:
                angle = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}[(dx, dy)]
                label(net, (sx, sy), angle)

    # PWR_FLAG – napájecí sítě buzené konektory (kvůli ERC)
    for i, net in enumerate(["GND", "VBUS", "VBAT"]):
        fx, fy = 30.48 + i * 15.24, 25.4
        place_symbol("power:PWR_FLAG", "#FLG%02d" % (i + 1), "PWR_FLAG", fx, fy, 0, {"Footprint": "", "Datasheet": ""}, ["1"], power=True)
        wire((fx, fy), (fx, fy + 2.54))
        if net in POWER_SYMBOLS:
            power(net, (fx, fy + 2.54), (0, 1))
        else:
            label(net, (fx, fy + 2.54), 270)

    # rámečky bloků a poznámky
    for title, x0, y0, x1, y1 in BLOCKS:
        items.append(["rectangle", ["start", x0, y0], ["end", x1, y1],
                      ["stroke", ["width", 0.2], ["type", "dash"]], ["fill", ["type", "none"]],
                      ["uuid", Q(uid("blk", title))]])
        items.append(["text", Q(title), ["at", x0 + 1.5, y0 + 3.5, 0], effects(2.0, "left bottom", bold=True),
                      ["uuid", Q(uid("blkt", title))]])
    for x, y, t in NOTES:
        items.append(["text", Q(t), ["at", x, y, 0], effects(1.5, "left bottom"), ["uuid", Q(uid("note", t))]])

    sch = ["kicad_sch", ["version", 20230121], ["generator", "eeschema"], ["uuid", Q(ROOT_UUID)],
           ["paper", Q("A3")],
           ["title_block", ["title", Q("LaserPlan – Bluetooth laserový metr")], ["date", Q("2026-11-11")],
            ["rev", Q("1.0")], ["comment", 1, Q("Vygenerováno z hardware/generator/circuit.py")],
            ["comment", 2, Q("ESP32-C3-WROOM-02, MCP73831, AP2112K-3.3, UART laser modul (JRT / ASCII)")]],
           ["lib_symbols"] + list(used.values())] + items + [
        ["sheet_instances", ["path", Q("/"), ["page", Q("1")]]]]
    os.makedirs(KDIR, exist_ok=True)
    path = os.path.join(KDIR, PROJECT + ".kicad_sch")
    with open(path, "w", encoding="utf-8") as f:
        f.write(dumps(sch) + "\n")
    # projektová knihovna s vlastním symbolem
    lib = ["kicad_symbol_lib", ["version", 20220914], ["generator", "laserplan_gen"],
           ["symbol", Q("ESP32-C3-WROOM-02")] + esp32_symbol()[2:]]
    with open(os.path.join(KDIR, "laserplan.kicad_sym"), "w", encoding="utf-8") as f:
        f.write(dumps(lib) + "\n")
    with open(os.path.join(KDIR, "sym-lib-table"), "w", encoding="utf-8") as f:
        f.write('(sym_lib_table\n  (lib (name "LaserPlan")(type "KiCad")(uri "${KIPRJMOD}/laserplan.kicad_sym")(options "")(descr "Symboly projektu LaserPlan"))\n)\n')
    print("uloženo", path)


if __name__ == "__main__":
    build()
