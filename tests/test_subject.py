"""End-to-end conversion of a synthetic subject laid out like the dataset."""

import json
from pathlib import Path
import tempfile
import unittest

import nibabel as nib
import numpy as np
import trimesh

from scripts.convert_subject import convert, mesh_structures


class SubjectTests(unittest.TestCase):
    """A subject is ct.nii.gz plus segmentations/<structure>.nii.gz on one grid."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.subject = self.root / "s0042"
        self.masks = self.subject / "segmentations"
        self.masks.mkdir(parents=True)
        self.affine = np.array(
            [[0, -2, 0.3, 10], [3, 0.2, 0, -20], [0, 0, 4, 30], [0, 0, 0, 1.0]]
        )
        self.volume = np.zeros((6, 7, 8), dtype=np.uint8)
        self.volume[1:4, 2:5, 3:6] = 1
        intensities = np.random.default_rng(42).integers(-1000, 1500, self.volume.shape, dtype=np.int16)
        self.ct = self.image(intensities)
        nib.save(self.ct, self.subject / "ct.nii.gz")

    def image(self, volume, affine=None, unit="mm"):
        image = nib.Nifti1Image(volume, self.affine if affine is None else affine)
        image.header.set_xyzt_units(unit)
        image.header["descrip"] = b"PRIVATE_DO_NOT_EXPORT"
        return image

    def write(self, name, volume=None, affine=None, unit="mm"):
        nib.save(
            self.image(self.volume if volume is None else volume, affine, unit),
            self.masks / name,
        )

    def mesh(self):
        scene = trimesh.Scene()
        return scene, *mesh_structures(scene, self.masks, self.ct, "mm", self.subject.name)

    def test_subject_converts_every_nonempty_mask_with_world_coordinates(self):
        self.write("liver.nii.gz")
        self.write("aorta.nii.gz")
        self.write("kidney_left.nii.gz")
        self.write("vertebrae_C3.nii.gz", np.zeros_like(self.volume))
        out = self.root / "model"
        result = convert(self.subject, out)
        self.assertEqual(result["schemaVersion"], 2)
        self.assertEqual([entry["id"] for entry in result["structures"]], ["aorta", "kidney_left", "liver"])
        self.assertEqual({entry["source"] for entry in result["structures"]}, {"TotalSegmentator dataset"})
        self.assertEqual([record["structureKey"] for record in result["metadata"]["skippedEmptyMasks"]], ["vertebrae_C3"])
        scene = trimesh.load(out.with_suffix(".glb"), force="scene", process=False)
        self.assertEqual(set(scene.geometry), {"aorta", "kidney_left", "liver"})
        for entry in result["structures"]:
            np.testing.assert_allclose(scene.geometry[entry["meshName"]].bounds, scene.geometry["liver"].bounds)
            witness = entry["geometry"]["affineWitness"]
            ras = self.affine @ np.r_[witness["voxel"], 1]
            np.testing.assert_allclose(witness["gltfM"], ras[[0, 2, 1]] * [0.001, 0.001, -0.001])
        # Header free text and intensities never reach the manifest.
        text = json.dumps(result)
        self.assertNotIn("PRIVATE_DO_NOT_EXPORT", text)
        self.assertNotIn("intensit", json.dumps(result["structures"]))
        self.assertEqual(result["metadata"]["subject"], "s0042")
        self.assertIn("CC BY 4.0", result["license"])
        self.assertIn("zenodo", result["source"])
        self.assertTrue(out.with_suffix(".json").exists())
        loaded = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual(loaded["metadata"]["glbBytes"], out.with_suffix(".glb").stat().st_size)

    def test_structures_receive_group_directed_display_and_explode(self):
        for name in ["brain", "skull", "spinal_cord", "vertebrae_C3", "clavicula_left", "common_carotid_artery_right", "trachea", "liver", "rib_right_4"]:
            self.write(f"{name}.nii.gz")
        _, structures, records, skipped = self.mesh()
        self.assertEqual(skipped, [])
        self.assertEqual(len(records), 9)
        by_name = {entry["sourceShortName"]: entry for entry in structures}
        self.assertEqual(by_name["brain"]["explode"], [0, 0.04, 0])
        self.assertEqual(by_name["skull"]["explode"], [0, 0.06, 0])
        self.assertEqual(by_name["spinal_cord"]["explode"], [0, -0.02, 0])
        self.assertEqual(by_name["vertebrae_C3"]["explode"], [0, -0.04, 0])
        self.assertEqual(by_name["clavicula_left"]["explode"], [-0.04, -0.04, 0])
        self.assertEqual(by_name["common_carotid_artery_right"]["explode"], [0.04, 0.02, 0])
        self.assertEqual(by_name["trachea"]["explode"], [0, 0.02, 0])
        self.assertEqual(by_name["liver"]["explode"], [0, -0.02, -0.04])
        self.assertEqual(by_name["rib_right_4"]["side"], "Right")
        self.assertEqual(by_name["rib_right_4"]["group"], "Ribs")
        # Skeleton and circulation open visible; soft tissue starts hidden.
        self.assertTrue(by_name["skull"]["defaultVisible"] and by_name["common_carotid_artery_right"]["defaultVisible"])
        self.assertFalse(by_name["brain"]["defaultVisible"] or by_name["liver"]["defaultVisible"])
        self.assertEqual(by_name["skull"]["defaultOpacity"], 0.2)
        self.assertEqual(by_name["common_carotid_artery_right"]["defaultOpacity"], 1.0)
        for entry in structures:
            self.assertGreater(np.linalg.norm(entry["explode"]), 0)
            self.assertEqual(entry["id"], entry["meshName"])
            self.assertEqual(entry["id"], entry["sourceShortName"].lower())

    def test_unset_units_are_read_as_mm_and_recorded_as_an_assumption(self):
        """The dataset's NIfTI files carry no xyzt_units; that must convert, honestly."""
        self.write("liver.nii.gz", unit="unknown")
        ct = nib.load(self.subject / "ct.nii.gz")
        ct.header.set_xyzt_units("unknown")
        nib.save(ct, self.subject / "ct.nii.gz")
        result = convert(self.subject, self.root / "model")
        self.assertEqual(result["metadata"]["ctUnits"], "unknown")
        self.assertEqual(result["metadata"]["resolvedUnits"], "mm")
        self.assertIn("assumed", result["metadata"]["unitsEvidence"]["method"])
        self.assertEqual(result["metadata"]["sourceUnitToMm"], 1.0)
        witness = result["structures"][0]["geometry"]["affineWitness"]
        ras = self.affine @ np.r_[witness["voxel"], 1]
        np.testing.assert_allclose(witness["gltfM"], ras[[0, 2, 1]] * [0.001, 0.001, -0.001])
        # An explicit override wins and is recorded as such.
        micron = convert(self.subject, self.root / "model", units="micron")
        self.assertEqual(micron["metadata"]["resolvedUnits"], "micron")
        self.assertEqual(micron["metadata"]["unitsEvidence"]["method"], "command-line override")
        self.assertEqual(micron["metadata"]["sourceUnitToMm"], 0.001)
        with self.assertRaisesRegex(ValueError, "--units"):
            convert(self.subject, self.root / "model", units="inch")

    def test_a_mask_that_declares_a_conflicting_unit_is_still_rejected(self):
        """Inheritance covers unset units only; a declared unit is held to the grid."""
        self.write("liver.nii.gz", unit="meter")
        with self.assertRaisesRegex(ValueError, "physical voxel grid"):
            self.mesh()

    def test_unit_equivalence(self):
        affine_m = self.affine.copy()
        affine_m[:3] /= 1000
        self.write("liver.nii.gz", affine=affine_m, unit="meter")
        self.assertEqual(len(self.mesh()[1]), 1)

    def test_rejects_mismatched_grid_including_empty_masks(self):
        for empty in [False, True]:
            with self.subTest(empty=empty):
                affine = self.affine.copy()
                affine[0, 3] += 1
                self.write("liver.nii.gz", np.zeros_like(self.volume) if empty else self.volume, affine)
                with self.assertRaisesRegex(ValueError, "physical voxel grid"):
                    self.mesh()
        self.write("liver.nii.gz", np.zeros((3, 3, 3), dtype=np.uint8))
        with self.assertRaisesRegex(ValueError, "identical voxel grid"):
            self.mesh()

    def test_rejects_nonbinary_unknown_units_and_missing_spatial_form(self):
        for value in [2, -1, 0.5, np.nan, np.inf]:
            with self.subTest(value=value):
                volume = self.volume.astype(np.float32)
                volume[0, 0, 0] = value
                self.write("liver.nii.gz", volume)
                with self.assertRaisesRegex(ValueError, "binary"):
                    self.mesh()
        # An unset mask unit inherits the CT's (covered separately); an unset CT
        # unit is resolved before this function runs, so only the spatial form is
        # left to reject here.
        image = self.image(self.volume)
        image.set_sform(None, code=0)
        image.set_qform(None, code=0)
        nib.save(image, self.masks / "liver.nii.gz")
        with self.assertRaisesRegex(ValueError, "sform or qform"):
            self.mesh()

    def test_rejects_bad_keys_all_empty_masks_and_a_missing_ct(self):
        self.write("liver.nii.gz")
        self.write("Liver.nii.gz")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.mesh()
        (self.masks / "Liver.nii.gz").unlink()
        self.write("../evil.nii.gz") if False else None
        (self.masks / "liver.nii.gz").rename(self.masks / "9liver.nii.gz")
        with self.assertRaisesRegex(ValueError, "structure keys"):
            self.mesh()
        (self.masks / "9liver.nii.gz").unlink()
        with self.assertRaisesRegex(ValueError, "Expected 1"):
            self.mesh()
        self.write("liver.nii.gz", np.zeros_like(self.volume))
        with self.assertRaisesRegex(ValueError, "Every mask"):
            self.mesh()
        (self.subject / "ct.nii.gz").unlink()
        with self.assertRaisesRegex(ValueError, "no ct.nii.gz"):
            convert(self.subject, self.root / "model")
