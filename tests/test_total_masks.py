"""Synthetic integration checks; no real source volumes are test fixtures."""

import json
from pathlib import Path
import tempfile
import unittest

import nibabel as nib
import numpy as np
import trimesh

from scripts.convert_topbrain import append_total_masks, convert


class TotalMaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.masks = self.root / "masks"
        self.masks.mkdir()
        self.affine = np.array(
            [[0, -2, 0.3, 10], [3, 0.2, 0, -20], [0, 0, 4, 30], [0, 0, 0, 1.0]]
        )
        self.volume = np.zeros((6, 7, 8), dtype=np.uint8)
        self.volume[1:4, 2:5, 3:6] = 1
        self.reference = self.image(self.volume)

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

    def append(self):
        scene, structures = trimesh.Scene(), []
        metadata = append_total_masks(
            scene, structures, self.masks, self.reference, "mm"
        )
        return scene, structures, metadata

    def test_combined_export_preserves_overlapping_masks_and_world_coordinates(self):
        self.write("Brain.nii.gz")
        self.write("Skull.nii.gz")
        self.write("Vertebrae_C3.nii.gz", np.zeros_like(self.volume))
        source = self.root / "PRIVATE_CASE.nii.gz"
        nib.save(self.reference, source)
        labelmap = self.root / "map.txt"
        labelmap.write_text('1 255 0 0 1 1 1 "BA"\n')
        license_path = self.root / "License.txt"
        license_path.write_text("non-commercial use; permission required")
        out = self.root / "model"
        result = convert(
            source, labelmap, license_path, out, total_masks_path=self.masks
        )
        self.assertEqual(result["schemaVersion"], 2)
        self.assertEqual(len(result["structures"]), 3)
        scene = trimesh.load(out.with_suffix(".glb"), force="scene", process=False)
        vessel = scene.geometry["label-001"]
        for entry in result["structures"][1:]:
            self.assertEqual(entry["source"], "TotalSegmentator")
            self.assertFalse(entry["defaultVisible"])
            np.testing.assert_allclose(
                scene.geometry[entry["meshName"]].bounds, vessel.bounds
            )
            witness = entry["geometry"]["affineWitness"]
            ras = nib.load(source).affine @ np.r_[witness["voxel"], 1]
            expected = ras[[0, 2, 1]] * [0.001, 0.001, -0.001]
            np.testing.assert_allclose(witness["gltfM"], expected)
            self.assertLess(
                np.linalg.norm(
                    scene.geometry[entry["meshName"]].vertices - expected, axis=1
                ).min(),
                1e-8,
            )
        total = result["metadata"]["totalSegmentator"]
        self.assertEqual(len(total["skippedEmpty"]), 1)
        self.assertEqual(total["inputMaskCount"], 3)
        serialized = json.dumps(result)
        for private in [str(self.root), "PRIVATE_CASE", "PRIVATE_DO_NOT_EXPORT"]:
            self.assertNotIn(private, serialized)

    def test_masks_receive_group_directed_explode_vectors(self):
        names = [
            "brain",
            "skull",
            "spinal_cord",
            "vertebrae_C3",
            "clavicula_left",
            "common_carotid_artery_right",
            "trachea",
        ]
        for name in names:
            self.write(f"{name}.nii.gz")
        structures = self.append()[1]
        explode = {entry["sourceShortName"]: entry["explode"] for entry in structures}
        self.assertEqual(set(explode), set(names))
        # Midline structures separate along the superior/inferior axis by group;
        # sided structures also move laterally with the TopBrain vessel sign.
        self.assertEqual(explode["brain"], [0, 0.04, 0])
        self.assertEqual(explode["skull"], [0, 0.06, 0])
        self.assertEqual(explode["spinal_cord"], [0, -0.02, 0])
        self.assertEqual(explode["vertebrae_C3"], [0, -0.04, 0])
        self.assertEqual(explode["clavicula_left"], [-0.04, -0.04, 0])
        self.assertEqual(explode["common_carotid_artery_right"], [0.04, 0.02, 0])
        self.assertEqual(explode["trachea"], [0, 0, -0.04])
        for vector in explode.values():
            self.assertGreater(np.linalg.norm(vector), 0)
            self.assertTrue(all(abs(component) <= 10 for component in vector))

    def test_combined_export_keeps_vessel_explode_and_separates_masks(self):
        self.write("brain.nii.gz")
        self.write("skull.nii.gz")
        source = self.root / "case.nii.gz"
        nib.save(self.reference, source)
        labelmap = self.root / "map.txt"
        labelmap.write_text('1 255 0 0 1 1 1 "BA"\n2 0 255 0 1 1 1 "R-ICA"\n')
        volume = self.volume.copy()
        volume[1:2] = 2
        nib.save(self.image(volume), source)
        license_path = self.root / "License.txt"
        license_path.write_text("non-commercial use; permission required")
        result = convert(
            source,
            labelmap,
            license_path,
            self.root / "model",
            total_masks_path=self.masks,
        )
        explode = {
            entry["sourceShortName"]: entry["explode"] for entry in result["structures"]
        }
        self.assertEqual(explode["BA"], [0, 0.02, 0])
        self.assertEqual(explode["R-ICA"], [0.04, 0.02, 0])
        self.assertEqual(explode["brain"], [0, 0.04, 0])
        self.assertEqual(explode["skull"], [0, 0.06, 0])
        self.assertNotEqual(explode["brain"], explode["BA"])

    def test_unit_equivalence(self):
        affine_m = self.affine.copy()
        affine_m[:3] /= 1000
        self.write("Brain.nii.gz", affine=affine_m, unit="meter")
        self.assertEqual(len(self.append()[1]), 1)

    def test_rejects_mismatched_grid_including_empty_masks(self):
        for empty in [False, True]:
            with self.subTest(empty=empty):
                affine = self.affine.copy()
                affine[0, 3] += 1
                self.write(
                    "Brain.nii.gz",
                    np.zeros_like(self.volume) if empty else self.volume,
                    affine,
                )
                with self.assertRaisesRegex(ValueError, "physical voxel grid"):
                    self.append()
        self.write("Brain.nii.gz", np.zeros((3, 3, 3), dtype=np.uint8))
        with self.assertRaisesRegex(ValueError, "identical voxel grid"):
            self.append()

    def test_rejects_nonbinary_unknown_units_and_missing_spatial_form(self):
        for value in [2, -1, 0.5, np.nan, np.inf]:
            with self.subTest(value=value):
                volume = self.volume.astype(np.float32)
                volume[0, 0, 0] = value
                self.write("Brain.nii.gz", volume)
                with self.assertRaisesRegex(ValueError, "binary"):
                    self.append()
        self.write("Brain.nii.gz", unit="unknown")
        with self.assertRaisesRegex(ValueError, "spatial units"):
            self.append()
        image = self.image(self.volume)
        image.set_sform(None, code=0)
        image.set_qform(None, code=0)
        nib.save(image, self.masks / "Brain.nii.gz")
        with self.assertRaisesRegex(ValueError, "sform or qform"):
            self.append()

    def test_rejects_duplicate_keys_and_empty_directory(self):
        with self.assertRaisesRegex(ValueError, "1–500"):
            self.append()
        self.write("Brain.nii.gz")
        self.write("Brain.nii")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.append()


if __name__ == "__main__":
    unittest.main()
