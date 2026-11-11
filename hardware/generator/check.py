#!/usr/bin/env python3
"""Kontrola konzistence: schéma (netlist z kicad-cli) == deska (pcbnew) == circuit.py."""
import os
import subprocess
import sys
import tempfile

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import circuit  # noqa: E402
import gen_pcb  # noqa: E402
from sexpr import find, find_all, parse  # noqa: E402

expected = {k: sorted(v) for k, v in circuit.nets().items() if k not in circuit.NO_CONNECT_NETS}

# --- schéma
with tempfile.TemporaryDirectory() as d:
    out = os.path.join(d, "n.net")
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "-o", out,
                    os.path.join(gen_pcb.KDIR, "laserplan.kicad_sch")], check=True, capture_output=True)
    root = parse(open(out, encoding="utf-8").read())
sch = {}
for n in find_all(find(root, "nets"), "net"):
    name = find(n, "name")[1].lstrip("/")
    nodes = sorted((find(x, "ref")[1], find(x, "pin")[1]) for x in find_all(n, "node")
                   if not find(x, "ref")[1].startswith("#"))
    if nodes and not name.startswith("unconnected"):
        sch[name] = nodes

# --- deska
board = pcbnew.LoadBoard(gen_pcb.PCB)
pcb = {}
for fp in board.GetFootprints():
    for pad in fp.Pads():
        net = pad.GetNetname()
        if net:
            pcb.setdefault(net, set()).add((fp.GetReference(), pad.GetNumber()))
pcb = {k: sorted(v) for k, v in pcb.items()}

ok = True
for label, got in (("schéma", sch), ("deska", pcb)):
    bad = [k for k in expected if got.get(k) != expected[k]] + [k for k in got if k not in expected]
    print(f"{label:7s}: {len(got)} sítí, rozdíly: {bad or 'žádné'}")
    ok &= not bad
sys.exit(0 if ok else 1)
