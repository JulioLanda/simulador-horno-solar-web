import * as THREE from "https://esm.sh/three@0.180.0";
import { OrbitControls } from "https://esm.sh/three@0.180.0/examples/jsm/controls/OrbitControls.js";

const COLORS = {
  background: 0x0b1620,
  grid: 0x28465b,
  steel: 0x7892a5,
  steelDark: 0x38566b,
  mirror: 0xbfe8f4,
  mirrorEdge: 0xe9fbff,
  receiver: 0xd1a744,
  receiverDark: 0x735a22,
  sun: 0xffdc4a,
  normal: 0xff9f43,
  target: 0x7de3ef,
  ray: 0xe8f7ff,
};

let renderer;
let scene;
let camera;
let controls;
let dynamicGroup;
let animationFrame;
let resizeObserver;
let lastRevision = null;
let framedOnce = false;
let currentTarget = new THREE.Vector3(0, 0, 0);

function simVector(values) {
  return new THREE.Vector3(Number(values[0]), Number(values[2]), -Number(values[1]));
}

function material(color, options = {}) {
  return new THREE.MeshStandardMaterial({
    color,
    roughness: options.roughness ?? 0.62,
    metalness: options.metalness ?? 0.12,
    transparent: options.opacity !== undefined && options.opacity < 1,
    opacity: options.opacity ?? 1,
    side: options.side ?? THREE.FrontSide,
  });
}

function disposeObject(root) {
  root.traverse((object) => {
    object.geometry?.dispose?.();
    if (Array.isArray(object.material)) object.material.forEach((item) => item.dispose?.());
    else object.material?.dispose?.();
  });
}

function lineBetween(a, b, color, width = 1, dashed = false) {
  const geometry = new THREE.BufferGeometry().setFromPoints([a, b]);
  const lineMaterial = dashed
    ? new THREE.LineDashedMaterial({ color, dashSize: 0.18, gapSize: 0.11, linewidth: width })
    : new THREE.LineBasicMaterial({ color, linewidth: width });
  const line = new THREE.Line(geometry, lineMaterial);
  if (dashed) line.computeLineDistances();
  return line;
}

function cylinderBetween(a, b, radius, color) {
  const direction = b.clone().sub(a);
  const length = direction.length();
  const mesh = new THREE.Mesh(
    new THREE.CylinderGeometry(radius, radius, length, 12),
    material(color, { metalness: 0.35 }),
  );
  mesh.position.copy(a).add(b).multiplyScalar(0.5);
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
  return mesh;
}

function arrow(origin, direction, length, color, headLength = 0.22) {
  return new THREE.ArrowHelper(
    direction.clone().normalize(),
    origin,
    length,
    color,
    headLength,
    Math.max(0.08, headLength * 0.42),
  );
}

function facetGeometry(shape, size) {
  if (shape === "Circular") return new THREE.CircleGeometry(size / 2, 32);
  if (shape === "Hexagonal") return new THREE.CircleGeometry(size / 2, 6);
  return new THREE.PlaneGeometry(size, size);
}

function addHeliostat(group, state) {
  const mirrorSize = Math.max(0.05, Number(state.mirror_size_m));
  const baseWidth = Math.max(0.10, Number(state.base_width_m));
  const forkHeight = Math.max(0.10, Number(state.fork_height_m));
  const groundY = -forkHeight;
  const normal = simVector(state.normal).normalize();

  const base = new THREE.Mesh(
    new THREE.BoxGeometry(baseWidth, 0.08, baseWidth * 0.72),
    material(COLORS.steelDark, { metalness: 0.45 }),
  );
  base.position.set(0, groundY, 0);
  group.add(base);

  const feet = [
    new THREE.Vector3(-baseWidth * 0.43, groundY, -baseWidth * 0.27),
    new THREE.Vector3(baseWidth * 0.43, groundY, -baseWidth * 0.27),
    new THREE.Vector3(0, groundY, baseWidth * 0.32),
  ];
  for (const foot of feet) {
    group.add(cylinderBetween(foot, new THREE.Vector3(foot.x * 0.22, -0.14, foot.z * 0.22), 0.035, COLORS.steel));
  }
  group.add(cylinderBetween(new THREE.Vector3(0, groundY, 0), new THREE.Vector3(0, -0.06, 0), 0.055, COLORS.steel));

  const forkSpread = mirrorSize * 0.58;
  group.add(cylinderBetween(new THREE.Vector3(-forkSpread, -0.18, 0), new THREE.Vector3(-forkSpread, 0.24, 0), 0.035, COLORS.steel));
  group.add(cylinderBetween(new THREE.Vector3(forkSpread, -0.18, 0), new THREE.Vector3(forkSpread, 0.24, 0), 0.035, COLORS.steel));

  const mirror = new THREE.Mesh(
    new THREE.BoxGeometry(mirrorSize, mirrorSize, Math.max(0.025, mirrorSize * 0.018)),
    material(COLORS.mirror, { metalness: 0.28, roughness: 0.28 }),
  );
  mirror.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal);
  mirror.renderOrder = 2;
  group.add(mirror);

  const edge = new THREE.LineSegments(
    new THREE.EdgesGeometry(mirror.geometry),
    new THREE.LineBasicMaterial({ color: COLORS.mirrorEdge }),
  );
  edge.quaternion.copy(mirror.quaternion);
  edge.renderOrder = 3;
  group.add(edge);
}

function addReceiver(group, state) {
  const center = simVector(state.target);
  const axis = center.clone().normalize();
  const facing = axis.clone().negate();
  const up = new THREE.Vector3(0, 1, 0);
  const uAxis = new THREE.Vector3(1, 0, 0).sub(axis.clone().multiplyScalar(axis.x)).normalize();
  let vAxis = up.clone().sub(axis.clone().multiplyScalar(up.dot(axis)));
  if (vAxis.lengthSq() < 1e-8) vAxis = new THREE.Vector3(0, 0, 1);
  vAxis.normalize();
  const screenSize = Math.max(0.08, Number(state.receiver_screen_m));
  const planeQuaternion = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), facing);

  const screen = new THREE.Mesh(
    new THREE.CircleGeometry(screenSize / 2, 48),
    material(COLORS.receiverDark, { opacity: 0.28, side: THREE.DoubleSide, metalness: 0.18 }),
  );
  screen.position.copy(center).add(axis.clone().multiplyScalar(0.035));
  screen.quaternion.copy(planeQuaternion);
  group.add(screen);

  const ring = new THREE.Mesh(
    new THREE.TorusGeometry(screenSize / 2, Math.max(0.018, screenSize * 0.018), 10, 48),
    material(COLORS.receiver, { metalness: 0.35 }),
  );
  ring.position.copy(center);
  ring.quaternion.copy(planeQuaternion);
  group.add(ring);

  if (state.facet_enabled && Array.isArray(state.facets)) {
    const shape = String(state.facet_shape);
    const facetSize = Math.max(0.01, Number(state.facet_size_m));
    for (const facet of state.facets) {
      const facetMesh = new THREE.Mesh(
        facetGeometry(shape, facetSize),
        material(COLORS.receiver, { roughness: 0.36, metalness: 0.24, side: THREE.DoubleSide }),
      );
      facetMesh.position.copy(center)
        .add(uAxis.clone().multiplyScalar(Number(facet[1])))
        .add(vAxis.clone().multiplyScalar(Number(facet[2])))
        .add(axis.clone().multiplyScalar(-0.015));
      facetMesh.quaternion.copy(planeQuaternion);
      group.add(facetMesh);
    }
  }

  const groundY = -Math.max(0.1, Number(state.fork_height_m));
  const frameHalf = screenSize * 0.62;
  group.add(cylinderBetween(
    center.clone().add(uAxis.clone().multiplyScalar(-frameHalf)),
    new THREE.Vector3(center.x - uAxis.x * frameHalf, groundY, center.z - uAxis.z * frameHalf),
    0.035,
    COLORS.steel,
  ));
  group.add(cylinderBetween(
    center.clone().add(uAxis.clone().multiplyScalar(frameHalf)),
    new THREE.Vector3(center.x + uAxis.x * frameHalf, groundY, center.z + uAxis.z * frameHalf),
    0.035,
    COLORS.steel,
  ));
}

function addVectors(group, state) {
  const origin = new THREE.Vector3(0, 0, 0);
  const sun = simVector(state.sun).normalize();
  const normal = simVector(state.normal).normalize();
  const reflected = simVector(state.reflected).normalize();
  const target = simVector(state.target);
  const incomingStart = origin.clone().add(sun.clone().multiplyScalar(3.2));

  group.add(lineBetween(incomingStart, origin, COLORS.sun, 2));
  group.add(arrow(incomingStart, sun.clone().negate(), 2.95, COLORS.sun, 0.25));
  group.add(arrow(origin, normal, 1.35, COLORS.normal, 0.22));
  group.add(arrow(origin, reflected, Math.min(2.2, Math.max(1.1, target.length() * 0.30)), COLORS.ray, 0.20));
  group.add(lineBetween(origin, target, COLORS.target, 1, true));
}

function addOrientationAxes(group, groundY) {
  const origin = new THREE.Vector3(0, groundY + 0.035, 0);
  group.add(arrow(origin, new THREE.Vector3(1, 0, 0), 1.15, 0xff6b6b, 0.16));
  group.add(arrow(origin, new THREE.Vector3(0, 1, 0), 1.15, 0x8ab4f8, 0.16));
  group.add(arrow(origin, new THREE.Vector3(0, 0, -1), 1.15, 0x65d98b, 0.16));
}

function rebuild(state) {
  if (!scene) return;
  if (dynamicGroup) {
    scene.remove(dynamicGroup);
    disposeObject(dynamicGroup);
  }
  dynamicGroup = new THREE.Group();
  dynamicGroup.name = "gemelo-dinamico";
  scene.add(dynamicGroup);

  const groundY = -Math.max(0.1, Number(state.fork_height_m));
  const target = simVector(state.target);
  const gridSize = Math.max(12, Number(state.rail_length_m) + 5);
  const grid = new THREE.GridHelper(gridSize, 24, COLORS.grid, COLORS.grid);
  grid.position.set(target.x * 0.5, groundY - 0.02, target.z * 0.5);
  dynamicGroup.add(grid);
  const groundOrigin = new THREE.Vector3(0, groundY + 0.03, 0);
  const groundTarget = new THREE.Vector3(target.x, groundY + 0.03, target.z);
  const railDirection = groundTarget.clone().sub(groundOrigin);
  if (railDirection.lengthSq() > 1e-8) {
    railDirection.normalize();
    const railEnd = groundOrigin.clone().add(
      railDirection.clone().multiplyScalar(Math.min(Number(state.rail_length_m), groundOrigin.distanceTo(groundTarget))),
    );
    const lateral = new THREE.Vector3(-railDirection.z, 0, railDirection.x).normalize().multiplyScalar(0.11);
    dynamicGroup.add(cylinderBetween(groundOrigin.clone().add(lateral), railEnd.clone().add(lateral), 0.025, COLORS.steel));
    dynamicGroup.add(cylinderBetween(groundOrigin.clone().sub(lateral), railEnd.clone().sub(lateral), 0.025, COLORS.steel));
  }
  addHeliostat(dynamicGroup, state);
  addReceiver(dynamicGroup, state);
  addVectors(dynamicGroup, state);
  addOrientationAxes(dynamicGroup, groundY);
  dynamicGroup.traverse((object) => {
    if (object.isMesh) {
      object.castShadow = true;
      object.receiveShadow = true;
    }
  });

  currentTarget.copy(target).multiplyScalar(0.42);
  if (!framedOnce) {
    controls.target.copy(currentTarget);
    setView("iso");
    framedOnce = true;
  }
}

function setView(name) {
  if (!camera || !controls) return;
  const distance = Math.max(8, currentTarget.length() * 2.4 + 5);
  const center = currentTarget.clone();
  const positions = {
    iso: new THREE.Vector3(distance * 0.72, distance * 0.54, distance * 0.78),
    front: new THREE.Vector3(0, distance * 0.10, distance),
    side: new THREE.Vector3(distance, distance * 0.12, 0),
    top: new THREE.Vector3(0.01, distance, 0.01),
  };
  camera.position.copy(center).add(positions[name] || positions.iso);
  camera.up.set(0, 1, 0);
  controls.target.copy(center);
  camera.lookAt(center);
  controls.update();
}

function initScene() {
  const canvas = document.getElementById("twin3d-canvas");
  if (!canvas || canvas.dataset.initialized === "true") return Boolean(renderer);
  canvas.dataset.initialized = "true";
  scene = new THREE.Scene();
  scene.background = new THREE.Color(COLORS.background);
  scene.fog = new THREE.FogExp2(COLORS.background, 0.018);
  camera = new THREE.PerspectiveCamera(42, 1, 0.03, 250);
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.075;
  controls.screenSpacePanning = true;
  controls.minDistance = 2.2;
  controls.maxDistance = 80;
  controls.mouseButtons.LEFT = THREE.MOUSE.PAN;
  controls.mouseButtons.MIDDLE = THREE.MOUSE.DOLLY;
  controls.mouseButtons.RIGHT = THREE.MOUSE.ROTATE;
  canvas.addEventListener("contextmenu", (event) => event.preventDefault());

  scene.add(new THREE.HemisphereLight(0xd8f2ff, 0x182532, 1.55));
  const keyLight = new THREE.DirectionalLight(0xffffff, 2.2);
  keyLight.position.set(7, 12, 8);
  keyLight.castShadow = true;
  scene.add(keyLight);

  document.querySelectorAll("[data-twin-view]").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.twinView));
  });

  const resize = () => {
    const bounds = canvas.parentElement.getBoundingClientRect();
    const width = Math.max(320, Math.floor(bounds.width));
    const height = Math.max(420, Math.floor(bounds.height));
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  };
  resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(canvas.parentElement);
  resize();

  const animate = () => {
    controls.update();
    renderer.render(scene, camera);
    animationFrame = requestAnimationFrame(animate);
  };
  animate();
  return true;
}

function updateFromPayload() {
  const payload = document.querySelector(".twin-state-payload");
  if (!payload) return;
  try {
    const state = JSON.parse(payload.textContent);
    if (state.revision === lastRevision) return;
    lastRevision = state.revision;
    if (!initScene()) return;
    rebuild(state);
    const status = document.getElementById("twin3d-status");
    if (status) status.textContent = `${state.status} · AZ ${Number(state.az_deg).toFixed(2)}° · EL ${Number(state.el_deg).toFixed(2)}°`;
  } catch (error) {
    const warning = document.getElementById("twin3d-warning");
    if (warning) {
      warning.hidden = false;
      warning.textContent = `No fue posible actualizar la escena 3D: ${error.message}`;
    }
  }
}

const observer = new MutationObserver(() => queueMicrotask(updateFromPayload));
observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
window.addEventListener("DOMContentLoaded", updateFromPayload);
queueMicrotask(updateFromPayload);
window.setTimeout(updateFromPayload, 500);
window.setTimeout(updateFromPayload, 1500);
window.addEventListener("beforeunload", () => {
  if (animationFrame) cancelAnimationFrame(animationFrame);
  resizeObserver?.disconnect();
  renderer?.dispose();
});
