#!/usr/bin/env python3
"""Grid autorouter for the LA_RP2040 V2 board.

usage: route.py <pads.json> <routes.json>

Four-layer strategy: In1 = GND plane, In2 = +3V3 plane.  Every SMD pad on a
plane net gets a short stub and a via; all other nets are routed on F.Cu /
B.Cu with an A* maze router (0.1 mm grid, 45° moves, rip-up and retry).
The result is checked afterwards by KiCad's own DRC, which is the authority.
"""
import heapq
import json
import math
import os
import pickle
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as D

G = 0.1                                 # grid pitch, mm
W0 = D.DEFAULT_WIDTH
CLR = D.CLEARANCE
MARGIN = 0.03
HALO = CLR + W0 / 2 + MARGIN            # keep-out radius around foreign copper for a W0 track centre
VIA_R = D.VIA_D / 2
EDGE = 0.35                             # copper to board edge
SNAP = G * 0.7072                        # a foreign feature is at most this far from the nearest grid point


def fat_radius(extent, extra=0.05):
    """Grid cells within this radius must be free so copper reaching `extent` from the cell keeps CLR."""
    return max(0.0, extent + CLR - HALO + SNAP + extra)
LAYERS = ('F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu')   # In1/In2 are the GND/+3V3 planes; signals may borrow them at extra cost
NL = len(LAYERS)
LAYER_COST = tuple(int(v) for v in os.environ.get('ROUTE_LAYER_COST', '0,40,8,0').split(','))  #             # extra cost per step on each layer (GND plane: last resort)
POWER_LAYER_COST = (6, 40, 0, 6)            # supply trunks belong on the inner layer, not across the signal fan-out
VIA_COST = 150
NEW_VIA_COST = 120                      # stub: prefer re-using a same-net via within ~0.4 mm
SOFT_COST = 600
HIST_INC = 60
HIST_VICTIM = 12                        # extra cost where a ripped unit used to run
STRAIGHT, DIAG = 10, 14


def strip(net):
    return net[1:] if net.startswith('/') else net


class Router:
    def __init__(self, data):
        self.L, self.W = data['board']['L'], data['board']['W']
        self.nx, self.ny = int(round(self.L / G)) + 1, int(round(self.W / G)) + 1
        self.N = self.nx * self.ny
        self.X, self.Y = np.meshgrid(np.arange(self.nx) * G, np.arange(self.ny) * G)
        self.pads = [p for p in data['pads'] if not p['npth']]
        self.holes = [p for p in data['pads'] if p['npth']]
        names = sorted({p['net'] for p in self.pads if p['net']})
        self.net_id = {n: i + 1 for i, n in enumerate(names)}
        self.net_name = {i: n for n, i in self.net_id.items()}
        self.units = []                 # committed/queued routing units
        self.registry = {}              # uid → unit (all passes)
        self.unit_net = [0]             # uid → net id
        self.hist = [np.zeros((self.ny, self.nx), np.int32) for _ in LAYERS]   # negotiated-congestion history
        self.build_static()

    # ── rasterisation helpers ──
    def window(self, x0, y0, x1, y1, r):
        ix0 = max(0, int(math.floor((x0 - r) / G))); ix1 = min(self.nx - 1, int(math.ceil((x1 + r) / G)))
        iy0 = max(0, int(math.floor((y0 - r) / G))); iy1 = min(self.ny - 1, int(math.ceil((y1 + r) / G)))
        return slice(iy0, iy1 + 1), slice(ix0, ix1 + 1)

    def rect_mask(self, x0, y0, x1, y1, r):
        sy, sx = self.window(x0, y0, x1, y1, r)
        X, Y = self.X[sy, sx], self.Y[sy, sx]
        dx = np.maximum(np.maximum(x0 - X, X - x1), 0)
        dy = np.maximum(np.maximum(y0 - Y, Y - y1), 0)
        return sy, sx, dx * dx + dy * dy < r * r

    def seg_mask(self, xa, ya, xb, yb, r):
        sy, sx = self.window(min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb), r)
        X, Y = self.X[sy, sx], self.Y[sy, sx]
        vx, vy = xb - xa, yb - ya
        ll = vx * vx + vy * vy
        t = np.clip(((X - xa) * vx + (Y - ya) * vy) / ll, 0, 1) if ll > 0 else 0
        dx, dy = X - (xa + t * vx), Y - (ya + t * vy)
        return sy, sx, dx * dx + dy * dy < r * r

    @staticmethod
    def claim(arr, sy, sx, mask, owner):
        cur = arr[sy, sx]
        arr[sy, sx] = np.where(mask, np.where((cur == 0) | (cur == owner), owner, -1), cur)

    def build_static(self):
        self.pad_own = [np.zeros((self.ny, self.nx), np.int32) for _ in LAYERS]
        self.novia = np.zeros((self.ny, self.nx), bool)
        edge = (self.X < EDGE + W0 / 2) | (self.X > self.L - EDGE - W0 / 2) | \
               (self.Y < EDGE + W0 / 2) | (self.Y > self.W - EDGE - W0 / 2)
        r = D.CORNER_R
        for cx, cy in ((r, r), (self.L - r, r), (r, self.W - r), (self.L - r, self.W - r)):
            corner = (np.abs(self.X - (0 if cx == r else self.L)) < r) & (np.abs(self.Y - (0 if cy == r else self.W)) < r)
            edge |= corner & (np.hypot(self.X - cx, self.Y - cy) > r - EDGE - W0 / 2)
        for a in self.pad_own:
            a[edge] = -1
        for h in self.holes:
            sy, sx, m = self.rect_mask(h['x'], h['y'], h['x'], h['y'], h['drill'] / 2 + 0.25 + W0 / 2 + MARGIN)
            for a in self.pad_own:
                a[sy, sx][m] = -1
        self.pad_cells = {}
        for i, p in enumerate(self.pads):
            nid = self.net_id.get(p['net'], -1)
            p['nid'] = nid
            sy, sx, m = self.rect_mask(p['x0'], p['y0'], p['x1'], p['y1'], HALO)
            for li, lname in enumerate(LAYERS):
                if lname in p['layers']:
                    self.claim(self.pad_own[li], sy, sx, m, nid)
            big = (p['x1'] - p['x0']) > 2.5 and (p['y1'] - p['y0']) > 2.5       # exposed pad: via-in-pad is fine
            through = p['drill'] > 0
            if not big and not through:
                sy, sx, m = self.rect_mask(p['x0'], p['y0'], p['x1'], p['y1'], VIA_R + 0.08)
                self.novia[sy, sx] |= m
            if through:                 # keep other vias' drills away from plated slots
                sy, sx, m = self.rect_mask(p['x0'], p['y0'], p['x1'], p['y1'], VIA_R + 0.25)
                self.novia[sy, sx] |= m
            p['big'] = big
        self.build_fixed()
        # cells a track may end on, per pad
        for i, p in enumerate(self.pads):
            if p['nid'] < 0:
                continue
            inset = 0.04
            ix0 = int(math.ceil((p['x0'] + inset) / G - 1e-6)); ix1 = int(math.floor((p['x1'] - inset) / G + 1e-6))
            iy0 = int(math.ceil((p['y0'] + inset) / G - 1e-6)); iy1 = int(math.floor((p['y1'] - inset) / G + 1e-6))
            cells = []
            for li, lname in enumerate(LAYERS):
                if lname not in p['layers']:
                    continue
                for iy in range(iy0, iy1 + 1):
                    for ix in range(ix0, ix1 + 1):
                        if self.pad_own[li][iy, ix] == p['nid']:
                            cells.append((li, iy * self.nx + ix))
            if not cells:
                raise SystemExit(f"pad {p['ref']}.{p['num']} has no routable grid cell")
            self.pad_cells[i] = cells
        self.reserve_escapes()
        self.rebuild_tracks()

    def kicad_net(self, name):
        return name if name in self.net_id else '/' + name

    def build_fixed(self):
        """Pre-routes from design.py (RP2040 supply fan-out) and the rule-based translator fan-out.
        They are stamped as static obstacles: the router connects to them but never moves them."""
        self.fixed_segs, self.fixed_vias, self.preconnected = [], {}, set()
        self.fixed_via_names, self._term = {}, {}
        parent = {}

        def find(t):
            parent.setdefault(t, t)
            while parent[t] != t:
                parent[t] = parent[parent[t]]
                t = parent[t]
            return t

        self.find_group = find
        pad_index = {(p['ref'], p['num']): i for i, p in enumerate(self.pads) if p['layers']}
        via_pos = {}

        def add_via(name, net, x, y):
            idx = int(round(y / G)) * self.nx + int(round(x / G))
            self.fixed_vias[idx] = self.net_id[self.kicad_net(net)]
            self.fixed_via_names[name] = idx
            via_pos[name] = (int(round(x / G)) * G, int(round(y / G)) * G)

        def resolve(tok):
            if isinstance(tok, tuple):
                return tok
            if tok in via_pos:
                return via_pos[tok]
            ref, num = tok.split('.')
            i = pad_index[(ref, num)]
            self.preconnected.add(i)
            return (self.pads[i]['x'], self.pads[i]['y'])

        def add_link(net, layer, a, b, w):
            (xa, ya), (xb, yb) = resolve(a), resolve(b)
            nid, li = self.net_id[self.kicad_net(net)], LAYERS.index(layer)
            pts = [(xa, ya), (xb, yb)]
            if isinstance(a, str) and (a.split('.')[0], a.split('.')[-1]) in pad_index:
                p = self.pads[pad_index[(a.split('.')[0], a.split('.')[-1])]]
                pw, ph = p['x1'] - p['x0'], p['y1'] - p['y0']
                if max(pw, ph) / min(pw, ph) > 1.5:      # leave a fine-pitch pad along its own axis first
                    pts.insert(1, (xb, ya) if pw > ph else (xa, yb))
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                if abs(x1 - x2) + abs(y1 - y2) > 1e-6:
                    self.fixed_segs.append((li, x1, y1, x2, y2, w, nid))
            parent[find(str(a))] = find(str(b))

        for name, (net, x, y) in D.PRE_VIAS.items():
            add_via(name, net, x, y)
        for c in D.COMPONENTS:
            if c['value'] != '74LVC1T45':
                continue
            cx, cy = c['pcb'][0], c['pcb'][1]
            layer = 'B.Cu' if c['pcb'][3] == 'B' else 'F.Cu'
            for pin in ('1', '2', '5', '6'):
                p = self.pads[pad_index[(c['ref'], pin)]]
                vx = cx + (D.TRANSLATOR_VIA_DX if p['x'] > cx else -D.TRANSLATOR_VIA_DX)
                vy = cy if pin in ('2', '5') else cy + (0.8 if p['y'] > cy else -0.8)
                name = f"{c['ref']}.v{pin}"
                add_via(name, strip(p['net']), vx, vy)
                add_link(strip(p['net']), layer, f"{c['ref']}.{pin}", name, 0.2)
        for net, layer, a, b, w in D.PRE_LINKS:
            add_link(net, layer, a, b, w)
        clash = 0
        for name, idx in self.fixed_via_names.items():          # a fixed via must not sit on or beside a pad
            x, y = (idx % self.nx) * G, (idx // self.nx) * G
            for p in self.pads:
                if not p['layers']:
                    continue
                dx = max(p['x0'] - x, 0, x - p['x1']); dy = max(p['y0'] - y, 0, y - p['y1'])
                gap = math.hypot(dx, dy) - VIA_R
                need = 0.05 if p['nid'] == self.fixed_vias[idx] and not p['big'] else CLR + 0.05
                if p['big'] and p['nid'] == self.fixed_vias[idx]:
                    continue
                if gap < need and not (p['drill'] > 0 and p['nid'] == self.fixed_vias[idx]):
                    clash += 1
                    print(f"  fixed via {name} at ({x:.1f}, {y:.1f}) too close to {p['ref']}.{p['num']} [{p['net']}]: {gap:.2f} mm")
        if clash:
            raise SystemExit(f'{clash} fixed-via placement conflict(s)')
        for (li, xa, ya, xb, yb, w, nid) in self.fixed_segs:
            sy, sx, m = self.seg_mask(xa, ya, xb, yb, w / 2 + HALO)
            self.claim(self.pad_own[li], sy, sx, m, nid)
        for idx, nid in self.fixed_vias.items():
            x, y = (idx % self.nx) * G, (idx // self.nx) * G
            sy, sx, m = self.rect_mask(x, y, x, y, VIA_R + HALO)
            for li in range(NL):
                self.claim(self.pad_own[li], sy, sx, m, nid)

    def reserve_escapes(self):
        """Give every IC pin a private corridor straight out of its pad, so that tracks of other nets
        cannot run along a pad row and fence the neighbouring pins in.  Also make the inside of the
        QFN (between pad ring and exposed pad) expensive: it is for the power-pin vias."""
        by_ref = {}
        for p in self.pads:
            by_ref.setdefault(p['ref'], []).append(p)
        self.base_cost = [np.zeros((self.ny, self.nx), np.int32) for _ in LAYERS]
        for ref, pads in by_ref.items():
            smd = [p for p in pads if p['drill'] == 0 and p['layers']]
            if len(smd) < 5:
                continue
            cx = sum(p['x'] for p in smd) / len(smd); cy = sum(p['y'] for p in smd) / len(smd)
            reach = 1.0 if len(smd) > 20 else 0.6
            for p in smd:
                if p['nid'] <= 0 or p['big']:
                    continue
                w, h = p['x1'] - p['x0'], p['y1'] - p['y0']
                if max(w, h) / min(w, h) >= 1.3:
                    horizontal = w > h
                else:                               # squarish pad (chip passives): follow the part's axis
                    horizontal = abs(p['x'] - cx) >= abs(p['y'] - cy)
                if horizontal:
                    x0, x1 = (p['x1'], p['x1'] + reach) if p['x'] > cx else (p['x0'] - reach, p['x0'])
                    y0, y1 = p['y0'], p['y1']
                else:
                    y0, y1 = (p['y1'], p['y1'] + reach) if p['y'] > cy else (p['y0'] - reach, p['y0'])
                    x0, x1 = p['x0'], p['x1']
                sy, sx, m = self.rect_mask(x0, y0, x1, y1, HALO)
                for li, lname in enumerate(LAYERS):
                    if lname in p['layers']:
                        cur = self.pad_own[li][sy, sx]
                        self.pad_own[li][sy, sx] = np.where(m & (cur == 0), p['nid'], cur)
            if len(smd) > 20:
                xs = [p['x'] for p in smd]; ys = [p['y'] for p in smd]
                li = LAYERS.index(smd[0]['layers'][0])
                sy, sx = self.window(min(xs), min(ys), max(xs), max(ys), 0)
                self.base_cost[li][sy, sx] = 30

    # ── dynamic (track) obstacle maps ──
    def rebuild_tracks(self):
        self.trk = [np.zeros((self.ny, self.nx), np.int32) for _ in LAYERS]
        self.via_at = dict(self.fixed_vias)     # cell index → net id
        self.via_near = np.zeros((self.ny, self.nx), bool)
        for idx in self.fixed_vias:
            x, y = (idx % self.nx) * G, (idx // self.nx) * G
            sy, sx, m = self.rect_mask(x, y, x, y, D.VIA_D + 0.25)
            self.via_near[sy, sx] |= m
        for u in self.units:
            if u.get('done'):
                self.stamp(u)

    def stamp(self, u):
        uid = u['uid']
        for (li, xa, ya, xb, yb, w) in u['segs']:
            sy, sx, m = self.seg_mask(xa, ya, xb, yb, w / 2 + HALO)
            self.claim_unit(self.trk[li], sy, sx, m, uid)
        for idx in u['vias']:
            x, y = (idx % self.nx) * G, (idx // self.nx) * G
            sy, sx, m = self.rect_mask(x, y, x, y, VIA_R + HALO)
            for li in range(len(LAYERS)):
                self.claim_unit(self.trk[li], sy, sx, m, uid)
            sy, sx, m = self.rect_mask(x, y, x, y, D.VIA_D + 0.25)
            self.via_near[sy, sx] |= m
            self.via_at[idx] = u['nid']

    def claim_unit(self, arr, sy, sx, mask, uid):
        cur = arr[sy, sx]
        nid = self.unit_net[uid]
        un = np.asarray(self.unit_net + [-1], np.int32)
        same = (cur == 0) | (un[cur] == nid)
        arr[sy, sx] = np.where(mask, np.where(same, np.where(cur == 0, uid, cur), -1), cur)

    def passable(self, nid):
        """Per layer: hard-passable map and soft (rip-up) map for a W0 track of net nid."""
        un = np.asarray(self.unit_net + [-1], np.int32)
        hard, soft = [], []
        for li in range(len(LAYERS)):
            pad_ok = (self.pad_own[li] == 0) | (self.pad_own[li] == nid)
            t = self.trk[li]
            trk_ok = (t == 0) | (un[t] == nid)
            hard.append(pad_ok & trk_ok)
            soft.append(pad_ok & (t != -1))
        return hard, soft

    @staticmethod
    def erode(mask, radius):
        k = int(math.floor(radius / G + 1e-6))
        out = mask.copy()
        for dy in range(-k, k + 1):
            for dx in range(-k, k + 1):
                if (dx or dy) and (dx * dx + dy * dy) * G * G <= radius * radius + 1e-9:
                    sh = np.zeros_like(mask)
                    ys = slice(max(0, dy), mask.shape[0] + min(0, dy)); yd = slice(max(0, -dy), mask.shape[0] + min(0, -dy))
                    xs = slice(max(0, dx), mask.shape[1] + min(0, dx)); xd = slice(max(0, -dx), mask.shape[1] + min(0, -dx))
                    sh[yd, xd] = mask[ys, xs]
                    out &= sh
        return out

    def via_ok_map(self, nid, hard):
        allow = hard[0]
        for h_ in hard[1:]:
            allow = allow & h_
        ok = self.erode(allow, fat_radius(VIA_R, 0.0)) & ~self.novia & ~self.via_near
        for idx, vn in self.via_at.items():
            if vn == nid:
                ok.flat[idx] = True
        return ok

    # ── A* ──
    def search(self, nid, sources, targets=None, goal_via=False, soft=False, layer_bias=None, margin=None, tabu=()):
        """sources: iterable of (layer, idx). targets: set of (layer, idx) or None with goal_via.
        Returns list of (layer, idx) from a source to the goal, or None.
        The search is first confined to a window around the terminals, then retried on the whole board."""
        if margin is None:
            sources = list(sources)
            for m in ((3.0, 8.0) if goal_via else (5.0, 12.0)):
                path = self.search(nid, sources, targets, goal_via, soft, layer_bias, margin=m, tabu=tabu)
                if path is not None:
                    return path
            margin = 1e9
        hard, softm = self.passable(nid)
        via_ok = self.via_ok_map(nid, hard)
        nx = self.nx
        for idx in tabu:                # via sites this stub was already ripped from
            x, y = (idx % nx) * G, (idx // nx) * G
            sy, sx, m = self.rect_mask(x, y, x, y, 0.45)
            via_ok[sy, sx] &= ~m
        if margin < 1e8:
            pts = [i for _, i in sources] + ([i for _, i in targets] if targets else [])
            xs = [i % nx for i in pts]; ys = [i // nx for i in pts]
            k = int(margin / G)
            win = np.zeros((self.ny, self.nx), bool)
            win[max(0, min(ys) - k):max(ys) + k + 1, max(0, min(xs) - k):max(xs) + k + 1] = True
            hard = [h_ & win for h_ in hard]
            softm = [s_ & win for s_ in softm]
        hp = [h.ravel().tobytes() for h in hard]
        sp = [s.ravel().tobytes() for s in softm] if soft else hp
        vo = via_ok.ravel().tobytes()
        hs = [h_.ravel().tolist() for h_ in self.hist]
        own_vias = {i for i, vn in self.via_at.items() if vn == nid}
        tmask = None
        if targets:
            tmask = [bytearray(self.N) for _ in range(NL)]
            txs, tys = [], []
            for (li, idx) in targets:
                tmask[li][idx] = 1
                txs.append(idx % nx); tys.append(idx // nx)
            bx0, bx1, by0, by1 = min(txs), max(txs), min(tys), max(tys)

            def h(idx):
                x, y = idx % nx, idx // nx
                dx = bx0 - x if x < bx0 else (x - bx1 if x > bx1 else 0)
                dy = by0 - y if y < by0 else (y - by1 if y > by1 else 0)
                return STRAIGHT * max(dx, dy) + (DIAG - STRAIGHT) * min(dx, dy)
        else:
            def h(idx):
                return 0
        N = self.N
        INF = 1 << 60
        g = [INF] * ((NL + 1) * N)
        prev = [-1] * ((NL + 1) * N)
        heap = []
        for (li, idx) in sources:
            s = li * N + idx
            if g[s]:
                g[s] = 0
                heapq.heappush(heap, (h(idx), 0, s))
        moves = ((1, STRAIGHT, 0, 0), (-1, STRAIGHT, 0, 0), (nx, STRAIGHT, 0, 0), (-nx, STRAIGHT, 0, 0),
                 (nx + 1, DIAG, nx, 1), (nx - 1, DIAG, nx, -1), (-nx + 1, DIAG, -nx, 1), (-nx - 1, DIAG, -nx, -1))
        bias = layer_bias or (POWER_LAYER_COST if strip(self.net_name[nid]) in D.WIDTHS else LAYER_COST)
        goal = -1
        while heap:
            f, gc, s = heapq.heappop(heap)
            if gc > g[s]:
                continue
            li, idx = divmod(s, N)
            if li == NL:                # virtual "via placed here" node of stub mode
                goal = prev[s]
                break
            if tmask is not None:
                if tmask[li][idx]:
                    goal = s
                    break
            elif goal_via and vo[idx]:
                nc = gc + (0 if idx in own_vias else NEW_VIA_COST)
                t = NL * N + idx
                if nc < g[t]:
                    g[t] = nc
                    prev[t] = s
                    heapq.heappush(heap, (nc, nc, t))
            hpl, spl = hp[li], sp[li]
            for d, c, o1, o2 in moves:
                j = idx + d
                if not spl[j]:
                    continue
                if o1 and not (spl[idx + o1] and spl[idx + o2]):
                    continue
                nc = gc + c + bias[li] + hs[li][j] + (0 if hpl[j] else SOFT_COST)
                t = li * N + j
                if nc < g[t]:
                    g[t] = nc
                    prev[t] = s
                    heapq.heappush(heap, (nc + h(j), nc, t))
            if vo[idx] and not goal_via:
                for ol in range(NL):
                    if ol != li and sp[ol][idx]:
                        nc = gc + VIA_COST + (0 if hp[ol][idx] else SOFT_COST)
                        t = ol * N + idx
                        if nc < g[t]:
                            g[t] = nc
                            prev[t] = s
                            heapq.heappush(heap, (nc + h(idx), nc, t))
        if goal < 0:
            return None
        path = []
        s = goal
        while s >= 0:
            path.append(divmod(s, N))
            s = prev[s]
        path.reverse()
        return path

    # ── units ──
    def conflicts(self, nid, path):
        un = self.unit_net
        hit = set()
        for li, idx in path:
            u = int(self.trk[li].flat[idx])
            if u > 0 and un[u] != nid:
                hit.add(u)
                x, y = (idx % self.nx) * G, (idx // self.nx) * G
                sy, sx, m = self.rect_mask(x, y, x, y, 0.35)
                self.hist[li][sy, sx] += np.where(m, HIST_INC, 0).astype(np.int32)
        return hit

    def width_runs(self, nid, path, wnet):
        """Split a path into (layer, [cells], width) runs, necking down where the wide track does not fit."""
        hard, _ = self.passable(nid)
        cands = [w for w in sorted({wnet, 0.25, W0}, reverse=True) if w <= wnet + 1e-9]
        er = {w: [self.erode(hard[li], fat_radius(w / 2) if w > W0 else 0.0) for li in range(NL)] for w in cands}
        widths = []
        for li, idx in path:
            for w in cands:
                if er[w][li].flat[idx]:
                    widths.append(w)
                    break
            else:
                widths.append(W0)
        # a wide run needs wide cells one step beyond its ends too → smooth with a min filter
        sm = [min(widths[max(0, i - 1):i + 2]) for i in range(len(widths))]
        return sm

    def commit(self, u, paths, end_vias=()):
        nid = u['nid']
        wnet = D.WIDTHS.get(strip(self.net_name[nid]), W0)
        segs, vias = [], set(end_vias)
        nx = self.nx
        for path in paths:
            widths = self.width_runs(nid, path, wnet) if wnet > W0 else [W0] * len(path)
            i = 0
            while i < len(path) - 1:
                li, a = path[i]
                lj, b = path[i + 1]
                if li != lj:
                    vias.add(a)
                    i += 1
                    continue
                d = b - a
                w = min(widths[i], widths[i + 1])
                j = i + 1
                while j < len(path) - 1 and path[j + 1][0] == li and path[j + 1][1] - path[j][1] == d \
                        and min(widths[j], widths[j + 1]) == w:
                    j += 1
                e = path[j][1]
                segs.append((li, (a % nx) * G, (a // nx) * G, (e % nx) * G, (e // nx) * G, w))
                i = j
        u['segs'] = u.get('segs', []) + segs
        u['vias'] = sorted(set(u.get('vias', [])) | vias)
        u['done'] = True
        self.stamp(u)

    def route_unit(self, u, soft=False):
        """Returns (ok, ripped_uids)."""
        nid = u['nid']
        u['segs'], u['vias'], u['done'] = [], [], False
        if u['kind'] == 'stub':
            cells = self.pad_cells[u['pads'][0]]
            p = self.pads[u['pads'][0]]
            path = self.search(nid, cells, goal_via=True, soft=soft, tabu=u.get('tabu', ()))
            if path is None and u.get('tabu'):
                u['tabu'] = set()
                path = self.search(nid, cells, goal_via=True, soft=soft)
            if path is None:
                return False, set()
            hit = self.rip_all(nid, path) if soft else set()
            self.commit(u, [path], end_vias=[path[-1][1]])
            return True, hit
        if u['kind'] == 'link':
            path = None
            for _ in range(4):
                path = self.search(nid, u['src'], targets=set(u['dst']), soft=soft)
                if path is None or not self.crowded_vias(path):
                    break
                path = None
            if path is None:
                return False, set()
            hit = self.rip_all(nid, path) if soft else set()
            self.commit(u, [path])
            return True, hit
        # tree: connect all pads of the net
        remaining = list(u['pads'])
        first = remaining.pop(0)
        tree = set(self.terminal_cells(first))
        paths, hits = [], set()
        while remaining:
            targets = {}
            for pi in remaining:
                for c in self.terminal_cells(pi):
                    targets[c] = pi
            path = None
            for _ in range(4):
                path = self.search(nid, tree, targets=set(targets), soft=soft)
                if path is None:
                    break
                vs = [path[k][1] for k in range(len(path) - 1) if path[k][0] != path[k + 1][0]]
                near = [(a, b) for i_, a in enumerate(vs) for b in vs[i_ + 1:] if a != b and
                        math.hypot((a % self.nx - b % self.nx) * G, (a // self.nx - b // self.nx) * G) < D.VIA_D + 0.3]
                if not near:
                    break
                for a, b in near:               # discourage hopping layers twice in the same spot
                    x, y = (b % self.nx) * G, (b // self.nx) * G
                    sy, sx, m = self.rect_mask(x, y, x, y, 0.6)
                    for li in range(NL):
                        self.hist[li][sy, sx] += np.where(m, 200, 0).astype(np.int32)
                path = None
            if path is None:
                # partial failure: undo what this unit stamped so far
                u['done'] = False
                u['segs'], u['vias'] = [], []
                self.rebuild_tracks()
                return False, hits
            if soft:
                hits |= self.rip_all(nid, path)
            pi = targets[path[-1]]
            remaining.remove(pi)
            tree |= set(path) | set(self.pad_cells[pi])
            for k in range(len(path) - 1):
                if path[k][0] != path[k + 1][0]:
                    for l_ in range(NL):
                        tree.add((l_, path[k][1]))
            self.commit(u, [path])
        return True, hits

    def crowded_vias(self, path):
        """True (and penalise the spot) if a path changes layer twice within less than a via pitch."""
        vs = [path[k][1] for k in range(len(path) - 1) if path[k][0] != path[k + 1][0]]
        near = [(a, b) for i_, a in enumerate(vs) for b in vs[i_ + 1:] if a != b and
                math.hypot((a % self.nx - b % self.nx) * G, (a // self.nx - b // self.nx) * G) < D.VIA_D + 0.3]
        for a, b in near:
            x, y = (b % self.nx) * G, (b // self.nx) * G
            sy, sx, m = self.rect_mask(x, y, x, y, 0.6)
            for li in range(NL):
                self.hist[li][sy, sx] += np.where(m, 200, 0).astype(np.int32)
        return bool(near)

    def terminal_cells(self, pi):
        """Cells that count as 'this pad': the pad itself plus everything pre-routed to it
        (other pads of its group and the group's fixed vias on every layer)."""
        if pi not in self._term:
            p = self.pads[pi]
            g = self.find_group(f"{p['ref']}.{p['num']}")
            cells = list(self.pad_cells[pi])
            for j, q in enumerate(self.pads):
                if j != pi and j in self.pad_cells and q['nid'] == p['nid'] and \
                        self.find_group(f"{q['ref']}.{q['num']}") == g:
                    cells += self.pad_cells[j]
            for name, idx in self.fixed_via_names.items():
                if self.fixed_vias[idx] == p['nid'] and self.find_group(name) == g:
                    cells += [(l, idx) for l in range(NL)]
            self._term[pi] = cells
        return self._term[pi]

    def rip_all(self, nid, path):
        """Rip every foreign unit whose copper halo covers the path (repeat: same-net units share claims)."""
        ripped = set()
        while True:
            hit = self.conflicts(nid, path)
            if not hit:
                return ripped
            ripped |= hit
            self.rip(hit)

    def rip(self, uids):
        for u in self.units:
            if u['uid'] in uids:
                for (li, xa, ya, xb, yb, w) in u['segs']:
                    sy, sx, m = self.seg_mask(xa, ya, xb, yb, 0.25)
                    self.hist[li][sy, sx] += np.where(m, HIST_VICTIM, 0).astype(np.int32)
                for idx in u['vias']:
                    x, y = (idx % self.nx) * G, (idx // self.nx) * G
                    sy, sx, m = self.rect_mask(x, y, x, y, 0.45)
                    for li in range(NL):
                        self.hist[li][sy, sx] += np.where(m, HIST_VICTIM, 0).astype(np.int32)
                if u['kind'] == 'stub':
                    u.setdefault('tabu', set()).update(u['vias'])
                u['done'] = False
                u['segs'], u['vias'] = [], []
                u['rips'] = u.get('rips', 0) + 1
        self.rebuild_tracks()

    def add_unit(self, kind, nid, pads, prio):
        uid = len(self.unit_net)
        self.unit_net.append(nid)
        u = dict(uid=uid, kind=kind, nid=nid, pads=pads, prio=prio, done=False, segs=[], vias=[])
        self.units.append(u)
        self.registry[uid] = u
        return u

    def name(self, u):
        if u['kind'] == 'link':
            return f"{self.net_name[u['nid']]}[plane link]"
        pads = ','.join(f"{self.pads[i]['ref']}.{self.pads[i]['num']}" for i in u['pads'][:3])
        return f"{self.net_name[u['nid']]}[{pads}{'…' if len(u['pads']) > 3 else ''}]"

    def build_units(self):
        for i in self.pad_cells:
            self.terminal_cells(i)
        plane_ids = {self.net_id[n] for n in D.PLANES if n in self.net_id}
        by_net = {}
        for i, p in enumerate(self.pads):
            if p['nid'] > 0:
                by_net.setdefault(p['nid'], []).append(i)
        for nid, pads in by_net.items():
            if nid in plane_ids:
                for i in pads:
                    p = self.pads[i]
                    if p['drill'] > 0 or i in self.preconnected:
                        continue                       # through-hole and pre-routed pads already reach the planes
                    fine = p['ref'] in ('U3', 'U4', 'J1')
                    self.add_unit('stub', nid, [i], 0 if fine else 1)      # after the signals: stubs can go anywhere
            elif len(pads) > 1:
                xs = [self.pads[i]['x'] for i in pads]; ys = [self.pads[i]['y'] for i in pads]
                span = (max(xs) - min(xs)) + (max(ys) - min(ys))
                name = strip(self.net_name[nid])
                crit = name.startswith(('USB', 'XIN', 'XOUT', 'QSPI', 'CC'))
                power = name in D.WIDTHS
                # one independent two-pad unit per minimum-spanning-tree edge: a rip-up only costs that edge
                def dist(a, b):
                    pa, pb = self.pads[a], self.pads[b]
                    return abs(pa['x'] - pb['x']) + abs(pa['y'] - pb['y']) + (0 if set(pa['layers']) & set(pb['layers']) else 1.5)
                def group(i):
                    return self.find_group(f"{self.pads[i]['ref']}.{self.pads[i]['num']}")
                inside, rest = [pads[0]], list(pads[1:])
                while rest:
                    d, a, b = min(((-1 if group(a) == group(b) else dist(a, b)), a, b) for a in inside for b in rest)
                    rest.remove(b)
                    inside.append(b)
                    if d >= 0:              # pads joined by a pre-route need no unit
                        # short critical links, then long hauls before short ones, supply trunks after the signals
                        if os.environ.get('ROUTE_ORDER') == 'short':
                            prio = (2 if crit or power else 3) + d / 1000.0
                        elif os.environ.get('ROUTE_ORDER') == 'short2':
                            prio = (2 if crit else (4 if power else 3)) + d / 1000.0
                        else:
                            prio = 0.5 if crit else (4 + d / 1000.0 if power else 3 - d / 1000.0)
                        self.add_unit('tree', nid, [a, b], prio)

    def try_place(self, u, depth, deadline):
        """Route u; if it is blocked, rip the units in its way and re-place those too (bounded
        backtracking).  Either everything involved ends up routed, or the board state is restored."""
        ok, _ = self.route_unit(u)
        if ok:
            return True
        if depth == 0 or time.time() > deadline:
            return False
        for attempt in range(5 if depth > 1 else 3):
            snap = self.snapshot()
            ok, ripped = self.route_unit(u, soft=True)
            if ok:
                victims = sorted((v for v in self.units if v['uid'] in ripped), key=lambda v: v['prio'])
                if all(self.try_place(v, depth - 1, deadline) for v in victims):
                    return True
            self.restore(snap)          # the congestion history keeps what was learnt, so the next try differs
            if not ok or time.time() > deadline:
                break
        return False

    def route_all(self, budget):
        t0 = time.time()
        queue = sorted(self.units, key=lambda u: u['prio'])
        blocked = []
        for u in queue:                 # pass A: no rip-up at all
            ok, _ = self.route_unit(u)
            if not ok:
                blocked.append(u)
        print(f'  first pass: {len(blocked)} of {len(queue)} blocked, {time.time() - t0:.0f}s', flush=True)
        if os.environ.get('ROUTE_HARD_ONLY'):
            return blocked
        for rnd in range(3):            # pass B: repair with bounded backtracking
            still = []
            for k, u in enumerate(blocked):
                if self.try_place(u, 2 + rnd, t0 + budget):
                    continue
                still.append(u)
                print(f'  round {rnd + 1}: still blocked {self.name(u)} ({time.time() - t0:.0f}s)', flush=True)
            if len(still) == len(blocked) or not still:
                blocked = still
                break
            blocked = still
        failed = [u for u in self.units if not u['done']]
        print(f'routing pass: {len(self.units)} units, {len(failed)} failed, {time.time() - t0:.1f}s', flush=True)
        return failed

    # ── keep the +3V3 plane (In2) in one piece: bridge islands cut off by borrowed signal tracks ──
    def plane_components(self, li, nid):
        ZC = 0.15 + 0.075 + 0.02        # zone clearance + half the minimum pour width + margin (see gen_pcb.zone)
        blocked = (self.pad_own[li] == -1)
        blocked = blocked | ((self.pad_own[li] != 0) & (self.pad_own[li] != nid))
        solid = np.zeros((self.ny, self.nx), bool)
        for (l2, xa, ya, xb, yb, w, n2) in self.fixed_segs:
            if l2 == li and n2 != nid:
                sy, sx, m = self.seg_mask(xa, ya, xb, yb, w / 2 + ZC)
                solid[sy, sx] |= m
        for idx, n2 in self.fixed_vias.items():
            if n2 != nid:
                x, y = (idx % self.nx) * G, (idx // self.nx) * G
                sy, sx, m = self.rect_mask(x, y, x, y, VIA_R + ZC)
                solid[sy, sx] |= m
        for u in self.units:
            if not u['done'] or u['nid'] == nid:
                continue
            for (l2, xa, ya, xb, yb, w) in u['segs']:
                if l2 == li:
                    sy, sx, m = self.seg_mask(xa, ya, xb, yb, w / 2 + ZC)
                    solid[sy, sx] |= m
            for idx in u['vias']:
                x, y = (idx % self.nx) * G, (idx // self.nx) * G
                sy, sx, m = self.rect_mask(x, y, x, y, VIA_R + ZC)
                solid[sy, sx] |= m
        free = ~(blocked | solid)
        label = np.zeros((self.ny, self.nx), np.int32)
        cur = 0
        fl = free.ravel(); lab = label.ravel(); nx = self.nx
        for start in np.flatnonzero(fl):
            if lab[start]:
                continue
            cur += 1
            lab[start] = cur
            stack = [int(start)]
            while stack:
                c = stack.pop()
                for d in (1, -1, nx, -nx):
                    n = c + d
                    if 0 <= n < self.N and fl[n] and not lab[n]:
                        lab[n] = cur
                        stack.append(n)
        return label

    def repair_plane(self, net, lname):
        """Tie plane-net vias that the pour cannot reach (cut off by borrowed tracks) back to the main area."""
        if lname not in LAYERS or net not in self.net_id:
            return 0
        li, nid = LAYERS.index(lname), self.net_id[net]
        added, gave_up = 0, set()
        deadline = time.time() + 1500
        for _ in range(int(os.environ.get('ROUTE_BRIDGES', 0))):
            label = self.plane_components(li, nid).ravel()
            comp = {}
            for idx, vn in self.via_at.items():
                if vn == nid:
                    comp.setdefault(int(label[idx]), []).append(idx)
            comp.pop(0, None)
            if len(comp) <= 1:
                break
            main = max(comp, key=lambda c: len(comp[c]))
            islands = [c for c in comp if c != main and min(comp[c]) not in gave_up]
            if not islands:
                break
            c = min(islands, key=lambda c: len(comp[c]))
            u = self.add_unit('link', nid, [], 9)
            u['src'] = [(l, i) for i in comp[c] for l in range(NL)]
            u['dst'] = [(l, i) for i in comp[main] for l in range(NL)]
            if self.try_place(u, 2, deadline):
                added += 1
            else:
                gave_up.add(min(comp[c]))
                print(f'  plane repair: could not bridge a {net} island of {len(comp[c])} via(s) at '
                      f'({(comp[c][0] % self.nx) * G:.1f}, {(comp[c][0] // self.nx) * G:.1f})', flush=True)
        return added

    def snapshot(self):
        return [(u['uid'], list(u['segs']), list(u['vias']), u['done']) for u in self.units]

    def restore(self, snap):
        keep = {uid: (segs, vias, done) for uid, segs, vias, done in snap}
        self.units = [self.registry[uid] for uid in keep]
        for u in self.units:
            segs, vias, done = keep[u['uid']]
            u['segs'], u['vias'], u['done'] = list(segs), list(vias), done
        self.rebuild_tracks()

    def run(self, passes=int(os.environ.get('ROUTE_PASSES', 4)), budget=int(os.environ.get('ROUTE_BUDGET', 700))):
        self.build_units()
        base_units = list(self.units)
        best = None
        for it in range(passes):
            self.units = list(base_units)
            for u in self.units:
                u['segs'], u['vias'], u['done'], u['rips'], u['softs'] = [], [], False, 0, 0
                u.pop('tabu', None)
            self.hist = [b.copy() for b in self.base_cost]
            self.rebuild_tracks()
            print(f'pass {it + 1}', flush=True)
            failed = self.route_all(budget)
            bridges = 0
            if os.environ.get('ROUTE_BRIDGES'):
                for net, lname in D.PLANES.items():
                    bridges += self.repair_plane(net, lname)
            print(f'  {len(failed)} unrouted, {bridges} plane bridge(s)', flush=True)
            if best is None or len(failed) < best[0]:
                best = (len(failed), self.snapshot(), [self.name(u) for u in failed])
            if not failed:
                break
            for u in failed:                # route the troublemakers first next time
                u['prio'] = 1.5 + u['prio'] / 100.0
        self.restore(best[1])
        print(f'best pass: {best[0]} unrouted {best[2]}')
        return best[2]

    def save(self, path):
        fg, self.find_group = self.find_group, None        # closures do not pickle; groups are cached in _term
        for i in self.pad_cells:
            pass
        with open(path, 'wb') as f:
            pickle.dump(self, f)
        self.find_group = fg

    def add_links(self, pairs, budget=900):
        """Connect point pairs that KiCad reported as unconnected (plane islands), with rip-up repair."""
        deadline = time.time() + budget
        ok = 0
        for pr in pairs:
            nid = self.net_id[pr['net']]
            ends = []
            for e in (pr['a'], pr['b']):
                idx = int(round(e['y'] / G)) * self.nx + int(round(e['x'] / G))
                layers = range(NL) if e['layer'] == '*' else [LAYERS.index(e['layer'])]
                ends.append([(l, idx) for l in layers])
            u = self.add_unit('link', nid, [], 9)
            u['src'], u['dst'] = ends
            if self.try_place(u, 3, deadline):
                ok += 1
            else:
                print('  link failed:', pr['a'], pr['b'], flush=True)
        print(f'links: {ok} of {len(pairs)} placed', flush=True)
        spec = os.environ.get('LINK_PLANE')            # e.g. GND:8 → also tie up to 8 stranded GND via groups
        if spec:
            net, n = spec.split(':')
            os.environ['ROUTE_BRIDGES'] = n
            print(f'plane links for {net}:', self.repair_plane(net, D.PLANES[net]), flush=True)

    def export(self, path):
        tracks, vias = [], {}
        for (li, xa, ya, xb, yb, w, nid) in self.fixed_segs:
            tracks.append(dict(net=self.net_name[nid], layer=LAYERS[li], x1=round(xa, 3), y1=round(ya, 3),
                               x2=round(xb, 3), y2=round(yb, 3), w=w))
        for idx, nid in self.fixed_vias.items():
            vias[idx] = dict(net=self.net_name[nid], x=round((idx % self.nx) * G, 3), y=round((idx // self.nx) * G, 3))
        for u in self.units:
            net = self.net_name[u['nid']]
            for (li, xa, ya, xb, yb, w) in u['segs']:
                tracks.append(dict(net=net, layer=LAYERS[li], x1=round(xa, 3), y1=round(ya, 3),
                                   x2=round(xb, 3), y2=round(yb, 3), w=w))
            for idx in u['vias']:
                vias[idx] = dict(net=net, x=round((idx % self.nx) * G, 3), y=round((idx // self.nx) * G, 3))
        length = sum(math.hypot(t['x2'] - t['x1'], t['y2'] - t['y1']) for t in tracks)
        json.dump(dict(tracks=tracks, vias=list(vias.values())), open(path, 'w'))
        print(f'exported {len(tracks)} segments ({length:.0f} mm), {len(vias)} vias')


def bridge(pads_json, routes_json, pairs_json, out_json):
    """Add links between points KiCad reports as unconnected (plane islands), keeping all existing copper."""
    r = Router(json.load(open(pads_json)))
    old = json.load(open(routes_json))
    for t in old['tracks']:
        nid, li = r.net_id[t['net']], LAYERS.index(t['layer'])
        sy, sx, m = r.seg_mask(t['x1'], t['y1'], t['x2'], t['y2'], t['w'] / 2 + HALO)
        r.claim(r.pad_own[li], sy, sx, m, nid)
        r.fixed_segs.append((li, t['x1'], t['y1'], t['x2'], t['y2'], t['w'], nid))
    n_fixed = len(r.fixed_segs)
    for v in old['vias']:
        nid = r.net_id[v['net']]
        idx = int(round(v['y'] / G)) * r.nx + int(round(v['x'] / G))
        r.fixed_vias[idx] = nid
        sy, sx, m = r.rect_mask(v['x'], v['y'], v['x'], v['y'], VIA_R + HALO)
        for li in range(NL):
            r.claim(r.pad_own[li], sy, sx, m, nid)
    r.hist = [b.copy() for b in r.base_cost]
    r.rebuild_tracks()
    added = 0
    for pr in json.load(open(pairs_json)):
        nid = r.net_id[pr['net']]
        ends = []
        for e in (pr['a'], pr['b']):
            idx = int(round(e['y'] / G)) * r.nx + int(round(e['x'] / G))
            layers = range(NL) if e['layer'] == '*' else [LAYERS.index(e['layer'])]
            hard, _ = r.passable(nid)
            ends.append([(l, idx) for l in layers if hard[l].flat[idx]])
        if not ends[0] or not ends[1]:
            print('  bridge: endpoint not routable', pr)
            continue
        u = r.add_unit('bridge', nid, [], 9)
        path = r.search(nid, ends[0], targets=set(ends[1]))
        if path is not None:
            r.commit(u, [path])
            added += 1
            continue
        for k in (0, 1):                # no direct path: tie each end (and the vias next to it) to the rest of the net
            ex, ey = ends[k][0][1] % r.nx, ends[k][0][1] // r.nx
            far = {(l, i) for i, n in r.via_at.items() if n == nid and
                   math.hypot(i % r.nx - ex, i // r.nx - ey) * G > 3.0 for l in range(NL)}
            near = [(l, i) for i, n in r.via_at.items() if n == nid and
                    math.hypot(i % r.nx - ex, i // r.nx - ey) * G <= 1.5 for l in range(NL)]
            path = r.search(nid, list(ends[k]) + near, targets=far) if far else None
            if path is None:
                print('  bridge: no path from', pr['a' if k == 0 else 'b'])
                continue
            u = r.add_unit('bridge', nid, [], 9)
            r.commit(u, [path])
            added += 1
    # the GND plane (In1) may have been cut by borrowed tracks: tie stranded GND vias back to the main area
    for net, lname in D.PLANES.items():
        if os.environ.get('BRIDGE_PLANES') and lname in LAYERS and net in r.net_id:
            li, nid = LAYERS.index(lname), r.net_id[net]
            for _ in range(25):
                label = r.plane_components(li, nid).ravel()
                comp = {}
                for idx, vn in r.via_at.items():
                    if vn == nid:
                        comp.setdefault(int(label[idx]), []).append(idx)
                comp.pop(0, None)
                if len(comp) <= 1:
                    break
                main = max(comp, key=lambda c: len(comp[c]))
                c = min((c for c in comp if c != main), key=lambda c: len(comp[c]))
                u = r.add_unit('bridge', nid, [], 9)
                path = r.search(nid, [(l, i) for i in comp[c] for l in range(NL)],
                                targets={(l, i) for i in comp[main] for l in range(NL)})
                if path is None:
                    print(f'  plane bridge: no path for a {net} island of {len(comp[c])} via(s)')
                    break
                r.commit(u, [path])
                added += 1
    tracks, vias = list(old['tracks']), {(v['x'], v['y']): v for v in old['vias']}
    for u in r.units:
        net = r.net_name[u['nid']]
        for (li, xa, ya, xb, yb, w) in u['segs']:
            tracks.append(dict(net=net, layer=LAYERS[li], x1=round(xa, 3), y1=round(ya, 3), x2=round(xb, 3), y2=round(yb, 3), w=w))
        for idx in u['vias']:
            x, y = round((idx % r.nx) * G, 3), round((idx // r.nx) * G, 3)
            vias[(x, y)] = dict(net=net, x=x, y=y)
    json.dump(dict(tracks=tracks, vias=list(vias.values())), open(out_json, 'w'))
    print(f'bridge: {added} link(s) added')


if __name__ == '__main__':
    if sys.argv[1] == '--bridge':
        bridge(*sys.argv[2:6])
        sys.exit(0)
    if sys.argv[1] == '--links':          # route.py --links state.pkl pairs.json out.json
        with open(sys.argv[2], 'rb') as f:
            r = pickle.load(f)
        r.add_links(json.load(open(sys.argv[3])))
        r.export(sys.argv[4])
        r.save(sys.argv[2])
        sys.exit(0)
    r = Router(json.load(open(sys.argv[1])))
    failed = r.run()
    r.export(sys.argv[2])
    if os.environ.get('ROUTE_SAVE'):
        r.save(os.environ['ROUTE_SAVE'])
    sys.exit(1 if failed else 0)
