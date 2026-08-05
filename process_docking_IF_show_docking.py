#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
process_rgroup_sdf.py

2) Extracts identifier, docking score, scaffold, and substitution patterns.
    if not csv_path:
        return None, {"ext_rows": 0, "ext_unique_ids": 0, "ext_duplicate_ids": 0, "ext_matched_molecules": 0}
    if not os.path.exists(csv_path):
        eprint(f"Warning: external interaction CSV not found: {csv_path}")
        return None, {"ext_rows": 0, "ext_unique_ids": 0, "ext_duplicate_ids": 0, "ext_matched_molecules": 0}
3) Optionally merges interaction fingerprint CSV (IF matrix).
4) Computes interaction count and weighted interaction score.
5) Ranks molecules, scaffold "central ideas", and scaffold "unique ideas".
6) Writes CSV outputs, publication-ready PNG plots, and an HTML report.

Dependencies
------------
- rdkit
- pandas
- matplotlib

Example
-------
python process_rgroup_sdf.py \
  --input direct_linker_enumeration_docking_pose_all_BB.sdf \
  --if-csv IF_across_all_BB_direct_linker_screen.csv \
  --outdir rgroup_report \
  --score-props r_i_docking_score r_i_glide_gscore docking_score score
"""

import argparse
import csv
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs
from rdkit.Chem import Descriptors
from rdkit.Chem import Draw
from rdkit.Chem import Crippen
from rdkit.Chem import Lipinski
from rdkit.Chem import rdDepictor
from rdkit.Chem import rdMolDescriptors
from rdkit.Chem.Draw import rdMolDraw2D
from rdkit.Chem.MolStandardize import rdMolStandardize
from rdkit.Chem.Scaffolds import MurckoScaffold

try:
    import mdtraj as md
except Exception:
    md = None

try:
    import pyarrow as pa
    import pyarrow.csv as pa_csv
except Exception:
    pa = None
    pa_csv = None

from cli_config import build_cli_parser, initialize_output_layout, prefixed_output_name, resolve_score_props
from export_helpers import collect_scaffold_export_data, flush_pending_csv_writes, make_central_barplot, make_central_structure_overview, make_qc_summary, make_residue_heatmap, make_scatter_plot, read_sdf_blocks_by_index, sanitize_sdf_blocks_for_viewer, write_dataframe_csv
from filtering import apply_report_filters, druglike_score_from_row, weighted_present
from progress_tracking import format_elapsed, progress_log, start_progress_bar, finish_progress_bar
from report_helpers import build_hbond_residue_filter_data, write_html_report
from ranking_helpers import load_external_interaction_counts, merge_and_rank_molecules, normalize_series
from scaffold_summary_helpers import add_scaffold_stats, aligned_depiction_mol, assign_scaffold_names_and_rerank, build_per_scaffold_substitution_table, build_scaffold_summary_row, draw_scaffold_panel, draw_scaffold_with_positions, filter_sig_to_positions, initialize_scaffold_analysis, mol_png_base64, mol_png_base64_from_smiles, representative_ranked_subset, scaffold_tick_image
from shared_utils import hash_text, normalize_id, safe_float

# Module-level Uncharger for pH-7 neutrality (reuse to avoid per-call overhead).
_UNCHARGER = rdMolStandardize.Uncharger()
DEFAULT_SCORE_WEIGHT = 0.4
DEFAULT_INTERACTION_WEIGHT = 0.6
DEFAULT_BINDING_SITE_RADIUS = 4.0
DEFAULT_POCKET_STICKS = True
DEFAULT_EXCLUDE_MATCH_MODE = "substructure"

_FILTER_PROP_CANDIDATES = {
    "mol_wt": ["molecular_weight", "MolecularWeight", "MW", "mol_wt"],
    "rot_bonds": ["Rotatable_bonds", "RotatableBonds", "RotBonds", "rot_bonds"],
    "hbd": ["Hydrogen bond donors", "HydrogenBondDonors", "HBD", "hbd"],
    "hba": ["Hydrogen bond acceptors", "HydrogenBondAcceptors", "HBA", "hba"],
}


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def canonicalize_smiles_or_none(smiles):
    if smiles is None:
        return None
    text = str(smiles).strip()
    if not text:
        return None
    mol = Chem.MolFromSmiles(text)
    if mol is None:
        return None
    try:
        return Chem.MolToSmiles(mol, isomericSmiles=True)
    except Exception:
        return None


def _parse_protein_pdb_inputs(raw_value):
    if raw_value is None:
        return []
    if isinstance(raw_value, (list, tuple)):
        values = raw_value
    else:
        values = str(raw_value).split(",")
    out = []
    seen = set()
    for value in values:
        path = str(value or "").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def _infer_protein_mol2_bond_orders(mol2_text):
    """Infer standard protein residue bond orders in MOL2 for viewer/runtime assets.

    Protein MOL2 files from conversion tools often flatten residue chemistry. For standard
    amino acids we restore explicit bond orders that match common residue valence rules:
    aromatic side chains use explicit single/double bonds instead of ``ar`` bonds, while
    carboxylates keep single C-O bonds.
    """
    if not mol2_text:
        return mol2_text

    lines = str(mol2_text).splitlines()
    atom_start = atom_end = bond_start = bond_end = None
    for i, line in enumerate(lines):
        token = line.strip().upper()
        if token == "@<TRIPOS>ATOM":
            atom_start = i + 1
        elif token == "@<TRIPOS>BOND":
            atom_end = i
            bond_start = i + 1
        elif token.startswith("@<TRIPOS>") and bond_start is not None and bond_end is None:
            bond_end = i
            break
    if atom_start is None or atom_end is None or bond_start is None:
        return mol2_text
    if bond_end is None:
        bond_end = len(lines)

    standard_residues = {
        "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
        "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
    }

    atom_meta = {}
    residue_atoms = defaultdict(dict)
    for i in range(atom_start, atom_end):
        row = lines[i].strip()
        if not row or row.startswith("#"):
            continue
        parts = row.split()
        if len(parts) < 8:
            continue
        try:
            atom_id = int(parts[0])
            atom_name = str(parts[1]).upper()
            subst_id = int(parts[6])
            subst_name = str(parts[7]).upper()
        except Exception:
            continue
        m = re.match(r"^([A-Z]{3})(?:\d+.*)?$", subst_name)
        if not m:
            continue
        resn = m.group(1)
        if resn not in standard_residues:
            continue
        key = (subst_id, resn)
        atom_meta[atom_id] = {"res_key": key, "atom_name": atom_name}
        residue_atoms[key][atom_name] = atom_id

    if not atom_meta:
        return mol2_text

    bond_rows = []
    bond_lookup = {}
    for i in range(bond_start, bond_end):
        row = lines[i]
        stripped = row.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 4:
            continue
        try:
            bond_id = int(parts[0])
            a1 = int(parts[1])
            a2 = int(parts[2])
        except Exception:
            continue
        btype = str(parts[3])
        extra = parts[4:]
        bond_rows.append({"line_idx": i, "bond_id": bond_id, "a1": a1, "a2": a2, "type": btype, "extra": extra})
        bond_lookup[frozenset((a1, a2))] = len(bond_rows) - 1

    def set_bond(atom_a, atom_b, btype):
        idx = bond_lookup.get(frozenset((atom_a, atom_b)))
        if idx is None:
            return
        bond_rows[idx]["type"] = btype

    def set_pair(res_atoms, name_a, name_b, btype):
        a = res_atoms.get(name_a)
        b = res_atoms.get(name_b)
        if a is None or b is None:
            return
        set_bond(a, b, btype)

    residue_bond_templates = {
        "PHE": [("CG", "CD1", "1"), ("CD1", "CE1", "2"), ("CE1", "CZ", "1"), ("CZ", "CE2", "2"), ("CE2", "CD2", "1"), ("CD2", "CG", "2")],
        "TYR": [("CG", "CD1", "1"), ("CD1", "CE1", "2"), ("CE1", "CZ", "1"), ("CZ", "CE2", "2"), ("CE2", "CD2", "1"), ("CD2", "CG", "2")],
        "HIS": [("CG", "ND1", "1"), ("ND1", "CE1", "2"), ("CE1", "NE2", "1"), ("NE2", "CD2", "2"), ("CD2", "CG", "1")],
        "TRP": [
            ("CG", "CD1", "2"), ("CD1", "NE1", "1"), ("NE1", "CE2", "2"), ("CE2", "CD2", "1"), ("CD2", "CG", "1"),
            ("CE2", "CZ2", "1"), ("CZ2", "CH2", "2"), ("CH2", "CZ3", "1"), ("CZ3", "CE3", "2"), ("CE3", "CD2", "1"),
        ],
        "ASP": [("CG", "OD1", "1"), ("CG", "OD2", "1")],
        "GLU": [("CD", "OE1", "1"), ("CD", "OE2", "1")],
        "ASN": [("CG", "OD1", "2"), ("CG", "ND2", "1")],
        "GLN": [("CD", "OE1", "2"), ("CD", "NE2", "1")],
    }

    for (subst_id, resn), res_atoms in residue_atoms.items():
        _unused = subst_id
        for spec in residue_bond_templates.get(resn, []):
            set_pair(res_atoms, spec[0], spec[1], spec[2])

    for bond in bond_rows:
        new_parts = [
            str(bond["bond_id"]),
            str(bond["a1"]),
            str(bond["a2"]),
            str(bond["type"]),
        ]
        if bond["extra"]:
            new_parts.extend(bond["extra"])
        lines[bond["line_idx"]] = " ".join(new_parts)

    out = "\n".join(lines)
    if str(mol2_text).endswith("\n"):
        out += "\n"
    return out


def load_exclusion_patterns(path):
    if not path:
        return [], {"exclude_patterns_loaded": 0, "exclude_pattern_parse_failures": 0}
    if not os.path.exists(path):
        raise FileNotFoundError(f"Exclude file not found: {path}")

    aliases = {
        "phenol": "Oc1ccccc1",
        
    }

    patterns = []
    parse_failures = 0
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            key = line.lower()
            candidate = aliases.get(key, line)
            pmol = Chem.MolFromSmiles(candidate)
            if pmol is None:
                parse_failures += 1
                eprint(f"Warning: could not parse exclusion pattern '{line}'")
                continue
            canon = Chem.MolToSmiles(pmol, isomericSmiles=True)
            patterns.append({"raw": line, "canonical": canon, "mol": pmol})

    # Deduplicate by canonical motif.
    dedup = {}
    for p in patterns:
        dedup[p["canonical"]] = p
    out = list(dedup.values())
    return out, {
        "exclude_patterns_loaded": int(len(out)),
        "exclude_pattern_parse_failures": int(parse_failures),
    }


def match_exclusion_pattern(mol, patterns, mode="substructure"):
    if mol is None or not patterns:
        return None
    if mode != "substructure":
        return None
    for patt in patterns:
        try:
            if mol.HasSubstructMatch(patt["mol"]):
                return patt
        except Exception:
            continue
    return None


def first_present_prop(mol, prop_names):
    for p in prop_names:
        if mol.HasProp(p):
            v = mol.GetProp(p)
            if str(v).strip() != "":
                return v, p
    return None, None


def first_present_numeric_prop(mol, prop_names):
    for p in prop_names:
        if not mol.HasProp(p):
            continue
        value = safe_float(mol.GetProp(p))
        if value is not None:
            return value, p
    return None, None


def mol_name(mol, idx, id_prop=None):
    if id_prop and mol.HasProp(id_prop):
        v = mol.GetProp(id_prop).strip()
        if v:
            return v
    for p in ["_Name", "TITLE", "Title", "name", "Name", "ID", "Id", "Compound_ID", "compound_id", "s_m_title"]:
        if mol.HasProp(p):
            v = mol.GetProp(p).strip()
            if v:
                return v
    return f"Mol_{idx + 1}"


def get_scaffold(mol):
    try:
        scaf = MurckoScaffold.GetScaffoldForMol(mol)
        if scaf is None or scaf.GetNumAtoms() == 0:
            return None
        Chem.SanitizeMol(scaf)
        return scaf
    except Exception:
        return None


def generic_scaffold_smiles(scaf):
    try:
        g = MurckoScaffold.MakeScaffoldGeneric(scaf)
        return Chem.MolToSmiles(g, isomericSmiles=False)
    except Exception:
        return None


def exact_scaffold_smiles(scaf):
    try:
        return Chem.MolToSmiles(scaf, isomericSmiles=True)
    except Exception:
        return None


def scaffold_match(mol, scaf):
    try:
        matches = mol.GetSubstructMatches(scaf, useChirality=False)
    except Exception:
        return None
    if not matches:
        return None
    return sorted(matches)[0]


def collect_substituent_atoms(mol, start_idx, blocked_set):
    visited = set()
    stack = [start_idx]
    while stack:
        aidx = stack.pop()
        if aidx in visited or aidx in blocked_set:
            continue
        visited.add(aidx)
        atom = mol.GetAtomWithIdx(aidx)
        for nbr in atom.GetNeighbors():
            nidx = nbr.GetIdx()
            if nidx not in visited and nidx not in blocked_set:
                stack.append(nidx)
    return visited


def fragment_smiles_from_atoms(mol, atom_ids):
    if not atom_ids:
        return None
    atom_ids = sorted(atom_ids)
    bond_ids = []
    aset = set(atom_ids)
    for b in mol.GetBonds():
        a1 = b.GetBeginAtomIdx()
        a2 = b.GetEndAtomIdx()
        if a1 in aset and a2 in aset:
            bond_ids.append(b.GetIdx())
    try:
        smi = Chem.MolFragmentToSmiles(
            mol,
            atomsToUse=atom_ids,
            bondsToUse=bond_ids,
            canonical=True,
            isomericSmiles=True,
            allHsExplicit=False,
            allBondsExplicit=False,
        )
        return smi
    except Exception:
        return None


def extract_position_substituents(mol, scaf):
    match = scaffold_match(mol, scaf)
    if match is None:
        return {}, None
    scaffold_atom_to_mol = {sidx: midx for sidx, midx in enumerate(match)}
    mol_scaffold_atoms = set(match)
    pos_map = defaultdict(list)

    for sidx, midx in scaffold_atom_to_mol.items():
        atom = mol.GetAtomWithIdx(midx)
        for nbr in atom.GetNeighbors():
            nidx = nbr.GetIdx()
            if nidx in mol_scaffold_atoms:
                continue
            frag_atoms = collect_substituent_atoms(mol, nidx, mol_scaffold_atoms)
            frag_smi = fragment_smiles_from_atoms(mol, frag_atoms)
            if frag_smi:
                pos_map[sidx].append(frag_smi)

    norm = {k: tuple(sorted(v)) for k, v in pos_map.items() if v}
    return norm, match


def substitution_signature(pos_map):
    if not pos_map:
        return "NO_SUBSTITUENTS"
    parts = []
    for pos in sorted(pos_map):
        frags = ".".join(pos_map[pos])
        parts.append(f"R{pos + 1}={frags}")
    return " | ".join(parts)


def _count_hbd_lipinski_strict(mol):
    """Count H-bond donors using Lipinski definition: NH2 = 2, NH/OH = 1 each."""
    mol_h = Chem.AddHs(Chem.Mol(mol))
    hbd = 0
    for atom in mol_h.GetAtoms():
        if atom.GetSymbol() == 'N' and atom.GetTotalDegree() <= 3:
            explicit_h = sum(1 for neighbor in atom.GetNeighbors() if neighbor.GetSymbol() == 'H')
            if explicit_h >= 1:
                hbd += explicit_h
        elif atom.GetSymbol() == 'O' and atom.GetTotalDegree() <= 2:
            explicit_h = sum(1 for neighbor in atom.GetNeighbors() if neighbor.GetSymbol() == 'H')
            if explicit_h == 1:
                hbd += 1
    return hbd


def descriptor_dict(mol):
    try:
        # Use Lipinski donor counting with explicit NH2 = 2 handling.
        hbd_count = float(_count_hbd_lipinski_strict(mol))
        # pH-7 neutrality via MolStandardize Uncharger (removes reversible protonation;
        # permanently charged groups such as quaternary ammonium remain charged).
        try:
            _neutral = _UNCHARGER.uncharge(mol)
            is_neutral_ph7 = (Chem.GetFormalCharge(_neutral) == 0)
        except Exception:
            is_neutral_ph7 = (Chem.GetFormalCharge(mol) == 0)
        return {
            "mol_wt": float(Descriptors.MolWt(mol)),
            "clogp": float(Crippen.MolLogP(mol)),
            "tpsa": float(rdMolDescriptors.CalcTPSA(mol)),
            "hbd": hbd_count,
            "hba": float(Lipinski.NumHAcceptors(mol)),
            "rot_bonds": float(Lipinski.NumRotatableBonds(mol)),
            "rings": float(rdMolDescriptors.CalcNumRings(mol)),
            "heavy_atoms": float(mol.GetNumHeavyAtoms()),
            "formal_charge": float(Chem.GetFormalCharge(mol)),
            "is_neutral_ph7": is_neutral_ph7,
            "fsp3": float(rdMolDescriptors.CalcFractionCSP3(mol)),
        }
    except Exception:
        return {
            "mol_wt": None,
            "clogp": None,
            "tpsa": None,
            "hbd": None,
            "hba": None,
            "rot_bonds": None,
            "rings": None,
            "heavy_atoms": None,
            "formal_charge": None,
            "is_neutral_ph7": None,
            "fsp3": None,
        }


def filter_values_from_sdf_or_descriptors(mol, descriptors):
    mw, mw_src = first_present_numeric_prop(mol, _FILTER_PROP_CANDIDATES["mol_wt"])
    rot, rot_src = first_present_numeric_prop(mol, _FILTER_PROP_CANDIDATES["rot_bonds"])
    hbd, hbd_src = first_present_numeric_prop(mol, _FILTER_PROP_CANDIDATES["hbd"])
    hba, hba_src = first_present_numeric_prop(mol, _FILTER_PROP_CANDIDATES["hba"])

    return {
        "filter_mol_wt": mw if mw is not None else descriptors.get("mol_wt"),
        "filter_rot_bonds": rot if rot is not None else descriptors.get("rot_bonds"),
        "filter_hbd": hbd if hbd is not None else descriptors.get("hbd"),
        "filter_hba": hba if hba is not None else descriptors.get("hba"),
        "filter_mol_wt_source": mw_src or "rdkit",
        "filter_rot_bonds_source": rot_src or "rdkit",
        "filter_hbd_source": hbd_src or "rdkit",
        "filter_hba_source": hba_src or "rdkit",
    }


def _normalize_sd_prop_list(values):
    out = []
    seen = set()
    for value in values or []:
        for part in str(value or "").split(","):
            text = part.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(text)
    return out


# SDF property names to extract for the HTML properties panel.
_REPORT_PROP_NAMES = [
    "GS_LogD", "GS_Sol_74_linear", "GS_CACO2_A2B_10_linear", "GS_CACO2_B2A_10_linear",
    "GS_HP_Free_LT_linear", "GS_CACO2_A2B_1_linear", "GS_CACO2_B2A_1_linear",
    "GS_HP_Free_linear", "GS_Pred_Cl_HLM_linear", "GS_MDCK_linear", "GS_RED_HP_linear",
    "interaction_count",
    "MW", "cLogP", "TPSA", "HBD", "HBA", "RotBonds", "HeavyAtoms", "FormalCharge",
    "RingCount", "FractionCSP3",
]


def _extract_mol_props_for_report(sdf_path, mol_df, scaf_df, numeric_prop_names, text_prop_names, run_started):
    """Read named SDF properties for all mol_df molecules; build scaffold→mol_id map.

    Returns
    -------
    tuple
        (mol_props_data, scaffold_mol_map, mol_text_props_data, text_prop_value_counts)
        mol_props_data : {mol_id: [float|None, ...]} value list indexed by numeric_prop_names order
        scaffold_mol_map : {scaffold_name: [mol_id, ...]} all members per scaffold
        mol_text_props_data : {mol_id: {prop_name: value_text}}
        text_prop_value_counts : {prop_name: [{"value": text, "count": n}, ...]}
    """
    # Build scaffold_name map from scaf_df.
    scaf_name_map: dict = {}
    if (
        scaf_df is not None and not scaf_df.empty
        and "scaffold_id" in scaf_df.columns and "scaffold_name" in scaf_df.columns
    ):
        scaf_name_map = scaf_df.set_index("scaffold_id")["scaffold_name"].to_dict()

    # Build scaffold_mol_map from mol_df.
    scaffold_mol_map: dict = {}
    if scaf_name_map and "scaffold_id" in mol_df.columns and "mol_id" in mol_df.columns:
        for sid, grp in mol_df.groupby("scaffold_id", dropna=True):
            sname = scaf_name_map.get(sid)
            if sname:
                scaffold_mol_map[str(sname)] = grp["mol_id"].tolist()

    # Build mol_index → mol_id lookup from mol_df.
    idx_to_id: dict = {}
    if "mol_index" in mol_df.columns and "mol_id" in mol_df.columns:
        for idx_val, id_val in zip(mol_df["mol_index"], mol_df["mol_id"]):
            try:
                idx_to_id[int(idx_val)] = str(id_val)
            except (ValueError, TypeError):
                pass

    if not idx_to_id:
        return {}, scaffold_mol_map

    interaction_count_map = {}
    if "mol_id" in mol_df.columns and "interaction_count" in mol_df.columns:
        for mol_id, count_val in zip(mol_df["mol_id"], mol_df["interaction_count"]):
            mol_id_txt = str(mol_id)
            if mol_id_txt in interaction_count_map:
                continue
            parsed = safe_float(count_val)
            interaction_count_map[mol_id_txt] = float(parsed) if parsed is not None else 0.0

    needed = set(idx_to_id.keys())
    mol_props_data: dict = {}
    mol_text_props_data: dict = {}
    text_value_counters = {prop: Counter() for prop in text_prop_names}
    text_value_display = {prop: {} for prop in text_prop_names}
    n_found = 0
    n_total = len(needed)
    try:
        suppl = Chem.SDMolSupplier(sdf_path, removeHs=False, sanitize=False)
        for i, mol in enumerate(suppl):
            if i not in needed:
                continue
            mol_id = idx_to_id[i]
            vals = []
            for p in numeric_prop_names:
                if p == "interaction_count":
                    vals.append(round(interaction_count_map.get(mol_id, 0.0), 5))
                    continue
                if mol is not None and mol.HasProp(p):
                    try:
                        vals.append(round(float(mol.GetProp(p)), 5))
                    except (ValueError, TypeError):
                        vals.append(None)
                else:
                    vals.append(None)
            mol_props_data[mol_id] = vals

            text_props_for_mol = {}
            for p in text_prop_names:
                if mol is None or not mol.HasProp(p):
                    continue
                raw_text = str(mol.GetProp(p) or "").strip()
                if not raw_text:
                    continue
                norm_text = raw_text.lower()
                text_value_counters[p][norm_text] += 1
                if norm_text not in text_value_display[p]:
                    text_value_display[p][norm_text] = raw_text
                text_props_for_mol[p] = raw_text
            if text_props_for_mol:
                mol_text_props_data[mol_id] = text_props_for_mol

            n_found += 1
            if n_found >= n_total:
                break
    except Exception as exc:
        eprint(f"Warning: property extraction for HTML panel failed: {exc}")
        return {}, scaffold_mol_map, {}, {}

    text_prop_value_counts = {}
    for prop in text_prop_names:
        counts = text_value_counters.get(prop, Counter())
        displays = text_value_display.get(prop, {})
        sorted_items = sorted(
            counts.items(),
            key=lambda kv: (-kv[1], displays.get(kv[0], kv[0]).lower()),
        )
        text_prop_value_counts[prop] = [
            {"value": displays.get(norm_val, norm_val), "count": int(count)}
            for norm_val, count in sorted_items
        ]

    progress_log(
        run_started,
        "Props panel data ready",
        extra=(
            f"molecules={n_found} numeric_props={len(numeric_prop_names)} "
            f"text_props={len(text_prop_names)}"
        ),
    )
    return mol_props_data, scaffold_mol_map, mol_text_props_data, text_prop_value_counts


def detect_protein_format_from_path(path):
    """Return 3Dmol parser token inferred from file extension."""
    ext = os.path.splitext(str(path or ""))[1].strip().lower()
    if ext == ".mol2":
        return "mol2"
    return "pdb"


def _dssp_code_to_3dmol_ss(code):
    code = str(code or "").strip().upper()
    if code in {"H", "G", "I"}:
        return "h"
    if code in {"E", "B"}:
        return "s"
    return "c"


def parse_mol2_secondary_structure_map_mdtraj(mol2_path):
    """Build chain|resi -> ss map from MOL2 using MDTraj DSSP.

    Returns
    -------
    tuple(dict, dict)
        (ss_map, stats) where stats includes counts for residue coverage.
    """
    stats = {
        "source": "mdtraj",
        "total_residues": 0,
        "protein_residues": 0,
        "assigned_residues": 0,
        "helix_residues": 0,
        "sheet_residues": 0,
        "coil_residues": 0,
    }
    ss_map = {}

    if md is None:
        raise RuntimeError("mdtraj is not installed; install it to enable MOL2-based DSSP")

    traj = md.load(mol2_path)
    topology = traj.topology
    stats["total_residues"] = int(topology.n_residues)
    residues = list(topology.residues)
    if not residues:
        return ss_map, stats

    # simplified=False keeps full DSSP classes (H/E/G/I/B/T/S/space).
    dssp = md.compute_dssp(traj, simplified=False)
    if dssp is None or len(dssp) == 0:
        return ss_map, stats
    codes = dssp[0]

    chain_resi_ss = {}
    by_resi = {}
    protein_like = 0
    assigned = 0
    for res, dssp_code in zip(residues, codes):
        raw = str(dssp_code or "").strip().upper()
        if raw in {"NA", "NONE"}:
            continue
        protein_like += 1
        ss = _dssp_code_to_3dmol_ss(dssp_code)
        resi = int(getattr(res, "resSeq", -1))
        if resi < 0:
            continue
        chain_obj = getattr(res, "chain", None)
        chain_name = getattr(chain_obj, "chain_id", None)
        if chain_name is None or str(chain_name).strip() == "":
            chain_name = getattr(chain_obj, "name", None)
        if chain_name is None or str(chain_name).strip() == "":
            chain_name = getattr(chain_obj, "index", None)
        chain_token = str(chain_name).strip() if chain_name is not None else "_"
        if not chain_token:
            chain_token = "_"
        chain_resi_ss[(chain_token, resi)] = ss
        if resi not in by_resi:
            by_resi[resi] = ss
        assigned += 1
        if ss == "h":
            stats["helix_residues"] += 1
        elif ss == "s":
            stats["sheet_residues"] += 1
        else:
            stats["coil_residues"] += 1

    for (chain_token, resi), ss in chain_resi_ss.items():
        ss_map[f"{chain_token}|{resi}"] = ss
    # Add chain-agnostic fallback keys for MOL2 files where chain IDs are blank.
    for resi, ss in by_resi.items():
        ss_map.setdefault(f"_|{resi}", ss)

    stats["protein_residues"] = int(protein_like)
    stats["assigned_residues"] = int(max(len(by_resi), assigned))
    return ss_map, stats


def build_manifest(args, n_mols, n_scaffolds):
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input_sdf": os.path.abspath(args.input),
        "n_molecules": n_mols,
        "n_scaffolds": n_scaffolds,
        "parameters": vars(args),
    }


def process_sdf_chunk(sdf_path, indices, score_props, id_prop, cluster_prop,
                      exclude_smiles_list, generate_images):
    """Process a list of molecule indices from an SDF file.

    Top-level (picklable) worker for ProcessPoolExecutor.
    Exclusion patterns are passed as canonical SMILES strings and re-parsed
    locally because RDKit Mol objects cannot cross process boundaries.

    Returns
    -------
    tuple: (rows, n_bad, excluded_count, excluded_counter, prop_names_set)
    """
    # Re-build exclusion pattern mols locally.
    local_patterns = []
    for smi in exclude_smiles_list:
        pmol = Chem.MolFromSmiles(smi)
        if pmol is not None:
            local_patterns.append({"raw": smi, "canonical": smi, "mol": pmol})

    suppl = Chem.SDMolSupplier(sdf_path, removeHs=False)
    rows = []
    n_bad = 0
    excluded_count = 0
    excluded_counter = Counter()
    prop_names = set()

    for i in indices:
        mol = suppl[i]
        if mol is None:
            n_bad += 1
            continue
        for p in mol.GetPropNames():
            prop_names.add(p)
        try:
            Chem.SanitizeMol(mol)
        except Exception:
            pass

        hit = match_exclusion_pattern(mol, local_patterns, mode=DEFAULT_EXCLUDE_MATCH_MODE)
        if hit is not None:
            excluded_count += 1
            excluded_counter[hit["canonical"]] += 1
            continue

        mid = mol_name(mol, i, id_prop)
        cluster_id = None
        if cluster_prop and mol.HasProp(cluster_prop):
            cluster_id = mol.GetProp(cluster_prop)

        raw_score, score_prop_used = first_present_prop(mol, score_props)
        score = safe_float(raw_score)

        scaf = get_scaffold(mol)
        if scaf is None:
            exact_scaf = None
            generic_scaf = None
            pos_map = {}
            sub_sig = "NO_SCAFFOLD"
            scaf_id = "NO_SCAFFOLD"
        else:
            exact_scaf = exact_scaffold_smiles(scaf)
            generic_scaf = generic_scaffold_smiles(scaf)
            pos_map, _ = extract_position_substituents(mol, scaf)
            sub_sig = substitution_signature(pos_map)
            scaf_id = exact_scaf

        try:
            smiles = Chem.MolToSmiles(Chem.RemoveHs(Chem.Mol(mol)), isomericSmiles=True)
        except Exception:
            smiles = None

        try:
            mol_png = mol_png_base64(mol, legend=mid) if generate_images else None
        except Exception:
            mol_png = None

        descriptors = descriptor_dict(mol)
        filter_values = filter_values_from_sdf_or_descriptors(mol, descriptors)

        rows.append(
            {
                "mol_index": i,
                "mol_id": mid,
                "mol_id_norm": normalize_id(mid),
                "smiles": smiles,
                "score": score,
                "score_prop_used": score_prop_used,
                "cluster_id": cluster_id,
                "scaffold_id": scaf_id,
                "exact_scaffold_smiles": exact_scaf,
                "generic_scaffold_smiles": generic_scaf,
                "substitution_signature": sub_sig,
                "substitution_map": dict(pos_map),
                "mol_png_b64": mol_png,
                **descriptors,
                **filter_values,
            }
        )

    return rows, n_bad, excluded_count, excluded_counter, prop_names


def _convert_pdb_to_mol2_with_obabel(pdb_path, outdir, file_prefix, run_started, output_tag=None):
    """Convert protein PDB to MOL2 using Open Babel, returning output path or None."""
    obabel_bin = shutil.which("obabel") or shutil.which("babel")
    if not obabel_bin:
        eprint("Warning: Open Babel CLI (obabel/babel) not found; using provided protein format.")
        return None

    try:
        os.makedirs(outdir, exist_ok=True)
    except Exception:
        pass

    tag = str(output_tag or Path(str(pdb_path)).stem or "protein").strip()
    tag = re.sub(r"[^A-Za-z0-9_.-]+", "_", tag)
    out_name = prefixed_output_name(file_prefix, f"protein_{tag}_obabel.mol2")
    out_path = os.path.join(outdir, out_name)
    cmd = [obabel_bin, "-ipdb", str(pdb_path), "-omol2", "-O", out_path]
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except Exception as exc:
        eprint(f"Warning: failed to launch Open Babel for PDB->MOL2 conversion: {exc}")
        return None

    if proc.returncode != 0 or not os.path.isfile(out_path):
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        detail = stderr or stdout or f"exit_code={proc.returncode}"
        eprint(f"Warning: Open Babel conversion failed ({detail}). Using provided protein format.")
        return None

    progress_log(
        run_started,
        "Protein converted to MOL2",
        extra=f"tool={os.path.basename(obabel_bin)} file={os.path.basename(out_path)}",
    )
    return out_path


def load_protein_assets(args, run_started):
    protein_pdb_text = None
    protein_cartoon_pdb_text = None
    protein_structure_format = "pdb"
    protein_ss_map = {}
    protein_sources = []
    protein_paths = _parse_protein_pdb_inputs(args.protein_pdb)
    args._protein_pdb_list = protein_paths

    for source_idx, protein_input_path in enumerate(protein_paths, start=1):
        runtime_path = protein_input_path
        runtime_format = detect_protein_format_from_path(runtime_path) if runtime_path else "pdb"
        interaction_pdb_path = protein_input_path
        cartoon_text = None
        runtime_text = None
        ss_map = {}

        if protein_input_path and runtime_format == "pdb":
            try:
                with open(protein_input_path, "r", encoding="utf-8", errors="replace") as pfh:
                    source_pdb_text = pfh.read()
                cartoon_text = source_pdb_text
                progress_log(
                    run_started,
                    "Protein cartoon PDB loaded",
                    extra=f"file={os.path.basename(protein_input_path)} (source PDB for cartoon)",
                )
            except Exception as exc:
                eprint(f"Warning: could not read source PDB for cartoon rendering '{protein_input_path}': {exc}")

            protein_runtime_input_path = protein_input_path

            converted_mol2 = _convert_pdb_to_mol2_with_obabel(
                protein_runtime_input_path,
                args.outdir,
                args.file_prefix,
                run_started,
                output_tag=f"{source_idx}_{Path(str(protein_input_path)).stem}",
            )
            if converted_mol2:
                runtime_path = converted_mol2
                runtime_format = "mol2"
            else:
                runtime_path = protein_runtime_input_path
                runtime_format = "pdb"

        if runtime_path:
            try:
                with open(runtime_path, "r", encoding="utf-8", errors="replace") as pfh:
                    runtime_text = pfh.read()
                if runtime_format == "mol2" and runtime_text:
                    inferred_runtime_text = _infer_protein_mol2_bond_orders(runtime_text)
                    if inferred_runtime_text != runtime_text:
                        write_path = runtime_path
                        if protein_input_path and os.path.abspath(str(runtime_path)) == os.path.abspath(str(protein_input_path)):
                            write_name = prefixed_output_name(
                                args.file_prefix,
                                f"protein_{source_idx}_{Path(str(protein_input_path)).stem}_runtime.mol2",
                            )
                            write_path = os.path.join(args.outdir, write_name)
                        try:
                            with open(write_path, "w", encoding="utf-8") as pfh:
                                pfh.write(inferred_runtime_text)
                            runtime_path = write_path
                            runtime_text = inferred_runtime_text
                            progress_log(
                                run_started,
                                "Protein MOL2 bond orders updated",
                                extra=f"file={os.path.basename(write_path)}",
                            )
                        except Exception as exc:
                            eprint(f"Warning: could not persist inferred MOL2 bond orders to '{write_path}': {exc}")
                            runtime_text = inferred_runtime_text
                progress_log(
                    run_started,
                    "Protein structure loaded",
                    extra=f"file={os.path.basename(runtime_path)} format={runtime_format}",
                )
            except Exception as exc:
                eprint(f"Warning: could not read protein structure '{runtime_path}': {exc}")

        if runtime_path and runtime_format == "mol2":
            try:
                ss_map, ss_stats = parse_mol2_secondary_structure_map_mdtraj(runtime_path)
                progress_log(
                    run_started,
                    "Protein SS map computed",
                    extra=(
                        f"source=mdtraj file={os.path.basename(runtime_path)} "
                        f"assigned={ss_stats.get('assigned_residues', 0)} "
                        f"helix={ss_stats.get('helix_residues', 0)} "
                        f"sheet={ss_stats.get('sheet_residues', 0)} "
                        f"coil={ss_stats.get('coil_residues', 0)}"
                    ),
                )
            except Exception as exc:
                eprint(
                    "Warning: MDTraj secondary structure computation failed for "
                    f"'{runtime_path}': {exc}. Falling back to JS geometry-based SS assignment."
                )

        if runtime_format == "mol2" and cartoon_text is None and runtime_path:
            stem = os.path.splitext(runtime_path)[0]
            companion_pdb = stem + ".pdb"
            if os.path.isfile(companion_pdb):
                try:
                    with open(companion_pdb, "r", encoding="utf-8", errors="replace") as pfh:
                        cartoon_text = pfh.read()
                    progress_log(
                        run_started,
                        "Protein cartoon PDB loaded",
                        extra=f"file={os.path.basename(companion_pdb)} (auto-detected for cartoon backbone)",
                    )
                except Exception as exc:
                    eprint(f"Warning: could not read companion cartoon PDB '{companion_pdb}': {exc}")

        protein_sources.append(
            {
                "id": f"protein-{source_idx}",
                "label": os.path.basename(str(protein_input_path)),
                "chem_text": runtime_text or "",
                "chem_format": runtime_format,
                "cartoon_text": cartoon_text or "",
                "ss_map": ss_map or {},
                "original_path": str(protein_input_path),
                "runtime_path": str(runtime_path or ""),
                "interaction_pdb_path": str(interaction_pdb_path or ""),
            }
        )

    first_source = protein_sources[0] if protein_sources else None
    if first_source:
        protein_pdb_text = first_source.get("chem_text") or None
        protein_cartoon_pdb_text = first_source.get("cartoon_text") or None
        protein_structure_format = str(first_source.get("chem_format") or "pdb")
        protein_ss_map = first_source.get("ss_map") or {}
        args._protein_runtime_path = first_source.get("runtime_path")
        args._protein_runtime_format = protein_structure_format
        args._protein_original_path = first_source.get("original_path")
        args._protein_interaction_pdb_path = first_source.get("interaction_pdb_path")
    else:
        args._protein_runtime_path = None
        args._protein_runtime_format = "pdb"
        args._protein_original_path = None
        args._protein_interaction_pdb_path = None

    args._protein_sources = protein_sources
    return protein_pdb_text, protein_cartoon_pdb_text, protein_structure_format, protein_ss_map, protein_sources


def _load_pi_interaction_module():
    """Load the local pi-pi interaction module from its hyphenated filename."""
    module_path = Path(__file__).resolve().with_name("pi-pi_interaction.py")
    if not module_path.exists():
        return None
    module_name = "pi_pi_interaction"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, str(module_path))
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def _serialize_interaction_payload(payload):
    out = dict(payload)
    for key in ("proteinAtomSerials", "ligandAtomSerials", "residueKeys"):
        val = out.get(key)
        if isinstance(val, set):
            out[key] = sorted(val)
    return out


def _precompute_pose_interactions_for_source(task):
    """Worker: precompute interactions for one protein source across pose indices."""
    source_id, source_label, interaction_pdb_path, input_sdf, pose_order = task
    module = _load_pi_interaction_module()
    if module is None:
        return source_id, {}, f"pi-pi module unavailable for '{source_label}'"
    try:
        protein_atoms = module.parse_pdb_atoms(Path(interaction_pdb_path))
        protein_rings = module.build_protein_aromatic_rings(protein_atoms)
    except Exception as exc:
        return source_id, {}, f"failed to parse protein '{source_label}' for precomputed interactions: {exc}"

    supplier = Chem.SDMolSupplier(input_sdf, removeHs=False)
    source_out = {}
    for pose_idx in pose_order:
        if pose_idx < 0 or pose_idx >= len(supplier):
            continue
        mol = supplier[pose_idx]
        if mol is None or mol.GetNumConformers() == 0:
            continue
        try:
            ligand_atoms, ligand_rings = module.ligand_atoms_and_rings(mol)
            interactions = module.classify_interactions(
                protein_atoms,
                ligand_atoms,
                protein_rings,
                ligand_rings,
                include_non_pi=True,
            )
            source_out[str(pose_idx)] = {k: _serialize_interaction_payload(v) for k, v in interactions.items()}
        except Exception:
            continue
    return source_id, source_out, None


def _precompute_pose_interactions(args, pose_indices, run_started):
    """Precompute pose interaction payloads for report visualizer tabs.

    Returns
    -------
    dict
        Mapping of string pose index -> viewer-compatible interaction payload.
    """
    if not pose_indices:
        return {}
    protein_sources = list(getattr(args, "_protein_sources", None) or [])
    if not protein_sources:
        protein_paths = getattr(args, "_protein_pdb_list", None) or _parse_protein_pdb_inputs(args.protein_pdb)
        primary_protein = getattr(args, "_protein_interaction_pdb_path", None) or (protein_paths[0] if protein_paths else None)
        if primary_protein:
            protein_sources = [
                {
                    "id": "default",
                    "label": os.path.basename(str(primary_protein)),
                    "interaction_pdb_path": str(primary_protein),
                    "original_path": str(primary_protein),
                }
            ]
    if not protein_sources:
        return {}

    module = _load_pi_interaction_module()
    if module is None:
        eprint("Warning: could not load pi-pi_interaction.py; falling back to JS runtime interactions.")
        return {}

    progress_log(
        run_started,
        "Precompute interactions started",
        extra=f"poses={len(pose_indices)} proteins={len(protein_sources)}",
    )
    pose_order = sorted(int(i) for i in pose_indices)
    out_by_source = {}
    source_tasks = []
    for source_idx, source in enumerate(protein_sources, start=1):
        source_id = str(source.get("id") or f"protein-{source_idx}")
        source_label = str(source.get("label") or source_id)
        interaction_pdb_path = str(source.get("interaction_pdb_path") or source.get("original_path") or "").strip()
        if not interaction_pdb_path:
            continue
        if detect_protein_format_from_path(interaction_pdb_path) != "pdb":
            eprint(
                f"Warning: skipping precomputed interactions for '{source_label}' (requires PDB input; got {os.path.basename(interaction_pdb_path)})."
            )
            continue
        source_tasks.append((source_id, source_label, interaction_pdb_path, args.input, pose_order))

    if not source_tasks:
        return {}

    n_workers = max(1, int(args.n_workers) if int(getattr(args, "n_workers", 0) or 0) > 0 else (os.cpu_count() or 2))
    max_workers = max(1, min(n_workers, len(source_tasks)))
    if max_workers > 1 and len(source_tasks) > 1:
        progress_log(run_started, "Precompute interactions", extra=f"parallel workers={max_workers}")
        with ProcessPoolExecutor(max_workers=max_workers) as ex:
            fut_map = {ex.submit(_precompute_pose_interactions_for_source, task): task for task in source_tasks}
            done_sources = 0
            for fut in as_completed(fut_map):
                source_id, source_label, _pdb_path, _input, _poses = fut_map[fut]
                try:
                    out_id, source_out, err = fut.result()
                except Exception as exc:
                    eprint(f"Warning: interaction precompute worker failed for protein '{source_label}': {exc}")
                    done_sources += 1
                    continue
                if err:
                    eprint(f"Warning: {err}")
                if source_out:
                    out_by_source[out_id] = source_out
                done_sources += 1
                progress_log(
                    run_started,
                    "Precompute interactions",
                    done=done_sources,
                    total=len(source_tasks),
                    extra=f"protein={source_label}",
                )
    else:
        for task in source_tasks:
            source_id, source_label, _pdb_path, _input, _poses = task
            out_id, source_out, err = _precompute_pose_interactions_for_source(task)
            if err:
                eprint(f"Warning: {err}")
            if source_out:
                out_by_source[out_id] = source_out
            progress_log(
                run_started,
                "Precompute interactions",
                done=len(out_by_source),
                total=len(source_tasks),
                extra=f"protein={source_label}",
            )

    progress_log(
        run_started,
        "Precompute interactions complete",
        extra=f"proteins_with_data={len(out_by_source)}",
    )
    return out_by_source


def _stage_sdf_parse(args, exclude_patterns, exclude_meta, run_started):
    """
    Parse SDF file and create mol_df with all molecule properties.
    Returns: (mol_df, all_prop_names, merge_stats, sdf_stats)
    """
    n_workers = max(1, int(args.n_workers) if args.n_workers > 0 else (os.cpu_count() or 2))
    suppl = Chem.SDMolSupplier(args.input, removeHs=False)
    total_mols = len(suppl)
    sdf_loop_started = time.time()
    progress_log(run_started, "SDF parse", extra=f"total={total_mols} workers={n_workers}")

    score_props = resolve_score_props(suppl, total_mols, args.score_props, args.auto_detect_score)
    exclude_smiles_list = [p["canonical"] for p in exclude_patterns]

    rows = []
    n_bad = 0
    all_prop_names: set = set()
    excluded_by_smiles_rules = 0
    excluded_pattern_counter: Counter = Counter()

    if n_workers > 1 and total_mols > 1:
        chunk_size = math.ceil(total_mols / n_workers)
        chunks = [
            list(range(start, min(start + chunk_size, total_mols)))
            for start in range(0, total_mols, chunk_size)
        ]
        chunk_results: list = [None] * len(chunks)
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            fut_to_idx = {
                pool.submit(
                    process_sdf_chunk,
                    args.input,
                    chunk,
                    score_props,
                    args.id_prop,
                    args.cluster_prop,
                    exclude_smiles_list,
                    args.generate_all_mol_images,
                ): cidx
                for cidx, chunk in enumerate(chunks)
            }
            done_chunks = 0
            for fut in as_completed(fut_to_idx):
                cidx = fut_to_idx[fut]
                chunk_results[cidx] = fut.result()
                done_chunks += 1
                approx_done = min(done_chunks * chunk_size, total_mols)
                progress_log(run_started, "SDF parse", done=approx_done, total=total_mols)
        for chunk_rows, chunk_bad, chunk_excl, chunk_excl_ctr, chunk_props in chunk_results:
            rows.extend(chunk_rows)
            n_bad += chunk_bad
            excluded_by_smiles_rules += chunk_excl
            excluded_pattern_counter.update(chunk_excl_ctr)
            all_prop_names.update(chunk_props)
        rows.sort(key=lambda r: r["mol_index"])
    else:
        progress_every = 1000
        for i, mol in enumerate(suppl):
            if i > 0 and i % progress_every == 0:
                elapsed = max(1e-9, time.time() - sdf_loop_started)
                rate = i / elapsed
                progress_log(
                    run_started,
                    "SDF parse",
                    done=i,
                    extra=f"kept={len(rows)} excluded={excluded_by_smiles_rules} invalid={n_bad} rate={rate:.0f}/s",
                )
            if mol is None:
                n_bad += 1
                continue
            for p in mol.GetPropNames():
                all_prop_names.add(p)
            try:
                Chem.SanitizeMol(mol)
            except Exception:
                pass

            hit = match_exclusion_pattern(mol, exclude_patterns, mode=DEFAULT_EXCLUDE_MATCH_MODE)
            if hit is not None:
                excluded_by_smiles_rules += 1
                excluded_pattern_counter[hit["canonical"]] += 1
                continue

            mid = mol_name(mol, i, args.id_prop)
            cluster_id = None
            if args.cluster_prop and mol.HasProp(args.cluster_prop):
                cluster_id = mol.GetProp(args.cluster_prop)

            raw_score, score_prop_used = first_present_prop(mol, score_props)
            score = safe_float(raw_score)

            scaf = get_scaffold(mol)
            if scaf is None:
                exact_scaf = None
                generic_scaf = None
                pos_map = {}
                sub_sig = "NO_SCAFFOLD"
                scaf_id = "NO_SCAFFOLD"
            else:
                exact_scaf = exact_scaffold_smiles(scaf)
                generic_scaf = generic_scaffold_smiles(scaf)
                pos_map, _ = extract_position_substituents(mol, scaf)
                sub_sig = substitution_signature(pos_map)
                scaf_id = exact_scaf

            try:
                smiles = Chem.MolToSmiles(Chem.RemoveHs(Chem.Mol(mol)), isomericSmiles=True)
            except Exception:
                smiles = None

            try:
                if args.generate_all_mol_images:
                    mol_png = mol_png_base64(mol, legend=mid)
                else:
                    mol_png = None
            except Exception:
                mol_png = None

            descriptors = descriptor_dict(mol)
            filter_values = filter_values_from_sdf_or_descriptors(mol, descriptors)

            rows.append(
                {
                    "mol_index": i,
                    "mol_id": mid,
                    "mol_id_norm": normalize_id(mid),
                    "smiles": smiles,
                    "score": score,
                    "score_prop_used": score_prop_used,
                    "cluster_id": cluster_id,
                    "scaffold_id": scaf_id,
                    "exact_scaffold_smiles": exact_scaf,
                    "generic_scaffold_smiles": generic_scaf,
                    "substitution_signature": sub_sig,
                    "substitution_map": dict(pos_map),
                    "mol_png_b64": mol_png,
                    **descriptors,
                    **filter_values,
                }
            )

    if not rows:
        raise RuntimeError("No valid molecules were read from input SDF.")

    progress_log(
        run_started,
        "SDF parse complete",
        done=len(rows),
        extra=(
            f"excluded={excluded_by_smiles_rules} invalid={n_bad} "
            f"elapsed={format_elapsed(time.time() - sdf_loop_started)}"
        ),
    )

    mol_df = pd.DataFrame(rows)
    merge_stats = {
        "invalid_sdf_records": int(n_bad),
        "excluded_by_smiles_rules": int(excluded_by_smiles_rules),
        "exclude_patterns_loaded": int(exclude_meta.get("exclude_patterns_loaded", 0)),
        "exclude_pattern_parse_failures": int(exclude_meta.get("exclude_pattern_parse_failures", 0)),
        "matched_molecules": 0,
        "unmatched_molecules": int(len(mol_df)),
        "ext_rows": 0,
        "ext_unique_ids": 0,
        "ext_duplicate_ids": 0,
        "ext_matched_molecules": 0,
    }
    sdf_stats = {
        "n_bad": n_bad,
        "excluded_by_smiles_rules": excluded_by_smiles_rules,
        "excluded_pattern_counter": excluded_pattern_counter,
    }
    return mol_df, all_prop_names, merge_stats, sdf_stats


def _stage_merge_and_rank(mol_df, args, run_started, merge_stats):
    """
    Merge interaction data and compute ranking scores.
    Returns: (mol_df, report_mol_df, merge_stats)
    """
    ext_df, ext_meta = load_external_interaction_counts(
        args.interaction_csv,
        id_col=args.interaction_id_col,
        interaction_col=args.interaction_count_col,
        eprint=eprint,
    )
    merge_stats.update(ext_meta)
    mol_df, report_mol_df, merge_counts, precluster_hbd_violations = merge_and_rank_molecules(
        mol_df,
        ext_df,
        score_weight=DEFAULT_SCORE_WEIGHT,
        interaction_weight=DEFAULT_INTERACTION_WEIGHT,
        max_molecular_weight=args.max_molecular_weight,
        max_hbd=args.max_hbond_donors,
        max_hba=args.max_hbond_acceptors,
        max_rot_bonds=args.max_rotatable_bonds,
        max_formal_charge=None,
        neutral_only=False,
    )
    merge_stats.update(merge_counts)
    progress_log(
        run_started,
        "Interaction CSV merge complete",
        extra=f"matched={merge_stats['matched_molecules']} unmatched={merge_stats['unmatched_molecules']}",
    )
    if precluster_hbd_violations > 0:
        eprint(
            f"Warning: report pool contains {precluster_hbd_violations} molecules above HBD threshold ({args.max_hbond_donors}) before scaffold clustering."
        )

    return mol_df, report_mol_df, merge_stats, precluster_hbd_violations


def _stage_scaffold_analysis(report_mol_df, mol_df, scaf_img_dir, n_workers, args, run_started):
    """
    Build scaffold summaries, rankings, and panels.
    Returns: (scaf_df, central_df, global_reference_smiles)
    """
    progress_log(run_started, "Scaffold summary started")
    scaf_rows = []
    grouped_scaf = list(report_mol_df.groupby("scaffold_id", dropna=False))
    total_scaf_groups = len(grouped_scaf)

    if n_workers > 1 and total_scaf_groups > 1:
        progress_log(run_started, "Scaffold summary", extra=f"parallel workers={n_workers}")
        tasks = [(scaf_id, sdf.to_dict("records"), scaf_img_dir, args.file_prefix) for scaf_id, sdf in grouped_scaf]
        with ProcessPoolExecutor(max_workers=n_workers) as ex:
            fut_map = {ex.submit(build_scaffold_summary_row, task): idx for idx, task in enumerate(tasks, start=1)}
            done = 0
            for fut in as_completed(fut_map):
                done += 1
                row = fut.result()
                if row is not None:
                    scaf_rows.append(row)
                if done % 25 == 0 or done == total_scaf_groups:
                    progress_log(run_started, "Scaffold summary", done=done, total=total_scaf_groups)
    else:
        for scaf_idx, (scaf_id, sdf) in enumerate(grouped_scaf, start=1):
            if scaf_idx % 100 == 0:
                progress_log(run_started, "Scaffold summary", done=scaf_idx, total=total_scaf_groups)
            row = build_scaffold_summary_row((scaf_id, sdf.to_dict("records"), scaf_img_dir, args.file_prefix))
            if row is not None:
                scaf_rows.append(row)
    progress_log(run_started, "Scaffold summary complete", done=total_scaf_groups)

    scaf_df, central_df, _unused_unique_df, global_reference_smiles = initialize_scaffold_analysis(
        scaf_rows,
        report_mol_df,
        args,
        include_unique=False,
    )

    # Scaffold naming and re-ranking.
    scaf_df, central_df, global_reference_smiles = assign_scaffold_names_and_rerank(scaf_df, args)

    # Draw panels.
    progress_log(run_started, "Scaffold panel rendering started")
    top_scaf_ids = central_df.head(args.max_scaffolds_in_report)["scaffold_id"].tolist()
    panel_path_map: dict = {}

    def _draw_panel(sid):
        row_mask = scaf_df["scaffold_id"] == sid
        if not row_mask.any():
            return sid, None
        ex = scaf_df.loc[row_mask, "exact_scaffold_smiles"].iloc[0]
        if not ex:
            return sid, None
        try:
            scaf = Chem.MolFromSmiles(str(ex))
            sdf_sub = report_mol_df[report_mol_df["scaffold_id"] == sid]
            positions = scaf_df.loc[row_mask, "variable_positions"].iloc[0] or []
            panel_name = prefixed_output_name(args.file_prefix, f"scaffold_{hash_text(sid)}_panel.png")
            panel_path = os.path.join(scaf_img_dir, panel_name)
            draw_scaffold_panel(scaf, positions, sdf_sub, panel_path, top_n=4, global_reference_smiles=global_reference_smiles)
            return sid, os.path.join("scaffold_images", panel_name)
        except Exception as exc:
            eprint(f"Warning: could not draw scaffold panel for {sid}: {exc}")
            return sid, None

    panel_threads = max(1, min(n_workers, len(top_scaf_ids)))
    with ThreadPoolExecutor(max_workers=panel_threads) as panel_ex:
        panel_futs = {panel_ex.submit(_draw_panel, sid): i for i, sid in enumerate(top_scaf_ids, 1)}
        done_panels = 0
        for fut in as_completed(panel_futs):
            done_panels += 1
            sid, path = fut.result()
            if path:
                panel_path_map[sid] = path
            if done_panels % 5 == 0 or done_panels == len(top_scaf_ids):
                progress_log(run_started, "Scaffold panels", done=done_panels, total=len(top_scaf_ids))

    for sid, path in panel_path_map.items():
        row_mask = scaf_df["scaffold_id"] == sid
        scaf_df.loc[row_mask, "scaffold_panel_png"] = path

    progress_log(run_started, "Scaffold panel rendering complete", done=len(top_scaf_ids), total=len(top_scaf_ids))

    # Refresh with panel updates.
    scaf_df, central_df, global_reference_smiles = assign_scaffold_names_and_rerank(scaf_df, args)

    # Regenerate core images.
    if global_reference_smiles:
        for i, ex in scaf_df["exact_scaffold_smiles"].items():
            if not ex:
                continue
            try:
                scaf_df.at[i, "core_png_b64"] = mol_png_base64(
                    Chem.MolFromSmiles(ex),
                    size=(220, 160),
                    legend="",
                    reference=global_reference_smiles,
                )
            except Exception:
                continue

    return scaf_df, central_df, global_reference_smiles


def _stage_export_and_report(
    mol_df,
    report_mol_df,
    scaf_df,
    central_df,
    global_reference_smiles,
    args,
    output_layout,
    merge_stats,
    precluster_hbd_violations,
    run_started,
):
    """
    Generate figures, per-scaffold CSVs, core outputs, HTML report, and manifest.
    """
    scaf_img_dir = output_layout["scaf_img_dir"]
    fig_dir = output_layout["fig_dir"]
    per_scaf_dir = output_layout["per_scaf_dir"]
    report_filename = output_layout["report_filename"]
    molecule_summary_name = output_layout["molecule_summary_name"]
    scaffold_summary_name = output_layout["scaffold_summary_name"]
    central_ideas_name = output_layout["central_ideas_name"]
    qc_summary_name = output_layout["qc_summary_name"]
    manifest_name = output_layout["manifest_name"]

    # Per-scaffold substitution tables.
    progress_log(run_started, "Per-scaffold CSV export started")
    grouped_sar = list(report_mol_df.groupby("scaffold_id", dropna=False))
    total_sar_groups = len(grouped_sar)
    n_workers = max(1, int(args.n_workers) if args.n_workers > 0 else (os.cpu_count() or 2))
    io_workers = n_workers

    if n_workers > 1 and total_sar_groups > 1:
        progress_log(run_started, "Per-scaffold CSV export", extra=f"parallel workers={n_workers}")
        tasks = [(scaf_id, sdf.to_dict("records")) for scaf_id, sdf in grouped_sar]
        with ProcessPoolExecutor(max_workers=n_workers) as ex, ThreadPoolExecutor(max_workers=io_workers) as io_ex:
            fut_map = {ex.submit(build_per_scaffold_substitution_table, task): idx for idx, task in enumerate(tasks, start=1)}
            pending_writes = []
            done = 0
            for fut in as_completed(fut_map):
                done += 1
                scaf_hash, tdf = fut.result()
                tname = prefixed_output_name(args.file_prefix, f"scaffold_{scaf_hash}_substitutions.csv")
                tpath = os.path.join(per_scaf_dir, tname)
                pending_writes.append(io_ex.submit(write_dataframe_csv, tdf, tpath, False, True))
                flush_pending_csv_writes(pending_writes, wait_all=False, max_pending=96)
                if done % 100 == 0 or done == total_sar_groups:
                    progress_log(run_started, "Per-scaffold CSV export", done=done, total=total_sar_groups)
            flush_pending_csv_writes(pending_writes, wait_all=True)
    else:
        with ThreadPoolExecutor(max_workers=io_workers) as io_ex:
            pending_writes = []
            for sar_idx, (scaf_id, sdf) in enumerate(grouped_sar, start=1):
                if sar_idx % 100 == 0:
                    progress_log(run_started, "Per-scaffold CSV export", done=sar_idx, total=total_sar_groups)
                scaf_hash, tdf = build_per_scaffold_substitution_table((scaf_id, sdf.to_dict("records")))
                tname = prefixed_output_name(args.file_prefix, f"scaffold_{scaf_hash}_substitutions.csv")
                tpath = os.path.join(per_scaf_dir, tname)
                pending_writes.append(io_ex.submit(write_dataframe_csv, tdf, tpath, False, True))
                flush_pending_csv_writes(pending_writes, wait_all=False, max_pending=96)
            flush_pending_csv_writes(pending_writes, wait_all=True)
    progress_log(run_started, "Per-scaffold CSV export complete", done=total_sar_groups, total=total_sar_groups)

    # QC summary.
    merge_stats["report_pool_size"] = int(len(report_mol_df))
    merge_stats["excluded_molecular_weight"] = int((~mol_df["passes_mol_weight_filter"]).sum())
    merge_stats["excluded_hbd"] = int((~mol_df["passes_hbd_filter"]).sum())
    merge_stats["excluded_hba"] = int((~mol_df["passes_hba_filter"]).sum())
    merge_stats["excluded_rot_bonds"] = int((~mol_df["passes_rotb_filter"]).sum())
    merge_stats["excluded_charged"] = int((~mol_df["passes_neutral_filter"]).sum())
    merge_stats["excluded_any_rule"] = int((~mol_df["report_eligible"]).sum())
    merge_stats["precluster_hbd_violations"] = precluster_hbd_violations
    merge_stats["report_hbd_violations"] = precluster_hbd_violations
    qc_df = make_qc_summary(mol_df, merge_stats)
    write_dataframe_csv(qc_df, os.path.join(args.outdir, qc_summary_name), index=False, prefer_arrow=False)

    # Load protein assets.
    protein_pdb_text, protein_cartoon_pdb_text, protein_structure_format, protein_ss_map, protein_sources = load_protein_assets(
        args,
        run_started,
    )

    # Collect pose indices for protein visualization.
    pose_indices = set()
    top_scaf_for_pose = central_df.head(args.max_scaffolds_in_report)["scaffold_id"].tolist()
    for sid in top_scaf_for_pose:
        subset = report_mol_df[report_mol_df["scaffold_id"] == sid].sort_values("priority_rank").head(args.top_per_scaffold)
        rep_subset = representative_ranked_subset(subset, top_n=args.top_per_scaffold)
        if "mol_index" in rep_subset.columns:
            pose_indices.update(int(i) for i in rep_subset["mol_index"].dropna().tolist())
    pose_sdf_by_index = sanitize_sdf_blocks_for_viewer(
        read_sdf_blocks_by_index(args.input, pose_indices)
    )
    hbond_residue_options, scaffold_hbond_map = build_hbond_residue_filter_data(report_mol_df, scaf_df)
    pose_interactions_by_index = _precompute_pose_interactions(args, pose_indices, run_started)

    # Write core outputs.
    progress_log(run_started, "Core CSV writing started")
    mol_out = mol_df.sort_values(["priority_rank", "mol_id"])
    scaf_out = scaf_df.sort_values(
        ["central_rerank_score", "central_priority", "n_members"],
        ascending=[False, False, False],
        na_position="last",
    )
    with ThreadPoolExecutor(max_workers=io_workers) as io_ex:
        write_futs = [
            io_ex.submit(write_dataframe_csv, mol_out, os.path.join(args.outdir, molecule_summary_name), False, True),
            io_ex.submit(write_dataframe_csv, scaf_out, os.path.join(args.outdir, scaffold_summary_name), False, True),
            io_ex.submit(write_dataframe_csv, central_df, os.path.join(args.outdir, central_ideas_name), False, True),
        ]
        for fut in write_futs:
            fut.result()
    progress_log(run_started, "Core CSV writing complete")

    # HTML report.
    figures = []
    progress_log(run_started, "HTML report building started")
    scaffold_export_data = collect_scaffold_export_data(
        report_mol_df,
        central_df.head(args.max_scaffolds_in_report),
        args.input,
        args.top_per_scaffold,
    )

    # Properties panel data: SDF tag values + scaffold→member map.
    mol_props_data, scaffold_mol_map, mol_text_props_data, text_prop_value_counts = _extract_mol_props_for_report(
        args.input,
        mol_df,
        scaf_df,
        args.numeric_sd_props,
        args.text_sd_props,
        run_started,
    )

    write_html_report(
        args.outdir,
        report_mol_df,
        scaf_df,
        central_df,
        qc_df,
        figures,
        scaffold_export_data=scaffold_export_data,
        report_filename=report_filename,
        top_per_scaffold=args.top_per_scaffold,
        max_scaffolds_in_report=args.max_scaffolds_in_report,
        global_reference_smiles=global_reference_smiles,
        protein_pdb_text=protein_pdb_text,
        protein_cartoon_pdb_text=protein_cartoon_pdb_text,
        protein_structure_format=protein_structure_format,
        protein_ss_map=protein_ss_map,
        protein_sources=protein_sources,
        pose_sdf_by_index=pose_sdf_by_index,
        binding_site_radius=DEFAULT_BINDING_SITE_RADIUS,
        default_pocket_sticks=DEFAULT_POCKET_STICKS,
        hbond_residue_options=hbond_residue_options,
        scaffold_hbond_map=scaffold_hbond_map,
        ref_ligand_sdf=getattr(args, "ref_ligand_sdf", None),
        pose_interactions_by_index=pose_interactions_by_index,
        mol_props_data=mol_props_data,
        scaffold_mol_map=scaffold_mol_map,
        prop_names_ordered=args.numeric_sd_props,
        text_prop_names=args.text_sd_props,
        mol_text_props_data=mol_text_props_data,
        text_prop_value_counts=text_prop_value_counts,
    )
    progress_log(run_started, "HTML report complete",
                 extra=os.path.join(args.outdir, report_filename))

    # Manifest.
    manifest = build_manifest(args, len(mol_df), int(scaf_df["scaffold_id"].nunique()))
    with open(os.path.join(args.outdir, manifest_name), "w", encoding="utf-8") as mf:
        json.dump(manifest, mf, indent=2)


def main():
    run_started = time.time()
    start_progress_bar(run_started)
    
    # Setup phase: parse CLI, initialize output layout, load exclusion patterns.
    ap = build_cli_parser()
    args = ap.parse_args()

    base_numeric_props = _normalize_sd_prop_list(_REPORT_PROP_NAMES)
    extra_numeric_props = _normalize_sd_prop_list(getattr(args, "numeric_sd_props", []))
    args.numeric_sd_props = _normalize_sd_prop_list(base_numeric_props + extra_numeric_props)
    args.text_sd_props = _normalize_sd_prop_list(getattr(args, "text_sd_props", []))

    if getattr(args, "ref_ligand_sdf", None):
        args.ref_ligand_sdf = os.path.abspath(args.ref_ligand_sdf)
        if not os.path.exists(args.ref_ligand_sdf):
            eprint(f"Warning: reference ligand SDF not found: {args.ref_ligand_sdf}")

    output_layout = initialize_output_layout(args.outdir, args.file_prefix)
    removed_prefixed = output_layout["removed_prefixed"]
    progress_log(run_started, "Run started", extra=f"input={os.path.basename(args.input)}")
    if str(args.file_prefix or "").strip():
        progress_log(
            run_started,
            "Prefix cleanup",
            extra=f"prefix={args.file_prefix} removed_files={removed_prefixed}",
        )

    exclude_patterns, exclude_meta = load_exclusion_patterns(args.exclude_smiles_file)
    progress_log(
        run_started,
        "Exclusion rules loaded",
        extra=(
            f"patterns={exclude_meta['exclude_patterns_loaded']} "
            f"parse_failures={exclude_meta['exclude_pattern_parse_failures']}"
        ),
    )

    # Stage 1: Parse SDF and build molecule dataframe.
    mol_df, all_prop_names, merge_stats, sdf_stats = _stage_sdf_parse(
        args, exclude_patterns, exclude_meta, run_started
    )

    # Stage 2: Merge interaction data and compute ranking scores.
    mol_df, report_mol_df, merge_stats, precluster_hbd_violations = _stage_merge_and_rank(
        mol_df, args, run_started, merge_stats
    )

    # Stage 3: Build scaffold summaries, rankings, and panels.
    n_workers = max(1, int(args.n_workers) if args.n_workers > 0 else (os.cpu_count() or 2))
    scaf_df, central_df, global_reference_smiles = _stage_scaffold_analysis(
        report_mol_df, mol_df, output_layout["scaf_img_dir"], n_workers, args, run_started
    )

    # Stage 4: Generate figures, per-scaffold CSVs, and all output files.
    _stage_export_and_report(
        mol_df, report_mol_df, scaf_df, central_df, global_reference_smiles,
        args, output_layout, merge_stats, precluster_hbd_violations, run_started
    )

    finish_progress_bar()

    # Final summary output.
    n_bad = sdf_stats["n_bad"]
    excluded_by_smiles_rules = sdf_stats["excluded_by_smiles_rules"]
    excluded_pattern_counter = sdf_stats["excluded_pattern_counter"]
    
    print(f"Read {len(mol_df)} molecules ({n_bad} invalid SDF records skipped).")
    if excluded_pattern_counter:
        top_hits = ", ".join([f"{k}:{v}" for k, v in excluded_pattern_counter.most_common(5)])
    else:
        top_hits = "none"
    print(
        f"Excluded by smiles rules: {excluded_by_smiles_rules} "
        f"(patterns={exclude_meta.get('exclude_patterns_loaded', 0)}, parse_failures={exclude_meta.get('exclude_pattern_parse_failures', 0)})."
    )
    print(f"Top exclusion hits: {top_hits}")
    print(f"Matched IF rows to molecules: {merge_stats['matched_molecules']} (unmatched: {merge_stats['unmatched_molecules']})")
    
    molecule_summary_name = output_layout["molecule_summary_name"]
    scaffold_summary_name = output_layout["scaffold_summary_name"]
    central_ideas_name = output_layout["central_ideas_name"]
    qc_summary_name = output_layout["qc_summary_name"]
    report_filename = output_layout["report_filename"]
    
    print(f"Wrote: {os.path.join(args.outdir, molecule_summary_name)}")
    print(f"Wrote: {os.path.join(args.outdir, scaffold_summary_name)}")
    print(f"Wrote: {os.path.join(args.outdir, central_ideas_name)}")
    print(f"Wrote: {os.path.join(args.outdir, qc_summary_name)}")
    print(f"Wrote: {os.path.join(args.outdir, report_filename)}")
    print(f"Total runtime: {format_elapsed(time.time() - run_started)}")


if __name__ == "__main__":
    main()
