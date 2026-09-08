import { useRef, useState } from 'react';
import { Activity, ArrowLeft, ArrowRight, BookOpen, Check, ChevronRight, Compass, Eye, EyeOff, Focus, Layers3, LoaderCircle, RotateCcw, Rotate3D, Search, Upload, X } from 'lucide-react';
import Viewer, { disposeAsset, readAsset, type Asset } from './Viewer';
import { demo } from './model';

const initial: Asset = { manifest: demo };
export default function App() {
  const [asset, setAsset] = useState(initial), [selected, setSelected] = useState(demo.structures[0].id);
  const [query, setQuery] = useState(''), [group, setGroup] = useState('All structures');
  const [hidden, setHidden] = useState(new Set<string>()), [isolate, setIsolate] = useState(false);
  const [explosion, setExplosion] = useState(0), [opacity, setOpacity] = useState(.85), [labels, setLabels] = useState(false), [autoRotate, setAutoRotate] = useState(false);
  const [view, setView] = useState({ name: 'anterior', tick: 0 }), [mode, setMode] = useState<'explore' | 'learn'>('explore');
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [info, setInfo] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const structures = asset.manifest.structures, current = structures.find(x => x.id === selected)!;
  const visible = structures.filter(s => (group === 'All structures' || s.group === group) && `${s.name} ${s.id} ${s.side}`.toLowerCase().includes(query.toLowerCase()));
  const reset = () => { setHidden(new Set()); setIsolate(false); setExplosion(0); setOpacity(.85); setLabels(false); setAutoRotate(false); setView(v => ({ name: 'anterior', tick: v.tick + 1 })); };
  const replace = (next: Asset) => { disposeAsset(asset); setAsset(next); setSelected(next.manifest.structures[0].id); setQuery(''); setGroup('All structures'); reset(); setError(''); };
  const select = (id: string) => { setSelected(id); setHidden(old => { const next = new Set(old); next.delete(id); return next; }); };
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
  const step = structures.findIndex(s => s.id === selected);
  return <div className="app-shell">
    <header className="topbar"><a className="brand" href="/" aria-label="TopBrain Studio home"><span className="brand-mark"><Activity size={22}/></span><span>TOPBRAIN<span className="brand-sub">STUDIO</span></span></a><nav aria-label="Studio mode"><button className={mode === 'explore' ? 'active' : ''} onClick={() => setMode('explore')}><Compass size={15}/> Explore</button><button className={mode === 'learn' ? 'active' : ''} onClick={() => setMode('learn')}><BookOpen size={15}/> Guided study</button></nav><div className="header-end"><span className="personal"><i/> Personal workspace</span><button className="icon-button" aria-label="Data source and scope" onClick={() => setInfo(true)}><Layers3 size={19}/></button></div></header>
    <div className="workspace">
      <aside className="explorer"><div className="eyebrow">THE ANATOMY COLLECTION</div><h1>Head &amp; neck<span>Vascular atlas</span></h1><p className="intro">구조를 선택하고, 공간 관계를<br/>직접 살펴보세요.</p><div className="dataset"><span className="dataset-icon"><Layers3 size={18}/></span><div><strong>{asset.scene ? 'TopBrain / Imported study' : 'Interactive schematic'}</strong><small>{asset.scene ? 'Local geometry · source attached' : 'Illustrative sample · not TopBrain data'}</small></div></div>
        <label className="search"><Search size={16}/><input aria-label="Search structures" value={query} onChange={e => setQuery(e.target.value)} placeholder="Find a structure…"/><kbd>/</kbd></label>
        <label className="group-label">SYSTEM<select aria-label="Filter system" value={group} onChange={e => setGroup(e.target.value)}>{['All structures', ...new Set(structures.map(s => s.group))].map(g => <option key={g}>{g}</option>)}</select></label>
        <div className="list-heading"><span>STRUCTURES</span><span>{visible.length} / {structures.length}</span></div><div className="structure-list">{visible.length ? visible.map((s, i) => <div className={`structure-row ${selected === s.id ? 'selected' : ''}`} key={s.id}><button className="structure-select" onClick={() => select(s.id)} aria-pressed={selected === s.id}><span className="structure-number">{String(i + 1).padStart(2, '0')}</span><i style={{ background: s.color }}/><span>{s.name}<small>{s.side} · {s.group}</small></span></button><button className="eye-button" aria-label={`${hidden.has(s.id) ? 'Show' : 'Hide'} ${s.name}`} onClick={() => setHidden(old => { const next = new Set(old); if (next.has(s.id)) next.delete(s.id); else next.add(s.id); return next; })}>{hidden.has(s.id) ? <EyeOff size={14}/> : <Eye size={14}/>}</button></div>) : <div className="empty">No matching structures.<button onClick={() => { setQuery(''); setGroup('All structures'); }}>Clear filters</button></div>}</div>
        <div className="source-actions"><button className="load-case" disabled={busy} onClick={loadLocalCase}>{busy ? <LoaderCircle className="spin" size={16}/> : <Layers3 size={16}/>} Open local TopBrain case</button><button disabled={busy} onClick={() => input.current?.click()}><Upload size={15}/> Import GLB + manifest</button><input ref={input} className="file-input" type="file" multiple accept=".json,.glb" onChange={e => void importFiles(e.target.files)}/><small>Files stay on this device.</small></div>
      </aside>
      <main className="studio"><div className="scene-heading"><div><span className="eyebrow">{asset.scene ? 'LOCAL DATASET' : 'SPATIAL EXPLORATION'}</span><h2>{asset.manifest.title}</h2></div><span className="sample-badge">{asset.scene ? 'Imported geometry' : 'Schematic preview'}</span></div>
        <Viewer asset={asset} selected={selected} hidden={hidden} isolate={isolate} explosion={explosion} opacity={opacity} labels={labels} autoRotate={autoRotate} view={view} onSelect={select} onError={setError}/>
        <div className="orientation"><span>S</span><div><b>R</b><i>✣</i><b>L</b></div><span>I</span><small>Anterior reference</small></div>
        <div className="view-buttons" aria-label="Camera views">{['anterior', 'left', 'superior'].map(name => <button key={name} className={view.name === name ? 'active' : ''} onClick={() => setView(v => ({ name, tick: v.tick + 1 }))}>{name}</button>)}<button className={autoRotate ? 'active' : ''} aria-label="Auto rotate" aria-pressed={autoRotate} onClick={() => setAutoRotate(v => !v)}><Rotate3D size={17}/></button><button aria-label="Reset view and visibility" onClick={reset}><RotateCcw size={16}/></button></div>
        <div className="scene-hint">Drag to orbit <i/> Scroll to zoom <i/> Click a vessel to inspect</div>
        {explosion > 0 && <div className="explosion-warning">Separated view · spatial relationships are displaced</div>}
        <div className="assembly-control"><button onClick={() => setExplosion(0)} className="assemble"><Layers3 size={21}/><span>Assembled</span></button><label className="explode-slider"><span>Separate structures <strong>{Math.round(explosion * 100)}%</strong></span><input aria-label="Separate structures" type="range" min="0" max="100" value={Math.round(explosion * 100)} onChange={e => setExplosion(Number(e.target.value) / 100)}/></label><button className={`labels-toggle ${labels ? 'active' : ''}`} aria-pressed={labels} onClick={() => setLabels(v => !v)}><span className="toggle"><i/></span>Labels</button></div>
      </main>
      <aside className="inspector"><div className="eyebrow">{mode === 'learn' ? 'GUIDED STUDY' : 'STRUCTURE INSIGHT'}</div><div className="part-symbol" style={{ color: current.color }}><Activity size={44} strokeWidth={1}/><span>{current.side}</span></div><span className="part-group">{current.group}</span><h2>{current.name}</h2><div className="part-meta"><span>{current.id}</span>{current.label !== undefined && <span>Label {current.label}</span>}</div><div className="divider"/><h3>{mode === 'learn' ? '지금 살펴볼 구조' : '이 구조 살펴보기'}</h3><p>{current.description}</p><div className="detail-actions"><button className={isolate ? 'active' : ''} aria-pressed={isolate} onClick={() => { setHidden(new Set()); setIsolate(v => !v); }}><Focus size={16}/>{isolate ? 'Show all structures' : 'Isolate structure'}</button><button onClick={() => setView(v => ({ name: 'anterior', tick: v.tick + 1 }))}><Compass size={16}/>Anterior view</button></div><label className="opacity"><span>Surrounding opacity <strong>{Math.round(opacity * 100)}%</strong></span><input aria-label="Surrounding opacity" type="range" min="10" max="100" value={opacity * 100} onChange={e => setOpacity(Number(e.target.value) / 100)}/></label>
        <div className="study-card"><span><BookOpen size={16}/>{mode === 'learn' ? `STRUCTURE ${step + 1} OF ${structures.length}` : 'A CLOSER LOOK'}</span><h3>{mode === 'learn' ? '한 구조씩 따라가 보세요' : 'From the whole to the detail'}</h3><p>선택한 구조를 단독으로 보고, 다시 전체를 표시해 주변과의 관계를 비교하세요.</p><div className="study-navigation"><button aria-label="Previous structure" disabled={step === 0} onClick={() => select(structures[step - 1].id)}><ArrowLeft size={16}/></button><span>{String(step + 1).padStart(2, '0')} / {String(structures.length).padStart(2, '0')}</span><button aria-label="Next structure" disabled={step === structures.length - 1} onClick={() => { setMode('learn'); select(structures[step + 1].id); }}><ArrowRight size={16}/></button></div></div>
        <button className="provenance-link" onClick={() => setInfo(true)}>Dataset &amp; attribution <ChevronRight size={14}/></button>
      </aside>
    </div>
    <footer><span><i/> {asset.scene ? 'LOCAL STUDY LOADED' : 'SCHEMATIC MODE'}</span><span>Educational exploration · {asset.scene ? `${structures.length} labeled structures` : 'Not to scale'} · Not for diagnosis</span><button disabled={busy} onClick={() => replace(initial)}>Reset to schematic</button></footer>
    {error && <div className="error-toast" role="alert"><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}><X size={16}/></button></div>}
    {info && <div className="modal-backdrop" onClick={() => setInfo(false)}><section className="source-modal" role="dialog" aria-modal="true" aria-labelledby="source-title" onClick={e => e.stopPropagation()}><button className="modal-close" aria-label="Close source details" onClick={() => setInfo(false)}><X/></button><span className="eyebrow">DATA &amp; SCOPE</span><h2 id="source-title">A source for every structure.</h2><dl><dt>Source</dt><dd>{asset.manifest.source}</dd><dt>License</dt><dd>{asset.manifest.license}</dd><dt>Provenance</dt><dd>{asset.manifest.provenance}</dd></dl><p>TopBrain은 혈관 분할 데이터입니다. 원 영상의 촬영·전처리 범위에 따라 목 전체나 뼈·신경·근육은 포함되지 않습니다. 첫 화면의 head 윤곽과 혈관 모식도는 TopBrain에서 추출한 해부학이 아닙니다.</p><a href="https://topbrain2025.grand-challenge.org/data/" target="_blank" rel="noreferrer">Official dataset documentation ↗</a><button className="load-case" onClick={() => setInfo(false)}><Check size={16}/>Back to exploration</button></section></div>}
  </div>;
}
