"""Convert one dataset subject to a static embedded GLB and manifest.

Two subject layouts are read. TotalSegmentator: ct.nii.gz plus one binary mask
per structure in segmentations/. Label map: image.nii.gz, labels.nii.gz (one
integer per structure), labelmap.json (value -> structure key) and dataset.json
(attribution, license, modality), as scripts/prepare_topbrain_subject.py writes
for the TopBrain and TopCoW releases.

Research and education use only, not for clinical decision. Each structure is
extracted by marching cubes at the dataset's native voxel grid. Any smoothing,
decimation or resampling that is applied is recorded in the manifest together
with its measured effect; none is applied yet.
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
# The browser half of this asset boundary lives in src/model.ts: inspectGlb
# enforces the byte limit, validateMeshData the per-mesh element counts. Both
# halves must move together or the converter writes files the viewer refuses.
MAX_GLB_BYTES = 150 * 1024 * 1024
MAX_MESH_VERTICES = 3_000_000
MAX_MESH_INDICES = 9_000_000
DATASET = "TotalSegmentator CT dataset v2.0.1 (Wasserthal et al.)"
DATASET_URL = "https://doi.org/10.5281/zenodo.10047292"
DATASET_PAPER = "https://doi.org/10.1148/ryai.230024"
DATASET_LICENSE = "CC BY 4.0"
DATASET_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
DISCLAIMER = "Research and education use only, not for clinical decision."
# Attribution for the TotalSegmentator layout. A label-map subject carries its own
# dataset.json with the same keys, written by the dataset's prepare script.
TOTALSEGMENTATOR = {
    "dataset": DATASET,
    "datasetUrl": DATASET_URL,
    "datasetPaper": DATASET_PAPER,
    "datasetLicense": DATASET_LICENSE,
    "datasetLicenseUrl": DATASET_LICENSE_URL,
    "structureSource": "TotalSegmentator dataset",
    "modality": "CT",
    "labelKind": "ground-truth segmentation",
    "catalog": "totalsegmentator",
}
DATASET_JSON_KEYS = ("dataset", "datasetUrl", "datasetPaper", "datasetLicense", "datasetLicenseUrl", "structureSource", "modality", "labelKind", "catalog")

# How the dataset's 117 structure keys become viewer groups. Each entry is
# (group, color, default opacity, visible at load, matcher); the first match
# wins. Circulation and the skeleton form the opening view, soft tissue starts
# hidden so it can be revealed group by group.
STRUCTURE_GROUPS = (
    ("Brain", "#dfb5b8", 0.2, False, lambda k: k == "brain"),
    ("Skull", "#ddd4bc", 0.2, True, lambda k: k == "skull"),
    ("Spinal cord", "#efd581", 0.65, False, lambda k: k == "spinal_cord"),
    ("Vertebrae", "#ddd4bc", 0.65, True, lambda k: k.startswith("vertebrae_") or k == "sacrum"),
    ("Ribs", "#ddd4bc", 0.65, True, lambda k: k.startswith("rib_") or k in {"sternum", "costal_cartilages"}),
    ("Limb bones", "#ddd4bc", 0.65, True, lambda k: k.startswith(("clavicula", "scapula", "humerus", "femur", "hip_"))),
    ("Heart", "#c0392b", 1.0, True, lambda k: k in {"heart", "atrial_appendage_left"}),
    ("Arteries", "#d9534f", 1.0, True, lambda k: "artery" in k or k in {"aorta", "brachiocephalic_trunk"}),
    ("Veins", "#5b7fc4", 1.0, True, lambda k: "vein" in k or "vena" in k),
    ("Lungs & airways", "#a3c5bd", 0.35, False, lambda k: k.startswith("lung_") or k == "trachea"),
    ("Abdominal organs", "#e0a458", 0.65, False, lambda k: k in {"liver", "gallbladder", "pancreas", "spleen", "stomach", "duodenum", "small_bowel", "colon", "esophagus"}),
    ("Urinary", "#c9a36b", 0.65, False, lambda k: k.startswith(("kidney", "urinary_bladder", "prostate"))),
    ("Glands", "#b98cc9", 0.65, False, lambda k: k.endswith("_gland") or k.startswith("adrenal_gland")),
    ("Muscles", "#b5655a", 0.5, False, lambda k: k.startswith(("gluteus_", "iliopsoas_", "autochthon_"))),
)
FALLBACK_GROUP = ("Other anatomy", "#9fb3b0", 0.65, False)
# Brain vessel catalog for the TopBrain/TopCoW label maps. Keys are the release
# label names as prepare_topbrain_subject.py normalises them: lower case, "-"
# to "_", a leading "3rd" spelled "third" (r_ica_c6_c7, l_pcom, third_a2, sss).
# A key is placed by the tokens between its underscores. Arteries open visible;
# the venous system starts hidden.
def _tokens(key: str) -> set[str]:
    return set(key.split("_"))


ANTERIOR_TOKENS = {"ica", "mca", "m1", "m2", "m3", "aca", "a1a2", "a3", "a2", "acom", "acha", "oa"}
POSTERIOR_TOKENS = {"ba", "pca", "p1p2", "p3p4", "pcom", "va", "sca", "aica", "pica"}
VENOUS_TOKENS = {"vog", "sts", "icvs", "bvr", "sss"}
EXTRACRANIAL_TOKENS = {"eca", "sta", "maxa", "mma"}
VESSEL_GROUPS = (
    ("Veins & sinuses", "#5b7fc4", 0.85, False, lambda k: bool(_tokens(k) & VENOUS_TOKENS)),
    ("Extracranial arteries", "#c98b6b", 0.9, True, lambda k: bool(_tokens(k) & EXTRACRANIAL_TOKENS)),
    ("Posterior circulation", "#e08a5b", 1.0, True, lambda k: bool(_tokens(k) & POSTERIOR_TOKENS)),
    ("Anterior circulation", "#d9534f", 1.0, True, lambda k: bool(_tokens(k) & ANTERIOR_TOKENS)),
)
CATALOGS = {"totalsegmentator": STRUCTURE_GROUPS, "brain-vessels": VESSEL_GROUPS}
# Rigid separation per group as (superior, posterior) offsets in glTF metres;
# the lateral component comes from the structure's side. Nested anatomy parts
# along the body axis, organs swing anteriorly, muscles posteriorly.
GROUP_EXPLODE = {
    "Skull": (0.06, 0.0),
    "Brain": (0.04, 0.0),
    "Spinal cord": (-0.02, 0.0),
    "Vertebrae": (-0.04, 0.0),
    "Ribs": (-0.04, 0.0),
    "Limb bones": (-0.04, 0.0),
    "Heart": (0.0, -0.03),
    "Arteries": (0.02, 0.0),
    "Veins": (-0.02, 0.0),
    "Lungs & airways": (0.02, 0.0),
    "Abdominal organs": (-0.02, -0.04),
    "Urinary": (-0.04, 0.0),
    "Glands": (0.0, -0.02),
    "Muscles": (-0.02, 0.03),
    "Anterior circulation": (0.0, -0.02),
    "Posterior circulation": (0.0, 0.02),
    "Veins & sinuses": (0.02, 0.0),
    "Extracranial arteries": (-0.02, 0.0),
}


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


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
    """Laterality from the structure key's _left/_right or _l/_r suffix.

    TotalSegmentator names sided structures with a suffix (kidney_left; rib_right_4
    is the one exception where the side sits mid-key). The brain vessel label maps
    use a prefix (r_ica, l_pcom). Casing is normalised here rather than relied on
    from the caller.
    """
    lowered = name.lower()
    if lowered.endswith(("_r", "_right")) or "_right_" in lowered or lowered.startswith(("r_", "right_")):
        return "Right"
    if lowered.endswith(("_l", "_left")) or "_left_" in lowered or lowered.startswith(("l_", "left_")):
        return "Left"
    return "Not side-specific"


def classify_structure(key: str, groups=STRUCTURE_GROUPS) -> tuple[str, str, float, bool]:
    """Group, color, default opacity and initial visibility for a structure key."""
    for group, color, opacity, visible, matches in groups:
        if matches(key):
            return group, color, opacity, visible
    return FALLBACK_GROUP


def anatomy_explode(group: str, side: str) -> list[float]:
    """Rigid separation vector in glTF meters (x Right+, y Superior+, z Posterior+).

    Sided structures move laterally with one sign; the remaining components come
    from the group table so nested anatomy parts along the body axis. A group the
    table does not know moves anteriorly, because a structure that does not
    separate defeats the explode view; a test keeps every table entry non-zero.
    """
    lateral = 0.04 if side == "Right" else -0.04 if side == "Left" else 0.0
    superior, posterior = GROUP_EXPLODE.get(group, (0.0, -0.04))
    return [lateral, superior, posterior]


def resolve_units(header_unit: str, override: str | None) -> tuple[str, dict]:
    """Decide the spatial unit for a subject and say how it was decided.

    The dataset's NIfTI files leave xyzt_units unset, which nibabel reports as
    "unknown". Unitless NIfTI is millimetres by convention and the dataset is
    documented at 1.5 mm, so that is assumed, but only ever as a recorded
    assumption: the manifest keeps the header's own value next to the resolved
    one and the reason. An explicit --units wins over both.
    """
    if override:
        if override not in UNIT_TO_MM:
            raise ValueError("--units must be mm, meter or micron.")
        return override, {"method": "command-line override", "headerUnits": header_unit}
    if header_unit in UNIT_TO_MM:
        return header_unit, {"method": "NIfTI header", "headerUnits": header_unit}
    if header_unit == "unknown":
        return "mm", {
            "method": "assumed: NIfTI header has no spatial unit; unitless NIfTI is millimetres by convention and the dataset is documented at 1.5 mm",
            "headerUnits": header_unit,
        }
    raise ValueError("NIfTI spatial units must be mm, meter, micron or unset.")


def manifest_schema_version(structures: list[dict]) -> int:
    """Schema 2 promises the viewer that every structure names its own source.

    src/model.ts falls back to the manifest source for a structure that has
    none, which would attribute that structure to whatever the manifest source
    leads with. validateManifest rejects a schema 2 manifest that breaks this;
    checking here as well means one is never written. Schema 1 is the legacy
    single-source manifest the viewer still accepts; this converter writes 2.
    """
    missing = [entry["id"] for entry in structures if not entry.get("source")]
    if missing:
        raise ValueError(
            f"Schema 2 requires an explicit source on every structure; {missing[0]} has none."
        )
    return 2


KEY_PATTERN = r"[A-Za-z][A-Za-z0-9_]{0,95}"


def mask_files(masks_dir: Path, reference, unit: str):
    """The TotalSegmentator layout: one binary NIfTI per structure in segmentations/.

    Grid equality is required for every mask; it is what lets structures from
    separate files share one coordinate frame without registration.
    """
    if not masks_dir.is_dir():
        raise ValueError("Subject has no segmentations directory.")
    files = sorted(
        p for p in masks_dir.iterdir() if p.name.lower().endswith((".nii", ".nii.gz"))
    )
    if not files or len(files) > 500:
        raise ValueError("Expected 1–500 NIfTI mask files in segmentations/.")
    expected_transform = voxel_to_gltf_transform(reference.affine, unit)
    for path in files:
        name = re.sub(r"\.nii(?:\.gz)?$", "", path.name, flags=re.IGNORECASE)
        # Only anatomical structure keys may enter the manifest, never arbitrary
        # source paths or free-text headers. Names follow per-structure exports.
        if not re.fullmatch(KEY_PATTERN, name):
            raise ValueError("Mask filenames must be anatomical structure keys.")
        image = nib.load(path)
        if len(image.shape) != 3 or image.shape != reference.shape:
            raise ValueError("Masks must have the identical voxel grid as the CT.")
        if not int(image.header["sform_code"]) and not int(image.header["qform_code"]):
            raise ValueError("Masks require an explicit sform or qform.")
        mask_unit = image.header.get_xyzt_units()[0]
        # A mask on the CT's grid that declares no unit shares the CT's; one that
        # declares a unit is held to it, so a mislabelled file cannot slip in.
        transform = voxel_to_gltf_transform(image.affine, unit if mask_unit == "unknown" else mask_unit)
        if not np.allclose(transform, expected_transform, rtol=0, atol=1e-8):
            raise ValueError(
                "Masks must have the identical physical voxel grid as the CT."
            )
        volume = np.asanyarray(image.dataobj)
        if not np.all((volume == 0) | (volume == 1)):
            raise ValueError("Masks must contain only binary 0/1 values.")
        record = {
            "structureKey": name,
            "sourceSha256": checksum(path),
            "sourceUnits": mask_unit,
            "sourceShapeVoxels": list(image.shape),
            "sourceAffine": image.affine.tolist(),
            "voxelToGltfM": transform.tolist(),
            "gridCheck": "identical dimensions and physical voxel-to-world transform",
        }
        yield name, name.replace("_", " "), volume, record


def label_map_masks(subject_dir: Path, reference, unit: str):
    """The label-map layout: labels.nii.gz holds one integer per structure.

    labelmap.json maps each integer to a structure key and display name, as the
    dataset's prepare script wrote it. Every value the map names must appear in
    the volume's own value set or be reported as empty, and every non-zero value
    in the volume must be named, so a label the catalog does not know is never
    silently dropped.
    """
    labels_path = subject_dir / "labels.nii.gz"
    if not labels_path.is_file():
        raise ValueError("Subject has no labels.nii.gz.")
    label_map = json.loads((subject_dir / "labelmap.json").read_text(encoding="utf-8"))
    if not isinstance(label_map, dict) or not label_map or len(label_map) > 500:
        raise ValueError("labelmap.json must map 1–500 label values to structures.")
    image = nib.load(labels_path)
    if len(image.shape) != 3 or image.shape != reference.shape:
        raise ValueError("Labels must have the identical voxel grid as the image.")
    if not int(image.header["sform_code"]) and not int(image.header["qform_code"]):
        raise ValueError("Labels require an explicit sform or qform.")
    label_unit = image.header.get_xyzt_units()[0]
    transform = voxel_to_gltf_transform(image.affine, unit if label_unit == "unknown" else label_unit)
    if not np.allclose(transform, voxel_to_gltf_transform(reference.affine, unit), rtol=0, atol=1e-8):
        raise ValueError("Labels must have the identical physical voxel grid as the image.")
    volume = np.asanyarray(image.dataobj)
    if not np.issubdtype(volume.dtype, np.integer) or volume.min() < 0:
        raise ValueError("Labels must be non-negative integers.")
    present = {int(v) for v in np.unique(volume) if v}
    named = {}
    for value, entry in label_map.items():
        if not re.fullmatch(r"[1-9][0-9]{0,5}", str(value)) or not isinstance(entry, dict):
            raise ValueError("labelmap.json keys must be positive integers mapping to objects.")
        key, name = entry.get("key"), entry.get("name")
        if not isinstance(key, str) or not re.fullmatch(KEY_PATTERN, key) or not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError("Every label needs a structure key and a display name.")
        named[int(value)] = (key, name)
    unnamed = sorted(present - set(named))
    if unnamed:
        raise ValueError(f"labels.nii.gz holds values {unnamed[:5]} that labelmap.json does not name.")
    digest = checksum(labels_path)
    for value in sorted(named):
        key, name = named[value]
        record = {
            "structureKey": key,
            "labelValue": value,
            "sourceSha256": digest,
            "sourceUnits": label_unit,
            "sourceShapeVoxels": list(image.shape),
            "sourceAffine": image.affine.tolist(),
            "voxelToGltfM": transform.tolist(),
            "gridCheck": "identical dimensions and physical voxel-to-world transform",
        }
        yield key, name, (volume == value).astype(np.uint8), record


def subject_layout(subject_dir: Path) -> str:
    """Which layout a subject directory uses; label-map subjects carry dataset.json."""
    if (subject_dir / "ct.nii.gz").is_file():
        return "masks"
    if (subject_dir / "image.nii.gz").is_file() and (subject_dir / "dataset.json").is_file():
        return "labelmap"
    raise ValueError("Subject directory has neither ct.nii.gz nor image.nii.gz with dataset.json.")


def dataset_attribution(subject_dir: Path, layout: str) -> dict:
    """The dataset entry a manifest is attributed to, validated field by field."""
    if layout == "masks":
        return dict(TOTALSEGMENTATOR)
    data = json.loads((subject_dir / "dataset.json").read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("dataset.json must be an object.")
    for key in DATASET_JSON_KEYS:
        if not isinstance(data.get(key), str) or not data[key].strip() or len(data[key]) > 2000:
            raise ValueError(f"dataset.json is missing {key}.")
    if data["catalog"] not in CATALOGS:
        raise ValueError("dataset.json names an unknown structure catalog.")
    if data["modality"] not in {"CT", "CTA", "MRA"}:
        raise ValueError("dataset.json modality must be CT, CTA or MRA.")
    return {key: data[key] for key in DATASET_JSON_KEYS} | {"citation": data.get("citation", "")}


def mesh_structures(
    scene: trimesh.Scene,
    masks,
    reference: nib.spatialimages.SpatialImage,
    unit: str,
    subject: str,
    dataset: dict = TOTALSEGMENTATOR,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Mesh every non-empty structure mask that shares the image's physical voxel grid.

    `masks` is a segmentations/ directory (TotalSegmentator layout) or any
    iterable of (key, display name, binary volume, source record).
    """
    if isinstance(masks, Path):
        masks = mask_files(masks, reference, unit)
    groups = CATALOGS[dataset["catalog"]]
    structures, records, skipped, ids = [], [], [], set()
    for name, display, volume, record in masks:
        key = name.lower()
        if key in ids:
            raise ValueError("Duplicate structure key.")
        ids.add(key)
        transform = np.asarray(record["voxelToGltfM"])
        if not np.any(volume):
            skipped.append(record)
            LOGGER.debug("Skipped empty mask %s.", name)
            continue
        group, color, opacity, visible = classify_structure(key, groups)
        mesh, geometry = label_mesh(volume, 1, transform)
        mesh.visual = trimesh.visual.TextureVisuals(
            material=trimesh.visual.material.PBRMaterial(
                name=key,
                baseColorFactor=[int(color[i : i + 2], 16) for i in [1, 3, 5]] + [255],
                metallicFactor=0.0,
                roughnessFactor=0.65,
                doubleSided=True,
            )
        )
        scene.add_geometry(mesh, node_name=key, geom_name=key)
        side = anatomy_side(key)
        structures.append(
            {
                "id": key,
                "meshName": key,
                "name": display,
                "group": group,
                "side": side,
                "color": color,
                "explode": anatomy_explode(group, side),
                "source": dataset["structureSource"],
                "sourceShortName": name,
                "defaultVisible": visible,
                "defaultOpacity": opacity,
                "description": (
                    f"{dataset['labelKind'].capitalize()} of {display} from subject "
                    f"{subject} of the {dataset['dataset']}. Geometry follows the native voxel grid; "
                    f"segmentation accuracy is the dataset's own. {DISCLAIMER}"
                ),
                "geometry": geometry,
            }
        )
        records.append(record)
    if not structures:
        raise ValueError("Every structure mask is empty.")
    return structures, records, skipped


def convert(subject_dir: Path, output: Path, units: str | None = None) -> dict:
    """Convert one dataset subject directory (either layout) to GLB + manifest."""
    started = time.perf_counter()
    layout = subject_layout(subject_dir)
    dataset = dataset_attribution(subject_dir, layout)
    ct_path = subject_dir / ("ct.nii.gz" if layout == "masks" else "image.nii.gz")
    image = nib.load(ct_path)
    if len(image.shape) != 3:
        raise ValueError("Expected a 3-D image NIfTI.")
    if not int(image.header["sform_code"]) and not int(image.header["qform_code"]):
        raise ValueError(
            "The image must define an explicit sform or qform; fallback geometry is not accepted."
        )
    header_unit = image.header.get_xyzt_units()[0]
    unit, units_evidence = resolve_units(header_unit, units)
    transform = voxel_to_gltf_transform(image.affine, unit)
    scene = trimesh.Scene()
    masks = subject_dir / "segmentations" if layout == "masks" else label_map_masks(subject_dir, image, unit)
    structures, mask_records, skipped = mesh_structures(scene, masks, image, unit, subject_dir.name, dataset)
    payload = scene.export(file_type="glb", include_normals=True)
    validate_embedded_glb(payload, {entry["meshName"] for entry in structures})
    dependencies = {
        name: importlib.metadata.version(name)
        for name in ["numpy", "nibabel", "scikit-image", "trimesh"]
    }
    manifest = {
        "schemaVersion": manifest_schema_version(structures),
        "title": f"Splatomy · {dataset['modality']} anatomy, subject {subject_dir.name}",
        "source": f"{dataset['dataset']}; {dataset['datasetUrl']}",
        "license": f"{dataset['datasetLicense']}; {dataset['datasetLicenseUrl']}",
        "coordinateSystem": "glTF-Y-up",
        "units": "m",
        "provenance": (
            f"{dataset['labelKind'].capitalize()}s of one subject from the public {dataset['dataset']}, "
            f"converted at the native voxel grid without registration or resampling. "
            f"Coverage is the subject's scan field of view; an empty mask is not evidence "
            f"of absent anatomy. {DISCLAIMER}"
        ),
        "structures": structures,
        "metadata": {
            "dataset": dataset["dataset"],
            "datasetUrl": dataset["datasetUrl"],
            "datasetPaper": dataset["datasetPaper"],
            "datasetLicense": dataset["datasetLicense"],
            "datasetLicenseUrl": dataset["datasetLicenseUrl"],
            "datasetCitation": dataset.get("citation", ""),
            "modality": dataset["modality"],
            "labelKind": dataset["labelKind"],
            "subjectLayout": layout,
            "subject": subject_dir.name,
            "ctSha256": checksum(ct_path),
            "ctUnits": header_unit,
            "resolvedUnits": unit,
            "unitsEvidence": units_evidence,
            "ctShapeVoxels": list(image.shape),
            "ctAffine": image.affine.tolist(),
            "imageFile": ct_path.name,
            "ctAffineSpace": "NIfTI RAS+ in resolvedUnits",
            "ctAxisCodes": list(nib.aff2axcodes(image.affine)),
            "ctSpacing": nib.affines.voxel_sizes(image.affine).tolist(),
            "sformCode": int(image.header["sform_code"]),
            "qformCode": int(image.header["qform_code"]),
            "sourceUnitToMm": UNIT_TO_MM[unit],
            "rasMmToGltfM": RAS_MM_TO_GLTF_M.tolist(),
            "voxelToGltfM": transform.tolist(),
            "coordinateRule": "voxel -> full NIfTI affine -> RAS mm -> (x,z,-y)/1000 glTF meters; no centering baked into mesh",
            "masks": mask_records,
            "skippedEmptyMasks": skipped,
            "processing": {
                "method": "marching_cubes",
                "level": 0.5,
                "gradientDirection": "ascent",
                "crop": "per-structure voxel bounding box",
                "paddingVoxels": 1,
                "stepSize": 1,
                "smoothing": False,
                "decimation": False,
                "resampling": False,
            },
            "dependencies": dependencies,
            "python": platform.python_version(),
            "platform": platform.system(),
            "elapsedSeconds": round(time.perf_counter() - started, 3),
            "glbBytes": len(payload),
            "glbSha256": hashlib.sha256(payload).hexdigest(),
            "boundsGltfM": scene.bounds.tolist(),
            "clinicalUse": DISCLAIMER,
            "privacy": "No image intensities or free-text NIfTI header fields are exported into this manifest; geometry and affines only.",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".glb").write_bytes(payload)
    output.with_suffix(".json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--subject",
        type=Path,
        required=True,
        help="Subject directory: ct.nii.gz + segmentations/ (TotalSegmentator) or image.nii.gz + labels.nii.gz + labelmap.json + dataset.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output stem, e.g. private-assets/local-case (writes .glb and .json)",
    )
    parser.add_argument(
        "--units",
        choices=sorted(UNIT_TO_MM),
        help="Spatial unit of the subject's NIfTI files; overrides the header. Unset headers are read as mm and recorded as an assumption.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        manifest = convert(args.subject, args.output, args.units)
    except (OSError, ValueError, nib.filebasedimages.ImageFileError) as error:
        # Exception text from external libraries can contain local paths.
        LOGGER.error(
            "Conversion failed (%s). Check the subject layout, spatial units and destination permissions.",
            type(error).__name__,
        )
        raise SystemExit(1) from None
    LOGGER.info(
        "Converted %d structures; GLB %d bytes; %.3f seconds. %s",
        len(manifest["structures"]),
        manifest["metadata"]["glbBytes"],
        manifest["metadata"]["elapsedSeconds"],
        DISCLAIMER,
    )


if __name__ == "__main__":
    main()
