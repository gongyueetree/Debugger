#!/usr/bin/env python3
"""Build the KiCad 9 PCB from design.py (run inside the KiCad container, needs pcbnew).

  gen_pcb.py place  <sch.net> <out.kicad_pcb> <pads.json>     footprints, nets, outline
  gen_pcb.py finish <in.kicad_pcb> <routes.json> <out.kicad_pcb>   tracks, vias, zones, silkscreen
"""
import json
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as D
from sexpr import parse, find, first

HERE = os.path.dirname(os.path.abspath(__file__))
KICAD_DIR = os.path.join(os.path.dirname(HERE), 'kicad')
FP_ROOT = os.environ.get('KICAD9_FOOTPRINT_DIR', '/usr/share/kicad/footprints')
OX, OY = D.BOARD_ORIGIN
MM = pcbnew.FromMM


def P(x, y):
    return pcbnew.VECTOR2I(MM(OX + x), MM(OY + y))


def write_j2_footprint():
    """2x8 2.54 mm header straddling the board edge: odd pins on F.Cu, even pins on B.Cu."""
    d = os.path.join(KICAD_DIR, f'{D.LIB}.pretty')
    os.makedirs(d, exist_ok=True)
    name = 'PinHeader_2x08_P2.54mm_EdgeMount'
    rows = [(-8.89 + 2.54 * k) for k in range(8)]
    out = [f'(footprint "{name}"', '\t(version 20241229)', '\t(generator "la_rp2040_v2_gen")', '\t(layer "F.Cu")',
           '\t(descr "2x8 2.54mm straight pin header soldered across the edge of a 1.6mm PCB; '
           'odd pins top side, even pins bottom side, board edge 2.5mm right of the origin")',
           '\t(tags "edge mount straddle pin header 2x08")',
           '\t(property "Reference" "REF**" (at -3.2 -10.2 0) (layer "F.Fab") (effects (font (size 0.8 0.8) (thickness 0.12))))',
           '\t(property "Value" "%s" (at 0 10.4 0) (layer "F.Fab") (effects (font (size 0.8 0.8) (thickness 0.12))))' % name,
           '\t(attr smd)']
    for layer in ('F.Fab', 'B.Fab'):
        out.append(f'\t(fp_rect (start 2.5 -10.16) (end 5.0 10.16) (stroke (width 0.1) (type solid)) (fill no) (layer "{layer}"))')
        for y in rows:
            out.append(f'\t(fp_rect (start -2.0 {y - 0.32:.2f}) (end 11.0 {y + 0.32:.2f}) (stroke (width 0.1) (type solid)) (fill no) (layer "{layer}"))')
    for layer in ('F.CrtYd', 'B.CrtYd'):
        out.append(f'\t(fp_rect (start -2.25 -9.65) (end 2.25 9.65) (stroke (width 0.05) (type solid)) (fill no) (layer "{layer}"))')
    for k, y in enumerate(rows):
        out.append(f'\t(pad "{2 * k + 1}" smd roundrect (at 0 {y:.2f}) (size 4 1.1) (layers "F.Cu" "F.Mask" "F.Paste") (roundrect_rratio 0.15))')
        out.append(f'\t(pad "{2 * k + 2}" smd roundrect (at 0 {y:.2f}) (size 4 1.1) (layers "B.Cu" "B.Mask" "B.Paste") (roundrect_rratio 0.15))')
    out.append(')')
    with open(os.path.join(d, name + '.kicad_mod'), 'w') as f:
        f.write('\n'.join(out) + '\n')


def load_netlist(path):
    tree = parse(open(path, encoding='utf-8').read())
    pinnet = {}
    for net in find(first(tree, 'nets'), 'net'):
        name = first(net, 'name')[1]
        for node in find(net, 'node'):
            pinnet[(first(node, 'ref')[1], first(node, 'pin')[1])] = name
    paths = {}
    for c in find(first(tree, 'components'), 'comp'):
        ts = first(c, 'tstamps')
        paths[first(c, 'ref')[1]] = ts[1] if ts else None
    return pinnet, paths


def outline(board):
    L, W, r = D.BOARD_L, D.BOARD_W, D.CORNER_R

    def seg(a, b):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(P(*a)); s.SetEnd(P(*b)); s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(MM(0.1)); board.Add(s)

    def arc(a, m, b):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_ARC)
        s.SetArcGeometry(P(*a), P(*m), P(*b)); s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(MM(0.1)); board.Add(s)

    k = r * (1 - 0.70710678)
    seg((r, 0), (L - r, 0)); seg((L, r), (L, W - r)); seg((L - r, W), (r, W)); seg((0, W - r), (0, r))
    arc((0, r), (k, k), (r, 0)); arc((L - r, 0), (L - k, k), (L, r))
    arc((L, W - r), (L - k, W - k), (L - r, W)); arc((r, W), (k, W - k), (0, W - r))


def place(netfile, out_pcb, out_json):
    write_j2_footprint()
    pinnet, paths = load_netlist(netfile)
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(4)
    bds = board.GetDesignSettings()
    bds.SetBoardThickness(MM(1.6))
    nets = {}

    def net(name):
        if name not in nets:
            n = pcbnew.NETINFO_ITEM(board, name)
            board.Add(n)
            nets[name] = n
        return nets[name]

    dump = dict(board=dict(L=D.BOARD_L, W=D.BOARD_W), pads=[], holes=[], courtyards=[])
    for c in D.COMPONENTS:
        lib, name = c['fp'].split(':')
        libdir = os.path.join(KICAD_DIR, lib + '.pretty') if lib == D.LIB else os.path.join(FP_ROOT, lib + '.pretty')
        fp = pcbnew.FootprintLoad(libdir, name)
        if fp is None:
            raise SystemExit(f'footprint not found: {c["fp"]}')
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetReference(c['ref'])
        fp.SetValue(c['value'])
        x, y, rot, side = c['pcb']
        fp.SetPosition(P(x, y))
        board.Add(fp)                       # must be on a board before Flip()
        if side == 'B':
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetOrientationDegrees(rot)
        if paths.get(c['ref']):
            fp.SetPath(pcbnew.KIID_PATH('/' + paths[c['ref']]))
        fp.SetSheetname('/')
        fp.SetSheetfile(f'{D.PROJECT}.kicad_sch')
        if c['mpn']:
            fp.SetField('MPN', c['mpn'])
            fp.GetFieldByName('MPN').SetVisible(False)
        # reference designators live on the Fab layers: the board is too dense for silkscreen refs
        fab = pcbnew.B_Fab if side == 'B' else pcbnew.F_Fab
        fp.Reference().SetLayer(fab)
        fp.Reference().SetTextSize(pcbnew.VECTOR2I(MM(0.5), MM(0.5)))
        fp.Reference().SetTextThickness(MM(0.08))
        fp.Reference().SetPosition(fp.GetPosition())
        fp.Value().SetVisible(False)
        if c['ref'].startswith('H'):
            fp.SetAttributes(pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
        for item in fp.GraphicalItems():
            if item.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                item.SetLayer(fab)          # silkscreen is drawn by finish(); footprint outlines would overlap pads
    for c in D.COMPONENTS:
        fp = board.FindFootprintByReference(c['ref'])
        side = c['pcb'][3]
        for pad in fp.Pads():
            num = pad.GetNumber()
            nname = pinnet.get((c['ref'], num))
            if nname:
                pad.SetNet(net(nname))
            bb = pad.GetBoundingBox()
            pos = pad.GetPosition()
            layers = [board.GetLayerName(l) for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
                      if pad.IsOnLayer(l)]
            rec = dict(ref=c['ref'], num=num, net=nname or '',
                       x=pcbnew.ToMM(pos.x) - OX, y=pcbnew.ToMM(pos.y) - OY,
                       x0=pcbnew.ToMM(bb.GetLeft()) - OX, y0=pcbnew.ToMM(bb.GetTop()) - OY,
                       x1=pcbnew.ToMM(bb.GetRight()) - OX, y1=pcbnew.ToMM(bb.GetBottom()) - OY,
                       layers=layers, drill=pcbnew.ToMM(pad.GetDrillSize().x), drill_y=pcbnew.ToMM(pad.GetDrillSize().y),
                       npth=pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH,
                       paste=pad.IsOnLayer(pcbnew.F_Paste) or pad.IsOnLayer(pcbnew.B_Paste))
            dump['pads'].append(rec)
        cy = fp.GetCourtyard(pcbnew.B_CrtYd if side == 'B' else pcbnew.F_CrtYd)
        if cy.OutlineCount():
            bb = cy.BBox()
            dump['courtyards'].append(dict(ref=c['ref'], side=side,
                                           x0=pcbnew.ToMM(bb.GetLeft()) - OX, y0=pcbnew.ToMM(bb.GetTop()) - OY,
                                           x1=pcbnew.ToMM(bb.GetRight()) - OX, y1=pcbnew.ToMM(bb.GetBottom()) - OY))
    outline(board)
    pcbnew.SaveBoard(out_pcb, board)
    with open(out_json, 'w') as f:
        json.dump(dump, f, indent=1)
    print(f'placed {len(D.COMPONENTS)} footprints, {len(dump["pads"])} pads, {len(nets)} nets')


# ───────────────────────────────── finish ─────────────────────────────────
def text(board, s, x, y, layer, size=0.8, rot=0, thick=None, justify=None):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
    t.SetTextThickness(MM(thick or size * 0.15))
    t.SetPosition(P(x, y))
    t.SetTextAngleDegrees(rot)
    if layer in (pcbnew.B_SilkS, pcbnew.B_Fab, pcbnew.B_Cu):
        t.SetMirrored(True)
    if justify == 'left':
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
    elif justify == 'right':
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT)
    board.Add(t)
    return t


def zone(board, netinfo, layer, name, clearance=0.15, thermal=True, priority=0, inset=0.0):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(netinfo)
    z.SetZoneName(name)
    z.SetAssignedPriority(priority)
    o = z.Outline()
    o.NewOutline()
    for x, y in ((inset, inset), (D.BOARD_L - inset, inset), (D.BOARD_L - inset, D.BOARD_W - inset), (inset, D.BOARD_W - inset)):
        o.Append(MM(OX + x), MM(OY + y))
    z.SetLocalClearance(MM(clearance))
    z.SetMinThickness(MM(0.15))
    z.SetThermalReliefGap(MM(0.2))
    z.SetThermalReliefSpokeWidth(MM(0.3))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL if thermal else pcbnew.ZONE_CONNECTION_FULL)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    board.Add(z)
    return z


def finish(in_pcb, routes_json, out_pcb):
    board = pcbnew.LoadBoard(in_pcb)
    routes = json.load(open(routes_json))
    lay = {'F.Cu': pcbnew.F_Cu, 'B.Cu': pcbnew.B_Cu, 'In1.Cu': pcbnew.In1_Cu, 'In2.Cu': pcbnew.In2_Cu}
    for t in routes['tracks']:
        tr = pcbnew.PCB_TRACK(board)
        tr.SetStart(P(t['x1'], t['y1'])); tr.SetEnd(P(t['x2'], t['y2']))
        tr.SetWidth(MM(t['w'])); tr.SetLayer(lay[t['layer']]); tr.SetNet(board.FindNet(t['net']))
        board.Add(tr)
    for v in routes['vias']:
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(P(v['x'], v['y']))
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetDrill(MM(D.VIA_DRILL))
        via.SetWidth(pcbnew.F_Cu, MM(D.VIA_D))
        via.SetNet(board.FindNet(v['net']))
        board.Add(via)

    gnd, v33 = board.FindNet('GND'), board.FindNet('+3V3')
    zone(board, gnd, pcbnew.In1_Cu, 'GND plane', thermal=False)
    zone(board, v33, pcbnew.In2_Cu, '+3V3 plane', thermal=False)
    zone(board, gnd, pcbnew.F_Cu, 'GND top')
    zone(board, gnd, pcbnew.B_Cu, 'GND bottom')

    # ── silkscreen ──
    F, B = pcbnew.F_SilkS, pcbnew.B_SilkS
    rows = D.ROWS
    xl = D.BOARD_L - 4.8
    top = ['VREF', 'IO0', 'IO1', 'IO2', 'IO3', 'IO4', 'A0', 'GND']
    bot = ['GND', 'IO5', 'IO6', 'IO7', 'GND', 'A1', 'A2', '5V']
    for y, s in zip(rows, top):
        text(board, s, xl, y, F, 0.8, justify='right')
    for k, (y, s) in enumerate(zip(rows, bot)):
        if k not in (4, 5, 6):          # U14 / D11 sit where these labels would go (the tray carries the legend)
            text(board, s, xl, y, B, 0.8, justify='left')
    text(board, 'BOOT', 7.4, 19.0, F, 0.7, rot=90)
    text(board, 'EXT', 31.0, 3.6, F, 0.7)
    text(board, 'INT', 41.2, 3.0, F, 0.7)
    text(board, 'LA_RP2040 V2', 23.5, 19.6, F, 1.0, thick=0.16)
    text(board, 'eetree.cn', 23.5, 18.1, F, 0.7)
    text(board, 'LA_RP2040 V2.0  2026-11', 15.0, 19.9, B, 0.8)
    text(board, 'IO 1.65-5.5V  A0-A2 0-3.3V', 15.5, 1.2, B, 0.7)
    text(board, 'RUN', 26.6, 1.3, B, 0.7); text(board, 'SWC', 28.9, 1.3, B, 0.7); text(board, 'SWD', 31.2, 1.3, B, 0.7)

    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    pcbnew.SaveBoard(out_pcb, board)
    print(f'finished: {len(routes["tracks"])} track segments, {len(routes["vias"])} vias')


if __name__ == '__main__':
    if sys.argv[1] == 'place':
        place(*sys.argv[2:5])
    else:
        finish(*sys.argv[2:5])
