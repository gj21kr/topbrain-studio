export type Vec3 = [number, number, number];
export interface Structure { id: string; name: string; label?: number; group: string; side: string; description: string; color: string; meshName: string; path?: Vec3[]; radius?: number; explode: Vec3; source?: string; defaultVisible?: boolean; defaultOpacity?: number }
export interface Manifest { schemaVersion: 1 | 2; title: string; source: string; license: string; coordinateSystem: 'glTF-Y-up'; units: 'm'; provenance: string; structures: Structure[] }
const segment = (id: string, name: string, group: string, side: string, description: string, color: string, path: Vec3[], radius: number, explode: Vec3): Structure => ({ id, name, group, side, description, color, path: path.map(([x,y,z]) => [-x,y,-z]), radius, explode: [-explode[0],explode[1],-explode[2]], meshName: id });
export const demo: Manifest = {
  schemaVersion: 1, title: 'Cerebral circulation', source: 'Procedural teaching schematic', license: 'Local illustrative sample', coordinateSystem: 'glTF-Y-up', units: 'm', provenance: 'Conceptual vessel paths. Not derived from TopBrain, not anatomically validated and not to scale.',
  structures: [
    segment('left-ica', 'Left internal carotid artery', 'Anterior circulation', 'Left', '앞순환을 살펴보는 시작점입니다. 실제 혈관의 주행·직경·변이는 TopBrain 실데이터를 연결한 뒤 확인해야 합니다.', '#ed8878', [[.58,-2.5,.32],[.62,-1.6,.32],[.65,-.6,.12],[.52,-.05,.36],[.7,.28,.48],[.58,.53,.14]], .115, [.8,0,.1]),
    segment('right-ica', 'Right internal carotid artery', 'Anterior circulation', 'Right', '좌우 구조를 선택해 화면에서 비교해 보세요. 현재 좌우 형태는 설명을 위한 대칭 모식도입니다.', '#efa291', [[-.58,-2.5,.32],[-.62,-1.6,.32],[-.65,-.6,.12],[-.52,-.05,.36],[-.7,.28,.48],[-.58,.53,.14]], .115, [-.8,0,.1]),
    segment('left-mca', 'Left middle cerebral artery', 'Anterior circulation', 'Left', '앞순환의 외측 분지를 선택하고 단독 보기로 주변 구조와 구분해 보세요. 임상적 영역은 이 모식도로 판단하지 않습니다.', '#edbd8b', [[.58,.53,.14],[1.05,.65,.16],[1.42,1,.12],[1.6,1.5,.1]], .09, [1,.35,.15]),
    segment('right-mca', 'Right middle cerebral artery', 'Anterior circulation', 'Right', '반대쪽 같은 이름의 구조와 위치 관계를 비교하는 학습 예시입니다.', '#edbd8b', [[-.58,.53,.14],[-1.05,.65,.16],[-1.42,1,.12],[-1.6,1.5,.1]], .09, [-1,.35,.15]),
    segment('left-aca', 'Left anterior cerebral artery', 'Anterior circulation', 'Left', '정중선 가까이 놓인 앞순환 분지의 개념적 위치입니다. 분해 모드에서는 원래의 공간 관계가 바뀝니다.', '#ef9275', [[.58,.53,.14],[.25,.7,.4],[.18,1.3,.6],[.2,1.85,.24],[.24,2.1,-.35]], .07, [.2,.75,.6]),
    segment('right-aca', 'Right anterior cerebral artery', 'Anterior circulation', 'Right', '분해 슬라이더를 0으로 되돌리면 예시 모델의 원래 위치로 돌아갑니다.', '#ef9275', [[-.58,.53,.14],[-.25,.7,.4],[-.18,1.3,.6],[-.2,1.85,.24],[-.24,2.1,-.35]], .07, [-.2,.75,.6]),
    segment('left-va', 'Left vertebral artery', 'Posterior circulation', 'Left', '뒤순환을 따라가는 학습 시작점입니다. 목 부분의 경로는 실제 데이터가 아닌 단순화된 예시입니다.', '#83b8d2', [[.36,-2.5,-.35],[.5,-1.7,-.48],[.42,-1,-.6],[.18,-.55,-.56],[0,-.25,-.55]], .078, [.6,-.2,-.8]),
    segment('right-va', 'Right vertebral artery', 'Posterior circulation', 'Right', '두 경로가 중앙에서 만나는 모습을 회전해 확인해 보세요.', '#83b8d2', [[-.36,-2.5,-.35],[-.5,-1.7,-.48],[-.42,-1,-.6],[-.18,-.55,-.56],[0,-.25,-.55]], .078, [-.6,-.2,-.8]),
    segment('basilar', 'Basilar artery', 'Posterior circulation', 'Midline', '뒤순환의 중앙 경로를 보여주는 모식도입니다. 실데이터의 구조 이름은 가져온 라벨 매핑으로 확인합니다.', '#9ed6d2', [[0,-.25,-.55],[0,.05,-.62],[0,.4,-.55],[0,.65,-.48]], .105, [0,.2,-1]),
    segment('left-pca', 'Left posterior cerebral artery', 'Posterior circulation', 'Left', '뒤쪽으로 향하는 분지의 예시입니다. 회전·단독 보기로 다른 경로와 분리해 살펴보세요.', '#91c8bd', [[0,.65,-.48],[.35,.7,-.5],[.72,.6,-.75],[.95,.88,-1.05]], .075, [.8,.5,-.7]),
    segment('right-pca', 'Right posterior cerebral artery', 'Posterior circulation', 'Right', '반대쪽 뒤순환 분지를 비교하는 예시입니다. 좌우 대칭은 실제 환자의 해부학을 의미하지 않습니다.', '#91c8bd', [[0,.65,-.48],[-.35,.7,-.5],[-.72,.6,-.75],[-.95,.88,-1.05]], .075, [-.8,.5,-.7]),
    segment('acom', 'Anterior communicating artery', 'Connections', 'Midline', '두 앞쪽 경로의 연결을 개념적으로 보여줍니다. TopBrain 실제 라벨의 존재 여부는 개별 데이터에서 확인해야 합니다.', '#d6b4e0', [[-.23,.77,.42],[0,.8,.45],[.23,.77,.42]], .05, [0,1,.9]),
  ]
};

export function validateManifest(value: unknown): Manifest {
  const object = (x: unknown): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x);
  const text = (x: unknown, limit = 2000): x is string => typeof x === 'string' && x.trim().length > 0 && x.length <= limit;
  const vector = (x: unknown): x is Vec3 => Array.isArray(x) && x.length === 3 && x.every(n => typeof n === 'number' && Number.isFinite(n) && Math.abs(n) <= 10);
  if (!object(value) || ![1, 2].includes(Number(value.schemaVersion)) || typeof value.schemaVersion !== 'number' || value.coordinateSystem !== 'glTF-Y-up' || value.units !== 'm') throw new Error('Manifest requires schemaVersion 1 or 2, units m, and coordinateSystem glTF-Y-up.');
  for (const key of ['title', 'source', 'license', 'provenance']) if (!text(value[key])) throw new Error(`Missing or invalid ${key}.`);
  if (!Array.isArray(value.structures) || value.structures.length < 1 || value.structures.length > 500) throw new Error('Expected 1–500 structures.');
  const ids = new Set<string>(), names = new Set<string>();
  for (const s of value.structures) {
    if (!object(s)) throw new Error('Invalid structure.');
    for (const key of ['id', 'name', 'group', 'side', 'description', 'meshName']) if (!text(s[key])) throw new Error(`Structure requires ${key}.`);
    if (!/^[a-zA-Z0-9_.-]+$/.test(s.id as string) || ids.has(s.id as string) || names.has(s.meshName as string)) throw new Error('Structure IDs and mesh names must be unique.');
    if (!text(s.color) || !/^#[0-9a-f]{6}$/i.test(s.color) || !vector(s.explode)) throw new Error('Invalid structure color or explode vector.');
    if (s.label !== undefined && (!Number.isSafeInteger(s.label) || Number(s.label) <= 0)) throw new Error('Invalid label ID.');
    if (s.source !== undefined && !text(s.source)) throw new Error('Invalid structure source.');
    // Schema 2 is a combined export. App.tsx renders `s.source ?? manifest.source`,
    // so a structure without its own source would be shown under the TopBrain
    // attribution the combined manifest source leads with.
    if (value.schemaVersion === 2 && s.source === undefined) throw new Error('Schema 2 requires an explicit source on every structure.');
    if (s.defaultVisible !== undefined && typeof s.defaultVisible !== 'boolean') throw new Error('Invalid defaultVisible.');
    if (s.defaultOpacity !== undefined && (typeof s.defaultOpacity !== 'number' || !Number.isFinite(s.defaultOpacity) || s.defaultOpacity < 0 || s.defaultOpacity > 1)) throw new Error('Invalid defaultOpacity: expected 0–1.');
    ids.add(s.id as string); names.add(s.meshName as string);
  }
  return value as unknown as Manifest;
}

export function initialDisplay(structures: Structure[]) {
  return {
    hidden: new Set(structures.filter(s => s.defaultVisible === false).map(s => s.id)),
    opacities: new Map(structures.map(s => [s.id, s.defaultOpacity ?? 1])),
    selected: (structures.find(s => s.defaultVisible !== false) ?? structures[0]).id,
  };
}

export function structureOpacity(structure: Structure, opacities: Map<string, number>, selected: boolean, surroundingOpacity: number): number {
  return (opacities.get(structure.id) ?? structure.defaultOpacity ?? 1) * (selected ? 1 : surroundingOpacity);
}

export function inspectGlb(buffer: ArrayBuffer): void {
  if (buffer.byteLength > 150 * 1024 * 1024) throw new Error('Model exceeds the 150 MB browser import limit.');
  if (buffer.byteLength < 20) throw new Error('Invalid GLB header.');
  const view = new DataView(buffer);
  if (view.getUint32(0, true) !== 0x46546c67 || view.getUint32(4, true) !== 2 || view.getUint32(8, true) !== buffer.byteLength) throw new Error('Expected a valid GLB 2.0 file.');
  const length = view.getUint32(12, true);
  if (view.getUint32(16, true) !== 0x4e4f534a || length % 4 || 20 + length > buffer.byteLength) throw new Error('Invalid GLB JSON chunk.');
  const json = JSON.parse(new TextDecoder().decode(buffer.slice(20, 20 + length)));
  const inspect = (value: unknown): void => {
    if (Array.isArray(value)) value.forEach(inspect);
    else if (value && typeof value === 'object') for (const [key, entry] of Object.entries(value)) {
      if (key === 'uri') throw new Error('External or data URI resources are not accepted. Use a fully embedded GLB.');
      inspect(entry);
    }
  };
  inspect(json);
  if (json.extensionsUsed?.length || json.extensionsRequired?.length || json.animations?.length || json.skins?.length) throw new Error('Export a static, uncompressed GLB without extensions, skins or animations.');
}

export function explosionOffset(vector: Vec3, amount: number, scale = 1): Vec3 {
  const bounded = Math.max(0, Math.min(1, Number.isFinite(amount) ? amount : 0));
  return vector.map(n => n * bounded * scale) as Vec3;
}

export function validateMeshData(positions: { array: ArrayLike<number>; count: number; itemSize: number }, index: { array: ArrayLike<number>; count: number } | null): void {
  if (positions.itemSize !== 3 || !Number.isSafeInteger(positions.count) || positions.count < 3 || positions.count > 3_000_000 || positions.array.length !== positions.count * 3) throw new Error('Invalid or oversized mesh positions.');
  for (let i = 0; i < positions.array.length; i++) if (!Number.isFinite(positions.array[i])) throw new Error('Mesh geometry contains non-finite coordinates.');
  const count = index ? index.count : positions.count;
  if (!Number.isSafeInteger(count) || count < 3 || count % 3 || count > 9_000_000) throw new Error('Expected complete triangle geometry.');
  if (index) {
    if (index.array.length !== index.count) throw new Error('Invalid index buffer length.');
    for (let i = 0; i < index.array.length; i++) if (!Number.isSafeInteger(index.array[i]) || index.array[i] < 0 || index.array[i] >= positions.count) throw new Error('Mesh index is outside the vertex buffer.');
  }
}
