// Procedural canvas textures for the city: grass, asphalt, facades with
// lit windows, gravel roofs. Small (128–256 px), generated once at boot.

import * as THREE from "three";

function makeCanvas(size) {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  return canvas;
}

function finish(canvas, repeat = 1) {
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(repeat, repeat);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}

function speckle(context, size, count, colors, minR, maxR) {
  for (let i = 0; i < count; i++) {
    context.fillStyle = colors[(Math.random() * colors.length) | 0];
    const r = minR + Math.random() * (maxR - minR);
    context.beginPath();
    context.arc(Math.random() * size, Math.random() * size, r, 0, 7);
    context.fill();
  }
}

/** Mottled grass. */
export function grassTexture() {
  const size = 256;
  const canvas = makeCanvas(size);
  const context = canvas.getContext("2d");
  context.fillStyle = "#4a5d3f";
  context.fillRect(0, 0, size, size);
  speckle(context, size, 900, ["#54684a", "#3f5238", "#5d7050", "#43573c"], 2, 7);
  speckle(context, size, 200, ["#66775a", "#6c7f57"], 1, 2.5);
  return finish(canvas, 140);
}

/** Dark asphalt with aggregate speckle. */
export function asphaltTexture() {
  const size = 128;
  const canvas = makeCanvas(size);
  const context = canvas.getContext("2d");
  context.fillStyle = "#34373d";
  context.fillRect(0, 0, size, size);
  speckle(context, size, 450, ["#3c4046", "#2d3036", "#42464c", "#31343a"], 1, 2.5);
  return finish(canvas, 1);
}

/** Concrete sidewalk. */
export function sidewalkTexture() {
  const size = 128;
  const canvas = makeCanvas(size);
  const context = canvas.getContext("2d");
  context.fillStyle = "#9c9a92";
  context.fillRect(0, 0, size, size);
  speckle(context, size, 260, ["#a5a39a", "#928f87", "#adaaa1"], 1, 2.2);
  context.strokeStyle = "rgba(70, 70, 66, 0.55)";
  context.lineWidth = 1.5;
  for (let i = 0; i <= 4; i++) {
    context.beginPath();
    context.moveTo((i * size) / 4, 0);
    context.lineTo((i * size) / 4, size);
    context.stroke();
  }
  return finish(canvas, 1);
}

/** Building facade: window grid with a storefront base and a parapet band.
 *  Returns { map, emissiveMap } — the emissive map lights a random subset
 *  of windows warm, so towers look inhabited. */
export function facadeTextures(rows = 12, columns = 6) {
  const size = 256;
  const map = makeCanvas(size);
  const emissive = makeCanvas(size);
  const ctx = map.getContext("2d");
  const emi = emissive.getContext("2d");

  ctx.fillStyle = "#b6b0a6";
  ctx.fillRect(0, 0, size, size);
  speckle(ctx, size, 160, ["#beb8ad", "#ada79c"], 1, 3);
  emi.fillStyle = "#000000";
  emi.fillRect(0, 0, size, size);

  const marginX = size * 0.07;
  const marginY = size * 0.06;
  const cellW = (size - marginX * 2) / columns;
  const cellH = (size - marginY * 2) / rows;
  for (let row = 0; row < rows; row++) {
    for (let column = 0; column < columns; column++) {
      const x = marginX + column * cellW + cellW * 0.16;
      const y = marginY + row * cellH + cellH * 0.18;
      const w = cellW * 0.68;
      const h = cellH * 0.62;
      const storefront = row >= rows - 1;
      ctx.fillStyle = storefront ? "#3a3f46" : "#2e3a44";
      ctx.fillRect(x, y, w, h);
      // Slight sill highlight for depth.
      ctx.fillStyle = "rgba(255,255,255,0.16)";
      ctx.fillRect(x, y, w, h * 0.18);
      if (Math.random() < 0.34) {
        emi.fillStyle = Math.random() < 0.5 ? "#ffcf87" : "#ffe9bd";
        emi.fillRect(x, y, w, h);
      }
    }
  }
  // Parapet band along the top of the facade.
  ctx.fillStyle = "#8f897f";
  ctx.fillRect(0, 0, size, marginY * 0.8);

  return { map: finish(map), emissiveMap: finish(emissive) };
}

/** Gravel rooftop. */
export function roofTexture() {
  const size = 128;
  const canvas = makeCanvas(size);
  const context = canvas.getContext("2d");
  context.fillStyle = "#6d6a64";
  context.fillRect(0, 0, size, size);
  speckle(context, size, 500, ["#77746d", "#625f59", "#7e7b73"], 1, 2.4);
  return finish(canvas, 1);
}
