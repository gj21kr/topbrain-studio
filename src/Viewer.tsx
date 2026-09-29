import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import type { SparkRenderer, SplatMesh } from '@sparkjsdev/spark';
import { demo, explosionOffset, inspectGlb, inspectSplatPly, validateContext, validateManifest, validateMeshData, structureOpacity, type ContextLayer, type Manifest, type Structure } from './model';
import { normalizedPressureAtPhase, PRESSURE_INPUT_LIMITS, type PressureInputs } from './flow';
import { isArterialStructure } from './arterial';

export interface ContextFiles { info: unknown; bytes: ArrayBuffer }
export interface Asset { manifest: Manifest; scene?: THREE.Group; context?: { layer: ContextLayer; bytes: ArrayBuffer } }
export async function readAsset(manifestData: unknown, buffer: ArrayBuffer, contextFiles?: ContextFiles): Promise<Asset> {
  const manifest = validateManifest(manifestData);
  inspectGlb(buffer);
  // Validated before the GLB is parsed so a bad layer costs nothing but the header read.
  const context = contextFiles && { layer: validateContext(contextFiles.info, inspectSplatPly(contextFiles.bytes), manifest), bytes: contextFiles.bytes };
  const manager = new THREE.LoadingManager();
  manager.setURLModifier(() => { throw new Error('Model resource requests are disabled.'); });
  const result = await new GLTFLoader(manager).parseAsync(buffer, '');
  const names = new Set<string>();
  try {
    result.scene.traverse(item => {
      if (item instanceof THREE.Mesh) {
        if (names.has(item.name)) throw new Error('GLB mesh names must be unique.');
        const positions = item.geometry.getAttribute('position');
        if (!positions) throw new Error('Missing mesh positions.');
        validateMeshData(positions, item.geometry.getIndex());
        names.add(item.name);
      }
    });
    if (names.size !== manifest.structures.length || manifest.structures.some(s => !names.has(s.meshName))) throw new Error('Manifest structures must match every GLB mesh exactly.');
    const bounds = new THREE.Box3().setFromObject(result.scene);
    if (bounds.isEmpty() || !Number.isFinite(bounds.getSize(new THREE.Vector3()).length()) || bounds.getSize(new THREE.Vector3()).length() < 1e-8) throw new Error('Model has invalid bounds.');
    return { manifest, scene: result.scene, context };
  } catch (error) { disposeAsset({ manifest, scene: result.scene }); throw error; }
}

export function disposeAsset(asset: Asset) {
  asset.scene?.traverse(obj => { if (obj instanceof THREE.Mesh) { obj.geometry.dispose(); const mats = Array.isArray(obj.material) ? obj.material : [obj.material]; mats.forEach(m => m.dispose()); } });
}

export type FlowParams = PressureInputs;
interface Props { asset: Asset; selected: string; hidden: Set<string>; isolate: boolean; explosion: number; opacity: number; context: boolean; contextOpacity: number; opacities: Map<string, number>; labels: boolean; autoRotate: boolean; showConnectionGuides?: boolean; flowEnabled?: boolean; flowParams?: FlowParams; flowPhaseOriginMs?: number; focusRegion?: 'all' | 'head' | 'origin'; view: { name: string; tick: number }; onSelect: (id: string) => void; onError: (message: string) => void }
interface Piece { mesh: THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial>; original: THREE.Vector3; data: Structure; label: HTMLDivElement; arterial: boolean; illuminated: boolean }

function bounded(value: number | undefined, fallback: number, low: number, high: number): number {
  return Number.isFinite(value) ? Math.max(low, Math.min(high, value!)) : fallback;
}

export default function Viewer(props: Props) {
  const host = useRef<HTMLDivElement>(null), latest = useRef(props);
  latest.current = props;
  useEffect(() => {
    if (!host.current) return;
    const element = host.current;
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true }); }
    catch { props.onError('WebGL을 시작할 수 없습니다. 브라우저의 하드웨어 가속을 확인해 주세요. 구조 목록은 계속 사용할 수 있습니다.'); return; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x142128, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.5;
    renderer.domElement.setAttribute('aria-label', 'Interactive 3D anatomy model');
    renderer.domElement.setAttribute('role', 'img');
    element.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(36, 1, .01, 100);
    camera.position.set(0, 1, -11.8);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true; controls.dampingFactor = .08;
    controls.minDistance = 3; controls.maxDistance = 24; controls.autoRotateSpeed = .6;
    scene.add(new THREE.HemisphereLight(0xdff4ef, 0x38404d, 2.4));
    const light = new THREE.DirectionalLight(0xffffff, 3); light.position.set(4, 7, 6); scene.add(light);
    const rim = new THREE.DirectionalLight(0x82adc7, 2); rim.position.set(-5, 2, -4); scene.add(rim);
    const pieces: Piece[] = [];
    let spark: SparkRenderer | undefined, splat: SplatMesh | undefined, disposed = false;
    const connectionGuides: { group: THREE.Group; from: string; to: string }[] = [];
    const explosionScale = 1.5 / Math.max(.000001, ...props.asset.manifest.structures.map(s => Math.hypot(...s.explode)));
    const addPiece = (geometry: THREE.BufferGeometry, data: Structure) => {
      const material = new THREE.MeshStandardMaterial({ color: data.color, roughness: .35, metalness: .12, side: THREE.DoubleSide });
      const mesh = new THREE.Mesh(geometry, material); mesh.name = data.id; scene.add(mesh);
      const label = document.createElement('div'); label.className = 'vessel-label'; label.textContent = data.name;
      label.style.display = 'none'; element.appendChild(label);
      pieces.push({ mesh, original: mesh.position.clone(), data, label, arterial: isArterialStructure(data), illuminated: false });
    };
    if (props.asset.scene) {
      const source = props.asset.scene; source.updateMatrixWorld(true);
      const box = new THREE.Box3().setFromObject(source), center = box.getCenter(new THREE.Vector3());
      const scale = 5 / Math.max(...box.getSize(new THREE.Vector3()).toArray());
      source.traverse(object => { if (object instanceof THREE.Mesh) {
        const data = props.asset.manifest.structures.find(s => s.meshName === object.name)!;
        const geometry = object.geometry.clone().applyMatrix4(object.matrixWorld).translate(-center.x, -center.y, -center.z).scale(scale, scale, scale);
        geometry.computeVertexNormals(); addPiece(geometry, data);
      } });
      if (props.asset.context) {
        // The PLY is already in the GLB's glTF Y-up frame (same voxelToGltfM), so the
        // layer gets exactly the mesh placement, (p - center) * scale, and no axis flip.
        // Spark transfers the bytes to its decode worker, so it gets a copy: the asset
        // keeps its buffer and a re-run of this effect can load the layer again.
        // Spark is its own chunk, fetched only when a case ships a layer: the public
        // demo never pays for it, and its bundle stays under the Pages size check.
        const bytes = props.asset.context.bytes;
        void import('@sparkjsdev/spark').then(({ SparkRenderer, SplatMesh, SplatFileType }) => {
          if (disposed) return;
          spark = new SparkRenderer({ renderer }); scene.add(spark);
          splat = new SplatMesh({ fileBytes: bytes.slice(0), fileType: SplatFileType.PLY, onLoad: () => { renderer.domElement.dataset.contextLoaded = 'true'; } });
          splat.name = 'ct-context'; splat.scale.setScalar(scale); splat.position.set(-center.x * scale, -center.y * scale, -center.z * scale);
          scene.add(splat);
        }).catch(() => latest.current.onError('맥락 레이어 렌더러를 불러오지 못했습니다. 메시는 계속 볼 수 있습니다.'));
      }
      for (const guide of props.asset.manifest.connectionGuides ?? []) {
        const start = new THREE.Vector3(...guide.fromPoint).sub(center).multiplyScalar(scale);
        const end = new THREE.Vector3(...guide.toPoint).sub(center).multiplyScalar(scale);
        const direction = end.clone().sub(start);
        const group = new THREE.Group();
        group.name = guide.id;
        group.userData.kind = 'schematic';
        // A straight dotted locator between measured mesh vertices. It is not
        // a reconstructed vessel surface or a claim about the cervical route.
        const material = new THREE.MeshBasicMaterial({ color: 0xf5c76f, transparent: true, opacity: .98, depthTest: false, depthWrite: false });
        const count = 8, dashFraction = .57;
        for (let index = 0; index < count; index++) {
          const length = direction.length() * dashFraction / count;
          const geometry = new THREE.CylinderGeometry(.013, .013, length, 7);
          const dash = new THREE.Mesh(geometry, material);
          dash.position.copy(start).addScaledVector(direction, (index + dashFraction / 2) / count);
          dash.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.clone().normalize());
          dash.renderOrder = 4;
          group.add(dash);
        }
        group.visible = false;
        scene.add(group);
        connectionGuides.push({ group, from: guide.from, to: guide.to });
      }
    } else {
      demo.structures.forEach(data => {
        const curve = new THREE.CatmullRomCurve3(data.path!.map(p => new THREE.Vector3(...p)));
        addPiece(new THREE.TubeGeometry(curve, 64, data.radius, 10, false), data);
      });
    }
    const regionBounds = (matches: (piece: Piece) => boolean) => {
      const box = new THREE.Box3();
      let found = false;
      for (const piece of pieces) {
        if (!matches(piece)) continue;
        piece.mesh.geometry.computeBoundingBox();
        box.union(piece.mesh.geometry.boundingBox!);
        found = true;
      }
      return found ? box : null;
    };
    const headBounds = regionBounds(piece => piece.data.id === 'skull' || piece.data.id === 'brain');
    const originBounds = regionBounds(piece => piece.data.group === 'Proximal arterial supply');
    const shell = new THREE.Group();
    if (!props.asset.scene) {
      const shellMaterial = new THREE.MeshStandardMaterial({ color: 0xa9c7c1, transparent: true, opacity: .065, depthWrite: false, wireframe: true });
      const head = new THREE.Mesh(new THREE.SphereGeometry(1, 28, 28), shellMaterial); head.scale.set(1.96, 2.28, 1.53); head.position.y = .52;
      const neck = new THREE.Mesh(new THREE.CylinderGeometry(.72, .95, 1.8, 24, 8, true), shellMaterial); neck.position.y = -2;
      shell.add(head, neck); scene.add(shell);
    }
    const grid = new THREE.GridHelper(12, 36, 0x425c62, 0x284047); grid.position.y = -3.1;
    (grid.material as THREE.Material).transparent = true; (grid.material as THREE.Material).opacity = .3; scene.add(grid);
    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    let reducedMotion = motionQuery.matches;
    const updateMotion = (event: MediaQueryListEvent) => { reducedMotion = event.matches; };
    motionQuery.addEventListener('change', updateMotion);
    const resize = new ResizeObserver(() => { const { width, height } = element.getBoundingClientRect(); renderer.setSize(width, height); camera.aspect = width / Math.max(height, 1); camera.updateProjectionMatrix(); }); resize.observe(element);
    let down = { x: 0, y: 0 };
    const pointerDown = (event: PointerEvent) => { down = { x: event.clientX, y: event.clientY }; };
    const pointerUp = (event: PointerEvent) => {
      if (Math.hypot(event.clientX - down.x, event.clientY - down.y) > 5) return;
      const rect = element.getBoundingClientRect(), ray = new THREE.Raycaster();
      ray.setFromCamera(new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1), camera);
      const hits = ray.intersectObjects(pieces.filter(p => p.mesh.visible).map(p => p.mesh), false);
      const pick = hits.find(hit => {
        const piece = pieces.find(p => p.mesh === hit.object);
        return piece && (piece.data.group !== 'Reference layers' || piece.mesh.material.opacity >= .5);
      }) ?? hits[0];
      if (pick) latest.current.onSelect(pick.object.name);
    };
    renderer.domElement.addEventListener('pointerdown', pointerDown); renderer.domElement.addEventListener('pointerup', pointerUp);
    const lost = (event: Event) => { event.preventDefault(); latest.current.onError('3D 화면 연결이 끊겼습니다. 페이지를 새로고침해 주세요.'); };
    renderer.domElement.addEventListener('webglcontextlost', lost);
    let frame = 0, tick = -1;
    const animate = () => {
      const p = latest.current;
      const now = performance.now();
      const heartRate = bounded(p.flowParams?.heartRate, 72, PRESSURE_INPUT_LIMITS.heartRate.min, PRESSURE_INPUT_LIMITS.heartRate.max);
      const pulsePhase = p.flowEnabled && !reducedMotion ? (Math.max(0, now - (p.flowPhaseOriginMs ?? 0)) * heartRate / 60000) % 1 : 0;
      // One synchronous teaching pulse for the arterial layer. Pressure changes
      // visual contrast slightly; it is not a flow or perfusion calculation.
      const pulse = normalizedPressureAtPhase(pulsePhase);
      const systolic = bounded(p.flowParams?.systolic, 120, PRESSURE_INPUT_LIMITS.systolic.min, PRESSURE_INPUT_LIMITS.systolic.max);
      const diastolic = bounded(p.flowParams?.diastolic, 80, PRESSURE_INPUT_LIMITS.diastolic.min, PRESSURE_INPUT_LIMITS.diastolic.max);
      const pulsePressure = Math.max(1, systolic - diastolic);
      const maximumPulsePressure = PRESSURE_INPUT_LIMITS.systolic.max - PRESSURE_INPUT_LIMITS.diastolic.min;
      const pressureContrast = pulsePressure < 40
        ? .9 + .1 * (pulsePressure - 1) / 39
        : 1 + .1 * (pulsePressure - 40) / (maximumPulsePressure - 40);
      if (p.view.tick !== tick) {
        tick = p.view.tick;
        const box = p.focusRegion === 'head' ? headBounds : p.focusRegion === 'origin' ? originBounds : null;
        const target = box ? box.getCenter(new THREE.Vector3()) : new THREE.Vector3();
        const size = box?.getSize(new THREE.Vector3());
        const angle = THREE.MathUtils.degToRad(camera.fov / 2);
        const width = p.view.name === 'left' ? size?.z : size?.x;
        const height = p.view.name === 'superior' ? size?.z : size?.y;
        const depth = p.view.name === 'left' ? size?.x : p.view.name === 'superior' ? size?.y : size?.z;
        const distance = size ? Math.max(4.5, Math.max((height ?? 0) / (2 * Math.tan(angle)), (width ?? 0) / (2 * Math.tan(angle) * Math.max(.3, camera.aspect))) * 1.28 + (depth ?? 0) / 2) : 11.8;
        camera.up.set(0, p.view.name === 'superior' ? 0 : 1, p.view.name === 'superior' ? -1 : 0);
        const direction: Record<string, number[]> = { anterior: [0,.034 * distance,-distance], left: [-distance,.034 * distance,0], superior: [0,distance,.01] };
        camera.position.copy(target).add(new THREE.Vector3().fromArray(direction[p.view.name] ?? direction.anterior)); controls.target.copy(target); controls.update();
      }
      controls.autoRotate = p.autoRotate;
      if (splat) { splat.visible = p.context; splat.opacity = p.contextOpacity; }
      controls.update();
      const labelCandidates: { piece: Piece; x: number; y: number; selected: boolean }[] = [];
      const canvasWidth = element.clientWidth, canvasHeight = element.clientHeight;
      for (const piece of pieces) {
        const selected = piece.data.id === p.selected;
        const opacity = structureOpacity(piece.data, p.opacities, selected, p.opacity);
        piece.mesh.visible = !p.hidden.has(piece.data.id) && (!p.isolate || selected) && opacity > 0;
        const offset = explosionOffset(piece.data.explode, p.explosion, explosionScale);
        const target = piece.original.clone().add(new THREE.Vector3(...offset)); piece.mesh.position.lerp(target, .12);
        const arterialFlow = !!p.flowEnabled && piece.arterial;
        const illuminated = selected || arterialFlow;
        if (illuminated !== piece.illuminated) {
          if (illuminated) piece.mesh.material.emissive.copy(piece.mesh.material.color);
          else piece.mesh.material.emissive.setRGB(0, 0, 0);
          piece.illuminated = illuminated;
        }
        piece.mesh.material.emissiveIntensity = arterialFlow
          ? (selected ? .3 : .08) + (reducedMotion ? .16 : .65 * pulse * pressureContrast)
          : selected ? .26 : 0;
        piece.mesh.material.opacity = opacity;
        piece.mesh.material.transparent = opacity < 1;
        piece.mesh.material.depthWrite = opacity > .7;
        piece.label.style.display = 'none';
        if (p.labels && piece.mesh.visible) {
          if (!piece.mesh.geometry.boundingSphere) piece.mesh.geometry.computeBoundingSphere();
          const center = piece.mesh.geometry.boundingSphere!.center.clone().add(piece.mesh.position).project(camera);
          if (Math.abs(center.x) <= 1 && Math.abs(center.y) <= 1 && center.z > -1 && center.z < 1) {
            labelCandidates.push({ piece, x: (center.x + 1) * canvasWidth / 2, y: (-center.y + 1) * canvasHeight / 2, selected });
          }
        }
      }
      for (const guide of connectionGuides) {
        const from = pieces.find(piece => piece.data.id === guide.from);
        const to = pieces.find(piece => piece.data.id === guide.to);
        guide.group.visible = !!p.showConnectionGuides && p.explosion < .001 && !p.isolate && !!from?.mesh.visible && !!to?.mesh.visible;
      }
      const occupied: { left: number; right: number; top: number; bottom: number }[] = [];
      labelCandidates.sort((a, b) => Number(b.selected) - Number(a.selected));
      for (const candidate of labelCandidates) {
        if (occupied.length >= 16) break;
        const width = Math.min(170, Math.max(60, candidate.piece.data.name.length * 5.7 + 16));
        const box = { left: candidate.x - width / 2, right: candidate.x + width / 2, top: candidate.y - 23, bottom: candidate.y };
        if (box.left < 2 || box.right > canvasWidth - 2 || box.top < 2 || box.bottom > canvasHeight - 2) continue;
        if (occupied.some(other => box.left < other.right + 6 && box.right > other.left - 6 && box.top < other.bottom + 6 && box.bottom > other.top - 6)) continue;
        const label = candidate.piece.label;
        label.style.display = 'block'; label.style.left = `${candidate.x}px`; label.style.top = `${candidate.y}px`;
        label.style.opacity = candidate.selected ? '1' : '.7';
        occupied.push(box);
      }
      renderer.render(scene, camera);
      renderer.domElement.dataset.rendered = 'true';
      renderer.domElement.dataset.visibleCount = String(pieces.filter(x => x.mesh.visible).length);
      renderer.domElement.dataset.contextVisible = String(!!splat && splat.visible);
      renderer.domElement.dataset.visibleGuideCount = String(connectionGuides.filter(guide => guide.group.visible).length);
      renderer.domElement.dataset.focusRegion = p.focusRegion ?? 'all';
      renderer.domElement.dataset.cameraPosition = camera.position.toArray().map(value => value.toFixed(2)).join(',');
      frame = requestAnimationFrame(animate);
    };
    animate();
    return () => {
      cancelAnimationFrame(frame); resize.disconnect(); controls.dispose(); motionQuery.removeEventListener('change', updateMotion);
      renderer.domElement.removeEventListener('pointerdown', pointerDown); renderer.domElement.removeEventListener('pointerup', pointerUp); renderer.domElement.removeEventListener('webglcontextlost', lost);
      scene.traverse(obj => { if (obj instanceof THREE.Mesh || obj instanceof THREE.LineSegments) { obj.geometry.dispose(); (Array.isArray(obj.material) ? obj.material : [obj.material]).forEach(m => m.dispose()); } });
      disposed = true; splat?.dispose(); spark?.dispose();
      pieces.forEach(p => p.label.remove()); renderer.dispose(); renderer.domElement.remove();
    };
  }, [props.asset]);
  return <div className="viewport-canvas" ref={host} />;
}
