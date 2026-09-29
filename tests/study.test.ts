import test from 'node:test';
import assert from 'node:assert/strict';
import { demo } from '../src/model.ts';
import { demoTrails } from '../src/study.ts';

test('three short schematic trails point only to demo structures', () => {
  const knownIds = new Set(demo.structures.map(structure => structure.id));
  assert.equal(demoTrails.length, 3);
  for (const trail of demoTrails) {
    assert.ok(trail.steps.length >= 2 && trail.steps.length <= 4, `${trail.id} is a short trail`);
    assert.match(trail.summary, /모식도/);
    for (const step of trail.steps) {
      assert.ok(knownIds.has(step.structureId), `${trail.id} targets a known demo structure: ${step.structureId}`);
      assert.ok(step.title.trim() && step.instruction.trim(), `${trail.id} has usable study copy`);
    }
  }
});

test('trail IDs and selected structures do not repeat', () => {
  const trailIds = demoTrails.map(trail => trail.id);
  const stepIds = demoTrails.flatMap(trail => trail.steps.map(step => step.structureId));
  assert.equal(new Set(trailIds).size, trailIds.length);
  assert.equal(new Set(stepIds).size, stepIds.length);
});
