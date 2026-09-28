import { useEffect, useRef, useState } from 'react';
import { Activity, ArrowLeft, ArrowRight, BookOpen, Check, ChevronRight, Compass, Eye, EyeOff, Focus, Layers3, LoaderCircle, RotateCcw, Rotate3D, Search, Upload, X } from 'lucide-react';
import Viewer, { disposeAsset, readAsset, type Asset, type FlowParams } from './Viewer';
import FlowPanel from './FlowPanel';
import { demo, initialDisplay, type Manifest } from './model';
import { demoTrails } from './study';

const initial: Asset = { manifest: demo };
type AssetKind = 'schematic' | 'reference' | 'imported';
const sourceSummary = (source: string, kind: AssetKind) => {
  if (kind !== 'reference') return source;
  const concept = source.match(/^BodyParts3D 4\.0 PART-OF (FMA\d+)\/(BP\d+)/);
  return concept ? `BodyParts3D · ${concept[1]} / ${concept[2]}` : source;
};
export default function App() {
  const [asset, setAsset] = useState(initial), [selected, setSelected] = useState(demo.structures[0].id);
  const [assetKind, setAssetKind] = useState<AssetKind>('schematic');
  const [query, setQuery] = useState(''), [group, setGroup] = useState('All structures');
  const [hidden, setHidden] = useState(() => initialDisplay(demo.structures).hidden), [isolate, setIsolate] = useState(false);
  const [opacities, setOpacities] = useState(() => initialDisplay(demo.structures).opacities);
  const [explosion, setExplosion] = useState(0), [opacity, setOpacity] = useState(.85), [labels, setLabels] = useState(false), [autoRotate, setAutoRotate] = useState(false);
  const [showConnectionGuides, setShowConnectionGuides] = useState(true);
  const [view, setView] = useState({ name: 'anterior', tick: 0 }), [mode, setMode] = useState<'explore' | 'learn'>('explore');
  const [focusRegion, setFocusRegion] = useState<'all' | 'head' | 'origin'>('all');
  const [flowEnabled, setFlowEnabled] = useState(false), [flowParams, setFlowParams] = useState<FlowParams | null>({ systolic: 120, diastolic: 80, heartRate: 72 });
  const [flowPhaseOriginMs, setFlowPhaseOriginMs] = useState(0);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [info, setInfo] = useState(false);
  const [referenceLoading, setReferenceLoading] = useState(false);
  const [trailId, setTrailId] = useState(demoTrails[0].id), [trailStep, setTrailStep] = useState(0);
  const [completedTrails, setCompletedTrails] = useState<Set<string>>(() => new Set());
  const input = useRef<HTMLInputElement>(null), searchInput = useRef<HTMLInputElement>(null), sourceDialog = useRef<HTMLElement>(null);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setInfo(false);
        if (document.activeElement === searchInput.current) searchInput.current?.blur();
      }
      if (info) return;
      if (event.key !== '/' || event.altKey || event.ctrlKey || event.metaKey) return;
      const target = event.target;
      if (target instanceof HTMLElement && target.closest('input, textarea, select, [contenteditable="true"]')) return;
      event.preventDefault();
      searchInput.current?.focus();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [info]);
  useEffect(() => {
    if (!info || !sourceDialog.current) return;
    const dialog = sourceDialog.current;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusable = () => [...dialog.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])')];
    (focusable()[0] ?? dialog).focus();
    const keepFocusInDialog = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return;
      const controls = focusable();
      if (!controls.length) { event.preventDefault(); dialog.focus(); return; }
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
        event.preventDefault(); first.focus();
      }
    };
    document.addEventListener('keydown', keepFocusInDialog);
    return () => { document.removeEventListener('keydown', keepFocusInDialog); previousFocus?.focus(); };
  }, [info]);
  const structures = asset.manifest.structures, current = structures.find(x => x.id === selected) ?? structures[0];
  const activeTrail = demoTrails.find(trail => trail.id === trailId) ?? demoTrails[0];
  const activeStudyStep = activeTrail.steps[trailStep] ?? activeTrail.steps[0];
  const groups = [...new Set(structures.map(s => s.group))];
  const visible = structures.filter(s => (group === 'All structures' || s.group === group) && `${s.name} ${s.id} ${s.side} ${s.source ?? asset.manifest.source}`.toLowerCase().includes(query.toLowerCase()));
  const reset = (manifest: Manifest = asset.manifest) => { const defaults = initialDisplay(manifest.structures); setHidden(defaults.hidden); setOpacities(defaults.opacities); setSelected(defaults.selected); setIsolate(false); setExplosion(0); setOpacity(.85); setLabels(false); setAutoRotate(false); setFocusRegion('all'); setView(v => ({ name: 'anterior', tick: v.tick + 1 })); };
  const replace = (next: Asset, kind: AssetKind = 'imported') => { disposeAsset(asset); setAsset(next); setAssetKind(kind); setShowConnectionGuides(true); setQuery(''); setGroup('All structures'); reset(next.manifest); setMode('explore'); setTrailStep(0); setCompletedTrails(new Set()); setError(''); };
  const changeOpacity = (ids: string[], value: number) => setOpacities(old => { const next = new Map(old); ids.forEach(id => next.set(id, value)); return next; });
  const toggleFlow = (enabled: boolean) => { if (enabled && flowParams) setFlowPhaseOriginMs(performance.now()); setFlowEnabled(enabled && !!flowParams); };
  const toggleGroup = (ids: string[]) => { setIsolate(false); setHidden(old => { const next = new Set(old), show = ids.some(id => next.has(id)); ids.forEach(id => show ? next.delete(id) : next.add(id)); return next; }); };
  const reveal = (id: string) => { setSelected(id); setHidden(old => { const next = new Set(old); next.delete(id); return next; }); };
  const select = (id: string) => {
    reveal(id);
    if (mode === 'learn' && !asset.scene) {
      const index = activeTrail.steps.findIndex(studyStep => studyStep.structureId === id);
      if (index >= 0) setTrailStep(index);
      else setMode('explore');
    }
  };
  const startTrail = (id: string) => {
    const trail = demoTrails.find(candidate => candidate.id === id) ?? demoTrails[0];
    setTrailId(trail.id); setTrailStep(0); setMode('learn'); setIsolate(false); setQuery(''); setGroup('All structures'); reveal(trail.steps[0].structureId);
  };
  const moveTrail = (index: number) => { setTrailStep(index); setIsolate(false); reveal(activeTrail.steps[index].structureId); };
  const importFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    setBusy(true); setError('');
    try {
      if (files.length !== 2) throw new Error('GLB 파일 1개와 JSON manifest 1개를 함께 선택해 주세요.');
      const model = Array.from(files).find(f => /\.glb$/i.test(f.name)), manifest = Array.from(files).find(f => /\.json$/i.test(f.name));
      if (!model || !manifest || manifest.size > 2 * 1024 * 1024 || model.size > 150 * 1024 * 1024) throw new Error('파일 형식 또는 크기를 확인해 주세요(GLB ≤150 MB, JSON ≤2 MB).');
      replace(await readAsset(JSON.parse(await manifest.text()), await model.arrayBuffer()));
    } catch (e) { setError(e instanceof Error ? e.message : '가져오기에 실패했습니다.'); }
    finally { setBusy(false); if (input.current) input.current.value = ''; }
  };
  const loadLocalCase = async () => {
    setBusy(true); setError('');
    try {
      const [manifest, model] = await Promise.all([fetch('/local-case/manifest.json'), fetch('/local-case/model.glb')]);
      if (!manifest.ok || !model.ok || !manifest.headers.get('content-type')?.includes('json')) throw new Error('로컬 사례가 준비되지 않았습니다. README의 데이터 변환 절차를 실행하거나 GLB + JSON을 가져와 주세요.');
      replace(await readAsset(await manifest.json(), await model.arrayBuffer()));
    } catch (e) { setError(e instanceof Error ? e.message : '사례를 불러오지 못했습니다.'); }
    finally { setBusy(false); }
  };
  const loadReference = async (signal?: AbortSignal) => {
    setBusy(true); setReferenceLoading(true); setError('');
    const timeout = new AbortController();
    const abort = () => timeout.abort();
    signal?.addEventListener('abort', abort, { once: true });
    const timer = window.setTimeout(abort, 30000);
    try {
      const base = `${import.meta.env.BASE_URL}reference/bodyparts3d`;
      const [manifest, model] = await Promise.all([fetch(`${base}.json`, { signal: timeout.signal }), fetch(`${base}.glb`, { signal: timeout.signal })]);
      if (!manifest.ok || !model.ok || !manifest.headers.get('content-type')?.includes('json')) throw new Error('공개 참고 모델을 불러오지 못했습니다. 모식도는 계속 사용할 수 있습니다.');
      const next = await readAsset(await manifest.json(), await model.arrayBuffer());
      if (timeout.signal.aborted) { disposeAsset(next); if (signal?.aborted) return; throw new Error('공개 참고 모델 요청 시간이 초과됐습니다.'); }
      replace(next, 'reference');
    } catch (e) { if (!signal?.aborted) setError(timeout.signal.aborted ? '공개 참고 모델 요청 시간이 초과됐습니다. 다시 시도하거나 GLB + manifest를 가져와 주세요.' : e instanceof Error ? e.message : '공개 참고 모델을 불러오지 못했습니다.'); }
    finally { window.clearTimeout(timer); signal?.removeEventListener('abort', abort); if (!signal?.aborted) { setBusy(false); setReferenceLoading(false); } }
  };
  useEffect(() => { const controller = new AbortController(); void loadReference(controller.signal); return () => controller.abort(); }, []);
  const step = structures.findIndex(s => s.id === selected);
  return <div className="app-shell">
    <header className="topbar"><a className="brand" href={import.meta.env.BASE_URL} aria-label="TopBrain Studio home"><span className="brand-mark"><Activity size={22}/></span><span>TOPBRAIN<span className="brand-sub">STUDIO</span></span></a><nav aria-label="Studio mode"><button className={mode === 'explore' ? 'active' : ''} onClick={() => setMode('explore')}><Compass size={15}/> Explore</button><button className={mode === 'learn' ? 'active' : ''} onClick={() => asset.scene ? setMode('learn') : startTrail(trailId)}><BookOpen size={15}/> {asset.scene ? 'Structure review' : 'Guided study'}</button></nav><div className="header-end"><span className="personal"><i/> Personal workspace</span><button className="icon-button" aria-label="Data source and scope" onClick={() => setInfo(true)}><Layers3 size={19}/></button></div></header>
    <div className="workspace">
      <aside className="explorer"><div className="eyebrow">THE ANATOMY COLLECTION</div><h1>3D anatomy<span>Structure explorer</span></h1><p className="intro">구조를 선택하고, 공간 관계를<br/>직접 살펴보세요.</p><div className="dataset"><span className="dataset-icon"><Layers3 size={18}/></span><div><strong>{assetKind === 'reference' ? 'BodyParts3D reference' : assetKind === 'imported' ? 'Local anatomy study' : referenceLoading ? 'Loading public reference…' : 'Interactive schematic'}</strong><small>{assetKind === 'reference' ? 'Public atlas meshes · CC BY 4.0' : assetKind === 'imported' ? 'Local geometry · source attached' : 'Illustrative sample · not TopBrain data'}</small></div></div>
        <label className="search"><Search size={16}/><input ref={searchInput} aria-label="Search structures" value={query} onChange={e => setQuery(e.target.value)} placeholder="Find a structure…"/><kbd>/</kbd></label>
        <label className="group-label">SYSTEM<select aria-label="Filter system" value={group} onChange={e => setGroup(e.target.value)}>{['All structures', ...new Set(structures.map(s => s.group))].map(g => <option key={g}>{g}</option>)}</select></label>
        <details className="layer-controls"><summary>Group visibility &amp; opacity</summary><div className="layer-list">{groups.map(name => {
          const members = structures.filter(s => s.group === name), ids = members.map(s => s.id);
          const shown = members.filter(s => !hidden.has(s.id)).length;
          const values = members.map(s => opacities.get(s.id) ?? 1), value = values.reduce((a, b) => a + b, 0) / values.length;
          const mixed = values.some(v => v !== values[0]);
          return <div className="layer-row" key={name}><button aria-label={`${shown === members.length ? 'Hide' : 'Show'} group ${name}`} aria-pressed={shown === members.length} onClick={() => toggleGroup(ids)}>{shown ? <Eye size={13}/> : <EyeOff size={13}/>}<span>{name}</span><small>{shown}/{members.length}</small></button><label><span>Opacity <strong>{mixed ? 'Mixed' : `${Math.round(value * 100)}%`}</strong></span><input aria-label={`${name} opacity`} type="range" min="0" max="100" value={Math.round(value * 100)} onChange={e => changeOpacity(ids, Number(e.target.value) / 100)}/></label></div>;
        })}</div></details>
        <div className="list-heading"><span>STRUCTURES</span><span>{visible.length} / {structures.length}</span></div><div className="structure-list">{visible.length ? visible.map((s, i) => <div className={`structure-row ${selected === s.id ? 'selected' : ''}`} key={s.id}><button className="structure-select" onClick={() => select(s.id)} aria-pressed={selected === s.id}><span className="structure-number">{String(i + 1).padStart(2, '0')}</span><i style={{ background: s.color }}/><span>{s.name}<small>{s.side} · {s.group}</small><small className="structure-source">{sourceSummary(s.source ?? asset.manifest.source, assetKind)}</small></span></button><button className="eye-button" aria-label={`${hidden.has(s.id) ? 'Show' : 'Hide'} ${s.name}`} onClick={() => setHidden(old => { const next = new Set(old); if (next.has(s.id)) next.delete(s.id); else next.add(s.id); return next; })}>{hidden.has(s.id) ? <EyeOff size={14}/> : <Eye size={14}/>}</button></div>) : <div className="empty">No matching structures.<button onClick={() => { setQuery(''); setGroup('All structures'); }}>Clear filters</button></div>}</div>
        <div className="source-actions">{assetKind !== 'reference' && <button className="load-case" disabled={busy} onClick={() => void loadReference()}>{busy ? <LoaderCircle className="spin" size={16}/> : <Layers3 size={16}/>} Open BodyParts3D reference</button>}{import.meta.env.DEV && <button className="load-case" disabled={busy} onClick={loadLocalCase}>{busy ? <LoaderCircle className="spin" size={16}/> : <Layers3 size={16}/>} Open local TopBrain case</button>}<button className={!import.meta.env.DEV && assetKind === 'reference' ? 'load-case' : ''} disabled={busy} onClick={() => input.current?.click()}><Upload size={15}/> Import GLB + manifest</button><input ref={input} className="file-input" type="file" multiple accept=".json,.glb" onChange={e => void importFiles(e.target.files)}/><small>Imported files stay on this device.</small></div>
      </aside>
      <main className="studio"><div className="scene-heading"><div><span className="eyebrow">{assetKind === 'reference' ? 'PUBLIC REFERENCE MODEL' : asset.scene ? 'LOCAL DATASET' : 'SPATIAL EXPLORATION'}</span><h2>{asset.manifest.title}</h2></div><span className="sample-badge">{assetKind === 'reference' ? 'BodyParts3D · CC BY 4.0' : asset.scene ? 'Imported geometry' : 'Schematic preview'}</span></div>
        <Viewer asset={asset} selected={selected} hidden={hidden} isolate={isolate} explosion={explosion} opacity={opacity} opacities={opacities} labels={labels} autoRotate={autoRotate} showConnectionGuides={assetKind === 'reference' && showConnectionGuides} flowEnabled={flowEnabled && !!flowParams} flowParams={flowParams ?? undefined} flowPhaseOriginMs={flowPhaseOriginMs} focusRegion={focusRegion} view={view} onSelect={select} onError={setError}/>
        <div className="view-buttons" aria-label="Camera views">{['anterior', 'left', 'superior'].map(name => <button key={name} className={view.name === name ? 'active' : ''} onClick={() => setView(v => ({ name, tick: v.tick + 1 }))}>{name}</button>)}{groups.includes('Proximal arterial supply') && <select className="focus-region" aria-label="Focus region" value={focusRegion} onChange={e => { setFocusRegion(e.target.value as 'all' | 'head' | 'origin'); setView(v => ({ ...v, tick: v.tick + 1 })); }}><option value="all">Whole atlas</option><option value="head">Head focus</option><option value="origin">Aortic origin</option></select>}<button className={autoRotate ? 'active' : ''} aria-label="Auto rotate" aria-pressed={autoRotate} onClick={() => setAutoRotate(v => !v)}><Rotate3D size={17}/></button><button aria-label="Reset view and visibility" onClick={() => reset()}><RotateCcw size={16}/></button><button className={flowEnabled ? 'active' : ''} aria-label="Pulse preview" aria-pressed={flowEnabled} disabled={!flowParams} onClick={() => toggleFlow(!flowEnabled)}><Activity size={14}/> Pulse</button></div>
        <div className="scene-hint">Drag to orbit <i/> Scroll to zoom <i/> Click a structure to inspect</div>
        {assetKind === 'reference' && !!asset.manifest.connectionGuides?.length && <button className={`connection-guide-legend ${showConnectionGuides ? 'active' : ''}`} aria-label="Schematic neck connections" aria-pressed={showConnectionGuides} onClick={() => setShowConnectionGuides(value => !value)}><span className="guide-swatch" aria-hidden="true">┄┄</span><span><strong>Neck gaps · schematic</strong><small>{showConnectionGuides && (isolate || explosion > 0) ? 'Hidden in isolate / separated view' : 'Carotid bifurcation · cervical vertebral'}</small></span><span className="guide-state">{showConnectionGuides ? (isolate || explosion > 0 ? 'Paused' : 'On') : 'Off'}</span></button>}
        {explosion > 0 && <div className="explosion-warning">Separated view · spatial relationships are displaced</div>}
        <div className="assembly-control"><button onClick={() => setExplosion(0)} className="assemble"><Layers3 size={21}/><span>Assembled</span></button><label className="explode-slider"><span>Separate structures <strong>{Math.round(explosion * 100)}%</strong></span><input aria-label="Separate structures" type="range" min="0" max="100" value={Math.round(explosion * 100)} onChange={e => setExplosion(Number(e.target.value) / 100)}/></label><button className={`labels-toggle ${labels ? 'active' : ''}`} aria-pressed={labels} onClick={() => setLabels(v => !v)}><span className="toggle"><i/></span>Labels</button></div>
      </main>
      <aside className="inspector"><div className="eyebrow">{mode === 'learn' ? (asset.scene ? 'STRUCTURE REVIEW' : 'GUIDED STUDY') : 'STRUCTURE INSIGHT'}</div><div className="part-symbol" style={{ color: current.color }}><Activity size={44} strokeWidth={1}/><span>{current.side}</span></div><span className="part-group">{current.group}</span><h2>{current.name}</h2><div className="part-meta"><span>{current.id}</span>{current.label !== undefined && <span>Label {current.label}</span>}</div><p className="structure-source">Source: {sourceSummary(current.source ?? asset.manifest.source, assetKind)}</p><div className="divider"/><h3>{mode === 'learn' ? '지금 살펴볼 구조' : '이 구조 살펴보기'}</h3><p>{current.description}</p><div className="detail-actions"><button className={isolate ? 'active' : ''} aria-pressed={isolate} onClick={() => { if (!isolate) select(selected); setIsolate(v => !v); }}><Focus size={16}/>{isolate ? 'Restore visible structures' : 'Isolate structure'}</button><button onClick={() => setView(v => ({ name: 'anterior', tick: v.tick + 1 }))}><Compass size={16}/>Anterior view</button></div><label className="opacity"><span>Structure opacity <strong>{Math.round((opacities.get(current.id) ?? 1) * 100)}%</strong></span><input aria-label="Structure opacity" type="range" min="0" max="100" value={Math.round((opacities.get(current.id) ?? 1) * 100)} onChange={e => changeOpacity([current.id], Number(e.target.value) / 100)}/></label><label className="opacity"><span>Surrounding opacity <strong>{Math.round(opacity * 100)}%</strong></span><input aria-label="Surrounding opacity" type="range" min="10" max="100" value={opacity * 100} onChange={e => setOpacity(Number(e.target.value) / 100)}/></label>
        <div className="study-card">
          {mode === 'learn' && !asset.scene ? <>
            <span><BookOpen size={16}/>SCHEMATIC ROUTE · {trailStep + 1} / {activeTrail.steps.length}</span>
            <label className="trail-picker">Choose a route<select aria-label="Study route" value={trailId} onChange={e => startTrail(e.target.value)}>{demoTrails.map(trail => <option key={trail.id} value={trail.id}>{trail.title}</option>)}</select></label>
            <p className="trail-summary">{activeTrail.summary}</p>
            <h3>{activeStudyStep.title}</h3><p>{activeStudyStep.instruction}</p>
            <div className="study-navigation"><button aria-label="Previous study step" disabled={trailStep === 0} onClick={() => moveTrail(trailStep - 1)}><ArrowLeft size={16}/></button><span>{String(trailStep + 1).padStart(2, '0')} / {String(activeTrail.steps.length).padStart(2, '0')}</span><button aria-label="Next study step" disabled={trailStep === activeTrail.steps.length - 1} onClick={() => moveTrail(trailStep + 1)}><ArrowRight size={16}/></button></div>
            {trailStep === activeTrail.steps.length - 1 && (completedTrails.has(activeTrail.id) ? <p className="trail-complete"><Check size={15}/> Route reviewed</p> : <button className="study-finish" onClick={() => setCompletedTrails(old => new Set(old).add(activeTrail.id))}><Check size={15}/> I reviewed this route</button>)}
          </> : <>
            <span><BookOpen size={16}/>{asset.scene ? `STRUCTURE ${step + 1} OF ${structures.length}` : 'THREE SHORT ROUTES'}</span>
            <h3>{asset.scene ? '구조를 하나씩 살펴보세요' : '모식도를 직접 탐색해 보세요'}</h3>
            <p>{asset.scene ? '구조별 출처와 설명을 읽고, 단독 보기와 전체 보기를 비교하세요.' : '선택·회전·분해를 연습하는 세 경로가 준비돼 있습니다. 실제 해부학 검수 자료는 아닙니다.'}</p>
            {asset.scene ? <div className="study-navigation"><button aria-label="Previous structure" disabled={step === 0} onClick={() => select(structures[step - 1].id)}><ArrowLeft size={16}/></button><span>{String(step + 1).padStart(2, '0')} / {String(structures.length).padStart(2, '0')}</span><button aria-label="Next structure" disabled={step === structures.length - 1} onClick={() => { setMode('learn'); select(structures[step + 1].id); }}><ArrowRight size={16}/></button></div> : <button className="study-finish" onClick={() => startTrail(trailId)}><BookOpen size={15}/> Start guided study</button>}
          </>}
        </div>
        <FlowPanel enabled={flowEnabled} phaseOriginMs={flowPhaseOriginMs} onToggle={toggleFlow} onChange={preview => { setFlowParams(preview); if (!preview) setFlowEnabled(false); else setFlowPhaseOriginMs(performance.now()); }}/>
        <button className="provenance-link" onClick={() => setInfo(true)}>Dataset &amp; attribution <ChevronRight size={14}/></button>
      </aside>
    </div>
    <footer><span><i/> {assetKind === 'reference' ? 'PUBLIC REFERENCE' : asset.scene ? 'LOCAL STUDY LOADED' : 'SCHEMATIC MODE'}</span><span>Educational exploration · {asset.scene ? `${structures.length} labeled structures` : 'Not to scale'} · Not for diagnosis</span><button disabled={busy} onClick={() => replace(initial, 'schematic')}>Show schematic</button></footer>
    {error && <div className="error-toast" role="alert"><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}><X size={16}/></button></div>}
    {info && <div className="modal-backdrop" onClick={() => setInfo(false)}><section ref={sourceDialog} tabIndex={-1} className="source-modal" role="dialog" aria-modal="true" aria-labelledby="source-title" onClick={e => e.stopPropagation()}>
      <button className="modal-close" aria-label="Close source details" onClick={() => setInfo(false)}><X/></button><span className="eyebrow">DATA &amp; SCOPE</span><h2 id="source-title">A source for every structure.</h2>
      {assetKind === 'reference' && <div className="neck-route-summary"><h3>머리에서 흉부까지</h3><p>앞순환: 상행 대동맥·대동맥궁 → 완두동맥(우측) 또는 좌총경동맥(좌측) → 양측 총경동맥 → 경동맥 분기부·경부 내경동맥 → 두개내 내경동맥.</p><p>뒤순환: 쇄골하동맥 → 척추동맥 기시부·경부 척추동맥 → 두개내 척추동맥 → 기저동맥.</p><p>황색 점선 네 개는 원본 메쉬 사이 약 50–63 mm의 빈 구간을 직선으로 표시한 방향 안내입니다. 실제 혈관 표면이나 해부학적 주행이 아닙니다.</p></div>}
      <dl><dt>Source</dt><dd>{asset.manifest.source}</dd><dt>Selected structure</dt><dd>{current.name}: {current.source ?? asset.manifest.source}</dd><dt>License</dt><dd>{asset.manifest.license}</dd><dt>Provenance</dt><dd>{asset.manifest.provenance}</dd></dl>
      {assetKind === 'reference' ? <><p>BodyParts3D, © The Database Center for Life Science licensed under CC Attribution 4.0 International.</p><p>BodyParts3D의 공개 참고 해부 모델입니다. 두개골·뇌·뇌혈관은 정렬된 3D 메시이며, 한 사람의 영상에서 얻은 voxel mask가 아닙니다. 구조의 완전성이나 개인별 변이를 판단하는 데 사용하지 마세요.</p><a href={`${import.meta.env.BASE_URL}reference/ATTRIBUTION.txt`} target="_blank" rel="noreferrer">Full source and adaptation details ↗</a><a href="https://dbarchive.biosciencedbc.jp/en/bodyparts3d/lic.html" target="_blank" rel="noreferrer">BodyParts3D source and CC BY 4.0 license ↗</a></> : assetKind === 'imported' ? <p>이 구조의 출처와 이용 조건은 가져온 manifest에 기록된 내용입니다. 파일은 브라우저 메모리에서 처리되며 업로드하지 않습니다. 실제 분할의 정확도와 지원 범위는 원본 자료에서 별도로 검증해야 합니다.</p> : <p>이 첫 화면의 head 윤곽과 혈관 경로는 코드로 만든 모식도입니다. TopBrain 자료나 검증된 해부학이 아니며 실제 크기와 위치를 나타내지 않습니다.</p>}
      <p>Educational exploration only. Not for diagnosis, treatment or procedure planning.</p><button className="load-case" onClick={() => setInfo(false)}><Check size={16}/>Back to exploration</button>
    </section></div>}
  </div>;
}
