"""Synthetic, CPU-only checks of geometry and the browser asset boundary."""
import json
from pathlib import Path
import struct
import tempfile
import unittest

import nibabel as nib
import numpy as np

from scripts.convert_subject import GROUP_EXPLODE, MAX_GLB_BYTES, MAX_MESH_INDICES, MAX_MESH_VERTICES, STRUCTURE_GROUPS, anatomy_explode, anatomy_side, classify_structure, convert, label_mesh, manifest_schema_version, validate_binary_layout, validate_embedded_glb, voxel_to_gltf_transform

# The 117 structure keys of the TotalSegmentator "total" task (dataset v2), as
# published in the tool's class map. The catalog below must place every one.
DATASET_KEYS = (
    "spleen kidney_right kidney_left gallbladder liver stomach pancreas adrenal_gland_right adrenal_gland_left "
    "lung_upper_lobe_left lung_lower_lobe_left lung_upper_lobe_right lung_middle_lobe_right lung_lower_lobe_right "
    "esophagus trachea thyroid_gland small_bowel duodenum colon urinary_bladder prostate kidney_cyst_left kidney_cyst_right "
    "sacrum vertebrae_S1 vertebrae_L5 vertebrae_L4 vertebrae_L3 vertebrae_L2 vertebrae_L1 vertebrae_T12 vertebrae_T11 "
    "vertebrae_T10 vertebrae_T9 vertebrae_T8 vertebrae_T7 vertebrae_T6 vertebrae_T5 vertebrae_T4 vertebrae_T3 vertebrae_T2 "
    "vertebrae_T1 vertebrae_C7 vertebrae_C6 vertebrae_C5 vertebrae_C4 vertebrae_C3 vertebrae_C2 vertebrae_C1 heart aorta "
    "pulmonary_vein brachiocephalic_trunk subclavian_artery_right subclavian_artery_left common_carotid_artery_right "
    "common_carotid_artery_left brachiocephalic_vein_left brachiocephalic_vein_right atrial_appendage_left superior_vena_cava "
    "inferior_vena_cava portal_vein_and_splenic_vein iliac_artery_left iliac_artery_right iliac_vena_left iliac_vena_right "
    "humerus_left humerus_right scapula_left scapula_right clavicula_left clavicula_right femur_left femur_right hip_left hip_right "
    "spinal_cord gluteus_maximus_left gluteus_maximus_right gluteus_medius_left gluteus_medius_right gluteus_minimus_left "
    "gluteus_minimus_right autochthon_left autochthon_right iliopsoas_left iliopsoas_right brain skull "
    "rib_left_1 rib_left_2 rib_left_3 rib_left_4 rib_left_5 rib_left_6 rib_left_7 rib_left_8 rib_left_9 rib_left_10 rib_left_11 rib_left_12 "
    "rib_right_1 rib_right_2 rib_right_3 rib_right_4 rib_right_5 rib_right_6 rib_right_7 rib_right_8 rib_right_9 rib_right_10 rib_right_11 rib_right_12 "
    "sternum costal_cartilages"
).split()


class GeometryTests(unittest.TestCase):
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

    def test_left_handed_affine_converts_end_to_end_with_outward_faces(self):
        """The reflection branch of label_mesh through the whole export path."""
        with tempfile.TemporaryDirectory() as directory:
            subject = Path(directory) / "s0001"
            (subject / "segmentations").mkdir(parents=True)
            volume = np.zeros((6, 6, 6), dtype=np.uint8)
            volume[1:4, 1:4, 1:4] = 1
            # LAS storage: a negative x spacing flips handedness, as real CTs often do.
            affine = np.diag([-1.5, 1.5, 2.0, 1.0])
            affine[:3, 3] = [40, -30, 100]
            for name, data in [("ct", np.random.default_rng(0).integers(0, 200, volume.shape, dtype=np.int16)), ("liver", volume)]:
                image = nib.Nifti1Image(data, affine)
                image.header.set_xyzt_units("mm")
                nib.save(image, (subject / ("ct.nii.gz" if name == "ct" else f"segmentations/{name}.nii.gz")))
            manifest = convert(subject, Path(directory) / "out")
            self.assertLess(np.linalg.det(np.array(manifest["metadata"]["ctAffine"])[:3, :3]), 0)
            geometry = manifest["structures"][0]["geometry"]
            self.assertTrue(geometry["closedSurface"])
            witness = geometry["affineWitness"]
            ras = affine @ np.r_[witness["voxel"], 1]
            np.testing.assert_allclose(witness["gltfM"], ras[[0, 2, 1]] * [0.001, 0.001, -0.001])


class StructureCatalogTests(unittest.TestCase):
    """The dataset's 117 keys must all land in a named group with a side."""

    def test_every_dataset_key_has_a_group_other_than_the_fallback(self):
        unplaced = [key for key in DATASET_KEYS if classify_structure(key.lower())[0] == "Other anatomy"]
        self.assertEqual(unplaced, [])
        self.assertEqual(len(DATASET_KEYS), 117)

    def test_groups_are_disjoint_by_first_match_and_named_as_documented(self):
        seen = {classify_structure(key.lower())[0] for key in DATASET_KEYS}
        self.assertEqual(seen, {group for group, *_ in STRUCTURE_GROUPS})
        self.assertEqual(classify_structure("aorta"), ("Arteries", "#d9534f", 1.0, True))
        self.assertEqual(classify_structure("portal_vein_and_splenic_vein")[0], "Veins")
        self.assertEqual(classify_structure("atrial_appendage_left")[0], "Heart")
        self.assertEqual(classify_structure("kidney_cyst_right")[0], "Urinary")
        self.assertEqual(classify_structure("costal_cartilages")[0], "Ribs")
        self.assertEqual(classify_structure("thyroid_gland")[0], "Glands")
        self.assertEqual(classify_structure("something_unknown"), ("Other anatomy", "#9fb3b0", 0.65, False))

    def test_opening_view_is_skeleton_and_circulation(self):
        visible = {classify_structure(key.lower())[0] for key in DATASET_KEYS if classify_structure(key.lower())[3]}
        self.assertEqual(visible, {"Skull", "Vertebrae", "Ribs", "Limb bones", "Heart", "Arteries", "Veins"})

    def test_side_is_read_from_suffix_and_mid_key_for_ribs(self):
        for key in ["kidney_right", "rib_right_4", "gluteus_maximus_right", "iliac_vena_right", "KIDNEY_RIGHT"]:
            with self.subTest(key=key):
                self.assertEqual(anatomy_side(key), "Right")
        for key in ["kidney_left", "rib_left_12", "lung_upper_lobe_left", "atrial_appendage_left", "adrenal_gland_left"]:
            with self.subTest(key=key):
                self.assertEqual(anatomy_side(key), "Left")
        for key in ["aorta", "brain", "skull", "trachea", "vertebrae_C3", "portal_vein_and_splenic_vein", "sternum"]:
            with self.subTest(key=key):
                self.assertEqual(anatomy_side(key), "Not side-specific")
        sided = sum(anatomy_side(key) != "Not side-specific" for key in DATASET_KEYS)
        self.assertEqual(sided, 66, "25 left/right pairs, 5 lung lobes, the left atrial appendage and 24 ribs")

    def test_explode_shares_one_lateral_sign_and_never_leaves_a_structure_in_place(self):
        for side, expected in [("Right", 0.04), ("Left", -0.04), ("Not side-specific", 0.0)]:
            for group, *_ in STRUCTURE_GROUPS:
                with self.subTest(side=side, group=group):
                    vector = anatomy_explode(group, side)
                    self.assertEqual(vector[0], expected)
                    self.assertNotEqual(vector, [0.0, 0.0, 0.0])
        self.assertEqual(anatomy_explode("Skull", "Not side-specific"), [0.0, 0.06, 0.0])
        self.assertEqual(anatomy_explode("Brain", "Not side-specific"), [0.0, 0.04, 0.0])
        self.assertEqual(anatomy_explode("Vertebrae", "Not side-specific"), [0.0, -0.04, 0.0])
        self.assertEqual(anatomy_explode("Arteries", "Right"), [0.04, 0.02, 0.0])
        self.assertEqual(anatomy_explode("Heart", "Left"), [-0.04, 0.0, -0.03])
        self.assertEqual(anatomy_explode("Muscles", "Not side-specific"), [0.0, -0.02, 0.03])
        # A group the table does not know still separates, anteriorly.
        self.assertEqual(anatomy_explode("Other anatomy", "Not side-specific"), [0.0, 0.0, -0.04])

    def test_every_group_has_a_non_zero_explode_entry(self):
        """The two tables must agree, or a midline structure could sit still."""
        self.assertEqual({group for group, *_ in STRUCTURE_GROUPS}, set(GROUP_EXPLODE))
        for group, offsets in GROUP_EXPLODE.items():
            with self.subTest(group=group):
                self.assertNotEqual(offsets, (0.0, 0.0))


class EmbeddedGlbTests(unittest.TestCase):
    """The producer half of the asset boundary reimplemented in src/model.ts.

    Every rejection here has a counterpart in inspectGlb, readAsset or
    validateMeshData. A limit that moves on one side must move on both.
    """

    def glb(self, document, binary=None):
        """Build a GLB whose BIN chunk actually carries the declared buffer."""
        raw = json.dumps(document).encode("utf-8")
        padded = raw + b" " * (-len(raw) % 4)
        if binary is None:
            declared = document.get("buffers") or [{}]
            length = declared[0].get("byteLength", 0)
            binary = bytes(length + (-length % 4))
        chunks = struct.pack("<II", len(padded), 0x4E4F534A) + padded
        if binary:
            chunks += struct.pack("<II", len(binary), 0x004E4942) + binary
        return struct.pack("<III", 0x46546C67, 2, 12 + len(chunks)) + chunks

    def document(self, names=("liver",), vertices=300, indices=300, primitives=1, mode=4):
        accessors, views, meshes, nodes, offset = [], [], [], [], 0
        for index, name in enumerate(names):
            views.append({"buffer": 0, "byteOffset": offset, "byteLength": vertices * 12})
            offset += vertices * 12
            views.append({"buffer": 0, "byteOffset": offset, "byteLength": indices * 4})
            offset += indices * 4
            accessors.append({"bufferView": 2 * index, "type": "VEC3", "componentType": 5126, "count": vertices})
            accessors.append({"bufferView": 2 * index + 1, "type": "SCALAR", "componentType": 5125, "count": indices})
            primitive = {"attributes": {"POSITION": 2 * index}, "indices": 2 * index + 1, "mode": mode}
            meshes.append({"primitives": [dict(primitive) for _ in range(primitives)]})
            nodes.append({"name": name, "mesh": index})
        return {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": offset}] if offset else [],
            "bufferViews": views,
            "accessors": accessors,
            "meshes": meshes,
            "nodes": nodes,
        }

    def test_accepts_the_static_subset_and_blocks_external_resources(self):
        self.assertEqual(len(validate_embedded_glb(self.glb(self.document()), {"liver"})["nodes"]), 1)
        for uri in ["https://example.com/scan.bin", "../private.bin", "data:application/octet-stream;base64,AA=="]:
            with self.subTest(uri=uri):
                document = self.document() | {"buffers": [{"uri": uri}]}
                with self.assertRaisesRegex(ValueError, "URI"):
                    validate_embedded_glb(self.glb(document), {"liver"})
        for key, value in [("extensionsUsed", ["KHR_draco_mesh_compression"]), ("extensionsRequired", ["KHR_draco_mesh_compression"]), ("animations", [{}]), ("skins", [{}])]:
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "static"):
                    validate_embedded_glb(self.glb(self.document() | {key: value}), {"liver"})

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
                    validate_embedded_glb(broken, {"liver"})
        for label, broken in [
            ("chunk type", payload[:16] + struct.pack("<I", 0x004E4942) + payload[20:]),
            ("unaligned chunk", payload[:12] + struct.pack("<I", 13) + payload[16:]),
            ("chunk past the file", payload[:12] + struct.pack("<I", len(payload)) + payload[16:]),
        ]:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, "JSON chunk"):
                    validate_embedded_glb(broken, {"liver"})

    def test_rejects_meshes_the_browser_would_refuse_to_import(self):
        for label, kwargs in [
            ("too many vertices", {"vertices": 3_000_001}),
            ("no vertices", {"vertices": 2}),
            ("too many indices", {"indices": 9_000_003}),
            ("incomplete triangles", {"indices": 301}),
            ("degenerate index count", {"indices": 0}),
        ]:
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    validate_embedded_glb(self.glb(self.document(**kwargs)), {"liver"})
        for label, kwargs in [("multi-primitive", {"primitives": 2}), ("no primitive", {"primitives": 0}), ("point cloud", {"mode": 0}), ("line strip", {"mode": 3})]:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, "one triangle primitive"):
                    validate_embedded_glb(self.glb(self.document(**kwargs)), {"liver"})
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
                    validate_embedded_glb(self.glb(document), {"liver"})
        document = self.document()
        document["accessors"][0]["type"] = "VEC2"
        with self.assertRaisesRegex(ValueError, "VEC3"):
            validate_embedded_glb(self.glb(document), {"liver"})
        on_limit = self.document(vertices=3_000_000, indices=9_000_000)
        self.assertEqual(len(validate_embedded_glb(self.glb(on_limit), {"liver"})["meshes"]), 1)
        non_indexed = self.document(vertices=299)
        non_indexed["meshes"][0]["primitives"][0].pop("indices")
        with self.assertRaisesRegex(ValueError, "complete triangles"):
            validate_embedded_glb(self.glb(non_indexed), {"liver"})

    def test_rejects_a_binary_chunk_that_does_not_tile_the_file(self):
        payload = self.glb(self.document())
        start = 20 + struct.unpack_from("<I", payload, 12)[0]
        retotal = lambda data: data[:8] + struct.pack("<I", len(data)) + data[12:]
        for label, broken in [
            ("wrong chunk type", payload[:start + 4] + struct.pack("<I", 0x4E4F534A) + payload[start + 8:]),
            ("unaligned length", payload[:start] + struct.pack("<I", 13) + payload[start + 4:]),
            ("length past the file", payload[:start] + struct.pack("<I", 1 << 20) + payload[start + 4:]),
            ("truncated chunk header", retotal(payload[:start + 4])),
            ("trailing bytes", retotal(payload + b"\0\0\0\0")),
            ("a third chunk", retotal(payload + struct.pack("<II", 0, 0x4E4F534A))),
        ]:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, "binary chunk"):
                    validate_embedded_glb(broken, {"liver"})

    def test_binary_layout_proves_the_bytes_behind_every_accessor_exist(self):
        base = self.document()
        length = base["buffers"][0]["byteLength"]
        validate_binary_layout(base, length)
        validate_binary_layout(base, length + 3)
        for label, padding in [("chunk shorter than its buffer", -4), ("more than padding", 4)]:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, "binary chunk that carries it"):
                    validate_binary_layout(base, length + padding)
        for label, mutate, message in [
            ("two buffers", lambda d: d["buffers"].append({"byteLength": 8}), "single binary buffer"),
            ("view past the buffer", lambda d: d["bufferViews"][1].__setitem__("byteLength", length), "outside the binary chunk"),
            ("view of a second buffer", lambda d: d["bufferViews"][0].__setitem__("buffer", 1), "not embedded"),
            ("accessor without a view", lambda d: d["accessors"][0].pop("bufferView"), "no buffer view"),
            ("accessor view out of range", lambda d: d["accessors"][0].__setitem__("bufferView", 9), "no buffer view"),
            ("unknown component type", lambda d: d["accessors"][0].__setitem__("componentType", 5124), "unknown component type"),
            ("unknown element type", lambda d: d["accessors"][0].__setitem__("type", "VEC9"), "unknown component type"),
            ("count past the view", lambda d: d["accessors"][0].__setitem__("count", 301), "past the end"),
            ("offset past the view", lambda d: d["accessors"][0].__setitem__("byteOffset", 12), "past the end"),
        ]:
            with self.subTest(label=label):
                document = json.loads(json.dumps(base))
                mutate(document)
                with self.assertRaisesRegex(ValueError, message):
                    validate_binary_layout(document, length)
        strided = json.loads(json.dumps(base))
        strided["bufferViews"][0]["byteStride"] = 24
        with self.assertRaisesRegex(ValueError, "past the end"):
            validate_binary_layout(strided, length)
        wired = self.document()
        wired["bufferViews"][0]["byteLength"] = wired["buffers"][0]["byteLength"] + 4
        with self.assertRaisesRegex(ValueError, "outside the binary chunk"):
            validate_embedded_glb(self.glb(wired), {"liver"})

    def test_rejects_payloads_over_the_browser_import_limit(self):
        with self.assertRaisesRegex(ValueError, "150 MB"):
            validate_embedded_glb(bytes(150 * 1024 * 1024 + 1), {"liver"})

    def test_limits_stay_equal_to_the_browser_half_in_model_ts(self):
        """Neither half of a mirrored limit may move without the other."""
        source = (Path(__file__).resolve().parents[1] / "src" / "model.ts").read_text(encoding="utf-8")
        self.assertEqual([MAX_GLB_BYTES, MAX_MESH_VERTICES, MAX_MESH_INDICES], [150 * 1024 * 1024, 3_000_000, 9_000_000])
        self.assertIn(f"byteLength > {MAX_GLB_BYTES // (1024 * 1024)} * 1024 * 1024", source)
        self.assertIn(f"positions.count > {MAX_MESH_VERTICES:_}", source)
        self.assertIn(f"count > {MAX_MESH_INDICES:_}", source)
        self.assertIn("!== 0x004e4942", source)
        self.assertIn("next + 8 + binary !== buffer.byteLength", source)

    def test_rejects_mesh_names_that_differ_from_the_manifest(self):
        for label, names, expected in [
            ("renamed", ("spleen",), {"liver"}),
            ("missing structure", ("liver",), {"liver", "spleen"}),
            ("extra mesh", ("liver", "spleen"), {"liver"}),
            ("duplicate", ("liver", "liver"), {"liver"}),
        ]:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, "names differ"):
                    validate_embedded_glb(self.glb(self.document(names)), expected)
        unnamed = self.document()
        unnamed["nodes"][0].pop("name")
        with self.assertRaisesRegex(ValueError, "names differ"):
            validate_embedded_glb(self.glb(unnamed), {"liver"})


class SchemaVersionTests(unittest.TestCase):
    """Schema 2 promises one thing that both halves enforce: every structure names its source."""

    def test_schema_2_requires_a_source_on_every_structure(self):
        good = [{"id": "liver", "source": "TotalSegmentator dataset"}, {"id": "aorta", "source": "TotalSegmentator dataset"}]
        self.assertEqual(manifest_schema_version(good), 2)
        for label, broken in [("absent", {}), ("null", {"source": None}), ("empty", {"source": ""})]:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, "aorta has none"):
                    manifest_schema_version([good[0], {"id": "aorta", **broken}])

    def test_the_promise_is_mirrored_in_the_browser_half(self):
        source = (Path(__file__).resolve().parents[1] / "src" / "model.ts").read_text(encoding="utf-8")
        self.assertIn("value.schemaVersion === 2 && s.source === undefined", source)
        self.assertIn("Schema 2 requires an explicit source on every structure.", source)
