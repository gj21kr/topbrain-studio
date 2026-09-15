# Combined anatomy integration verification

Implementation supports local TopBrain vascular labels and same-case
TotalSegmentator binary masks as independent structures. Vessel-only schema-1
assets remain supported; combined exports use schema 2.

## Automated checks

- Python: 10 synthetic converter tests passed, including overlapping masks,
  exported world-coordinate witnesses, equivalent physical units, empty masks,
  duplicate keys, nonbinary values and mismatched/missing spatial metadata.
- Frontend: 9 tests passed, including schema compatibility, invalid defaults,
  reset state and opacity composition.
- Production build and whitespace checks passed. The existing bundle-size
  advisory remains; no new dependencies were installed.

## Observed browser behavior

A locally held combined asset was loaded in the actual browser/WebGL viewer.
Vascular structures appeared by default. Brain, bone and spinal-cord group
controls revealed the additional geometry in the same scene. Changing brain
opacity, selecting its source-labelled entry and isolating it changed the
rendered scene. Selecting a translucent structure preserved its opacity.
Reset restored vascular-only visibility and imported opacity defaults.

At a 1280 × 720 viewport, the expanded group panel initially pushed the import
buttons below the footer. Compact desktop styling now keeps the controls and
structure list inside the available sidebar height; the resulting layout was
visually rechecked with the combined scene displayed.

Case-specific counts, source paths, geometry and manifests remain in ignored
local storage. The static distribution contains no local case data.

## Follow-up: separation of added anatomy

The first combined asset exported every TotalSegmentator structure with a zero
`explode` vector, so the **Separate structures** slider moved vessels only.
The converter now assigns group-directed vectors (lateral for sided masks,
vertical by group for midline masks, anterior for other midline anatomy); two
synthetic tests pin the vectors and confirm vessel vectors are unchanged. The
viewer was not modified. The local combined asset was reconverted; the GLB is
byte-identical and only the manifest changed. Feeding that manifest through the
viewer's own offset function gives nonzero, distinct displacements for every
added structure at 100% and zero at 0%. Interactive browser recheck of the
reconverted asset is still pending.

## Limits

These checks establish data import and rendering/interaction behavior, not
segmentation accuracy or clinical acceptance. Source-volume slice overlays,
cross-case coverage, frame-rate/GPU-memory benchmarks and automatic registration
of different grids were not performed. No smoothing or decimation is applied;
the source mask's voxel boundaries remain visible. Empty predictions do not
establish anatomical absence.
