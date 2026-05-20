#!/usr/bin/env bash

if command -v conda >/dev/null 2>&1; then
  PYTHON_CMD=(conda run -n rdkit-env python)
else
  PYTHON_CMD=(python3)
fi

"${PYTHON_CMD[@]}" process_docking_IF_show_docking.py --input  direct_linker_enumeration_docking_pose_all_BB_with_props.sdf \
	--protein-pdb 6782_protein.pdb \
	--file-prefix VS_visualization_05052026 \
	--interaction-csv direct_linker_all_IF.csv \
	--interaction-id-col Title \
  	--interaction-count-col interaction_count \
	--high-interaction-cutoff 3 \
	--unique-by-novelty \
 	--high-interaction-top-n 10 \
	--outdir /home/pgupta11/Projects/STAT6_PPI/PPI_program_writing/R_group_mapping/advanced_problems/ \
	--score-props r_i_docking_score fsp3 interaction_count druglike_score \
	--auto-detect-score  \
	--interaction-weight 0.7 \
        --exclude-smiles-file exclude_motifs.smi \
        --exclude-match-mode substructure \
	--top-per-scaffold 10 \
	--max-scaffolds-in-report 25 \
	--max-rot-bonds 13 \
	--max-hbd 2 \
	--neutral-only \
	--n-workers 8 \
	--csv-io-workers 8 \
	--ref-ligand-sdf ref_structures.sdf \
	#--generate-all-mol-images \



