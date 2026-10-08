// Traffic signals: mast poles with three-lamp heads, one per approach.
// Each head is colored from the EXACT characters of the live SUMO state
// string that belong to its approach's incoming lane (via the network's
// lane -> signal-link map); without a link map, heads fall back to equal
// chunks of the state string.  Large networks get one compact head per
// junction to keep the draw-call count sane.

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

function majorityKind(state, indices) {
  if (indices && indices.length) {
    let r = 0, y = 0, g = 0;
    for (const index of indices) {
      const ch = state[index];
      if (ch === "r" || ch === "o") r++;
      else if (ch === "y") y++;
      else if (ch === "G" || ch === "g") g++;
    }
    if (r + y + g === 0) return "r";
    return r >= y && r >= g ? "r" : y >= g ? "y" : "g";
  }
  return null;
}

/** One mast with an arm reaching over the approach + a 3-lamp housing.
 *  Returns { mast (merged geometry), lampPositions: [r,y,g] world spots }. */
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
  const lampPositions = [0, 1, 2].map((index) =>
    headCenter
      .clone()
      .addScaledVector(dir, -0.28)
      .setY(6.15 - index * 0.55),
  );
  return { mast, lampPositions };
}

function lampMaterial(kind) {
  return new THREE.MeshStandardMaterial({
    color: kind === "r" ? 0x5a1512 : kind === "y" ? 0x5a4512 : 0x11402a,
    emissive: kind === "r" ? 0xff2a1e : kind === "y" ? 0xffb020 : 0x2aff6a,
    emissiveIntensity: 0.04,
    roughness: 0.35,
  });
}

export function buildSignals(scene, net) {
  const detailed = net.tls.length <= DETAILED_MAX_JUNCTIONS;
  const controllers = []; // [{ id, heads: [{ lamps, indices }] }]

  for (const junction of net.tls) {
    const approaches = junctionApproaches(net, junction);
    const laneLinks = junction.lane_links || {};
    const heads = [];
    const masts = [];

    if (detailed) {
      for (const approach of approaches) {
        const { mast, lampPositions } = headGeometry(junction, approach);
        masts.push(mast);
        const lamps = {};
        ["r", "y", "g"].forEach((kind, index) => {
          const lamp = new THREE.Mesh(LAMP_GEO, lampMaterial(kind));
          const position = lampPositions[index];
          lamp.position.copy(position);
          lamp.castShadow = true;
          scene.add(lamp);
          lamps[kind] = lamp;
        });
        heads.push({ lamps, indices: laneLinks[approach.lane] || null });
      }
    } else {
      // Compact fallback: one pole + housing per junction.
      const pole = new THREE.CylinderGeometry(0.14, 0.2, 6.4, 8);
      pole.translate(junction.x, 3.2, junction.y);
      masts.push(pole);
      const housing = new THREE.BoxGeometry(0.62, 1.7, 0.42);
      housing.translate(junction.x, 5.6, junction.y);
      masts.push(housing);
      const lamps = {};
      ["r", "y", "g"].forEach((kind, index) => {
        const lamp = new THREE.Mesh(LAMP_GEO, lampMaterial(kind));
        lamp.position.set(junction.x, 6.15 - index * 0.55, junction.y);
        scene.add(lamp);
        lamps[kind] = lamp;
      });
      heads.push({ lamps, indices: null });
    }

    scene.add(new THREE.Mesh(mergeGeometries(masts, false), METAL));
    controllers.push({ id: junction.id, heads, approachCount: heads.length });
  }

  const byId = new Map(controllers.map((c) => [c.id, c]));
  return {
    /** Apply live SUMO states; each head follows its own approach's links. */
    update(states) {
      for (const [id, state] of Object.entries(states)) {
        const controller = byId.get(id);
        if (!controller) continue;
        controller.heads.forEach((head, headIndex) => {
          let kind = majorityKind(state, head.indices);
          if (!kind) {
            // No link map for this approach: approximate with an equal
            // chunk of the state string so heads still switch over time.
            const size = Math.ceil(state.length / controller.approachCount);
            const chunk = state.slice(headIndex * size, (headIndex + 1) * size);
            kind = chunkMajority(chunk);
          }
          for (const key of ["r", "y", "g"]) {
            head.lamps[key].material.emissiveIntensity =
              key === kind ? 1.6 : 0.04;
          }
        });
      }
    },
  };
}

function chunkMajority(chunk) {
  let r = 0, y = 0, g = 0;
  for (const ch of chunk) {
    if (ch === "r" || ch === "o") r++;
    else if (ch === "y") y++;
    else if (ch === "G" || ch === "g") g++;
  }
  if (r + y + g === 0) return "r";
  return r >= y && r >= g ? "r" : y >= g ? "y" : "g";
}
