#!/usr/bin/env python3
"""Write the grouped BOM (CSV) from design.py.  usage: gen_bom.py <out.csv>"""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as D


def natural(ref):
    m = re.match(r'([A-Z]+)(\d+)', ref)
    return (m.group(1), int(m.group(2)))


groups = {}
for c in D.COMPONENTS:
    if c['ref'].startswith('H'):
        continue
    key = (c['value'], c['fp'].split(':')[1], c['mpn'], c['desc'])
    groups.setdefault(key, []).append(c['ref'])
rows = sorted(groups.items(), key=lambda kv: natural(sorted(kv[1], key=natural)[0]))
with open(sys.argv[1], 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['Item', 'Qty', 'Reference', 'Value', 'Footprint', 'Part / MPN', 'Side', 'Description'])
    for i, ((value, fp, mpn, desc), refs) in enumerate(rows, 1):
        refs = sorted(refs, key=natural)
        sides = {next(c['pcb'][3] for c in D.COMPONENTS if c['ref'] == r) for r in refs}
        side = {'F': 'Top', 'B': 'Bottom'}[sides.pop()] if len(sides) == 1 else 'Top+Bottom'
        w.writerow([i, len(refs), ' '.join(refs), value, fp, mpn, side, desc])
total = sum(len(r) for _, r in rows)
print(f'wrote {sys.argv[1]}: {len(rows)} line items, {total} parts')
