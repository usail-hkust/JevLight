// Procedural vehicle models, instanced per SUMO size class.
//
// Each model is several boxes merged into one geometry with baked vertex
// colors: body parts are white (so the per-instance SUMO color shows), the
// cabin glass and wheels are dark gray (they stay dark whatever the body
// color). One InstancedMesh per class keeps the whole fleet at 3 draw calls.

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

/** Class 0: passenger car (body + cabin + 4 wheels + bumpers), ~4.6 m. */
function sedanGeometry() {
  const wheelY = 0.34;
  const wheelZ = 1.45;
  const wheelX = 0.82;
  const parts = [
    part(1.76, 0.52, 4.35, 0, 0.62, 0, BODY),
    part(1.6, 0.5, 2.3, 0, 1.1, -0.25, GLASS),
    part(1.68, 0.1, 4.45, 0, 0.34, 0, TRIM),
    part(0.24, 0.62, 0.7, -wheelX, wheelY, wheelZ, TIRE),
    part(0.24, 0.62, 0.7, wheelX, wheelY, wheelZ, TIRE),
    part(0.24, 0.62, 0.7, -wheelX, wheelY, -wheelZ, TIRE),
    part(0.24, 0.62, 0.7, wheelX, wheelY, -wheelZ, TIRE),
  ];
  return mergeGeometries(parts, false);
}

/** Class 1: long vehicle (bus / truck / trailer), ~10 m. */
function longVehicleGeometry() {
  const parts = [
    part(2.4, 2.3, 9.6, 0, 1.75, 0.2, BODY),
    part(2.2, 1.0, 2.2, 0, 2.45, 3.4, GLASS), // windshield band
    part(2.44, 0.14, 9.7, 0, 0.62, 0.2, TRIM),
    part(0.3, 1.0, 0.7, -1.05, 0.5, 3.3, TIRE),
    part(0.3, 1.0, 0.7, 1.05, 0.5, 3.3, TIRE),
    part(0.3, 1.0, 0.7, -1.05, 0.5, -0.4, TIRE),
    part(0.3, 1.0, 0.7, 1.05, 0.5, -0.4, TIRE),
    part(0.3, 1.0, 0.7, -1.05, 0.5, -2.4, TIRE),
    part(0.3, 1.0, 0.7, 1.05, 0.5, -2.4, TIRE),
  ];
  return mergeGeometries(parts, false);
}

/** Class 2: two-wheeler (bicycle / moped / motorcycle), ~2.1 m. */
function bikeGeometry() {
  const parts = [
    part(0.5, 0.4, 1.9, 0, 0.75, 0, BODY),
    part(0.42, 0.34, 0.42, 0, 1.06, 0.55, GLASS), // helmet-ish head
    part(0.16, 0.62, 0.16, 0, 0.34, 0.72, TIRE),
    part(0.16, 0.62, 0.16, 0, 0.34, -0.72, TIRE),
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
    this.meshes = [sedanGeometry, longVehicleGeometry, bikeGeometry].map(
      (build) => {
        const mesh = new THREE.InstancedMesh(build(), material, MAX_PER_CLASS);
        mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
        mesh.count = 0;
        mesh.castShadow = true;
        scene.add(mesh);
        return mesh;
      },
    );
    this._matrix = new THREE.Matrix4();
    this._quat = new THREE.Quaternion();
    this._axis = new THREE.Vector3(0, 1, 0);
    this._pos = new THREE.Vector3();
    this._scale = new THREE.Vector3(1, 1, 1);
    this._color = new THREE.Color();
  }

  /** rows: [id, x, y, z, angleDeg, speed, r, g, b, classIdx][] */
  update(rows) {
    const buckets = [[], [], []];
    for (const row of rows) {
      const classIdx = row.length > 9 ? Math.min(2, Math.max(0, row[9] | 0)) : 0;
      buckets[classIdx].push(row);
    }
    buckets.forEach((bucket, classIdx) => {
      const mesh = this.meshes[classIdx];
      const n = Math.min(bucket.length, MAX_PER_CLASS);
      for (let i = 0; i < n; i++) {
        const [, x, y, z, angleDeg, , r, g, b] = bucket[i];
        // SUMO heading: degrees clockwise from north (+y). three: +z north.
        this._quat.setFromAxisAngle(
          this._axis,
          THREE.MathUtils.degToRad(angleDeg),
        );
        this._pos.set(x, 0.02 + (z || 0), y);
        this._matrix.compose(this._pos, this._quat, this._scale);
        mesh.setMatrixAt(i, this._matrix);
        mesh.setColorAt(i, this._color.setRGB(r / 255, g / 255, b / 255));
      }
      mesh.count = n;
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    });
  }
}
