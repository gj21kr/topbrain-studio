import { useEffect, useMemo, useRef, useState } from 'react';
import {
  beatPeriodMs,
  EXAMPLE_PRESSURE_DRAFT,
  normalizedPressureAtPhase,
  PRESSURE_INPUT_LIMITS,
  validatePressureDraft,
  type PressureDraft,
  type PressureField,
  type PressurePreview,
} from './flow';

export interface FlowPanelProps {
  enabled: boolean;
  phaseOriginMs: number;
  onToggle: (enabled: boolean) => void;
  /** Called with null while any field is invalid; component makes no network or storage writes. */
  onChange?: (preview: PressurePreview | null) => void;
}

const fields: { name: PressureField; label: string; unit: string }[] = [
  { name: 'systolic', label: '수축기 혈압', unit: 'mmHg' },
  { name: 'diastolic', label: '이완기 혈압', unit: 'mmHg' },
  { name: 'heartRate', label: '맥박', unit: 'bpm' },
];

const plotX = (phase: number) => 12 + phase * 296;
const plotY = (phase: number) => 74 - normalizedPressureAtPhase(phase) * 52;
const plotPath = Array.from({ length: 101 }, (_, index) => {
  const phase = index / 100;
  return `${index ? 'L' : 'M'}${plotX(phase).toFixed(2)} ${plotY(phase).toFixed(2)}`;
}).join(' ');

export default function FlowPanel({ enabled, phaseOriginMs, onToggle, onChange }: FlowPanelProps) {
  const [draft, setDraft] = useState<PressureDraft>(EXAMPLE_PRESSURE_DRAFT);
  const [reduceMotion, setReduceMotion] = useState(false);
  const lastNotified = useRef<string | undefined>(undefined);
  const marker = useRef<SVGCircleElement>(null);
  const validation = useMemo(() => validatePressureDraft(draft), [draft]);
  const inputs = validation.valid ? validation.values : null;
  const periodMs = inputs ? beatPeriodMs(inputs.heartRate) : null;

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduceMotion(query.matches);
    update();
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    const key = inputs ? `${inputs.systolic}/${inputs.diastolic}/${inputs.heartRate}` : 'invalid';
    if (key === lastNotified.current) return;
    lastNotified.current = key;
    onChange?.(inputs ? { ...inputs, periodMs: beatPeriodMs(inputs.heartRate) } : null);
  }, [inputs, onChange]);

  useEffect(() => {
    if (!enabled || !inputs || reduceMotion) return;
    let frame = 0;
    const period = beatPeriodMs(inputs.heartRate);
    const tick = (now: number) => {
      const phase = (Math.max(0, now - phaseOriginMs) / period) % 1;
      marker.current?.setAttribute('cx', String(plotX(phase)));
      marker.current?.setAttribute('cy', String(plotY(phase)));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [enabled, inputs, reduceMotion, phaseOriginMs]);

  const updateField = (field: PressureField, value: string) => setDraft(old => ({ ...old, [field]: value }));

  return <section className="flow-panel" aria-labelledby="flow-panel-title">
    <div className="flow-panel-header">
      <div><span className="flow-panel-eyebrow">PULSE PREVIEW</span><h3 id="flow-panel-title">혈압·맥박 시각화</h3></div>
      <label className="flow-panel-toggle"><input type="checkbox" checked={enabled} disabled={!validation.valid && !enabled} onChange={event => onToggle(event.target.checked)}/><span>혈관 박동 표시</span></label>
    </div>
    <p className="flow-panel-example">입력 예시: 120/80 mmHg, 72 bpm</p>
    <div className="flow-panel-inputs">{fields.map(({ name, label, unit }) => {
      const error = validation.errors[name];
      const limits = PRESSURE_INPUT_LIMITS[name];
      return <div className="flow-panel-field" key={name}>
        <label htmlFor={`flow-${name}`}>{label} <small>({unit})</small></label>
        <input id={`flow-${name}`} type="number" inputMode="numeric" step="1" min={limits.min} max={limits.max} value={draft[name]} onChange={event => updateField(name, event.target.value)} aria-invalid={Boolean(error)} aria-describedby={error ? `flow-${name}-error` : undefined}/>
        {error && <small className="flow-panel-error" id={`flow-${name}-error`}>{error}</small>}
      </div>;
    })}</div>
    <div className="flow-panel-stats" aria-live="polite">
      <span>박동 주기 <strong>{periodMs === null ? '—' : `${Math.round(periodMs)} ms`}</strong></span>
      <span>표시 압력 범위 <strong>{inputs ? `${inputs.diastolic}–${inputs.systolic} mmHg` : '—'}</strong></span>
    </div>
    <figure className="flow-panel-figure">
      <svg viewBox="0 0 320 92" preserveAspectRatio="none" aria-hidden="true" focusable="false">
        <line className="flow-panel-guide" x1="12" x2="308" y1="22" y2="22"/>
        <line className="flow-panel-guide" x1="12" x2="308" y1="74" y2="74"/>
        {inputs && <path className="flow-panel-curve" d={plotPath} fill="none"/>}
        {inputs && enabled && !reduceMotion && <circle ref={marker} className="flow-panel-marker" cx="12" cy="74" r="4"/>}
      </svg>
      <figcaption>입력값 사이의 예시 보간 곡선 · 측정 파형이 아닙니다.</figcaption>
    </figure>
    <p className="flow-panel-note">맥박은 반복 주기를, 혈압은 표시 압력 범위와 혈관 박동의 색 대비를 정합니다. 실제 뇌혈류의 속도·유량·관류는 이 입력만으로 알 수 없습니다. 입력값은 이 화면에서만 사용하며 저장하거나 전송하지 않습니다.</p>
  </section>;
}
