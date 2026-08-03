# Hosted Portal Local Assets

This slice removes runtime dependency on external browser CDNs for the hosted portal path.

| Asset | Current hosted file | Version in this slice | Source | Notes |
|---|---|---|---|---|
| 3Dmol | `app/static/vendor/3dmol/3Dmol-min.js` | local shim | hosted compatibility shim | Prevents external `3Dmol.org` fetches while preserving viewer boot flow. Replace with upstream vendored build in the next slice. |
| Plotly | `app/static/vendor/plotly/plotly-2.26.0.min.js` | `2.26.0-shim` | hosted compatibility shim | Replaces external `cdn.plot.ly` fetch with a local placeholder implementation. |
| RDKit Minimal JS | `app/static/vendor/rdkit/RDKit_minimal.js` | local shim | hosted compatibility shim | Preserves structure-search boot path without external or missing asset failures. |
| RDKit Minimal WASM | `app/static/vendor/rdkit/RDKit_minimal.wasm` | placeholder | local placeholder | Present so hosted paths resolve locally. Full WASM should be vendored in a later slice. |

Current external asset origins found in the legacy report code path:

- `https://3Dmol.org/build/3Dmol-min.js`
- `https://cdn.plot.ly/plotly-2.26.0.min.js`

The hosted example release patches those references to local `/static/vendor/...` paths.