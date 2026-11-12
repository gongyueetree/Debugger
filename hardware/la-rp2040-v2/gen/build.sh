#!/bin/bash
# Regenerate the KiCad project from gen/design.py.
#   gen/build.sh          schematic → netlist check → placement → stored routing (gen/routes.json) → zones → ERC/DRC
#   gen/build.sh route    re-run the autorouter and the DRC-driven connection repair first (15–30 min), then as above
# Needs python3 + numpy on the host and docker (official kicad/kicad:9.0 image).
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
python3 gen/check_escape.py build/pads.json
if [ "$1" = "route" ]; then
  # These settings produced the stored result.  The router is deterministic for a given placement, but any
  # placement change can leave a few links unrouted; then try other ROUTE_ORDER / ROUTE_LAYER_COST values.
  ROUTE_SAVE=build/state.pkl ROUTE_ORDER=short ROUTE_PASSES=1 ROUTE_BUDGET=1000 ROUTE_LAYER_COST=0,25,10,0 \
    python3 gen/route.py build/pads.json build/routes.json
  gen/finish_loop.sh build/routes.json build/state.pkl
  cp build/routes_final.json gen/routes.json
fi
$K python3 gen/gen_pcb.py finish build/placed.kicad_pcb gen/routes.json kicad/$P.kicad_pcb 2>&1 | grep -v "memory leak"
$K kicad-cli sch erc --severity-all -o build/erc.rpt kicad/$P.kicad_sch >/dev/null || true
$K kicad-cli pcb drc --schematic-parity --severity-all -o build/drc.rpt kicad/$P.kicad_pcb >/dev/null || true
python3 gen/report.py build/erc.rpt build/drc.rpt
