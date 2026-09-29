"""Turn a subject's image intensities into a Gaussian-splat context layer.

Meshes show where each segmented structure ends; they cannot show the bone and
soft tissue those structures sit in. This writes the image itself as one
Gaussian per selected voxel, initialised directly from the volume with no
fitting, in the same glTF frame as the GLB so the two layers coincide. For CT
and CTA the appearance is a transfer function of Hounsfield units; for MRA,
whose intensities carry no unit, it is a transfer function of the volume's own
intensity percentiles. Neither is a photograph.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
from pathlib import Path
import sys
import time

import nibabel as nib
import numpy as np

if __package__ in (None, ""):  # run as `python scripts/splat_context.py`, like convert_subject.py in the docs
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.convert_subject import (
    DISCLAIMER,
    UNIT_TO_MM,
    checksum,
    dataset_attribution,
    resolve_units,
    subject_layout,
    voxel_to_gltf_transform,
)

LOGGER = logging.getLogger(__name__)
# The browser half of this limit lives in src/model.ts (inspectSplatPly). Both
# halves must move together or the writer produces files the viewer refuses.
MAX_SPLATS = 2_000_000
SH_C0 = 0.28209479177387814
# The 3D Gaussian Splatting PLY layout every splat renderer reads: position,
# zeroth-order spherical-harmonic color, logit opacity, log scale, quaternion.
PLY_PROPERTIES = (
    "x", "y", "z",
    "f_dc_0", "f_dc_1", "f_dc_2",
    "opacity",
    "scale_0", "scale_1", "scale_2",
    "rot_0", "rot_1", "rot_2", "rot_3",
)
# Transfer function over Hounsfield units: (band, hu_min, hu_max, stride, alpha,
# rgb). A band's stride keeps every stride-th voxel per axis and widens the
# Gaussian to match, so dense soft tissue stays affordable while bone and
# contrast-filled vessels keep full resolution.
TRANSFER = (
    ("bone", 300, 4000, 1, 0.85, (0.93, 0.90, 0.82)),
    ("contrast", 150, 300, 1, 0.45, (0.85, 0.55, 0.45)),
    ("soft tissue", -200, 150, 3, 0.06, (0.55, 0.50, 0.50)),
)
# MRA (time-of-flight) has no unit: flowing blood is the brightest tissue, so
# the bands are intensity percentiles of the volume, resolved per subject and
# recorded. The top percentile keeps full resolution; parenchyma is strided.
TRANSFER_MRA = (
    ("vessel", 99.0, 100.0, 1, 0.85, (0.90, 0.45, 0.40)),
    ("tissue", 55.0, 99.0, 3, 0.05, (0.62, 0.60, 0.62)),
)
TRANSFERS = {"CT": ("hu", TRANSFER), "CTA": ("hu", TRANSFER), "MRA": ("percentile", TRANSFER_MRA)}


def gaussian_frame(transform: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-axis voxel size in metres and the voxel-frame rotation as a quaternion.

    A voxel becomes an axis-aligned Gaussian in the voxel frame, so the affine's
    linear part must be a rotation times per-axis scales. A reflection is fine
    (a Gaussian is symmetric under flipping an axis); shear is not, because it
    cannot be expressed as one rotation plus three scales.
    """
    linear = np.asarray(transform, dtype=np.float64)[:3, :3]
    spacing = np.linalg.norm(linear, axis=0)
    if not np.all(spacing > 0):
        raise ValueError("Voxel axes must have non-zero length.")
    rotation = linear / spacing
    if np.linalg.det(rotation) < 0:
        rotation = rotation.copy()
        rotation[:, 0] *= -1
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6):
        raise ValueError("Splat context requires a shear-free affine.")
    # Shepperd's method: rotation matrix to unit quaternion (w, x, y, z).
    trace = np.trace(rotation)
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        quaternion = np.array([0.25 * s, (rotation[2, 1] - rotation[1, 2]) / s, (rotation[0, 2] - rotation[2, 0]) / s, (rotation[1, 0] - rotation[0, 1]) / s])
    else:
        i = int(np.argmax(np.diag(rotation)))
        j, k = (i + 1) % 3, (i + 2) % 3
        s = math.sqrt(1.0 + rotation[i, i] - rotation[j, j] - rotation[k, k]) * 2
        quaternion = np.empty(4)
        quaternion[0] = (rotation[k, j] - rotation[j, k]) / s
        quaternion[1 + i] = 0.25 * s
        quaternion[1 + j] = (rotation[j, i] + rotation[i, j]) / s
        quaternion[1 + k] = (rotation[k, i] + rotation[i, k]) / s
    return spacing, quaternion / np.linalg.norm(quaternion)


def resolve_transfer(volume: np.ndarray, modality: str = "CT") -> tuple[str, list[dict]]:
    """The transfer function for a modality with every band's bounds resolved to intensities.

    Strides start at the table's values. When the selection would exceed the
    viewer's splat limit, the band holding the most splats is strided one step
    further, repeatedly, and both the requested and the resolved stride are
    recorded: a 0.5 mm braincase CTA has more bone voxels than a 1.5 mm whole
    body, and the layer must stay honest about what it dropped.
    """
    if modality not in TRANSFERS:
        raise ValueError("Modality must be CT, CTA or MRA.")
    kind, table = TRANSFERS[modality]
    bands = []
    for band, low, high, stride, alpha, rgb in table:
        entry = {"band": band, "strideRequested": stride, "stride": stride, "alpha": alpha, "rgb": list(rgb), "kind": kind}
        if kind == "hu":
            entry |= {"huMin": low, "huMax": high, "low": low, "high": high}
        else:
            lo, hi = np.percentile(volume, [low, high]).tolist()
            entry |= {"percentileMin": low, "percentileMax": high, "low": lo, "high": hi}
        # The top band is closed at the maximum so the brightest voxel is kept.
        entry["mask"] = (volume >= entry["low"]) & ((volume <= entry["high"]) if entry["high"] >= volume.max() else (volume < entry["high"]))
        bands.append(entry)
    def count(entry):
        step = entry["stride"]
        return int(entry["mask"][::step, ::step, ::step].sum())
    counts = [count(entry) for entry in bands]
    while sum(counts) > MAX_SPLATS:
        largest = max(range(len(bands)), key=lambda i: counts[i])
        if bands[largest]["stride"] >= 8:
            raise ValueError("The transfer function cannot fit the splat limit even at stride 8.")
        bands[largest]["stride"] += 1
        counts[largest] = count(bands[largest])
    for entry, n in zip(bands, counts):
        entry["selected"] = n
    return kind, bands


def strided(shape, stride: int) -> np.ndarray:
    """A keep-mask holding every stride-th voxel per axis."""
    keep = np.zeros(shape, dtype=bool)
    keep[::stride, ::stride, ::stride] = True
    return keep


def select_voxels(volume: np.ndarray, modality: str = "CT") -> list[tuple[str, np.ndarray, int, float, tuple[float, float, float]]]:
    """Voxel indices per transfer-function band, already strided."""
    bands = []
    _, resolved = resolve_transfer(volume, modality)
    for entry in resolved:
        mask, stride = entry["mask"], entry["stride"]
        if stride > 1:
            mask = mask & strided(mask.shape, stride)
        bands.append((entry["band"], np.argwhere(mask), stride, entry["alpha"], tuple(entry["rgb"])))
    return bands


def write_splat_ply(path: Path, transform: np.ndarray, bands) -> tuple[int, dict, dict]:
    """Write a 3DGS PLY; return the splat count, per-band counts and a witness."""
    spacing, quaternion = gaussian_frame(transform)
    counts = {band: int(len(indices)) for band, indices, *_ in bands}
    total = sum(counts.values())
    if total == 0:
        raise ValueError("The transfer function selected no voxels.")
    if total > MAX_SPLATS:
        raise ValueError(
            f"{total} splats exceed the viewer's {MAX_SPLATS} limit; raise the soft-tissue stride."
        )
    records = np.empty(total, dtype=[(name, "<f4") for name in PLY_PROPERTIES])
    offset, witness = 0, None
    for band, indices, stride, alpha, rgb in bands:
        n = len(indices)
        if not n:
            continue
        homogeneous = np.c_[indices, np.ones(n)]
        positions = (transform @ homogeneous.T).T[:, :3]
        block = records[offset : offset + n]
        block["x"], block["y"], block["z"] = positions.T
        for channel, value in zip(("f_dc_0", "f_dc_1", "f_dc_2"), rgb):
            block[channel] = (value - 0.5) / SH_C0
        block["opacity"] = math.log(alpha / (1 - alpha))
        for axis, name in enumerate(("scale_0", "scale_1", "scale_2")):
            block[name] = math.log(spacing[axis] * stride / 2)
        for component, name in enumerate(("rot_0", "rot_1", "rot_2", "rot_3")):
            block[name] = quaternion[component]
        if witness is None:
            witness = {"voxel": indices[0].tolist(), "gltfM": positions[0].tolist(), "band": band}
        offset += n
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {total}\n"
        + "".join(f"property float {name}\n" for name in PLY_PROPERTIES)
        + "end_header\n"
    ).encode("ascii")
    path.write_bytes(header + records.tobytes())
    return total, counts, witness


def validate_splat_ply(payload: bytes) -> int:
    """Check the 3DGS PLY subset the viewer accepts; mirrors inspectSplatPly in src/model.ts."""
    end = payload.find(b"end_header\n")
    if not payload.startswith(b"ply\n") or end < 0 or end > 4096:
        raise ValueError("Invalid splat PLY header.")
    lines = payload[: end].decode("ascii", errors="replace").split("\n")
    if lines[1] != "format binary_little_endian 1.0":
        raise ValueError("Splat PLY must be binary little-endian.")
    element = [line for line in lines if line.startswith("element ")]
    if len(element) != 1 or not element[0].startswith("element vertex "):
        raise ValueError("Splat PLY must hold exactly one vertex element.")
    count = int(element[0].split()[2])
    if not 1 <= count <= MAX_SPLATS:
        raise ValueError(f"Splat PLY must hold 1-{MAX_SPLATS} splats.")
    properties = tuple(line.split()[2] for line in lines if line.startswith("property "))
    if properties != PLY_PROPERTIES or any(not line.startswith("property float ") for line in lines if line.startswith("property ")):
        raise ValueError("Splat PLY properties differ from the 3DGS layout.")
    body = payload[end + len(b"end_header\n") :]
    if len(body) != count * len(PLY_PROPERTIES) * 4:
        raise ValueError("Splat PLY body length does not match its header.")
    positions = np.frombuffer(body, dtype="<f4").reshape(count, len(PLY_PROPERTIES))[:, :3]
    if not np.isfinite(positions).all():
        raise ValueError("Splat PLY contains non-finite positions.")
    return count


def build_context(subject_dir: Path, output: Path, units: str | None = None) -> dict:
    """Write <output>.context.ply and .context.json for one subject (either layout)."""
    started = time.perf_counter()
    layout = subject_layout(subject_dir)
    dataset = dataset_attribution(subject_dir, layout)
    modality = dataset["modality"]
    ct_path = subject_dir / ("ct.nii.gz" if layout == "masks" else "image.nii.gz")
    image = nib.load(ct_path)
    if len(image.shape) != 3:
        raise ValueError("Expected a 3-D image NIfTI.")
    if not int(image.header["sform_code"]) and not int(image.header["qform_code"]):
        raise ValueError("The image must define an explicit sform or qform.")
    header_unit = image.header.get_xyzt_units()[0]
    unit, units_evidence = resolve_units(header_unit, units)
    transform = voxel_to_gltf_transform(image.affine, unit)
    volume = np.asanyarray(image.dataobj)
    if not np.issubdtype(volume.dtype, np.number) or not np.isfinite(volume).all():
        raise ValueError("Image intensities must be finite numbers.")
    kind, resolved = resolve_transfer(volume, modality)
    bands = [(e["band"], np.argwhere(e["mask"] if e["stride"] == 1 else e["mask"] & strided(e["mask"].shape, e["stride"])), e["stride"], e["alpha"], tuple(e["rgb"])) for e in resolved]
    ply_path = output.with_suffix(".context.ply")
    output.parent.mkdir(parents=True, exist_ok=True)
    total, counts, witness = write_splat_ply(ply_path, transform, bands)
    payload = ply_path.read_bytes()
    validate_splat_ply(payload)
    spacing, quaternion = gaussian_frame(transform)
    context = {
        "contextVersion": 1,
        "kind": "gaussian-splat-context",
        "source": f"{dataset['dataset']}; {dataset['datasetUrl']}",
        "license": f"{dataset['datasetLicense']}; {dataset['datasetLicenseUrl']}",
        "coordinateSystem": "glTF-Y-up",
        "units": "m",
        "provenance": (
            f"{modality} intensities of one subject rendered as one Gaussian per selected voxel, "
            "initialised from the volume without fitting. Color and opacity are a transfer "
            + ("function of Hounsfield units" if kind == "hu" else "function of the volume's intensity percentiles")
            + f", not a photograph. {DISCLAIMER}"
        ),
        "subject": subject_dir.name,
        "modality": modality,
        "imageFile": ct_path.name,
        "ctSha256": checksum(ct_path),
        "ctUnits": header_unit,
        "resolvedUnits": unit,
        "unitsEvidence": units_evidence,
        "sourceUnitToMm": UNIT_TO_MM[unit],
        "voxelToGltfM": transform.tolist(),
        "coordinateRule": "voxel -> full NIfTI affine -> RAS mm -> (x,z,-y)/1000 glTF meters; identical to the GLB manifest so both layers coincide",
        "gaussianFrame": {"voxelSizeM": spacing.tolist(), "rotationWxyz": quaternion.tolist(), "sigma": "half a (strided) voxel per axis"},
        "transferFunction": [{k: v for k, v in entry.items() if k not in {"mask", "selected"}} | {"splats": counts[entry["band"]]} for entry in resolved],
        "splats": total,
        "witness": witness,
        "plyBytes": len(payload),
        "plySha256": hashlib.sha256(payload).hexdigest(),
        "elapsedSeconds": round(time.perf_counter() - started, 3),
        "clinicalUse": DISCLAIMER,
    }
    output.with_suffix(".context.json").write_text(json.dumps(context, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return context


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", type=Path, required=True, help="Subject directory in either layout (ct.nii.gz, or image.nii.gz + dataset.json)")
    parser.add_argument("--output", type=Path, required=True, help="Output stem shared with convert_subject.py, e.g. private-assets/local-case")
    parser.add_argument("--units", choices=sorted(UNIT_TO_MM), help="Spatial unit override; unset headers are read as mm and recorded")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        context = build_context(args.subject, args.output, args.units)
    except (OSError, ValueError, nib.filebasedimages.ImageFileError) as error:
        LOGGER.error("Context layer failed (%s). Check the subject layout, spatial units and destination permissions.", type(error).__name__)
        raise SystemExit(1) from None
    LOGGER.info(
        "Wrote %d splats (%s); PLY %.1f MB; %.1f s. %s",
        context["splats"],
        ", ".join(f"{b['band']} {b['splats']:,}" for b in context["transferFunction"]),
        context["plyBytes"] / 1048576,
        context["elapsedSeconds"],
        DISCLAIMER,
    )


if __name__ == "__main__":
    main()
