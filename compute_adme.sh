#!/bin/bash

chemprop_predict \
    --test_path direct_linker_enumeration_docking_pose_all_BB_SMILES.csv \
    --preds_path direct_linker_enumeration_docking_pose_all_BB_SMILES_adme.csv \
    --smiles_column SMILES \
    --checkpoint_path /home/cjamieson/bin/reinvent/adme_models/2026_03_01/model.pt \
    --features_generator rdkit_2d_normalized \
    --no_features_scaling
