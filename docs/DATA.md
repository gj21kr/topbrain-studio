# Data and conversion

The converter reads one subject of the public TotalSegmentator CT dataset and
produces a static, fully embedded GLB plus a JSON manifest that the viewer
loads. This document is the contract between the two.

## Source

TotalSegmentator CT dataset v2.0.1 (Wasserthal et al.), CC BY 4.0.
Dataset: https://doi.org/10.5281/zenodo.10047292 · paper: https://doi.org/10.1148/ryai.230024

Each subject is a directory:

```
s0011/
  ct.nii.gz                    the CT volume (intensities are never exported)
  segmentations/
    liver.nii.gz               one 0/1 mask per structure, 117 at most
    aorta.nii.gz
    ...
```

Masks that share the CT's physical voxel grid are meshed; a mask on a different
grid stops the conversion rather than being resampled. An empty mask is skipped
and listed under `metadata.skippedEmptyMasks`; it is not evidence that the
structure is absent, only that the scan did not cover it or the label is empty.

## Command

```
python scripts/convert_subject.py --subject <dataset>/s0011 --output private-assets/local-case
```

writes `private-assets/local-case.glb` and `.json`. Derived assets stay out of
the repository.

## Pipeline

1. Load `ct.nii.gz`; require a 3-D volume with an explicit sform or qform and
   spatial units of mm, meter or micron. No fallback geometry is accepted.
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

## Structure catalog

The 117 dataset keys are placed into viewer groups by `STRUCTURE_GROUPS` in the
converter: Brain, Skull, Spinal cord, Vertebrae, Ribs, Limb bones, Heart,
Arteries, Veins, Lungs & airways, Abdominal organs, Urinary, Glands, Muscles.
Each group carries a color, a default opacity and whether it is visible when the
asset opens; the skeleton and circulation open visible, soft tissue starts
hidden. A test asserts that every one of the 117 keys lands in a named group.

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

## Privacy and provenance

The manifest carries geometry, affines, checksums of the source files, the
dataset citation and license, and the subject's dataset identifier. It never
carries image intensities or free-text NIfTI header fields. The dataset is
public and anonymised; the same rule keeps the manifest small and auditable.
