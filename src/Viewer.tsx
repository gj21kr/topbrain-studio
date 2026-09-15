import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { demo, explosionOffset, inspectGlb, validateManifest, validateMeshData, structureOpacity, type Manifest, type Structure } from './model';

export interface Asset { manifest: Manifest; scene?: THREE.Group }
export async function readAsset(manifestData: unknown, buffer: ArrayBuffer): Promise<Asset> {
  const manifest = validateManifest(manifestData);
  inspectGlb(buffer);
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
    return { manifest, scene: result.scene };
  } catch (error) { disposeAsset({ manifest, scene: result.scene }); throw error; }
}

export function disposeAsset(asset: Asset) {
  asset.scene?.traverse(obj => { if (obj instanceof THREE.Mesh) { obj.geometry.dispose(); const mats = Array.isArray(obj.material) ? obj.material : [obj.material]; mats.forEach(m => m.dispose()); } });
}

interface Props { asset: Asset; selected: string; hidden: Set<string>; isolate: boolean; explosion: number; opacity: number; opacities: Map<string, number>; labels: boolean; autoRotate: boolean; view: { name: string; tick: number }; onSelect: (id: string) => void; onError: (message: string) => void }
interface Piece { mesh: THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial>; original: THREE.Vector3; data: Structure; label: HTMLDivElement }

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
    const explosionScale = 1.5 / Math.max(.000001, ...props.asset.manifest.structures.map(s => Math.hypot(...s.explode)));
    const addPiece = (geometry: THREE.BufferGeometry, data: Structure) => {
      const material = new THREE.MeshStandardMaterial({ color: data.color, roughness: .35, metalness: .12, side: THREE.DoubleSide });
      const mesh = new THREE.Mesh(geometry, material); mesh.name = data.id; scene.add(mesh);
      const label = document.createElement('div'); label.className = 'vessel-label'; label.textContent = data.name;
      label.style.display = 'none'; element.appendChild(label);
      pieces.push({ mesh, original: mesh.position.clone(), data, label });
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
    } else {
      demo.structures.forEach(data => {
        const curve = new THREE.CatmullRomCurve3(data.path!.map(p => new THREE.Vector3(...p)));
        addPiece(new THREE.TubeGeometry(curve, 64, data.radius, 10, false), data);
      });
    }
    const shell = new THREE.Group();
    if (!props.asset.scene) {
      const shellMaterial = new THREE.MeshStandardMaterial({ color: 0xa9c7c1, transparent: true, opacity: .065, depthWrite: false, wireframe: true });
      const head = new THREE.Mesh(new THREE.SphereGeometry(1, 28, 28), shellMaterial); head.scale.set(1.96, 2.28, 1.53); head.position.y = .52;
      const neck = new THREE.Mesh(new THREE.CylinderGeometry(.72, .95, 1.8, 24, 8, true), shellMaterial); neck.position.y = -2;
      shell.add(head, neck); scene.add(shell);
    }
    const grid = new THREE.GridHelper(12, 36, 0x425c62, 0x284047); grid.position.y = -3.1;
    (grid.material as THREE.Material).transparent = true; (grid.material as THREE.Material).opacity = .3; scene.add(grid);
    const resize = new ResizeObserver(() => { const { width, height } = element.getBoundingClientRect(); renderer.setSize(width, height); camera.aspect = width / Math.max(height, 1); camera.updateProjectionMatrix(); }); resize.observe(element);
    let down = { x: 0, y: 0 };
    const pointerDown = (event: PointerEvent) => { down = { x: event.clientX, y: event.clientY }; };
    const pointerUp = (event: PointerEvent) => {
      if (Math.hypot(event.clientX - down.x, event.clientY - down.y) > 5) return;
      const rect = element.getBoundingClientRect(), ray = new THREE.Raycaster();
      ray.setFromCamera(new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1), camera);
      const hits = ray.intersectObjects(pieces.filter(p => p.mesh.visible).map(p => p.mesh), false);
      if (hits.length) latest.current.onSelect(hits[0].object.name);
    };
    renderer.domElement.addEventListener('pointerdown', pointerDown); renderer.domElement.addEventListener('pointerup', pointerUp);
    const lost = (event: Event) => { event.preventDefault(); latest.current.onError('3D 화면 연결이 끊겼습니다. 페이지를 새로고침해 주세요.'); };
    renderer.domElement.addEventListener('webglcontextlost', lost);
    let frame = 0, tick = -1;
    const animate = () => {
      const p = latest.current;
      if (p.view.tick !== tick) {
        tick = p.view.tick;
        const direction: Record<string, number[]> = { anterior: [0,.4,-11.8], left: [-11.8,.4,0], superior: [0,11.8,.01] };
        camera.up.set(0, p.view.name === 'superior' ? 0 : 1, p.view.name === 'superior' ? -1 : 0);
        camera.position.fromArray(direction[p.view.name] ?? direction.anterior); controls.target.set(0,0,0); controls.update();
      }
      controls.autoRotate = p.autoRotate;
      for (const piece of pieces) {
        const selected = piece.data.id === p.selected;
        const opacity = structureOpacity(piece.data, p.opacities, selected, p.opacity);
        piece.mesh.visible = !p.hidden.has(piece.data.id) && (!p.isolate || selected) && opacity > 0;
        const offset = explosionOffset(piece.data.explode, p.explosion, explosionScale);
        const target = piece.original.clone().add(new THREE.Vector3(...offset)); piece.mesh.position.lerp(target, .12);
        piece.mesh.material.emissive.set(selected ? piece.data.color : '#000000'); piece.mesh.material.emissiveIntensity = selected ? .26 : 0;
        piece.mesh.material.opacity = opacity;
        piece.mesh.material.transparent = opacity < 1;
        piece.mesh.material.depthWrite = opacity > .7;
        piece.label.style.display = p.labels && piece.mesh.visible ? 'block' : 'none';
        if (p.labels && piece.mesh.visible) {
          const center = new THREE.Box3().setFromObject(piece.mesh).getCenter(new THREE.Vector3()).project(camera);
          piece.label.style.left = `${(center.x + 1) * element.clientWidth / 2}px`;
          piece.label.style.top = `${(-center.y + 1) * element.clientHeight / 2}px`;
          piece.label.style.opacity = selected ? '1' : '.65';
        }
      }
      controls.update(); renderer.render(scene, camera);
      renderer.domElement.dataset.rendered = 'true';
      renderer.domElement.dataset.visibleCount = String(pieces.filter(x => x.mesh.visible).length);
      frame = requestAnimationFrame(animate);
    };
    animate();
    return () => {
      cancelAnimationFrame(frame); resize.disconnect(); controls.dispose();
      renderer.domElement.removeEventListener('pointerdown', pointerDown); renderer.domElement.removeEventListener('pointerup', pointerUp); renderer.domElement.removeEventListener('webglcontextlost', lost);
      scene.traverse(obj => { if (obj instanceof THREE.Mesh || obj instanceof THREE.LineSegments) { obj.geometry.dispose(); (Array.isArray(obj.material) ? obj.material : [obj.material]).forEach(m => m.dispose()); } });
      pieces.forEach(p => p.label.remove()); renderer.dispose(); renderer.domElement.remove();
    };
  }, [props.asset]);
  return <div className="viewport-canvas" ref={host} />;
}
