#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if command -v conda >/dev/null 2>&1; then
  PYTHON_CMD=(conda run -n rdkit-env python)
else
  PYTHON_CMD=(python3)
fi

"${PYTHON_CMD[@]}" process_docking_IF_show_docking.py \
  -i direct_linker_enumeration_docking_pose_all_BB_with_props.sdf \
  -P "$SCRIPT_DIR/6782_protein.pdb" \
  -f VS_visualization_05232026 \
  -c "$SCRIPT_DIR/direct_linker_all_IF.csv" \
  -j Title \
  -k interaction_count \
  -o "$SCRIPT_DIR" \
  -b 13 \
  -D 2 \
  -e "$SCRIPT_DIR/exclude_motifs.smi" \
  -t 10 \
  -m 25 \
  -n 8 \
  -r "$SCRIPT_DIR/ref_structures.sdf"
  # -G
