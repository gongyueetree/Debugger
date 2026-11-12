#!/bin/bash
# Regenerate everything from gen/design.py.  Needs: python3 + numpy on the host, docker (kicad/kicad:9.0).
#   gen/build.sh            full flow: schematic → netlist check → place → route → finish → ERC/DRC → fab outputs
#   gen/build.sh noroute    reuse build/routes.json (skip the slow autorouter)
set -e
cd "$(dirname "$0")/.."
K=gen/kicad-docker.sh
P=LA_RP2040_V2
SYMS=${KICAD_SYMBOL_DIR:-build/symbols}
mkdir -p build
if [ ! -d "$SYMS" ]; then            # symbol libraries are read on the host; copy them out of the container once
  $K bash -c "cp -r /usr/share/kicad/symbols build/symbols && chmod -R a+rwX build/symbols"
fi
python3 gen/gen_sch.py "$SYMS" kicad/$P.kicad_sch
python3 gen/gen_pro.py kicad/$P.kicad_pro
$K kicad-cli sch export netlist --format kicadsexpr -o build/sch.net kicad/$P.kicad_sch >/dev/null
python3 gen/check_netlist.py build/sch.net
$K python3 gen/gen_pcb.py place build/sch.net build/placed.kicad_pcb build/pads.json 2>&1 | grep -v "memory leak"
python3 gen/check_place.py build/pads.json
if [ "$1" != "noroute" ]; then
  python3 gen/route.py build/pads.json build/routes.json
fi
$K python3 gen/gen_pcb.py finish build/placed.kicad_pcb build/routes.json kicad/$P.kicad_pcb 2>&1 | grep -v "memory leak"
$K kicad-cli sch erc --severity-all --exit-code-violations -o build/erc.rpt kicad/$P.kicad_sch || true
$K kicad-cli pcb drc --schematic-parity --severity-all -o build/drc.rpt kicad/$P.kicad_pcb || true
python3 gen/report.py build/erc.rpt build/drc.rpt
