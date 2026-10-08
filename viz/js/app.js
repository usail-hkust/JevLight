// JevLight 3D — SUMO live visualization (three.js).
// Talks to scripts/serve_3d.py: GET /api/network once, then SSE frames.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const MAX_VEHICLES = 4096;
const VEHICLE_SIZE = [1.8, 1.5, 4.6]; // width, height, length (meters)

const state = {
  net: null,
  playing: true,
  frames: 0,
  lastFrameAt: 0,
  stepsPerSecond: 0,
};

// --------------------------------------------------------------------- //
// Scene
// --------------------------------------------------------------------- //

const canvas = document.getElementById("scene");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b0e13);
scene.fog = new THREE.Fog(0x0b0e13, 1500, 6000);

const camera = new THREE.PerspectiveCamera(
  55,
  window.innerWidth / window.innerHeight,
  1,
  30000,
);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.maxPolarAngle = Math.PI / 2.05; // keep the camera above ground

scene.add(new THREE.HemisphereLight(0xbfd4ff, 0x1a1f29, 0.9));
const sun = new THREE.DirectionalLight(0xffffff, 1.1);
sun.position.set(400, 900, 300);
scene.add(sun);

window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// --------------------------------------------------------------------- //
// Road network
// --------------------------------------------------------------------- //

/** A flat ribbon (triangle strip) along a 2D polyline. */
function ribbonGeometry(points, width) {
  const clean = [];
  for (const p of points) {
    const prev = clean[clean.length - 1];
    if (!prev || Math.hypot(p[0] - prev[0], p[1] - prev[1]) > 0.05) clean.push(p);
  }
  if (clean.length < 2) return null;
  const half = width / 2;
  const positions = [];
  const indices = [];
  const at = (i) => {
    const p = clean[i];
    const a = clean[Math.max(0, i - 1)];
    const b = clean[Math.min(clean.length - 1, i + 1)];
    let dx = b[0] - a[0];
    let dy = b[1] - a[1];
    const len = Math.hypot(dx, dy) || 1;
    dx /= len;
    dy /= len;
    return [p, [-dy * half, dx * half]];
  };
  for (let i = 0; i < clean.length; i++) {
    const [p, n] = at(i);
    positions.push(p[0] + n[0], 0.05, p[1] + n[1]);
    positions.push(p[0] - n[0], 0.05, p[1] - n[1]);
    if (i > 0) {
      const base = (i - 1) * 2;
      indices.push(base, base + 1, base + 2, base + 1, base + 3, base + 2);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(positions, 3),
  );
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function buildNetwork(net) {
  document.getElementById("banner").textContent = "building road network…";

  const roadMaterial = new THREE.MeshStandardMaterial({
    color: 0x2c3442,
    roughness: 0.95,
    metalness: 0.05,
  });
  const laneGroup = new THREE.Group();
  for (const lane of net.lanes) {
    const geometry = ribbonGeometry(lane.shape, Math.max(lane.width, 2.5));
    if (geometry) laneGroup.add(new THREE.Mesh(geometry, roadMaterial));
  }
  scene.add(laneGroup);

  // Ground below the roads.
  const { min, max } = net.bounds;
  const cx = (min[0] + max[0]) / 2;
  const cz = (min[1] + max[1]) / 2;
  const size = Math.max(max[0] - min[0], max[1] - min[1]) * 1.4;
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(size, size),
    new THREE.MeshStandardMaterial({ color: 0x10141b, roughness: 1 }),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.position.set(cx, -0.4, cz);
  scene.add(ground);
  const grid = new THREE.GridHelper(size, 40, 0x1c2330, 0x161c27);
  grid.position.set(cx, -0.35, cz);
  scene.add(grid);

  // Traffic-light markers.
  const tlsMeshes = new Map();
  const tlsGeometry = new THREE.SphereGeometry(4.5, 16, 12);
  for (const tls of net.tls) {
    const mesh = new THREE.Mesh(
      tlsGeometry,
      new THREE.MeshStandardMaterial({
        color: 0x7d8798,
        emissive: 0x000000,
        roughness: 0.4,
      }),
    );
    mesh.position.set(tls.x, 7, tls.y);
    scene.add(mesh);
    tlsMeshes.set(tls.id, mesh);
  }
  buildTlsChips(net.tls);

  fitCamera(net.bounds);
  document.getElementById("banner").style.display = "none";
  return tlsMeshes;
}

let homeCamera = null;
function fitCamera(bounds) {
  const { min, max } = bounds;
  const cx = (min[0] + max[0]) / 2;
  const cz = (min[1] + max[1]) / 2;
  const span = Math.max(max[0] - min[0], max[1] - min[1]);
  const distance = span * 1.15;
  camera.position.set(cx + distance * 0.35, distance * 0.85, cz + distance * 0.75);
  controls.target.set(cx, 0, cz);
  controls.update();
  homeCamera = { position: camera.position.clone(), target: controls.target.clone() };
}

// --------------------------------------------------------------------- //
// Vehicles (instanced)
// --------------------------------------------------------------------- //

const vehicleMesh = new THREE.InstancedMesh(
  new THREE.BoxGeometry(...VEHICLE_SIZE),
  new THREE.MeshStandardMaterial({ roughness: 0.5, metalness: 0.15 }),
  MAX_VEHICLES,
);
vehicleMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
vehicleMesh.count = 0;
scene.add(vehicleMesh);

const _matrix = new THREE.Matrix4();
const _quat = new THREE.Quaternion();
const _axis = new THREE.Vector3(0, 1, 0);
const _pos = new THREE.Vector3();
const _scale = new THREE.Vector3(1, 1, 1);
const _color = new THREE.Color();

function updateVehicles(rows) {
  const n = Math.min(rows.length, MAX_VEHICLES);
  for (let i = 0; i < n; i++) {
    const [, x, y, z, angleDeg, , r, g, b] = rows[i];
    // SUMO heading: degrees clockwise from north (+y). three: +z is north.
    _quat.setFromAxisAngle(_axis, THREE.MathUtils.degToRad(angleDeg));
    _pos.set(x, 0.75 + (z || 0), y);
    _matrix.compose(_pos, _quat, _scale);
    vehicleMesh.setMatrixAt(i, _matrix);
    vehicleMesh.setColorAt(i, _color.setRGB(r / 255, g / 255, b / 255));
  }
  vehicleMesh.count = n;
  vehicleMesh.instanceMatrix.needsUpdate = true;
  if (vehicleMesh.instanceColor) vehicleMesh.instanceColor.needsUpdate = true;
}

// --------------------------------------------------------------------- //
// Traffic lights
// --------------------------------------------------------------------- //

let tlsMeshes = new Map();

function tlsColor(state) {
  let r = 0, y = 0, g = 0;
  for (const ch of state) {
    if (ch === "r" || ch === "o") r++;
    else if (ch === "y") y++;
    else if (ch === "G" || ch === "g") g++;
  }
  if (r >= y && r >= g) return "r";
  if (y >= g) return "y";
  return "g";
}

const TLS_MATERIAL = {
  r: { color: 0xff5d5d, emissive: 0x5a1010 },
  y: { color: 0xffd166, emissive: 0x5a4a10 },
  g: { color: 0x3ddc84, emissive: 0x0f5a2c },
};

function updateTrafficLights(states) {
  for (const [id, state] of Object.entries(states)) {
    const mesh = tlsMeshes.get(id);
    if (!mesh) continue;
    const kind = tlsColor(state);
    mesh.material.color.setHex(TLS_MATERIAL[kind].color);
    mesh.material.emissive.setHex(TLS_MATERIAL[kind].emissive);
    const chip = document.getElementById(`tls-${cssId(id)}`);
    if (chip) chip.className = `tls ${kind}`;
  }
}

function cssId(id) {
  return id.replace(/[^a-zA-Z0-9_-]/g, "_");
}

function buildTlsChips(tlsList) {
  const bar = document.getElementById("tlsbar");
  for (const tls of tlsList) {
    const chip = document.createElement("div");
    chip.id = `tls-${cssId(tls.id)}`;
    chip.className = "tls";
    chip.innerHTML = `<span class="dot"></span>${tls.id}`;
    bar.appendChild(chip);
  }
}

// --------------------------------------------------------------------- //
// HUD + commands
// --------------------------------------------------------------------- //

const el = (id) => document.getElementById(id);

function command(payload) {
  fetch("/api/command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).catch((err) => console.error("command failed", err));
}

function setPlaying(playing) {
  state.playing = playing;
  el("play").textContent = playing ? "⏸ Pause" : "▶ Play";
}

el("play").addEventListener("click", () => {
  const next = !state.playing;
  setPlaying(next);
  command({ action: next ? "play" : "pause" });
});
el("step").addEventListener("click", () => {
  setPlaying(false);
  command({ action: "pause" });
  command({ action: "step" });
});
el("speed").addEventListener("change", (event) => {
  command({ action: "speed", speed: parseFloat(event.target.value) });
});
el("cam").addEventListener("click", () => {
  if (homeCamera) {
    camera.position.copy(homeCamera.position);
    controls.target.copy(homeCamera.target);
    controls.update();
  }
});

function updateHud(frame) {
  el("time").textContent = frame.t.toFixed(0);
  el("vehicles").textContent = frame.vehicles.length;
  state.frames += 1;
  const now = performance.now();
  if (now - state.lastFrameAt > 1000) {
    state.stepsPerSecond =
      (state.frames * 1000) / (now - state.lastFrameAt);
    state.frames = 0;
    state.lastFrameAt = now;
    el("rate").textContent = state.stepsPerSecond.toFixed(1);
  }
}

// --------------------------------------------------------------------- //
// Streaming
// --------------------------------------------------------------------- //

function connectStream() {
  const source = new EventSource("/api/stream");
  source.addEventListener("init", (event) => {
    const meta = JSON.parse(event.data);
    setPlaying(meta.playing);
    el("speed").value = String(meta.speed);
  });
  source.addEventListener("frame", (event) => {
    const frame = JSON.parse(event.data);
    updateVehicles(frame.vehicles);
    updateTrafficLights(frame.tls);
    updateHud(frame);
  });
  source.onerror = () => {
    el("banner").style.display = "";
    el("banner").textContent = "connection lost — retrying…";
  };
  source.onopen = () => {
    el("banner").style.display = "none";
  };
}

async function boot() {
  const response = await fetch("/api/network");
  if (!response.ok) throw new Error(`/api/network ${response.status}`);
  state.net = await response.json();
  tlsMeshes = buildNetwork(state.net);
  connectStream();
}

boot().catch((err) => {
  el("banner").textContent = `failed to start: ${err}`;
  console.error(err);
});

// Render loop.
(function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
})();
