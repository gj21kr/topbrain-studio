"""prepare_topbrain_subject.py: a release case becomes a label-map subject the converter and context builder read."""

import json
from pathlib import Path
import tempfile
import unittest

import nibabel as nib
import numpy as np

from scripts.convert_subject import convert
from scripts.prepare_topbrain_subject import NAMES, TOPCOW_LABELS, display_name, label_map_entries, prepare, structure_key
from scripts.splat_context import build_context


class NamingTests(unittest.TestCase):
    def test_release_labels_become_keys_and_names(self):
        self.assertEqual(structure_key("R-ICA-C6-C7"), "r_ica_c6_c7")
        self.assertEqual(structure_key("3rd-A2"), "third_a2")
        self.assertEqual(display_name("R-ICA-C6-C7"), "Right internal carotid artery, C6–C7 (supraclinoid)")
        self.assertEqual(display_name("L-Pcom"), "Left posterior communicating artery")
        self.assertEqual(display_name("BA"), "Basilar artery")
        self.assertEqual(display_name("3rd-A2"), "Third A2 segment (median callosal artery)")
        with self.assertRaisesRegex(ValueError, "No display name"):
            display_name("R-XYZ")

    def test_label_map_entries_drop_background_and_refuse_collisions(self):
        entries = label_map_entries({"background": 0, "BA": 1, "R-ICA": 4})
        self.assertEqual(entries, {"1": {"key": "ba", "name": "Basilar artery", "label": "BA"}, "4": {"key": "r_ica", "name": "Right internal carotid artery", "label": "R-ICA"}})
        with self.assertRaisesRegex(ValueError, "invalid or duplicate"):
            label_map_entries({"BA": 1, "Acom": 1})
        self.assertEqual(len(label_map_entries(TOPCOW_LABELS)), 13)
        self.assertTrue(all(base in NAMES for base in ("PCA", "MCA", "ACA")))


class ReleaseLayoutTests(unittest.TestCase):
    """A synthetic TopBrain release folder, then the full pipeline on the prepared subject."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.release = self.root / "TopBrain_Release"
        for folder in ("imagesTr_topbrain", "labelsTr_topbrain_v2_topaneu36class", "labelsTr_topbrain_v1_ct", "labelmap_jsons"):
            (self.release / folder).mkdir(parents=True)
        self.affine = np.diag([0.5, 0.5, 0.6, 1.0]); self.affine[:3, 3] = [70, 55, -80]
        labels = np.zeros((16, 16, 16), dtype=np.uint8)
        labels[2:5, 2:5, 2:8] = 4     # R-ICA-C6-C7
        labels[10:13, 2:5, 2:8] = 6   # L-ICA-C6-C7
        labels[7:9, 7:9, 3:12] = 1    # BA
        image = np.random.default_rng(1).integers(-100, 150, labels.shape, dtype=np.int16)
        image[labels > 0] = 250     # contrast-filled vessels
        image[0:2, :, :] = 1200       # a slab of bone
        for volume, path in ((image, "imagesTr_topbrain/topcow_ct_004_0000.nii.gz"), (labels, "labelsTr_topbrain_v2_topaneu36class/topcow_ct_004.nii.gz")):
            nifti = nib.Nifti1Image(volume, self.affine); nifti.header.set_xyzt_units("mm")
            nib.save(nifti, self.release / path)
        (self.release / "labelmap_jsons" / "labels_topbrain_v2_topaneu36class.json").write_text(
            json.dumps({"labels": {"background": 0, "BA": 1, "R-ICA-C6-C7": 4, "L-ICA-C6-C7": 6, "Acom": 10}}), encoding="utf-8")

    def test_prepare_then_convert_and_context(self):
        subject = self.root / "subjects" / "topcow_ct_004"
        attribution = prepare(self.release, "topbrain", "ct", "004", "v2", subject)
        self.assertEqual(attribution["modality"], "CTA")
        self.assertEqual(sorted(p.name for p in subject.iterdir()), ["dataset.json", "image.nii.gz", "labelmap.json", "labels.nii.gz"])
        dataset = json.loads((subject / "dataset.json").read_text(encoding="utf-8"))
        self.assertIn("zenodo.21972006", dataset["datasetUrl"])
        self.assertIn("commercial use requires permission", dataset["datasetLicense"])
        self.assertEqual(dataset["catalog"], "brain-vessels")
        manifest = convert(subject, self.root / "out" / "case")
        ids = [s["id"] for s in manifest["structures"]]
        self.assertEqual(ids, ["ba", "r_ica_c6_c7", "l_ica_c6_c7"])
        self.assertEqual(manifest["structures"][1]["name"], "Right internal carotid artery, C6–C7 (supraclinoid)")
        self.assertEqual({s["source"] for s in manifest["structures"]}, {"TopBrain labels"})
        self.assertEqual([r["structureKey"] for r in manifest["metadata"]["skippedEmptyMasks"]], ["acom"])
        self.assertIn("TopBrain 2025", manifest["source"])
        self.assertEqual(manifest["metadata"]["modality"], "CTA")
        context = build_context(subject, self.root / "out" / "case")
        self.assertEqual(context["modality"], "CTA")
        self.assertEqual(context["ctSha256"], manifest["metadata"]["ctSha256"])
        np.testing.assert_allclose(context["voxelToGltfM"], manifest["metadata"]["voxelToGltfM"])
        bands = {b["band"]: b["splats"] for b in context["transferFunction"]}
        self.assertEqual((bands["bone"], bands["contrast"]), (2 * 16 * 16, 3 * 3 * 6 * 2 + 2 * 2 * 9))

    def test_missing_case_and_bad_ids_are_refused(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            prepare(self.release, "topbrain", "mr", "004", "v2", self.root / "x")
        with self.assertRaisesRegex(ValueError, "three-digit"):
            prepare(self.release, "topbrain", "ct", "4", "v2", self.root / "x")
        with self.assertRaisesRegex(ValueError, "missing"):
            prepare(self.release, "topcow", "ct", "004", "v2", self.root / "x")
