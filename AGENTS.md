# TopBrain Studio

Personal, non-commercial anatomy education project. The maintainer's canonical strategy is local-only at `~/.claude/strategies/topbrain-studio.md`; it is not required to run this repository.

This GitHub repository distributes code only. Never commit, upload, attach to releases or distribute TopBrain source volumes, segmentations, derived GLB geometry, JSON manifests or case-specific spatial metadata. Keep these files in ignored local storage, including `private-assets/`; do not put them in `public/` or documentation. Tests must generate synthetic fixtures.

TopBrain supplies vascular segmentations; do not label illustrative head shells or invented anatomy as TopBrain data. Keep source provenance, coordinate transforms, label IDs and the original dataset license attached to locally imported assets. This application is not a diagnostic device. Do not copy company CAD or proprietary code into this repository. Do not choose or change a code license without the maintainer's instruction. No git add/commit/push without an explicit user request.

Verify changes with `npm test`, `npm run build`, then a real browser interaction and visual check for scene changes. Tests alone do not prove WebGL rendering.
