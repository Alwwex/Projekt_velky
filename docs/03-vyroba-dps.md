# 3. Výroba desky plošného spoje

Vše potřebné je ve složce [`hardware/vyroba/`](../hardware/vyroba/):

| Soubor | K čemu |
|---|---|
| `laserplan-gerber.zip` | Gerbery + vrtání – **tohle nahraješ výrobci** |
| `bom.csv`, `bom.md` | kusovník (všechny součástky) |
| `bom-jlcpcb.csv`, `cpl-jlcpcb.csv` | podklady pro osazení SMD součástek u JLCPCB |
| `schema.pdf` | schéma zapojení (vytiskni si ho k pájení) |
| `laserplan.step` | 3D model osazené desky (kontrola krabičky ve FreeCADu/Fusion) |
| `gerber/laserplan-drl_map.pdf` | mapa vrtání |

## Parametry desky

- 2 vrstvy, **90 × 44 mm**, tloušťka 1,6 mm, měď 1 oz
- nejmenší cesta 0,2 mm, izolace 0,2 mm (0,15 mm u USB-C), prokovy 0,6/0,3 mm
- obě vrstvy vylité zemí (GND), anténa ESP32 je nad oblastí bez mědi
- 4 otvory M2.5 v rozích

To zvládne každý běžný levný výrobce (JLCPCB, PCBWay, Seeed, AISLER…).

## Objednání u JLCPCB (příklad)

1. Na jlcpcb.com klikni **Order now → Add gerber file** a nahraj `laserplan-gerber.zip`.
2. Nech výchozí hodnoty: *Layers 2, 1.6 mm, HASL (lead free)*; barva libovolná.
3. Množství 5 ks (minimum), objednej.

### Volitelně: osazení SMD součástek (PCB Assembly)

Ušetříš si pájení USB-C konektoru a malých součástek:

1. Zapni **PCB Assembly**, strana *Top*.
2. Nahraj `bom-jlcpcb.csv` a `cpl-jlcpcb.csv`.
3. Ve sloupci *LCSC Part #* doplň čísla dílů – v systému JLC je vyhledáš podle **MPN**
   (např. `MCP73831T-2ACI/OT`, `AP2112K-3.3TRG1`, `USBLC6-2SC6`, `AO3401A`, `AO3400A`,
   `TYPE-C-31-M-12`, `ESP32-C3-WROOM-02-N4`). Rezistory a kondenzátory 0805 vyber ze
   „Basic parts“ (bez příplatku). Čísla LCSC záměrně nejsou předvyplněná – mění se sklad a cena,
   zkontroluj je před objednáním.
4. Zkontroluj náhled natočení součástek (hlavně U1–U4, Q1–Q4, diody a LED).
5. Součástky THT (tlačítka, vypínač, bzučák, lišty, JST) připájíš ručně.

## Úprava návrhu

Desku otevřeš v **KiCadu 7+** (`hardware/kicad/laserplan.kicad_pro`). Celý návrh je ale vygenerovaný
skripty – pokud chceš změnit zapojení, uprav [`hardware/generator/circuit.py`](../hardware/generator/circuit.py)
a spusť `hardware/generator/build_all.sh`. Podrobnosti v [hardware/README.md](../hardware/README.md).
