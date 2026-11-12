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
LAYERS = ('F.Cu', 'In2.Cu', 'B.Cu')    # In2 is the +3V3 plane; signals may borrow it at extra cost
NL = len(LAYERS)
LAYER_COST = (0, 8, 0)                  # extra cost per step on each layer
VIA_COST = 150
NEW_VIA_COST = 120                      # stub: prefer re-using a same-net via within ~0.4 mm
SOFT_COST = 400
HIST_INC = 25
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
        self.rebuild_tracks()

    # ── dynamic (track) obstacle maps ──
    def rebuild_tracks(self):
        self.trk = [np.zeros((self.ny, self.nx), np.int32) for _ in LAYERS]
        self.via_at = {}                # cell index → net id
        self.via_near = np.zeros((self.ny, self.nx), bool)
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
        bias = layer_bias or LAYER_COST
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
        # tree: connect all pads of the net
        remaining = list(u['pads'])
        first = remaining.pop(0)
        tree = set(self.pad_cells[first])
        paths, hits = [], set()
        while remaining:
            targets = {}
            for pi in remaining:
                for c in self.pad_cells[pi]:
                    targets[c] = pi
            path = self.search(nid, tree, targets=set(targets), soft=soft)
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
        pads = ','.join(f"{self.pads[i]['ref']}.{self.pads[i]['num']}" for i in u['pads'][:3])
        return f"{self.net_name[u['nid']]}[{pads}{'…' if len(u['pads']) > 3 else ''}]"

    def build_units(self):
        plane_ids = {self.net_id[n] for n in D.PLANES if n in self.net_id}
        by_net = {}
        for i, p in enumerate(self.pads):
            if p['nid'] > 0:
                by_net.setdefault(p['nid'], []).append(i)
        for nid, pads in by_net.items():
            if nid in plane_ids:
                for i in pads:
                    p = self.pads[i]
                    if p['drill'] > 0:
                        continue                       # through-hole pads reach the planes directly
                    fine = p['ref'] in ('U3', 'U4', 'J1')
                    self.add_unit('stub', nid, [i], 0 if fine else 1)
            elif len(pads) > 1:
                xs = [self.pads[i]['x'] for i in pads]; ys = [self.pads[i]['y'] for i in pads]
                span = (max(xs) - min(xs)) + (max(ys) - min(ys))
                name = strip(self.net_name[nid])
                crit = name.startswith(('USB', 'XIN', 'XOUT', 'QSPI', 'CC')) or name in D.WIDTHS
                # start each tree from the pad closest to the centroid for shorter branches
                cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
                pads = sorted(pads, key=lambda i: abs(self.pads[i]['x'] - cx) + abs(self.pads[i]['y'] - cy))
                self.add_unit('tree', nid, pads, (2 if crit else 3) + span / 1000.0)

    def route_all(self, budget):
        queue = sorted(self.units, key=lambda u: u['prio'])
        t0 = time.time()
        failed = []
        guard = 0
        while queue:
            u = queue.pop(0)
            guard += 1
            if guard % 40 == 0:
                done = sum(1 for v in self.units if v['done'])
                print(f'  … step {guard}: {done}/{len(self.units)} routed, queue {len(queue)}, {time.time() - t0:.0f}s', flush=True)
            if time.time() - t0 > budget:
                failed.append(u)
                continue
            ok, _ = self.route_unit(u)
            if ok:
                continue
            if u.get('rips', 0) + u.get('softs', 0) > 30:
                failed.append(u)
                print('  FAILED', self.name(u), flush=True)
                continue
            u['softs'] = u.get('softs', 0) + 1
            ok, ripped = self.route_unit(u, soft=True)
            if not ok:
                failed.append(u)
                print('  FAILED (soft)', self.name(u), flush=True)
                queue = [v for v in self.units if v['uid'] in ripped] + queue
                continue
            if ripped:
                queue = [v for v in self.units if v['uid'] in ripped] + queue
        failed = [u for u in self.units if not u['done']]
        print(f'routing pass: {len(self.units)} units, {len(failed)} failed, {time.time() - t0:.1f}s', flush=True)
        return failed

    # ── keep the +3V3 plane (In2) in one piece: bridge islands cut off by borrowed signal tracks ──
    def plane_components(self, li, nid):
        ZC = 0.2 + 0.1 + 0.05           # zone clearance + half the minimum pour width + margin
        blocked = (self.pad_own[li] == -1)
        blocked = blocked | ((self.pad_own[li] != 0) & (self.pad_own[li] != nid))
        solid = np.zeros((self.ny, self.nx), bool)
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
        if lname not in LAYERS or net not in self.net_id:
            return 0
        li, nid = LAYERS.index(lname), self.net_id[net]
        added = 0
        for _ in range(12):
            label = self.plane_components(li, nid).ravel()
            comp = {}
            for idx, vn in self.via_at.items():
                if vn == nid:
                    comp.setdefault(int(label[idx]), []).append(idx)
            comp.pop(0, None)
            if len(comp) <= 1:
                break
            main = max(comp, key=lambda c: len(comp[c]))
            islands = sorted((c for c in comp if c != main), key=lambda c: len(comp[c]))
            c = islands[0]
            src = comp[c]
            # nearest via of the main component
            def pos(i):
                return (i % self.nx, i // self.nx)
            best = min(((abs(pos(a)[0] - pos(b)[0]) + abs(pos(a)[1] - pos(b)[1]), a, b) for a in src for b in comp[main]))
            u = self.add_unit('bridge', nid, [], 9)
            sources = [(l, best[1]) for l in range(NL)]
            targets = {(l, b) for b in comp[main] for l in range(NL)}
            path = self.search(nid, sources, targets=targets)
            if path is None:
                print(f'  plane repair: could not bridge a {net} island of {len(src)} via(s)')
                u['done'] = False
                break
            self.commit(u, [path])
            added += 1
        return added

    def snapshot(self):
        return [(u['uid'], list(u['segs']), list(u['vias']), u['done']) for u in self.units]

    def restore(self, snap):
        keep = {uid: (segs, vias, done) for uid, segs, vias, done in snap}
        self.units = [self.registry[uid] for uid in keep]
        for u in self.units:
            u['segs'], u['vias'], u['done'] = keep[u['uid']]
        self.rebuild_tracks()

    def run(self, passes=4, budget=700):
        self.build_units()
        base_units = list(self.units)
        best = None
        for it in range(passes):
            self.units = list(base_units)
            for u in self.units:
                u['segs'], u['vias'], u['done'], u['rips'], u['softs'] = [], [], False, 0, 0
                u.pop('tabu', None)
            self.hist = [np.zeros((self.ny, self.nx), np.int32) for _ in LAYERS]
            self.rebuild_tracks()
            print(f'pass {it + 1}', flush=True)
            failed = self.route_all(budget)
            bridges = 0
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

    def export(self, path):
        tracks, vias = [], {}
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


if __name__ == '__main__':
    r = Router(json.load(open(sys.argv[1])))
    failed = r.run()
    r.export(sys.argv[2])
    sys.exit(1 if failed else 0)
