#!/bin/bash
S=/tmp/claude-0/-home-user-Debugger/cc9a1765-fad2-5995-86b8-75c8da70122c/scratchpad
cd /home/user/Debugger/hardware/la-rp2040-v2
python3 gen/gen_sch.py $S/klib/symbols kicad/LA_RP2040_V2.kicad_sch && gen/kicad-docker.sh kicad-cli sch export svg -o /w/kicad/_svg kicad/LA_RP2040_V2.kicad_sch >/dev/null 2>&1; cp kicad/_svg/*.svg $S/view/sch.svg; rm -rf kicad/_svg
cd $S && node shot.js $S/view/sch.svg $S/view/sch.png ${1:-2000} $2
