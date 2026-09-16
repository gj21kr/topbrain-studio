"""Convert local TopBrain NIfTI labels to a static embedded GLB and manifest.

Research use only, not for clinical decision. No resampling, smoothing or
decimation is performed. All nonzero labels must have an explicit label mapping.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import logging
from pathlib import Path
import platform
import re
import shlex
import struct
import time

import nibabel as nib
import numpy as np
from skimage.measure import marching_cubes
import trimesh


LOGGER = logging.getLogger(__name__)
UNIT_TO_MM = {"mm": 1.0, "meter": 1000.0, "micron": 0.001}
RAS_MM_TO_GLTF_M = np.array(
    [[0.001, 0, 0, 0], [0, 0, 0.001, 0], [0, -0.001, 0, 0], [0, 0, 0, 1]],
    dtype=np.float64,
)
# The ITK-SNAP label map carries no group column, so the only signal for the
# arteries/veins split is the release's own label numbering: batch 1 numbers
# arteries 1-34 and veins/sinuses above that. Re-confirm against the label map
# before converting a release that renumbers labels.
LAST_ARTERY_LABEL = 34
ARTERY_GROUP = "Arteries"
VEIN_GROUP = "Veins and sinuses"
VESSEL_GROUPS = (ARTERY_GROUP, VEIN_GROUP)
# The browser half of this asset boundary lives in src/model.ts: inspectGlb
# enforces the byte limit, validateMeshData the per-mesh element counts. Both
# halves must move together or the converter writes files the viewer refuses.
MAX_GLB_BYTES = 150 * 1024 * 1024
MAX_MESH_VERTICES = 3_000_000
MAX_MESH_INDICES = 9_000_000
SOURCE = "TopBrain 2025 MICCAI Challenge Data Release, batch 1 (2025-07-30)"
WEBSITE = "https://topbrain2025.grand-challenge.org"
OWNER = "University Hospital of Zurich, Department of Neurology (USZ)"
DISCLAIMER = "Research use only, not for clinical decision."


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_labelmap(path: Path, fullnames_path: Path | None = None) -> dict[int, dict]:
    """Read the supplied ITK-SNAP label IDs/colors and optional source full names."""
    fullnames = {}
    if fullnames_path:
        for line in fullnames_path.read_text(encoding="utf-8-sig").splitlines():
            if "→" in line:
                short, full = line.split("→", 1)
                fullnames[short.strip()] = full.strip()
    labels = {}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), 1
    ):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = shlex.split(line)
        if len(fields) != 8:
            raise ValueError(f"Invalid label map row {line_number}; expected 8 fields.")
        label, red, green, blue = map(int, fields[:4])
        if (
            label < 0
            or label in labels
            or any(c < 0 or c > 255 for c in [red, green, blue])
        ):
            raise ValueError(f"Invalid or duplicate label/color at row {line_number}.")
        if not fields[7].strip():
            raise ValueError(f"Empty label name at row {line_number}.")
        labels[label] = {
            "shortName": fields[7],
            "name": fullnames.get(fields[7], fields[7]),
            "color": f"#{red:02x}{green:02x}{blue:02x}",
        }
    if not labels:
        raise ValueError("Label map contains no labels.")
    return labels


def voxel_to_gltf_transform(affine: np.ndarray, source_unit: str) -> np.ndarray:
    """Return voxel→glTF meters including rotation, shear, origin and spacing."""
    if source_unit not in UNIT_TO_MM:
        raise ValueError("NIfTI spatial units must explicitly be mm, meter or micron.")
    affine = np.asarray(affine, dtype=np.float64)
    if affine.shape != (4, 4) or not np.isfinite(affine).all():
        raise ValueError("NIfTI affine must be a finite 4×4 matrix.")
    if (
        not np.allclose(affine[3], [0, 0, 0, 1])
        or abs(np.linalg.det(affine[:3, :3])) < 1e-12
    ):
        raise ValueError("NIfTI affine must be invertible and homogeneous.")
    to_mm = np.diag([UNIT_TO_MM[source_unit]] * 3 + [1.0])
    return RAS_MM_TO_GLTF_M @ to_mm @ affine


def label_mesh(
    volume: np.ndarray, label: int, transform: np.ndarray
) -> tuple[trimesh.Trimesh, dict]:
    """Extract a complete 0.5 isosurface after bounding-box crop and zero padding."""
    mask = volume == label
    occupied = [
        np.flatnonzero(np.any(mask, axis=tuple(a for a in range(3) if a != axis)))
        for axis in range(3)
    ]
    if any(len(axis) == 0 for axis in occupied):
        raise ValueError("Cannot extract an absent label.")
    lower = np.array([axis[0] for axis in occupied])
    upper = np.array([axis[-1] + 1 for axis in occupied])
    cropped = mask[tuple(slice(int(lo), int(hi)) for lo, hi in zip(lower, upper))]
    # A full background layer closes structures even at the original image edge.
    padded = np.pad(cropped, 1, constant_values=False).astype(np.uint8)
    vertices, faces, _, _ = marching_cubes(
        padded, level=0.5, gradient_direction="ascent", allow_degenerate=False
    )
    voxel_vertices = vertices.astype(np.float64) + lower - 1
    mesh = trimesh.Trimesh(vertices=voxel_vertices, faces=faces, process=False)
    # Trimesh reverses face winding when this transform changes handedness.
    mesh.apply_transform(transform)
    bounds = mesh.bounds.tolist()
    return mesh, {
        "voxelCount": int(np.count_nonzero(cropped)),
        "voxelBoundingBoxExclusive": [lower.tolist(), upper.tolist()],
        "vertexCount": len(mesh.vertices),
        "triangleCount": len(mesh.faces),
        "boundsGltfM": bounds,
        "closedSurface": bool(mesh.is_watertight),
        "affineWitness": {
            "voxel": voxel_vertices[0].tolist(),
            "gltfM": mesh.vertices[0].tolist(),
        },
    }


# glTF 2.0 accessor element sizes, needed to prove an accessor's bytes exist.
COMPONENT_BYTES = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
TYPE_COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


def _size(value, default=None):
    """A JSON number that is a usable byte count, never a bool or a float."""
    if value is None and default is not None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("GLB binary layout uses a non-integer size.")
    return value


def validate_binary_layout(document: dict, binary_length: int) -> None:
    """Prove every accessor's bytes exist inside the GLB's binary chunk.

    validate_embedded_glb already checks that per-mesh element counts stay
    inside the browser's limits, but a count is only a claim until the bytes
    behind it are shown to exist. An embedded GLB references no URIs, so all of
    them live in the single BIN chunk. Index *values* are still the browser's
    check after it parses; this is about extent, not content.
    """
    buffers = document.get("buffers", [])
    if len(buffers) > 1:
        raise ValueError("An embedded GLB must hold a single binary buffer.")
    buffer_length = _size(buffers[0].get("byteLength")) if buffers else 0
    # The BIN chunk is padded to a 4-byte boundary, so it may run up to 3 bytes
    # past the buffer it carries, but never short of it.
    if buffers and not 0 <= binary_length - buffer_length <= 3:
        raise ValueError("GLB buffer does not match the binary chunk that carries it.")
    views = document.get("bufferViews", [])
    for view in views:
        if _size(view.get("buffer"), 0) != 0:
            raise ValueError("GLB buffer view references a buffer that is not embedded.")
        length = _size(view.get("byteLength"))
        if _size(view.get("byteOffset"), 0) + length > buffer_length:
            raise ValueError("GLB buffer view falls outside the binary chunk.")
    for accessor in document.get("accessors", []):
        index = accessor.get("bufferView")
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(views):
            raise ValueError("GLB accessor has no buffer view inside this file.")
        component = COMPONENT_BYTES.get(accessor.get("componentType"))
        components = TYPE_COMPONENTS.get(accessor.get("type"))
        if component is None or components is None:
            raise ValueError("GLB accessor uses an unknown component type.")
        count, element = _size(accessor.get("count")), component * components
        stride = views[index].get("byteStride")
        span = (count - 1) * _size(stride) + element if stride else count * element
        if count and _size(accessor.get("byteOffset"), 0) + span > _size(views[index].get("byteLength")):
            raise ValueError("GLB accessor reads past the end of its buffer view.")


def validate_embedded_glb(payload: bytes, expected_names: set[str]) -> dict:
    """Check the static GLB subset accepted by the browser before writing.

    Mirrors every rejection in src/model.ts: inspectGlb (size, header, chunk,
    URIs, extensions), readAsset (one parsed mesh per manifest structure with
    equal names) and validateMeshData (per-mesh element counts), plus the chunk
    layout the browser half also checks. validate_binary_layout then proves the
    bytes behind those counts exist. Index *values* live in the binary chunk and
    stay the browser's check after it parses.
    """
    if len(payload) > MAX_GLB_BYTES:
        raise ValueError("Generated GLB exceeds the browser's 150 MB import limit.")
    if len(payload) < 20 or struct.unpack_from("<III", payload) != (
        0x46546C67,
        2,
        len(payload),
    ):
        raise ValueError("Invalid GLB header.")
    chunk_length, chunk_type = struct.unpack_from("<II", payload, 12)
    if chunk_type != 0x4E4F534A or chunk_length % 4 or 20 + chunk_length > len(payload):
        raise ValueError("Invalid GLB JSON chunk.")
    # The chunks must tile the file exactly: a JSON chunk, an optional BIN chunk
    # and nothing after it. Trailing bytes and extra chunks are what a reader
    # silently ignores, so they are rejected rather than carried in the asset.
    binary_length, offset = 0, 20 + chunk_length
    if offset != len(payload):
        if offset + 8 > len(payload):
            raise ValueError("Invalid GLB binary chunk.")
        binary_length, binary_type = struct.unpack_from("<II", payload, offset)
        if (
            binary_type != 0x004E4942
            or binary_length % 4
            or offset + 8 + binary_length != len(payload)
        ):
            raise ValueError("Invalid GLB binary chunk.")
    document = json.loads(payload[20 : 20 + chunk_length])

    def inspect(value):
        if isinstance(value, dict):
            if "uri" in value:
                raise ValueError(
                    "GLB must not reference external or data URI resources."
                )
            for entry in value.values():
                inspect(entry)
        elif isinstance(value, list):
            for entry in value:
                inspect(entry)

    inspect(document)
    if any(
        document.get(key)
        for key in ["extensionsUsed", "extensionsRequired", "animations", "skins"]
    ):
        raise ValueError("GLB must be static and uncompressed without extensions.")
    accessors = document.get("accessors", [])

    def accessor(index, kind):
        if isinstance(index, bool) or not isinstance(index, int):
            raise ValueError(f"GLB mesh {kind} accessor is missing.")
        if not 0 <= index < len(accessors):
            raise ValueError(f"GLB mesh {kind} accessor is missing.")
        entry = accessors[index]
        if isinstance(entry.get("count"), bool) or not isinstance(
            entry.get("count"), int
        ):
            raise ValueError(f"GLB mesh {kind} accessor is missing.")
        return entry

    for mesh in document.get("meshes", []):
        primitives = mesh.get("primitives", [])
        # The viewer matches manifest names against parsed three.js meshes, and a
        # multi-primitive mesh becomes several of those behind one glTF node.
        if len(primitives) != 1 or primitives[0].get("mode", 4) != 4:
            raise ValueError("Each GLB mesh must hold exactly one triangle primitive.")
        position = accessor(
            primitives[0].get("attributes", {}).get("POSITION"), "position"
        )
        if position.get("type") != "VEC3" or not (
            3 <= position["count"] <= MAX_MESH_VERTICES
        ):
            raise ValueError(
                f"Each GLB mesh needs 3-{MAX_MESH_VERTICES} VEC3 vertices to stay importable."
            )
        elements = position["count"]
        if "indices" in primitives[0]:
            elements = accessor(primitives[0]["indices"], "index")["count"]
        if elements < 3 or elements % 3 or elements > MAX_MESH_INDICES:
            raise ValueError(
                f"Each GLB mesh needs complete triangles within {MAX_MESH_INDICES} indices."
            )
    names = [node.get("name") for node in document.get("nodes", []) if "mesh" in node]
    if len(names) != len(set(names)) or set(names) != expected_names:
        raise ValueError("GLB mesh node names differ from manifest structures.")
    validate_binary_layout(document, binary_length)
    return document


def anatomy_side(name: str) -> str:
    """Laterality from either naming convention the two import paths carry.

    TopBrain label short names mark the side with an R-/L- prefix, while
    TotalSegmentator mask keys use an _r/_right/_l/_left suffix. Mask keys are
    validated against [A-Za-z][A-Za-z0-9_]* and so can never hold a hyphen,
    so reading both conventions here cannot make one path answer for the other.
    Casing is normalised here rather than relied on from the caller.
    """
    lowered = name.lower()
    if lowered.startswith("r-") or lowered.endswith(("_r", "_right")):
        return "Right"
    if lowered.startswith("l-") or lowered.endswith(("_l", "_left")):
        return "Left"
    return "Not side-specific"


def anatomy_explode(key: str, group: str, side: str) -> list[float]:
    """Rigid separation vector in glTF meters (x Right+, y Superior+, z Posterior+).

    Sided structures move laterally with one sign for both import paths. The
    remaining component parts nested anatomy by group: skull highest, then brain
    and vessels above the origin, spinal cord and the rest of the bones below.
    A midline structure with no group of its own moves anteriorly instead,
    because a vertical move would keep it inside whatever encloses it.

    `key` is the TotalSegmentator mask key or the TopBrain label short name;
    only the skull needs to be recognised by name rather than by group.
    """
    lateral = 0.04 if side == "Right" else -0.04 if side == "Left" else 0.0
    # Vessels answer from the group alone, so no label short name can reach the
    # skull special case below.
    if group in VESSEL_GROUPS:
        return [lateral, 0.02, 0.0]
    if group == "Brain":
        return [lateral, 0.04, 0.0]
    if key == "skull":
        return [lateral, 0.06, 0.0]
    if group == "Bones":
        return [lateral, -0.04, 0.0]
    if group == "Spinal cord":
        return [lateral, -0.02, 0.0]
    return [lateral, 0.02, 0.0] if lateral else [0.0, 0.0, -0.04]


def append_total_masks(
    scene: trimesh.Scene,
    structures: list[dict],
    directory: Path,
    reference: nib.spatialimages.SpatialImage,
    resolved_unit: str,
) -> dict:
    """Add same-grid binary predictions without mixing their label IDs with TopBrain.

    The caller must select results belonging to the same case. Grid equality is
    necessary for this import path, but is not evidence of patient identity.
    """
    if not directory.is_dir():
        raise ValueError("TotalSegmentator directory does not exist.")
    files = sorted(
        p for p in directory.iterdir() if p.name.lower().endswith((".nii", ".nii.gz"))
    )
    if not files or len(files) > 500:
        raise ValueError("Expected 1–500 TotalSegmentator NIfTI mask files.")
    expected_transform = voxel_to_gltf_transform(reference.affine, resolved_unit)
    records, skipped = [], []
    ids = {s["id"] for s in structures}
    for path in files:
        name = re.sub(r"\.nii(?:\.gz)?$", "", path.name, flags=re.IGNORECASE)
        # Only anatomical structure keys may enter the manifest, never arbitrary
        # source paths or free-text headers. Names follow per-structure exports.
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,95}", name):
            raise ValueError("Mask filenames must be anatomical structure keys.")
        key = name.lower()
        node_name = "total-" + key.replace("_", "-")
        if node_name in ids:
            raise ValueError("Duplicate TotalSegmentator structure key.")
        ids.add(node_name)
        image = nib.load(path)
        if len(image.shape) != 3 or image.shape != reference.shape:
            raise ValueError(
                "TotalSegmentator masks must have the identical voxel grid as TopBrain."
            )
        if not int(image.header["sform_code"]) and not int(image.header["qform_code"]):
            raise ValueError(
                "TotalSegmentator masks require an explicit sform or qform."
            )
        unit = image.header.get_xyzt_units()[0]
        transform = voxel_to_gltf_transform(image.affine, unit)
        if not np.allclose(transform, expected_transform, rtol=0, atol=1e-8):
            raise ValueError(
                "TotalSegmentator masks must have the identical physical voxel grid as TopBrain."
            )
        volume = np.asanyarray(image.dataobj)
        if not np.all((volume == 0) | (volume == 1)):
            raise ValueError(
                "TotalSegmentator masks must contain only binary 0/1 values."
            )
        record = {
            "structureKey": name,
            "sourceSha256": checksum(path),
            "sourceUnits": unit,
            "sourceShapeVoxels": list(image.shape),
            "sourceAffine": image.affine.tolist(),
            "voxelToGltfM": transform.tolist(),
            "gridCheck": "identical dimensions and physical voxel-to-world transform",
        }
        if not np.any(volume):
            skipped.append(record)
            LOGGER.debug(
                "Skipped empty anatomy mask (%d/%d).",
                len(records) + len(skipped),
                len(files),
            )
            continue
        if len(structures) >= 500:
            raise ValueError("Combined asset exceeds the viewer's 500 structure limit.")
        if key == "brain":
            group, color, opacity = "Brain", "#dfb5b8", 0.2
        elif (
            key == "skull"
            or key.startswith(
                (
                    "vertebrae_",
                    "rib_",
                    "clavicula",
                    "scapula",
                    "humerus",
                    "femur",
                    "hip_",
                )
            )
            or key in {"sacrum", "sternum"}
        ):
            group, color, opacity = "Bones", "#ddd4bc", 0.2 if key == "skull" else 0.65
        elif key == "spinal_cord":
            group, color, opacity = "Spinal cord", "#efd581", 0.65
        else:
            group, color, opacity = "Other anatomy", "#a3c5bd", 0.65
        mesh, geometry = label_mesh(volume, 1, transform)
        mesh.visual = trimesh.visual.TextureVisuals(
            material=trimesh.visual.material.PBRMaterial(
                name=node_name,
                baseColorFactor=[int(color[i : i + 2], 16) for i in [1, 3, 5]] + [255],
                metallicFactor=0.0,
                roughnessFactor=0.65,
                doubleSided=True,
            )
        )
        scene.add_geometry(mesh, node_name=node_name, geom_name=node_name)
        side = anatomy_side(key)
        structures.append(
            {
                "id": node_name,
                "meshName": node_name,
                "name": name.replace("_", " "),
                "group": group,
                "side": side,
                "color": color,
                "explode": anatomy_explode(key, group, side),
                "source": "TotalSegmentator",
                "sourceShortName": name,
                "defaultVisible": False,
                "defaultOpacity": opacity,
                "description": "Local TotalSegmentator prediction. Coverage is limited to the supplied mask and image field of view. "
                + DISCLAIMER,
                "geometry": geometry,
            }
        )
        records.append(record)
        LOGGER.info(
            "Added anatomy structure %d (%d/%d masks).",
            len(records),
            len(records) + len(skipped),
            len(files),
        )
    return {
        "source": "TotalSegmentator",
        "inputMaskCount": len(files),
        "included": records,
        "skippedEmpty": skipped,
        "resampled": False,
        "caseAssociation": "Caller-selected same-case directory; grid equality does not prove case identity",
        "modelVersion": "Not supplied; totalV2 folder name is not a verified model version",
    }


def manifest_schema_version(structures: list[dict], combined: bool) -> int:
    """Pick the schema version and enforce the one thing that number promises.

    Schema 2 marks a combined export, and its promise to the viewer is that
    every structure names its own source. src/model.ts falls back to the
    manifest source for a structure that has none, which in a combined export
    would show a TotalSegmentator prediction under the TopBrain attribution.
    validateManifest rejects such a manifest; checking here as well means one is
    never written. Schema 1 vessel-only exports carry no per-structure source.
    """
    if not combined:
        return 1
    missing = [entry["id"] for entry in structures if not entry.get("source")]
    if missing:
        raise ValueError(
            f"Schema 2 requires an explicit source on every structure; {missing[0]} has none."
        )
    return 2


def convert(
    input_path: Path,
    labelmap_path: Path,
    license_path: Path,
    output: Path,
    fullnames_path: Path | None = None,
    units_reference_path: Path | None = None,
    total_masks_path: Path | None = None,
) -> dict:
    """Convert one CTA label volume; emit only selected non-PHI spatial metadata."""
    started = time.perf_counter()
    labels = read_labelmap(labelmap_path, fullnames_path)
    license_text = license_path.read_text(encoding="utf-8-sig").strip()
    if "non-commercial" not in license_text or "permission" not in license_text:
        raise ValueError(
            "Expected the local TopBrain non-commercial/permission license; review the supplied source."
        )
    image = nib.load(input_path)
    if len(image.shape) != 3:
        raise ValueError("Expected a 3-D NIfTI label image.")
    if not int(image.header["sform_code"]) and not int(image.header["qform_code"]):
        raise ValueError(
            "NIfTI must define an explicit sform or qform; fallback geometry is not accepted."
        )
    source_unit = image.header.get_xyzt_units()[0]
    resolved_unit = source_unit
    units_evidence = {"method": "label NIfTI header"}
    if source_unit == "unknown" and units_reference_path:
        reference = nib.load(units_reference_path)
        if reference.shape != image.shape or not np.allclose(
            reference.affine, image.affine, rtol=0, atol=1e-6
        ):
            raise ValueError(
                "Units reference must have the identical voxel grid and affine as the label image."
            )
        resolved_unit = reference.header.get_xyzt_units()[0]
        units_evidence = {
            "method": "matching image header; identical shape and affine verified",
            "referenceSha256": checksum(units_reference_path),
        }
    transform = voxel_to_gltf_transform(image.affine, resolved_unit)
    volume = np.asanyarray(image.dataobj)
    if (
        not np.isfinite(volume).all()
        or np.any(volume < 0)
        or np.any(volume != np.floor(volume))
    ):
        raise ValueError("Label voxels must be finite non-negative integers.")
    present = [int(value) for value in np.unique(volume) if value != 0]
    if not present or len(present) > 500:
        raise ValueError("Expected 1–500 nonzero labels.")
    if any(value not in labels for value in present):
        raise ValueError(
            "At least one source label has no mapping; supply the matching release label map."
        )
    scene = trimesh.Scene()
    structures = []
    for value in present:
        entry = labels[value]
        node_name = f"label-{value:03d}"
        mesh, geometry = label_mesh(volume, value, transform)
        color = entry["color"]
        rgba = [int(color[i : i + 2], 16) for i in [1, 3, 5]] + [255]
        mesh.visual = trimesh.visual.TextureVisuals(
            material=trimesh.visual.material.PBRMaterial(
                name=node_name,
                baseColorFactor=rgba,
                metallicFactor=0.0,
                roughnessFactor=0.65,
                doubleSided=True,
            )
        )
        scene.add_geometry(mesh, node_name=node_name, geom_name=node_name)
        short_name = entry["shortName"]
        side = anatomy_side(short_name)
        group = ARTERY_GROUP if value <= LAST_ARTERY_LABEL else VEIN_GROUP
        explode = anatomy_explode(short_name, group, side)
        structures.append(
            {
                "id": node_name,
                "name": entry["name"],
                "label": value,
                "group": group,
                "side": side,
                "description": f"TopBrain batch-1 CTA label {value}: {short_name}. Name and color follow the supplied label map. {DISCLAIMER}",
                "color": color,
                "meshName": node_name,
                "explode": explode,
                "sourceShortName": short_name,
                "geometry": geometry,
                **(
                    {
                        "source": "TopBrain",
                        "defaultVisible": True,
                        "defaultOpacity": 1.0,
                    }
                    if total_masks_path
                    else {}
                ),
            }
        )
    total_metadata = (
        append_total_masks(scene, structures, total_masks_path, image, resolved_unit)
        if total_masks_path
        else None
    )
    payload = scene.export(file_type="glb", include_normals=True)
    validate_embedded_glb(payload, {entry["meshName"] for entry in structures})
    dependencies = {
        name: importlib.metadata.version(name)
        for name in ["numpy", "nibabel", "scikit-image", "trimesh"]
    }
    manifest = {
        "schemaVersion": manifest_schema_version(structures, total_metadata is not None),
        "title": "TopBrain · real CTA vessel anatomy",
        "source": f"{OWNER}; {SOURCE}; {WEBSITE}",
        "license": "Non-commercial use with source attribution. Commercial use requires prior permission of the data owner (USZ).",
        "coordinateSystem": "glTF-Y-up",
        "units": "m",
        "provenance": f"Real segmentation geometry from the local TopBrain batch-1 release dated 2025-07-30, modality CTA. This is not a v3 dataset asset. Brain vessels only: no complete head/neck anatomy. {DISCLAIMER}",
        "structures": structures,
        "metadata": {
            "modality": "CTA",
            "release": "TopBrain batch 1, 2025-07-30",
            "sourceSha256": checksum(input_path),
            "labelmapSha256": checksum(labelmap_path),
            "fullnamesSha256": checksum(fullnames_path) if fullnames_path else None,
            "licenseSha256": checksum(license_path),
            "licenseText": license_text,
            "attribution": {
                "owner": OWNER,
                "title": SOURCE,
                "datasetUrl": WEBSITE,
                "citationRequestedByLocalReadme": "https://arxiv.org/abs/2312.17670",
            },
            "sourceUnits": source_unit,
            "resolvedSourceUnits": resolved_unit,
            "unitsEvidence": units_evidence,
            "sourceShapeVoxels": list(image.shape),
            "sourceAffine": image.affine.tolist(),
            "sourceAffineSpace": "NIfTI RAS+ in resolvedSourceUnits",
            "sourceAxisCodes": list(nib.aff2axcodes(image.affine)),
            "sourceSpacing": nib.affines.voxel_sizes(image.affine).tolist(),
            "sformCode": int(image.header["sform_code"]),
            "qformCode": int(image.header["qform_code"]),
            "sourceUnitToMm": UNIT_TO_MM[resolved_unit],
            "rasMmToGltfM": RAS_MM_TO_GLTF_M.tolist(),
            "voxelToGltfM": transform.tolist(),
            "coordinateRule": "voxel -> full NIfTI affine -> RAS mm -> (x,z,-y)/1000 glTF meters; no centering baked into mesh",
            "processing": {
                "method": "marching_cubes",
                "level": 0.5,
                "gradientDirection": "ascent",
                "crop": "per-label voxel bounding box",
                "paddingVoxels": 1,
                "stepSize": 1,
                "smoothing": False,
                "decimation": False,
            },
            "dependencies": dependencies,
            "python": platform.python_version(),
            "platform": platform.system(),
            "elapsedSeconds": round(time.perf_counter() - started, 3),
            "glbBytes": len(payload),
            "glbSha256": hashlib.sha256(payload).hexdigest(),
            "boundsGltfM": scene.bounds.tolist(),
            "clinicalUse": DISCLAIMER,
            "privacy": "No image intensities, source filename, patient identifiers or free-text NIfTI header fields exported. Geometry and affine remain local derived medical data.",
        },
    }
    if total_metadata is not None:
        manifest["title"] = "TopBrain · CTA vessels and TotalSegmentator anatomy"
        manifest["source"] += "; local TotalSegmentator predictions"
        manifest["provenance"] = (
            f"TopBrain batch-1 CTA vascular labels plus separately identified local TotalSegmentator predictions. Same physical voxel grid checked; no registration, resampling or invented missing anatomy. This is not a complete head/neck atlas. {DISCLAIMER}"
        )
        manifest["metadata"]["totalSegmentator"] = total_metadata
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".glb").write_bytes(payload)
    output.with_suffix(".json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, required=True, help="Local 3-D CTA NIfTI label image"
    )
    parser.add_argument(
        "--labelmap", type=Path, required=True, help="Matching ITK-SNAP label map"
    )
    parser.add_argument(
        "--fullnames",
        type=Path,
        help="Optional label-name expansions supplied with release",
    )
    parser.add_argument(
        "--license", type=Path, required=True, help="Local release License.txt"
    )
    parser.add_argument(
        "--units-reference",
        type=Path,
        help="Matching image NIfTI header used only if label units are unknown; grid and affine must match",
    )
    parser.add_argument(
        "--total-masks",
        type=Path,
        help="Same-case directory of TotalSegmentator binary NIfTI masks; matching physical voxel grid required",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output stem under ignored private-assets",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        manifest = convert(
            args.input,
            args.labelmap,
            args.license,
            args.output,
            args.fullnames,
            args.units_reference,
            args.total_masks,
        )
    except (OSError, ValueError, nib.filebasedimages.ImageFileError) as error:
        # Exception text from external libraries can contain sensitive source paths.
        LOGGER.error(
            "Conversion failed (%s). Check input format, spatial units, label map and destination permissions.",
            type(error).__name__,
        )
        raise SystemExit(1) from None
    LOGGER.info(
        "Converted %d labels; GLB %d bytes; %.3f seconds. %s",
        len(manifest["structures"]),
        manifest["metadata"]["glbBytes"],
        manifest["metadata"]["elapsedSeconds"],
        DISCLAIMER,
    )


if __name__ == "__main__":
    main()
