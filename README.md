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

## Quick Start

The recommended entry point is the shell wrapper:

```bash
bash run_show_docking.sh
```

Both scripts call process_docking_IF_show_docking.py with project-typical inputs. You can also run the Python script directly.

Long-flag core-input example:

```bash
python process_docking_IF_show_docking.py \
  --input direct_linker_enumeration_docking_pose_all_BB_with_props.sdf \
  --interaction-csv direct_linker_all_IF.csv \
  --interaction-id-col Title \
  --interaction-count-col interaction_count \
  --outdir ./ \
  --file-prefix VS_visualization_05232026
```

Long-flag example with protein, reference, filters, and report-size tuning:

```bash
python process_docking_IF_show_docking.py \
  --input direct_linker_enumeration_docking_pose_all_BB_with_props.sdf \
  --interaction-csv direct_linker_all_IF.csv \
  --interaction-id-col Title \
  --interaction-count-col interaction_count \
  --protein-pdb 6782_protein.pdb \
  --ref-ligand-sdf ref_structures.sdf \
  --exclude-smiles-file exclude_motifs.smi \
  --max-molecular-weight 800 \
  --max-rotatable-bonds 13 \
  --max-hbond-donors 2 \
  --max-hbond-acceptors 10 \
  --file-prefix VS_visualization_05052026 \
  --top-per-scaffold 10 \
  --max-scaffolds-in-report 25 \
  --n-workers 8 \
  --outdir ./
```

## Hosted Portal Scaffold

This repository now includes the first hosted Flask scaffold described in [HOSTED_PORTAL_TECHNICAL_DESIGN.md](HOSTED_PORTAL_TECHNICAL_DESIGN.md). The hosted scaffold is read-only and is intended to serve immutable published releases from a configurable release root. It does not replace the existing static HTML generation workflow.

### Local Run Requirements

- Python 3.10+
- Flask
- Gunicorn for production-like local serving

Install the web dependencies in your environment if they are not already present:

```bash
pip install flask gunicorn
```

### Environment Variables

- `HOSTED_PORTAL_HOST`: Flask bind host for local serving
- `HOSTED_PORTAL_PORT`: Flask bind port for local serving
- `HOSTED_PORTAL_BASE_URL`: externally reachable portal base URL used for generated links
- `HOSTED_PORTAL_RELEASE_ROOT`: root directory containing published release folders
- `HOSTED_PORTAL_ACTIVE_RELEASE`: optional default release ID to highlight or open first
- `HOSTED_PORTAL_CACHE_DIR`: writable cache directory for hosted portal runtime state
- `HOSTED_PORTAL_ENV`: `development` or `production`
- `HOSTED_PORTAL_LOG_LEVEL`: log level such as `INFO` or `DEBUG`

Safe local defaults are provided when these variables are not set:

- release root defaults to `./releases`
- cache dir defaults to `./tmp/hosted_portal_cache`
- environment defaults to `development`
- host defaults to `127.0.0.1`
- port defaults to `5005`
- base URL defaults to `http://<HOSTED_PORTAL_HOST>:<HOSTED_PORTAL_PORT>`

### Expected Hosted Release Layout

```text
releases/
  RELEASE_TAG/
    manifest.json
    data/
    poses/
    exports/
    static_payload/
```

Minimal manifest example:

```json
{
  "release_id": "example_release",
  "display_name": "Example Release",
  "created_at": "2026-08-02",
  "program": "PPI",
  "target": "example_target",
  "description": "Example hosted docking portal release",
  "files": {
    "scaffolds": "data/scaffolds.json",
    "molecules": "data/molecules.json",
    "pose_index": "data/pose_index.json"
  }
}
```

### Validate a Release Manifest

Validate a release directory or a specific manifest file:

```bash
python scripts/validate_release_manifest.py releases/EXAMPLE_RELEASE
python scripts/validate_release_manifest.py releases/EXAMPLE_RELEASE/manifest.json
```

The validator checks required manifest fields and confirms referenced files exist inside the release directory.

### Start the Hosted Portal Locally

Development server:

```bash
export HOSTED_PORTAL_RELEASE_ROOT="$PWD/releases"
export HOSTED_PORTAL_HOST=127.0.0.1
export HOSTED_PORTAL_PORT=5005
export HOSTED_PORTAL_BASE_URL=http://127.0.0.1:5005
FLASK_APP=wsgi:app python -m flask run --host "$HOSTED_PORTAL_HOST" --port "$HOSTED_PORTAL_PORT"
```

Gunicorn:

```bash
export HOSTED_PORTAL_RELEASE_ROOT="$PWD/releases"
export HOSTED_PORTAL_BASE_URL=http://127.0.0.1:5005
gunicorn -c deploy/gunicorn.conf.py wsgi:app
```

Initial hosted routes:

- `/`: release selector shell
- `/release/<release_id>`: hosted report shell for a selected release
- `/api/releases`: list available releases
- `/api/releases/<release_id>/manifest`: manifest metadata
- `/api/releases/<release_id>/scaffolds`: placeholder or file-backed scaffold payload
- `/api/releases/<release_id>/molecules`: placeholder or file-backed molecule payload
- `/api/releases/<release_id>/pose-index`: placeholder or file-backed pose index payload
- `/api/health`: health and configuration status

### Local Asset Policy

The hosted scaffold does not use external CDN URLs. Vendor placeholders are provided under `app/static/vendor/` for:

- `3dmol`
- `plotly`
- `bootstrap`
- `rdkit`
- `fonts`

Before production cutover, any browser dependency used by the hosted UI must be copied into those directories and served locally.

### Development vs Production Access

- Development access: `http://127.0.0.1:5005`
- Production access target: `https://10.17.x.x`

The application should move between these environments using only environment and deployment configuration changes, not code changes.

## Hosted Example Release

This repository now includes a path for creating a concrete hosted example release from the authoritative generated report HTML.

Create or refresh the example release:

```bash
python scripts/create_example_release_from_report.py \
  --report-html VS_PPI_Leo_Bicyclic_headgroup_screen_06052026_report.html \
  --release-id example_release \
  --release-root releases
```

Expected output layout:

```text
releases/
  example_release/
    manifest.json
    data/
      scaffolds.json
      molecules.json
      pose_index.json
    poses/
    exports/
    static_payload/
      report.html
```

The example release is derived from the existing generated report and patches hosted asset references to local `/static/vendor/...` paths.

### One-Step Wrapper For a New SDF

Use the wrapper below to do all three steps automatically:

1. generate the static docking report
2. package that report into a hosted release
3. validate the hosted release manifest

```bash
python scripts/build_hosted_release.py \
  --input /path/to/new_input.sdf \
  --interaction-csv /path/to/new_interactions.csv \
  --release-id my_new_release \
  --protein-pdb /path/to/protein.pdb \
  --ref-ligand-sdf /path/to/ref_ligands.sdf \
  --exclude-smiles-file /path/to/exclude_motifs.smi \
  --max-molecular-weight 800 \
  --max-rotatable-bonds 13 \
  --max-hbond-donors 2 \
  --top-per-scaffold 10 \
  --max-scaffolds-in-report 500 \
  --n-workers 8 \
  --serve
```

By default this writes intermediate static-report outputs under:

```text
hosted_builds/<release_id>/
```

and the hosted release under:

```text
releases/<release_id>/
```

If you need to pass additional flags directly to `process_docking_IF_show_docking.py`, append them to the wrapper command. Unknown flags are forwarded unchanged. Example:

```bash
python scripts/build_hosted_release.py \
  --input /path/to/new_input.sdf \
  --interaction-csv /path/to/new_interactions.csv \
  --release-id my_new_release \
  --protein-pdb /path/to/protein.pdb \
  -- --text-sd-props Vendor ring_system --numeric-sd-props custom_score
```

Use the same Python environment that can already run `process_docking_IF_show_docking.py`, including RDKit and its existing dependencies.

When `--serve` is enabled, the wrapper starts Flask using a compatibility-safe invocation:

```bash
FLASK_APP=wsgi:app python -m flask run --host 127.0.0.1 --port 5005
```

You can override host and port:

```bash
python scripts/build_hosted_release.py \
  --input /path/to/new_input.sdf \
  --interaction-csv /path/to/new_interactions.csv \
  --release-id my_new_release \
  --serve \
  --serve-host 0.0.0.0 \
  --serve-port 5010
```

When you set `HOSTED_PORTAL_BASE_URL`, wrapper output links use that base URL instead of assuming localhost.

## Production Deployment

See `DEPLOYMENT.md` for:

- Nginx + Gunicorn + Flask architecture
- reverse proxy header requirements
- `.env.production` and `.env.development` usage
- firewall assumptions
- production validation checklist

## Same-Server Deployment With Existing Dash App

If an existing Dash app is already running on the same VM (for example on `10.17.7.88:8865`), the hosted portal can be run independently on `10.17.7.88:8866`.

This keeps the existing Dash deployment unchanged by using:

- a separate process
- a separate systemd service name
- a separate TCP port

Reference guide:

- `DEPLOYMENT_SAME_SERVER_8866.md`

Service template for this mode:

- `deploy/hosted-portal-8866.service.template`

## Frontend Migration Status

See `HOSTED_FRONTEND_MIGRATION_STATUS.md` for the section-by-section migration tracker.

Current status summary:

- migrated: hosted release selection shell and top-level report wrapper layout
- partially migrated: KPI and hero layout in Flask templates using extracted report-like CSS
- preserved via hosted payload: Overview, filters, Central Ideas, deep dives, and report navigation
- pending: direct extraction of client-side filter logic, chart behavior, and 3D viewer internals

## Local Assets

See `app/static/vendor/VENDORED_ASSETS.md` for the hosted asset inventory.

This slice includes local compatibility shims for:

- 3Dmol
- Plotly
- RDKit Minimal

They remove runtime CDN dependency for the hosted path. They are not a substitute for fully vendored upstream libraries, which should be added in the next migration slice.

## CLI Reference

### Core Inputs and Outputs

- --input: input docking SDF file (required)
- --outdir: output directory
- --file-prefix: prefix for output filenames
- --interaction-csv: interaction count CSV
- --interaction-id-col: ligand ID column in interaction CSV
- --interaction-count-col: interaction-count column in interaction CSV
- --id-prop: preferred SD tag for molecule identifier
- --cluster-prop: optional SD tag containing pre-assigned cluster ID

### Scoring and Scaffold Controls

- --score-props: candidate SD tags for docking score
- --auto-detect-score: auto-detect score-like SD tags
- --min-group-size: minimum group size for central idea ranking
- --top-per-scaffold: representatives shown per scaffold in report
- --max-scaffolds-in-report: scaffold cards shown in detailed section

### Structures and Filters

- --protein-pdb: one or more receptor files (.pdb, .cif/.mmcif, .mol2)
- --ref-ligand-sdf: optional reference ligand SDF for viewer overlays
- --exclude-smiles-file: motifs to exclude (substructure match)
- --max-molecular-weight: report max molecular weight filter
- --max-rotatable-bonds: report max rotatable bonds filter
- --max-hbond-donors: report max hydrogen bond donors filter
- --max-hbond-acceptors: report max hydrogen bond acceptors filter

### Performance and Rendering

- --generate-all-mol-images: eagerly generate all molecule images
- --n-workers: worker count (0 means auto-detect)

## Important Defaults

These options are now fixed in code (not exposed as CLI flags):

- docking-score weight: 0.4
- interaction-count weight: 0.6
- docking viewer binding-site radius: 4.0 A
- docking viewer default pocket sticks: enabled
- exclusion match mode: substructure
- charged molecules are allowed by default

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

## Troubleshooting

- Reference ligand dropdown is empty:
  - Confirm --ref-ligand-sdf points to an existing file.
  - Use an absolute path if running from another working directory.
  - Check stderr for warning: reference ligand SDF not found.
- No molecules after filtering:
  - Relax one or more max filters (--max-molecular-weight, --max-rotatable-bonds, --max-hbond-donors, --max-hbond-acceptors).
- Exclusion motifs remove too many molecules:
  - Review exclude_motifs.smi patterns and test with fewer motifs first.

## Example

Typical output after a run includes a report, summary CSVs, scaffold images, and a manifest file in the chosen output directory. The example wrapper in this folder writes files prefixed with `VS_visualization_05052026`.

## Contribution Guidelines

- Keep changes focused on the docking-to-report workflow.
- Update the README when CLI flags, inputs, or outputs change.
- Preserve compatibility with the existing CSV, SDF, and HTML report formats.

## License

License not specified in this folder. Add licensing information before external distribution.