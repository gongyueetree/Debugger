#!/usr/bin/env python3
"""Parametric two-piece enclosure for the LA_RP2040 V2 probe (CadQuery).

usage: python3 enclosure.py [output-dir]

Coordinates are the PCB's: x along the board (USB-C at x=0, target header at
x=BOARD_L), y across, z=0 at the PCB bottom face, PCB top face at z=PCB_T.
Outputs STEP + STL for the tray and the lid, a STEP assembly with a PCB
stand-in, and SVG views.
"""
import os
import sys

import cadquery as cq

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'gen'))
import design as D

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))

# ── board facts (from design.py) ──
L, W, PCB_T = D.BOARD_L, D.BOARD_W, 1.6
HOLES = [c['pcb'][:2] for c in D.COMPONENTS if c['ref'] in ('H1', 'H2')]
LEDS = [(D.LED_X0 + 2.5 * i, 19.2, lab) for i, (_, _, _, _, lab) in enumerate(D.LEDS)]
BOOT = next(c['pcb'][:2] for c in D.COMPONENTS if c['ref'] == 'SW1')
SLIDE_X = next(c['pcb'][0] for c in D.COMPONENTS if c['ref'] == 'SW2')
USB_Y = next(c['pcb'][1] for c in D.COMPONENTS if c['ref'] == 'J1')

# ── enclosure parameters (mm) ──
GAP = 0.25            # PCB edge to wall
WALL = 1.6
USB_WALL = 1.2        # thinner so the USB-C plug seats fully
FLOOR = 1.4
ROOF = 1.4
Z_BOT = -2.1          # cavity bottom: header body reaches -1.74
Z_TOP = 5.2           # cavity top: USB-C shell reaches 4.86
LAP_Z = 3.1           # top of the tray's outer lip
LIP_T = 0.8           # lap-joint lip thickness
LIP_CLEAR = 0.12
R_OUT = 2.2           # outer vertical corner radius
BOSS_D = 5.2
SCREW_PILOT = 1.7     # M2 self-tapping screw (M2x8)
SCREW_CLEAR = 2.3
HEAD_D, HEAD_H = 4.0, 1.5

X0, X1 = -0.3 - USB_WALL, L + GAP + WALL          # outer x extents
Y0, Y1 = -GAP - WALL, W + GAP + WALL
ZF, ZR = Z_BOT - FLOOR, Z_TOP + ROOF              # outer z extents
XI0, XI1 = -0.3, L + GAP                          # inner x extents
YI0, YI1 = -GAP, W + GAP

HDR_Y0, HDR_Y1 = W / 2 - 10.4, W / 2 + 10.4       # 2x8 header body + clearance
HDR_Z0, HDR_Z1 = PCB_T / 2 - 2.75, PCB_T / 2 + 2.75
USB_HALF_W = 4.75
USB_Z1 = PCB_T + 3.26 + 0.2


def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane('XY').box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def outer(z0, z1):
    b = box(X0, X1, Y0, Y1, z0, z1)
    return b.edges('|Z').fillet(R_OUT)


def make_tray():
    # shell up to the PCB top face, plus an outer lip up to LAP_Z (lap joint with the lid)
    body = outer(ZF, LAP_Z)
    body = body.cut(box(XI0, XI1, YI0, YI1, Z_BOT, LAP_Z + 1))                         # cavity
    body = body.cut(box(XI0 - LIP_T, XI1 + LIP_T, YI0 - LIP_T, YI1 + LIP_T, PCB_T, LAP_Z + 1))   # seat for the lid lip
    body = body.edges('<Z').fillet(0.8)
    # PCB support ledges along the long walls (clear of bottom-side parts)
    for (xa, xb) in ((8, 14), (26, 32), (46, 52)):
        body = body.union(box(xa, xb, YI0, 0.75, Z_BOT, 0))
    for (xa, xb) in ((8, 14), (26, 32), (51.4, 53.0)):
        body = body.union(box(xa, xb, W - 0.75, YI1, Z_BOT, 0))
    # screw bosses under the mounting holes
    for (hx, hy) in HOLES:
        boss = cq.Workplane('XY').circle(BOSS_D / 2).extrude(-Z_BOT).translate((hx, hy, Z_BOT))
        web = box(XI0, hx, hy - 1.0, hy + 1.0, Z_BOT, 0)
        body = body.union(boss).union(web)
        body = body.cut(cq.Workplane('XY').circle(SCREW_PILOT / 2).extrude(-Z_BOT + FLOOR - 0.5)
                        .translate((hx, hy, Z_BOT - FLOOR + 0.5)))
    # header opening (lower half) and USB-C notch through the lip
    body = body.cut(box(XI1 - 0.1, X1 + 1, HDR_Y0, HDR_Y1, HDR_Z0, LAP_Z + 1))
    body = body.cut(box(X0 - 1, XI0 + 0.1, USB_Y - USB_HALF_W, USB_Y + USB_HALF_W, PCB_T, LAP_Z + 1))
    # slide-switch slot and finger scoop
    body = body.cut(box(SLIDE_X - 2.9, SLIDE_X + 2.9, Y0 - 1, YI0 + 0.1, PCB_T, LAP_Z + 1))
    body = body.cut(box(SLIDE_X - 4.5, SLIDE_X + 4.5, Y0 - 1, Y0 + 0.9, PCB_T - 1.2, LAP_Z + 1))
    # snap grooves near the header end (lid bumps click in)
    for y in (YI0 - LIP_T, YI1 + LIP_T):
        body = body.cut(cq.Workplane('YZ').circle(0.4).extrude(4.4).translate((48.8, y, 2.45)))
    # bottom-side pin legend
    try:
        for y, s in zip(D.ROWS, ('GND', 'IO5', 'IO6', 'IO7', 'GND', 'A1', 'A2', '5V')):
            t = (cq.Workplane('XY').text(s, 1.5, 0.35, halign='right', valign='center', kind='bold')
                 .mirror('YZ').translate((L - 5.0 - 6.0, y, ZF - 0.01)))
            body = body.cut(t.translate((0, 0, 0.0)))
    except Exception as e:                                                            # fonts are optional
        print('tray legend skipped:', e)
    return body


def make_lid():
    body = outer(LAP_Z, ZR)
    body = body.cut(box(XI0, XI1, YI0, YI1, LAP_Z - 1, Z_TOP))                         # cavity
    body = body.edges('>Z').fillet(0.8)
    # lap-joint lip reaching down inside the tray's outer lip, stopping 0.2 above the PCB
    lip_out = box(XI0 - LIP_T + LIP_CLEAR, XI1 + LIP_T - LIP_CLEAR, YI0 - LIP_T + LIP_CLEAR, YI1 + LIP_T - LIP_CLEAR,
                  PCB_T + 0.2, LAP_Z)
    lip = lip_out.cut(box(XI0, XI1, YI0, YI1, PCB_T, LAP_Z + 1))
    body = body.union(lip)
    # snap bumps
    for y, sgn in ((YI0 - LIP_T + LIP_CLEAR, 1), (YI1 + LIP_T - LIP_CLEAR, -1)):
        bump = cq.Workplane('YZ').circle(0.35).extrude(4.0).translate((49.0, y, 2.45))
        body = body.union(bump.intersect(box(48, 54, y - 0.4 if sgn > 0 else y, y if sgn > 0 else y + 0.4, 1.9, 3.0)))
    # screw posts clamp the PCB at the USB end
    for (hx, hy) in HOLES:
        post = cq.Workplane('XY').circle(BOSS_D / 2).extrude(Z_TOP - PCB_T).translate((hx, hy, PCB_T))
        body = body.union(post)
        body = body.cut(cq.Workplane('XY').circle(SCREW_CLEAR / 2).extrude(ZR - PCB_T + 1).translate((hx, hy, PCB_T - 0.5)))
        body = body.cut(cq.Workplane('XY').circle(HEAD_D / 2).extrude(HEAD_H + 1).translate((hx, hy, ZR - HEAD_H)))
    # hold-down pins at the header end
    for (px, py) in ((51.6, 0.75), (51.6, W - 0.75)):
        body = body.union(cq.Workplane('XY').circle(0.6).extrude(Z_TOP - PCB_T).translate((px, py, PCB_T)))
    # openings: USB-C, header (upper half), slide switch
    body = body.cut(box(X0 - 1, XI0 + 0.1, USB_Y - USB_HALF_W, USB_Y + USB_HALF_W, PCB_T - 1, USB_Z1))
    body = body.cut(box(XI1 - 1.0, X1 + 1, HDR_Y0, HDR_Y1, PCB_T - 1, HDR_Z1))
    body = body.cut(box(SLIDE_X - 2.9, SLIDE_X + 2.9, Y0 - 1, YI0 + 0.1, PCB_T - 1, 3.5))
    body = body.cut(box(SLIDE_X - 4.5, SLIDE_X + 4.5, Y0 - 1, Y0 + 0.9, PCB_T - 1, 4.4))
    # LED windows and BOOT pin-hole
    for (lx, ly, _) in LEDS:
        body = body.cut(cq.Workplane('XY').circle(0.7).extrude(ROOF + 2).translate((lx, ly, Z_TOP - 1)))
    body = body.cut(cq.Workplane('XY').circle(0.9).extrude(ROOF + 2).translate((BOOT[0], BOOT[1], Z_TOP - 1)))
    # legends (engraved 0.35 mm)
    try:
        def engrave(s, x, y, size, rot=0, halign='center'):
            nonlocal body
            t = cq.Workplane('XY').text(s, size, 0.5, halign=halign, valign='center', kind='bold')
            if rot:
                t = t.rotate((0, 0, 0), (0, 0, 1), rot)
            body = body.cut(t.translate((x, y, ZR - 0.35)))
        for y, (s, fn) in zip(D.ROWS, (('VREF', ''), ('IO0', 'SWCLK'), ('IO1', 'SWDIO'), ('IO2', 'nRST'),
                                       ('IO3', 'TX'), ('IO4', 'RX'), ('A0', ''), ('GND', ''))):
            engrave(s, L - 0.6, y, 1.5, halign='right')
            if fn:
                engrave(fn, L - 6.4, y, 1.1, halign='right')
        for (lx, ly, lab) in LEDS:
            engrave(lab, lx, ly - 1.5, 1.2, rot=90, halign='left')
        engrave('BOOT', BOOT[0], BOOT[1] - 2.2, 1.2)
        engrave('LA_RP2040', 27.0, 7.2, 3.2)
        engrave('DEBUG PROBE  V2', 27.0, 11.2, 1.6)
        engrave('INT VIO EXT', SLIDE_X, 2.0, 1.2)
    except Exception as e:
        print('lid legend skipped:', e)
    return body


def make_pcb_standin():
    pcb = box(0, L, 0, W, 0, PCB_T).edges('|Z').fillet(D.CORNER_R)
    for (hx, hy) in HOLES:
        pcb = pcb.cut(cq.Workplane('XY').circle(1.1).extrude(PCB_T).translate((hx, hy, 0)))
    usb = box(-1.0, 6.3, USB_Y - 4.47, USB_Y + 4.47, PCB_T, PCB_T + 3.26)
    hdr = box(L, L + 2.5, W / 2 - 10.16, W / 2 + 10.16, PCB_T / 2 - 2.54, PCB_T / 2 + 2.54)
    pins = None
    for y in D.ROWS:
        for z in (PCB_T / 2 - 1.27, PCB_T / 2 + 1.27):
            p = box(L - 3.0, L + 8.5, y - 0.32, y + 0.32, z - 0.32, z + 0.32)
            pins = p if pins is None else pins.union(p)
    sw = box(SLIDE_X - 3.35, SLIDE_X + 3.35, 0.4, 3.1, PCB_T, PCB_T + 1.4).union(
        box(SLIDE_X + 0.2, SLIDE_X + 1.5, -1.15, 0.4, PCB_T + 0.3, PCB_T + 1.1))
    mcu = box(D.MX - 3.5, D.MX + 3.5, D.MY - 3.5, D.MY + 3.5, PCB_T, PCB_T + 0.9)
    return pcb, usb.union(hdr).union(pins).union(sw).union(mcu)


def main():
    os.makedirs(OUT, exist_ok=True)
    tray, lid = make_tray(), make_lid()
    pcb, parts = make_pcb_standin()
    clash = lid.intersect(tray).val().Volume()
    clash_pcb = (lid.union(tray)).intersect(pcb.union(parts)).val().Volume()
    print(f'outer size: {X1 - X0:.2f} x {Y1 - Y0:.2f} x {ZR - ZF:.2f} mm')
    print(f'tray {tray.val().Volume() / 1000:.2f} cm3, lid {lid.val().Volume() / 1000:.2f} cm3')
    print(f'interference lid/tray: {clash:.3f} mm3, enclosure/PCB stand-in: {clash_pcb:.3f} mm3')
    for name, obj in (('tray', tray), ('lid', lid)):
        cq.exporters.export(obj, os.path.join(OUT, f'LA_RP2040_V2_{name}.step'))
        cq.exporters.export(obj, os.path.join(OUT, f'LA_RP2040_V2_{name}.stl'), tolerance=0.02, angularTolerance=0.2)
    if os.environ.get('STANDIN_STL'):          # preview meshes for the renderer, not deliverables
        cq.exporters.export(pcb, os.path.join(OUT, '_pcb.stl'), tolerance=0.02, angularTolerance=0.3)
        cq.exporters.export(parts, os.path.join(OUT, '_parts.stl'), tolerance=0.02, angularTolerance=0.3)
    asm = cq.Assembly(name='LA_RP2040_V2_enclosure')
    asm.add(tray, name='tray', color=cq.Color(0.15, 0.17, 0.2))
    asm.add(lid, name='lid', color=cq.Color(0.15, 0.17, 0.2))
    asm.add(pcb, name='pcb', color=cq.Color(0.05, 0.35, 0.15))
    asm.add(parts, name='parts', color=cq.Color(0.7, 0.7, 0.72))
    asm.save(os.path.join(OUT, 'LA_RP2040_V2_assembly.step'))
    # CadQuery's SVG projectionDir is the viewing direction (from the eye into the model)
    views = {'iso_top': (1.0, 1.4, -1.1), 'iso_bottom': (-1.0, 1.4, 1.1), 'top': (0, 0, -1), 'usb_end': (1, 0, 0),
             'header_end': (-1, 0, 0), 'side': (0, 1, 0)}
    closed = tray.union(lid).union(parts)
    exploded = tray.union(lid.translate((0, 0, 14))).union(pcb.union(parts).translate((0, 0, 7)))
    for vname, d in views.items():
        cq.exporters.export(closed, os.path.join(OUT, f'view_{vname}.svg'),
                            opt=dict(width=1100, height=700, marginLeft=40, marginTop=40, showAxes=False,
                                     projectionDir=d, strokeWidth=0.25, showHidden=False))
    cq.exporters.export(exploded, os.path.join(OUT, 'view_exploded.svg'),
                        opt=dict(width=1100, height=900, marginLeft=40, marginTop=40, showAxes=False,
                                 projectionDir=(1.0, 1.4, -0.9), strokeWidth=0.25, showHidden=False))


if __name__ == '__main__':
    main()
