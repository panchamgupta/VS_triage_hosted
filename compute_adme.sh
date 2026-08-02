#!/bin/bash

CHEMPROP_BIN="${CHEMPROP_BIN:-/home/cjamieson/anaconda3/envs/reinvent4.5/bin/chemprop_predict}"

"${CHEMPROP_BIN}" \
    --test_path direct_linker_enumeration_docking_pose_all_BB_SMILES.csv \
    --preds_path direct_linker_enumeration_docking_pose_all_BB_SMILES_adme.csv \
    --smiles_column SMILES \
    --checkpoint_path /home/ppadmin/PropertyCalculator/models/model_0/model.pt \
    --features_generator rdkit_2d_normalized \
    --no_features_scaling
