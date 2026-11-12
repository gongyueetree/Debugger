#!/bin/bash
# Export manufacturing and documentation files from the finished KiCad project.
set -e
cd "$(dirname "$0")/.."
K=gen/kicad-docker.sh
P=LA_RP2040_V2
PCB=kicad/$P.kicad_pcb
rm -rf fab/gerber && mkdir -p fab/gerber doc
$K kicad-cli pcb export gerbers -o fab/gerber/ --no-protel-ext --subtract-soldermask \
  --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts $PCB >/dev/null
$K kicad-cli pcb export drill -o fab/gerber/ --format excellon --excellon-separate-th --excellon-units mm \
  --generate-map --map-format gerberx2 $PCB >/dev/null
$K kicad-cli pcb export pos -o fab/${P}_pos.csv --format csv --units mm --side both --exclude-dnp $PCB >/dev/null
python3 gen/gen_bom.py fab/${P}_BOM.csv
(cd fab/gerber && rm -f ../${P}_gerber.zip && python3 -c "
import zipfile, os
with zipfile.ZipFile('../${P}_gerber.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    for f in sorted(os.listdir('.')):
        z.write(f)
print('gerber zip:', len(os.listdir('.')), 'files')")
$K kicad-cli sch export pdf -o doc/${P}_schematic.pdf kicad/$P.kicad_sch >/dev/null
$K kicad-cli sch export svg -o doc/_sch kicad/$P.kicad_sch >/dev/null && mv doc/_sch/*.svg doc/${P}_schematic.svg && rm -rf doc/_sch
for side in front back; do
  if [ $side = front ]; then L=F.Cu,F.SilkS,F.Mask,Edge.Cuts; M=""; else L=B.Cu,B.SilkS,B.Mask,Edge.Cuts; M="--mirror"; fi
  $K kicad-cli pcb export svg -o doc/${P}_pcb_$side.svg --layers $L $M --page-size-mode 2 --exclude-drawing-sheet $PCB >/dev/null
done
$K kicad-cli pcb export svg -o doc/${P}_pcb_inner.svg --layers In1.Cu,In2.Cu,Edge.Cuts --page-size-mode 2 --exclude-drawing-sheet $PCB >/dev/null
$K kicad-cli pcb export pdf -o doc/${P}_pcb.pdf --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.SilkS,B.SilkS,F.Fab,B.Fab,Edge.Cuts \
  --mode-multipage --include-border-title $PCB >/dev/null 2>&1 || \
$K kicad-cli pcb export pdf -o doc/${P}_pcb.pdf --layers F.Cu,B.Cu,F.SilkS,B.SilkS,Edge.Cuts $PCB >/dev/null
$K kicad-cli pcb export step -o fab/${P}_board.step --subst-models --force $PCB >/dev/null 2>&1 || echo "STEP export skipped"
if [ -n "$KICAD_3DMODELS" ]; then
  for side in top bottom; do
    $K kicad-cli pcb render -o doc/${P}_render_$side.png --side $side --width 1800 --height 900 --quality high \
      --background opaque $PCB >/dev/null 2>&1 || echo "render $side skipped"
  done
fi
ls fab fab/gerber doc
