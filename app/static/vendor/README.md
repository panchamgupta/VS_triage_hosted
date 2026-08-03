# Local Vendor Assets

This directory is reserved for browser dependencies that must be served locally.

Production hosts for the hosted portal must not rely on outbound internet access or external CDNs.

Planned vendored assets:

- `3dmol/` for 3Dmol.js
- `plotly/` for Plotly
- `bootstrap/` only if the extracted static report depends on it
- `rdkit/` for RDKit Minimal JS/WASM
- `fonts/` for any non-system font files that the hosted report requires

TODO before production cutover:

1. Audit the generated static report for any CDN or remote asset references.
2. Copy required libraries into this vendor tree.
3. Update report JavaScript to load only local assets.
4. Confirm Content Security Policy remains `self`-hosted.