"""Schematic drawing layout for gen_sch.py: where every symbol sits and how its nets are drawn.

All coordinates are in grid units of 1.27 mm (50 mil), so every pin lands on the routing grid.
The electrical content (parts, pins, nets) stays in design.py; this file only decides the picture:

  POS       ref → (x, y, rotation, mirrored)
  GROUPS    supply rails drawn as wires that end in one power symbol
  SPLIT     nets drawn in several wired pieces that are joined by a net label (connector side)
  CHANNEL   the wire bundle between the RP2040 GPIO pins and the level translators / LEDs / ADC inputs

Everything not listed is wired pin to pin by the schematic router in gen_sch.py.
"""
import design as D

PAPER = 'A2'
POS = {}
TEXT = {}          # ref → ((dx, dy) reference, (dx, dy) value) in mm from the symbol origin; None hides the field
GROUPS = []        # (net, [REF.PIN, ...], (x, y, direction the symbol points: 90 = up, 270 = down))
SPLIT = {}         # net → [([REF.PIN, ...], (x, y, direction) label position or None), ...]
NOTES = []         # (x, y, size mm, text)
FLAGS = {}         # net → (x, y) of a PWR_FLAG


def P(ref, x, y, rot=0, mirror=False):
    POS[ref] = (x, y, rot, mirror)


def caps(refs, x0, y, pitch=6):
    for i, ref in enumerate(refs):
        P(ref, x0 + i * pitch, y)


# ══════════════════════════ USB-C input and power ══════════════════════════
P('J1', 20, 60)
P('R1', 43, 52, 90)
P('R2', 56, 54, 90)
P('U1', 66, 64)
P('F1', 44, 36, 90)
P('C1', 54, 39)
P('U2', 66, 38)
P('C2', 80, 39)
P('R3', 80, 64, 90)
P('R4', 92, 66, 90)
TEXT['R4'] = 'below'
TEXT['U1'] = ((-4.6, -3.4), (-8.5, 6.3))
# the D+/D- traces run through the pads of the ESD array: draw it in-line, both sides named
SPLIT['USB_C_DP'] = [(['J1.A6', 'J1.B6', 'U1.1'], None), (['U1.6', 'R3.1'], None)]
SPLIT['USB_C_DM'] = [(['J1.A7', 'J1.B7', 'U1.3'], None), (['U1.4', 'R4.1'], None)]
GROUPS += [('+5V', ['F1.2', 'C1.1', 'U2.1', 'U2.3'], (50, 36, 90)),
           ('+3V3', ['U2.5', 'C2.1'], (84, 36, 90)),
           ('GND', ['C1.2', 'U2.2', 'C2.2'], (66, 46, 270)),
           ('GND', ['J1.A1', 'J1.S1'], (17, 82, 270))]
TEXT['J1'] = ((-8.0, -19.3), (2.0, -19.3))
NOTES += [(12, 24, 2.5, 'USB-C INPUT / POWER'),
          (12, 27, 1.5, 'CC1 and CC2 each have their own 5.1k Rd, so USB-C to USB-C hosts enable VBUS.')]

# ═════════════════════════════════ RP2040 ══════════════════════════════════
MX, MY = 130, 164
P('U3', MX, MY)
caps(['C4', 'C5', 'C6', 'C7', 'C8', 'C9', 'C12'], 46, 117, 8)
P('R65', 108, 117)
P('C14', 108, 123)
caps(['C10', 'C11', 'C13'], 144, 123, 8)
GROUPS += [('+3V3', ['U3.48', 'U3.1', 'U3.44', 'R65.1', 'C4.1', 'C5.1', 'C6.1', 'C7.1', 'C8.1', 'C9.1', 'C12.1'],
            (42, 114, 90)),
           ('GND', ['C4.2', 'C5.2', 'C6.2', 'C7.2', 'C8.2', 'C9.2', 'C12.2'], (70, 122, 270)),
           ('+1V1', ['U3.45', 'U3.23', 'C10.1', 'C11.1', 'C13.1'], (166, 120, 90)),
           ('GND', ['C10.2', 'C11.2', 'C13.2'], (152, 128, 270))]
P('R9', 94, 143)
P('TP1', 86, 146, 90)
NOTES += [(112, 208, 2.0, 'RP2040 — pin map of the'), (112, 211, 2.0, 'Raspberry Pi Debug Probe firmware')]

# QSPI flash + BOOTSEL
P('U4', 70, 166, 0, True)
P('C17', 52, 157)
TEXT['U4'] = ((6.0, -11.4), (-8.5, 11.8))
P('R8', 84, 157)
P('R7', 96, 157, 180)
P('SW1', 88, 150, 180)
GROUPS += [('+3V3', ['U4.8', 'C17.1', 'R8.1'], (77, 154, 90))]
TEXT['SW1'] = ((0, 3.6), (0, 5.4))

# crystal
P('Y1', 96, 180, 270)
P('R6', 101, 184, 270)
P('C15', 78, 179)
P('C16', 84, 187)
TEXT['Y1'] = ((6.0, -1.0), (7.0, 1.0))
TEXT['R6'] = 'below'

# factory test points
P('TP2', 100, 190, 90)
P('TP3', 100, 192, 90)
for _tp in ('TP1', 'TP2', 'TP3'):
    TEXT[_tp] = ((-7.2, 0), None)

# ══════════ RP2040 GPIO → LEDs / level translators / analog inputs ══════════
CH_X0, CH_PITCH = 170, 2                 # first vertical track of the wire channel, track pitch
XD, XA, XT, XR, XP, XL = 222, 230, 246, 265, 272, 278      # DIR pull, A pull, translator, series R, IO pull, label

LED_Y = [21, 27, 33, 39, 45]
for (_d, _r, _net, _c, _n), _y in zip(D.LEDS, LED_Y):
    P(_r, 241, _y, 90)
    P(_d, 257, _y, 180)
GROUPS += [('GND', [f'{led[0]}.1' for led in D.LEDS], (264, 47, 270))]
NOTES += [(238, 15, 2.5, 'STATUS LEDS (same GPIOs as the official Debug Probe)')]

# one row per translator, in connector order.  (ref, series R, A-side net, DIR net)
CELLS = [('U5', 'R20', 63), ('U6', 'R21', 87), ('U7', 'R22', 111), ('U8', 'R23', 135), ('U9', 'R24', 159),
         ('U10', 'R25', 183), ('U11', 'R26', 207), ('U12', 'R27', 231), ('U13', 'R28', 255)]
ROW = {}
for _u, _r, _y in CELLS:
    P(_u, XT, _y)
    P(_r, XR, _y, 90)
    ROW[_u] = _y


def pull(ref, x, line_y, up, drop=0):
    """Vertical pull resistor on a horizontal line; pin 1 is the rail in design.py for R3x/R5x, else see call."""
    P(ref, x, line_y - 3 - drop if up else line_y + 3 + drop, 0)


def _translator_of(net):
    for c in D.COMPONENTS:
        if c['value'] == '74LVC1T45' and net in (c['pins']['3'], c['pins']['5'], c['pins']['4']):
            return c
    raise KeyError(net)


# DIR default resistors (pin 1 = rail): pull-ups sit above the A line and cross it, pull-downs hang below DIR
for _ref, _net, _rail in D.DIRS:
    _y = ROW[_translator_of(_net)['ref']] + 4
    if _rail == 'GND':
        P(_ref, XD, _y + 3, 180)
    else:
        P(_ref, XD, _y - 9, 0)
# A-side idle levels
P('R40', XA - 4, ROW['U5'] + 9)              # IO0_A pull-down: pin 1 = IO0_A (top), crosses the DIR line
P('R41', XA, ROW['U6'] - 3)
P('R42', XA, ROW['U7'] - 3)
P('R43', XA, ROW['U9'] - 3)
P('R44', XA, ROW['U10'] - 3)
# target-side idle levels (pin 1 = rail) and the label that leads to the connector
_series = {'IO0': ['R20'], 'IO1': ['R21', 'R22'], 'IO2': ['R23'], 'IO3': ['R24'], 'IO4': ['R25'], 'IO5': ['R26'],
           'IO6': ['R27'], 'IO7': ['R28']}
for _ref, _net, _rail in D.PULLS:
    _y = ROW[_translator_of(f'{_net}_B' if _net != 'IO1' else 'IO1_BO')['ref']]
    if _rail == 'GND':
        P(_ref, XP, _y + 3, 180)
    else:
        P(_ref, XP, _y - 3, 0)
    SPLIT[_net] = [([f'{r}.2' for r in _series[_net]] + [f'{_ref}.2'], (XL, _y, 0))]
NOTES += [(270, 21, 2.5, 'LEVEL-SHIFTED IO0..IO7'),
          (270, 24, 1.5, 'A = 3V3 side, B = VIO side'), (270, 26, 1.5, 'DIR high = probe drives the pin'),
          (XL + 6, 64, 1.3, 'SWCLK (GP12)'), (XL + 6, 88, 1.3, 'SWDIO: out GP14 through 470R, in GP13'),
          (XL + 6, 136, 1.3, 'nRESET (GP20)'), (XL + 6, 160, 1.3, 'UART TX (GP4)'),
          (XL + 6, 184, 1.3, 'UART RX (GP5)'), (XL + 6, 208, 1.3, 'GP23'), (XL + 6, 232, 1.3, 'GP24'),
          (XL + 6, 256, 1.3, 'GP25   IO5..IO7 share one direction line (GP10)')]

# analog inputs: series resistor + clamp pair, and the VIO sense divider
ADC_Y = [275, 279, 283]
for (_r, _d, _ain, _adc, _rp, _dp), _y, _x in zip(D.ADC, ADC_Y, (226, 242, 258)):
    P(_r, 266, _y, 270)
    SPLIT[_ain] = []
    P(_d, _x, 299, 90)
    TEXT[_d] = ((-6.0, -1.0), (-7.2, 1.0))
P('R60', 280, 284)
P('R61', 280, 290)
P('C31', 288, 290)
NOTES += [(238, 270, 2.5, 'ANALOG INPUTS (clamped to 0..3.3 V) / VIO SENSE')]

# nets that run in the channel, and the pins the channel reaches with a straight horizontal wire
CHANNEL_NETS = ['LED_USB', 'LED_RX', 'LED_TX', 'LED_DAP', 'LED_ACT',
                'IO0_A', 'DIR0', 'SWDIO_O', 'DIR1', 'IO1_A', 'IO2_A', 'DIR2', 'IO3_A', 'DIR3', 'IO4_A', 'DIR4',
                'IO5_A', 'IO6_A', 'IO7_A', 'DIR567', 'ADC0', 'ADC1', 'ADC2', 'VIO_SENSE']
CHANNEL_EXTRA = {'VIO_SENSE': ['R60.2']}        # 2-pin parts entered from the side

# ═══════════════ target connector, protection, VIO, +5 V out ═══════════════
X3 = 336
# VIO source: 3V3 → Schottky → polyfuse → INT/EXT switch → VIO rail with the translator decoupling
P('D6', X3, 40, 180)
P('F2', X3 + 13, 40, 90)
P('SW2', X3 + 28, 42, 0, True)
P('D7', X3 + 40, 45, 270)
caps(['C30', 'C25', 'C26', 'C27', 'C28', 'C29'], X3 + 48, 45, 8)
GROUPS += [('+3V3', ['D6.2'], (X3 - 8, 40, 90)),
           ('VIO', ['SW2.2', 'D7.1', 'C30.1', 'C25.1', 'C26.1', 'C27.1', 'C28.1', 'C29.1'], (X3 + 36, 42, 90)),
           ('GND', ['D7.2', 'C30.2', 'C25.2', 'C26.2', 'C27.2', 'C28.2', 'C29.2'], (X3 + 64, 50, 270))]
TEXT['SW2'] = ((0, -6.2), (0, 6.6))
TEXT['D7'] = ((-4.2, -1.0), (-3.6, 1.0))
NOTES += [(X3 - 6, 30, 2.5, 'VIO (target reference): INT = 3V3 from the probe, EXT = VTREF from the target')]

caps(['C20', 'C21', 'C22', 'C23', 'C24'], X3, 73, 8)
GROUPS += [('+3V3', ['C20.1', 'C21.1', 'C22.1', 'C23.1', 'C24.1'], (X3 - 4, 70, 90)),
           ('GND', ['C20.2', 'C21.2', 'C22.2', 'C23.2', 'C24.2'], (X3 + 16, 78, 270))]
NOTES += [(X3 - 6, 62, 2.5, 'TRANSLATOR 3V3-SIDE DECOUPLING')]

# connector
P('J2', X3 + 40, 130)
GROUPS += [('VIO', ['J2.1'], (X3 + 30, 122, 90)),
           ('GND', ['J2.15'], (X3 + 30, 140, 270)),
           ('GND', ['J2.2', 'J2.10'], (X3 + 60, 134, 270))]
TEXT['J2'] = ((1.6, -12.4), (1.6, 12.8))
NOTES += [(X3 - 6, 112, 2.5, 'TARGET CONNECTOR (2x8, 2.54 mm)')]

# ESD arrays
P('U14', X3 + 20, 172)
P('U15', X3 + 60, 172)
TEXT['U14'] = TEXT['U15'] = ((-10.5, -11.4), (9.0, 11.6))
NOTES += [(X3 - 6, 154, 2.5, 'TARGET-SIDE ESD')]

# +5 V to the target
P('D8', X3, 210, 180)
P('F3', X3 + 13, 210, 90)
P('D9', X3 + 24, 213, 270)
GROUPS += [('+5V', ['D8.2'], (X3 - 8, 210, 90))]
SPLIT['5V_OUT'] = [(['F3.2', 'D9.1'], (X3 + 32, 210, 0))]
TEXT['D9'] = ((-4.2, -1.0), (-3.6, 1.0))
NOTES += [(X3 - 6, 200, 2.5, '+5 V TO THE TARGET (USB VBUS through Schottky + polyfuse)')]

P('H1', X3, 240)
P('H2', X3 + 12, 240)
FLAGS.update({'GND': (X3 + 30, 240), '+5V': (X3 + 38, 240), 'VIO': (X3 + 46, 240), 'VBUS': (X3 + 54, 240),
              'ADC_AVDD': (X3 + 62, 240)})
NOTES += [(X3 - 6, 230, 2.5, 'MOUNTING HOLES / ERC POWER FLAGS')]
