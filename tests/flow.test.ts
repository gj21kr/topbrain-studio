import test from 'node:test';
import assert from 'node:assert/strict';
import {
  beatPeriodMs,
  EXAMPLE_PRESSURE_DRAFT,
  normalizedPressureAtPhase,
  pressureAtPhase,
  validatePressureDraft,
} from '../src/flow.ts';

test('example inputs produce a period and a bounded illustrative pressure interpolation', () => {
  const parsed = validatePressureDraft(EXAMPLE_PRESSURE_DRAFT);
  assert.equal(parsed.valid, true);
  if (!parsed.valid) return;
  assert.equal(beatPeriodMs(parsed.values.heartRate), 60_000 / 72);
  assert.equal(pressureAtPhase(parsed.values, 0), 80);
  assert.equal(pressureAtPhase(parsed.values, 0.18), 120);
  for (let index = 0; index < 100; index++) {
    const pressure = pressureAtPhase(parsed.values, index / 100);
    assert.ok(pressure >= 80 && pressure <= 120);
  }
});

test('phase wraps once per beat and the normalized curve is independent of entered pressures', () => {
  assert.equal(normalizedPressureAtPhase(0), 0);
  assert.equal(normalizedPressureAtPhase(0.18), 1);
  assert.ok(Math.abs(normalizedPressureAtPhase(0.4) - normalizedPressureAtPhase(1.4)) < 1e-12);
  assert.ok(Math.abs(normalizedPressureAtPhase(-0.6) - normalizedPressureAtPhase(0.4)) < 1e-12);
});

test('incomplete, out-of-range, and reversed pressure inputs are rejected', () => {
  assert.equal(validatePressureDraft({ systolic: '', diastolic: '80', heartRate: '72' }).valid, false);
  assert.equal(validatePressureDraft({ systolic: '1e2', diastolic: '80', heartRate: '72' }).valid, false);
  assert.equal(validatePressureDraft({ systolic: '120.5', diastolic: '80', heartRate: '72' }).valid, false);
  assert.equal(validatePressureDraft({ systolic: '120', diastolic: '130', heartRate: '72' }).valid, false);
  assert.equal(validatePressureDraft({ systolic: '301', diastolic: '80', heartRate: '72' }).valid, false);
  assert.equal(validatePressureDraft({ systolic: '120', diastolic: '80', heartRate: '0' }).valid, false);
  assert.throws(() => beatPeriodMs(0), RangeError);
  assert.throws(() => normalizedPressureAtPhase(Number.NaN), RangeError);
});
