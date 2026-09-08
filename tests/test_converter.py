"""Synthetic, CPU-only checks of geometry and the browser asset boundary."""
import json
from pathlib import Path
import tempfile
import unittest

import nibabel as nib
import numpy as np
import trimesh

from scripts.convert_topbrain import convert, label_mesh, read_labelmap, validate_embedded_glb, voxel_to_gltf_transform


class ConverterTests(unittest.TestCase):
    def test_rotation_shear_spacing_origin_and_units(self):
        affine = np.array([[0, -2, 0.3, 10], [3, 0.2, 0, -20], [0, 0, 4, 30], [0, 0, 0, 1]])
        point = np.array([2, 3, 4, 1])
        expected_ras_mm = np.array([5.2, -13.4, 46])
        actual = voxel_to_gltf_transform(affine, "mm") @ point
        np.testing.assert_allclose(actual[:3], expected_ras_mm[[0, 2, 1]] * [0.001, 0.001, -0.001])
        affine_m = affine.copy()
        affine_m[:3] /= 1000
        np.testing.assert_allclose(voxel_to_gltf_transform(affine_m, "meter"), voxel_to_gltf_transform(affine, "mm"))

    def test_boundary_single_voxel_is_closed_and_remains_in_original_position(self):
        volume = np.zeros((3, 4, 5), dtype=np.uint8)
        volume[0, 3, 4] = 4
        mesh, metadata = label_mesh(volume, 4, np.eye(4))
        np.testing.assert_allclose(mesh.bounds, [[-0.5, 2.5, 3.5], [0.5, 3.5, 4.5]])
        self.assertTrue(mesh.is_watertight)
        self.assertGreater(mesh.volume, 0, "Face winding must point outwards for correct lighting")
        mirrored, _ = label_mesh(volume, 4, np.diag([-1, 1, 1, 1]))
        self.assertGreater(mirrored.volume, 0, "Affine reflection must preserve outward face winding")
        self.assertEqual(metadata["voxelCount"], 1)
        self.assertEqual(len(mesh.faces), 8)
        with self.assertRaises(ValueError):
            label_mesh(volume, 7, np.eye(4))

    def test_unknown_units_and_singular_affine_rejected(self):
        for unit in ["unknown", "", "inch"]:
            with self.assertRaises(ValueError):
                voxel_to_gltf_transform(np.eye(4), unit)
        with self.assertRaises(ValueError):
            voxel_to_gltf_transform(np.zeros((4, 4)), "mm")

    def test_full_conversion_preserves_every_label_and_exported_affine_witness(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            labelmap = root / "labelmap.txt"
            labelmap.write_text('0 0 0 0 0 0 0 "Clear"\n1 255 0 0 1 1 1 "BA"\n4 0 255 0 1 1 1 "R-ICA"\n', encoding="utf-8")
            fullnames = root / "fullnames.txt"
            fullnames.write_text("BA → Basilar Artery\nR-ICA → Right Internal Carotid Artery", encoding="utf-8")
            license_path = root / "License.txt"
            license_path.write_text("non-commercial use; commercial permission required", encoding="utf-8")
            volume = np.zeros((5, 6, 7), dtype=np.uint8)
            volume[0, 0, 0] = 1
            volume[3:5, 3:5, 3:6] = 4
            affine = np.array([[0, -2, 0.3, 10], [3, 0.2, 0, -20], [0, 0, 4, 30], [0, 0, 0, 1]])
            image = nib.Nifti1Image(volume, affine)
            image.header.set_xyzt_units("mm")
            # These fields must never propagate to the output.
            image.header["descrip"] = b"PRIVATE_HEADER_DO_NOT_EXPORT"
            source = root / "PRIVATE_SOURCE_DO_NOT_EXPORT.nii.gz"
            nib.save(image, source)
            output = root / "assets" / "model"
            result = convert(source, labelmap, license_path, output, fullnames)
            payload = output.with_suffix(".glb").read_bytes()
            document = validate_embedded_glb(payload, {"label-001", "label-004"})
            self.assertEqual({entry["label"] for entry in result["structures"]}, {1, 4})
            self.assertEqual(result["structures"][0]["name"], "Basilar Artery")
            scene = trimesh.load(output.with_suffix(".glb"), force="scene", process=False)
            affine_readback = nib.load(source).affine
            for entry in result["structures"]:
                witness = entry["geometry"]["affineWitness"]
                # Compute independently rather than calling the converter transform.
                ras_mm = affine_readback @ np.r_[witness["voxel"], 1]
                expected = ras_mm[[0, 2, 1]] * [0.001, 0.001, -0.001]
                geometry = scene.geometry[entry["meshName"]]
                self.assertLess(np.linalg.norm(geometry.vertices - expected, axis=1).min(), 1e-8)
                np.testing.assert_allclose(witness["gltfM"], expected)
            combined = json.dumps(result) + json.dumps(document)
            self.assertNotIn("PRIVATE_HEADER", combined)
            self.assertNotIn("PRIVATE_SOURCE", combined)
            self.assertNotIn(str(root), combined)
            # Batch-1 regression: label header lacks units while the matching CTA
            # image declares mm. Unit evidence must come from an identical grid.
            reference = root / "reference.nii.gz"
            nib.save(image, reference)
            image.header.set_xyzt_units("unknown")
            nib.save(image, source)
            with self.assertRaisesRegex(ValueError, "spatial units"):
                convert(source, labelmap, license_path, output, fullnames)
            resolved = convert(source, labelmap, license_path, output, fullnames, reference)
            self.assertEqual(resolved["metadata"]["sourceUnits"], "unknown")
            self.assertEqual(resolved["metadata"]["resolvedSourceUnits"], "mm")
            other = nib.Nifti1Image(volume, affine + np.diag([0, 0, 1, 0]))
            other.header.set_xyzt_units("mm")
            nib.save(other, reference)
            with self.assertRaisesRegex(ValueError, "identical voxel grid"):
                convert(source, labelmap, license_path, output, fullnames, reference)
            image.header.set_xyzt_units("mm")
            nib.save(image, source)
            labelmap.write_text('1 255 0 0 1 1 1 "BA"\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no mapping"):
                convert(source, labelmap, license_path, output, fullnames)

    def test_label_map_rejects_duplicate_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "labels.txt"
            path.write_text('1 255 0 0 1 1 1 "BA"\n1 0 0 0 1 1 1 "Different"\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                read_labelmap(path)


if __name__ == "__main__":
    unittest.main()
