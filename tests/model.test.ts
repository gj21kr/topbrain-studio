import test from 'node:test';
import assert from 'node:assert/strict';
import { demo, validateManifest, inspectGlb, explosionOffset, validateMeshData, initialDisplay, structureOpacity } from '../src/model.ts';
function glb(json: unknown) { const raw = new TextEncoder().encode(JSON.stringify(json)), length = Math.ceil(raw.length / 4) * 4; const buffer = new ArrayBuffer(20 + length), view = new DataView(buffer); view.setUint32(0,0x46546c67,true);view.setUint32(4,2,true);view.setUint32(8,buffer.byteLength,true);view.setUint32(12,length,true);view.setUint32(16,0x4e4f534a,true);new Uint8Array(buffer,20).fill(32);new Uint8Array(buffer,20).set(raw);return buffer; }
test('validates provenance, unique IDs, coordinate units and finite vectors', () => {
  assert.equal(validateManifest(demo).structures.length, 12);
  assert.throws(() => validateManifest({ ...demo, provenance: '' }), /provenance/);
  assert.throws(() => validateManifest({ ...demo, structures: [demo.structures[0], demo.structures[0]] }), /unique/);
  assert.throws(() => validateManifest({ ...demo, structures: [{ ...demo.structures[0], explode: [Infinity,0,0] }] }), /vector/);
  assert.throws(() => validateManifest({ ...demo, units: 'mm' }), /units/);
});
function glbWithBin(json: unknown, binary: Uint8Array, opts: { type?: number; declared?: number; trailing?: number } = {}) {
  const raw = new TextEncoder().encode(JSON.stringify(json)), jsonLen = Math.ceil(raw.length / 4) * 4;
  const total = 20 + jsonLen + 8 + binary.length + (opts.trailing ?? 0);
  const buffer = new ArrayBuffer(total), view = new DataView(buffer);
  view.setUint32(0, 0x46546c67, true); view.setUint32(4, 2, true); view.setUint32(8, total, true);
  view.setUint32(12, jsonLen, true); view.setUint32(16, 0x4e4f534a, true);
  new Uint8Array(buffer, 20, jsonLen).fill(32); new Uint8Array(buffer, 20).set(raw);
  view.setUint32(20 + jsonLen, opts.declared ?? binary.length, true);
  view.setUint32(24 + jsonLen, opts.type ?? 0x004e4942, true);
  new Uint8Array(buffer, 28 + jsonLen, binary.length).set(binary);
  return buffer;
}
test('rejects a binary chunk that does not tile the file', () => {
  const asset = { asset: { version: '2.0' } }, body = new Uint8Array(16);
  assert.doesNotThrow(() => inspectGlb(glbWithBin(asset, body)));
  assert.doesNotThrow(() => inspectGlb(glb(asset)), 'a GLB with no binary chunk stays valid');
  assert.throws(() => inspectGlb(glbWithBin(asset, body, { type: 0x4e4f534a })), /binary chunk/);
  assert.throws(() => inspectGlb(glbWithBin(asset, body, { declared: 13 })), /binary chunk/);
  assert.throws(() => inspectGlb(glbWithBin(asset, body, { declared: 1024 })), /binary chunk/);
  assert.throws(() => inspectGlb(glbWithBin(asset, body, { trailing: 4 })), /binary chunk/);
  const valid = glbWithBin(asset, body), cut = valid.slice(0, valid.byteLength - 20);
  new DataView(cut).setUint32(8, cut.byteLength, true);
  assert.throws(() => inspectGlb(cut), /binary chunk/, 'a truncated chunk header is not a whole chunk');
});
test('blocks remote and data resources before loader requests', () => {
  for (const uri of ['https://example.com/scan.bin','../private.bin','data:application/octet-stream;base64,AA==']) assert.throws(() => inspectGlb(glb({ asset: { version: '2.0' }, buffers: [{ uri }] })), /URI/);
  assert.throws(() => inspectGlb(glb({ extensionsUsed: ['KHR_draco_mesh_compression'] })), /extensions/);
  assert.throws(() => inspectGlb(new ArrayBuffer(3)), /header/);
  assert.doesNotThrow(() => inspectGlb(glb({ asset: { version: '2.0' } })));
});
test('explosion is reversible bounded and deterministic', () => {
  assert.deepEqual(explosionOffset([1,-2,3],0),[0,-0,0]);
  assert.deepEqual(explosionOffset([1,-2,3],.5,2),[1,-2,3]);
  assert.deepEqual(explosionOffset([1,2,3],4),[1,2,3]);
  assert.deepEqual(explosionOffset([1,2,3],NaN),[0,0,0]);
});
test('rejects indices outside the vertex buffer and incomplete triangles', () => {
  const positions = { array: new Float32Array([0,0,0,1,0,0,0,1,0]), count: 3, itemSize: 3 };
  assert.doesNotThrow(() => validateMeshData(positions, { array: new Uint16Array([0,1,2]), count: 3 }));
  assert.throws(() => validateMeshData(positions, { array: new Uint16Array([0,1,65535]), count: 3 }), /outside/);
  assert.throws(() => validateMeshData(positions, { array: new Uint16Array([0,1]), count: 2 }), /triangle/);
});
test('schematic laterality follows the same RAS to glTF convention as real data', () => {
  assert.ok(demo.structures.find(s => s.id === 'left-ica')!.path!.every(p => p[0] < 0));
  assert.ok(demo.structures.find(s => s.id === 'right-ica')!.path!.every(p => p[0] > 0));
  assert.ok(demo.structures.find(s => s.id === 'basilar')!.path!.every(p => p[2] > 0));
});

test('accepts legacy manifests and version 2 per-structure provenance and defaults', () => {
  const anatomy = { ...demo.structures[0], source: 'TotalSegmentator', defaultVisible: false, defaultOpacity: .2 };
  assert.equal(validateManifest(demo).schemaVersion, 1);
  const manifest = validateManifest({ ...demo, schemaVersion: 2, structures: [anatomy] });
  assert.equal(manifest.structures[0].source, 'TotalSegmentator');
  assert.equal(manifest.structures[0].defaultOpacity, .2);
  for (const schemaVersion of [0, 3, '1', '2']) assert.throws(() => validateManifest({ ...demo, schemaVersion }), /schemaVersion/);
});

test('schema 2 requires every structure to name its own source', () => {
  const anatomy = { ...demo.structures[0], source: 'TotalSegmentator' }, vessel = { ...demo.structures[1], source: 'TopBrain' };
  assert.equal(validateManifest({ ...demo, schemaVersion: 2, structures: [anatomy, vessel] }).structures.length, 2);
  // Without one the viewer shows the manifest source, attributing a
  // TotalSegmentator prediction to TopBrain.
  assert.throws(() => validateManifest({ ...demo, schemaVersion: 2 }), /source on every structure/);
  assert.throws(() => validateManifest({ ...demo, schemaVersion: 2, structures: [anatomy, demo.structures[1]] }), /source on every structure/);
  // Schema 1 vessel assets carry no per-structure source and stay valid.
  assert.doesNotThrow(() => validateManifest(demo));
});

test('rejects malformed source and display defaults without coercing values', () => {
  for (const source of ['', ' ', 2]) assert.throws(() => validateManifest({ ...demo, structures: [{ ...demo.structures[0], source }] }), /source/);
  for (const defaultVisible of ['false', 0, null]) assert.throws(() => validateManifest({ ...demo, structures: [{ ...demo.structures[0], defaultVisible }] }), /defaultVisible/);
  for (const defaultOpacity of [-.1, 1.1, Infinity, NaN, '.2', null]) assert.throws(() => validateManifest({ ...demo, structures: [{ ...demo.structures[0], defaultOpacity }] }), /defaultOpacity/);
  for (const defaultOpacity of [0, 1]) assert.doesNotThrow(() => validateManifest({ ...demo, structures: [{ ...demo.structures[0], defaultOpacity }] }));
});

test('reset restores hidden anatomy and opacity defaults without mutating the manifest', () => {
  const anatomy = { ...demo.structures[0], id: 'brain', defaultVisible: false, defaultOpacity: .2 };
  const vessel = { ...demo.structures[1] };
  const structures = [anatomy, vessel];
  const display = initialDisplay(structures);
  assert.equal(display.selected, vessel.id);
  assert.deepEqual([...display.hidden], ['brain']);
  assert.equal(display.opacities.get(vessel.id), 1);
  display.hidden.clear(); display.opacities.set('brain', 1);
  const reset = initialDisplay(structures);
  assert.deepEqual([...reset.hidden], ['brain']);
  assert.equal(reset.opacities.get('brain'), .2);
  assert.equal(anatomy.defaultOpacity, .2);
  assert.equal(initialDisplay([anatomy]).selected, 'brain');
});

test('selection preserves translucent anatomy and individual opacity overrides', () => {
  const anatomy = { ...demo.structures[0], defaultOpacity: .2 };
  assert.equal(structureOpacity(anatomy, new Map(), true, .85), .2);
  assert.equal(structureOpacity(anatomy, new Map(), false, .5), .1);
  assert.equal(structureOpacity(anatomy, new Map([[anatomy.id, .65]]), true, .85), .65);
  assert.equal(structureOpacity(anatomy, new Map([[anatomy.id, 0]]), true, .85), 0);
  assert.equal(structureOpacity(demo.structures[1], new Map(), false, .85), .85);
});
