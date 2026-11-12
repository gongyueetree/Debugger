#!/usr/bin/env python3
"""Static placement check: every routable pad must reach open board area through cells that are not
inside another net's pad clearance or escape corridor.  usage: check_escape.py <pads.json>"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import route as R

r = R.Router(json.load(open(sys.argv[1])))
nx, N = r.nx, r.N
bad = 0
for i, p in enumerate(r.pads):
    if p['nid'] <= 0 or i not in r.pad_cells or p['drill'] > 0:
        continue
    best = 0
    for li in range(R.NL):
        cells = [idx for (l, idx) in r.pad_cells[i] if l == li]
        if not cells:
            continue
        own = r.pad_own[li].ravel()
        ok = ((own == 0) | (own == p['nid'])).tolist()
        seen = set(cells)
        stack = list(cells)
        while stack and len(seen) < 1500:
            c = stack.pop()
            for d in (1, -1, nx, -nx):
                n = c + d
                if 0 <= n < N and ok[n] and n not in seen:
                    seen.add(n)
                    stack.append(n)
        best = max(best, len(seen))
    if best < 1500:
        bad += 1
        print(f"  boxed in: {p['ref']}.{p['num']} [{p['net']}] at ({p['x']:.2f}, {p['y']:.2f}) reach {best * R.G * R.G:.1f} mm2")
print('escape check:', 'OK' if not bad else f'{bad} pad(s) boxed in')
sys.exit(1 if bad else 0)
