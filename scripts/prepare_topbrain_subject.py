"""Assemble one Splatomy subject directory from a TopBrain or TopCoW release.

The TopBrain 2025 release (Zenodo 21972006) holds 25 CTA/MRA pairs of the
TopCoW image data with whole-brain vessel label maps; the TopCoW release
(Zenodo 15692630) holds 250 images with Circle of Willis label maps. Both are
one multi-class NIfTI per image, so this script copies the image and its label
map into the label-map subject layout that convert_subject.py and
splat_context.py read: image.nii.gz, labels.nii.gz, labelmap.json (value ->
structure key and display name) and dataset.json (attribution and license).

Nothing is resampled or reoriented; the release's LPS+ images keep their own
affines. Data use: "Open use. Must provide the source. Use for commercial
purposes requires permission of the data owner." (University Hospital Zurich).
Run from the repository root:

    python scripts/prepare_topbrain_subject.py --release <unzipped TopBrain folder> \\
        --patient 001 --modality ct --output private-assets/subjects/topcow_ct_001
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import re
import shutil
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.convert_subject import DISCLAIMER, KEY_PATTERN

LOGGER = logging.getLogger(__name__)

TOPBRAIN = {
    "dataset": "TopBrain 2025 challenge data release (Yang et al.), TopCoW CTA/MRA images with whole-brain vessel annotations",
    "datasetUrl": "https://doi.org/10.5281/zenodo.21972006",
    "datasetPaper": "https://topbrain2025.grand-challenge.org",
    "datasetLicense": "Open use, attribution required (opendata.swiss terms): non-commercial use is free, commercial use requires permission of the data owner, University Hospital Zurich",
    "datasetLicenseUrl": "https://opendata.swiss/en/terms-of-use",
    "structureSource": "TopBrain labels",
    "labelKind": "expert voxel annotation",
    "catalog": "brain-vessels",
    "citation": (
        "Yang K, Shi P, Huang H, et al. TopBrain segmentation challenge for whole brain vessel anatomy. medRxiv 2026. "
        "Yang K, Musio F, Ma Y, et al. The TopCoW Challenge: Topology-Aware Circle of Willis Segmentation for CT and MR Angiography. NEJM AI 2026;3(8)."
    ),
}
TOPCOW = {
    "dataset": "TopCoW challenge training data release (Yang et al.), CTA/MRA with Circle of Willis annotations",
    "datasetUrl": "https://doi.org/10.5281/zenodo.15692630",
    "datasetPaper": "https://doi.org/10.48550/arXiv.2312.17670",
    "datasetLicense": TOPBRAIN["datasetLicense"],
    "datasetLicenseUrl": TOPBRAIN["datasetLicenseUrl"],
    "structureSource": "TopCoW labels",
    "labelKind": "expert voxel annotation",
    "catalog": "brain-vessels",
    "citation": "Yang K, Musio F, Ma Y, et al. The TopCoW Challenge: Topology-Aware Circle of Willis Segmentation for CT and MR Angiography. NEJM AI 2026;3(8).",
}
# TopCoW's 13 Circle of Willis classes (TopBrain keeps the same values 1-12 and 15).
TOPCOW_LABELS = {
    "BA": 1, "R-PCA": 2, "L-PCA": 3, "R-ICA": 4, "R-MCA": 5, "L-ICA": 6, "L-MCA": 7,
    "R-Pcom": 8, "L-Pcom": 9, "Acom": 10, "R-ACA": 11, "L-ACA": 12, "3rd-A2": 15,
}
# Display names for every label of the TopBrain v1 (CT 40, MR 42) and v2 (36) maps
# and the TopCoW map. Side prefixes are expanded by side_name().
NAMES = {
    "BA": "Basilar artery",
    "PCA": "Posterior cerebral artery",
    "P1P2": "Posterior cerebral artery, P1–P2",
    "P3P4": "Posterior cerebral artery, P3–P4",
    "ICA": "Internal carotid artery",
    "ICA-C6-C7": "Internal carotid artery, C6–C7 (supraclinoid)",
    "ICA-C1-C5": "Internal carotid artery, C1–C5 (infraclinoid)",
    "MCA": "Middle cerebral artery",
    "M1": "Middle cerebral artery, M1",
    "M2": "Middle cerebral artery, M2",
    "M3": "Middle cerebral artery, M3",
    "Pcom": "Posterior communicating artery",
    "Acom": "Anterior communicating artery",
    "ACA": "Anterior cerebral artery",
    "A1A2": "Anterior cerebral artery, A1–A2",
    "A3": "Anterior cerebral artery, A3",
    "3rd-A2": "Third A2 segment (median callosal artery)",
    "3rd-A3": "Third A3 segment",
    "VA": "Vertebral artery",
    "SCA": "Superior cerebellar artery",
    "AICA": "Anterior inferior cerebellar artery",
    "PICA": "Posterior inferior cerebellar artery",
    "AChA": "Anterior choroidal artery",
    "OA": "Ophthalmic artery",
    "VoG": "Vein of Galen",
    "StS": "Straight sinus",
    "ICVs": "Internal cerebral veins",
    "BVR": "Basal vein of Rosenthal",
    "SSS": "Superior sagittal sinus",
    "ECA": "External carotid artery",
    "STA": "Superficial temporal artery",
    "MaxA": "Maxillary artery",
    "MMA": "Middle meningeal artery",
}


def split_side(label: str) -> tuple[str, str]:
    """('R', 'ICA-C6-C7') for 'R-ICA-C6-C7'; ('', 'BA') for an unsided label."""
    match = re.fullmatch(r"([LR])-(.+)", label)
    return (match.group(1), match.group(2)) if match else ("", label)


def structure_key(label: str) -> str:
    """Label name -> manifest key: lower case, '-' to '_', a leading '3rd' spelled out."""
    key = label.lower().replace("-", "_")
    key = re.sub(r"^3rd_", "third_", key)
    if not re.fullmatch(KEY_PATTERN, key):
        raise ValueError(f"Label {label!r} does not form a structure key.")
    return key


def display_name(label: str) -> str:
    side, base = split_side(label)
    if base not in NAMES:
        raise ValueError(f"No display name for label {label!r}; add it to NAMES.")
    return f"{ {'L': 'Left', 'R': 'Right'}[side] } {NAMES[base][0].lower()}{NAMES[base][1:]}" if side else NAMES[base]


def label_map_entries(labels: dict[str, int]) -> dict[str, dict]:
    """labelmap.json content from a release label map (name -> value), background dropped."""
    entries = {}
    for label, value in labels.items():
        if label == "background" or value == 0:
            continue
        if not isinstance(value, int) or value < 1 or str(value) in entries:
            raise ValueError(f"Label {label!r} has an invalid or duplicate value {value!r}.")
        entries[str(value)] = {"key": structure_key(label), "name": display_name(label), "label": label}
    if len({entry["key"] for entry in entries.values()}) != len(entries):
        raise ValueError("Two labels map to the same structure key.")
    return dict(sorted(entries.items(), key=lambda item: int(item[0])))


def locate(release: Path, kind: str, modality: str, patient: str, labels: str) -> tuple[Path, Path, dict]:
    """Image path, label path and the release label map for one case."""
    if not re.fullmatch(r"[0-9]{3}", patient) or modality not in {"ct", "mr"}:
        raise ValueError("--patient is a three-digit ID and --modality is ct or mr.")
    stem = f"topcow_{modality}_{patient}"
    if kind == "topbrain":
        image = release / "imagesTr_topbrain" / f"{stem}_0000.nii.gz"
        if labels == "v2":
            label_path = release / "labelsTr_topbrain_v2_topaneu36class" / f"{stem}.nii.gz"
            map_path = release / "labelmap_jsons" / "labels_topbrain_v2_topaneu36class.json"
        else:
            label_path = release / f"labelsTr_topbrain_v1_{modality}" / f"{stem}.nii.gz"
            map_path = release / "labelmap_jsons" / f"labels_topbrain_v1_{modality}.json"
        label_map = json.loads(map_path.read_text(encoding="utf-8"))["labels"]
    else:
        image = release / "imagesTr" / f"{stem}_0000.nii.gz"
        label_path = release / "cow_seg_labelsTr" / f"{stem}.nii.gz"
        label_map = dict(TOPCOW_LABELS)
    for path in (image, label_path):
        if not path.is_file():
            raise ValueError(f"Release is missing {path.name}.")
    return image, label_path, label_map


def prepare(release: Path, kind: str, modality: str, patient: str, labels: str, output: Path) -> dict:
    image, label_path, label_map = locate(release, kind, modality, patient, labels)
    entries = label_map_entries(label_map)
    attribution = dict(TOPBRAIN if kind == "topbrain" else TOPCOW)
    attribution["modality"] = {"ct": "CTA", "mr": "MRA"}[modality]
    attribution["labelSet"] = f"TopBrain {labels}" if kind == "topbrain" else "TopCoW CoW 13 classes"
    attribution["releaseCase"] = image.name
    attribution["clinicalUse"] = DISCLAIMER
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(image, output / "image.nii.gz")
    shutil.copyfile(label_path, output / "labels.nii.gz")
    (output / "labelmap.json").write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "dataset.json").write_text(json.dumps(attribution, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return attribution


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--release", type=Path, required=True, help="Unzipped release folder (the one holding imagesTr_topbrain/ or imagesTr/)")
    parser.add_argument("--kind", choices=["topbrain", "topcow"], default="topbrain")
    parser.add_argument("--patient", required=True, help="Three-digit patient ID, e.g. 001")
    parser.add_argument("--modality", choices=["ct", "mr"], required=True)
    parser.add_argument("--labels", choices=["v1", "v2"], default="v2", help="TopBrain label set: v2 unified 36 classes (default) or v1 per-modality 40/42 classes")
    parser.add_argument("--output", type=Path, required=True, help="Subject directory to create, e.g. private-assets/subjects/topcow_ct_001")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        attribution = prepare(args.release, args.kind, args.modality, args.patient, args.labels, args.output)
    except (OSError, ValueError, KeyError) as error:
        LOGGER.error("Preparation failed (%s). Check the release folder, patient ID and modality.", type(error).__name__)
        raise SystemExit(1) from None
    LOGGER.info("Prepared %s (%s, %s). %s", args.output.name, attribution["modality"], attribution["labelSet"], DISCLAIMER)


if __name__ == "__main__":
    main()
