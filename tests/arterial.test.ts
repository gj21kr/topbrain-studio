import test from 'node:test';
import assert from 'node:assert/strict';
import { isArterialStructure } from '../src/arterial.ts';

test('TopBrain artery group pulses abbreviated labels while vein and reference groups do not', () => {
  for (const name of ['BA', 'R-ICA', 'L-PCA']) {
    assert.equal(isArterialStructure({ group: 'Arteries', name }), true, name);
  }
  assert.equal(isArterialStructure({ group: 'Veins and sinuses', name: 'SSS' }), false);
  assert.equal(isArterialStructure({ group: 'Veins and sinuses', name: 'Carotid artery' }), false);
  assert.equal(isArterialStructure({ group: 'Reference layers', name: 'Ascending aorta' }), false);
  assert.equal(isArterialStructure({ group: 'Anterior circulation', name: 'ACA' }), true);
});
