# Hosted Frontend Migration Status

This file tracks how the generated report UI is being moved into the hosted Flask application without redesigning the interface.

## Source of Truth

- Authoritative report: `VS_PPI_Leo_Bicyclic_headgroup_screen_06052026_report.html`
- Report generation source: `report_helpers.py`
- Pose viewer source: `docking_pose_visualizer_block.py`

## Section Status

| Report section | Status | Notes |
|---|---|---|
| Hero title and KPI layout | partially migrated | Top shell styling and KPI card layout were extracted into `app/templates/release.html` and `app/static/css/legacy_report.css`. |
| Release navigation | migrated | Hosted release dropdown and release selector shell are now live in Flask templates. |
| Help panel | pending direct extraction | Preserved in the hosted static payload report loaded in the iframe. |
| Hydrogen Bonding Residues panel | pending direct extraction | Preserved in hosted static payload. Requires API-backed residue metadata later. |
| Structure Search panel | pending direct extraction | Hosted payload keeps current DOM and behavior. Future work needs real local RDKit assets instead of the current shim. |
| Exclude Motif panel | pending direct extraction | Preserved in hosted payload. |
| Molecule Properties panel | pending direct extraction | Plotly path patched to local hosted asset. Current hosted asset is a compatibility shim, not full Plotly. |
| Central Ideas scaffold grid | pending direct extraction | Full current grid preserved in hosted payload. Real scaffold JSON is now available for direct template rendering later. |
| Scaffold Deep Dive | pending direct extraction | Preserved in hosted payload. |
| 3D pose viewer | pending direct extraction | Hosted path loads a local compatibility shim instead of external 3Dmol. Full vendored viewer needed later. |
| Export toolbar | pending direct extraction | Preserved in hosted payload. |

## Extracted CSS and Layout Containers

Extracted in this slice:

- top-level hero shell structure
- KPI grid style
- panel container style
- hosted wrapper toolbar
- report iframe container

Files:

- `app/templates/release.html`
- `app/static/css/legacy_report.css`

## Data Requirements Identified

Direct template migration will need these release-backed payloads:

- scaffold summary list and central-card ordering
- deep-dive member payloads
- molecule property metadata for charts and filters
- residue filter metadata
- pose lookup and interactions
- export state payloads

## Asset Audit

Legacy external asset dependencies identified:

- `https://3Dmol.org/build/3Dmol-min.js`
- `https://cdn.plot.ly/plotly-2.26.0.min.js`

Hosted replacements in this slice:

- `/static/vendor/3dmol/3Dmol-min.js`
- `/static/vendor/plotly/plotly-2.26.0.min.js`
- `/static/vendor/rdkit/RDKit_minimal.js`

## Next Direct Migration Targets

1. Replace the iframe preservation layer with direct template rendering of the Overview and Central Ideas sections.
2. Vendor real upstream RDKit, Plotly, and 3Dmol assets locally.
3. Extract filter and deep-dive JavaScript from the generated report into modular static JS files.