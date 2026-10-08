// Traffic signals: realistic mast poles with three-lamp heads facing each
// approach.  Junctions switch lamps by their live SUMO state (majority
// color).  Large networks fall back to one compact head per junction to
// keep the draw-call count sane.

import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { junctionApproaches } from "/js/traffic_cam.js";

const DETAILED_MAX_JUNCTIONS = 60;

const LAMP_GEO = new THREE.SphereGeometry(0.3, 10, 8);
const METAL = new THREE.MeshStandardMaterial({
  color: 0x2f343b,
  roughness: 0.45,
  metalness: 0.65,
});
const HOUSING = new THREE.MeshStandardMaterial({
  color: 0x1f2329,
  roughness: 0.6,
});

/** One mast with an arm reaching over the approach + a 3-lamp housing.
 *  Returns { mast (merged geometry), lampOffsets: [r,y,g] world offsets }. */
function headGeometry(junction, approach) {
  const dir = new THREE.Vector3(approach.dx, 0, approach.dy); // outward
  const perp = new THREE.Vector3(-dir.z, 0, dir.x);
  const base = new THREE.Vector3(junction.x, 0, junction.y)
    .addScaledVector(dir, -7)
    .addScaledVector(perp, 9);

  const parts = [];
  const pole = new THREE.CylinderGeometry(0.14, 0.2, 6.4, 8);
  pole.translate(base.x, 3.2, base.z);
  parts.push(pole);
  const armLength = 11;
  const arm = new THREE.BoxGeometry(0.16, 0.16, armLength);
  // Rotate the arm to run from the pole top toward the junction center.
  const armCenter = base.clone().addScaledVector(perp, -armLength / 2);
  arm.rotateY(Math.atan2(perp.x, perp.z));
  arm.translate(armCenter.x, 6.3, armCenter.z);
  parts.push(arm);
  const headCenter = base.clone().addScaledVector(perp, -armLength);
  const housing = new THREE.BoxGeometry(0.62, 1.7, 0.42);
  housing.translate(headCenter.x, 5.6, headCenter.z);
  parts.push(housing);

  const mast = mergeGeometries(parts, false);
  parts.forEach((part) => part.dispose());

  // Lamps stacked red over yellow over green, facing the oncoming traffic.
  const lampOffsets = ["r", "y", "g"].map((_, index) => {
    const offset = headCenter
      .clone()
      .addScaledVector(dir, -0.28)
      .setY(6.15 - index * 0.55);
    return offset;
  });
  return { mast, lampOffsets };
}

export function buildSignals(scene, net) {
  const detailed = net.tls.length <= DETAILED_MAX_JUNCTIONS;
  const controllers = []; // [{ set(kind) }]

  for (const junction of net.tls) {
    const approaches = junctionApproaches(net, junction);
    const lampParts = { r: [], y: [], g: [] };
    const masts = [];
    if (detailed) {
      for (const approach of approaches) {
        const { mast, lampOffsets } = headGeometry(junction, approach);
        masts.push(mast);
        ["r", "y", "g"].forEach((kind, index) => {
          const lamp = LAMP_GEO.clone();
          const offset = lampOffsets[index];
          lamp.translate(offset.x, offset.y, offset.z);
          lampParts[kind].push(lamp);
        });
      }
    } else {
      // Compact fallback: one pole + housing per junction.
      const pole = new THREE.CylinderGeometry(0.14, 0.2, 6.4, 8);
      pole.translate(junction.x, 3.2, junction.y);
      masts.push(pole);
      const housing = new THREE.BoxGeometry(0.62, 1.7, 0.42);
      housing.translate(junction.x, 5.6, junction.y);
      masts.push(housing);
      ["r", "y", "g"].forEach((kind, index) => {
        const lamp = LAMP_GEO.clone();
        lamp.translate(junction.x, 6.15 - index * 0.55, junction.y);
        lampParts[kind].push(lamp);
      });
    }

    scene.add(new THREE.Mesh(mergeGeometries(masts, false), METAL));

    const lamps = {};
    for (const kind of ["r", "y", "g"]) {
      const material = new THREE.MeshStandardMaterial({
        color: kind === "r" ? 0x5a1512 : kind === "y" ? 0x5a4512 : 0x11402a,
        emissive: kind === "r" ? 0xff2a1e : kind === "y" ? 0xffb020 : 0x2aff6a,
        emissiveIntensity: 0.04,
        roughness: 0.35,
      });
      const merged = mergeGeometries(lampParts[kind], false);
      lampParts[kind].forEach((part) => part.dispose());
      const mesh = new THREE.Mesh(merged, material);
      scene.add(mesh);
      lamps[kind] = { material, mesh };
    }

    controllers.push({
      junctionId: junction.id,
      set(kind) {
        for (const key of ["r", "y", "g"]) {
          lamps[key].material.emissiveIntensity = key === kind ? 1.6 : 0.04;
        }
      },
    });
  }

  const byId = new Map(controllers.map((c) => [c.junctionId, c]));
  return {
    /** Apply live SUMO states: majority color per junction. */
    update(states) {
      for (const [id, state] of Object.entries(states)) {
        const controller = byId.get(id);
        if (!controller) continue;
        let r = 0, y = 0, g = 0;
        for (const ch of state) {
          if (ch === "r" || ch === "o") r++;
          else if (ch === "y") y++;
          else if (ch === "G" || ch === "g") g++;
        }
        controller.set(r >= y && r >= g ? "r" : y >= g ? "y" : "g");
      }
    },
  };
}
