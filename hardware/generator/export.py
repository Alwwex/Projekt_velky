#!/usr/bin/env python3
"""
Výrobní podklady LaserPlan -> hardware/vyroba/

  laserplan-gerber.zip   Gerbery + vrtání (nahraj na JLCPCB / PCBWay / ...)
  bom.csv                kusovník (všechny součástky na desce)
  bom-jlcpcb.csv         kusovník pro osazení SMD u JLCPCB (doplň LCSC čísla)
  cpl-jlcpcb.csv         souřadnice SMD součástek pro osazení
  schema.pdf             schéma zapojení
  laserplan.step         3D model osazené desky (pro konstrukci krabičky)
  ../../docs/img/        náhledy desky a schématu (PNG)
"""
import csv
import glob
import os
import re
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import circuit  # noqa: E402
import gen_pcb  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
KDIR = gen_pcb.KDIR
OUT = os.path.normpath(os.path.join(HERE, "..", "vyroba"))
IMG = os.path.normpath(os.path.join(HERE, "..", "..", "docs", "img"))
PCB = gen_pcb.PCB
SCH = os.path.join(KDIR, "laserplan.kicad_sch")


def run(*args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        raise SystemExit("selhalo: " + " ".join(args))
    return r.stdout


def gerbers():
    gdir = os.path.join(OUT, "gerber")
    shutil.rmtree(gdir, ignore_errors=True)
    os.makedirs(gdir)
    run("kicad-cli", "pcb", "export", "gerbers", "--layers",
        "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts",
        "--subtract-soldermask", "--no-x2", "-o", gdir + "/", PCB)
    run("kicad-cli", "pcb", "export", "drill", "--format", "excellon", "--drill-origin", "absolute",
        "--excellon-units", "mm", "--generate-map", "--map-format", "pdf", "-o", gdir + "/", PCB)
    zpath = os.path.join(OUT, "laserplan-gerber.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(glob.glob(os.path.join(gdir, "*"))):
            if f.endswith(".pdf"):
                continue
            z.write(f, os.path.basename(f))
    print("gerbery:", zpath, sorted(os.listdir(gdir)))


def bom():
    groups = {}
    for p in circuit.PARTS:
        key = (p["value"], p["footprint"], p["mpn"])
        groups.setdefault(key, []).append(p)
    rows = []
    for (value, fpid, mpn), parts in groups.items():
        refs = sorted((p["ref"] for p in parts), key=lambda r: (re.sub(r"\d", "", r), int(re.sub(r"\D", "", r) or 0)))
        p0 = parts[0]
        descs = {p["desc"] for p in parts}
        desc = p0["desc"] if len(descs) == 1 else {
            "Device:C": "Kondenzátor MLCC (blokování / filtrace)",
            "Device:R": "Rezistor (pull-up / dělič / omezení proudu)"}.get(p0["symbol"], "; ".join(sorted(descs)))
        rows.append({"Označení": ",".join(refs), "Počet": len(refs), "Hodnota": value,
                     "Pouzdro": fpid.split(":")[1], "Výrobce": p0["manufacturer"], "MPN": mpn,
                     "Montáž": "SMD" if p0.get("smd") else "THT (ručně)",
                     "Osadit": "ne (propojka)" if p0.get("no_bom") else "ano", "Popis": desc})
    rows.sort(key=lambda r: r["Označení"])
    with open(os.path.join(OUT, "bom.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(rows)
    # JLCPCB formát (jen SMD)
    with open(os.path.join(OUT, "bom-jlcpcb.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "MPN"])
        for r in rows:
            if r["Montáž"] != "SMD" or r["Osadit"] != "ano":
                continue
            w.writerow([r["Hodnota"], r["Označení"], r["Pouzdro"], "", r["MPN"]])
    # Markdown verze pro dokumentaci
    with open(os.path.join(OUT, "bom.md"), "w", encoding="utf-8") as f:
        f.write("# Kusovník desky LaserPlan\n\n_Vygenerováno z `hardware/generator/circuit.py`._\n\n")
        f.write("| Označení | Ks | Hodnota | Pouzdro | Výrobce / MPN | Montáž | Popis |\n|---|---|---|---|---|---|---|\n")
        for r in rows:
            f.write(f"| {r['Označení'].replace(',', ', ')} | {r['Počet']} | {r['Hodnota']} | {r['Pouzdro']} | "
                    f"{r['Výrobce']} / {r['MPN']} | {r['Montáž']} | {r['Popis']}"
                    f"{' (neosazuje se)' if r['Osadit'] != 'ano' else ''} |\n")
    print("bom: %d řádků" % len(rows))
    return rows


def cpl():
    tmp = os.path.join(OUT, "_pos.csv")
    run("kicad-cli", "pcb", "export", "pos", "--side", "front", "--format", "csv", "--units", "mm",
        "--smd-only", "-o", tmp, PCB)
    nobom = {p["ref"] for p in circuit.PARTS if p.get("no_bom")}
    with open(tmp, encoding="utf-8") as f, open(os.path.join(OUT, "cpl-jlcpcb.csv"), "w", newline="", encoding="utf-8") as g:
        w = csv.writer(g)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for row in csv.DictReader(f):
            if row["Ref"] in nobom:
                continue
            # osa Y v KiCadu míří dolů; JLC očekává kartézské souřadnice
            w.writerow([row["Ref"], "%.3fmm" % float(row["PosX"]), "%.3fmm" % -float(row["PosY"]),
                        "Top", "%.1f" % float(row["Rot"])])
    os.remove(tmp)
    print("cpl hotovo")


def schematic():
    run("kicad-cli", "sch", "export", "pdf", "-o", os.path.join(OUT, "schema.pdf"), SCH)
    tmpd = os.path.join(OUT, "_svg")
    run("kicad-cli", "sch", "export", "svg", "-o", tmpd, SCH)
    import cairosvg
    os.makedirs(IMG, exist_ok=True)
    cairosvg.svg2png(url=glob.glob(tmpd + "/*.svg")[0], write_to=os.path.join(IMG, "schema.png"),
                     output_width=3000, background_color="white")
    shutil.rmtree(tmpd)


def step():
    env = dict(os.environ, KICAD7_3DMODEL_DIR="/usr/share/kicad/3dmodels")
    out = os.path.join(OUT, "laserplan.step")
    r = subprocess.run(["kicad-cli", "pcb", "export", "step", "--subst-models", "--force", "-o", out, PCB],
                       capture_output=True, text=True, env=env)
    print("step:", "OK %.1f MB" % (os.path.getsize(out) / 1e6) if os.path.exists(out) else r.stdout[-500:])


# --- "fotorealistický" náhled: vrstvy obarvíme a složíme na sebe
COLORS = {"board": "#0f5132", "Cu": "#1f7a4d", "Mask": "#d4a84a", "SilkS": "#f4f4f0", "Edge": "#0b3d26"}


def layer_svg(layer, mirror=False):
    tmp = os.path.join(OUT, "_l.svg")
    args = ["kicad-cli", "pcb", "export", "svg", "--layers", layer + ",Edge.Cuts" if layer != "Edge.Cuts" else layer,
            "--black-and-white", "--page-size-mode", "2", "--exclude-drawing-sheet", "-o", tmp, PCB]
    if mirror:
        args.insert(-3, "--mirror")
    run(*args)
    txt = open(tmp, encoding="utf-8").read()
    os.remove(tmp)
    return txt


def render(side):
    import cairosvg
    pre = "F" if side == "top" else "B"
    mirror = side == "bottom"
    base = layer_svg("Edge.Cuts", mirror)
    m = re.search(r'<svg[^>]*>', base)
    head = m.group(0)
    vb = re.search(r'viewBox="([^"]+)"', head).group(1).split()
    x0, y0, w, h = map(float, vb)

    def body(svg, color):
        inner = svg[svg.index(">", svg.index("<svg")) + 1: svg.rindex("</svg>")]
        inner = re.sub(r"(fill|stroke)(:|=\")#?(000000|000|black)", lambda mm: mm.group(1) + mm.group(2) + color, inner, flags=re.I)
        inner = re.sub(r"(fill|stroke):(#[0-9A-Fa-f]{6})", lambda mm: mm.group(1) + ":" + color if mm.group(2).upper() in ("#000000",) else mm.group(0), inner)
        return inner

    parts = [f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="#ffffff"/>']
    # deska = vyplněný obrys (zjednodušeně obdélník se zaoblením)
    # levý horní roh obrysu = nejmenší souřadnice čar Edge.Cuts (jednotky = mm)
    pts = [(float(a), float(b)) for a, b in re.findall(r"[ML]\s*(-?[\d.]+)[ ,]+(-?[\d.]+)", base)]
    bx = min(p[0] for p in pts)
    by = min(p[1] for p in pts)
    r = gen_pcb.CORNER_R
    bw, bh = gen_pcb.W, gen_pcb.H
    parts.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="{r}" fill="{COLORS["board"]}"/>')
    parts.append(body(layer_svg(pre + ".Cu", mirror), COLORS["Cu"]))
    parts.append(body(layer_svg(pre + ".Mask", mirror), COLORS["Mask"]))
    parts.append(body(layer_svg(pre + ".SilkS", mirror), COLORS["SilkS"]))
    svg = head + "".join(parts) + "</svg>"
    os.makedirs(IMG, exist_ok=True)
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=os.path.join(IMG, f"pcb-{side}.png"),
                     output_width=1800)
    print("náhled", side)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    gerbers()
    bom()
    cpl()
    schematic()
    render("top")
    render("bottom")
    if "--step" in sys.argv:
        step()
