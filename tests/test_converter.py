"""Synthetic, CPU-only checks of geometry and the browser asset boundary."""
import json
from pathlib import Path
import struct
import tempfile
import unittest

import nibabel as nib
import numpy as np
import trimesh

from scripts.convert_topbrain import MAX_GLB_BYTES, MAX_MESH_INDICES, MAX_MESH_VERTICES, anatomy_explode, anatomy_side, convert, label_mesh, read_labelmap, validate_embedded_glb, voxel_to_gltf_transform


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

    def test_label_groups_split_arteries_from_veins_at_the_release_boundary(self):
        """Both sides of the grouping boundary, which drives the viewer's filters."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            labelmap = root / "labelmap.txt"
            labelmap.write_text('34 255 0 0 1 1 1 "L-PCA"\n35 0 0 255 1 1 1 "SSS"\n', encoding="utf-8")
            license_path = root / "License.txt"
            license_path.write_text("non-commercial use; commercial permission required", encoding="utf-8")
            volume = np.zeros((5, 5, 5), dtype=np.uint8)
            volume[1, 1, 1] = 34
            volume[3, 3, 3] = 35
            image = nib.Nifti1Image(volume, np.eye(4))
            image.header.set_xyzt_units("mm")
            source = root / "case.nii.gz"
            nib.save(image, source)
            manifest = convert(source, labelmap, license_path, root / "model")
            grouped = {entry["label"]: entry["group"] for entry in manifest["structures"]}
            self.assertEqual(grouped, {34: "Arteries", 35: "Veins and sinuses"})
            sided = {entry["label"]: entry["side"] for entry in manifest["structures"]}
            self.assertEqual(sided, {34: "Left", 35: "Not side-specific"})

    def test_label_map_rejects_duplicate_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "labels.txt"
            path.write_text('1 255 0 0 1 1 1 "BA"\n1 0 0 0 1 1 1 "Different"\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                read_labelmap(path)


if __name__ == "__main__":
    unittest.main()


class EmbeddedGlbTests(unittest.TestCase):
    """The producer half of the asset boundary reimplemented in src/model.ts.

    Every rejection here has a counterpart in inspectGlb, readAsset or
    validateMeshData. A limit that moves on one side must move on both.
    """

    def glb(self, document):
        raw = json.dumps(document).encode("utf-8")
        padded = raw + b" " * (-len(raw) % 4)
        header = struct.pack("<IIIII", 0x46546C67, 2, 20 + len(padded), len(padded), 0x4E4F534A)
        return header + padded

    def document(self, names=("label-001",), vertices=300, indices=300, primitives=1, mode=4):
        accessors, meshes, nodes = [], [], []
        for index, name in enumerate(names):
            accessors.append({"type": "VEC3", "componentType": 5126, "count": vertices})
            accessors.append({"type": "SCALAR", "componentType": 5125, "count": indices})
            primitive = {"attributes": {"POSITION": 2 * index}, "indices": 2 * index + 1, "mode": mode}
            meshes.append({"primitives": [dict(primitive) for _ in range(primitives)]})
            nodes.append({"name": name, "mesh": index})
        return {"asset": {"version": "2.0"}, "accessors": accessors, "meshes": meshes, "nodes": nodes}

    def test_accepts_the_static_subset_and_blocks_external_resources(self):
        self.assertEqual(len(validate_embedded_glb(self.glb(self.document()), {"label-001"})["nodes"]), 1)
        for uri in ["https://example.com/scan.bin", "../private.bin", "data:application/octet-stream;base64,AA=="]:
            with self.subTest(uri=uri):
                document = self.document() | {"buffers": [{"uri": uri}]}
                with self.assertRaisesRegex(ValueError, "URI"):
                    validate_embedded_glb(self.glb(document), {"label-001"})
        for key, value in [("extensionsUsed", ["KHR_draco_mesh_compression"]), ("extensionsRequired", ["KHR_draco_mesh_compression"]), ("animations", [{}]), ("skins", [{}])]:
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "static"):
                    validate_embedded_glb(self.glb(self.document() | {key: value}), {"label-001"})

    def test_rejects_malformed_header_and_json_chunk(self):
        payload = self.glb(self.document())
        for label, broken in [
            ("truncated", payload[:12]),
            ("magic", b"\x00\x00\x00\x00" + payload[4:]),
            ("version", payload[:4] + struct.pack("<I", 1) + payload[8:]),
            ("declared length", payload[:8] + struct.pack("<I", len(payload) + 4) + payload[12:]),
        ]:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, "header"):
                    validate_embedded_glb(broken, {"label-001"})
        for label, broken in [
            ("chunk type", payload[:16] + struct.pack("<I", 0x004E4942) + payload[20:]),
            ("unaligned chunk", payload[:12] + struct.pack("<I", 13) + payload[16:]),
            ("chunk past the file", payload[:12] + struct.pack("<I", len(payload)) + payload[16:]),
        ]:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, "JSON chunk"):
                    validate_embedded_glb(broken, {"label-001"})

    def test_rejects_meshes_the_browser_would_refuse_to_import(self):
        # Regression: the converter used to cap only total bytes, so a single
        # dense structure could stay under 150 MB and still exceed the per-mesh
        # limits validateMeshData applies after the browser parses the file.
        for label, kwargs in [
            ("too many vertices", {"vertices": 3_000_001}),
            ("no vertices", {"vertices": 2}),
            ("too many indices", {"indices": 9_000_003}),
            ("incomplete triangles", {"indices": 301}),
            ("degenerate index count", {"indices": 0}),
        ]:
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    validate_embedded_glb(self.glb(self.document(**kwargs)), {"label-001"})
        # A multi-primitive mesh parses into several three.js meshes behind one
        # glTF node, which breaks the viewer's manifest-to-mesh name matching.
        for label, kwargs in [("multi-primitive", {"primitives": 2}), ("no primitive", {"primitives": 0}), ("point cloud", {"mode": 0}), ("line strip", {"mode": 3})]:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, "one triangle primitive"):
                    validate_embedded_glb(self.glb(self.document(**kwargs)), {"label-001"})
        for label, mutate in [
            ("missing POSITION", lambda d: d["meshes"][0]["primitives"][0]["attributes"].clear()),
            ("POSITION out of range", lambda d: d["meshes"][0]["primitives"][0]["attributes"].__setitem__("POSITION", 9)),
            ("index out of range", lambda d: d["meshes"][0]["primitives"][0].__setitem__("indices", 9)),
            ("countless accessor", lambda d: d["accessors"][0].pop("count")),
        ]:
            with self.subTest(label=label):
                document = self.document()
                mutate(document)
                with self.assertRaisesRegex(ValueError, "accessor is missing"):
                    validate_embedded_glb(self.glb(document), {"label-001"})
        document = self.document()
        document["accessors"][0]["type"] = "VEC2"
        with self.assertRaisesRegex(ValueError, "VEC3"):
            validate_embedded_glb(self.glb(document), {"label-001"})
        # Sitting exactly on both browser limits must still convert.
        on_limit = self.document(vertices=3_000_000, indices=9_000_000)
        self.assertEqual(len(validate_embedded_glb(self.glb(on_limit), {"label-001"})["meshes"]), 1)
        # Non-indexed geometry falls back to the vertex count for the triangle check.
        non_indexed = self.document(vertices=299)
        non_indexed["meshes"][0]["primitives"][0].pop("indices")
        with self.assertRaisesRegex(ValueError, "complete triangles"):
            validate_embedded_glb(self.glb(non_indexed), {"label-001"})

    def test_rejects_payloads_over_the_browser_import_limit(self):
        with self.assertRaisesRegex(ValueError, "150 MB"):
            validate_embedded_glb(bytes(150 * 1024 * 1024 + 1), {"label-001"})

    def test_limits_stay_equal_to_the_browser_half_in_model_ts(self):
        """Neither half of a mirrored limit may move without the other."""
        source = (Path(__file__).resolve().parents[1] / "src" / "model.ts").read_text(encoding="utf-8")
        self.assertEqual([MAX_GLB_BYTES, MAX_MESH_VERTICES, MAX_MESH_INDICES], [150 * 1024 * 1024, 3_000_000, 9_000_000])
        self.assertIn(f"byteLength > {MAX_GLB_BYTES // (1024 * 1024)} * 1024 * 1024", source)
        self.assertIn(f"positions.count > {MAX_MESH_VERTICES:_}", source)
        self.assertIn(f"count > {MAX_MESH_INDICES:_}", source)

    def test_rejects_mesh_names_that_differ_from_the_manifest(self):
        for label, names, expected in [
            ("renamed", ("label-002",), {"label-001"}),
            ("missing structure", ("label-001",), {"label-001", "label-004"}),
            ("extra mesh", ("label-001", "label-004"), {"label-001"}),
            ("duplicate", ("label-001", "label-001"), {"label-001"}),
        ]:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, "names differ"):
                    validate_embedded_glb(self.glb(self.document(names)), expected)
        unnamed = self.document()
        unnamed["nodes"][0].pop("name")
        with self.assertRaisesRegex(ValueError, "names differ"):
            validate_embedded_glb(self.glb(unnamed), {"label-001"})


class SharedDerivationTests(unittest.TestCase):
    """Laterality and separation now have one implementation for both paths.

    TopBrain labels and TotalSegmentator masks name their sides differently, so
    these used to be two rules with a shared vocabulary and no shared code.
    """

    def test_side_reads_both_naming_conventions_and_normalises_casing(self):
        for name in ["R-ICA", "r-ica", "R-TS", "kidney_r", "KIDNEY_R", "common_carotid_artery_right"]:
            with self.subTest(name=name):
                self.assertEqual(anatomy_side(name), "Right")
        for name in ["L-MCA", "l-mca", "L-VA", "kidney_l", "clavicula_left", "lung_upper_lobe_l"]:
            with self.subTest(name=name):
                self.assertEqual(anatomy_side(name), "Left")
        for name in ["BA", "SSS", "AComA", "Torcula", "brain", "skull", "trachea", "aorta", "spinal_cord", "vertebrae_C3"]:
            with self.subTest(name=name):
                self.assertEqual(anatomy_side(name), "Not side-specific")

    def test_side_never_contradicts_the_prefix_rule_it_replaced(self):
        """Reading both conventions may resolve a name, never re-answer one."""
        prefix_only = lambda n: "Right" if n.startswith("R-") else "Left" if n.startswith("L-") else None
        corpus = ["BA", "R-ICA", "L-MCA", "SSS", "AComA", "Torcula", "R-TS", "L-VA", "ICA_R", "sinus_left", "r-ica"]
        widened = []
        for name in corpus:
            old, unified = prefix_only(name), anatomy_side(name)
            if old is not None:
                self.assertEqual(unified, old, f"{name} lost or changed its side")
            elif unified != "Not side-specific":
                widened.append(name)
        # A mask key can never hold a hyphen, so only label names widen here.
        self.assertEqual(widened, ["ICA_R", "sinus_left", "r-ica"])

    def test_explode_shares_one_lateral_sign_across_both_import_paths(self):
        for side, expected in [("Right", 0.04), ("Left", -0.04), ("Not side-specific", 0.0)]:
            with self.subTest(side=side):
                vessel = anatomy_explode("R-ICA", "Arteries", side)
                vein = anatomy_explode("SSS", "Veins and sinuses", side)
                anatomy = anatomy_explode("kidney_r", "Other anatomy", side)
                bone = anatomy_explode("rib_left_4", "Bones", side)
                for vector in [vessel, vein, anatomy, bone]:
                    self.assertEqual(vector[0], expected)
                # Vessels keep the vector convert() used to build inline.
                self.assertEqual(vessel, [expected, 0.02, 0.0])
                self.assertEqual(vein, [expected, 0.02, 0.0])

    def test_explode_parts_nested_groups_along_distinct_offsets(self):
        verticals = {
            "skull": anatomy_explode("skull", "Bones", "Not side-specific"),
            "brain": anatomy_explode("brain", "Brain", "Not side-specific"),
            "vessel": anatomy_explode("BA", "Arteries", "Not side-specific"),
            "cord": anatomy_explode("spinal_cord", "Spinal cord", "Not side-specific"),
            "bone": anatomy_explode("vertebrae_C3", "Bones", "Not side-specific"),
        }
        self.assertEqual([v[1] for v in verticals.values()], [0.06, 0.04, 0.02, -0.02, -0.04])
        self.assertEqual(len({tuple(v) for v in verticals.values()}), len(verticals))
        # A vessel answers from its group alone, so no label short name can
        # reach the skull special case that sits below it.
        self.assertEqual(anatomy_explode("skull", "Arteries", "Not side-specific"), [0.0, 0.02, 0.0])
        self.assertEqual(anatomy_explode("skull", "Bones", "Not side-specific"), [0.0, 0.06, 0.0])
        # An ungrouped midline structure moves anteriorly, not vertically.
        self.assertEqual(anatomy_explode("trachea", "Other anatomy", "Not side-specific"), [0.0, 0.0, -0.04])
        for vector in [*verticals.values(), anatomy_explode("trachea", "Other anatomy", "Not side-specific")]:
            self.assertNotEqual(vector, [0.0, 0.0, 0.0], "every structure must separate")
