#!/usr/bin/env python3
"""Find groups of copper on a net that the zone fills leave disconnected from the main group (run inside
the KiCad container).  usage: gnd_islands.py <board.kicad_pcb> <net> <pairs.json>
Writes one point pair per stranded group (a point in the group → nearest point of the main group)."""
import json
import sys

import pcbnew

board = pcbnew.LoadBoard(sys.argv[1])
net = board.FindNet(sys.argv[2])
code = net.GetNetCode()
OX = OY = 100.0
layers = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
names = {pcbnew.F_Cu: 'F.Cu', pcbnew.In1_Cu: 'In1.Cu', pcbnew.In2_Cu: 'In2.Cu', pcbnew.B_Cu: 'B.Cu'}
parent = {}


def find(a):
    parent.setdefault(a, a)
    while parent[a] != a:
        parent[a] = parent[parent[a]]
        a = parent[a]
    return a


def union(a, b):
    parent[find(a)] = find(b)


islands = []                                            # (key, layer, polyset, index)
for zi, z in enumerate(board.Zones()):
    if z.GetNetCode() != code:
        continue
    for l in layers:
        if not z.IsOnLayer(l):
            continue
        ps = z.GetFilledPolysList(l)
        for k in range(ps.OutlineCount()):
            islands.append((('z', zi, l, k), l, ps, k))


def touch(key, pt, on_layers):
    for ikey, l, ps, k in islands:
        if l in on_layers and ps.Contains(pt, k, 1000):
            union(key, ikey)


points = {}
for fp in board.GetFootprints():
    for pad in fp.Pads():
        if pad.GetNetCode() == code:
            key = ('p', fp.GetReference(), pad.GetNumber(), pad.GetPosition().x, pad.GetPosition().y)
            ls = [l for l in layers if pad.IsOnLayer(l)]
            points[key] = (pad.GetPosition(), ls)
            touch(key, pad.GetPosition(), ls)
ends = {}
for t in board.GetTracks():
    if t.GetNetCode() != code:
        continue
    if t.GetClass() == 'PCB_VIA':
        key = ('v', t.GetPosition().x, t.GetPosition().y)
        points[key] = (t.GetPosition(), layers)
        touch(key, t.GetPosition(), layers)
        for l in layers:
            ends.setdefault((t.GetPosition().x, t.GetPosition().y, l), []).append(key)
    else:
        key = ('t', t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y, t.GetLayer())
        points[key] = (t.GetStart(), [t.GetLayer()])
        for pt in (t.GetStart(), t.GetEnd()):
            touch(key, pt, [t.GetLayer()])
            ends.setdefault((pt.x, pt.y, t.GetLayer()), []).append(key)
for keys in ends.values():
    for k in keys[1:]:
        union(keys[0], k)
# track ends / vias sitting on pads
for (x, y, l), keys in ends.items():
    for pk, (pos, ls) in points.items():
        if pk[0] == 'p' and l in ls:
            fp = board.FindFootprintByReference(pk[1])
            for pad in fp.Pads():
                if pad.GetNumber() == pk[2] and pad.GetPosition().x == pk[3] and pad.HitTest(pcbnew.VECTOR2I(x, y)):
                    union(keys[0], pk)
groups = {}
for k in points:
    groups.setdefault(find(k), []).append(k)
main = max(groups.values(), key=len)
mm = lambda v: round(pcbnew.ToMM(v) - 100.0, 3)
pairs = []
for g in groups.values():
    if g is main:
        continue
    a = g[0]
    pa, la = points[a]
    best = min(main, key=lambda k: abs(points[k][0].x - pa.x) + abs(points[k][0].y - pa.y))
    pb, lb = points[best]
    lay = lambda ls: '*' if len(ls) > 1 else names[ls[0]]
    pairs.append(dict(net=sys.argv[2], a=dict(x=mm(pa.x), y=mm(pa.y), layer=lay(la)), b=dict(x=mm(pb.x), y=mm(pb.y), layer=lay(lb))))
    print('stranded group:', len(g), 'item(s), e.g.', a[:3], 'at', mm(pa.x), mm(pa.y))
json.dump(pairs, open(sys.argv[3], 'w'), indent=1)
print(f'{len(groups)} group(s), {len(pairs)} stranded')
