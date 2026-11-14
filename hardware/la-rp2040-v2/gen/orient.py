#!/usr/bin/env python3
"""Orientation check for two-pad parts.  usage: orient.py <pads.json>

For every resistor / capacitor / diode / fuse / LED, compare the distance from each of its pads to the nearest
pad it has to be wired to (same net, another part) in the current orientation and turned by 180 degrees.
Parts whose routed length would shrink are listed; design.py applies the list through ORIENT_FLIP.
Plane nets (GND, +3V3) are ignored: those pads drop straight into the inner layers.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as D

data = json.load(open(sys.argv[1]))
pads = [p for p in data['pads'] if p['layers'] and p['net'] and not p['npth']]
plane = set(D.PLANES)
by_ref = {}
for p in pads:
    by_ref.setdefault(p['ref'], []).append(p)
locked = {t.split('.')[0] for link in D.PRE_LINKS for t in link[2:4] if isinstance(t, str)}


def strip(n):
    return n[1:] if n.startswith('/') else n


def cost(ref, pos):
    """Sum of distances from this part's signal pads (at positions pos) to the nearest same-net pad elsewhere."""
    total = 0.0
    for p, (x, y) in zip(by_ref[ref], pos):
        if strip(p['net']) in plane:
            continue
        others = [q for q in pads if q['net'] == p['net'] and q['ref'] != ref]
        if others:
            total += min(math.hypot(q['x'] - x, q['y'] - y) + (0.8 if not set(q['layers']) & set(p['layers']) else 0)
                         for q in others)
    return total


flips = set()
for _ in range(6):
    changed = False
    for ref, ps in by_ref.items():
        if len(ps) != 2 or ref[0] not in 'RCDF' or ref in locked:
            continue
        here = [(p['x'], p['y']) for p in ps]
        a, b = cost(ref, here), cost(ref, here[::-1])
        if b < a - 0.15:
            (ps[0]['x'], ps[0]['y']), (ps[1]['x'], ps[1]['y']) = here[1], here[0]
            flips ^= {ref}
            changed = True
            print(f'  {ref}: {a:.2f} mm -> {b:.2f} mm when turned 180 deg')
    if not changed:
        break
print('ORIENT_FLIP =', sorted(flips, key=lambda r: (r[0], int(r[1:]))))
