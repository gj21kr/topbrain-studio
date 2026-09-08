import test from 'node:test';
import assert from 'node:assert/strict';
import { demo, validateManifest, inspectGlb, explosionOffset, validateMeshData } from '../src/model.ts';
function glb(json: unknown) { const raw = new TextEncoder().encode(JSON.stringify(json)), length = Math.ceil(raw.length / 4) * 4; const buffer = new ArrayBuffer(20 + length), view = new DataView(buffer); view.setUint32(0,0x46546c67,true);view.setUint32(4,2,true);view.setUint32(8,buffer.byteLength,true);view.setUint32(12,length,true);view.setUint32(16,0x4e4f534a,true);new Uint8Array(buffer,20).fill(32);new Uint8Array(buffer,20).set(raw);return buffer; }
test('validates provenance, unique IDs, coordinate units and finite vectors', () => {
  assert.equal(validateManifest(demo).structures.length, 12);
  assert.throws(() => validateManifest({ ...demo, provenance: '' }), /provenance/);
  assert.throws(() => validateManifest({ ...demo, structures: [demo.structures[0], demo.structures[0]] }), /unique/);
  assert.throws(() => validateManifest({ ...demo, structures: [{ ...demo.structures[0], explode: [Infinity,0,0] }] }), /vector/);
  assert.throws(() => validateManifest({ ...demo, units: 'mm' }), /units/);
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
