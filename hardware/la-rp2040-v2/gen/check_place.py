#!/usr/bin/env python3
"""Report courtyard overlaps and out-of-board parts.  usage: check_place.py <pads.json>"""
import json
import sys

d = json.load(open(sys.argv[1]))
cy = d['courtyards']
L, W = d['board']['L'], d['board']['W']
bad = 0
for i, a in enumerate(cy):
    if a['ref'] not in ('J1', 'J2', 'SW2', 'H1', 'H2') and (a['x0'] < 0.2 or a['y0'] < 0.2 or a['x1'] > L - 0.2 or a['y1'] > W - 0.2):
        print('near/over edge:', a['ref'], [round(a[k], 2) for k in ('x0', 'y0', 'x1', 'y1')]); bad += 1
    for b in cy[i + 1:]:
        if a['side'] != b['side']:
            continue
        ox = min(a['x1'], b['x1']) - max(a['x0'], b['x0'])
        oy = min(a['y1'], b['y1']) - max(a['y0'], b['y0'])
        if ox > 0.01 and oy > 0.01:
            print(f"overlap {a['ref']}–{b['ref']} ({a['side']}): {ox:.2f} x {oy:.2f} mm"); bad += 1
print('placement check:', 'OK' if not bad else f'{bad} issue(s)')
