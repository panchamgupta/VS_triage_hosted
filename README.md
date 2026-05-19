# STAT6 PPI R-Group Mapping and Docking Report Toolkit

This folder contains a Python workflow for analyzing docking poses, grouping molecules by scaffold, and generating a web-based report with central and unique scaffold ideas. It combines RDKit-based chemistry processing with HTML visualization and per-scaffold export files.

## Key Features

- Parses docking SDF files and extracts molecule identifiers, scores, and SD tags.
- Merges interaction-count data from CSV files and ranks molecules by multi-factor priority.
- Builds scaffold summaries, central ideas, unique ideas, and per-scaffold substitution tables.
- Generates publication-style CSV summaries, PNG figures, and an interactive HTML report.
- Supports optional receptor structures, reference ligands, and motif-based exclusion filters.
- Ships with an offline 3D viewer asset bundle for docking pose inspection.

## Installation

1. Create and activate a Python environment with RDKit installed.
   ```bash
   conda create -n rdkit-env python=3.11 -y
   conda activate rdkit-env
   conda install -c conda-forge rdkit pandas numpy matplotlib pyarrow mdtraj -y
   ```
2. If you prefer pip-based installation, make sure compatible builds of RDKit and its dependencies are already available in your environment.
3. Confirm that the main scripts in this folder can import RDKit, pandas, NumPy, and matplotlib.

## Usage

The recommended entry point is the shell wrapper:

```bash
bash run_show_docking.sh
```

That script calls `process_docking_IF_show_docking.py` with the project’s typical inputs and output prefix. You can also run the Python script directly:

```bash
python process_docking_IF_show_docking.py \
  --input direct_linker_enumeration_docking_pose_all_BB_with_props.sdf \
  --interaction-csv direct_linker_all_IF.csv \
  --interaction-id-col Title \
  --interaction-count-col interaction_count \
  --protein-pdb 6782_protein.pdb,STAT6-1650495_wo_lig.pdb \
  --ref-ligand-sdf ref_structures.sdf \
  --exclude-smiles-file exclude_motifs.smi \
  --file-prefix VS_visualization_05052026 \
  --outdir ./
```

## Input / Output

### Inputs

- Docking poses: SDF files with molecule records and SD tags.
- Interaction data: CSV files with ligand IDs and interaction counts.
- Protein structures: PDB or MOL2 files for the docking viewer.
- Optional reference ligands: multi-entry SDF files.
- Optional exclusion motifs: SMILES text files, one motif per line.

### Outputs

- `report.html`: interactive summary report.
- `molecule_summary.csv`: molecule-level ranking table.
- `scaffold_summary.csv`: scaffold-level summary table.
- `central_ideas.csv`: top scaffold ideas.
- `unique_ideas.csv`: rare or novel scaffold ideas.
- `qc_summary.csv`: quality-control summary.
- `run_manifest.json`: run metadata and configuration.
- `figures/`, `scaffold_images/`, `per_scaffold_tables/`: supporting figures and per-scaffold exports.

## Project Structure

- `process_docking_IF_show_docking.py`: main workflow and report generation entry point.
- `report_helpers.py`: HTML report assembly and embedded viewer helpers.
- `export_helpers.py`: CSV/figure export utilities.
- `ranking_helpers.py`: molecule ranking and interaction merge logic.
- `scaffold_summary_helpers.py`: scaffold extraction, ranking, and depiction helpers.
- `filtering.py`: report filters and drug-likeness scoring.
- `docking_pose_visualizer_block.py`: embedded viewer JavaScript generation.
- `report_assets/` and `sdf-viewer-offline/`: offline visualization assets.
- `run_show_docking.sh`: example launch script.

## Dependencies / Requirements

- Python 3.10+ recommended.
- RDKit.
- pandas.
- NumPy.
- matplotlib.
- pyarrow, if available, for faster CSV I/O.
- MDTraj, if you need MOL2/PDB secondary-structure handling in the viewer.

## Example

Typical output after a run includes a report, summary CSVs, scaffold images, and a manifest file in the chosen output directory. The example wrapper in this folder writes files prefixed with `VS_visualization_05052026`.

## Contribution Guidelines

- Keep changes focused on the docking-to-report workflow.
- Update the README when CLI flags, inputs, or outputs change.
- Preserve compatibility with the existing CSV, SDF, and HTML report formats.

## License

License not specified in this folder. Add licensing information before external distribution.