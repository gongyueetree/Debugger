#!/bin/bash
# Run a command inside the official KiCad 9 container with this hardware directory mounted at /w.
#   gen/kicad-docker.sh kicad-cli ...        gen/kicad-docker.sh python3 gen/gen_pcb.py ...
# Optional: KICAD_3DMODELS=/path/to/kicad-packages3D adds component models for STEP export and renders.
set -e
HERE="$(cd "$(dirname "$0")/.." && pwd)"
MODELS=()
if [ -n "$KICAD_3DMODELS" ]; then
  MODELS=(-v "$KICAD_3DMODELS":/models:ro -e KICAD9_3DMODEL_DIR=/models)
fi
exec docker run --rm -u 0 -e HOME=/tmp/home "${MODELS[@]}" -v "$HERE":/w -w /w kicad/kicad:9.0 bash -c '
  mkdir -p /tmp/home/.config/kicad/9.0
  cp /usr/share/kicad/template/sym-lib-table /usr/share/kicad/template/fp-lib-table /tmp/home/.config/kicad/9.0/
  "$@"' -- "$@"
