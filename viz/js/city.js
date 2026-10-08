// City scene: sidewalks, asphalt lanes, road markings, zebra crossings and
// procedural street buildings, all derived from the SUMO network payload.

import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

const LANE_Y = 0.04; // asphalt sits just above the sidewalk ribbon
const MARK_Y = 0.06; // markings above asphalt

// --------------------------------------------------------------------- //
// Geometry helpers
// --------------------------------------------------------------------- //

/** Deduplicate a polyline and drop zero-length segments. */
function cleanPolyline(points, epsilon = 0.05) {
  const clean = [];
  for (const p of points) {
    const prev = clean[clean.length - 1];
    if (!prev || Math.hypot(p[0] - prev[0], p[1] - prev[1]) > epsilon) {
      clean.push(p);
    }
  }
  return clean;
}

/**
 * A flat horizontal ribbon (triangle strip) along a 2D polyline.
 * Returns positions only; caller supplies y and material color.
 */
function ribbonPositions(points, width, y) {
  const clean = cleanPolyline(points);
  if (clean.length < 2) return null;
  const half = width / 2;
  const positions = [];
  for (let i = 0; i < clean.length; i++) {
    const p = clean[i];
    const a = clean[Math.max(0, i - 1)];
    const b = clean[Math.min(clean.length - 1, i + 1)];
    let dx = b[0] - a[0];
    let dy = b[1] - a[1];
    const len = Math.hypot(dx, dy) || 1;
    dx /= len;
    dy /= len;
    const nx = -dy * half;
    const ny = dx * half;
    positions.push(p[0] + nx, y, p[1] + ny, p[0] - nx, y, p[1] - ny);
  }
  return { clean, positions };
}

function ribbonGeometry(points, width, y) {
  const ribbon = ribbonPositions(points, width, y);
  if (!ribbon) return null;
  const indices = [];
  for (let i = 1; i < ribbon.clean.length; i++) {
    const base = (i - 1) * 2;
    indices.push(base, base + 1, base + 2, base + 1, base + 3, base + 2);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(ribbon.positions, 3),
  );
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

/** A rotated marking quad: center (x,y), size along dir (sl) / across (sw). */
function markingQuadDir(x, y, dirX, dirY, sl, sw, z = MARK_Y) {
  const g = new THREE.PlaneGeometry(sw, sl); // width across, length along dir
  g.rotateX(-Math.PI / 2);
  g.rotateY(Math.atan2(dirX, dirY));
  g.translate(x, z, y);
  return g;
}

// Deterministic hash-based pseudo-random in [0,1) for stable cities.
function hash01(a, b, c = 0) {
  let h = (a * 374761393 + b * 668265263 + c * 2147483647) | 0;
  h = (h ^ (h >> 13)) * 1274126177;
  h = h ^ (h >> 16);
  return ((h >>> 0) % 100000) / 100000;
}

// --------------------------------------------------------------------- //
// Buildings
// --------------------------------------------------------------------- //

const BUILDING_PALETTE = [
  0xb8b2a7, 0xa89f93, 0xc4bdb2, 0x9b8f82, 0xb0a396, 0x8f867c, 0xcac2b5,
  0xa39890,
];

/** Grid index over lane segments for fast point-to-road distance checks. */
class SegmentGrid {
  constructor(net, cell = 40) {
    this.cell = cell;
    this.cells = new Map();
    for (const lane of net.lanes) {
      const clean = cleanPolyline(lane.shape);
      for (let i = 0; i < clean.length - 1; i++) {
        const [ax, ay] = clean[i];
        const [bx, by] = clean[i + 1];
        const key = `${Math.floor(((ax + bx) / 2) / cell)}:${Math.floor(((ay + by) / 2) / cell)}`;
        if (!this.cells.has(key)) this.cells.set(key, []);
        this.cells.get(key).push([ax, ay, bx, by]);
      }
    }
  }

  /** Distance from (x,y) to the nearest lane segment (checked with a ring
   *  radius in grid cells, so short probe radii stay cheap). */
  distanceToRoad(x, y, maxRadius) {
    const cell = this.cell;
    const cx = Math.floor(x / cell);
    const cy = Math.floor(y / cell);
    const rings = Math.ceil(maxRadius / cell) + 1;
    let best = Infinity;
    for (let rx = -rings; rx <= rings; rx++) {
      for (let ry = -rings; ry <= rings; ry++) {
        const bucket = this.cells.get(`${cx + rx}:${cy + ry}`);
        if (!bucket) continue;
        for (const [ax, ay, bx, by] of bucket) {
          best = Math.min(best, pointSegmentDistance(x, y, ax, ay, bx, by));
          if (best < 1) return best; // close enough for any clearance test
        }
      }
    }
    return best;
  }
}

function pointSegmentDistance(px, py, ax, ay, bx, by) {
  const dx = bx - ax;
  const dy = by - ay;
  const lengthSquared = dx * dx + dy * dy;
  const t = lengthSquared
    ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / lengthSquared))
    : 0;
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

/**
 * Street-wall buildings along both sides of every road.  Candidate lots
 * are pushed sideways off the sampled lane, then VALIDATED against the
 * real distance to every lane segment (divided carriageways, wide roads
 * and nearby parallel streets are all handled by the same check): a lot
 * must clear the full road corridor plus its own half-depth, or it is
 * dropped.  Junction corners stay open.
 */
function buildBuildings(net) {
  const junctions = net.tls.map((tls) => [tls.x, tls.y]);
  const grid = new SegmentGrid(net);
  const lots = [];
  const taken = new Set();

  for (const lane of net.lanes) {
    const clean = cleanPolyline(lane.shape);
    if (clean.length < 2) continue;
    for (let side = -1; side <= 1; side += 2) {
      for (let i = 0; i < clean.length - 1; i++) {
        const [ax, ay] = clean[i];
        const [bx, by] = clean[i + 1];
        const segLen = Math.hypot(bx - ax, by - ay);
        if (segLen < 40) continue; // junction-adjacent: keep corners open
        const dx = (bx - ax) / segLen;
        const dy = (by - ay) / segLen;
        const nx = -dy * side;
        const ny = dx * side;
        for (let s = 20; s < segLen - 20; s += 30) {
          const px = ax + dx * s;
          const py = ay + dy * s;
          let nearJunction = false;
          for (const [jx, jy] of junctions) {
            if (Math.hypot(jx - px, jy - py) < 40) {
              nearJunction = true;
              break;
            }
          }
          if (nearJunction) continue;
          const r1 = hash01(px | 0, py | 0, 1 + (side > 0 ? 8 : 0));
          const r2 = hash01(px | 0, py | 0, 2 + (side > 0 ? 8 : 0));
          const r3 = hash01(px | 0, py | 0, 3 + (side > 0 ? 8 : 0));
          const depth = 10 + r2 * 8;
          const width = 12 + r2 * 8;
          // Push the lot out until it clears every road by margin + its
          // own half-depth (the opposite carriageway is a lane too, so
          // divided roads push buildings past the whole corridor).
          let placed = null;
          for (let offset = 12 + depth / 2; offset < 60 + depth / 2; offset += 10) {
            const cx = px + nx * offset;
            const cy = py + ny * offset;
            if (grid.distanceToRoad(cx, cy, offset + 40) > 9 + depth / 2) {
              placed = [cx, cy];
              break;
            }
          }
          if (!placed) continue;
          const key = `${Math.round(placed[0] / 16)}:${Math.round(placed[1] / 16)}`;
          if (taken.has(key)) continue;
          taken.add(key);
          const floors = 2 + Math.floor(r1 * 5) + (r3 > 0.94 ? 7 : 0);
          lots.push({
            x: placed[0],
            z: placed[1],
            w: width,
            d: depth,
            h: floors * 3.2 + 1.5,
            color: BUILDING_PALETTE[Math.floor(r3 * BUILDING_PALETTE.length)],
          });
        }
      }
    }
  }

  const geometry = new THREE.BoxGeometry(1, 1, 1);
  geometry.translate(0, 0.5, 0); // grow from the ground
  const mesh = new THREE.InstancedMesh(
    geometry,
    new THREE.MeshStandardMaterial({ roughness: 0.9, metalness: 0.05 }),
    Math.max(lots.length, 1),
  );
  const matrix = new THREE.Matrix4();
  const color = new THREE.Color();
  lots.forEach((lot, index) => {
    matrix.makeRotationY(hash01(lot.x | 0, lot.z | 0, 4) * 0.14 - 0.07);
    matrix.scale(new THREE.Vector3(lot.w, lot.h, lot.d));
    matrix.setPosition(lot.x, 0, lot.z);
    mesh.setMatrixAt(index, matrix);
    mesh.setColorAt(index, color.setHex(lot.color));
  });
  mesh.count = lots.length;
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  mesh.instanceMatrix.needsUpdate = true;
  if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  if (mesh.count) mesh.computeBoundingSphere(); // cull against real extent
  return mesh;
}

// --------------------------------------------------------------------- //
// Markings: lane dashes, stop lines, zebra crossings
// --------------------------------------------------------------------- //

function buildMarkings(net) {
  const junctions = net.tls.map((tls) => [tls.x, tls.y]);
  const parts = [];
  const bigNetwork = net.lanes.length > 400;
  const dashStep = bigNetwork ? 9 : 6; // dash every N meters (perf on NYC)

  for (const lane of net.lanes) {
    const clean = cleanPolyline(lane.shape);
    if (clean.length < 2) continue;

    // Dashed center line along the lane.
    for (let i = 0; i < clean.length - 1; i++) {
      const [ax, ay] = clean[i];
      const [bx, by] = clean[i + 1];
      const segLen = Math.hypot(bx - ax, by - ay);
      if (segLen < 4) continue;
      const dx = (bx - ax) / segLen;
      const dy = (by - ay) / segLen;
      for (let s = 3; s < segLen - 3; s += dashStep) {
        const px = ax + dx * (s + 1.5);
        const py = ay + dy * (s + 1.5);
        parts.push(markingQuadDir(px, py, dx, dy, 3, 0.15));
      }
    }

    // Stop line + zebra crossing where the lane ends at a junction.
    const [ex, ey] = clean[clean.length - 1];
    const [px, py] = clean[clean.length - 2];
    for (const [jx, jy] of junctions) {
      if (Math.hypot(jx - ex, jy - ey) > 26) continue;
      let dx = ex - px;
      let dy = ey - py;
      const len = Math.hypot(dx, dy) || 1;
      dx /= len;
      dy /= len;
      const nx = -dy;
      const ny = dx;
      const w = lane.width;
      // Stop bar across the lane, 1 m before the junction end.
      const sx = ex - dx * 1.2;
      const sy = ey - dy * 1.2;
      parts.push(markingQuadDir(sx, sy, dx, dy, 0.45, w));
      // Zebra: five stripes behind the stop bar.
      for (let z = 2.2; z <= 6.2; z += 1.0) {
        const zx = ex - dx * z;
        const zy = ey - dy * z;
        parts.push(markingQuadDir(zx, zy, dx, dy, 0.55, w));
      }
      break;
    }
  }
  if (!parts.length) return null;
  const merged = mergeGeometries(parts, false);
  parts.forEach((part) => part.dispose());
  return new THREE.Mesh(
    merged,
    new THREE.MeshStandardMaterial({
      color: 0xf2f0e8,
      roughness: 0.85,
    }),
  );
}

// --------------------------------------------------------------------- //
// Public entry
// --------------------------------------------------------------------- //

/** Build the whole static city: ground, sidewalks, roads, markings,
 *  buildings. Returns the THREE.Group plus network bounds info. */
export function buildCity(net) {
  const group = new THREE.Group();
  const { min, max } = net.bounds;
  const cx = (min[0] + max[0]) / 2;
  const cz = (min[1] + max[1]) / 2;
  const span = Math.max(max[0] - min[0], max[1] - min[1]) * 1.6;

  // Ground: park-like base under the whole district.
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(span, span),
    new THREE.MeshStandardMaterial({ color: 0x3d4a3a, roughness: 1 }),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.position.set(cx, -0.35, cz);
  ground.receiveShadow = true;
  group.add(ground);

  // Sidewalk ribbon under every lane (wider, concrete), then asphalt.
  const sidewalkMaterial = new THREE.MeshStandardMaterial({
    color: 0x9a978f,
    roughness: 0.95,
  });
  const asphaltMaterial = new THREE.MeshStandardMaterial({
    color: 0x33363c,
    roughness: 0.92,
  });
  for (const lane of net.lanes) {
    const sidewalk = ribbonGeometry(lane.shape, lane.width + 5.0, 0.02);
    if (sidewalk) {
      const mesh = new THREE.Mesh(sidewalk, sidewalkMaterial);
      mesh.receiveShadow = true;
      group.add(mesh);
    }
    const asphalt = ribbonGeometry(lane.shape, lane.width, LANE_Y);
    if (asphalt) {
      const mesh = new THREE.Mesh(asphalt, asphaltMaterial);
      mesh.receiveShadow = true;
      group.add(mesh);
    }
  }

  const markings = buildMarkings(net);
  if (markings) group.add(markings);
  group.add(buildBuildings(net));
  return group;
}
