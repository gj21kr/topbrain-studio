# Data and conversion

The converter reads one subject of a public dataset and produces a static,
fully embedded GLB plus a JSON manifest that the viewer loads. This document is
the contract between the two.

## Sources

**TotalSegmentator CT dataset v2.0.1** (Wasserthal et al.), CC BY 4.0.
Dataset: https://doi.org/10.5281/zenodo.10047292 · paper: https://doi.org/10.1148/ryai.230024

**TopBrain 2025 data release** (Yang et al.): 25 CTA/MRA pairs of the TopCoW
image data with whole-brain vessel label maps, 36 unified classes (v2) or 40 CT
/ 42 MR classes (v1, adds dural sinuses and deep veins on CT, extracranial
arteries on MR). https://doi.org/10.5281/zenodo.21972006
**TopCoW training data release** (Yang et al.): 250 CTA/MRA with the 13 Circle
of Willis classes. https://doi.org/10.5281/zenodo.15692630
Both are braincase-cropped, defaced, LPS+ NIfTI, and both carry the
opendata.swiss terms "Open use. Must provide the source. Use for commercial
purposes requires permission of the data owner" (University Hospital Zurich).
Derived assets are therefore non-commercial and stay local.

## Subject layouts

The TotalSegmentator layout is one binary mask per structure:

```
s0011/
  ct.nii.gz                    the CT volume (intensities are never exported)
  segmentations/
    liver.nii.gz               one 0/1 mask per structure, 117 at most
    aorta.nii.gz
    ...
```

The label-map layout is one integer per structure, as
`scripts/prepare_topbrain_subject.py` writes it from a release case:

```
topcow_ct_001/
  image.nii.gz                 the CTA or MRA volume (intensities are never exported)
  labels.nii.gz                one label value per structure
  labelmap.json                {"1": {"key": "ba", "name": "Basilar artery", "label": "BA"}, ...}
  dataset.json                 attribution, license, modality, label kind, catalog
```

Keys are the release label names lower-cased with `-` folded to `_` and a
leading `3rd` spelled `third` (`r_ica_c6_c7`, `l_pcom`, `third_a2`); sides come
from the `l_`/`r_` prefix. Every non-zero value in `labels.nii.gz` must be
named in `labelmap.json`, and every named value that is absent from the volume
is listed under `metadata.skippedEmptyMasks`, so a label the catalog does not
know is never dropped silently.

In both layouts, masks that share the image's physical voxel grid are meshed; a
mask on a different grid stops the conversion rather than being resampled. An
empty mask is not evidence that the structure is absent, only that the scan did
not cover it or the label is empty.

## Commands

```
python scripts/convert_subject.py --subject <dataset>/s0011 --output private-assets/local-case
```

writes `private-assets/local-case.glb` and `.json` for a TotalSegmentator
subject. For a TopBrain or TopCoW case, first assemble the subject folder:

```
python scripts/prepare_topbrain_subject.py --release <unzipped release> --patient 001 --modality ct --output private-assets/subjects/topcow_ct_001
python scripts/convert_subject.py --subject private-assets/subjects/topcow_ct_001 --output private-assets/local-case
```

`--labels v1|v2` picks the TopBrain label set, `--kind topcow` reads the TopCoW
release folders (`imagesTr/`, `cow_seg_labelsTr/`). Derived assets stay out of
the repository.

## Pipeline

1. Load the image (`ct.nii.gz` or `image.nii.gz`); require a 3-D volume with
   an explicit sform or qform and spatial units of mm, meter or micron. No
   fallback geometry is accepted.
2. Build the voxel→glTF transform from the full affine: voxel → RAS mm →
   `(x, z, -y) / 1000` glTF metres (Y up). Rotation, shear, spacing and origin
   are all kept; nothing is centred or normalised in the mesh.
3. For every mask: check the grid (shape, and the physical transform to 1e-8 m),
   require binary values, crop to the structure's bounding box, pad one voxel
   of background so surfaces close at the image edge, and run marching cubes at
   level 0.5. Trimesh corrects face winding when the affine flips handedness.
4. Store the affine, units, spacing, axis codes, per-structure bounding boxes
   and one independently checkable voxel/vertex pair per structure.
5. Export one mesh node per structure, named by the structure key, matching the
   manifest's `id` and `meshName`.

No smoothing, decimation or resampling is applied today. When one is added it
must be recorded under `metadata.processing` together with its measured error
against the source voxels.

## Structure catalogs

`dataset.json` names the catalog. The TotalSegmentator catalog
(`STRUCTURE_GROUPS`) places the 117 keys into Brain, Skull, Spinal cord,
Vertebrae, Ribs, Limb bones, Heart, Arteries, Veins, Lungs & airways, Abdominal
organs, Urinary, Glands and Muscles; the skeleton and circulation open visible,
soft tissue starts hidden. The brain vessel catalog (`VESSEL_GROUPS`) places the
TopBrain and TopCoW keys by their tokens into Anterior circulation (ICA, MCA,
ACA, Acom, AChA, ophthalmic), Posterior circulation (BA, PCA, Pcom, VA, SCA,
AICA, PICA), Veins & sinuses (SSS, straight sinus, vein of Galen, internal
cerebral veins, basal veins) and Extracranial arteries (ECA, STA, maxillary,
middle meningeal); arteries open visible, veins start hidden. Tests assert that
every key of every release label map lands in a named group. Each group carries
a color, a default opacity and an explode entry.

Laterality is read from the key (`_left`/`_right`, `_l`/`_r`, or the mid-key
`_left_`/`_right_` of ribs). Every structure receives a rigid explode vector in
glTF metres: sided structures move laterally with one shared sign, and the
group supplies the superior/posterior components so nested anatomy parts along
the body axis. Explosion is an educational interaction and changes anatomical
position; Reset restores the manifest defaults.

## GLB and manifest contract

The GLB includes geometry, normals and solid-color PBR materials. It has no
external or data URI resources, compression extensions, skins or animations.
The converter validates that subset and the complete node-to-manifest
correspondence before writing, and rejects exports over the viewer's 150 MiB
limit or with any mesh over 3,000,000 vertices or 9,000,000 indices.

The chunks must tile the file exactly: a JSON chunk, an optional BIN chunk and
nothing after it. The converter and the viewer both check that layout. The
converter additionally proves that every buffer view fits its buffer and every
accessor's bytes fit its view; the viewer does not repeat that walk because its
glTF loader re-derives the same bounds while parsing.

Manifests are schema 2, which guarantees exactly one thing: every structure
names its own source. The viewer falls back to the manifest source for a
structure without one, so both sides reject a schema-2 manifest that breaks
this. Schema-1 manifests (the landing-page schematic) remain accepted.

The browser half of every limit above lives in `src/model.ts`; a Python test
reads that file and fails if either side moves alone.

## Image context layer

`scripts/splat_context.py` reads the same image and writes
`<stem>.context.ply` and `<stem>.context.json` next to the GLB. The PLY is the
3D Gaussian Splatting layout (`x y z`, `f_dc_0..2`, `opacity`, `scale_0..2`,
`rot_0..3`, all float32, binary little-endian) that the viewer's Spark renderer
loads directly.

```
python scripts/splat_context.py --subject <dataset>/s0011 --output private-assets/local-case
```

One Gaussian per selected voxel, initialised from the volume without any
fitting:

- **Selection** for CT and CTA is a transfer function over Hounsfield units:
  bone (300 HU and above, every voxel, alpha 0.85), contrast-filled vessels and
  dense soft tissue (150–300 HU, every voxel, alpha 0.45) and soft tissue
  (−200–150 HU, every third voxel per axis, alpha 0.06). Air and the table fall
  below the window. MRA has no unit, so its bands are percentiles of the
  volume's own intensities, resolved per subject and recorded: vessels (the top
  1 %, every voxel, alpha 0.85) and tissue (55th–99th percentile, every third
  voxel, alpha 0.05). When a selection would exceed the splat limit, the band
  holding the most splats is strided one step further until it fits, and the
  JSON records both `strideRequested` and the resolved `stride` per band. A
  0.5 mm braincase CTA reaches the limit on bone alone and ends at stride 2.
- **Placement** applies the GLB's own `voxelToGltfM` to the voxel centre, so
  the layer and the meshes share one frame with no alignment step in the
  viewer. The viewer gives the layer exactly the centring and scaling it gives
  the meshes, and no axis flip: the PLY is already glTF Y-up (verified against
  Spark's decoder, which keeps PLY coordinates as written).
- **Shape** is the voxel's own frame: the affine's rotation becomes the
  quaternion, half the (strided) voxel size per axis becomes the scale, so
  anisotropic and rotated volumes stay correct. Shear is rejected.
- **Color** is the band's RGB written as SH degree-0 coefficients
  (`(rgb − 0.5) / 0.2820948`), opacity as its logit, scale as its log.

The context JSON carries the modality, the resolved transfer function, the
splat count, the image checksum (`ctSha256`, whatever the modality), the voxel
transform, one witness splat (voxel index and expected
position) and the PLY's SHA-256. The viewer accepts a layer only when its JSON
count equals the count in the PLY header, its CT checksum equals the manifest's
and its voxel transform equals the manifest's to 1e-9, so a layer from another
subject or another frame is refused rather than drawn in the wrong place.

The limit is 2,000,000 splats and, in the app, a 120 MB PLY. A whole-body scan
at 1.5 mm yields about 1.7 million splats; the converter and the viewer both
check the count, the property layout and finite positions, and the Python test
reads `src/model.ts` so the two halves cannot drift.

Voxel-sized Gaussians stack along a view ray, so even the 0.06 soft-tissue
alpha turns opaque through a body; the viewer's Density slider multiplies every
splat's alpha and opens at 35 %.

The layer is image intensity, not segmentation: it is meant to show what tissue
a mesh boundary sits in. For the brain vessel releases, which segment no skull
or brain, it is the only view of the surrounding anatomy. Rendering 1.7 million Gaussians needs a real GPU; on
software WebGL the frame time is seconds.

## Privacy and provenance

The manifest carries geometry, affines, checksums of the source files, the
dataset citation and license, and the subject's dataset identifier. It never
carries image intensities or free-text NIfTI header fields. The dataset is
public and anonymised; the same rule keeps the manifest small and auditable.
