#!/usr/bin/env bash
# Kompletní regenerace hardwaru LaserPlan (KiCad 7 + Python 3, numpy, cairosvg)
#   schéma -> rozmístění -> autorouting -> rozlitá měď + DRC -> výrobní data
set -euo pipefail
cd "$(dirname "$0")"
python3 gen_schematic.py
python3 router.py            # obsahuje i rozmístění (gen_pcb.place)
python3 gen_pcb.py finish    # GND plochy, prošívání, DRC report -> ../kicad/drc_report.txt
python3 export.py --step     # Gerbery, BOM, CPL, PDF schéma, náhledy, STEP
grep -E "^\*\* Found" ../kicad/drc_report.txt
python3 check.py             # schéma == deska == circuit.py
