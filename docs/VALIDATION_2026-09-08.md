# Validation — 2026-09-08

This public record describes implementation checks only. The GitHub repository
distributes code; TopBrain source data, derived GLB/JSON files and case-specific
metadata remain local and are never distributed through this project.

## Automated checks

- `npm test`: 5 passed. Manifest provenance, IDs, coordinates; URI/extension rejection; bounded explosion; index buffer bounds; demo laterality.
- `npm run build`: passed.
- Python converter: 5 synthetic tests passed. Affine shear/rotation/reflection, boundary voxel surface, unknown units rejection. Reproduction commands and coordinate contract: [local conversion guide](TOPBRAIN_DATA.md).
- A separately held local source was converted and checked against its exported geometry. The original source remained unchanged. Case-specific results and assets are excluded from this repository.

## Browser observations

Local app `http://127.0.0.1:5181`, desktop browser viewport 1280 × 720. Actual visible WebGL scene inspected, not inferred solely from tests.

1. Procedural preview visibly renders and identifies itself as schematic.
2. Open local TopBrain case loads the separately prepared geometry and displays its structure names and IDs.
3. Structure search filters the list; isolate shows the selected mesh, hide removes it, and reset restores visibility.
4. Separation 100% visibly displaces the real structures; reset shows 0% and restores the assembled scene.
5. Guided study Next advances the selection and updates the explanation.
6. Superior camera changes the actual scene. Real coordinates are +X patient right, +Y superior, +Z posterior; anterior camera is −Z and left camera −X. Demo coordinates were corrected to use the same convention.
7. Direct two-file chooser import of a separately held local GLB + JSON succeeds.
8. No browser error/warning was reported in the inspected TopBrain logs.

## Local data boundary

- `/local-case/manifest.json` returns 200 with JSON and no-store caching.
- Direct `/private-assets/topbrain-cta-001.json` returns 403.
- Cross-site requests to the local case route return 403.
- Assets and data environments are Git-ignored; static build contains no GLB/NIfTI assets.

## Limitations

Screenshots were inspected during browser verification; a persistent desktop/mobile screenshot suite is not saved in this repository. No FPS benchmark, CT overlay review, clinical validation or user study is claimed. A missing segmentation label does not imply anatomical absence. The publication of this code does not include permission to distribute any original or derived data.
