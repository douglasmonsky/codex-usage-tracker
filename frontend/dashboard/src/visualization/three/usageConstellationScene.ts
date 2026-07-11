import {
  ACESFilmicToneMapping,
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  Color,
  FogExp2,
  GridHelper,
  LineBasicMaterial,
  LineSegments,
  PerspectiveCamera,
  Points,
  Raycaster,
  Scene,
  ShaderMaterial,
  SRGBColorSpace,
  Vector2,
  Vector3,
  WebGLRenderer,
} from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

import type { UsageConstellationModel, UsageConstellationPoint } from './types';

type HoverPosition = { x: number; y: number };

type SceneOptions = {
  canvas: HTMLCanvasElement;
  model: UsageConstellationModel;
  onHover: (point: UsageConstellationPoint | null, position: HoverPosition | null) => void;
  onOpen: (point: UsageConstellationPoint) => void;
};

export type UsageConstellationScene = {
  destroy: () => void;
  reset: () => void;
};

const BACKGROUND = '#0b1016';
const CAMERA_POSITION = new Vector3(10.5, 8.2, 13.5);
const CAMERA_TARGET = new Vector3(0, 2.2, 0);

export function createUsageConstellationScene(options: SceneOptions): UsageConstellationScene {
  const { canvas, model } = options;
  const renderer = new WebGLRenderer({
    antialias: true,
    alpha: false,
    canvas,
    powerPreference: 'high-performance',
  });
  renderer.outputColorSpace = SRGBColorSpace;
  renderer.toneMapping = ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.12;
  renderer.setClearColor(BACKGROUND, 1);

  const scene = new Scene();
  scene.background = new Color(BACKGROUND);
  scene.fog = new FogExp2(BACKGROUND, 0.026);
  const camera = new PerspectiveCamera(43, 1, 0.1, 100);
  camera.position.copy(CAMERA_POSITION);

  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = false;
  controls.enablePan = false;
  controls.minDistance = 7;
  controls.maxDistance = 27;
  controls.maxPolarAngle = Math.PI * 0.86;
  controls.target.copy(CAMERA_TARGET);

  const grid = new GridHelper(16, 16, '#30455d', '#182534');
  scene.add(grid);
  const axes = createAxes();
  scene.add(axes);
  const links = createThreadLinks(model);
  if (links) scene.add(links);
  const dropLines = createDropLines(model);
  scene.add(dropLines);

  const pointGeometry = createPointGeometry(model);
  const pointMaterial = createPointMaterial();
  const pointCloud = new Points(pointGeometry, pointMaterial);
  scene.add(pointCloud);

  const baseIntensity = model.points.map(point => 0.28 + (point.wastePressure * 0.72));
  const intensityAttribute = pointGeometry.getAttribute('intensity') as BufferAttribute;
  const pointer = new Vector2();
  const raycaster = new Raycaster();
  raycaster.params.Points.threshold = 0.32;
  let hoveredIndex: number | null = null;
  let pointerDown: HoverPosition | null = null;
  let destroyed = false;

  const render = () => {
    if (destroyed) return;
    renderer.render(scene, camera);
    canvas.dataset.rendered = 'true';
    canvas.dataset.pointCount = String(model.points.length);
    updatePrimaryHitTarget(canvas, camera, model);
  };
  const resize = () => {
    const parent = canvas.parentElement;
    const width = Math.max(1, parent?.clientWidth ?? canvas.clientWidth);
    const height = Math.max(1, parent?.clientHeight ?? canvas.clientHeight);
    renderer.setPixelRatio(Math.min(globalThis.devicePixelRatio || 1, 1.75));
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.fov = camera.aspect < 1.2 ? 62 : 43;
    camera.updateProjectionMatrix();
    pointMaterial.uniforms.pixelRatio.value = renderer.getPixelRatio();
    render();
  };
  const updateHover = (index: number | null, event?: PointerEvent) => {
    if (hoveredIndex === index && index === null) return;
    if (hoveredIndex !== null) intensityAttribute.setX(hoveredIndex, baseIntensity[hoveredIndex]);
    hoveredIndex = index;
    if (index !== null) intensityAttribute.setX(index, 1.65);
    intensityAttribute.needsUpdate = true;
    canvas.style.cursor = index === null ? 'grab' : 'pointer';
    options.onHover(
      index === null ? null : model.points[index],
      index === null || !event ? null : pointerPosition(canvas, event),
    );
    render();
  };
  const hitTest = (event: PointerEvent): number | null => {
    const rect = canvas.getBoundingClientRect();
    pointer.set(
      (((event.clientX - rect.left) / rect.width) * 2) - 1,
      -(((event.clientY - rect.top) / rect.height) * 2) + 1,
    );
    raycaster.setFromCamera(pointer, camera);
    return raycaster.intersectObject(pointCloud, false)[0]?.index ?? null;
  };
  const handlePointerMove = (event: PointerEvent) => updateHover(hitTest(event), event);
  const handlePointerLeave = () => updateHover(null);
  const handlePointerDown = (event: PointerEvent) => {
    pointerDown = { x: event.clientX, y: event.clientY };
  };
  const handleClick = (event: PointerEvent) => {
    const travel = pointerDown ? Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y) : 0;
    pointerDown = null;
    if (travel > 5) return;
    const index = hitTest(event);
    if (index !== null) options.onOpen(model.points[index]);
  };
  const handleContextLoss = (event: Event) => {
    event.preventDefault();
    canvas.dataset.rendered = 'false';
  };

  canvas.addEventListener('pointermove', handlePointerMove);
  canvas.addEventListener('pointerleave', handlePointerLeave);
  canvas.addEventListener('pointerdown', handlePointerDown);
  canvas.addEventListener('click', handleClick);
  canvas.addEventListener('webglcontextlost', handleContextLoss);
  controls.addEventListener('change', render);
  const resizeObserver = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize);
  resizeObserver?.observe(canvas.parentElement ?? canvas);
  globalThis.addEventListener('resize', resize);
  controls.update();
  resize();

  return {
    reset() {
      camera.position.copy(CAMERA_POSITION);
      controls.target.copy(CAMERA_TARGET);
      controls.update();
      updateHover(null);
      render();
    },
    destroy() {
      destroyed = true;
      resizeObserver?.disconnect();
      globalThis.removeEventListener('resize', resize);
      canvas.removeEventListener('pointermove', handlePointerMove);
      canvas.removeEventListener('pointerleave', handlePointerLeave);
      canvas.removeEventListener('pointerdown', handlePointerDown);
      canvas.removeEventListener('click', handleClick);
      canvas.removeEventListener('webglcontextlost', handleContextLoss);
      controls.removeEventListener('change', render);
      controls.dispose();
      pointGeometry.dispose();
      pointMaterial.dispose();
      grid.geometry.dispose();
      disposeMaterial(grid.material);
      axes.geometry.dispose();
      disposeMaterial(axes.material);
      links?.geometry.dispose();
      if (links) disposeMaterial(links.material);
      dropLines.geometry.dispose();
      disposeMaterial(dropLines.material);
      renderer.dispose();
    },
  };
}

function createPointGeometry(model: UsageConstellationModel): BufferGeometry {
  const positions = new Float32Array(model.points.length * 3);
  const colors = new Float32Array(model.points.length * 3);
  const sizes = new Float32Array(model.points.length);
  const intensities = new Float32Array(model.points.length);
  model.points.forEach((point, index) => {
    positions.set(point.position, index * 3);
    new Color(point.color).toArray(colors, index * 3);
    sizes[index] = point.size;
    intensities[index] = 0.28 + (point.wastePressure * 0.72);
  });
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(positions, 3));
  geometry.setAttribute('color', new BufferAttribute(colors, 3));
  geometry.setAttribute('pointSize', new BufferAttribute(sizes, 1));
  geometry.setAttribute('intensity', new BufferAttribute(intensities, 1));
  geometry.computeBoundingSphere();
  return geometry;
}

function createPointMaterial(): ShaderMaterial {
  return new ShaderMaterial({
    blending: AdditiveBlending,
    depthWrite: false,
    transparent: true,
    vertexColors: true,
    uniforms: { pixelRatio: { value: 1 } },
    vertexShader: `
      attribute float pointSize;
      attribute float intensity;
      varying vec3 vColor;
      varying float vIntensity;
      uniform float pixelRatio;
      void main() {
        vColor = color;
        vIntensity = intensity;
        vec4 viewPosition = modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = clamp(pointSize * pixelRatio * (92.0 / -viewPosition.z), 3.0, 34.0);
        gl_Position = projectionMatrix * viewPosition;
      }
    `,
    fragmentShader: `
      varying vec3 vColor;
      varying float vIntensity;
      void main() {
        float distanceToCenter = distance(gl_PointCoord, vec2(0.5));
        if (distanceToCenter > 0.5) discard;
        float core = 1.0 - smoothstep(0.08, 0.5, distanceToCenter);
        float halo = (1.0 - smoothstep(0.18, 0.5, distanceToCenter)) * 0.48;
        float alpha = (core + halo) * (0.58 + (vIntensity * 0.34));
        gl_FragColor = vec4(vColor * (1.0 + (vIntensity * 0.38)), alpha);
      }
    `,
  });
}

function createThreadLinks(model: UsageConstellationModel): LineSegments<BufferGeometry, LineBasicMaterial> | null {
  if (!model.links.length) return null;
  const positions = new Float32Array(model.links.length * 6);
  model.links.forEach((link, index) => {
    positions.set(model.points[link.sourceIndex].position, index * 6);
    positions.set(model.points[link.targetIndex].position, (index * 6) + 3);
  });
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(positions, 3));
  return new LineSegments(geometry, new LineBasicMaterial({ color: '#52708f', opacity: 0.22, transparent: true }));
}

function createDropLines(model: UsageConstellationModel): LineSegments<BufferGeometry, LineBasicMaterial> {
  const positions = new Float32Array(model.points.length * 6);
  const colors = new Float32Array(model.points.length * 6);
  model.points.forEach((point, index) => {
    positions.set(point.position, index * 6);
    positions.set([point.position[0], 0, point.position[2]], (index * 6) + 3);
    const color = new Color(point.color);
    color.toArray(colors, index * 6);
    color.clone().multiplyScalar(0.32).toArray(colors, (index * 6) + 3);
  });
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(positions, 3));
  geometry.setAttribute('color', new BufferAttribute(colors, 3));
  return new LineSegments(geometry, new LineBasicMaterial({ opacity: 0.34, transparent: true, vertexColors: true }));
}

function createAxes(): LineSegments<BufferGeometry, LineBasicMaterial> {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([
    -7.8, 0, 0, 7.8, 0, 0,
    0, 0, 0, 0, 5.7, 0,
    0, 0, -4.6, 0, 0, 4.6,
  ]), 3));
  return new LineSegments(geometry, new LineBasicMaterial({ color: '#6383a6', opacity: 0.68, transparent: true }));
}

function updatePrimaryHitTarget(
  canvas: HTMLCanvasElement,
  camera: PerspectiveCamera,
  model: UsageConstellationModel,
) {
  const primary = [...model.points]
    .sort((left, right) => (right.wastePressure + (right.size / 100)) - (left.wastePressure + (left.size / 100)))[0];
  if (!primary) return;
  const projected = new Vector3(...primary.position).project(camera);
  canvas.dataset.primaryHitX = String(((projected.x + 1) / 2) * canvas.clientWidth);
  canvas.dataset.primaryHitY = String(((-projected.y + 1) / 2) * canvas.clientHeight);
}

function pointerPosition(canvas: HTMLCanvasElement, event: PointerEvent): HoverPosition {
  const rect = canvas.getBoundingClientRect();
  return {
    x: Math.min(rect.width - 12, Math.max(12, event.clientX - rect.left)),
    y: Math.min(rect.height - 12, Math.max(12, event.clientY - rect.top)),
  };
}

function disposeMaterial(material: LineBasicMaterial | LineBasicMaterial[]) {
  if (Array.isArray(material)) material.forEach(item => item.dispose());
  else material.dispose();
}
