#!/bin/bash
# finish → DRC → bridge whatever the plane fills left unconnected → repeat (max 6 rounds)
# usage: gen/finish_loop.sh <routes.json>
set -e
cd "$(dirname "$0")/.."
K=gen/kicad-docker.sh
P=LA_RP2040_V2
cp "$1" build/routes_final.json
for round in 1 2 3 4 5 6; do
  $K python3 gen/gen_pcb.py finish build/placed.kicad_pcb build/routes_final.json kicad/$P.kicad_pcb 2>&1 | grep -v "memory leak"
  $K kicad-cli pcb drc --schematic-parity --severity-all -o build/drc.rpt kicad/$P.kicad_pcb >/dev/null || true
  python3 gen/report.py build/drc.rpt
  if ! python3 gen/drc_pairs.py build/drc.rpt build/pairs.json; then
    grep -q "unconnected_items" build/drc.rpt || break       # clean
    [ -n "$BRIDGE_PLANES" ] && break                         # zone islands that bridging did not fix
    export BRIDGE_PLANES=1                                   # only zone-level items left: repair the planes once
  fi
  python3 gen/route.py --bridge build/pads.json build/routes_final.json build/pairs.json build/routes_next.json
  mv build/routes_next.json build/routes_final.json
done
