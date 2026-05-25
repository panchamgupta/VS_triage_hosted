# HTML Report Tutorial

This tutorial explains how to use the generated report page effectively for hit triage, scaffold-level analysis, and docking-pose inspection.

## 0. Generate the Report (Long-Flag Examples Only)

Use long flags when running the pipeline.

### 0.1 Core Inputs Example

```bash
python process_docking_IF_show_docking.py \
  --input direct_linker_enumeration_docking_pose_all_BB_with_props.sdf \
  --interaction-csv direct_linker_all_IF.csv \
  --interaction-id-col Title \
  --interaction-count-col interaction_count \
  --outdir ./ \
  --file-prefix VS_visualization_05232026
```

### 0.2 Other Common Examples

Include protein context and reference overlay:

```bash
python process_docking_IF_show_docking.py \
  --input direct_linker_enumeration_docking_pose_all_BB_with_props.sdf \
  --interaction-csv direct_linker_all_IF.csv \
  --interaction-id-col Title \
  --interaction-count-col interaction_count \
  --protein-pdb 6782_protein.pdb \
  --ref-ligand-sdf ref_structures.sdf \
  --outdir ./ \
  --file-prefix VS_visualization_05232026
```

Apply report-facing property and motif filters:

```bash
python process_docking_IF_show_docking.py \
  --input direct_linker_enumeration_docking_pose_all_BB_with_props.sdf \
  --interaction-csv direct_linker_all_IF.csv \
  --interaction-id-col Title \
  --interaction-count-col interaction_count \
  --exclude-smiles-file exclude_motifs.smi \
  --max-molecular-weight 800 \
  --max-rotatable-bonds 13 \
  --max-hbond-donors 2 \
  --max-hbond-acceptors 10 \
  --outdir ./ \
  --file-prefix VS_visualization_05232026
```

Tune scaffold/report size and worker parallelism:

```bash
python process_docking_IF_show_docking.py \
  --input direct_linker_enumeration_docking_pose_all_BB_with_props.sdf \
  --interaction-csv direct_linker_all_IF.csv \
  --interaction-id-col Title \
  --interaction-count-col interaction_count \
  --top-per-scaffold 10 \
  --max-scaffolds-in-report 25 \
  --n-workers 8 \
  --outdir ./ \
  --file-prefix VS_visualization_05232026
```

## 1. Open the Report and Orient Yourself

- Open the generated report HTML file in a modern browser.
- Start at the top summary area to check:
  - run metadata
  - molecule/scaffold counts
  - QC values
- Use this first pass to confirm your run is complete and filters were applied as expected.

## 2. Use Filtering to Narrow to Actionable Molecules

The report supports multiple filtering styles. Apply broad filters first, then tighten.

### 2.1 Property-Based Filtering

Use these for medicinal chemistry triage:

- Hydrogen bond donor threshold:
  - Keep donor count low when permeability or oral exposure is a concern.
  - Start with a strict threshold, then relax if too few compounds remain.
- Hydrogen bond acceptor threshold:
  - Use with donor filtering for balanced polarity control.
- Molecular-weight and rotatable-bond thresholds:
  - Use together to avoid overly large or flexible compounds.

Practical workflow:

- First pass: conservative thresholds to identify high-confidence leads.
- Second pass: loosen one property at a time to recover near-miss chemotypes.

### 2.2 Substructure Filtering

Use structure search when you want compounds that contain a motif.

- Draw or provide a query motif.
- Use substructure mode to keep only compounds containing that motif.
- Compare how many scaffolds remain after applying the motif.

When to use:

- Validate whether a known pharmacophore appears in top-ranked scaffolds.
- Focus on a chemical series for SAR discussion.

### 2.3 Exclusion Motif Filtering

Use exclusion motifs to remove undesired chemotypes globally.

- Provide motifs in the exclusion SMILES file.
- Rerun the pipeline so excluded compounds are removed from report-facing outputs.
- In review meetings, confirm which motifs were excluded before ranking interpretation.

Common use cases:

- remove liabilities
- remove chemically unstable motifs
- remove known false-positive substructures

## 3. Read Scaffold Panels Properly

Scaffold panels summarize each scaffold family visually.

How to use them:

- Start with top-ranked scaffold cards.
- Check member count and representative compounds.
- Scan substitution patterns to identify consistent beneficial regions.
- Compare panels side by side for diversity and property balance.

Best practice:

- Do not choose by rank alone.
- Combine panel pattern quality, interaction behavior, and property profile.

## 4. Use the Deep Dive Section Effectively

The deep dive section is where scaffold-level decisions become concrete.

Suggested workflow per scaffold:

- Review member list and rank spread.
- Inspect substitution table for position-specific trends.
- Identify substitutions that repeatedly improve interaction or ranking.
- Flag outliers:
  - high rank but poor property balance
  - good properties but weak interactions

Decision output from deep dive:

- keep for progression
- hold for analog expansion
- deprioritize

## 5. Docking Pose Visualizer Window Guide

The docking visualizer is designed for fast pose triage and comparison.

### 5.1 Basic Operations

- Open pose view from a scaffold/member entry.
- Toggle protein cartoon and pocket sticks depending on clarity needs.
- Keep ligand sticks on for geometry interpretation.
- Recenter and reset view after each scaffold switch.

### 5.2 Hydrogen-Bond and Interaction Review

- Turn on hydrogen-bond overlays.
- Review residue labels and donor/acceptor consistency.
- Cross-check whether reported interactions align with visible geometry.

### 5.3 Reference Ligand Overlay

- Use the reference ligand dropdown to load a crystal/reference pose.
- Overlay reference and docked ligand to inspect:
  - core alignment
  - vector direction differences
  - key interaction retention/loss
- Remove reference overlay when switching to a different scaffold family.

If dropdown is empty:

- Confirm the run used a valid ref ligand SDF path.
- Confirm the file exists at runtime.
- Check run logs for a missing-file warning.

### 5.4 Multi-Protein Context (if provided)

- Use the protein-source selector to switch receptor structures.
- Compare pose stability across proteins before selecting synthesis candidates.

### 5.5 Performance Behavior in Current Viewer

- First pose open now prioritizes fast model display and defers interaction dash drawing to the next frame.
- Control changes (palette, opacity, interaction toggles) use style-only rerender paths where possible.
- Interaction summaries are cached by protein source, pose index, and binding radius.
- Slider-driven controls are debounced to avoid unnecessary full rerenders while dragging.
- Console timing markers are emitted for:
  - pose open total
  - pocket detection
  - hbond computation
  - pipi computation
  - full rerender after control toggle

## 6. Recommended End-to-End Review Playbook

- Apply property filters to define a practical design space.
- Use substructure filtering to focus on desired series.
- Confirm excluded motifs are not present in final candidates.
- Rank candidate scaffolds from scaffold panel + deep dive evidence.
- Validate top members in docking visualizer with interaction and reference overlays.
- Export final short list for synthesis or follow-up computation.

## 7. Common Mistakes to Avoid

- Overfitting to a single score without checking interaction geometry.
- Ignoring scaffold diversity when top ranks are clustered.
- Applying overly strict filters too early and losing valuable series.
- Skipping reference overlays when crystal guidance exists.

## 8. Practical Checklist Before Final Selection

- Are filters documented and reproducible?
- Are top candidates free of excluded motifs?
- Do key interactions appear geometrically plausible in 3D?
- Are selected compounds balanced on MW, flexibility, and H-bond profile?
- Is scaffold diversity adequate for portfolio risk control?

If all answers are yes, your shortlist is usually strong enough for chemistry planning discussion.
