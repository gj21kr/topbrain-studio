# Local TopBrain data conversion

Research use only, not for clinical decision.

The converter reads a local TopBrain CTA label volume and produces a static,
embedded GLB plus a JSON manifest (schema 1 for vessels, schema 2 for combined anatomy). TopBrain covers
vascular structures and does not supply a complete head-and-neck anatomy atlas.
No bone, muscle, nerve, organ or neck coverage is invented or inferred from
missing labels.

**The GitHub repository distributes code only.** Source volumes, segmentations,
derived GLB files, JSON manifests and case-specific spatial metadata are never
distributed through this project. Obtain any data separately under its applicable
terms and keep it in local storage. Published tests use synthetic inputs.

## Source, attribution and permitted use

- Data owner: **University Hospital of Zurich, Department of Neurology (USZ)**.
- Title: **TopBrain 2025 MICCAI Challenge Data Release**. Record the actual release
  identifier with each local conversion.
- Dataset: [TopBrain 2025 challenge](https://topbrain2025.grand-challenge.org).
- The local release README requests the challenge website and the
  [TopCoW challenge preprint](https://arxiv.org/abs/2312.17670) as citations.
- The supplied `License.txt` permits non-commercial use with author/title/dataset
  attribution. Commercial use requires prior permission from the data owner.
  This is not a public-domain or unrestricted-commercial dataset.
- The output manifest retains the complete local license text, attribution,
  checksums and release identifier. The optional full-name mapping supplied with
  this local dataset is recorded by checksum; its expansions have not undergone
  independent anatomical review.
- Raw images remain in their original local storage. Derived meshes and spatial
  metadata stay in ignored `private-assets/`; never commit them, attach them to
  releases or copy them into a public build. Preserving attribution does not
  change this project's code-only distribution boundary.

## Installation and conversion (PowerShell)

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-data.txt
.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v

.venv\Scripts\python.exe scripts/convert_topbrain.py `
  --input '<local-release>\labelsTr_topbrain_ct\<case>.nii.gz' `
  --labelmap '<local-release>\itksnap_labelmap_txt\labelmap_topbrain_ct.txt' `
  --fullnames '<local-release>\itksnap_labelmap_txt\labelmap_topbrain_ct - fullnames.txt' `
  --license '<local-release>\License.txt' `
  --units-reference '<local-release>\imagesTr_topbrain_ct\<matching-case>_0000.nii.gz' `
  --output private-assets/topbrain-cta-001
```

The output pair is `private-assets/topbrain-cta-001.glb` and
`private-assets/topbrain-cta-001.json`. Open the GLB and manifest together in the
viewer, or use the app's explicitly local asset entry point when available.
These are the app's fixed local output names, not source-case identifiers.
The converter does not copy the source image, intensity data or source filename
to the result. Do not select a `public/` output directory.

Use `--units-reference` when the label NIfTI has unknown spatial units and a
matching source image provides explicit unit information.
The converter checks identical volume dimensions and the full affine before
using that header as unit evidence. It records the original and resolved unit
values, reference checksum and decision in the local manifest. A mismatched image, missing
units evidence or absent sform/qform is rejected. Image pixel intensities are not
loaded or exported when reading the reference header.

## Coordinate and mesh contract

### Optional TotalSegmentator results

Add this option to the conversion command above:

```powershell
  --total-masks '<local-release>\totalV2\imagesTr_topbrain_ct\<matching-case>_0000'
```

Select the same case as `--input`; matching grids alone cannot establish case
identity. This option reads per-structure `.nii`/`.nii.gz` binary (0/1) masks.
Each must have an explicit sform/qform, known spatial units, identical volume
dimensions and the same physical voxel-to-world transform as the vessel labels.
Equivalent mm/meter units are accepted. Mismatched grids, nonbinary values,
duplicate structure names and missing spatial evidence stop conversion before
output is written. Automatic registration/resampling is not performed.

Empty masks are skipped and recorded in local metadata. Nonempty masks become
separate `total-*` mesh nodes, so overlaps cannot overwrite TopBrain labels.
Anatomical names come from the mask filenames, not an inferred numeric class map.
Use only anatomical structure keys as filenames. Individual source checksums,
affines, empty-mask records and the original dataset license remain local.
The `totalV2` directory name does not establish the prediction model version;
the manifest explicitly records that version as unverified.

Added anatomy receives its own rigid `explode` vector so the **Separate
structures** slider moves it together with the vessels. Sided masks
(`*_left`/`*_right`) move laterally with the same sign as TopBrain vessels
(glTF x, Right positive). Midline structures separate along the vertical axis
by group: skull +0.06 m, brain +0.04 m, vessels +0.02 m, spinal cord −0.02 m,
other bones −0.04 m; remaining midline anatomy moves anteriorly (−0.04 m in
glTF z). The viewer normalizes the largest vector to a fixed on-screen
distance, so only these ratios matter; assembled (0%) restores original
coordinates. Assets converted before this rule carry `[0, 0, 0]` for anatomy
and must be reconverted to separate.

Combined exports use schema version 2 with per-structure `source`,
`defaultVisible` and `defaultOpacity`. Schema 2 guarantees exactly one thing:
every structure names its own source. The viewer falls back to the manifest
source for a structure without one, which in a combined export would attribute
a TotalSegmentator prediction to TopBrain, so both the converter and the viewer
reject a schema-2 manifest that breaks this. Legacy schema-1 vessel assets
carry no per-structure source and remain supported. Vessels start visible; added anatomy starts hidden. Brain and skull
default to 20% base structure opacity, other anatomy to 65%. The surrounding
opacity control additionally multiplies the opacity of unselected structures
(initially 85%). Expand **Group visibility & opacity** for group controls. Group and
individual controls let the user reveal structures without changing their
original coordinates. Reset restores the manifest defaults. These predictions
do not extend the source field of view or constitute a complete anatomy atlas.

### Shared geometry rules

1. Read the unresampled NIfTI array in original voxel-index order. NiBabel's full
   affine maps these coordinates to RAS+, even when voxel axis codes are LPS.
   See [NiBabel coordinate documentation](https://nipy.org/nibabel/coordinate_systems.html).
2. For every present nonzero label, find its complete voxel bounding box, crop,
   then add a one-voxel zero-valued border. Run marching cubes at 0.5 with step
   size 1. Padding closes surfaces touching both crop and source-image edges.
3. Undo crop offset and padding, apply the complete affine including translation,
   rotation and shear, and convert the declared spatial unit to millimeters.
4. Map RAS millimeters to glTF meters as `(x, z, -y) / 1000`. No centering or
   per-structure repositioning is baked into the exported anatomy. Trimesh also
   corrects face winding for transforms that change handedness.
5. Store original affine, source/resolved units, axis codes, spacing, all matrices,
   bounding boxes and one independently checkable voxel/vertex pair per label.
6. Export one mesh node named `label-###` per present label, matching manifest
   `id` and `meshName`. Label IDs, names and colors follow the local label map.
   No smoothing or decimation is applied. Labels absent from the volume are not
   synthesized. Missing mappings fail conversion. Structures are grouped as
   `Arteries` up to label `LAST_ARTERY_LABEL` (34 in batch 1) and
   `Veins and sinuses` above it, because the ITK-SNAP label map has no group
   column. Re-confirm that boundary against the label map of any release that
   renumbers labels.

The GLB includes geometry, normals and solid-color PBR materials. It has no
external/data URI resources, compression extensions, skins or animations. The
converter validates that subset and the complete node-to-manifest correspondence
before writing. It rejects exports larger than the viewer's 150 MiB limit.

All structures receive their own rigid explode offset in the manifest; explosion
is an educational interaction and changes anatomical position. Reset must restore
the original coordinates. No dimensions or pathology should be assessed from
this viewer.

## Verification coverage

The converter was exercised against synthetic inputs and a separately held local
TopBrain volume during initial integration. Source-to-manifest correspondence,
closed outward-facing surfaces and exported vertices against source label
boundaries were checked locally. Case-specific geometry, measurements, hashes
and label-presence lists are intentionally excluded from this public document.

For each local conversion, verify label-to-node correspondence and the exported
coordinates against the source. Absence in a segmentation does **not** establish
anatomical absence; annotation completeness and field of view require source
review. Complete head/neck coverage remains unsupported.

Tests cover a rotated/sheared/anisotropic affine with translation, mm/meter unit
equivalence, a boundary singleton with closed outward-facing surface, mirrored
affine winding, unknown units, same-grid reference-header resolution, rejection
of a mismatched reference, duplicate labels, missing labels, static GLB names,
and prevention of private filename/free-text-header propagation. The current
NumPy 2.5/scikit-image combination emits an upstream array-shape deprecation
warning; conversion and checks succeed with the pinned requirements.

These checks exercise the converter's geometry and metadata boundary. They do
not replace browser/WebGL evidence, anatomical review, a source-volume coverage
figure or learner evaluation. See [browser validation](VALIDATION_2026-09-08.md)
for the separate interaction checks. Data redistribution is outside this
project's code-only publication scope.
