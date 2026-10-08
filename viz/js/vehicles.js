// Procedural vehicle models, instanced per SUMO size class.
//
// Each model is a set of boxes merged into one geometry with baked vertex
// colors: body panels are white (the per-instance SUMO color shows),
// glass, tires and trim are baked dark, headlights/taillights baked warm
// so they read as lamps at any body color. One InstancedMesh per class
// keeps the whole fleet at 3 draw calls.

import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

const MAX_PER_CLASS = 2048;

/** A box part with a baked vertex color, positioned + sized in meters. */
function part(w, h, d, x, y, z, color) {
  const geometry = new THREE.BoxGeometry(w, h, d);
  geometry.translate(x, y, z);
  const count = geometry.attributes.position.count;
  const colors = new Float32Array(count * 3);
  const c = new THREE.Color(color);
  for (let i = 0; i < count; i++) {
    colors[i * 3] = c.r;
    colors[i * 3 + 1] = c.g;
    colors[i * 3 + 2] = c.b;
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return geometry;
}

const BODY = 0xffffff; // takes the per-instance SUMO color
const GLASS = 0x2b3138; // baked dark "glass"
const TIRE = 0x14161a; // baked dark tires
const TRIM = 0xdadde2; // baked light bumper/trim
const HEADLIGHT = 0xfff3c4; // baked warm lamp
const TAILLIGHT = 0xff4030; // baked red lamp

/** Wheel = tire + slightly protruding silver hub. */
function wheel(x, y, z) {
  return [
    part(0.26, 0.64, 0.64, x, y, z, TIRE),
    part(0.3, 0.3, 0.3, x, y, z, TRIM),
  ];
}

/** Class 0: passenger sedan — hood, cabin, trunk, bumpers, lamps. ~4.6 m. */
function sedanGeometry() {
  const wheelY = 0.34;
  const frontZ = 1.5;
  const rearZ = -1.5;
  const parts = [
    // Lower body band spanning the whole car.
    part(1.76, 0.42, 4.42, 0, 0.5, 0, BODY),
    // Hood (front, slightly lower) and trunk lid (rear).
    part(1.7, 0.16, 1.15, 0, 0.74, 1.55, BODY),
    part(1.7, 0.18, 0.95, 0, 0.76, -1.68, BODY),
    // Cabin: glass box with a body-colored roof cap.
    part(1.56, 0.44, 2.05, 0, 1.0, -0.3, GLASS),
    part(1.5, 0.07, 1.75, 0, 1.24, -0.3, BODY),
    // Bumpers + lamps.
    part(1.72, 0.2, 4.5, 0, 0.32, 0, TRIM),
    part(0.34, 0.12, 0.08, -0.55, 0.62, 2.22, HEADLIGHT),
    part(0.34, 0.12, 0.08, 0.55, 0.62, 2.22, HEADLIGHT),
    part(0.36, 0.12, 0.08, -0.58, 0.64, -2.18, TAILLIGHT),
    part(0.36, 0.12, 0.08, 0.58, 0.64, -2.18, TAILLIGHT),
    ...wheel(-0.84, wheelY, frontZ),
    ...wheel(0.84, wheelY, frontZ),
    ...wheel(-0.84, wheelY, rearZ),
    ...wheel(0.84, wheelY, rearZ),
  ];
  return mergeGeometries(parts, false);
}

/** Class 1a: city bus — window band, roof AC, boarding doors. ~11 m. */
function busGeometry() {
  const parts = [
    part(2.45, 2.1, 11.2, 0, 1.62, 0, BODY),
    part(2.3, 0.72, 10.4, 0, 2.35, 0, GLASS), // window band
    part(2.2, 0.5, 2.4, 0, 2.75, 1.2, TRIM), // roof AC unit
    part(2.49, 0.16, 11.3, 0, 0.6, 0, TRIM), // skirt
    part(0.9, 1.5, 0.08, -0.78, 1.25, 4.1, GLASS), // windshield
    part(0.9, 1.5, 0.08, 0.78, 1.25, 4.1, GLASS),
    part(0.3, 0.16, 0.08, -0.85, 0.9, 5.62, HEADLIGHT),
    part(0.3, 0.16, 0.08, 0.85, 0.9, 5.62, HEADLIGHT),
    part(0.34, 0.14, 0.08, -0.88, 1.0, -5.62, TAILLIGHT),
    part(0.34, 0.14, 0.08, 0.88, 1.0, -5.62, TAILLIGHT),
    ...wheel(-1.05, 0.5, 3.6),
    ...wheel(1.05, 0.5, 3.6),
    ...wheel(-1.05, 0.5, -0.6),
    ...wheel(1.05, 0.5, -0.6),
    ...wheel(-1.05, 0.5, -3.4),
    ...wheel(1.05, 0.5, -3.4),
  ];
  return mergeGeometries(parts, false);
}

/** Class 1b: truck — cab + container cargo box. ~10 m. */
function truckGeometry() {
  const parts = [
    part(2.3, 1.9, 2.3, 0, 1.55, 3.4, BODY), // cab
    part(2.14, 0.75, 0.1, 0, 2.2, 4.5, GLASS), // cab windows
    part(2.42, 2.5, 6.8, 0, 1.85, -1.3, 0xd9dde2), // container
    part(2.44, 0.16, 6.9, 0, 0.62, -1.3, TRIM),
    part(0.32, 0.14, 0.08, -0.8, 0.85, 4.58, HEADLIGHT),
    part(0.32, 0.14, 0.08, 0.8, 0.85, 4.58, HEADLIGHT),
    part(0.34, 0.14, 0.08, -0.9, 1.0, -4.72, TAILLIGHT),
    part(0.34, 0.14, 0.08, 0.9, 1.0, -4.72, TAILLIGHT),
    ...wheel(-1.0, 0.5, 3.5),
    ...wheel(1.0, 0.5, 3.5),
    ...wheel(-1.0, 0.5, -0.9),
    ...wheel(1.0, 0.5, -0.9),
    ...wheel(-1.0, 0.5, -3.0),
    ...wheel(1.0, 0.5, -3.0),
  ];
  return mergeGeometries(parts, false);
}

/** Class 2: two-wheeler with rider. ~2.1 m. */
function bikeGeometry() {
  const parts = [
    part(0.42, 0.34, 1.85, 0, 0.68, 0, BODY),
    part(0.5, 0.06, 0.5, 0, 0.94, 0.62, TRIM), // handlebar
    part(0.36, 0.5, 0.3, 0, 1.02, 0.05, 0x3a4a5a), // rider torso
    part(0.3, 0.28, 0.28, 0, 1.38, 0.05, GLASS), // helmet
    part(0.18, 0.55, 0.18, 0, 0.34, 0.78, TIRE),
    part(0.18, 0.55, 0.18, 0, 0.34, -0.78, TIRE),
  ];
  return mergeGeometries(parts, false);
}

export class Fleet {
  constructor(scene) {
    const material = new THREE.MeshStandardMaterial({
      roughness: 0.35,
      metalness: 0.25,
      vertexColors: true,
    });
    // Four meshes: sedan, bus, truck, bike.  SUMO class 1 (long vehicles)
    // is split between bus and truck bodies by a hash of the vehicle id.
    this.meshes = [
      sedanGeometry(),
      busGeometry(),
      truckGeometry(),
      bikeGeometry(),
    ].map((geometry) => {
      const mesh = new THREE.InstancedMesh(geometry, material, MAX_PER_CLASS);
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      mesh.count = 0;
      mesh.castShadow = true;
      // The instance bounding sphere is cached from the first (empty)
      // frame and never recomputed as cars spawn — frustum culling
      // would drop the whole fleet. Four draw calls; skip culling.
      mesh.frustumCulled = false;
      scene.add(mesh);
      return mesh;
    });
    this._matrix = new THREE.Matrix4();
    this._quat = new THREE.Quaternion();
    this._axis = new THREE.Vector3(0, 1, 0);
    this._pos = new THREE.Vector3();
    this._scale = new THREE.Vector3(1, 1, 1);
    this._color = new THREE.Color();
  }

  /** Deterministic bus/truck choice from the vehicle id string. */
  static longBodyIndex(id) {
    let hash = 0;
    for (let i = 0; i < id.length; i++) {
      hash = (hash * 31 + id.charCodeAt(i)) | 0;
    }
    return (hash >>> 0) % 2 === 0 ? 1 : 2; // 1 = bus, 2 = truck
  }

  /** rows: [id, x, y, z, angleDeg, speed, r, g, b, classIdx][] */
  update(rows) {
    const buckets = [[], [], [], []];
    for (const row of rows) {
      const classIdx = row.length > 9 ? Math.min(2, Math.max(0, row[9] | 0)) : 0;
      const meshIndex =
        classIdx === 1 ? Fleet.longBodyIndex(String(row[0])) : classIdx;
      buckets[meshIndex].push(row);
    }
    buckets.forEach((bucket, meshIndex) => {
      const mesh = this.meshes[meshIndex];
      const n = Math.min(bucket.length, MAX_PER_CLASS);
      for (let i = 0; i < n; i++) {
        const row = bucket[i];
        // SUMO heading: degrees clockwise from north (+y). three: +z north.
        this._quat.setFromAxisAngle(
          this._axis,
          THREE.MathUtils.degToRad(row[4]),
        );
        this._pos.set(row[1], 0.02 + (row[3] || 0), row[2]);
        this._matrix.compose(this._pos, this._quat, this._scale);
        mesh.setMatrixAt(i, this._matrix);
        mesh.setColorAt(
          i,
          this._color.setRGB(row[6] / 255, row[7] / 255, row[8] / 255),
        );
      }
      mesh.count = n;
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    });
  }
}
