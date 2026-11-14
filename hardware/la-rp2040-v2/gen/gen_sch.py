#!/usr/bin/env python3
"""Generate the KiCad 9 schematic from design.py (parts, nets) and sch_layout.py (drawing positions).

usage: gen_sch.py <kicad-symbol-dir> <output.kicad_sch>

Connections are drawn as wires: a small maze router on the 1.27 mm schematic grid joins the pins of every
net (orthogonal wires, crossings without a junction, junction dots on tees).  Supply rails end in power
symbols, the RP2040 GPIO lines run through a channel of parallel wires to the translators, and only the
connector side is joined by net labels.  Every wired net carries one label so that net names stay the same
as on the PCB.  The result is verified against design.py with `kicad-cli sch export netlist`.
"""
import heapq
import math
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as D
import sch_layout as L
from sexpr import Q, parse, dump, find, first

NS = uuid.UUID('6f1d3c1e-6f0a-4b61-9d57-2a5c0f8e2040')
U = 1.27
PROJECT_LIB = D.LIB
POWER_SYMS = {'GND': 'power:GND', '+3V3': 'power:+3V3', '+5V': 'power:+5V', '+1V1': 'power:+1V1',
              'VIO': f'{PROJECT_LIB}:VIO'}
VEC = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}       # direction in degrees → grid step (y grows down)
CHAR = 0.9                                                       # text width per character / text size
BEND, CROSS = 3, 6


def uid(*key):
    return Q(str(uuid.uuid5(NS, '/'.join(str(k) for k in key))))


ROOT = uid('root')[:]
_libs = {}


def project_symbols(symdir):
    """Project-local symbols: a VIO power symbol derived from power:+3V3."""
    src = dump(load_symbol(symdir, 'power:+3V3')).replace('+3V3', 'VIO').replace('power:VIO', 'VIO')
    return {'VIO': parse(src)}


def load_symbol(symdir, lib_id):
    lib, name = lib_id.split(':')
    if lib == PROJECT_LIB:
        return ['symbol', Q(lib_id)] + project_symbols(symdir)[name][2:]
    if lib not in _libs:
        tree = parse(open(os.path.join(symdir, lib + '.kicad_sym'), encoding='utf-8').read())
        _libs[lib] = {s[1]: s for s in find(tree, 'symbol')}
    sym = _libs[lib][name]
    ext = first(sym, 'extends')
    if ext:
        parent = _libs[lib][ext[1]]
        body = []
        for item in parent[2:]:
            if isinstance(item, list) and item[0] == 'property':
                continue
            if isinstance(item, list) and item[0] == 'symbol':
                item = [item[0], Q(item[1].replace(ext[1], name, 1))] + item[2:]
            body.append(item)
        props = [x for x in sym[2:] if isinstance(x, list) and x[0] == 'property']
        head = [x for x in body if not (isinstance(x, list) and x[0] == 'symbol')]
        units = [x for x in body if isinstance(x, list) and x[0] == 'symbol']
        sym = ['symbol', Q(name)] + head + props + units
    return ['symbol', Q(lib_id)] + sym[2:]


def sym_pins(sym):
    pins = []
    for unit in find(sym, 'symbol'):
        for p in find(unit, 'pin'):
            at = first(p, 'at')
            pins.append(dict(num=str(first(p, 'number')[1]), x=float(at[1]), y=float(at[2]),
                             ang=float(at[3]) if len(at) > 3 else 0.0, len=float(first(p, 'length')[1])))
    return pins


def sym_points(sym):
    """Corner points of the symbol graphics (library coordinates)."""
    pts = []
    for unit in find(sym, 'symbol'):
        for r in find(unit, 'rectangle'):
            for k in ('start', 'end'):
                pts.append((float(first(r, k)[1]), float(first(r, k)[2])))
        for pl in find(unit, 'polyline'):
            pts += [(float(xy[1]), float(xy[2])) for xy in find(first(pl, 'pts'), 'xy')]
        for c in find(unit, 'circle'):
            cx, cy, rad = float(first(c, 'center')[1]), float(first(c, 'center')[2]), float(first(c, 'radius')[1])
            pts += [(cx - rad, cy - rad), (cx + rad, cy + rad)]
        for a in find(unit, 'arc'):
            for k in ('start', 'mid', 'end'):
                pts.append((float(first(a, k)[1]), float(first(a, k)[2])))
    return pts


def rot(x, y, deg):
    r = math.radians(deg)
    return x * math.cos(r) - y * math.sin(r), x * math.sin(r) + y * math.cos(r)


def r2(v):
    return round(v + 0.0, 4)


def font(size=1.27, justify=None, hide=False):
    e = ['effects', ['font', ['size', size, size]]]
    if justify:
        e.append(['justify'] + justify)
    if hide:
        e.append(['hide', 'yes'])
    return e


def prop(name, value, x, y, ang=0, justify=None, hide=False, size=1.27):
    return ['property', Q(name), Q(value), ['at', r2(x), r2(y), ang], font(size, justify, hide)]


class Cluster:
    """A set of pins drawn as one connected piece of wire."""

    def __init__(self, key, net):
        self.key, self.net = key, net
        self.pins = []              # pin-node dicts
        self.nodes = set()          # grid nodes on the wire tree
        self.edges = set()          # ((x, y), (x2, y2)) with the first point smaller
        self.term = []              # extra terminals: (node, kind, direction)
        self.want_label = False


class Sheet:
    def __init__(self, symdir):
        self.symdir = symdir
        self.lib = {}
        self.items = []
        self.pwr = 0
        self.blocked = set()        # nodes covered by symbol bodies, pin shafts, texts
        self.pinnode = {}           # node → cluster key that owns the pin end there
        self.arrive = {}            # node → grid step a wire must make when it enters an IC pin end
        self.reserved = {}          # node → cluster key (escape stub in front of an IC pin)
        self.h, self.v = {}, {}     # unit edges → cluster key
        self.at = {}                # node → {cluster key: set of grid steps leaving the node}
        self.clusters = {}
        self.nodes_of = {}          # net → [pin node dict]
        self.npins = {}             # node → number of pin ends there
        self.warn = []

    # ───────────────────────────── primitives ─────────────────────────────
    def use(self, lib_id):
        if lib_id not in self.lib:
            self.lib[lib_id] = load_symbol(self.symdir, lib_id)
        return self.lib[lib_id]

    def wire(self, a, b, key):
        self.items.append(['wire', ['pts', ['xy', r2(a[0] * U), r2(a[1] * U)], ['xy', r2(b[0] * U), r2(b[1] * U)]],
                           ['stroke', ['width', 0], ['type', 'default']], ['uuid', uid('w', *key)]])

    def block_box(self, x0, y0, x1, y1, margin=0.0, keep=()):
        """Block the grid nodes inside a box given in mm."""
        for gx in range(math.ceil((min(x0, x1) - margin) / U - 1e-6), math.floor((max(x0, x1) + margin) / U + 1e-6) + 1):
            for gy in range(math.ceil((min(y0, y1) - margin) / U - 1e-6),
                            math.floor((max(y0, y1) + margin) / U + 1e-6) + 1):
                if (gx, gy) not in keep:
                    self.blocked.add((gx, gy))

    def block_text(self, cx, cy, text, size, ang=0):
        w, h = CHAR * size * len(text), size
        if ang in (90, 270):
            w, h = h, w
        self.block_box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, 0.15)

    def label(self, net, node, out_deg, key, size=1.27):
        just = ['left', 'bottom'] if out_deg in (0, 90) else ['right', 'bottom']
        x, y = node[0] * U, node[1] * U
        self.items.append(['label', Q(net), ['at', r2(x), r2(y), out_deg], font(size, just), ['uuid', uid('l', *key)]])
        w = CHAR * size * len(net) + 0.4
        dx, dy = VEC[out_deg]
        if dx:
            self.block_box(x, y - size - 0.5, x + dx * w, y - 0.4)
        else:
            self.block_box(x - size - 0.5, y, x - 0.4, y + dy * w)

    def power(self, net, node, point_deg, key):
        """Power symbol with its pin on `node`, graphic pointing in `point_deg`."""
        lib_id = POWER_SYMS[net]
        self.use(lib_id)
        self.pwr += 1
        ref = f'#PWR{self.pwr:03d}'
        base = 270 if net == 'GND' else 90          # direction the graphic points at angle 0
        ang = int((point_deg - base) % 360)
        x, y = node[0] * U, node[1] * U
        dx, dy = VEC[point_deg]
        if dx:
            vx, vy = x + dx * (3.0 + CHAR * 0.5 * len(net)), y
        else:
            vx, vy = x, y + dy * (3.7 if net != 'GND' else 4.1)
        self.items.append(['symbol', ['lib_id', Q(lib_id)], ['at', r2(x), r2(y), ang], ['unit', 1],
                           ['exclude_from_sim', 'no'], ['in_bom', 'yes'], ['on_board', 'yes'], ['dnp', 'no'],
                           ['uuid', uid('p', *key)],
                           prop('Reference', ref, x, y, hide=True),
                           prop('Value', net, vx, vy, 0, size=1.0),
                           prop('Footprint', '', x, y, hide=True),
                           prop('Datasheet', '', x, y, hide=True),
                           ['pin', Q('1'), ['uuid', uid('pp', *key)]],
                           ['instances', ['project', Q(D.PROJECT),
                                          ['path', Q('/' + ROOT), ['reference', Q(ref)], ['unit', 1]]]]])
        px, py = -dy, dx
        self.block_box(x + dx * 0.7 + px * 1.3, y + dy * 0.7 + py * 1.3, x + dx * 2.6 - px * 1.3, y + dy * 2.6 - py * 1.3)
        self.block_text(vx, vy, net, 1.0)

    def flag(self, net, node):
        self.use('power:PWR_FLAG')
        self.pwr += 1
        ref = f'#FLG{self.pwr:03d}'
        x, y = node[0] * U, node[1] * U
        self.items.append(['symbol', ['lib_id', Q('power:PWR_FLAG')], ['at', r2(x), r2(y), 0], ['unit', 1],
                           ['exclude_from_sim', 'no'], ['in_bom', 'yes'], ['on_board', 'yes'], ['dnp', 'no'],
                           ['uuid', uid('f', net)],
                           prop('Reference', ref, x, y, hide=True),
                           prop('Value', 'PWR_FLAG', x, y - 5.0, size=1.0),
                           prop('Footprint', '', x, y, hide=True), prop('Datasheet', '', x, y, hide=True),
                           ['pin', Q('1'), ['uuid', uid('fp', net)]],
                           ['instances', ['project', Q(D.PROJECT),
                                          ['path', Q('/' + ROOT), ['reference', Q(ref)], ['unit', 1]]]]])
        end = (node[0], node[1] + 2)
        self.wire(node, end, ('flag', net))
        if net in POWER_SYMS:
            self.power(net, end, 270 if net == 'GND' else 270, ('flag', net))
        else:
            self.label(net, end, 270, ('flag', net))

    def text(self, x, y, size, s):
        self.items.append(['text', Q(s), ['exclude_from_sim', 'no'], ['at', r2(x * U), r2(y * U), 0],
                           font(size, ['left', 'bottom']), ['uuid', uid('t', s)]])

    # ───────────────────────────── symbols ─────────────────────────────
    def place(self, c):
        sym = self.use(c['sym'])
        gx, gy, R, mirror = L.POS[c['ref']]
        X, Y = gx * U, gy * U
        pins = sym_pins(sym)

        def tf(px, py):
            if mirror:
                px = -px
            rx, ry = rot(px, py, R)
            return X + rx, Y - ry

        groups = {}
        shafts = []
        for p in pins:
            ang = (180 - p['ang']) % 360 if mirror else p['ang']
            ex, ey = tf(p['x'], p['y'])
            rx, ry = tf(p['x'] + p['len'] * math.cos(math.radians(p['ang'])),
                        p['y'] + p['len'] * math.sin(math.radians(p['ang'])))
            out = int(round(ang + 180 + R)) % 360
            node = (round(ex / U), round(ey / U))
            if abs(node[0] * U - ex) > 1e-3 or abs(node[1] * U - ey) > 1e-3:
                raise SystemExit(f"{c['ref']}.{p['num']} is off the 1.27 mm grid")
            groups.setdefault((node, out), []).append(p['num'])
            shafts.append((node, (rx, ry)))
        pts = [tf(*q) for q in sym_points(sym)] or [(X - 2.54, Y - 2.54), (X + 2.54, Y + 2.54)]
        bx0, bx1 = min(q[0] for q in pts), max(q[0] for q in pts)
        by0, by1 = min(q[1] for q in pts), max(q[1] for q in pts)
        ends = {node for node, _ in groups}
        two_pin = len(pins) == 2 and c['ref'][0] in 'RCFDL'
        if two_pin:                                    # graphics (LED arrows) must not reach past the pin ends
            ex = sorted(n[0] * U for n in ends)
            ey = sorted(n[1] * U for n in ends)
            if ex[0] != ex[-1]:
                bx0, bx1 = max(bx0, ex[0] + 0.5), min(bx1, ex[-1] - 0.5)
            else:
                by0, by1 = max(by0, ey[0] + 0.5), min(by1, ey[-1] - 0.5)
        self.block_box(bx0, by0, bx1, by1, 0.9, keep=ends)
        for node, (rx, ry) in shafts:
            self.block_box(node[0] * U, node[1] * U, rx, ry, keep=ends)

        ref, val = c['ref'], c['value']
        wr, wv = CHAR * 1.27 * len(ref), CHAR * 1.0 * len(val)
        horizontal = two_pin and all(out in (0, 180) for _, out in groups)
        pa = 90 if R in (90, 270) else 0               # field angles are relative to the symbol
        spec = L.TEXT.get(ref)
        if isinstance(spec, tuple):
            (rp, vp) = spec
            rpos = (X + rp[0], Y + rp[1]) if rp else None
            vpos = (X + vp[0], Y + vp[1]) if vp else None
        elif horizontal:
            wr = CHAR * 1.0 * len(ref)
            total = wr + 0.8 + wv
            ty = by1 + 1.0 if spec == 'below' else by0 - 1.0
            rpos, vpos = (X - total / 2 + wr / 2, ty), (X + total / 2 - wv / 2, ty)
        elif two_pin:
            wr = CHAR * 1.0 * len(ref)
            rpos, vpos = (bx1 + 0.7 + wr / 2, Y - 0.9), (bx1 + 0.7 + wv / 2, Y + 0.9)
        elif len(pins) <= 4:
            rpos, vpos = (X, by0 - 3.0), (X, by0 - 1.3)
        else:
            rpos = (bx0 + wr / 2, by0 - 1.1)
            vpos = (min(bx0 + wv / 2, X - 3.0 - wv / 2), by1 + 1.1)
        rsize = 1.0 if two_pin else 1.27
        props = [prop('Reference', ref, *(rpos or (X, Y)), pa, hide=rpos is None, size=rsize),
                 prop('Value', val, *(vpos or (X, Y)), pa, hide=vpos is None, size=1.0)]
        if rpos:
            self.block_text(*rpos, ref, rsize)
        if vpos:
            self.block_text(*vpos, val, 1.0)
        in_bom = 'no' if ref.startswith(('H', 'TP')) else 'yes'
        inst = ['symbol', ['lib_id', Q(c['sym'])], ['at', r2(X), r2(Y), R]]
        if mirror:
            inst.append(['mirror', 'y'])
        inst += [['unit', 1], ['exclude_from_sim', 'no'], ['in_bom', in_bom], ['on_board', 'yes'], ['dnp', 'no'],
                 ['uuid', uid('sym', ref)]] + props + [
                    prop('Footprint', c['fp'], X, Y, hide=True), prop('Datasheet', '', X, Y, hide=True),
                    prop('MPN', c['mpn'], X, Y, hide=True), prop('Description', c['desc'], X, Y, hide=True)]
        for p in pins:
            inst.append(['pin', Q(p['num']), ['uuid', uid('pin', ref, p['num'])]])
        inst.append(['instances', ['project', Q(D.PROJECT),
                                   ['path', Q('/' + ROOT), ['reference', Q(ref)], ['unit', 1]]]])
        self.items.append(inst)

        for (node, out), nums in groups.items():
            nets = {c['pins'].get(n, '!missing') for n in nums}
            if '!missing' in nets:
                raise SystemExit(f"{ref}: pins {nums} have no net assignment")
            if len(nets) != 1:
                raise SystemExit(f"{ref}: stacked pins {nums} carry different nets {nets}")
            net = nets.pop()
            if net is None:
                self.items.append(['no_connect', ['at', r2(node[0] * U), r2(node[1] * U)], ['uuid', uid('nc', ref, nums[0])]])
                self.blocked.add(node)
                continue
            pn = dict(ref=ref, nums=nums, node=node, out=out, net=net, ic=not two_pin,
                      names={f'{ref}.{n}' for n in nums})
            self.nodes_of.setdefault(net, []).append(pn)
            self.npins[node] = self.npins.get(node, 0) + 1
        unknown = set(c['pins']) - {p['num'] for p in pins}
        if unknown:
            raise SystemExit(f"{ref}: pins {sorted(unknown)} do not exist on {c['sym']}")

    # ───────────────────────────── clusters ─────────────────────────────
    def new_cluster(self, net, pins):
        key = (net, len([k for k in self.clusters if k[0] == net]))
        cl = self.clusters[key] = Cluster(key, net)
        cl.pins = pins
        for p in pins:
            other = self.pinnode.get(p['node'])
            if other not in (None, key):
                raise SystemExit(f"pins of {net} and {other[0]} share the point {p['node']}")
            self.pinnode[p['node']] = key
            if p['ic']:
                self.arrive[p['node']] = tuple(-v for v in VEC[p['out']])
        return cl

    def build_clusters(self):
        grouped = {}
        for i, (net, names, sympos) in enumerate(L.GROUPS):
            grouped.setdefault(net, []).append((set(names), sympos, ('grp', i)))
        for net, pins in self.nodes_of.items():
            rest = list(pins)

            def take(names):
                got = [p for p in rest if p['names'] & names]
                missing = names - set().union(*[p['names'] for p in got]) if got else names
                if missing:
                    raise SystemExit(f'{net}: layout names pins that are not on this net: {sorted(missing)}')
                for p in got:
                    rest.remove(p)
                return got

            if net in POWER_SYMS:
                for names, (x, y, deg), tag in grouped.pop(net, []):
                    cl = self.new_cluster(net, take(names))
                    cl.term.append(((x, y), 'power', deg))
                for p in rest:                         # power symbol straight on the pin
                    self.pinnode[p['node']] = (net, 'direct', p['ref'], p['nums'][0])
                    self.power(net, p['node'], p['out'], (p['ref'], p['nums'][0]))
                continue
            for names, labelpos in (L.SPLIT[net] if net in L.SPLIT else [(set().union(*[p['names'] for p in pins]), None)]):
                cl = self.new_cluster(net, take(set(names)))
                if labelpos:
                    cl.term.append(((labelpos[0], labelpos[1]), 'label', labelpos[2]))
                else:
                    cl.want_label = len(cl.pins) > 1 or net in L.SPLIT
                if len(cl.pins) == 1 and not labelpos:
                    rest.append(cl.pins[0])
                    del self.clusters[cl.key]
            for p in rest:                             # single pin: stub + label
                cl = self.new_cluster(net, [p])
                dx, dy = VEC[p['out']]
                end = (p['node'][0] + 2 * dx, p['node'][1] + 2 * dy)
                self.add_path(cl, [p['node'], (p['node'][0] + dx, p['node'][1] + dy), end])
                self.pinnode[end] = cl.key
                self.label(net, end, p['out'], (p['ref'], p['nums'][0]))
        if grouped:
            raise SystemExit(f'layout groups for nets without pins: {list(grouped)}')
        for cl in self.clusters.values():
            for node, kind, deg in cl.term:
                if self.pinnode.get(node, cl.key) != cl.key or node in self.blocked:
                    raise SystemExit(f'{cl.net}: terminal {node} is not free')
                self.pinnode[node] = cl.key
                if kind == 'power':
                    self.power(cl.net, node, deg, ('grp',) + cl.key + node)
                else:
                    self.label(cl.net, node, deg, ('term',) + cl.key + node)
        # keep the two grid points in front of every IC pin free for its own wire
        for cl in self.clusters.values():
            for p in cl.pins:
                if p['ic']:
                    dx, dy = VEC[p['out']]
                    for k in (1, 2):
                        n = (p['node'][0] + k * dx, p['node'][1] + k * dy)
                        if n not in self.blocked and n not in self.pinnode and n not in self.reserved:
                            self.reserved[n] = cl.key

    # ───────────────────────────── wires ─────────────────────────────
    def edge_owner(self, a, b):
        if a > b:
            a, b = b, a
        return (self.h if a[1] == b[1] else self.v).get(a)

    def can_enter(self, key, a, b, step):
        """May a wire of cluster `key` go from a to the neighbouring node b?  Returns None or the extra cost."""
        if b in self.blocked:
            return None
        if self.pinnode.get(b, key) != key or self.reserved.get(b, key) != key:
            return None
        if self.edge_owner(a, b) is not None:
            return None
        cost = 0
        for other, steps in self.at.get(b, {}).items():
            if other == key:
                continue
            if steps != {(-step[1], step[0]), (step[1], -step[0])}:      # only a straight wire may be crossed
                return None
            cost += CROSS
        return cost

    def add_path(self, cl, path):
        for a, b in zip(path, path[1:]):
            step = (b[0] - a[0], b[1] - a[1])
            lo = min(a, b)
            (self.h if a[1] == b[1] else self.v)[lo] = cl.key
            cl.edges.add((lo, max(a, b)))
            self.at.setdefault(a, {}).setdefault(cl.key, set()).add(step)
            self.at.setdefault(b, {}).setdefault(cl.key, set()).add((-step[0], -step[1]))
        cl.nodes.update(path)

    def straight(self, cl, a, b):
        """Lay a straight wire a→b for the channel; fails loudly if the layout leaves no room."""
        step = ((b[0] > a[0]) - (b[0] < a[0]), (b[1] > a[1]) - (b[1] < a[1]))
        path = [a]
        while path[-1] != b:
            n = (path[-1][0] + step[0], path[-1][1] + step[1])
            if self.edge_owner(path[-1], n) == cl.key:
                path.append(n)
                continue
            if self.can_enter(cl.key, path[-1], n, step) is None:
                raise SystemExit(f'channel wire of {cl.net} is blocked at {n} (from {a} to {b})')
            path.append(n)
        self.add_path(cl, path)

    def targets(self, cl):
        """Nodes a new branch may end on: the cluster's wire nodes that no other wire crosses."""
        return {n for n in cl.nodes if len(self.at.get(n, {})) <= 1}

    def search(self, cl, src, forced, targets):
        key = cl.key
        xs, ys = [t[0] for t in targets], [t[1] for t in targets]
        bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)

        def hfun(n):
            return max(bx0 - n[0], 0, n[0] - bx1) + max(by0 - n[1], 0, n[1] - by1)

        start = (src, forced or (0, 0))
        dist = {start: 0}
        prev = {}
        heap = [(hfun(src), 0, src, forced or (0, 0), bool(forced))]
        seen = set()
        while heap:
            _, d, n, step, first_move = heapq.heappop(heap)
            state = (n, step, first_move)
            if state in seen:
                continue
            seen.add(state)
            if n in targets and n != src:
                path = [n]
                s = (n, step)
                while s in prev:
                    s = prev[s]
                    path.append(s[0])
                return path[::-1]
            crossing = any(o != key for o in self.at.get(n, {})) and n != src
            for nstep in VEC.values():
                if first_move and nstep != step:
                    continue
                if not first_move and step != (0, 0):
                    if nstep == (-step[0], -step[1]):
                        continue
                    if crossing and nstep != step:
                        continue
                b = (n[0] + nstep[0], n[1] + nstep[1])
                if not (0 < b[0] < self.gw and 0 < b[1] < self.gh):
                    continue
                extra = self.can_enter(key, n, b, nstep)
                if extra is None:
                    continue
                if b in self.arrive and b != src and self.arrive[b] != nstep:
                    continue
                if b in cl.nodes and b not in targets:
                    continue
                nd = d + 1 + extra + (BEND if step not in ((0, 0), nstep) else 0)
                ns = (b, nstep)
                if nd < dist.get(ns, 1e9):
                    dist[ns] = nd
                    prev[ns] = (n, step)
                    heapq.heappush(heap, (nd + hfun(b), nd, b, nstep, False))
        return None

    def route(self, cl):
        todo = [(p['node'], VEC[p['out']] if p['ic'] else None) for p in cl.pins] + [(t[0], None) for t in cl.term]
        todo = [t for i, t in enumerate(todo) if t[0] not in [u[0] for u in todo[:i]]]
        if not cl.nodes:
            cl.nodes.add(todo[0][0])
        while True:
            todo = [t for t in todo if t[0] not in cl.nodes]
            if not todo:
                return
            tg = self.targets(cl)
            todo.sort(key=lambda t: min(abs(t[0][0] - n[0]) + abs(t[0][1] - n[1]) for n in tg))
            node, forced = todo.pop(0)
            path = self.search(cl, node, forced, tg)
            if path is None:
                self.warn.append(f'UNROUTED {cl.net}: {node}')
                cl.nodes.add(node)
                self.label(cl.net, node, 0, ('fallback',) + cl.key + node)
                tree = min(tg)
                self.label(cl.net, tree, 0, ('fallback', 'tree') + cl.key + node)
                continue
            self.add_path(cl, path)

    def channel(self):
        """GPIO bundle: MCU pin → own vertical track → straight into the facing pins on the right."""
        nets = []
        for net in L.CHANNEL_NETS:
            cl = self.clusters[(net, 0)]
            src = [p['node'] for p in cl.pins if p['node'][0] < L.CH_X0 and p['out'] == 0]
            extra = set(L.CHANNEL_EXTRA.get(net, []))
            dst = [p['node'] for p in cl.pins if p['node'][0] > L.CH_X0 and (p['out'] == 180 or p['names'] & extra)]
            if len(src) != 1 or not dst:
                raise SystemExit(f'channel net {net}: needs one source pin and at least one facing pin')
            nets.append((net, cl, src[0], sorted(dst, key=lambda n: n[1])))
        up = sorted((n for n in nets if sum(d[1] for d in n[3]) / len(n[3]) < n[2][1]), key=lambda n: n[2][1])
        down = sorted((n for n in nets if n not in up), key=lambda n: -n[2][1])
        for i, (net, cl, src, dst) in enumerate(up + down):
            x = L.CH_X0 + i * L.CH_PITCH
            ys = [src[1]] + [d[1] for d in dst]
            self.straight(cl, src, (x, src[1]))
            self.straight(cl, (x, min(ys)), (x, max(ys)))
            for d in dst:
                self.straight(cl, (x, d[1]), d)

    def auto_label(self, cl):
        """One net label on the wire: on a horizontal run with free space above it."""
        size = 1.0
        need = math.ceil((CHAR * size * len(cl.net) + 0.8) / U)
        runs = self.runs(cl)
        hruns = sorted((r for r in runs if r[0][1] == r[1][1]),
                       key=lambda r: (not any(p['ic'] and p['node'] in r for p in cl.pins), -(r[1][0] - r[0][0])))
        for a, b in hruns:
            y = a[1]
            starts = list(range(a[0] + 1, b[0] - need + 1)) or list(range(a[0], b[0] - need + 1))
            if any(p['ic'] and p['node'] == b for p in cl.pins):
                starts.reverse()
            for x0 in starts:
                span = range(x0, x0 + need + 1)
                if all((x, y - 1) not in self.blocked and (x, y - 1) not in self.v
                       and (x, y - 1) not in self.h and (x - 1, y - 1) not in self.h for x in span) \
                        and all(len(self.at.get((x, y), {})) <= 1 for x in span):
                    self.label(cl.net, (x0, y), 0, ('auto',) + cl.key, size)
                    self.blocked.discard((x0, y))
                    return
        # no room above a horizontal run: put the label on the longest run anyway and say so
        best = max(runs, key=lambda r: abs(r[1][0] - r[0][0]) + abs(r[1][1] - r[0][1])) if runs else None
        if best is None:
            node = cl.pins[0]['node']
            self.label(cl.net, node, 0, ('auto',) + cl.key, size)
        elif best[0][1] == best[1][1]:
            self.label(cl.net, best[0], 0, ('auto',) + cl.key, size)
        else:
            self.label(cl.net, best[1], 90, ('auto',) + cl.key, size)
        self.warn.append(f'label of {cl.net} has no free space')

    def runs(self, cl):
        """Maximal straight wire pieces, split at tees, pins and terminals."""
        adj = {}
        for a, b in cl.edges:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
        stops = {p['node'] for p in cl.pins} | {t[0] for t in cl.term}
        out = []
        for horizontal in (True, False):
            edges = sorted(e for e in cl.edges if (e[0][1] == e[1][1]) == horizontal)
            edges.sort(key=lambda e: (e[0][1], e[0][0]) if horizontal else (e[0][0], e[0][1]))
            cur = None
            for a, b in edges:
                if cur and cur[1] == a and len(adj[a]) == 2 and a not in stops and a not in self.pinnode:
                    cur[1] = b
                else:
                    if cur:
                        out.append(tuple(cur))
                    cur = [a, b]
            if cur:
                out.append(tuple(cur))
        cl.adj = adj
        return out

    def emit(self, cl):
        for i, (a, b) in enumerate(self.runs(cl)):
            self.wire(a, b, cl.key + (i,))
        for node, nb in cl.adj.items():
            if len(nb) + self.npins.get(node, 0) + sum(1 for t in cl.term if t[0] == node and t[1] == 'power') >= 3:
                self.items.append(['junction', ['at', r2(node[0] * U), r2(node[1] * U)], ['diameter', 0],
                                   ['color', 0, 0, 0, 0], ['uuid', uid('j', *cl.key, *node)]])

    def render(self):
        tree = ['kicad_sch', ['version', 20250114], ['generator', Q('eeschema')], ['generator_version', Q('9.0')],
                ['uuid', Q(ROOT)], ['paper', Q(L.PAPER)],
                ['title_block', ['title', Q(D.TITLE)], ['date', Q(D.DATE)], ['rev', Q(D.REV)],
                 ['company', Q(D.COMPANY)], ['comment', 1, Q('www.eetree.cn')],
                 ['comment', 2, Q('Generated from gen/design.py + gen/sch_layout.py — edit the generator, not this file')],
                 ['comment', 3, Q('Pin map compatible with Raspberry Pi Debug Probe (debugprobe) firmware')]],
                ['lib_symbols'] + list(self.lib.values())]
        tree += self.items
        tree += [['sheet_instances', ['path', Q('/'), ['page', Q('1')]]], ['embedded_fonts', 'no']]
        return dump(tree) + '\n'


def write_project_lib(symdir, out_sch):
    """The VIO power symbol lives in a project library next to the schematic."""
    folder = os.path.dirname(os.path.abspath(out_sch))
    lib = ['kicad_symbol_lib', ['version', 20241209], ['generator', Q('kicad_symbol_editor')],
           ['generator_version', Q('9.0')]] + list(project_symbols(symdir).values())
    with open(os.path.join(folder, f'{PROJECT_LIB}.kicad_sym'), 'w', encoding='utf-8') as f:
        f.write(dump(lib) + '\n')
    with open(os.path.join(folder, 'sym-lib-table'), 'w', encoding='utf-8') as f:
        f.write('(sym_lib_table\n  (version 7)\n  (lib (name "%s")(type "KiCad")(uri "${KIPRJMOD}/%s.kicad_sym")'
                '(options "")(descr "Project power symbols"))\n)\n' % (PROJECT_LIB, PROJECT_LIB))


def main():
    symdir, out = sys.argv[1], sys.argv[2]
    sh = Sheet(symdir)
    sh.gw, sh.gh = {'A3': (330, 233), 'A2': (467, 330)}[L.PAPER]
    missing = [c['ref'] for c in D.COMPONENTS if c['ref'] not in L.POS]
    if missing:
        raise SystemExit(f'sch_layout.py has no position for {missing}')
    for c in D.COMPONENTS:
        sh.place(c)
    for x, y, size, s in L.NOTES:
        sh.text(x, y, size, s)
        sh.block_box(x * U, y * U - size, x * U + CHAR * size * len(s), y * U)
    for net, pos in L.FLAGS.items():
        sh.flag(net, pos)
        sh.block_box(pos[0] * U - 3, pos[1] * U - 6, pos[0] * U + 3, pos[1] * U + 9)
    sh.build_clusters()
    sh.channel()

    def size(cl):
        pts = [p['node'] for p in cl.pins] + [t[0] for t in cl.term]
        return (max(p[0] for p in pts) - min(p[0] for p in pts)) + (max(p[1] for p in pts) - min(p[1] for p in pts))

    for cl in sorted(sh.clusters.values(), key=size):
        sh.route(cl)
    for cl in sh.clusters.values():
        if cl.want_label:
            sh.auto_label(cl)
    for cl in sh.clusters.values():
        sh.emit(cl)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(sh.render())
    write_project_lib(symdir, out)
    wires = sum(len(cl.edges) for cl in sh.clusters.values())
    print(f'wrote {out}: {len(D.COMPONENTS)} components, {len(sh.clusters)} wired groups, {wires * U:.0f} mm of wire')
    for w in sh.warn:
        print('  ' + w)


if __name__ == '__main__':
    main()
