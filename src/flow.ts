/** Values entered for an educational pressure and pulse preview. */
export interface PressureInputs {
  systolic: number;
  diastolic: number;
  heartRate: number;
}

export interface PressurePreview extends PressureInputs {
  periodMs: number;
}

export interface PressureDraft {
  systolic: string;
  diastolic: string;
  heartRate: string;
}

export type PressureField = keyof PressureDraft;
export type PressureErrors = Partial<Record<PressureField, string>>;

/** Bounds keep this browser visualization usable; they are not clinical categories. */
export const PRESSURE_INPUT_LIMITS = {
  systolic: { min: 50, max: 300 },
  diastolic: { min: 20, max: 250 },
  heartRate: { min: 20, max: 240 },
} as const;

export const EXAMPLE_PRESSURE_DRAFT: PressureDraft = {
  systolic: '120',
  diastolic: '80',
  heartRate: '72',
};

export type PressureValidation =
  | { valid: true; values: PressureInputs; errors: PressureErrors }
  | { valid: false; values: null; errors: PressureErrors };

/** Parse whole-number inputs without silently rounding or accepting exponent notation. */
export function validatePressureDraft(draft: PressureDraft): PressureValidation {
  const errors: PressureErrors = {};
  const parsed: Partial<PressureInputs> = {};
  const labels: Record<PressureField, string> = {
    systolic: '수축기 혈압',
    diastolic: '이완기 혈압',
    heartRate: '맥박',
  };

  for (const field of ['systolic', 'diastolic', 'heartRate'] as const) {
    const raw = draft[field].trim();
    const { min, max } = PRESSURE_INPUT_LIMITS[field];
    const value = /^\d+$/.test(raw) ? Number(raw) : NaN;
    if (!Number.isSafeInteger(value) || value < min || value > max) {
      errors[field] = `${labels[field]}: 시각화 입력 범위 ${min}–${max}의 정수를 입력해 주세요.`;
      continue;
    }
    parsed[field] = value;
  }

  if (parsed.systolic !== undefined && parsed.diastolic !== undefined && parsed.systolic <= parsed.diastolic) {
    errors.diastolic = '이완기 혈압은 수축기 혈압보다 작아야 합니다.';
  }

  if (Object.keys(errors).length > 0) return { valid: false, values: null, errors };
  return { valid: true, values: parsed as PressureInputs, errors };
}

/** Duration of one beat, derived only from beats per minute. */
export function beatPeriodMs(heartRate: number): number {
  if (!Number.isFinite(heartRate) || heartRate <= 0) throw new RangeError('Heart rate must be positive and finite.');
  return 60_000 / heartRate;
}

function smoothstep(value: number): number {
  return value * value * (3 - 2 * value);
}

/**
 * An arbitrary 0..1 rise and fall for one beat. This is an illustration, not
 * a measured arterial pressure waveform or a cerebral flow calculation.
 */
export function normalizedPressureAtPhase(phase: number): number {
  if (!Number.isFinite(phase)) throw new RangeError('Phase must be finite.');
  const cycle = ((phase % 1) + 1) % 1;
  const peakPhase = 0.18;
  if (cycle <= peakPhase) return smoothstep(cycle / peakPhase);
  return smoothstep((1 - cycle) / (1 - peakPhase));
}

/** Interpolate only between the entered diastolic and systolic pressure. */
export function pressureAtPhase(inputs: PressureInputs, phase: number): number {
  return inputs.diastolic + (inputs.systolic - inputs.diastolic) * normalizedPressureAtPhase(phase);
}
