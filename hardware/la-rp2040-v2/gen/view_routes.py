#!/usr/bin/env python3
"""Quick raster preview of pads + routes.  usage: view_routes.py pads.json routes.json out.png [scale]"""
import json
import sys
from PIL import Image, ImageDraw

d = json.load(open(sys.argv[1])); r = json.load(open(sys.argv[2]))
S = float(sys.argv[4]) if len(sys.argv) > 4 else 28
L, W = d['board']['L'], d['board']['W']
img = Image.new('RGB', (int(L * S) + 20, int(4 * W * S) + 80), 'white')
dr = ImageDraw.Draw(img)
for k, layer in enumerate(('F.Cu', 'B.Cu', 'In2.Cu', 'In1.Cu')):
    oy = 10 + k * (W * S + 20)
    T = lambda x, y: (10 + x * S, oy + y * S)
    dr.rectangle([T(0, 0), T(L, W)], outline='black')
    col = ((200, 40, 40), (40, 80, 200), (150, 0, 150), (0, 130, 130))[k]
    routed = {(round(t['x1'], 1), round(t['y1'], 1)) for t in r['tracks']} | {(round(t['x2'], 1), round(t['y2'], 1)) for t in r['tracks']}
    for p in d['pads']:
        if layer in p['layers'] or p['npth']:
            c = (150, 150, 150) if p['npth'] else ((0, 150, 0) if p['net'] == 'GND' else ((230, 150, 0) if p['net'] == '+3V3' else (90, 90, 90)))
            dr.rectangle([T(p['x0'], p['y0']), T(p['x1'], p['y1'])], fill=c)
    for t in r['tracks']:
        if t['layer'] == layer:
            dr.line([T(t['x1'], t['y1']), T(t['x2'], t['y2'])], fill=col, width=max(1, int(t['w'] * S)))
    for v in r['vias']:
        x, y = T(v['x'], v['y'])
        c = (0, 150, 0) if v['net'] == 'GND' else ((230, 150, 0) if v['net'] == '+3V3' else (0, 0, 0))
        dr.ellipse([x - 0.3 * S, y - 0.3 * S, x + 0.3 * S, y + 0.3 * S], outline=c, width=2)
    for c in d['courtyards']:
        if k < 2 and (c['side'] == 'F') == (k == 0):
            dr.rectangle([T(c['x0'], c['y0']), T(c['x1'], c['y1'])], outline=(180, 180, 255))
            dr.text(T(c['x0'] + 0.1, c['y0'] + 0.05), c['ref'], fill=(120, 0, 120))
img.save(sys.argv[3])
