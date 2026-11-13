#!/usr/bin/env python3
"""Turn the 'unconnected items' of a KiCad DRC report into point pairs for `route.py --bridge`.
usage: drc_pairs.py <drc.rpt> <pairs.json>   (exit code 0 if there is something to bridge)"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as D

OX, OY = D.BOARD_ORIGIN
text = open(sys.argv[1], encoding='utf-8').read()
pairs, skipped = [], 0
for block in re.findall(r'\[unconnected_items\][^\n]*\n[^\n]*\n((?:\s+@[^\n]*\n){2})', text):
    ends = []
    for line in block.strip().splitlines():
        m = re.match(r'\s*@\(([\d.]+) mm, ([\d.]+) mm\): (\w+).*?\[([^\]]+)\].* on (.+)$', line)
        if not m or m.group(3) == 'Zone':
            ends = None
            break
        layer = '*' if ' - ' in m.group(5) or m.group(3) == 'Via' else m.group(5).split(',')[0].strip()
        ends.append(dict(x=float(m.group(1)) - OX, y=float(m.group(2)) - OY, layer=layer, net=m.group(4)))
    if not ends:
        skipped += 1
        continue
    pairs.append(dict(net=ends[0]['net'], a=ends[0], b=ends[1]))
json.dump(pairs, open(sys.argv[2], 'w'), indent=1)
print(f'{len(pairs)} unconnected pair(s) to bridge, {skipped} zone-only item(s) skipped')
sys.exit(0 if pairs else 1)
