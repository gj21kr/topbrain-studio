# Splatomy

Personal portfolio project: an interactive CT anatomy atlas. A Python converter turns one subject of the public TotalSegmentator dataset (CC BY 4.0) into an embedded GLB plus a JSON manifest; a three.js viewer loads them across a validated asset boundary that both sides enforce.

This repository distributes code. The dataset is downloaded from Zenodo by whoever runs the converter, and derived assets (GLB geometry, manifests, splat files) stay in ignored local storage such as `private-assets/`, except an attributed demo asset the maintainer explicitly chooses to publish. Tests use synthetic fixtures, never dataset files.

The one published exception is the maintainer-approved BodyParts3D 4.0 reference atlas (CC BY 4.0, Database Center for Life Science) that the public demo opens with: `public/reference/bodyparts3d.glb`, `public/reference/bodyparts3d.json` and `public/reference/ATTRIBUTION.txt`, 24 selected structures (cerebral vessels, skull, brain and proximal supply segments) converted from the official PART-OF archive by `scripts/prepare_bodyparts3d.py`. Its four dashed `connectionGuides` are schematic display guides where the archive has no cervical carotid or vertebral segments, not official meshes. All three files are required for publication, their digests are pinned in `scripts/check-public-build.mjs`, and any other public anatomy asset needs a new explicit maintainer decision.

Keep source provenance, coordinate transforms and the dataset license attached to every converted asset, and never present the landing-page schematic as dataset anatomy. This application is not a diagnostic device. Do not change the code license without the maintainer's instruction. No git add/commit/push without an explicit user request.

Geometry may be simplified (smoothing, decimation, resampling) when the gain is clear and measured. Record what was done and the measured error in the manifest so the asset stays honest about its distance from the source voxels.

Verify changes with `python -m unittest discover -s tests -t .`, `npm test`, `npm run build`, then a real browser interaction and visual check for scene changes. Tests alone do not prove WebGL rendering.
