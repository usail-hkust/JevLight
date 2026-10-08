// Traffic-camera mode: a virtual surveillance camera at one junction,
// rendering the four approach directions as a 2x2 live view grid.
//
// The camera junction is chosen at random ("🎲") or by clicking an item in
// the junction list; approaches are derived from the lanes that END at the
// junction (incoming lanes), viewed from the junction looking outward.

import * as THREE from "three";

const APPROACH_RADIUS = 30; // lane end within this distance = approach
const COMPASS = [
  [0, "北 N"], [45, "东北 NE"], [90, "东 E"], [135, "东南 SE"],
  [180, "南 S"], [225, "西南 SW"], [270, "西 W"], [315, "西北 NW"],
];

function compassLabel(bearingDeg) {
  const deg = ((bearingDeg % 360) + 360) % 360;
  const index = Math.round(deg / 45) % 8;
  return COMPASS[index][1];
}

/** The four approach view directions of one junction (unit vectors),
 *  deduplicated into bearing buckets and sorted for a stable 2x2 layout. */
export function junctionApproaches(net, junction, maxViews = 4) {
  const buckets = new Map();
  for (const lane of net.lanes) {
    const shape = lane.shape;
    if (shape.length < 2) continue;
    const [ex, ey] = shape[shape.length - 1];
    if (Math.hypot(ex - junction.x, ey - junction.y) > APPROACH_RADIUS) continue;
    const [px, py] = shape[shape.length - 2];
    // Outward view direction: from the incoming lane's end back along it.
    let dx = ex - px;
    let dy = ey - py;
    const len = Math.hypot(dx, dy) || 1;
    dx /= len;
    dy /= len;
    const bearing = ((Math.atan2(dx, dy) * 180) / Math.PI + 360) % 360;
    const key = Math.round(bearing / 30) % 12;
    if (!buckets.has(key) || buckets.get(key).bearing > bearing) {
      buckets.set(key, { dx: -dx, dy: -dy, bearing });
    }
  }
  const approaches = [...buckets.values()].sort((a, b) => a.bearing - b.bearing);
  if (!approaches.length) {
    // Isolated junction: fall back to the four cardinal directions.
    return [
      { dx: 0, dy: 1, bearing: 0 },
      { dx: 1, dy: 0, bearing: 90 },
      { dx: 0, dy: -1, bearing: 180 },
      { dx: -1, dy: 0, bearing: 270 },
    ];
  }
  return approaches.slice(0, maxViews).map((a) => ({
    dx: a.dx,
    dy: a.dy,
    bearing: a.bearing,
  }));
}

/** A small surveillance pole placed at the junction corner (main-view marker). */
function buildPole() {
  const group = new THREE.Group();
  const metal = new THREE.MeshStandardMaterial({
    color: 0x8a9099,
    roughness: 0.4,
    metalness: 0.6,
  });
  const dark = new THREE.MeshStandardMaterial({ color: 0x1c2026, roughness: 0.6 });
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.3, 9, 10), metal);
  pole.position.y = 4.5;
  pole.castShadow = true;
  group.add(pole);
  const arm = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.18, 3.4), metal);
  arm.position.set(0, 8.8, 1.7);
  group.add(arm);
  const head = new THREE.Mesh(new THREE.BoxGeometry(0.7, 0.55, 1.5), dark);
  head.position.set(0, 8.5, 3.2);
  head.castShadow = true;
  group.add(head);
  const beacon = new THREE.Mesh(
    new THREE.SphereGeometry(0.12, 8, 8),
    new THREE.MeshBasicMaterial({ color: 0xff4444 }),
  );
  beacon.position.set(0, 8.85, 3.2);
  group.add(beacon);
  return group;
}

export class TrafficCam {
  /** scene: main scene (for the pole marker); net: /api/network payload. */
  constructor(scene, net) {
    this.net = net;
    this.junctions = net.tls;
    this.junction = null;
    this.approaches = [];
    this.cameras = [];
    this.pole = buildPole();
    this.pole.visible = false;
    scene.add(this.pole);
    this._aspect = 16 / 9;
  }

  /** Move the camera to a junction by id; returns the junction or null. */
  setJunction(tlsId) {
    const junction = this.junctions.find((j) => j.id === tlsId);
    if (!junction) return null;
    this.junction = junction;
    this.approaches = junctionApproaches(this.net, junction);
    this.cameras = this.approaches.map((approach) => {
      const camera = new THREE.PerspectiveCamera(58, this._aspect, 1, 4000);
      this._placeCamera(camera, approach);
      return {
        camera,
        bearing: approach.bearing,
        label: compassLabel(approach.bearing),
      };
    });
    this.pole.position.set(junction.x, 0, junction.y);
    this.pole.rotation.y = this.approaches.length
      ? Math.atan2(this.approaches[0].dx, this.approaches[0].dy)
      : 0;
    this.pole.visible = true;
    return junction;
  }

  /** Pick a junction different from the current one when possible. */
  randomJunction() {
    if (!this.junctions.length) return null;
    if (this.junctions.length === 1) return this.setJunction(this.junctions[0].id);
    let pick = this.junction;
    while (!pick || pick.id === this.junction?.id) {
      pick = this.junctions[Math.floor(Math.random() * this.junctions.length)];
    }
    return this.setJunction(pick.id);
  }

  /** Mount each sub-camera on a 9 m pole set back from the junction center,
   *  looking down its approach road. */
  _placeCamera(camera, approach) {
    const { x, y } = this.junction;
    const back = 12;
    const height = 9;
    camera.position.set(
      x - approach.dx * back,
      height,
      y - approach.dy * back,
    );
    camera.lookAt(
      x + approach.dx * 90,
      height * 0.35,
      y + approach.dy * 90,
    );
  }

  setAspect(aspect) {
    this._aspect = aspect;
    for (const view of this.cameras) {
      view.camera.aspect = aspect;
      view.camera.updateProjectionMatrix();
    }
  }

  hide() {
    this.pole.visible = false;
  }
}
