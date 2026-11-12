#!/usr/bin/env python3
"""Generate the KiCad 9 schematic from design.py.

usage: gen_sch.py <kicad-symbol-dir> <output.kicad_sch>

Every pin gets a short wire stub that ends in a net label (or a power symbol
for GND / +3V3 / +5V / +1V1), so connectivity is by name and can be verified
against design.py with `kicad-cli sch export netlist`.
"""
import math
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as D
from sexpr import Q, parse, dump, find, first

NS = uuid.UUID('6f1d3c1e-6f0a-4b61-9d57-2a5c0f8e2040')
POWER_SYMS = {'GND': 'power:GND', '+3V3': 'power:+3V3', '+5V': 'power:+5V', '+1V1': 'power:+1V1'}
STUB = 2.54


def uid(*key):
    return Q(str(uuid.uuid5(NS, '/'.join(str(k) for k in key))))


ROOT = uid('root')[:]
_libs = {}


def load_symbol(symdir, lib_id):
    lib, name = lib_id.split(':')
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


class Sheet:
    def __init__(self, symdir):
        self.symdir = symdir
        self.lib = {}
        self.items = []
        self.pwr = 0

    def use(self, lib_id):
        if lib_id not in self.lib:
            self.lib[lib_id] = load_symbol(self.symdir, lib_id)
        return self.lib[lib_id]

    def wire(self, a, b, key):
        self.items.append(['wire', ['pts', ['xy', r2(a[0]), r2(a[1])], ['xy', r2(b[0]), r2(b[1])]],
                           ['stroke', ['width', 0], ['type', 'default']], ['uuid', uid('w', *key)]])

    def label(self, net, pos, out_deg, key):
        ang = {0: 0, 90: 90, 180: 180, 270: 270}[out_deg]
        just = ['left', 'bottom'] if out_deg in (0, 90) else ['right', 'bottom']
        self.items.append(['label', Q(net), ['at', r2(pos[0]), r2(pos[1]), ang], font(1.27, just),
                           ['uuid', uid('l', *key)]])

    def power(self, net, pos, out_deg, key):
        lib_id = POWER_SYMS[net]
        self.use(lib_id)
        self.pwr += 1
        ref = f'#PWR{self.pwr:03d}'
        base = 270 if net == 'GND' else 90          # direction the graphic points at angle 0
        ang = int((out_deg - base) % 360)
        dx, dy = math.cos(math.radians(out_deg)), -math.sin(math.radians(out_deg))
        vx, vy = pos[0] + dx * 4.6, pos[1] + dy * 4.6
        horizontal = out_deg in (0, 180)
        just = (['left'] if out_deg == 0 else ['right']) if horizontal else None
        if horizontal:
            vx = pos[0] + dx * 3.2
        self.items.append(['symbol', ['lib_id', Q(lib_id)], ['at', r2(pos[0]), r2(pos[1]), ang], ['unit', 1],
                           ['exclude_from_sim', 'no'], ['in_bom', 'yes'], ['on_board', 'yes'], ['dnp', 'no'],
                           ['uuid', uid('p', *key)],
                           prop('Reference', ref, pos[0], pos[1], hide=True),
                           prop('Value', net, vx, vy, 0, just, size=1.0),
                           prop('Footprint', '', pos[0], pos[1], hide=True),
                           prop('Datasheet', '', pos[0], pos[1], hide=True),
                           ['pin', Q('1'), ['uuid', uid('pp', *key)]],
                           ['instances', ['project', Q(D.PROJECT),
                                          ['path', Q('/' + ROOT), ['reference', Q(ref)], ['unit', 1]]]]])

    def flag(self, net, pos):
        self.use('power:PWR_FLAG')
        self.pwr += 1
        ref = f'#FLG{self.pwr:03d}'
        x, y = pos
        self.items.append(['symbol', ['lib_id', Q('power:PWR_FLAG')], ['at', x, y, 0], ['unit', 1],
                           ['exclude_from_sim', 'no'], ['in_bom', 'yes'], ['on_board', 'yes'], ['dnp', 'no'],
                           ['uuid', uid('f', net)],
                           prop('Reference', ref, x, y, hide=True),
                           prop('Value', 'PWR_FLAG', x, y - 5.0, size=1.0),
                           prop('Footprint', '', x, y, hide=True), prop('Datasheet', '', x, y, hide=True),
                           ['pin', Q('1'), ['uuid', uid('fp', net)]],
                           ['instances', ['project', Q(D.PROJECT),
                                          ['path', Q('/' + ROOT), ['reference', Q(ref)], ['unit', 1]]]]])
        self.wire((x, y), (x, y + STUB), ('flag', net))
        if net in POWER_SYMS:
            self.power(net, (x, y + STUB), 270, ('flag', net))
        else:
            self.label(net, (x, y + STUB), 270, ('flag', net))

    def place(self, c):
        sym = self.use(c['sym'])
        X, Y, R = c['sch']
        pins = sym_pins(sym)
        # body box from pin roots (sheet coordinates)
        bx, by = [], []
        groups = {}
        for p in pins:
            px, py = rot(p['x'], p['y'], R)
            ex, ey = rot(p['x'] + p['len'] * math.cos(math.radians(p['ang'])),
                         p['y'] + p['len'] * math.sin(math.radians(p['ang'])), R)
            bx.append(X + ex)
            by.append(Y - ey)
            out = int(round(p['ang'] + 180 + R)) % 360
            groups.setdefault((r2(X + px), r2(Y - py), out), []).append(p['num'])
        if not pins:
            bx, by = [X - 2.54, X + 2.54], [Y - 2.54, Y + 2.54]
        two_pin = len(pins) == 2 and c['ref'][0] in 'RCFDL'
        if two_pin:
            pa = 90 if R in (90, 270) else 0       # field angles are relative to the symbol
            rp = prop('Reference', c['ref'], X, Y - 2.4, pa)
            vp = prop('Value', c['value'], X, Y + 2.4, pa, size=1.0)
        elif len(pins) <= 4:
            top = min(by + [Y - 2.54])
            rp = prop('Reference', c['ref'], X, top - 4.2)
            vp = prop('Value', c['value'], X, top - 2.4, size=1.0)
        else:
            x0 = min(bx) - 0.6
            rp = prop('Reference', c['ref'], x0, min(by) - 1.0, 0, ['right', 'bottom'])
            vp = prop('Value', c['value'], x0, max(by) + 1.0, 0, ['right', 'top'])
        in_bom = 'no' if c['ref'].startswith(('H', 'TP')) else 'yes'
        inst = ['symbol', ['lib_id', Q(c['sym'])], ['at', r2(X), r2(Y), R], ['unit', 1],
                ['exclude_from_sim', 'no'], ['in_bom', in_bom], ['on_board', 'yes'], ['dnp', 'no'],
                ['uuid', uid('sym', c['ref'])], rp, vp,
                prop('Footprint', c['fp'], X, Y, hide=True), prop('Datasheet', '', X, Y, hide=True),
                prop('MPN', c['mpn'], X, Y, hide=True), prop('Description', c['desc'], X, Y, hide=True)]
        for p in pins:
            inst.append(['pin', Q(p['num']), ['uuid', uid('pin', c['ref'], p['num'])]])
        inst.append(['instances', ['project', Q(D.PROJECT),
                                   ['path', Q('/' + ROOT), ['reference', Q(c['ref'])], ['unit', 1]]]])
        self.items.append(inst)

        for (px, py, out), nums in groups.items():
            nets = {c['pins'].get(n, '!missing') for n in nums}
            if '!missing' in nets:
                raise SystemExit(f"{c['ref']}: pins {nums} have no net assignment")
            if len(nets) != 1:
                raise SystemExit(f"{c['ref']}: stacked pins {nums} carry different nets {nets}")
            net = nets.pop()
            key = (c['ref'], nums[0])
            if net is None:
                self.items.append(['no_connect', ['at', px, py], ['uuid', uid('nc', *key)]])
                continue
            dx, dy = math.cos(math.radians(out)), -math.sin(math.radians(out))
            end = (px + dx * STUB, py + dy * STUB)
            self.wire((px, py), end, key)
            if net in POWER_SYMS:
                self.power(net, end, out, key)
            else:
                self.label(net, end, out, key)
        unknown = set(c['pins']) - {p['num'] for p in pins}
        if unknown:
            raise SystemExit(f"{c['ref']}: pins {sorted(unknown)} do not exist on {c['sym']}")

    def text(self, x, y, size, s):
        self.items.append(['text', Q(s), ['exclude_from_sim', 'no'], ['at', x, y, 0],
                           font(size, ['left', 'bottom']), ['uuid', uid('t', s)]])

    def render(self):
        tree = ['kicad_sch', ['version', 20250114], ['generator', Q('eeschema')], ['generator_version', Q('9.0')],
                ['uuid', Q(ROOT)], ['paper', Q('A3')],
                ['title_block', ['title', Q(D.TITLE)], ['date', Q(D.DATE)], ['rev', Q(D.REV)],
                 ['company', Q(D.COMPANY)], ['comment', 1, Q('www.eetree.cn')],
                 ['comment', 2, Q('Generated from gen/design.py — edit the generator, not this file')],
                 ['comment', 3, Q('Pin map compatible with Raspberry Pi Debug Probe (debugprobe) firmware')]],
                ['lib_symbols'] + list(self.lib.values())]
        tree += self.items
        tree += [['sheet_instances', ['path', Q('/'), ['page', Q('1')]]], ['embedded_fonts', 'no']]
        return dump(tree) + '\n'


def main():
    symdir, out = sys.argv[1], sys.argv[2]
    sh = Sheet(symdir)
    for c in D.COMPONENTS:
        sh.place(c)
    for net, pos in D.PWR_FLAGS.items():
        sh.flag(net, pos)
    for x, y, size, s in D.SCH_NOTES:
        sh.text(x, y, size, s)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(sh.render())
    print(f'wrote {out}: {len(D.COMPONENTS)} components')


if __name__ == '__main__':
    main()
