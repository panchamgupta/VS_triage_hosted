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
	--input Wuxi_Enamine_Leo_Bicyclic_docking_pose_3D_filtered_w_ADME.sdf \
	--protein-pdb STAT6-1669872_wo_lig.pdb \
	--file-prefix VS_PPI_Leo_Bicyclic_headgroup_screen_06052026 \
	--interaction-csv "$SCRIPT_DIR/Wuxi_Enamine_Leo_Bicyclic_IF.csv" \
	--interaction-id-col Title \
	--interaction-count-col interaction_count \
	--outdir "$SCRIPT_DIR" \
	--ref-ligand-sdf Leo_Bicyclic_ref_pose.sdf \
	--max-molecular-weight 800 \
	--max-rotatable-bonds 13 \
	--max-hbond-donors 2 \
	--exclude-smiles-file "$SCRIPT_DIR/exclude_motifs.smi" \
	--top-per-scaffold 10 \
	--max-scaffolds-in-report 500 \
	--n-workers 8 \
	--text-sd-props Vendor ring_system \
	 --generate-all-mol-images \
	#--numeric-sd-props ring_system \



