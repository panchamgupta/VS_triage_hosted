# Prompt: Generate the STAT6 Docking Report Codebase From Scratch

Use the following prompt with a coding LLM to recreate this project in a clean folder.

## Prompt Text

You are an expert Python and cheminformatics engineer. Build a production-ready codebase that analyzes docking SDF files, merges interaction counts, ranks molecules by scaffold, and generates an interactive HTML report with docking-pose visualization.

Follow the implementation in stepwise phases below. Keep tasks grouped by similar concerns. Complete each phase fully before moving to the next.

### Phase 1: Project Scaffold and Environment

- Create a Python project for command-line workflow execution.
- Add modules with this structure:
  - cli_config.py
  - process_docking_IF_show_docking.py
  - ranking_helpers.py
  - filtering.py
  - scaffold_summary_helpers.py
  - export_helpers.py
  - report_helpers.py
  - docking_pose_visualizer_block.py
  - shared_utils.py
  - progress_tracking.py
- Add shell wrappers:
  - run_show_docking.sh
  - run_show_docking_shortflags.sh
- Add README.md with setup and usage examples.
- Target dependencies:
  - rdkit, pandas, numpy, matplotlib
  - optional: pyarrow, mdtraj

### Phase 2: CLI and Configuration Layer

- Build argparse parser in cli_config.py.
- Support both long and one-letter flags for all user-exposed arguments.
- Implement grouped argument sets:
  - Core I/O: input SDF, output dir, prefix
  - Interaction CSV mapping: CSV path, ID column, interaction count column
  - Scoring controls: score properties, auto-detect score tags
  - Scaffold controls: min group size, top per scaffold, max scaffolds in report
  - Structure inputs: protein files, reference ligand SDF
  - Filtering controls: max molecular weight, max rotatable bonds, max H-bond donors, max H-bond acceptors, exclusion motifs file
  - Performance: n-workers, optional eager image generation
- Keep these defaults hardcoded in code, not CLI arguments:
  - score weight 0.4
  - interaction weight 0.6
  - binding-site radius 4.0 A
  - pocket sticks on by default
  - exclusion match mode substructure
  - charged molecules allowed by default

### Phase 3: Molecule Parsing and Descriptor Pipeline

- Parse SDF records with RDKit and preserve molecule index mapping.
- Extract molecule identifiers using preferred SD tag, then fallback tags.
- Extract docking score from candidate score tags.
- Compute descriptors:
  - molecular weight, cLogP, TPSA
  - HBD, HBA, rotatable bonds
  - ring count, heavy atoms, formal charge, Fsp3
- Build filter properties with SDF-first logic and RDKit fallback:
  - molecular_weight / MW aliases
  - Rotatable_bonds aliases
  - Hydrogen bond donors aliases
  - Hydrogen bond acceptors aliases
- Support motif exclusion using substructure matching from a SMILES file.

### Phase 4: Ranking, Merging, and Eligibility Filters

- Load external interaction CSV and merge by normalized ligand ID.
- Normalize score and interaction terms.
- Compute priority score using fixed weights.
- Compute drug-like score from descriptor ranges.
- Build report eligibility filtering with max thresholds:
  - molecular weight
  - rotatable bonds
  - H-bond donors
  - H-bond acceptors
- Add pass/fail columns and exclusion reason tags.
- Generate report-facing molecule dataframe containing only eligible compounds.

### Phase 5: Scaffold Analysis and Exports

- Compute Murcko scaffolds and substitution signatures.
- Group molecules by scaffold and build scaffold summary statistics.
- Generate scaffold-level outputs:
  - scaffold summary CSV
  - central ideas CSV
  - per-scaffold substitution CSV tables
- Build publication-style figures and scaffold panel images.
- Write molecule summary and QC summary CSV files.
- Emit a run manifest JSON containing parameters and run metadata.

### Phase 6: HTML Report and Interactive Viewer

- Build report page with sections:
  - Overview and QC
  - Central ideas table/cards
  - Scaffold panels
  - Deep dive per scaffold
  - Docking pose visualizer popup
- Add structure-search filtering in report UI.
- Add exclusion motif awareness and filtering controls in report UI.
- Add reference ligand support:
  - parse multi-entry SDF
  - build reference ligand tiles
  - add dropdown options in visualizer
  - support overlay with docked ligands
- Ensure pose SDF blocks are mapped by index and available to JS.
- Include offline viewer assets in report output.

### Phase 7: Parallelism, Performance, and Stability

- Use process/thread pools for scalable parsing and export steps.
- Use n-workers consistently for CPU and CSV-writing parallelism.
- Add progress logging with elapsed-time updates.
- Add robust warnings for missing optional files (for example missing ref ligand SDF).
- Avoid hard crashes for optional component failures; fail gracefully with diagnostics.

### Phase 8: Validation and Deliverables

- Validate CLI end-to-end with sample commands (long and short flags).
- Ensure generated report includes:
  - functioning scaffold cards and deep dive sections
  - working docking pose visualizer
  - populated reference ligand dropdown when ref ligand SDF exists
- Provide final deliverables:
  - fully runnable scripts and modules
  - README with setup and troubleshooting
  - sample run scripts

### Quality Constraints

- Write clean, modular Python with clear function boundaries.
- Prefer deterministic behavior and explicit defaults.
- Keep generated outputs stable and reproducible.
- Include concise comments only where logic is non-obvious.
- Ensure Linux compatibility for scripts and paths.
