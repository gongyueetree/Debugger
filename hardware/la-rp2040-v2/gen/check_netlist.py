#!/usr/bin/env python3
"""Compare a KiCad-exported netlist (kicadsexpr) against design.py.  usage: check_netlist.py <file.net>"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as D
from sexpr import parse, find, first

tree = parse(open(sys.argv[1], encoding='utf-8').read())
got = {}
for net in find(first(tree, 'nets'), 'net'):
    name = first(net, 'name')[1].lstrip('/')
    for node in find(net, 'node'):
        got[(first(node, 'ref')[1], first(node, 'pin')[1])] = name
want = {(c['ref'], pin): net for c in D.COMPONENTS for pin, net in c['pins'].items() if net}
bad = 0
for key in sorted(set(got) | set(want)):
    g, w = got.get(key), want.get(key)
    if g and g.startswith('unconnected-'):
        g = None
    if g != w:
        bad += 1
        print(f'MISMATCH {key[0]}.{key[1]}: schematic={g} design={w}')
refs = {first(c, 'ref')[1] for c in find(first(tree, 'components'), 'comp')}
missing = {c['ref'] for c in D.COMPONENTS} - refs
if missing:
    bad += 1
    print('missing components:', sorted(missing))
print(f'netlist check: {len(want)} pins, {len(set(want.values()))} nets, {bad} mismatches')
sys.exit(1 if bad else 0)
