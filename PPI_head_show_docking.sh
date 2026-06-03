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
	--input Wuxi_Enamine_docking_pose_3D_w_ADME.sdf \
	--protein-pdb "$SCRIPT_DIR/6782_protein.pdb" \
	--file-prefix VS_PPI_head_06032026 \
	--interaction-csv "$SCRIPT_DIR/Wuxi_Enamine_direct.csv" \
	--interaction-id-col Title \
	--interaction-count-col interaction_count \
	--outdir "$SCRIPT_DIR" \
	--ref-ligand-sdf ref_structures.sdf \
	--max-molecular-weight 800 \
	--max-rotatable-bonds 13 \
	--max-hbond-donors 2 \
	--exclude-smiles-file "$SCRIPT_DIR/exclude_motifs.smi" \
	--top-per-scaffold 10 \
	--max-scaffolds-in-report 300 \
	--n-workers 8 \
	--text-sd-props Vendor ring_system \
	#--numeric-sd-props ring_system \
	# --generate-all-mol-images



