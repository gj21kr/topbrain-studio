"""The CT context layer: voxels to Gaussians in the GLB's frame, with the viewer's limits."""

import json
from pathlib import Path
import tempfile
import unittest

import nibabel as nib
import numpy as np

from scripts.convert_subject import RAS_MM_TO_GLTF_M, voxel_to_gltf_transform
from scripts.splat_context import MAX_SPLATS, PLY_PROPERTIES, SH_C0, TRANSFER, build_context, gaussian_frame, validate_splat_ply


class GaussianFrameTests(unittest.TestCase):
    def test_identity_and_the_ras_to_gltf_rotation(self):
        spacing, quaternion = gaussian_frame(np.eye(4))
        np.testing.assert_allclose(spacing, [1, 1, 1])
        np.testing.assert_allclose(quaternion, [1, 0, 0, 0])
        # RAS mm -> glTF is a -90 degree turn about x plus a uniform 1/1000 scale.
        spacing, quaternion = gaussian_frame(RAS_MM_TO_GLTF_M)
        np.testing.assert_allclose(spacing, [0.001, 0.001, 0.001])
        np.testing.assert_allclose(np.abs(quaternion), [np.sqrt(0.5), np.sqrt(0.5), 0, 0], atol=1e-12)

    def test_anisotropic_spacing_and_reflection_are_frames_but_shear_is_not(self):
        spacing, _ = gaussian_frame(np.diag([0.7, 0.7, 2.5, 1.0]))
        np.testing.assert_allclose(spacing, [0.7, 0.7, 2.5])
        spacing, quaternion = gaussian_frame(np.diag([-1.5, 1.5, 1.5, 1.0]))
        np.testing.assert_allclose(spacing, [1.5, 1.5, 1.5])
        self.assertAlmostEqual(np.linalg.norm(quaternion), 1.0)
        with self.assertRaisesRegex(ValueError, "shear-free"):
            gaussian_frame(np.array([[1, 0.3, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1.0]]))
        with self.assertRaisesRegex(ValueError, "non-zero"):
            gaussian_frame(np.diag([1, 0, 1, 1.0]))


class ContextLayerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.subject = self.root / "s0007"
        self.subject.mkdir()
        self.affine = np.diag([1.5, 1.5, 1.5, 1.0])
        self.affine[:3, 3] = [-100, -50, 200]
        # Three HU regions: air, soft tissue and bone, one block each.
        volume = np.full((12, 12, 12), -1000, dtype=np.int16)
        volume[0:6, :, :] = 40          # soft tissue: 6*12*12 = 864 voxels
        volume[6:9, :, :] = 250         # contrast band: 3*12*12 = 432
        volume[9:12, :, :] = 900        # bone: 432
        self.volume = volume
        image = nib.Nifti1Image(volume, self.affine)
        image.header["descrip"] = b"PRIVATE_DO_NOT_EXPORT"
        nib.save(image, self.subject / "ct.nii.gz")

    def test_writes_a_valid_ply_in_the_glb_frame_with_the_transfer_function_applied(self):
        context = build_context(self.subject, self.root / "case")
        ply = (self.root / "case.context.ply").read_bytes()
        self.assertEqual(validate_splat_ply(ply), context["splats"])
        counts = {band["band"]: band["splats"] for band in context["transferFunction"]}
        self.assertEqual(counts["bone"], 432)
        self.assertEqual(counts["contrast"], 432)
        # Soft tissue keeps every 3rd voxel per axis: indices 0,3 in x (of 0..5), 0,3,6,9 in y and z.
        self.assertEqual(counts["soft tissue"], 2 * 4 * 4)
        self.assertEqual(context["splats"], 432 + 432 + 32)
        # Same frame as the GLB manifest would carry for this subject.
        transform = voxel_to_gltf_transform(self.affine, "mm")
        np.testing.assert_allclose(context["voxelToGltfM"], transform)
        witness = context["witness"]
        np.testing.assert_allclose(witness["gltfM"], (transform @ np.r_[witness["voxel"], 1])[:3])
        # Header says unknown, resolved as mm, and it is written down.
        self.assertEqual(context["ctUnits"], "unknown")
        self.assertEqual(context["resolvedUnits"], "mm")
        self.assertIn("assumed", context["unitsEvidence"]["method"])
        self.assertNotIn("PRIVATE_DO_NOT_EXPORT", json.dumps(context))
        # Decode the first record and check the encodings a renderer will invert.
        body = ply[ply.index(b"end_header\n") + len(b"end_header\n"):]
        record = np.frombuffer(body[: len(PLY_PROPERTIES) * 4], dtype="<f4")
        bone = next(b for b in TRANSFER if b[0] == "bone")
        np.testing.assert_allclose(record[3:6] * SH_C0 + 0.5, bone[5], atol=1e-6)      # SH DC -> rgb
        self.assertAlmostEqual(1 / (1 + np.exp(-record[6])), bone[4], places=6)         # logit -> alpha
        np.testing.assert_allclose(np.exp(record[7:10]), 0.0015 / 2, rtol=1e-6)        # log scale -> sigma
        np.testing.assert_allclose(np.abs(record[10:14]), [np.sqrt(0.5), np.sqrt(0.5), 0, 0], atol=1e-6)
        self.assertEqual(context["plyBytes"], len(ply))

    def test_strided_soft_tissue_gaussians_widen_to_cover_the_gap(self):
        build_context(self.subject, self.root / "case")
        ply = (self.root / "case.context.ply").read_bytes()
        body = ply[ply.index(b"end_header\n") + len(b"end_header\n"):]
        records = np.frombuffer(body, dtype="<f4").reshape(-1, len(PLY_PROPERTIES))
        sigmas = np.exp(records[:, 7])
        self.assertAlmostEqual(sigmas[:864].max(), 0.0015 / 2, places=9)        # bone + contrast: one voxel
        self.assertAlmostEqual(sigmas[864:].min(), 0.0015 * 3 / 2, places=9)    # soft tissue: three voxels

    def test_the_context_json_carries_every_key_the_browser_cross_checks(self):
        # validateContext in src/model.ts ties the JSON to its PLY (splats) and to the
        # GLB manifest (ctSha256, voxelToGltfM); build_context must keep writing them.
        source = (Path(__file__).resolve().parents[1] / "src" / "model.ts").read_text(encoding="utf-8")
        context = build_context(self.subject, self.root / "case")
        for key in ("kind", "contextVersion", "coordinateSystem", "units", "source", "license", "provenance", "splats", "subject", "ctSha256", "voxelToGltfM"):
            with self.subTest(key=key):
                self.assertIn(key, context)
                self.assertIn(key, source)
        self.assertEqual(context["kind"], "gaussian-splat-context")
        self.assertIn("value.kind !== 'gaussian-splat-context'", source)
        self.assertEqual(context["contextVersion"], 1)
        self.assertIn("value.contextVersion !== 1", source)
        self.assertIn("value.splats !== splats", source)
        self.assertIn("export function validateContext", source)

    def test_rejects_a_missing_ct_a_2d_volume_a_sheared_affine_and_too_many_splats(self):
        with self.assertRaisesRegex(ValueError, "neither ct.nii.gz"):
            build_context(self.root / "nowhere", self.root / "case")
        sheared = self.affine.copy()
        sheared[0, 1] = 0.4
        nib.save(nib.Nifti1Image(self.volume, sheared), self.subject / "ct.nii.gz")
        with self.assertRaisesRegex(ValueError, "shear-free"):
            build_context(self.subject, self.root / "case")
        # More bone voxels than the viewer accepts: the bone band is strided, not refused, and says so.
        side = int(np.ceil((MAX_SPLATS + 1) ** (1 / 3)))
        nib.save(nib.Nifti1Image(np.full((side, side, side), 900, dtype=np.int16), self.affine), self.subject / "ct.nii.gz")
        context = build_context(self.subject, self.root / "case")
        bone = next(b for b in context["transferFunction"] if b["band"] == "bone")
        self.assertEqual((bone["strideRequested"], bone["stride"]), (1, 2))
        self.assertEqual(context["splats"], bone["splats"])
        self.assertLessEqual(context["splats"], MAX_SPLATS)
        self.assertEqual(bone["splats"], int(np.ceil(side / 2)) ** 3)
        nib.save(nib.Nifti1Image(np.full((4, 4, 4), -1000, dtype=np.int16), self.affine), self.subject / "ct.nii.gz")
        with self.assertRaisesRegex(ValueError, "selected no voxels"):
            build_context(self.subject, self.root / "case")


class SplatPlyBoundaryTests(unittest.TestCase):
    """validate_splat_ply and inspectSplatPly must reject the same files."""

    def ply(self, count=2, header=None, body=None):
        header = header or (
            "ply\nformat binary_little_endian 1.0\n"
            f"element vertex {count}\n" + "".join(f"property float {p}\n" for p in PLY_PROPERTIES) + "end_header\n"
        )
        body = body if body is not None else np.zeros(count * len(PLY_PROPERTIES), dtype="<f4").tobytes()
        return header.encode("ascii") + body

    def test_accepts_the_layout_the_writer_produces(self):
        self.assertEqual(validate_splat_ply(self.ply(2)), 2)

    def test_rejects_every_deviation_from_the_layout(self):
        good = self.ply(2)
        cases = [
            ("magic", b"PLY\n" + good[4:], "header"),
            ("ascii format", good.replace(b"binary_little_endian", b"ascii"), "little-endian"),
            ("second element", good.replace(b"end_header", b"element face 1\nproperty float a\nend_header"), "exactly one vertex element"),
            ("zero splats", self.ply(0), "1-"),
            ("over the limit", self.ply(count=MAX_SPLATS + 1, body=b""), "1-"),
            ("property renamed", good.replace(b"property float rot_3", b"property float rot_w"), "3DGS layout"),
            ("property retyped", good.replace(b"property float x\n", b"property double x\n"), "3DGS layout"),
            ("short body", good[:-4], "body length"),
            ("long body", good + b"\0\0\0\0", "body length"),
            ("nan position", self.ply(2, body=np.array([np.nan] + [0.0] * (2 * len(PLY_PROPERTIES) - 1), dtype="<f4").tobytes()), "non-finite"),
        ]
        for label, payload, message in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, message):
                    validate_splat_ply(payload)

    def test_the_limit_and_layout_are_mirrored_in_the_browser_half(self):
        source = (Path(__file__).resolve().parents[1] / "src" / "model.ts").read_text(encoding="utf-8")
        self.assertEqual(MAX_SPLATS, 2_000_000)
        self.assertIn("count > 2_000_000", source)
        self.assertIn("'" + "', '".join(PLY_PROPERTIES) + "'", source)
        self.assertIn("export function inspectSplatPly", source)



class MraContextTests(unittest.TestCase):
    """MRA has no Hounsfield scale: the bands are the volume's own intensity percentiles."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.subject = self.root / "topcow_mr_003"
        self.subject.mkdir()
        affine = np.diag([0.5, 0.5, 0.5, 1.0])
        volume = np.random.default_rng(3).integers(0, 500, (12, 12, 12), dtype=np.int16)
        volume[5:7, 5:7, 0:6] = 2000  # 24 bright voxels, more than the top 1% of 1728
        self.volume = volume
        image = nib.Nifti1Image(volume, affine); image.header.set_xyzt_units("mm")
        nib.save(image, self.subject / "image.nii.gz")
        nib.save(nib.Nifti1Image(np.zeros_like(volume), affine), self.subject / "labels.nii.gz")
        (self.subject / "labelmap.json").write_text(json.dumps({"1": {"key": "ba", "name": "Basilar artery"}}), encoding="utf-8")
        (self.subject / "dataset.json").write_text(json.dumps({
            "dataset": "Synthetic MRA release", "datasetUrl": "https://example.org/d", "datasetPaper": "https://example.org/p",
            "datasetLicense": "Open use", "datasetLicenseUrl": "https://example.org/l", "structureSource": "Synthetic labels",
            "modality": "MRA", "labelKind": "annotation", "catalog": "brain-vessels"}), encoding="utf-8")

    def test_percentile_bands_are_resolved_per_subject_and_recorded(self):
        context = build_context(self.subject, self.root / "case")
        self.assertEqual(context["modality"], "MRA")
        self.assertIn("intensity percentiles", context["provenance"])
        bands = {b["band"]: b for b in context["transferFunction"]}
        self.assertEqual(set(bands), {"vessel", "tissue"})
        vessel, tissue = bands["vessel"], bands["tissue"]
        self.assertEqual((vessel["kind"], vessel["percentileMin"], vessel["percentileMax"]), ("percentile", 99.0, 100.0))
        np.testing.assert_allclose([vessel["low"], vessel["high"]], np.percentile(self.volume, [99.0, 100.0]))
        # The brightest voxels are in the vessel band, the top band being closed at the maximum.
        self.assertEqual(vessel["high"], 2000)
        self.assertGreaterEqual(vessel["splats"], 24)
        self.assertEqual(vessel["stride"], 1)
        self.assertEqual(tissue["stride"], 3)
        self.assertEqual(context["splats"], vessel["splats"] + tissue["splats"])
        self.assertEqual(validate_splat_ply((self.root / "case.context.ply").read_bytes()), context["splats"])
        self.assertNotIn("huMin", vessel)

    def test_ct_bands_stay_hounsfield_and_unknown_modalities_are_refused(self):
        from scripts.splat_context import resolve_transfer
        kind, bands = resolve_transfer(self.volume, "CT")
        self.assertEqual(kind, "hu")
        self.assertEqual([(b["band"], b["huMin"], b["huMax"]) for b in bands], [("bone", 300, 4000), ("contrast", 150, 300), ("soft tissue", -200, 150)])
        with self.assertRaisesRegex(ValueError, "Modality"):
            resolve_transfer(self.volume, "PET")


class SplatBudgetTests(unittest.TestCase):
    """When a volume holds more voxels than the viewer accepts, strides grow and say so."""

    def test_the_largest_band_is_strided_until_the_selection_fits(self):
        import scripts.splat_context as module
        from scripts.splat_context import resolve_transfer
        volume = np.full((30, 30, 30), 500, dtype=np.int16)   # 18,000 bone voxels once the contrast slab is cut out
        volume[:, :, :10] = 200                                 # 9,000 contrast voxels
        original = module.MAX_SPLATS
        module.MAX_SPLATS = 12_000
        try:
            _, bands = resolve_transfer(volume, "CT")
        finally:
            module.MAX_SPLATS = original
        bone, contrast, soft = bands
        # 27,000 selected at stride 1 is over 12,000; bone (the largest band) goes to stride 2,
        # which keeps 15 x 15 x 10 = 2,250 of its 18,000 voxels; 2,250 + 9,000 fits, so it stops there.
        self.assertEqual((bone["strideRequested"], bone["stride"], bone["selected"]), (1, 2, 2250))
        self.assertEqual((contrast["strideRequested"], contrast["stride"], contrast["selected"]), (1, 1, 9000))
        self.assertEqual(soft["selected"], 0)
        _, untouched = resolve_transfer(volume, "CT")
        self.assertEqual([b["stride"] for b in untouched], [1, 1, 3])
        self.assertEqual(sum(b["selected"] for b in untouched), 27_000)

    def test_a_volume_that_cannot_fit_even_at_stride_eight_is_refused(self):
        import scripts.splat_context as module
        from scripts.splat_context import resolve_transfer
        volume = np.full((16, 16, 16), 500, dtype=np.int16)
        original = module.MAX_SPLATS
        module.MAX_SPLATS = 1
        try:
            with self.assertRaisesRegex(ValueError, "stride 8"):
                resolve_transfer(volume, "CT")
        finally:
            module.MAX_SPLATS = original
