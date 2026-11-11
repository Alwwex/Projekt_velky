#!/usr/bin/env python3
"""
Vygeneruje desku plošného spoje LaserPlan v KiCadu 7 (pcbnew Python API).

  python3 gen_pcb.py place     -> kicad/laserplan.kicad_pcb (rozmístěno, nerozvedeno)
  python3 gen_pcb.py route     -> autorouting (router.py)
  python3 gen_pcb.py finish    -> GND rozlitá měď, prošívací prokovy, DRC report

Souřadnice v tabulce PLACEMENT jsou v mm vůči levému hornímu rohu desky.
Osa X míří dozadu (k USB-C), osa Y dolů. Přední hrana (x = 0) je u laseru.
"""
import math
import os
import sys
import uuid

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
import circuit  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
KDIR = os.path.normpath(os.path.join(HERE, "..", "kicad"))
PCB = os.path.join(KDIR, "laserplan.kicad_pcb")
FPLIB = "/usr/share/kicad/footprints"

OX, OY = 100.0, 100.0          # posun počátku desky na výkresu
W, H = 90.0, 44.0              # rozměr desky (mm)
CORNER_R = 3.0

# ref: (x, y, rotace°)
PLACEMENT = {
    # --- USB-C a ochrana (zadní hrana)
    "J1": (86.3, 24.0, 90),
    "U1": (70.8, 14.1, 0),
    "R1": (79.0, 29.4, 0),
    "R2": (79.0, 19.0, 0),
    # --- nabíječka
    "U2": (74.5, 33.0, 0),
    "R3": (74.5, 29.6, 0),
    "C1": (78.5, 33.0, 90),
    "C2": (70.8, 33.0, 90),
    "R4": (83.2, 34.0, 0),
    "D2": (86.7, 34.0, 180),
    "R5": (83.2, 36.5, 180),
    "D3": (86.7, 36.5, 0),
    "J4": (74.0, 39.6, 0),
    # --- napájecí cesta + LDO
    "D1": (75.0, 21.5, 90),
    "Q1": (75.0, 26.0, 90),
    "R6": (77.8, 25.5, 90),
    "SW1": (22.0, 2.25, 180),
    "C3": (81.6, 5.6, 90),
    "U3": (78.5, 5.5, 0),
    "C4": (75.4, 5.6, 90),
    "R11": (72.2, 9.6, 0),
    "R12": (75.8, 9.6, 0),
    "C8": (79.4, 9.6, 0),
    "R13": (84.0, 12.0, 90),
    "R14": (84.0, 8.6, 90),
    # --- ESP32-C3
    "U4": (57.0, 13.35, 0),
    "C5": (41.0, 4.6, 0),
    "C6": (41.0, 7.2, 0),
    "R7": (36.5, 4.6, 0),
    "C7": (36.5, 7.2, 0),
    "R8": (49.5, 23.3, 0),
    "R9": (68.5, 9.0, 90),
    "R10": (45.5, 23.3, 0),
    "R20": (44.5, 10.0, 90),
    # --- ovládání
    "SW3": (34.5, 11.5, 0),      # REŽIM
    "SW2": (34.5, 22.5, 0),      # MĚŘIT
    "R19": (45.0, 26.5, 0),
    "D5": (45.0, 29.0, 0),
    # --- bzučák
    "BZ1": (35.5, 37.6, 0),
    "Q4": (49.0, 31.5, 90),
    "R18": (52.5, 31.5, 90),
    "D4": (47.5, 36.2, 90),
    # --- laser
    "J2": (49.0, 41.6, 90),
    "Q2": (51.0, 37.0, 90),
    "C9": (54.5, 37.0, 90),
    "R15": (57.0, 33.5, 90),
    "C10": (59.2, 33.5, 90),
    "R17": (57.5, 29.0, 0),
    "Q3": (61.0, 29.0, 90),
    "R16": (64.0, 28.5, 90),
    "JP1": (53.0, 27.0, 0),
    # --- displej (záhlaví OLED směrem dozadu – displej otočen o 180°)
    "J3": (30.5, 17.19, 0),
}

HOLES = {"H1": (3.2, 3.2), "H2": (W - 3.2, 3.2), "H3": (3.2, H - 3.2), "H4": (W - 3.2, H - 3.2)}


def mm(v):
    return pcbnew.FromMM(v)


def P(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


def sym_uuid(ref):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "laserplan/" + ref))


def load_fp(fpid):
    lib, name = fpid.split(":")
    fp = pcbnew.FootprintLoad(os.path.join(FPLIB, lib + ".pretty"), name)
    if fp is None:
        raise RuntimeError("footprint nenalezen: " + fpid)
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def add_line(board, a, b, layer, width=0.15):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(P(*a))
    s.SetEnd(P(*b))
    s.SetLayer(layer)
    s.SetWidth(mm(width))
    board.Add(s)
    return s


def add_arc(board, center, start, angle_deg, layer, width=0.15):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_ARC)
    s.SetCenter(P(*center))
    s.SetStart(P(*start))
    s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(angle_deg, pcbnew.DEGREES_T), True)
    s.SetLayer(layer)
    s.SetWidth(mm(width))
    board.Add(s)


def add_rect(board, x0, y0, x1, y1, layer, width=0.15):
    add_line(board, (x0, y0), (x1, y0), layer, width)
    add_line(board, (x1, y0), (x1, y1), layer, width)
    add_line(board, (x1, y1), (x0, y1), layer, width)
    add_line(board, (x0, y1), (x0, y0), layer, width)


def add_text(board, text, x, y, size=1.0, layer=pcbnew.F_SilkS, rot=0, bold=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(P(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(size * (0.2 if bold else 0.15)))
    t.SetTextAngle(pcbnew.EDA_ANGLE(rot, pcbnew.DEGREES_T))
    if layer == pcbnew.B_SilkS:
        t.SetMirrored(True)
    board.Add(t)


def outline(board):
    r = CORNER_R
    L = pcbnew.Edge_Cuts
    add_line(board, (r, 0), (W - r, 0), L, 0.1)
    add_line(board, (W, r), (W, H - r), L, 0.1)
    add_line(board, (W - r, H), (r, H), L, 0.1)
    add_line(board, (0, H - r), (0, r), L, 0.1)
    add_arc(board, (r, r), (0, r), 90, L, 0.1)
    add_arc(board, (W - r, r), (W - r, 0), 90, L, 0.1)
    add_arc(board, (W - r, H - r), (W, H - r), 90, L, 0.1)
    add_arc(board, (r, H - r), (r, H), 90, L, 0.1)


def design_rules(board):
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    ds.m_TrackMinWidth = mm(0.15)
    ds.m_ViasMinSize = mm(0.5)
    ds.m_ViasMinAnnularWidth = mm(0.13)
    ds.m_MinThroughDrill = mm(0.3)
    ds.m_MinClearance = mm(0.15)
    ds.m_CopperEdgeClearance = mm(0.3)
    ds.m_HoleClearance = mm(0.25)
    ds.m_HoleToHoleMin = mm(0.25)
    ds.m_SolderMaskMinWidth = mm(0)
    nc = ds.m_NetSettings.m_DefaultNetClass
    nc.SetClearance(mm(0.2))
    nc.SetTrackWidth(mm(0.25))
    nc.SetViaDiameter(mm(0.6))
    nc.SetViaDrill(mm(0.3))


def place():
    board = pcbnew.BOARD()
    design_rules(board)
    netmap = {}
    for name in sorted(circuit.nets()):
        if name in circuit.NO_CONNECT_NETS:
            continue
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        netmap[name] = ni

    for part in circuit.PARTS:
        ref = part["ref"]
        fp = load_fp(part["footprint"])
        fp.SetReference(ref)
        fp.SetValue(part["value"])
        fp.SetPath(pcbnew.KIID_PATH("/" + sym_uuid(ref)))
        fp.SetProperty("MPN", part["mpn"])
        fp.SetProperty("Manufacturer", part["manufacturer"])
        x, y, rot = PLACEMENT[ref]
        board.Add(fp)
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(P(x, y))
        if ref in ("J1", "SW1"):
            # součástky přesahující hranu desky: sítotisk mimo desku odstranit
            fp.SetOrientationDegrees(PLACEMENT[ref][2])
            fp.SetPosition(P(*PLACEMENT[ref][:2]))
            for g in list(fp.GraphicalItems()):
                if g.GetLayer() != pcbnew.F_SilkS:
                    continue
                bb = g.GetBoundingBox()
                if (pcbnew.ToMM(bb.GetRight()) > OX + W - 0.4 or pcbnew.ToMM(bb.GetTop()) < OY + 0.4
                        or pcbnew.ToMM(bb.GetLeft()) < OX + 0.4 or pcbnew.ToMM(bb.GetBottom()) > OY + H - 0.4):
                    fp.Remove(g)
        if ref == "U4":
            # termální prokovy knihovny mají vrták 0,2 mm (mimo běžné 2vrstvé možnosti)
            # -> nahradíme je 4 standardními (0,6/0,3 mm) uvnitř zemnicí plošky
            for pad in list(fp.Pads()):
                if pad.GetNumber() == "19" and pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                    fp.Remove(pad)
            ep = [p for p in fp.Pads() if p.GetNumber() == "19"][0]
            for k, (dx, dy) in enumerate([(-0.55, -0.55), (0.55, -0.55), (-0.55, 0.55), (0.55, 0.55)]):
                v = pcbnew.PAD(fp)
                v.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
                v.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
                v.SetSize(pcbnew.VECTOR2I(mm(0.6), mm(0.6)))
                v.SetDrillSize(pcbnew.VECTOR2I(mm(0.3), mm(0.3)))
                v.SetLayerSet(pcbnew.PAD.PTHMask())
                v.SetNumber("19")
                v.SetPosition(ep.GetPosition() + pcbnew.VECTOR2I(mm(dx), mm(dy)))
                v.SetLocalCoord()
                fp.Add(v)
        for pad in fp.Pads():
            net = part["pins"].get(pad.GetNumber())
            if net and net in netmap:
                pad.SetNet(netmap[net])
            if ref == "J1" and net == "GND" and pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                pad.SetZoneConnection(pcbnew.ZONE_CONNECTION_FULL)   # úzké plošky – plné napojení
        # menší reference na sítotisku
        rt = fp.Reference()
        rt.SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
        rt.SetTextThickness(mm(0.12))
        fp.Value().SetVisible(False)

    for ref, (x, y) in HOLES.items():
        fp = load_fp("MountingHole:MountingHole_2.7mm_M2.5")
        fp.SetReference(ref)
        fp.SetValue("M2.5")
        fp.SetBoardOnly(True)
        fp.Reference().SetVisible(False)
        board.Add(fp)
        fp.SetPosition(P(x, y))

    outline(board)
    silkscreen(board)
    place_refs(board)
    os.makedirs(KDIR, exist_ok=True)
    write_project()
    board.SetFileName(PCB)
    pcbnew.SaveBoard(PCB, board)
    print("uloženo", PCB)
    return board


def write_project():
    """Projektový soubor KiCadu: pravidla (odpovídají běžné výrobě JLCPCB/PCBWay), třídy spojů."""
    import json
    nc = lambda name, w, prio: {  # noqa: E731
        "name": name, "clearance": 0.2, "track_width": w, "via_diameter": 0.6, "via_drill": 0.3,
        "microvia_diameter": 0.3, "microvia_drill": 0.1, "diff_pair_gap": 0.25, "diff_pair_width": 0.2,
        "diff_pair_via_gap": 0.25, "bus_width": 12, "wire_width": 6, "line_style": 0,
        "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)", "priority": prio}
    classes = [nc("Default", 0.25, 2147483647), nc("Napajeni", 0.5, 0), nc("USB", 0.2, 1)]
    patterns = [{"netclass": "Napajeni", "pattern": n} for n in ("VBUS", "VBAT", "VSYS", "VIN", "+3V3", "LASER_VCC", "LASER_VSRC")]
    patterns += [{"netclass": "USB", "pattern": n} for n in ("USB_DP", "USB_DN", "CC1", "CC2")]
    pro = {
        "board": {"design_settings": {
            "defaults": {"board_outline_line_width": 0.1, "copper_line_width": 0.2, "silk_line_width": 0.15,
                         "silk_text_size_h": 0.8, "silk_text_size_v": 0.8, "silk_text_thickness": 0.12},
            "rule_severities": {"lib_footprint_issues": "ignore", "lib_footprint_mismatch": "ignore",
                                "silk_over_copper": "warning", "silk_overlap": "warning", "text_height": "warning"},
            "rules": {"min_clearance": 0.15, "min_track_width": 0.15, "min_via_diameter": 0.5,
                      "min_via_annular_width": 0.13, "min_through_hole_diameter": 0.3, "min_hole_clearance": 0.25,
                      "min_hole_to_hole": 0.25, "min_copper_edge_clearance": 0.3, "min_silk_clearance": 0.0,
                      "min_text_height": 0.8, "min_text_thickness": 0.08, "solder_mask_min_width": 0.0},
            "track_widths": [0.0, 0.2, 0.25, 0.35, 0.5, 0.6], "via_dimensions": [{"diameter": 0.0, "drill": 0.0}, {"diameter": 0.6, "drill": 0.3}]}},
        "meta": {"filename": "laserplan.kicad_pro", "version": 1},
        "net_settings": {"classes": classes, "meta": {"version": 3}, "netclass_patterns": patterns},
        "pcbnew": {"page_layout_descr_file": ""},
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": [["b5c98115-cdfc-55bc-9dab-5ae66145f100", ""]],
        "text_variables": {},
    }
    with open(os.path.join(KDIR, "laserplan.kicad_pro"), "w", encoding="utf-8") as f:
        json.dump(pro, f, indent=2, ensure_ascii=False)


def place_refs(board):
    """Umístí označení součástek (R1, C5…) tak, aby nepřekrývala plošky ani jiné popisky."""
    obstacles = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            bb.Inflate(mm(0.2))
            obstacles.append(bb)
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.F_SilkS:
            obstacles.append(d.GetBoundingBox())
    circles = []          # (fp, střed, poloměr) – kruhy na sítotisku (bzučák)
    for fp in board.GetFootprints():
        for g in fp.GraphicalItems():
            if g.GetLayer() != pcbnew.F_SilkS or g.Type() != pcbnew.PCB_FP_SHAPE_T:
                continue
            if g.GetShape() == pcbnew.SHAPE_T_CIRCLE:
                circles.append((fp, g.GetCenter(), g.GetRadius()))
            else:
                obstacles.append((fp, g.GetBoundingBox()))

    def hits(tb, own):
        for o in obstacles:
            if isinstance(o, tuple):
                if o[0] is own:
                    continue
                o = o[1]
            if tb.Intersects(o):
                return True
        for fp_, c, r in circles:
            # vzdálenost středu kružnice k obdélníku textu (min / max)
            dx = max(tb.GetLeft() - c.x, 0, c.x - tb.GetRight())
            dy = max(tb.GetTop() - c.y, 0, c.y - tb.GetBottom())
            dmin = math.hypot(dx, dy)
            dmax = max(math.hypot(c.x - xx, c.y - yy) for xx in (tb.GetLeft(), tb.GetRight())
                       for yy in (tb.GetTop(), tb.GetBottom()))
            if dmin - mm(0.15) <= r <= dmax + mm(0.15):
                return True
        return False
    edge = pcbnew.BOX2I(P(0.6, 0.6), pcbnew.VECTOR2I(mm(W - 1.2), mm(H - 1.2)))
    fps = sorted(board.GetFootprints(), key=lambda f: f.GetReference())
    for fp in fps:
        if fp.GetReference().startswith("H"):
            continue
        rt = fp.Reference()
        bb = fp.GetBoundingBox(False, False)
        cx, cy = bb.GetCenter().x, bb.GetCenter().y
        th = rt.GetBoundingBox().GetHeight()
        tw = rt.GetBoundingBox().GetWidth()
        g = mm(0.25)
        cands = [(cx, bb.GetTop() - th // 2 - g), (cx, bb.GetBottom() + th // 2 + g),
                 (bb.GetLeft() - tw // 2 - g, cy), (bb.GetRight() + tw // 2 + g, cy),
                 (bb.GetLeft() - tw // 2 - g, bb.GetTop() - th // 2), (bb.GetRight() + tw // 2 + g, bb.GetTop() - th // 2),
                 (bb.GetLeft() - tw // 2 - g, bb.GetBottom() + th // 2), (bb.GetRight() + tw // 2 + g, bb.GetBottom() + th // 2)]
        placed = False
        for (x, y) in cands:
            rt.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
            tb = rt.GetBoundingBox()
            tb.Inflate(mm(0.1))
            if not edge.Contains(tb):
                continue
            if hits(tb, fp):
                continue
            obstacles.append(rt.GetBoundingBox())
            placed = True
            break
        if not placed:
            # bez místa -> jen do výkresové vrstvy (Fab), na sítotisku nebude
            rt.SetLayer(pcbnew.F_Fab)
            rt.SetPosition(pcbnew.VECTOR2I(int(cx), int(cy)))


def silkscreen(board):
    S = pcbnew.F_SilkS
    # obrys OLED modulu (0,96" 27,3 x 27,8 mm), záhlaví vzadu (u x = 30,5)
    add_rect(board, 3.4, 6.35, 31.8, 33.65, pcbnew.F_Fab, 0.1)
    add_text(board, "OLED 0.96\" (zahlavi vzadu)", 17.0, 20.0, 1.0, pcbnew.F_Fab)
    for i, lbl in enumerate(["GND", "VCC", "SCL", "SDA"]):
        add_text(board, lbl, 27.4, 17.19 + i * 2.54, 0.8, S)
    for i, lbl in enumerate(["VCC", "GND", "TX", "RX", "AUX"]):
        add_text(board, lbl, 49.0 + i * 2.54, 39.6, 0.8, S)
    add_text(board, "MERIT", 37.75, 29.6, 0.8, S)
    add_text(board, "REZIM", 37.75, 18.6, 0.8, S)
    add_text(board, "BT", 47.4, 29.0, 0.8, S)
    add_text(board, "NABIJI", 85.0, 39.0, 0.8, S)
    add_text(board, "ON/OFF", 20.0, 6.0, 0.8, S)
    add_text(board, "+", 72.6, 36.6, 0.8, S, bold=True)
    add_text(board, "-", 77.4, 36.6, 0.8, S, bold=True)
    add_text(board, "1-2:3V3 2-3:BAT", 53.0, 25.1, 0.8, S)
    # spodní strana – název
    add_text(board, "LaserPlan v1.0", 15.5, 13.0, 2.0, pcbnew.B_SilkS, bold=True)
    add_text(board, "BLE laserovy metr", 15.5, 17.0, 1.2, pcbnew.B_SilkS)
    add_text(board, "ESP32-C3 / 2026", 15.5, 20.0, 1.0, pcbnew.B_SilkS)


# ---------------------------------------------------------------------------
# Autorouting – vlastní router (router.py), bez externích nástrojů
# ---------------------------------------------------------------------------
def route():
    import router
    return router.main()


# ---------------------------------------------------------------------------
# Rozlitá měď, prošívání, DRC
# ---------------------------------------------------------------------------
def add_zone(board, layer, net):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNetCode(net.GetNetCode())
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetLocalClearance(mm(0.3))
    z.SetMinThickness(mm(0.25))
    z.SetThermalReliefGap(mm(0.4))
    z.SetThermalReliefSpokeWidth(mm(0.4))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    z.SetAssignedPriority(0)
    pts = [(0.3, 0.3), (W - 0.3, 0.3), (W - 0.3, H - 0.3), (0.3, H - 0.3)]
    ol = z.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(mm(OX + x), mm(OY + y))
    board.Add(z)
    return z


def fill(board):
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())


def stitch(board, gnd, pitch=5.0, via_d=0.6, drill=0.3):
    """Prošívací GND prokovy všude, kde jsou obě vrstvy vylité a nic nepřekáží."""
    zones = [z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetCode() == gnd.GetNetCode()]
    keepouts = [z for z in board.Zones() if z.GetIsRuleArea()]
    obstacles = []
    for t in board.GetTracks():
        obstacles.append(t)
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    btexts = []
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.B_SilkS:
            bb = d.GetBoundingBox()
            bb.Inflate(mm(0.8))
            btexts.append(type("T", (), {"GetBoundingBox": lambda self, b=bb: b})())
    added = 0
    clearance = mm(0.35)
    y = 2.0
    while y < H - 1.5:
        x = 2.0
        while x < W - 1.5:
            pos = P(x, y)
            ok = all(any(z.GetLayer() == lay and z.HitTestFilledArea(lay, pos, mm(via_d / 2 + 0.25))
                         for z in zones) for lay in (pcbnew.F_Cu, pcbnew.B_Cu))
            if ok and any(t.GetBoundingBox().Contains(pos) for t in btexts):
                ok = False
            if ok and not any(k.Outline().Contains(pos) for k in keepouts):
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pos)
                v.SetWidth(mm(via_d))
                v.SetDrill(mm(drill))
                v.SetNetCode(gnd.GetNetCode())
                shape = v.GetEffectiveShape(pcbnew.F_Cu)
                bad = False
                for o in obstacles:
                    if o.GetNetCode() == gnd.GetNetCode() and o.Type() != pcbnew.PCB_VIA_T:
                        continue
                    if o.GetEffectiveShape(pcbnew.F_Cu if o.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu).Collide(shape, clearance):
                        bad = True
                        break
                if not bad:
                    for p in pads:
                        if p.GetEffectiveShape(pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu).Collide(shape, clearance + mm(0.1)):
                            bad = True
                            break
                    if not bad:
                        for fp in board.GetFootprints():
                            if fp.GetReference().startswith("H") and (fp.GetPosition() - pos).EuclideanNorm() < mm(3.5):
                                bad = True
                if not bad:
                    board.Add(v)
                    obstacles.append(v)
                    added += 1
            x += pitch
        y += pitch
    return added


def finish():
    board = pcbnew.LoadBoard(PCB)
    for z in list(board.Zones()):
        if not z.GetIsRuleArea():
            board.Remove(z)
    for t in list(board.GetTracks()):
        if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == "GND" and t.GetFlags() == 0 and getattr(t, "IsLocked", lambda: False)():
            board.Remove(t)
    gnd = board.FindNet("GND")
    add_zone(board, pcbnew.F_Cu, gnd)
    add_zone(board, pcbnew.B_Cu, gnd)
    fill(board)
    n = stitch(board, gnd)
    print("prošívacích prokovů:", n)
    fill(board)
    pcbnew.SaveBoard(PCB, board)
    rpt = os.path.join(KDIR, "drc_report.txt")
    pcbnew.WriteDRCReport(board, rpt, pcbnew.EDA_UNITS_MILLIMETRES, True)
    print(open(rpt).read()[-3000:])


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "place"
    {"place": place, "route": route, "finish": finish}[step]()
