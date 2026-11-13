#!/bin/bash
# finish → DRC → connect whatever the plane fills left unconnected (router state + rip-up repair) → repeat
# usage: gen/finish_loop.sh <routes.json> <router-state.pkl>
set -e
cd "$(dirname "$0")/.."
K=gen/kicad-docker.sh
P=LA_RP2040_V2
cp "$1" build/routes_final.json
for round in 1 2 3 4 5 6 7 8; do
  $K python3 gen/gen_pcb.py finish build/placed.kicad_pcb build/routes_final.json kicad/$P.kicad_pcb 2>&1 | grep -v "memory leak"
  $K kicad-cli pcb drc --schematic-parity --severity-all -o build/drc.rpt kicad/$P.kicad_pcb >/dev/null || true
  python3 gen/report.py build/drc.rpt
  if ! python3 gen/drc_pairs.py build/drc.rpt build/pairs.json; then
    grep -q "unconnected_items" build/drc.rpt || break      # nothing left
    # only pour-to-pour items left: locate the stranded GND groups from the filled zones
    $K python3 gen/gnd_islands.py kicad/$P.kicad_pcb GND build/pairs.json 2>&1 | grep -v "memory leak"
  fi
  python3 gen/route.py --links "$2" build/pairs.json build/routes_final.json
done
