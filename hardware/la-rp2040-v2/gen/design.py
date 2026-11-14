"""LA_RP2040 V2 — single source of truth for schematic and PCB generation.

Every component is declared once with its symbol, footprint, pin→net map,
PCB placement (board-local mm, origin = top-left board corner, top view)
and schematic placement.  gen_sch.py and gen_pcb.py both read this file, so
schematic and layout cannot drift apart.
"""

PROJECT = 'LA_RP2040_V2'
TITLE = 'LA_RP2040 V2 — Multi-function Debug Probe'
REV = 'V2.0'
DATE = '2026-11-12'
COMPANY = 'EETree Info & Tech'

BOARD_L = 58.0          # mm, USB-C at x=0, target header at x=BOARD_L
BOARD_W = 21.0
BOARD_ORIGIN = (100.0, 100.0)   # KiCad page position of the board's top-left corner
CORNER_R = 1.5

LIB = 'LA_RP2040_V2'    # project-local footprint library (J2 edge header)

COMPONENTS = []


def comp(ref, sym, value, fp, pins, pcb, sch, mpn='', desc=''):
    COMPONENTS.append(dict(ref=ref, sym=sym, value=value, fp=fp, pins={str(k): v for k, v in pins.items()},
                           pcb=pcb, sch=sch, mpn=mpn, desc=desc))


R0402 = 'Resistor_SMD:R_0402_1005Metric'
C0402 = 'Capacitor_SMD:C_0402_1005Metric'
C0603 = 'Capacitor_SMD:C_0603_1608Metric'
LED0603 = 'LED_SMD:LED_0603_1608Metric'
SOD323 = 'Diode_SMD:D_SOD-323'
SC70_6 = 'Package_TO_SOT_SMD:SOT-363_SC-70-6'


def R(ref, value, a, b, pcb, sch):
    comp(ref, 'Device:R', value, R0402, {1: a, 2: b}, pcb, sch + (90,), mpn=f'0402 {value} 1%')


def C(ref, value, a, b, pcb, sch, fp=C0402):
    size = '0603' if fp == C0603 else '0402'
    comp(ref, 'Device:C', value, fp, {1: a, 2: b}, pcb, sch + (90,), mpn=f'{size} {value} X5R/X7R (15pF: C0G)')


# The `sch` argument of every part below is no longer used: the drawing positions live in sch_layout.py.
def col(x, y0, pitch=7.62):
    """Yield successive positions down a column (legacy schematic argument)."""
    i = 0
    while True:
        yield (x, y0 + i * pitch)
        i += 1


# ══════════════════════════ USB-C input and power ══════════════════════════
comp('J1', 'Connector:USB_C_Receptacle_USB2.0_16P', 'USB-C 16P', 'Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12',
     {'A1': 'GND', 'A12': 'GND', 'B1': 'GND', 'B12': 'GND', 'S1': 'GND',
      'A4': 'VBUS', 'A9': 'VBUS', 'B4': 'VBUS', 'B9': 'VBUS',
      'A5': 'CC1', 'B5': 'CC2',
      'A6': 'USB_C_DP', 'B6': 'USB_C_DP', 'A7': 'USB_C_DM', 'B7': 'USB_C_DM',
      'A8': None, 'B8': None},
     pcb=(2.65, 10.5, 270, 'F'), sch=(30.48, 53.34, 0), mpn='HRO TYPE-C-31-M-12',
     desc='USB 2.0 Type-C receptacle, 16 pin')

p = col(86.36, 35.56)
R('R1', '5.1k', 'CC1', 'GND', (9.0, 7.6, 0, 'F'), next(p))
R('R2', '5.1k', 'CC2', 'GND', (9.0, 13.4, 0, 'F'), next(p))
comp('F1', 'Device:Polyfuse', '500mA', 'Fuse:Fuse_0805_2012Metric', {1: 'VBUS', 2: '+5V'},
     (9.7, 4.6, 0, 'F'), next(p) + (90,), mpn='0805 PTC 0.5A hold / 6V (e.g. SMD0805P050TF)',
     desc='Resettable fuse on USB input')
R('R3', '27', 'USB_C_DP', 'USB_DP', (14.2, 10.4, 0, 'F'), next(p))
R('R4', '27', 'USB_C_DM', 'USB_DM', (14.2, 11.5, 0, 'F'), next(p))

comp('U1', 'Power_Protection:USBLC6-2SC6', 'USBLC6-2SC6', 'Package_TO_SOT_SMD:SOT-23-6',
     {1: 'USB_C_DP', 6: 'USB_C_DP', 3: 'USB_C_DM', 4: 'USB_C_DM', 2: 'GND', 5: 'VBUS'},
     (10.4, 10.5, 0, 'F'), (127.0, 43.18, 0), mpn='USBLC6-2SC6', desc='USB D+/D-/VBUS ESD protection')
comp('U2', 'Regulator_Linear:AP2112K-3.3', 'AP2112K-3.3', 'Package_TO_SOT_SMD:SOT-23-5',
     {1: '+5V', 3: '+5V', 2: 'GND', 4: None, 5: '+3V3'},
     (13.6, 3.0, 0, 'F'), (127.0, 71.12, 0), mpn='AP2112K-3.3TRG1', desc='600 mA LDO, same part as the official Debug Probe')
p = col(162.56, 35.56)
C('C1', '10uF', '+5V', 'GND', (9.2, 2.2, 0, 'F'), next(p), fp=C0603)
C('C2', '10uF', '+3V3', 'GND', (17.3, 2.2, 0, 'F'), next(p), fp=C0603)

# ═════════════════════════════════ RP2040 ══════════════════════════════════
MX, MY = 21.0, 9.6     # RP2040 centre on the PCB (on the 0.1 mm routing grid)
comp('U3', 'MCU_RaspberryPi:RP2040', 'RP2040', 'Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm',
     {1: '+3V3', 10: '+3V3', 22: '+3V3', 33: '+3V3', 42: '+3V3', 49: '+3V3', 44: '+3V3', 48: '+3V3',
      43: 'ADC_AVDD', 45: '+1V1', 23: '+1V1', 50: '+1V1', 57: 'GND', 19: 'GND',
      # bottom side of the QFN as placed: only the pins the official firmware fixes, plus two DIR lines
      2: None, 3: None, 4: 'LED_USB', 5: None, 6: 'IO3_A', 7: 'IO4_A', 8: None, 9: 'LED_RX',
      11: 'LED_TX', 12: 'DIR4', 13: 'DIR567', 14: None,
      15: 'IO0_A', 16: 'IO1_A', 17: 'SWDIO_O', 18: 'LED_DAP',
      20: 'XIN', 21: 'XOUT', 24: 'MCU_SWCLK', 25: 'MCU_SWDIO', 26: 'RUN',
      27: 'LED_ACT', 28: None,
      29: 'DIR0', 30: 'DIR1', 31: 'IO2_A', 32: 'DIR2', 34: 'DIR3', 35: 'IO5_A', 36: 'IO6_A', 37: 'IO7_A',
      38: 'ADC0', 39: 'ADC1', 40: 'ADC2', 41: 'VIO_SENSE',
      46: 'USB_DM', 47: 'USB_DP',
      51: 'QSPI_SD3', 52: 'QSPI_SCLK', 53: 'QSPI_SD0', 54: 'QSPI_SD2', 55: 'QSPI_SD1', 56: 'QSPI_SS'},
     (MX, MY, 90, 'F'), (213.36, 114.3, 0), mpn='RP2040', desc='Dual Cortex-M0+ MCU')

# decoupling (bottom side, under/around the QFN)
p = col(104.14, 104.14)
C('C4', '100nF', '+3V3', 'GND', (16.8, 13.6, 0, 'B'), next(p))
C('C5', '100nF', '+3V3', 'GND', (22.0, 14.5, 0, 'B'), next(p))
C('C6', '100nF', '+3V3', 'GND', (22.0, 10.0, 180, 'B'), next(p))
C('C7', '100nF', '+3V3', 'GND', (22.0, 4.9, 0, 'B'), next(p))
C('C8', '100nF', '+3V3', 'GND', (16.6, 5.7, 0, 'B'), next(p))
C('C9', '100nF', '+3V3', 'GND', (17.3, 9.2, 180, 'B'), next(p))
C('C12', '1uF', '+3V3', 'GND', (17.3, 7.2, 180, 'B'), next(p))
p = col(142.24, 104.14)
C('C10', '100nF', '+1V1', 'GND', (22.0, 8.9, 180, 'B'), next(p))
C('C11', '100nF', '+1V1', 'GND', (20.0, 10.0, 0, 'B'), next(p))
C('C13', '1uF', '+1V1', 'GND', (20.0, 8.0, 0, 'B'), next(p))
C('C14', '1uF', 'ADC_AVDD', 'GND', (15.6, 6.6, 0, 'F'), next(p))
R('R65', '10', '+3V3', 'ADC_AVDD', (15.6, 5.5, 0, 'F'), next(p))
R('R9', '10k', '+3V3', 'RUN', (26.3, 7.5, 0, 'B'), next(p))

# crystal
comp('Y1', 'Device:Crystal_GND24', '12MHz', 'Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm',
     {1: 'XIN', 3: 'XOUT_X', 2: 'GND', 4: 'GND'}, (29.7, 10.4, 0, 'B'), (40.64, 152.4, 0),
     mpn='12 MHz 3225 CL=10..12pF (e.g. ABM8-272-T3)', desc='12 MHz crystal')
p = col(86.36, 147.32)
C('C15', '15pF', 'XIN', 'GND', (29.2, 13.1, 0, 'B'), next(p))
C('C16', '15pF', 'XOUT_X', 'GND', (30.6, 7.7, 0, 'B'), next(p))
R('R6', '1k', 'XOUT', 'XOUT_X', (28.5, 7.7, 0, 'B'), next(p))

# QSPI flash + BOOTSEL
comp('U4', 'Memory_Flash:W25Q32JVSS', 'W25Q16JVUXIQ', 'Package_SON:Winbond_USON-8-1EP_3x2mm_P0.5mm_EP0.2x1.6mm',
     {1: 'QSPI_SS', 2: 'QSPI_SD1', 3: 'QSPI_SD2', 4: 'GND', 5: 'QSPI_SD0', 6: 'QSPI_SCLK', 7: 'QSPI_SD3', 8: '+3V3'},
     (13.6, 15.4, 0, 'F'), (45.72, 114.3, 0), mpn='W25Q16JVUXIQ',
     desc='16 Mbit QSPI flash, same part as the official Debug Probe')
p = col(86.36, 104.14)
C('C17', '100nF', '+3V3', 'GND', (14.6, 17.4, 0, 'F'), next(p))
R('R7', '1k', 'QSPI_SS', 'BOOT', (10.3, 15.2, 0, 'F'), next(p))
R('R8', '10k', '+3V3', 'QSPI_SS', (10.3, 16.3, 0, 'F'), next(p))
comp('SW1', 'Switch:SW_Push', 'BOOT', 'Button_Switch_SMD:SW_SPST_B3U-1000P', {1: 'BOOT', 2: 'GND'},
     (11.0, 19.0, 0, 'F'), (45.72, 176.53, 0), mpn='Omron B3U-1000P', desc='BOOTSEL button')

# factory test points (bottom)
for i, (ref, net, y) in enumerate((('TP1', 'RUN', 26.6), ('TP2', 'MCU_SWCLK', 28.9), ('TP3', 'MCU_SWDIO', 31.2))):
    comp(ref, 'Connector:TestPoint', net.replace('MCU_', ''), 'TestPoint:TestPoint_Pad_D1.0mm', {1: net},
         (y, 3.0, 0, 'B'), (124.46 + i * 12.7, 162.56, 0), desc='Factory test pad')

LED_X0 = 31.0
# status LEDs — same GPIOs as the official Debug Probe
LEDS = (('D1', 'R10', 'LED_USB', 'Red', 'USB'), ('D2', 'R11', 'LED_RX', 'Green', 'RX'),
        ('D3', 'R12', 'LED_TX', 'Yellow', 'TX'), ('D4', 'R13', 'LED_DAP', 'Green', 'DAP'),
        ('D5', 'R14', 'LED_ACT', 'Yellow', 'RUN'))
for i, (d, r, net, colour, _) in enumerate(LEDS):
    x = LED_X0 + 2.5 * i
    R(r, '470', net, f'{net}_A', (x, 16.6, 90, 'F'), (33.02, 195.58 + 7.62 * i))
    comp(d, 'Device:LED', colour, LED0603, {2: f'{net}_A', 1: 'GND'}, (x, 19.2, 90, 'F'),
         (73.66, 195.58 + 7.62 * i, 0), mpn=f'0603 LED {colour}', desc='Status LED')

# ══════════════════ level-shifted, direction-controlled IO ══════════════════
# IOn: connector pin ─ TVS ─ series R ─ B|74LVC1T45|A ─ RP2040.  VCCB = VIO.
XT = 45.0               # top-side translator column
ROWS = [1.61 + 2.54 * k for k in range(8)]      # J2 pad rows (y)
CY = [3.6 + 3.3 * k for k in range(5)]          # top-side translator rows
BY = [4.4 + 3.3 * k for k in range(4)]          # bottom-side translator rows
XB = 39.0                                       # bottom-side translator column


def lvc(ref, a, b, d, pcb, sch):
    comp(ref, 'Logic_LevelTranslator:SN74LVC1T45DCK', '74LVC1T45', SC70_6,
         {1: '+3V3', 2: 'GND', 3: a, 4: b, 5: d, 6: 'VIO'}, pcb, sch + (0,), mpn='SN74LVC1T45DCKR',
         desc='1-bit dual-supply transceiver, 1.65–5.5 V, Ioff')


SX = (281.94, 327.66, 373.38)
SY = (45.72, 86.36, 127.0)
lvc('U5', 'IO0_A', 'IO0_B', 'DIR0', (XT, CY[0], 0, 'F'), (SX[0], SY[0]))
lvc('U6', 'SWDIO_O', 'IO1_BO', 'DIR1', (XT, CY[1], 0, 'F'), (SX[1], SY[0]))
lvc('U7', 'IO1_A', 'IO1_BI', 'GND', (XB, BY[3], 0, 'B'), (SX[2], SY[0]))
lvc('U8', 'IO2_A', 'IO2_B', 'DIR2', (XT, CY[2], 0, 'F'), (SX[0], SY[1]))
lvc('U9', 'IO3_A', 'IO3_B', 'DIR3', (XT, CY[3], 0, 'F'), (SX[1], SY[1]))
lvc('U10', 'IO4_A', 'IO4_B', 'DIR4', (XT, CY[4], 0, 'F'), (SX[2], SY[1]))
lvc('U11', 'IO5_A', 'IO5_B', 'DIR567', (XB, BY[0], 0, 'B'), (SX[0], SY[2]))
lvc('U12', 'IO6_A', 'IO6_B', 'DIR567', (XB, BY[1], 0, 'B'), (SX[1], SY[2]))
lvc('U13', 'IO7_A', 'IO7_B', 'DIR567', (XB, BY[2], 0, 'B'), (SX[2], SY[2]))

PX = (271.78, 309.88, 347.98, 386.08)
p = col(PX[0], 154.94)
# series resistors (470R on the SWDIO driver: lets the stock firmware share the line without a DIR signal)
R('R20', '100', 'IO0_B', 'IO0', (48.6, CY[0] + 0.65, 0, 'F'), next(p))
R('R21', '470', 'IO1_BO', 'IO1', (48.6, CY[1] + 0.65, 0, 'F'), next(p))
R('R22', '100', 'IO1_BI', 'IO1', (48.6, CY[1] + 1.95, 0, 'F'), next(p))
R('R23', '100', 'IO2_B', 'IO2', (48.6, CY[2] + 0.65, 0, 'F'), next(p))
R('R24', '100', 'IO3_B', 'IO3', (48.6, CY[3] + 0.65, 0, 'F'), next(p))
R('R25', '100', 'IO4_B', 'IO4', (48.6, CY[4] + 0.65, 0, 'F'), next(p))
R('R26', '100', 'IO5_B', 'IO5', (48.6, ROWS[1], 0, 'B'), next(p))
R('R27', '100', 'IO6_B', 'IO6', (48.6, ROWS[2], 0, 'B'), next(p))
R('R28', '100', 'IO7_B', 'IO7', (48.6, ROWS[3], 0, 'B'), next(p))

# DIR defaults: high = probe drives the pin (A→B), low = input (B→A)
p = col(PX[1], 154.94)
DIRS = (('R30', 'DIR0', '+3V3'), ('R31', 'DIR1', '+3V3'), ('R32', 'DIR2', 'GND'), ('R33', 'DIR3', '+3V3'),
        ('R34', 'DIR4', 'GND'), ('R35', 'DIR567', 'GND'))
# each DIR resistor sits at its translator's DIR via: IO0..IO4 under the top-side chips, IO5..IO7 beside the bottom ones
DIR_POS = [(47.0, CY[0] + 1.2, 90, 'B'), (47.0, CY[1] + 1.2, 90, 'B'), (47.0, CY[2] + 1.2, 90, 'B'),
           (47.0, CY[3] + 1.2, 90, 'B'), (47.0, CY[4] + 1.2, 90, 'B'),
           (42.6, BY[0], 180, 'B'), (42.6, BY[1], 180, 'B'), (42.6, BY[2], 180, 'B')]
for i, (ref, net, rail) in enumerate(DIRS):
    R(ref, '10k', rail, net, DIR_POS[i], next(p))

# A-side idle levels (define the bus while firmware has not configured the pins or VIO is absent)
p = col(PX[2], 154.94)
R('R40', '100k', 'IO0_A', 'GND', (34.0, 5.6, 0, 'F'), next(p))
R('R41', '10k', '+3V3', 'SWDIO_O', (34.0, 7.0, 0, 'F'), next(p))
R('R42', '100k', '+3V3', 'IO1_A', (34.0, 8.4, 0, 'F'), next(p))
R('R43', '100k', '+3V3', 'IO3_A', (34.0, 9.8, 0, 'F'), next(p))
R('R44', '100k', '+3V3', 'IO4_A', (34.0, 11.2, 0, 'F'), next(p))

# target-side idle levels
PULLS = (('R50', 'IO0', 'GND'), ('R51', 'IO1', 'VIO'), ('R52', 'IO2', 'VIO'), ('R53', 'IO3', 'VIO'),
         ('R54', 'IO4', 'VIO'), ('R55', 'IO5', 'GND'), ('R56', 'IO6', 'GND'), ('R57', 'IO7', 'GND'))
for i, (ref, net, rail) in enumerate(PULLS[:4]):
    R(ref, '100k', rail, net, (43.6 + 1.6 * i, 1.5, 90, 'B'), next(p))
p = col(PX[3], 154.94)
for i, (ref, net, rail) in enumerate(PULLS[4:]):
    R(ref, '100k', rail, net, (37.4 + 1.6 * i, 18.4, 90, 'B'), next(p))

# translator decoupling
C('C20', '100nF', '+3V3', 'GND', (44.1, 5.25, 90, 'B'), next(p))
C('C21', '100nF', '+3V3', 'GND', (44.1, 11.85, 90, 'B'), next(p))
C('C22', '100nF', '+3V3', 'GND', (44.1, 15.15, 90, 'B'), next(p))
C('C23', '100nF', '+3V3', 'GND', (35.6, 12.6, 0, 'B'), next(p))
C('C24', '100nF', '+3V3', 'GND', (35.6, 6.0, 0, 'B'), next(p))
p = col(PX[0], 228.6)
C('C25', '100nF', 'VIO', 'GND', (45.9, 5.25, 90, 'B'), next(p))
C('C26', '100nF', 'VIO', 'GND', (45.9, 11.85, 90, 'B'), next(p))
C('C27', '100nF', 'VIO', 'GND', (45.9, 15.15, 90, 'B'), next(p))
p = col(PX[1], 228.6)
C('C28', '100nF', 'VIO', 'GND', (42.6, 14.9, 0, 'B'), next(p))
C('C29', '100nF', 'VIO', 'GND', (42.6, 8.15, 0, 'B'), next(p))
C('C30', '1uF', 'VIO', 'GND', (44.4, 1.6, 0, 'F'), next(p))

# ESD arrays on the target-side nets
comp('U14', 'Power_Protection:SRV05-4', 'SRV05-4', 'Package_TO_SOT_SMD:SOT-23-6',
     {1: 'IO0', 3: 'IO1', 4: 'IO2', 6: 'IO3', 2: 'GND', 5: None},
     (50.8, 12.0, 90, 'B'), (127.0, 198.12, 0), mpn='SRV05-4 (SOT-23-6)', desc='4-line 5 V TVS array')
comp('U15', 'Power_Protection:SRV05-4', 'SRV05-4', 'Package_TO_SOT_SMD:SOT-23-6',
     {1: 'IO4', 3: 'IO5', 4: 'IO6', 6: 'IO7', 2: 'GND', 5: None},
     (33.6, 16.0, 0, 'B'), (127.0, 238.76, 0), mpn='SRV05-4 (SOT-23-6)', desc='4-line 5 V TVS array')

# ═════════════════════ VIO (target reference voltage) ══════════════════════
comp('D6', 'Device:D_Schottky', 'B5819WS', SOD323, {2: '+3V3', 1: 'VIO_F'},
     (28.6, 1.5, 0, 'F'), (180.34, 228.6, 0), mpn='B5819WS (SOD-323)', desc='Blocks back-feed from the target into +3V3')
comp('F2', 'Device:Polyfuse', '200mA', 'Fuse:Fuse_0603_1608Metric', {1: 'VIO_F', 2: 'VIO_INT'},
     (28.6, 3.4, 0, 'F'), (180.34, 236.22, 90), mpn='0603 PTC 0.2A hold / 6V', desc='Limits current sourced on VTREF')
comp('SW2', 'Switch:SW_SPDT', 'VIO INT/EXT', 'Button_Switch_SMD:SW_SPDT_Shouhan_MSK12C02',
     {2: 'VIO', 1: 'VIO_INT', 3: None}, (36.0, 1.75, 180, 'F'), (180.34, 259.08, 0), mpn='Shouhan MSK-12C02',
     desc='VIO source: INT = probe 3V3, EXT = target VTREF')
comp('D7', 'Device:D_TVS', '5V', SOD323, {1: 'VIO', 2: 'GND'}, (47.6, 1.3, 0, 'F'), (180.34, 243.84, 0),
     mpn='PESD5V0S1BA (SOD-323)', desc='VTREF pin ESD clamp')
R('R60', '100k', 'VIO', 'VIO_SENSE', (33.0, 5.5, 0, 'B'), (226.06, 228.6))
R('R61', '100k', 'VIO_SENSE', 'GND', (33.0, 6.9, 0, 'B'), (226.06, 236.22))
C('C31', '100nF', 'VIO_SENSE', 'GND', (33.0, 8.3, 0, 'B'), (226.06, 243.84))

# ═══════════════════════════ +5 V target supply ════════════════════════════
comp('D8', 'Device:D_Schottky', 'B5819WS', SOD323, {2: '+5V', 1: '5V_F'},
     (44.6, 19.8, 0, 'B'), (226.06, 251.46, 0), mpn='B5819WS (SOD-323)', desc='Blocks back-feed into USB VBUS')
comp('F3', 'Device:Polyfuse', '350mA', 'Fuse:Fuse_0603_1608Metric', {1: '5V_F', 2: '5V_OUT'},
     (49.1, 19.7, 0, 'B'), (226.06, 259.08, 90), mpn='0603 PTC 0.35A hold / 6V', desc='Limits current on the 5 V pin')
comp('D9', 'Device:D_TVS', '5V', SOD323, {1: '5V_OUT', 2: 'GND'}, (48.6, 19.4, 0, 'F'), (226.06, 266.7, 0),
     mpn='PESD5V0S1BA (SOD-323)', desc='5 V pin ESD clamp')

# ═════════════════════════════ analog inputs ═══════════════════════════════
ADC = (('R62', 'D10', 'AIN0', 'ADC0', (48.6, 16.1, 0, 'F'), (45.0, 19.45, 180, 'F')),
       ('R63', 'D11', 'AIN1', 'ADC1', (49.6, 15.0, 0, 'B'), (51.9, 17.0, 90, 'B')),
       ('R64', 'D12', 'AIN2', 'ADC2', (49.6, ROWS[6], 0, 'B'), (34.8, 19.2, 0, 'B')))
for i, (r, d, ain, adc, rp, dp) in enumerate(ADC):
    R(r, '2.2k', ain, adc, rp, (147.32, 266.7 + 7.62 * i))
    comp(d, 'Diode:BAT54SW', 'BAT54SW', 'Package_TO_SOT_SMD:SOT-323_SC-70', {1: 'GND', 2: '+3V3', 3: adc},
         dp, (30.48 + 35.56 * i, 266.7, 0), mpn='BAT54SW (SOT-323)', desc='ADC input clamp to GND / 3V3')

# ═════════════════════════════ target connector ════════════════════════════
J2_PINS = {1: 'VIO', 2: 'GND', 3: 'IO0', 4: 'IO5', 5: 'IO1', 6: 'IO6', 7: 'IO2', 8: 'IO7',
           9: 'IO3', 10: 'GND', 11: 'IO4', 12: 'AIN1', 13: 'AIN0', 14: 'AIN2', 15: 'GND', 16: '5V_OUT'}
comp('J2', 'Connector_Generic:Conn_02x08_Odd_Even', 'Target 2x8', f'{LIB}:PinHeader_2x08_P2.54mm_EdgeMount',
     J2_PINS, (BOARD_L - 2.5, BOARD_W / 2, 0, 'F'), (215.9, 198.12, 0),
     mpn='2x8 2.54 mm straight pin header, straddle-mounted on the 1.6 mm board edge', desc='Target connector')

comp('H1', 'Mechanical:MountingHole', 'M2', 'MountingHole:MountingHole_2.2mm_M2', {}, (3.4, 2.4, 0, 'F'), (401.32, 231.14, 0))
comp('H2', 'Mechanical:MountingHole', 'M2', 'MountingHole:MountingHole_2.2mm_M2', {}, (3.4, 18.6, 0, 'F'), (401.32, 241.3, 0))

# Parts turned by 180 degrees relative to the positions above, so that each pad faces the pad it is wired to.
# The list comes from gen/orient.py (shortest pad-to-pad distance per part); re-run it after moving parts.
ORIENT_FLIP = ['C1', 'C14', 'C30', 'D8', 'D9', 'R7', 'R9', 'R10', 'R11', 'R12', 'R13', 'R14', 'R40', 'R50', 'R51',
               'R52', 'R53', 'R54', 'R60', 'R62', 'R64']
for _c in COMPONENTS:
    if _c['ref'] in ORIENT_FLIP:
        x, y, rot, side = _c['pcb']
        _c['pcb'] = (x, y, (rot + 180) % 360, side)

# routing classes: net → track width (mm).  GND is the In1 plane.
PLANES = {'GND': 'In1.Cu', '+3V3': 'In2.Cu'}
WIDTHS = {'VBUS': 0.4, '+5V': 0.4, '5V_F': 0.4, '5V_OUT': 0.4, 'GND': 0.25, '+3V3': 0.25, '+1V1': 0.25,
          'VIO': 0.3, 'VIO_F': 0.3, 'VIO_INT': 0.3, 'ADC_AVDD': 0.2}
DEFAULT_WIDTH = 0.15
CLEARANCE = 0.15
VIA_D, VIA_DRILL = 0.55, 0.3

# Hand-placed fan-out for the RP2040 supply pins (board-local mm, on the 0.1 mm grid).  The space between
# the QFN pad ring and its exposed pad only fits a few vias, so they are assigned here instead of being
# left to the autorouter.  Endpoints are 'REF.PIN', a via name, or an (x, y) point.
PRE_VIAS = {
    'V44': ('+3V3', MX - 2.4, MY - 2.4), 'V45': ('+1V1', MX - 2.4, MY - 1.6), 'V48': ('+3V3', MX - 2.4, MY - 0.4),
    'V50': ('+1V1', MX - 2.4, MY + 0.4), 'V22': ('+3V3', MX + 2.4, MY + 0.2), 'V23': ('+1V1', MX + 2.4, MY - 0.8),
    'V33': ('+3V3', MX + 1.0, MY - 2.4), 'V1': ('+3V3', MX - 2.4, MY + 2.4), 'V10': ('+3V3', MX + 1.0, MY + 2.4),
    'G1': ('GND', MX, MY - 2.4), 'G2': ('GND', MX, MY + 1.3),
}
PRE_LINKS = [
    # top side: pin → via between the pad ring and the exposed pad
    ('+3V3', 'F.Cu', 'U3.44', 'V44', 0.2), ('+3V3', 'F.Cu', 'U3.42', 'V44', 0.2), ('+1V1', 'F.Cu', 'U3.45', 'V45', 0.2),
    ('+3V3', 'F.Cu', 'U3.48', 'V48', 0.2), ('+3V3', 'F.Cu', 'U3.49', 'V48', 0.2), ('+1V1', 'F.Cu', 'U3.50', 'V50', 0.2),
    ('+3V3', 'F.Cu', 'U3.22', 'V22', 0.2), ('+1V1', 'F.Cu', 'U3.23', 'V23', 0.2), ('+3V3', 'F.Cu', 'U3.33', 'V33', 0.2),
    ('+3V3', 'F.Cu', 'U3.1', 'V1', 0.2), ('+3V3', 'F.Cu', 'U3.10', 'V10', 0.2),
    ('GND', 'F.Cu', 'U3.19', (MX + 1.2, MY + 1.0), 0.2),            # TESTEN straight into the exposed pad
    # bottom side: via → decoupling capacitor under the chip
    ('+3V3', 'B.Cu', 'V44', 'C12.1', 0.25), ('+3V3', 'B.Cu', 'V48', 'C9.1', 0.25),
    ('+1V1', 'B.Cu', 'V45', 'C13.1', 0.25), ('+1V1', 'B.Cu', 'V50', 'C11.1', 0.25), ('+1V1', 'B.Cu', 'C13.1', 'C11.1', 0.25),
    ('+1V1', 'B.Cu', 'V23', 'C10.1', 0.25), ('+3V3', 'B.Cu', 'V22', 'C6.1', 0.25),
    ('GND', 'B.Cu', 'C13.2', 'G1', 0.25), ('GND', 'B.Cu', 'C10.2', 'G1', 0.25),
    ('GND', 'B.Cu', 'C11.2', 'G2', 0.25), ('GND', 'B.Cu', 'C6.2', 'G2', 0.25),
    # +1V1 from the regulator side (pins 45/50) across to pin 23, on the inner layer under the exposed pad
    ('+1V1', 'In2.Cu', 'V45', (MX + 1.5, MY - 1.6), 0.25), ('+1V1', 'In2.Cu', (MX + 1.5, MY - 1.6), 'V23', 0.25),
]
# Level translators get the same treatment: supply and DIR vias sit 2.2 mm either side of the chip.
TRANSLATOR_VIA_DX = 2.2
PRE_LINKS += [(net, 'B.Cu', f'{u}.v5', f'{r}.2', 0.2) for net, u, r in
              (('DIR0', 'U5', 'R30'), ('DIR1', 'U6', 'R31'), ('DIR2', 'U8', 'R32'), ('DIR3', 'U9', 'R33'),
               ('DIR4', 'U10', 'R34'), ('DIR567', 'U11', 'R35'))]
