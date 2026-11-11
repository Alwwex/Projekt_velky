#!/usr/bin/env python3
"""
Jednoduchý, ale DRC-korektní dvouvrstvý autorouter pro KiCad 7 (pcbnew).

Princip
-------
* Deska se navzorkuje jemnou mřížkou (krok H = 0,125 mm). Pro každou vrstvu se
  udržuje přesná vzdálenost k nejbližší mědi a k nejbližší mědi JINÉ sítě
  (trik "dvou nejbližších značek"), takže legálnost cesty pro libovolnou síť
  lze spočítat jedním numpy výrazem.
* Cesty vedou po uzlech mřížky s krokem 2H = 0,25 mm (8 směrů, 45° úhly).
  Kontroluje se i střed každého kroku, takže chyba diskretizace je < 0,02 mm.
* Hledání cesty: A* se stavem (vrstva, uzel, směr) – penalizace lomů a prokovů.
* Vícebodové sítě se stavějí jako strom (multi-source A* k nejbližší ploše).
* Při neúspěchu: rip-up & reroute – vytrhne sítě, které překážejí, a zkusí
  pořadí znovu.

Použití:  python3 router.py  (čte a přepisuje kicad/laserplan.kicad_pcb)
"""
import heapq
import math
import os
import sys
import time

import numpy as np
import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import circuit  # noqa: E402
import gen_pcb  # noqa: E402

H = 0.125                     # vzorkování (mm)
CLR = 0.20                    # izolační mezera (mm)
EDGE_CLR = 0.35               # od hrany desky
MARGIN = 0.03                 # rezerva na diskretizaci
VIA_D, VIA_DRILL = 0.6, 0.3
DEFAULT_W = 0.25
INFL = 1.2                    # dosah vlivu jednoho objektu (mm)
COST_VIA = 24.0
COST_BEND45 = 1.0
COST_BEND90 = 4.0
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)

DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]

# Únikové koridory (zde nepoužité – USB-C řeší pevné vyvedení níže)
ESCAPE = {}

# Pevně navržené vyvedení USB-C (J1 na (86,3; 24,0), otočení 90°).
# Piny D+/D- se v řadě střídají (D+ 23,25 | D- 23,75 | D+ 24,25 | D- 24,75),
# proto: D+ spojeno "U" smyčkou nahoře, D- jde přes dva prokovy a spodní vrstvu.
# Formát: síť -> [(vrstva 0=F/1=B, [(x, y), ...]), ...]  (mm, mřížka 0,25)
PREROUTE = {
    "USB_DP": [(0, [(82.25, 23.25), (81.25, 23.25), (80.75, 22.75), (79.25, 22.75), (79.25, 24.25)]),
               (0, [(82.25, 24.25), (79.25, 24.25)])],
    "USB_DN": [(0, [(82.25, 23.75), (81.0, 23.75), (80.75, 23.5), (80.5, 23.5)]),
               (0, [(82.25, 24.75), (80.75, 24.75), (80.5, 25.0)]),
               ("via", [(80.5, 23.5), (80.5, 25.0)]),
               (1, [(80.5, 23.5), (80.5, 25.0)])],
    "CC1": [(0, [(82.25, 25.25), (81.25, 25.25), (80.75, 25.75)])],
    # GND vývod ESD ochrany U1 leží mezi linkami D+/D- -> hned prokov do spodní země
    "GND": [(0, [(69.5, 14.0), (68.5, 14.0)]), ("via", [(68.5, 14.0)])],
}
PREROUTE_W = 0.2


def to_mm(v):
    return pcbnew.ToMM(v)


class Grid:
    def __init__(self, W, Hh, ox, oy):
        self.W, self.Hh, self.ox, self.oy = W, Hh, ox, oy
        self.NX = int(round(W / H)) + 1
        self.NY = int(round(Hh / H)) + 1
        shp = (2, self.NY, self.NX)
        self.d1 = np.full(shp, np.inf, np.float32)
        self.n1 = np.full(shp, -999999, np.int32)
        self.d2 = np.full(shp, np.inf, np.float32)
        self.keep = np.zeros(shp, bool)          # zakázané oblasti pro cesty
        self.novia = np.zeros((self.NY, self.NX), bool)
        xs = np.arange(self.NX) * H
        ys = np.arange(self.NY) * H
        self.X, self.Y = np.meshgrid(xs, ys)
        # vzdálenost dovnitř od hrany desky (obdélník se zaoblenými rohy)
        r = gen_pcb.CORNER_R
        cx, cy = W / 2, Hh / 2
        qx = np.abs(self.X - cx) - (W / 2 - r)
        qy = np.abs(self.Y - cy) - (Hh / 2 - r)
        outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r
        self.edge_in = (-outside).astype(np.float32)

    # ---- okno indexů pro bbox
    def window(self, x0, y0, x1, y1, infl=INFL):
        i0 = max(0, int(math.floor((y0 - infl) / H)))
        i1 = min(self.NY, int(math.ceil((y1 + infl) / H)) + 1)
        j0 = max(0, int(math.floor((x0 - infl) / H)))
        j1 = min(self.NX, int(math.ceil((x1 + infl) / H)) + 1)
        return i0, i1, j0, j1

    def merge(self, li, label, win, dn):
        i0, i1, j0, j1 = win
        d1 = self.d1[li, i0:i1, j0:j1]
        n1 = self.n1[li, i0:i1, j0:j1]
        d2 = self.d2[li, i0:i1, j0:j1]
        same = n1 == label
        closer = (~same) & (dn < d1)
        other = (~same) & (~closer)
        # stejná značka
        np.minimum(d1, np.where(same, dn, np.inf), out=d1)
        # nová nejbližší jiná značka
        d2[closer] = d1[closer]
        n1[closer] = label
        d1[closer] = dn[closer]
        # dál než nejbližší
        np.minimum(d2, np.where(other, dn, np.inf), out=d2)

    # ---- primitiva vzdálenosti
    def add_poly(self, li, label, pts):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        win = self.window(min(xs), min(ys), max(xs), max(ys))
        i0, i1, j0, j1 = win
        X = self.X[i0:i1, j0:j1]
        Y = self.Y[i0:i1, j0:j1]
        d = poly_dist(X, Y, pts)
        self.merge(li, label, win, d)
        return d, win

    def add_seg(self, li, label, a, b, w):
        win = self.window(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
        i0, i1, j0, j1 = win
        X = self.X[i0:i1, j0:j1]
        Y = self.Y[i0:i1, j0:j1]
        d = np.maximum(seg_dist(X, Y, a, b) - w / 2, 0).astype(np.float32)
        self.merge(li, label, win, d)

    def add_circle(self, li, label, c, r):
        win = self.window(c[0], c[1], c[0], c[1])
        i0, i1, j0, j1 = win
        X = self.X[i0:i1, j0:j1]
        Y = self.Y[i0:i1, j0:j1]
        d = np.maximum(np.hypot(X - c[0], Y - c[1]) - r, 0).astype(np.float32)
        self.merge(li, label, win, d)

    def legal(self, label, hw):
        """Bool pole [2,NY,NX]: střed cesty polovičné šířky hw smí ležet zde."""
        od = np.where(self.n1 == label, self.d2, self.d1)
        ok = od > (hw + CLR + MARGIN)
        ok &= (self.edge_in > hw + EDGE_CLR)[None, :, :]
        ok &= ~self.keep
        return ok


def seg_dist(X, Y, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return np.hypot(X - ax, Y - ay)
    t = np.clip(((X - ax) * dx + (Y - ay) * dy) / L2, 0, 1)
    return np.hypot(X - (ax + t * dx), Y - (ay + t * dy))


def poly_dist(X, Y, pts):
    n = len(pts)
    d = np.full(X.shape, np.inf)
    inside = np.zeros(X.shape, bool)
    for k in range(n):
        a = pts[k]
        b = pts[(k + 1) % n]
        d = np.minimum(d, seg_dist(X, Y, a, b))
        # even-odd
        cond = ((a[1] > Y) != (b[1] > Y))
        with np.errstate(divide="ignore", invalid="ignore"):
            xint = (b[0] - a[0]) * (Y - a[1]) / (b[1] - a[1] + 1e-12) + a[0]
        inside ^= cond & (X < xint)
    d[inside] = 0
    return d.astype(np.float32)


# ---------------------------------------------------------------------------
class Router:
    def __init__(self, board):
        self.board = board
        self.ox, self.oy = gen_pcb.OX, gen_pcb.OY
        self.g = Grid(gen_pcb.W, gen_pcb.H, self.ox, self.oy)
        self.nets = {}            # jméno -> label
        self.pads = []            # dict(net, layers, poly, center)
        self.routes = {}          # net -> list of paths (list of (li, x, y))
        self.vias = {}            # net -> list of (x, y)
        self.width = {}
        self.unreached = []
        self.fixed = {}           # net -> list of paths (předem navržené)
        self.done = getattr(self, "done", set())
        self._extract()
        self._apply_preroute()

    def bm(self, v):
        """Souřadnice KiCad (nm) -> mm vůči desce."""
        return (to_mm(v.x) - self.ox, to_mm(v.y) - self.oy)

    def _extract(self):
        names = sorted({n for p in circuit.PARTS for n in p["pins"].values()} - circuit.NO_CONNECT_NETS)
        for i, n in enumerate(names):
            self.nets[n] = i
            self.width[n] = circuit.NET_WIDTH.get(n, DEFAULT_W)
        self.width["GND"] = 0.35
        uniq = -10
        body_keep = []
        for fp in self.board.GetFootprints():
            ref = fp.GetReference()
            if ref == "U4":
                # pod tělem modulu nevedeme cesty po horní vrstvě
                pos = self.bm(fp.GetPosition())
                body_keep.append((pos[0] - 8.0, pos[1] - 12.6, pos[0] + 8.0, pos[1] + 6.2))
            for z in fp.Zones():
                if z.GetIsRuleArea():
                    ol = z.Outline().Outline(0)
                    pts = [self.bm(ol.CPoint(k)) for k in range(ol.PointCount())]
                    self._keep_poly(pts, (0, 1))
            for pad in fp.Pads():
                lays = [li for li, L in enumerate(LAYERS) if pad.IsOnLayer(L)]
                if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    c = self.bm(pad.GetPosition())
                    r = to_mm(pad.GetDrillSize().x) / 2 + 0.07   # izolace od otvoru 0,25 mm
                    if ref.startswith("H"):
                        r = 2.6          # hlava šroubu M2.5
                    for li in (0, 1):
                        self.g.add_circle(li, uniq, c, r)
                    uniq -= 1
                    continue
                if not lays:
                    continue
                netname = pad.GetNetname()
                if netname in self.nets:
                    label = self.nets[netname]
                else:
                    label = uniq
                    uniq -= 1
                ol = pad.GetEffectivePolygon().Outline(0)
                pts = [self.bm(ol.CPoint(k)) for k in range(ol.PointCount())]
                info = dict(net=netname, label=label, layers=lays, poly=pts,
                            center=self.bm(pad.GetPosition()), ref=ref, num=pad.GetNumber(),
                            smd=pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD)
                dmask = None
                for li in lays:
                    d, win = self.g.add_poly(li, label, pts)
                    dmask = (d, win)
                info["mask"] = dmask
                if info["smd"]:
                    # žádné prokovy v plošce
                    d, (i0, i1, j0, j1) = dmask
                    self.g.novia[i0:i1, j0:j1] |= d < (VIA_D / 2 + 0.15)
                if (ref, pad.GetNumber()) in ESCAPE and label >= 0:
                    # rezervovaný únikový koridor pro jemnou rozteč (jen vlastní síť)
                    dx, dy, length = ESCAPE[(ref, pad.GetNumber())]
                    c = info["center"]
                    self.g.add_seg(0, label, c, (c[0] + dx * length, c[1] + dy * length), 0.2)
                self.pads.append(info)
        for (x0, y0, x1, y1) in body_keep:
            self.g.keep[0] |= (self.g.X > x0) & (self.g.X < x1) & (self.g.Y > y0) & (self.g.Y < y1)
            # ale plošky modulu samotné zůstávají dosažitelné (jsou na kraji)
        # otvory pro šrouby: také žádné prokovy
        for fp in self.board.GetFootprints():
            if fp.GetReference().startswith("H"):
                c = self.bm(fp.GetPosition())
                self.g.novia |= np.hypot(self.g.X - c[0], self.g.Y - c[1]) < 3.0

    def _expand(self, li, pts):
        """Lomená čára (mm) -> posloupnost uzlů (li, x, y) v H-souřadnicích."""
        out = []
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            a = (int(round(x0 / H)), int(round(y0 / H)))
            b = (int(round(x1 / H)), int(round(y1 / H)))
            assert a[0] % 2 == 0 and a[1] % 2 == 0 and b[0] % 2 == 0 and b[1] % 2 == 0, "mimo mřížku"
            dx = (b[0] > a[0]) - (b[0] < a[0])
            dy = (b[1] > a[1]) - (b[1] < a[1])
            n = max(abs(b[0] - a[0]), abs(b[1] - a[1])) // 2
            assert dx == 0 or dy == 0 or abs(b[0] - a[0]) == abs(b[1] - a[1]), "jen 0/45/90°"
            first = 0 if not out else 1
            for kk in range(first, n + 1):
                out.append((li, a[0] + 2 * dx * kk, a[1] + 2 * dy * kk))
        return out

    def _apply_preroute(self):
        for net, items in PREROUTE.items():
            if net not in self.nets:
                continue
            label = self.nets[net]
            for li, pts in items:
                if li == "via":
                    for (xa, ya) in pts:
                        a = (0, int(round(xa / H)), int(round(ya / H)))
                        path = [a, (1, a[1], a[2])]
                        for L in (0, 1):
                            self.g.add_circle(L, label, self.node_xy(a[1], a[2]), VIA_D / 2)
                        self.fixed.setdefault(net, []).append(path)
                    continue
                path = self._expand(li, pts)
                for a, b in zip(path, path[1:]):
                    if a[0] != b[0]:
                        c = self.node_xy(a[1], a[2])
                        for L in (0, 1):
                            self.g.add_circle(L, label, c, VIA_D / 2)
                    else:
                        self.g.add_seg(a[0], label, self.node_xy(a[1], a[2]), self.node_xy(b[1], b[2]), PREROUTE_W)
                self.fixed.setdefault(net, []).append(path)

    def _keep_poly(self, pts, layers):
        d = poly_dist(self.g.X, self.g.Y, pts)
        for li in layers:
            self.g.keep[li] |= d < 0.3
        self.g.novia |= d < 0.5

    # ------------------------------------------------------------------
    def node_xy(self, x, y):
        return (float(x) * H, float(y) * H)

    def pad_nodes(self, pad, legal):
        """Sudé uzly mřížky uvnitř plošky, které jsou legální."""
        d, (i0, i1, j0, j1) = pad["mask"]
        out = []
        ii, jj = np.nonzero(d <= 0)
        for a, b in zip(ii, jj):
            i, j = int(i0 + a), int(j0 + b)
            if i % 2 or j % 2:
                continue
            for li in pad["layers"]:
                if legal[li, i, j]:
                    out.append((li, j, i))
        return out

    def astar(self, sources, targets, legal, via_ok, tcenters):
        """sources/targets: množiny (li, x, y) v H-souřadnicích (sudé)."""
        NX, NY = self.g.NX, self.g.NY
        tset = set(targets)
        L0 = legal[0].tobytes()
        L1 = legal[1].tobytes()
        LL = (L0, L1)
        VO = via_ok.tobytes()
        gbest = {}
        heap = []
        tc = tcenters

        def h(x, y):
            best = 1e18
            for (tx, ty) in tc:
                dx = abs(x - tx)
                dy = abs(y - ty)
                v = (dx + dy) + (0.41421356 * min(dx, dy) - min(dx, dy))  # oktilová
                if v < best:
                    best = v
            return best

        cnt = 0
        for s in sources:
            li, x, y = s
            key = (li, x, y, 8)
            gbest[key] = 0.0
            heapq.heappush(heap, (h(x, y), 0.0, cnt, li, x, y, 8, None))
            cnt += 1
        parent = {}
        expanded = 0
        while heap:
            f, gc, _, li, x, y, d, par = heapq.heappop(heap)
            key = (li, x, y, d)
            if gbest.get(key, 1e18) < gc:
                continue
            parent[key] = par
            if (li, x, y) in tset:
                # rekonstrukce
                path = []
                k = key
                while k is not None:
                    path.append((k[0], k[1], k[2]))
                    k = parent[k]
                path.reverse()
                return path
            expanded += 1
            if expanded > 600000:
                return None
            Lb = LL[li]
            for nd, (dx, dy) in enumerate(DIRS):
                if d != 8:
                    diff = (nd - d) % 8
                    if diff == 4:
                        continue
                    if diff in (3, 5):
                        continue          # ostré úhly 135° zakázat
                nx, ny = x + 2 * dx, y + 2 * dy
                if nx < 0 or ny < 0 or nx >= NX or ny >= NY:
                    continue
                if not Lb[ny * NX + nx] or not Lb[(y + dy) * NX + (x + dx)]:
                    continue
                step = 2.8284 if dx and dy else 2.0
                if d != 8:
                    if diff in (1, 7):
                        step += COST_BEND45
                    elif diff in (2, 6):
                        step += COST_BEND90
                ng = gc + step
                nk = (li, nx, ny, nd)
                if ng < gbest.get(nk, 1e18):
                    gbest[nk] = ng
                    heapq.heappush(heap, (ng + h(nx, ny), ng, cnt, li, nx, ny, nd, key))
                    cnt += 1
            # prokov
            if VO[y * NX + x]:
                ol = 1 - li
                if LL[ol][y * NX + x]:
                    ng = gc + COST_VIA
                    nk = (ol, x, y, 8)
                    if ng < gbest.get(nk, 1e18):
                        gbest[nk] = ng
                        heapq.heappush(heap, (ng + h(x, y), ng, cnt, ol, x, y, 8, key))
                        cnt += 1
        return None

    # ------------------------------------------------------------------
    def commit_path(self, net, path, w):
        label = self.nets[net]
        for a, b in zip(path, path[1:]):
            if a[0] != b[0]:
                c = self.node_xy(a[1], a[2])
                for li in (0, 1):
                    self.g.add_circle(li, label, c, VIA_D / 2)
                self.vias.setdefault(net, []).append(c)
            else:
                self.g.add_seg(a[0], label, self.node_xy(a[1], a[2]), self.node_xy(b[1], b[2]), w)
        self.routes.setdefault(net, []).append(path)

    def route_net(self, net):
        label = self.nets[net]
        pads = [p for p in self.pads if p["net"] == net]
        if len(pads) < 2:
            return True
        w = self.width[net]
        partial = net == "GND"
        widths = [w] + [x for x in (0.4, DEFAULT_W, 0.2) if x < w]
        for attempt_w in widths:
            hw = attempt_w / 2
            legal = self.g.legal(label, hw)
            vleg = self.g.legal(label, VIA_D / 2)
            via_ok = vleg[0] & vleg[1] & ~self.g.novia
            # strom: začni ploškou nejblíž těžišti
            remaining = list(range(len(pads)))
            cx = sum(p["center"][0] for p in pads) / len(pads)
            cy = sum(p["center"][1] for p in pads) / len(pads)
            remaining.sort(key=lambda k: math.hypot(pads[k]["center"][0] - cx, pads[k]["center"][1] - cy))
            tree = set()
            for fp_path in self.fixed.get(net, []):
                tree.update(fp_path)
            if tree:
                # plošky, kterých se už dotýká pevná cesta, jsou připojené
                for k in list(remaining):
                    d, (i0, i1, j0, j1) = pads[k]["mask"]
                    hit = any(n[0] in pads[k]["layers"] and i0 <= n[2] < i1 and j0 <= n[1] < j1
                              and d[n[2] - i0, n[1] - j0] <= 0 for n in tree)
                    if hit:
                        remaining.remove(k)
                        tree.update(self.pad_nodes(pads[k], legal))
            while remaining and not tree:
                first = remaining.pop(0)
                tree = set(self.pad_nodes(pads[first], legal))
            if not tree:
                print(f"   ! {net}: ploška {pads[first]['ref']}.{pads[first]['num']} nedosažitelná (w={attempt_w})")
                continue
            paths = []
            ok = True
            while remaining:
                targets = {}
                for k in remaining:
                    for n in self.pad_nodes(pads[k], legal):
                        targets[n] = k
                if not targets:
                    if partial:
                        self.unreached.extend(f"{pads[k]['ref']}.{pads[k]['num']}" for k in remaining)
                    ok = partial
                    break
                tcent = list({(int(round(pads[k]["center"][0] / H)), int(round(pads[k]["center"][1] / H)))
                              for k in remaining})
                path = self.astar(tree, list(targets), legal, via_ok, tcent)
                if path is None:
                    if partial:
                        self.unreached.extend(f"{pads[k]['ref']}.{pads[k]['num']}" for k in remaining)
                    ok = partial
                    break
                k = targets[path[-1]]
                remaining.remove(k)
                paths.append(path)
                tree.update(path)
                tree.update(self.pad_nodes(pads[k], legal))
            if ok:
                for p in paths:
                    self.commit_path(net, p, attempt_w)
                self.width[net] = attempt_w
                return True
        return False

    def fanout(self, net, pad):
        """Krátké vyvedení plošky na prokov (napojí ji spodní rozlitá měď)."""
        label = self.nets[net]
        hw = self.width[net] / 2
        legal = self.g.legal(label, hw)
        vleg = self.g.legal(label, VIA_D / 2)
        via_ok = vleg[0] & vleg[1] & ~self.g.novia
        src = [n for n in self.pad_nodes(pad, legal) if n[0] == 0]
        if not src:
            return False
        cx, cy = pad["center"]
        targets = []
        R = int(8.0 / H)
        i0, j0 = int(cy / H), int(cx / H)
        for i in range(max(0, i0 - R) & ~1, min(self.g.NY, i0 + R), 2):
            for j in range(max(0, j0 - R) & ~1, min(self.g.NX, j0 + R), 2):
                if via_ok[i, j] and legal[0, i, j] and legal[1, i, j]:
                    targets.append((0, j, i))
        if not targets:
            return False
        path = self.astar(set(src), targets, legal, via_ok, [(j0, i0)])
        if not path:
            return False
        path = path + [(1, path[-1][1], path[-1][2])]
        self.commit_path(net, path, self.width[net])
        return True

    def rip(self, net):
        """Odstraní cesty sítě – přepočítá pole vzdáleností od nuly (jednoduché)."""
        self.routes.pop(net, None)
        self.vias.pop(net, None)
        self.rebuild()

    def rebuild(self):
        routes, vias = self.routes, self.vias
        widths = dict(self.width)
        unreached = self.unreached
        done = self.done
        self.__init__(self.board)
        self.unreached = unreached
        self.done = done
        self.width.update(widths)
        for net, paths in routes.items():
            for p in paths:
                self.commit_path(net, p, self.width[net])
        self.vias = {}
        for net, paths in self.routes.items():
            for p in paths:
                for a, b in zip(p, p[1:]):
                    if a[0] != b[0]:
                        self.vias.setdefault(net, []).append(self.node_xy(a[1], a[2]))

    # ------------------------------------------------------------------
    def order(self):
        def span(net):
            ps = [p["center"] for p in self.pads if p["net"] == net]
            if len(ps) < 2:
                return 0
            xs = [p[0] for p in ps]
            ys = [p[1] for p in ps]
            return (max(xs) - min(xs)) + (max(ys) - min(ys))
        nets = [n for n in self.nets if n != "GND"]
        prio = ["USB_DP", "USB_DN", "CC1", "CC2"]
        nets.sort(key=lambda n: (n not in prio, span(n)))
        return nets + ["GND"]

    def run(self, max_rounds=6):
        ok = self._run(max_rounds)
        # GND plošky, ke kterým se nedostala cesta -> vyvést na prokov
        still = []
        for name in self.unreached:
            ref, num = name.split(".")
            pads = [p for p in self.pads if p["ref"] == ref and p["num"] == num and p["net"] == "GND"]
            if pads and pads[0]["smd"] and not self.fanout("GND", pads[0]):
                still.append(name)
            elif pads and not pads[0]["smd"]:
                still.append(name)
        self.unreached = still
        return ok

    def _run(self, max_rounds=6):
        order = self.order()
        for rnd in range(max_rounds):
            failed = []
            t0 = time.time()
            for net in order:
                if net in self.done:
                    continue
                ok = self.route_net(net)
                if ok:
                    self.done.add(net)
                print(f"  {'OK ' if ok else 'XX '} {net:12s} w={self.width[net]:.2f}  ({time.time() - t0:5.1f}s)")
                if not ok:
                    failed.append(net)
            if not failed:
                return True
            print("Nerozvedeno:", failed)
            if rnd == max_rounds - 1:
                break
            # rip-up: všechno zahodit a dát neúspěšné sítě na začátek
            order = failed + [n for n in order if n not in failed]
            self.unreached = []
            self.routes, self.vias = {}, {}
            self.done = set()
            self.rebuild()
        return False

    # ------------------------------------------------------------------
    def write(self):
        b = self.board
        for t in list(b.GetTracks()):
            b.Remove(t)
        allnets = set(self.routes) | set(self.fixed)
        for net in sorted(allnets):
            ni = b.FindNet(net)
            paths = self.routes.get(net, [])
            # uzly, kde se větví – musí být koncem segmentu
            junction = set()
            for p in paths:
                junction.add(p[0])
                junction.add(p[-1])
            for fpath in self.fixed.get(net, []):
                self._write_path(fpath, ni, pcbnew.FromMM(PREROUTE_W), junction)
            for p in paths:
                self._write_path(p, ni, pcbnew.FromMM(self.width[net]), junction)
        # body napojení na existující cesty (T-spoje) – rozdělit segmenty
        self._split_at_junctions()

    def _write_path(self, pts, ni, w, junction):
        b = self.board
        seg_start = pts[0]
        for k in range(1, len(pts)):
            a, cur = pts[k - 1], pts[k]
            if a[0] != cur[0]:
                if seg_start != a:
                    self._track(seg_start, a, ni, w)
                v = pcbnew.PCB_VIA(b)
                x, y = self.node_xy(a[1], a[2])
                v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(self.ox + x), pcbnew.FromMM(self.oy + y)))
                v.SetWidth(pcbnew.FromMM(VIA_D))
                v.SetDrill(pcbnew.FromMM(VIA_DRILL))
                v.SetNet(ni)
                b.Add(v)
                seg_start = cur
                continue
            nxt = pts[k + 1] if k + 1 < len(pts) else None
            straight = (nxt is not None and nxt[0] == cur[0] and
                        (nxt[1] - cur[1], nxt[2] - cur[2]) == (cur[1] - a[1], cur[2] - a[2]))
            if not straight or cur in junction:
                self._track(seg_start, cur, ni, w)
                seg_start = cur

    def _track(self, a, b, ni, w):
        if (a[1], a[2]) == (b[1], b[2]):
            return
        t = pcbnew.PCB_TRACK(self.board)
        xa, ya = self.node_xy(a[1], a[2])
        xb, yb = self.node_xy(b[1], b[2])
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(self.ox + xa), pcbnew.FromMM(self.oy + ya)))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(self.ox + xb), pcbnew.FromMM(self.oy + yb)))
        t.SetWidth(w)
        t.SetLayer(LAYERS[a[0]])
        t.SetNet(ni)
        self.board.Add(t)

    def _split_at_junctions(self):
        b = self.board
        tracks = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
        ends = {}
        for t in tracks:
            for p in (t.GetStart(), t.GetEnd()):
                ends.setdefault((t.GetNetCode(), t.GetLayer()), set()).add((p.x, p.y))
        for v in b.GetTracks():
            if v.Type() == pcbnew.PCB_VIA_T:
                for L in LAYERS:
                    ends.setdefault((v.GetNetCode(), L), set()).add((v.GetPosition().x, v.GetPosition().y))
        changed = True
        while changed:
            changed = False
            for t in [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]:
                s, e = t.GetStart(), t.GetEnd()
                for (px, py) in ends.get((t.GetNetCode(), t.GetLayer()), ()):
                    if (px, py) in ((s.x, s.y), (e.x, e.y)):
                        continue
                    # leží bod na segmentu?
                    dx, dy = e.x - s.x, e.y - s.y
                    L2 = dx * dx + dy * dy
                    tt = ((px - s.x) * dx + (py - s.y) * dy) / L2
                    if 0 < tt < 1:
                        qx, qy = s.x + tt * dx, s.y + tt * dy
                        if abs(qx - px) < 2000 and abs(qy - py) < 2000:
                            t2 = pcbnew.PCB_TRACK(b)
                            t2.SetStart(pcbnew.VECTOR2I(px, py))
                            t2.SetEnd(e)
                            t2.SetWidth(t.GetWidth())
                            t2.SetLayer(t.GetLayer())
                            t2.SetNetCode(t.GetNetCode())
                            t.SetEnd(pcbnew.VECTOR2I(px, py))
                            b.Add(t2)
                            changed = True
                            break
                if changed:
                    break


def main():
    # vždy z čerstvě rozmístěné desky (bez starých cest)
    gen_pcb.place()
    board = pcbnew.LoadBoard(gen_pcb.PCB)
    r = Router(board)
    t0 = time.time()
    ok = r.run()
    print("hotovo za %.0f s, vše rozvedeno: %s" % (time.time() - t0, ok))
    r.write()
    pcbnew.SaveBoard(gen_pcb.PCB, board)
    nv = sum(len(v) for v in r.vias.values())
    print("prokovů:", nv)
    if r.unreached:
        print("GND plošky bez cesty (napojí je rozlitá měď):", r.unreached)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
