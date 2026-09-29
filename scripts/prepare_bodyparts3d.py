"""Prepare a compact public BodyParts3D reference atlas for the demo.

The source is the official, 99% polygon-reduced BodyParts3D 4.0 PART-OF
archive. Its atomic FJ meshes share one reference coordinate system. This
script never reads dataset CT volumes or patient images.

Run from the repository root with ``python scripts/prepare_bodyparts3d.py``.
The 62 MB source archive and mapping tables are cached under ignored
``private-assets/bodyparts3d/``; only the three files in ``public/reference``
are publication outputs. Use ``--cache-dir`` for an existing offline cache.
"""

from __future__ import annotations

import argparse
from array import array
from collections import defaultdict
import hashlib
import io
import json
import math
from pathlib import Path
import re
import struct
import sys
from urllib.request import ProxyHandler, build_opener
import zipfile


BASE = "https://dbarchive.biosciencedbc.jp/data/bodyparts3d/20130619/"
ARCHIVE_NAME = "partof_BP3D_4.0_obj_99.zip"
ARCHIVE_SHA256 = "9fbc713fffeee924a5a657d9813d84d7eb957bded63adb854931dd5e3eb61c97"
TABLES = {
    "partof_parts_list_e.txt": "9224080557053e6f1322f1e13ab27f0ecde0db19bb3b505f0631afad230eeebd",
    "partof_element_parts.txt": "3f5f6df1028eb122b30de77c711597b6bb8e5541658e5985859fd228adbf88ea",
}
LICENSE_URL = "https://dbarchive.biosciencedbc.jp/en/bodyparts3d/lic.html"
ARCHIVE_URL = BASE + ARCHIVE_NAME
CREDIT = "BodyParts3D, © The Database Center for Life Science licensed under CC Attribution 4.0 International"
SOURCE = "BodyParts3D 4.0 PART-OF Tree reference anatomy (DBCLS)"


# Curated atomic files form disjoint, accurately named structures. Compound
# skull and brain membership is read from the official element table below.
# The PART-OF 4.0 archive contains no left MCA counterpart to its right MCA
# compound, so none is invented or mirrored here.
VESSELS = [
    ("right-aca", "Right anterior cerebral artery", "Anterior circulation", "Right", "FMA50029", "BP9915", ("FJ1654",), "앞대뇌동맥의 오른쪽 참조 구조입니다.", "#e87866", (0.7, 0.25, -0.15)),
    ("left-aca", "Left anterior cerebral artery", "Anterior circulation", "Left", "FMA50030", "BP10243", ("FJ1654M",), "앞대뇌동맥의 왼쪽 참조 구조입니다.", "#fa9b77", (-0.7, 0.25, -0.15)),
    ("acom", "Anterior communicating artery", "Anterior circulation", "Midline", "FMA50169", "BP6762", ("FJ1655",), "양쪽 앞대뇌동맥 사이의 연결 구조입니다.", "#eac075", (0.0, 0.45, -0.45)),
    ("right-mca", "Right middle cerebral artery", "Anterior circulation", "Right", "FMA50082", "BP9813", ("FJ1662", "FJ1663", "FJ1692"), "중대뇌동맥의 오른쪽 참조 구조입니다. 이 판본에는 상응하는 왼쪽 합성 구조가 없습니다.", "#f5aa8e", (0.9, 0.15, -0.1)),
    ("right-ica", "Right internal carotid artery", "Anterior circulation", "Right", "FMA3949", "BP9518", ("FJ1682",), "오른쪽 내경동맥의 참조 요소입니다. 아래쪽 온목동맥과 연결되는 경부 메쉬가 원본에 없습니다.", "#d97168", (0.85, -0.25, 0.1)),
    ("left-ica", "Left internal carotid artery", "Anterior circulation", "Left", "FMA4062", "BP9516", ("FJ1682M",), "왼쪽 내경동맥의 참조 요소입니다. 아래쪽 온목동맥과 연결되는 경부 메쉬가 원본에 없습니다.", "#eb8b7e", (-0.85, -0.25, 0.1)),
    ("right-pcom", "Right posterior communicating artery", "Connections", "Right", "FMA50085", "BP7710", ("FJ1713",), "오른쪽 뒤교통동맥의 참조 구조입니다.", "#e4bc79", (0.55, 0.2, 0.55)),
    ("left-pcom", "Left posterior communicating artery", "Connections", "Left", "FMA50086", "BP9658", ("FJ1713M",), "왼쪽 뒤교통동맥의 참조 구조입니다.", "#f1ce90", (-0.55, 0.2, 0.55)),
    ("right-pca", "Right posterior cerebral artery", "Posterior circulation", "Right", "FMA50584", "BP7696", ("FJ1723", "FJ1661", "FJ1675", "FJ1677", "FJ1678", "FJ1680", "FJ1687", "FJ1691", "FJ1720", "FJ1727"), "오른쪽 뒤대뇌동맥과 분지의 참조 요소입니다.", "#84c5bb", (0.8, 0.4, 0.55)),
    ("left-pca", "Left posterior cerebral artery", "Posterior circulation", "Left", "FMA50585", "BP9430", ("FJ1723M", "FJ1661M", "FJ1675M", "FJ1677M", "FJ1678M", "FJ1680M", "FJ1687M", "FJ1691M", "FJ1720M", "FJ1727M"), "왼쪽 뒤대뇌동맥과 분지의 참조 요소입니다.", "#9bdbca", (-0.8, 0.4, 0.55)),
    ("basilar", "Basilar artery", "Posterior circulation", "Midline", "FMA50542", "BP9431", ("FJ1672", "FJ1844"), "뇌바닥동맥 몸통의 참조 요소입니다.", "#75bcb8", (0.0, -0.2, 0.95)),
    ("right-va", "Right vertebral artery", "Posterior circulation", "Right", "FMA3958", "BP9432", ("FJ1725",), "오른쪽 척추동맥의 참조 요소입니다. 빗장밑동맥에서 이 요소로 이어지는 하부 경부 메쉬가 원본에 없습니다.", "#73a8c8", (0.6, -0.55, 0.4)),
    ("left-va", "Left vertebral artery", "Posterior circulation", "Left", "FMA4066", "BP9323", ("FJ1725M",), "왼쪽 척추동맥의 참조 요소입니다. 빗장밑동맥에서 이 요소로 이어지는 하부 경부 메쉬가 원본에 없습니다.", "#91bad7", (-0.6, -0.55, 0.4)),
    ("right-sca", "Right superior cerebellar artery", "Posterior circulation", "Right", "FMA50574", "BP7713", ("FJ1726",), "오른쪽 위소뇌동맥의 참조 요소입니다.", "#8fd5d0", (0.65, -0.2, 0.8)),
    ("left-sca", "Left superior cerebellar artery", "Posterior circulation", "Left", "FMA50575", "BP10235", ("FJ1726M",), "왼쪽 위소뇌동맥의 참조 요소입니다.", "#ade2d6", (-0.65, -0.2, 0.8)),
    ("ascending-aorta", "Ascending aorta", "Proximal arterial supply", "Midline", "FMA3736", "BP10408", ("FJ3413",), "오름대동맥의 공식 참조 요소입니다. 전체 대동맥은 포함하지 않습니다.", "#be7b70", (0.0, -0.9, -0.4)),
    ("aortic-arch", "Arch of aorta", "Proximal arterial supply", "Midline", "FMA3768", "BP10404", ("FJ3411",), "대동맥활의 공식 참조 요소입니다.", "#d18d79", (0.0, -0.65, -0.55)),
    ("brachiocephalic", "Brachiocephalic artery", "Proximal arterial supply", "Midline", "FMA3932", "BP9434", ("FJ3417",), "팔머리동맥 줄기의 공식 참조 요소입니다.", "#e2a48b", (0.35, -0.45, -0.25)),
    ("right-cca", "Right common carotid artery", "Proximal arterial supply", "Right", "FMA3941", "BP9519", ("FJ3564",), "오른쪽 온목동맥의 공식 참조 요소입니다. 위쪽 내경동맥까지 약 6 cm의 원본 모델 공백이 있습니다.", "#e69b7d", (0.85, -0.15, -0.1)),
    ("left-cca", "Left common carotid artery", "Proximal arterial supply", "Left", "FMA4058", "BP9517", ("FJ3483",), "왼쪽 온목동맥의 공식 참조 요소입니다. 위쪽 내경동맥까지 약 6 cm의 원본 모델 공백이 있습니다.", "#f0af90", (-0.85, -0.15, -0.1)),
    ("right-subclavian", "Right subclavian artery", "Proximal arterial supply", "Right", "FMA3953", "BP9433", ("FJ3579",), "오른쪽 빗장밑동맥의 공식 참조 요소입니다. 척추동맥과 연결되는 하부 경부 메쉬가 원본에 없습니다.", "#c98f91", (1.1, -0.35, 0.1)),
    ("left-subclavian", "Left subclavian artery", "Proximal arterial supply", "Left", "FMA4694", "BP9324", ("FJ3479",), "왼쪽 빗장밑동맥의 공식 참조 요소입니다. 척추동맥과 연결되는 하부 경부 메쉬가 원본에 없습니다.", "#d6a4a1", (-1.1, -0.35, 0.1)),
]

# These are display-only guides across source omissions. Endpoints are
# calculated from the nearest vertices of the named source meshes below and
# stored in manifest coordinates; the GLB is never altered to bridge gaps.
GUIDE_PAIRS = [
    ("right-carotid-gap", "right-cca", "right-ica", "Official PART-OF omits the right cervical carotid transition. This dashed line is a schematic orientation guide only."),
    ("left-carotid-gap", "left-cca", "left-ica", "Official PART-OF omits the left cervical carotid transition. This dashed line is a schematic orientation guide only."),
    ("right-vertebral-gap", "right-subclavian", "right-va", "Official PART-OF omits the right lower cervical vertebral artery. This dashed line is a schematic orientation guide only."),
    ("left-vertebral-gap", "left-subclavian", "left-va", "Official PART-OF omits the left lower cervical vertebral artery. This dashed line is a schematic orientation guide only."),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def acquire(cache: Path, name: str, expected_hash: str) -> Path:
    path = cache / name
    if not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        # The execution sandbox sets a deliberately unreachable localhost
        # proxy. Direct HTTPS to the official archive succeeds here; users
        # behind a real proxy can supply the files with --cache-dir.
        opener = build_opener(ProxyHandler({}))
        url = BASE + name
        print(f"Downloading {url}", flush=True)
        temporary = path.with_suffix(path.suffix + ".part")
        try:
            with opener.open(url, timeout=90) as response, temporary.open("wb") as target:
                while chunk := response.read(1024 * 1024):
                    target.write(chunk)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    actual = sha256(path)
    if actual != expected_hash:
        raise ValueError(f"Unexpected SHA-256 for {path}: {actual}")
    return path


def read_tables(parts_path: Path, elements_path: Path):
    parts = {}
    for line in parts_path.read_text(encoding="utf-8-sig").splitlines()[1:]:
        fma, bp, name = line.split("\t")
        parts[fma] = (bp, name)
    elements = defaultdict(list)
    for line in elements_path.read_text(encoding="utf-8-sig").splitlines()[1:]:
        fma, _name, fj = line.split("\t")
        elements[fma].append(fj)
    return parts, elements


def read_obj(archive: zipfile.ZipFile, fj: str):
    filename = f"partof_BP3D_4.0_obj_99/{fj}.obj"
    vertices = []
    faces = []
    header = {}
    with archive.open(filename) as source:
        for raw in source:
            line = raw.decode("ascii").strip()
            if line.startswith("# "):
                match = re.match(r"# (File ID|Concept ID|Representation ID) : (.*)", line)
                if match:
                    header[match.group(1)] = match.group(2).strip()
            elif line.startswith("v "):
                fields = line.split()
                if len(fields) < 4:
                    raise ValueError(f"Invalid vertex in {filename}")
                x, y, z = map(float, fields[1:4])
                if not all(math.isfinite(n) and abs(n) < 10000 for n in (x, y, z)):
                    raise ValueError(f"Non-finite or oversized vertex in {filename}")
                # Official BodyParts3D: mm, Z superior, +X anatomical left,
                # -Y anterior. glTF: m, Y up; this proper rotation leaves
                # anatomical left at -X and anterior at -Z in the viewer.
                vertices.extend((-x * 0.001, z * 0.001, y * 0.001))
            elif line.startswith("f "):
                corners = []
                for field in line.split()[1:]:
                    index = int(field.split("/", 1)[0])
                    index = index - 1 if index > 0 else len(vertices) // 3 + index
                    if index < 0 or index >= len(vertices) // 3:
                        raise ValueError(f"Invalid face index in {filename}")
                    corners.append(index)
                if len(corners) < 3:
                    raise ValueError(f"Incomplete face in {filename}")
                for i in range(1, len(corners) - 1):
                    faces.extend((corners[0], corners[i], corners[i + 1]))
    if header.get("File ID") != fj or not vertices or not faces:
        raise ValueError(f"Incomplete or mismatched OBJ {filename}")
    return vertices, faces, header


def aligned_write(stream: io.BytesIO, payload: bytes):
    offset = stream.tell()
    stream.write(payload)
    stream.write(b"\x00" * ((-stream.tell()) % 4))
    return offset, len(payload)


def packed_array(code: str, values):
    result = array(code, values)
    if sys.byteorder != "little":
        result.byteswap()
    return result.tobytes()


def exported_point(values):
    """Round to the float32 coordinates actually written to the GLB."""
    return tuple(struct.unpack("<f", struct.pack("<f", value))[0] for value in values)


def connection_guides(vertices_by_structure):
    records = []
    for id_, from_id, to_id, description in GUIDE_PAIRS:
        from_vertices = vertices_by_structure[from_id]
        to_vertices = vertices_by_structure[to_id]
        best = (math.inf, None, None)
        for first in from_vertices:
            for second in to_vertices:
                squared = sum((first[i] - second[i]) ** 2 for i in range(3))
                if squared < best[0]:
                    best = (squared, first, second)
        gap_mm = round(math.sqrt(best[0]) * 1000, 2)
        if not 30 < gap_mm < 90:
            raise ValueError(f"Unexpected source gap for {id_}: {gap_mm} mm")
        records.append({
            "id": id_, "from": from_id, "to": to_id,
            "fromPoint": list(best[1]), "toPoint": list(best[2]),
            "gapMm": gap_mm, "kind": "schematic", "description": description,
        })
    return records


def build_specs(parts, elements):
    specs = []
    for id_, name, group, side, fma, bp, fjs, description, color, explode in VESSELS:
        if parts.get(fma) != (bp, name.lower()):
            raise ValueError(f"Official name or ID changed for {fma}")
        members = set(elements[fma])
        for fj in fjs:
            if fj not in members and not (fj == "FJ1723" and id_ == "right-pca") and not (fj == "FJ1723M" and id_ == "left-pca"):
                raise ValueError(f"{fj} is not an official member of {fma}")
        specs.append((id_, name, group, side, fma, bp, fjs, description, color, explode, 1.0))
    for id_, name, fma, bp, color, opacity, explode, description in [
        ("skull", "Skull (reference assembly)", "FMA46565", "BP9486", "#c3d8d0", 0.08, (0.0, 0.0, -1.0), "공식 BodyParts3D 두개골 요소를 합친 참조 모델입니다. CT 마스크가 아닙니다."),
        ("brain", "Brain (reference assembly)", "FMA50801", "BP6687", "#a5afcc", 0.16, (0.0, 0.35, 0.25), "공식 BodyParts3D 뇌 요소를 합친 참조 모델입니다. MRI 분할 마스크가 아닙니다."),
    ]:
        if parts.get(fma) != (bp, id_):
            raise ValueError(f"Official name or ID changed for {fma}")
        fjs = tuple(dict.fromkeys(elements[fma]))
        if len(fjs) != (43 if id_ == "skull" else 59):
            raise ValueError(f"Unexpected {id_} element count")
        specs.append((id_, name, "Reference layers", "Midline", fma, bp, fjs, description, color, explode, opacity))
    seen = set()
    for spec in specs:
        overlap = seen.intersection(spec[6])
        if overlap:
            raise ValueError(f"Atomic meshes assigned to multiple structures: {overlap}")
        seen.update(spec[6])
    return specs


def build_outputs(archive_path: Path, parts_path: Path, elements_path: Path, out_dir: Path):
    parts, elements = read_tables(parts_path, elements_path)
    specs = build_specs(parts, elements)
    binary = io.BytesIO()
    gltf = {
        "asset": {"version": "2.0", "generator": "Splatomy BodyParts3D reference converter"},
        "scene": 0, "scenes": [{"nodes": list(range(len(specs)))}],
        "nodes": [], "meshes": [], "accessors": [], "bufferViews": [], "buffers": [],
    }
    structures = []
    guide_endpoints = {id_ for _, from_id, to_id, _ in GUIDE_PAIRS for id_ in (from_id, to_id)}
    guide_vertices = {}
    with zipfile.ZipFile(archive_path) as archive:
        for spec in specs:
            id_, name, group, side, fma, bp, fjs, description, color, explode, opacity = spec
            positions = []
            indices = []
            atomic = []
            for fj in fjs:
                vertices, faces, header = read_obj(archive, fj)
                base = len(positions) // 3
                positions.extend(vertices)
                indices.extend(base + i for i in faces)
                atomic.append({"fileId": fj, "conceptId": header.get("Concept ID", ""), "representationId": header.get("Representation ID", "")})
            count = len(positions) // 3
            if count > 3_000_000 or len(indices) > 9_000_000:
                raise ValueError(f"{id_} exceeds browser mesh limits")
            if id_ in guide_endpoints:
                guide_vertices[id_] = [exported_point(positions[i:i + 3]) for i in range(0, len(positions), 3)]
            position_offset, position_length = aligned_write(binary, packed_array("f", positions))
            index_offset, index_length = aligned_write(binary, packed_array("I", indices))
            pview = len(gltf["bufferViews"])
            gltf["bufferViews"].append({"buffer": 0, "byteOffset": position_offset, "byteLength": position_length, "target": 34962})
            iview = len(gltf["bufferViews"])
            gltf["bufferViews"].append({"buffer": 0, "byteOffset": index_offset, "byteLength": index_length, "target": 34963})
            paccessor = len(gltf["accessors"])
            gltf["accessors"].append({"bufferView": pview, "componentType": 5126, "count": count, "type": "VEC3", "min": [min(positions[n::3]) for n in range(3)], "max": [max(positions[n::3]) for n in range(3)]})
            iaccessor = len(gltf["accessors"])
            gltf["accessors"].append({"bufferView": iview, "componentType": 5125, "count": len(indices), "type": "SCALAR"})
            gltf["meshes"].append({"name": id_, "primitives": [{"attributes": {"POSITION": paccessor}, "indices": iaccessor, "mode": 4}]})
            gltf["nodes"].append({"name": id_, "mesh": len(gltf["meshes"]) - 1, "extras": {"conceptId": fma, "representationId": bp, "elementFileIds": list(fjs)}})
            structures.append({
                "id": id_, "name": name, "group": group, "side": side,
                "description": description, "color": color, "meshName": id_,
                "explode": list(explode), "defaultVisible": True,
                "defaultOpacity": opacity,
                "atomicElements": atomic,
                "source": f"BodyParts3D 4.0 PART-OF {fma}/{bp}; atomic OBJ: {', '.join(fjs)}" + ("; precommunicating PCA segment FMA50639/BP7712" if id_ == "right-pca" else "; precommunicating PCA segment FMA50640/BP9514" if id_ == "left-pca" else ""),
            })
            print(f"{id_}: {len(fjs)} OBJ, {count:,} vertices, {len(indices)//3:,} triangles", flush=True)
    gltf["buffers"] = [{"byteLength": binary.tell()}]
    json_chunk = json.dumps(gltf, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    json_chunk += b" " * ((-len(json_chunk)) % 4)
    bin_chunk = binary.getvalue()
    total = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    if total >= 50 * 1024 * 1024:
        raise ValueError(f"Unexpectedly large GLB: {total} bytes")
    out_dir.mkdir(parents=True, exist_ok=True)
    glb_path = out_dir / "bodyparts3d.glb"
    with glb_path.open("wb") as stream:
        stream.write(struct.pack("<III", 0x46546C67, 2, total))
        stream.write(struct.pack("<II", len(json_chunk), 0x4E4F534A))
        stream.write(json_chunk)
        stream.write(struct.pack("<II", len(bin_chunk), 0x004E4942))
        stream.write(bin_chunk)
    manifest = {
        "schemaVersion": 2,
        "title": "BodyParts3D 4.0 brain and arterial supply reference",
        "source": SOURCE,
        "license": "CC BY 4.0 International",
        "coordinateSystem": "glTF-Y-up", "units": "m",
        "provenance": f"Official BodyParts3D 4.0 PART-OF 99% reduced OBJ archive {ARCHIVE_URL}; SHA-256 {ARCHIVE_SHA256}. Atomic FJ files selected using the official partof_element_parts.txt and partof_parts_list_e.txt mappings. Ascending aorta and aortic arch are separate official segments; full aorta extending into the abdomen is omitted. The source omits connectors between common and internal carotids (nearest source vertices 62.5–63.4 mm apart) and between subclavian and vertebral arteries (50.2–50.9 mm apart). Four manifest connectionGuides are explicitly schematic display lines between nearest source vertices; the official GLB geometry is unchanged. Coordinates converted from BodyParts3D mm/Z-up (+X anatomical left, -Y anterior) to glTF m/Y-up (-X anatomical left, -Z anterior); atomic elements joined by reference concept; no mirrored or invented anatomy. Adult male CAD atlas reference surfaces, not patient masks or spatially registered to imported TotalSegmentator cases. See ATTRIBUTION.txt.",
        "structures": structures,
        "connectionGuides": connection_guides(guide_vertices),
    }
    json_path = out_dir / "bodyparts3d.json"
    json_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    attribution = (
        CREDIT + ".\n\n"
        "Official license (updated 2025-02-27): " + LICENSE_URL + "\n"
        "License terms: https://creativecommons.org/licenses/by/4.0/\n"
        "Source: BodyParts3D 4.0, 99% polygon-reduced PART-OF Tree OBJ archive:\n"
        + ARCHIVE_URL + "\n"
        + "Source archive SHA-256: " + ARCHIVE_SHA256 + "\n"
        + "Official concept and element tables: " + BASE + "partof_parts_list_e.txt ; " + BASE + "partof_element_parts.txt\n"
        + "Publication: Mitsuhashi et al. (2009), BodyParts3D: 3D structure database for anatomical concepts. https://doi.org/10.1093/nar/gkn613\n\n"
        + "Adaptations: selected named atomic FJ meshes from the 4.0 PART-OF archive, including separate ascending aorta and aortic arch segments and their source-mapped branches; assembled compound skull and brain concepts from the official element table; converted OBJ to one embedded GLB with positions and triangles; converted millimeters/Z-up to meters/Y-up; assigned display colors, opacity and educational groupings. The full aorta, which extends into the abdomen, is omitted to keep the brain legible. Geometry was not mirrored, sculpted or inferred. Individual FMA, BP and FJ IDs are in bodyparts3d.json.\n"
        + "Source coverage: the official PART-OF archive has no matching mesh for the visible bilateral gaps between common and internal carotid arteries (nearest vertices 62.5-63.4 mm apart) or between subclavian and vertebral arteries (50.2-50.9 mm apart). Other nearby named arteries do not connect these trunks. The four connectionGuides records in bodyparts3d.json are explicitly schematic display guides between nearest source vertices; they add no geometry to the official GLB.\n"
        + "The source is an adult male CAD anatomical reference, not a scan-derived patient brain mask and not spatially registered to any imported TotalSegmentator case. It is for anatomy education and is not a diagnostic device.\n"
    )
    attr_path = out_dir / "ATTRIBUTION.txt"
    attr_path.write_text(attribution, encoding="utf-8")
    for path in (glb_path, json_path, attr_path):
        print(f"{path}: {path.stat().st_size:,} bytes, SHA-256 {sha256(path)}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=Path("private-assets/bodyparts3d"))
    parser.add_argument("--output-dir", type=Path, default=Path("public/reference"))
    args = parser.parse_args()
    archive = acquire(args.cache_dir, ARCHIVE_NAME, ARCHIVE_SHA256)
    table_paths = {name: acquire(args.cache_dir, name, digest) for name, digest in TABLES.items()}
    build_outputs(archive, table_paths["partof_parts_list_e.txt"], table_paths["partof_element_parts.txt"], args.output_dir)


if __name__ == "__main__":
    main()
