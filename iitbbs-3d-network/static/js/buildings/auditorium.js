/* ============================================================================
   IIT Bhubaneswar - Auditorium (detailed model)
   Built from the reference photos + architect renders:
     - rounded-rectangle stone drum, stepped stone-slab fins curving round both ends
     - glass foyer with white columns behind it, warm interior glow
     - upper glass band above the canopy, held by diagonal white tension struts
     - big floating canopy: white rim, orange downlit underside
     - wide curved entrance steps, paver forecourt, blue fountain planter,
       yellow/black kerbs, marigolds, lamp posts, palms, cars, people

   Local coordinates: building centre = (0,0,0), FRONT faces +z, y is up, 1 unit = 1 m.
   Every tunable number is in the CONFIG block below.
   ============================================================================ */
import * as THREE from 'three';

const PI = Math.PI;

/* ---------- procedural textures (DataTexture, so no DOM/canvas is needed) ---------- */
const hash = (a, b = 0, c = 0) => {
  let h = Math.imul(a | 0, 374761393) ^ Math.imul(b | 0, 668265263) ^ Math.imul(c | 0, 1274126177);
  h = Math.imul(h ^ (h >>> 13), 1103515245);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
};
function dataTex(w, h, fn) {
  const d = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const [r, g, b] = fn(x / w, y / h, x, y), i = (y * w + x) * 4;
    d[i] = r; d[i + 1] = g; d[i + 2] = b; d[i + 3] = 255;
  }
  const t = new THREE.DataTexture(new Uint8Array(d.buffer), w, h, THREE.RGBAFormat);
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace;
  t.generateMipmaps = true; t.minFilter = THREE.LinearMipmapLinearFilter; t.magFilter = THREE.LinearFilter;
  t.anisotropy = 4; t.needsUpdate = true; return t;
}
// stone wall: 4 courses per tile, 2 blocks per course, running bond. Tile = 3.0 m wide x 2.4 m tall.
const stoneCourses = () => dataTex(256, 256, (u, v, px, py) => {
  const row = Math.floor(v * 4), ry = v * 4 - row, cu = u * 2 + (row & 1) * .5, bi = Math.floor(cu), fu = cu - bi;
  const k = (.9 + hash(((bi % 2) + 2) % 2, row, 3) * .18) * (.95 + hash(px, py, 9) * .1) * ((ry < .07 || fu < .035) ? .7 : 1);
  return [178 * k, 169 * k, 154 * k];
});
const stoneSpeckle = () => dataTex(64, 64, (u, v, px, py) => { const k = .88 + hash(px, py, 5) * .22; return [190 * k, 181 * k, 165 * k]; });
// herringbone-ish brick pavers. Tile = 2.4 m square, bricks 0.3 x 0.15 m.
const pavers = () => dataTex(256, 256, (u, v, px, py) => {
  const row = Math.floor(v * 16), ry = v * 16 - row, cu = u * 8 + (row & 1) * .5, bi = Math.floor(cu), fu = cu - bi;
  const hv = hash(((bi % 8) + 8) % 8, row, 1), base = hv > .8 ? [170, 148, 134] : [192, 174, 160], k = .93 + hash(px, py, 2) * .1;
  const j = (ry < .09 || fu < .06) ? .78 : 1;
  return [base[0] * k * j, base[1] * k * j, base[2] * k * j];
});
// warm lit foyer back wall with timber doors in the middle
const foyerGlow = () => dataTex(256, 128, (u, v) => {
  let c = [255, 226, 160]; const f = .74 + .26 * v, pu = u * 13, e = Math.abs(pu - Math.round(pu));
  if (e < .03) c = c.map(x => x * .82);
  if (u > .34 && u < .66 && v < .6) {
    const du = ((u - .34) / .32 * 6) % 1;
    c = (du < .05 || du > .95 || v > .57) ? [70, 44, 26] : [128, 82, 46];
    if (v < .04) c = [60, 40, 28];
  }
  return c.map(x => x * f);
});
// upper hall seen through the clerestory: orange timber ribs
const hallGlow = () => dataTex(128, 64, (u, v) => {
  const e = Math.abs(u * 28 - Math.round(u * 28)), k = e < .1 ? .8 : 1;
  return [255 * k, (170 + v * 50) * k, (92 + v * 60) * k];
});

/* ---------- geometry helpers ---------- */
// rounded rectangle outline in plan, CCW-ish list of [x,z]
function roundedRect(hw, hd, r, seg) {
  const cs = [[hw - r, hd - r, 0], [-(hw - r), hd - r, PI / 2], [-(hw - r), -(hd - r), PI], [hw - r, -(hd - r), PI * 1.5]], p = [];
  for (const [cx, cz, a0] of cs) for (let j = 0; j <= seg; j++) { const a = a0 + j / seg * PI / 2; p.push([cx + r * Math.cos(a), cz + r * Math.sin(a)]); }
  return p;
}
// extrude a plan polygon [[x,z],...] upward by `depth`, starting at height y0. holes: array of polygons
function extrudeXZ(pts, depth, y0, holes = []) {
  const V = ([x, z]) => new THREE.Vector2(x, -z), sh = new THREE.Shape(pts.map(V));
  holes.forEach(h => sh.holes.push(new THREE.Path(h.map(V))));
  const geo = new THREE.ExtrudeGeometry(sh, { depth, bevelEnabled: false, curveSegments: 1 });
  geo.rotateX(-PI / 2); geo.translate(0, y0, 0); return geo;
}
const scalePoly = (pts, cx, cz, sx, sz) => pts.map(([x, z]) => [x * sx, cz + (z - cz) * sz]);
function boxUV(geo, w, h, d, tw, th) {   // make a box's texture repeat in metres
  const uv = geo.attributes.uv, dims = [[d, h], [d, h], [w, d], [w, d], [w, h], [w, h]];
  for (let f = 0; f < 6; f++) for (let k = 0; k < 4; k++) { const i = f * 4 + k; uv.setXY(i, uv.getX(i) * dims[f][0] / tw, uv.getY(i) * dims[f][1] / th); }
  return geo;
}
const pointInPoly = (x, z, poly) => {
  let c = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, zi] = poly[i], [xj, zj] = poly[j];
    if ((zi > z) !== (zj > z) && x < (xj - xi) * (z - zi) / (zj - zi) + xi) c = !c;
  } return c;
};

/* ============================================================================ */
export function buildAuditorium({ g, b, pickables, colliders }) {
  const id = b.id, hw = b.w / 2, hd = b.d / 2, H = b.h;

  /* ----- CONFIG ----- */
  const R = 11;                       // plan corner radius of the drum
  const FW = hw - R;                  // half-width of the straight glass front
  const PLINTH = .6;                  // finished floor level
  const Y_CAN = 8.4, CAN_T = 1.05;    // canopy underside height, rim thickness
  const Y_GLASS_TOP = 13.3;           // top of the upper glass band
  const FIN_STEP = 2.2;               // spacing of stone fins along the perimeter
  const rng = (a => () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; })(2024);

  /* ----- materials ----- */
  const M = (c, o = {}) => new THREE.MeshStandardMaterial({ color: c, roughness: .85, metalness: 0, ...o });
  const BASIC = (c, o = {}) => new THREE.MeshBasicMaterial({ color: c, ...o });
  const stoneMat = M(0xffffff, { map: stoneCourses() });
  const blockMat = M(0xffffff, { map: stoneSpeckle() });
  const plinthMat = M(0x8c867c), roofMat = M(0x9a9d9f), copingMat = M(0xd6d0c4);
  const whiteMat = M(0xf5f3ee, { roughness: .55 }), steelMat = M(0xdfe3e6, { roughness: .45, metalness: .12 });
  const frameMat = M(0x45413b, { roughness: .45, metalness: .4 });
  const glassMat = M(0x8fbfd3, { transparent: true, opacity: .3, roughness: .06, metalness: .15, depthWrite: false, side: THREE.DoubleSide });
  const underMat = M(0xe8913f, { roughness: .7, emissive: 0xc2661a, emissiveIntensity: 1.25 });
  const lightMat = BASIC(0xffc566), slitMat = BASIC(0xf0dca8), ledMat = BASIC(0x4ff08e);
  const stepMat = M(0xcfc8bc), paverMat = M(0xffffff, { map: pavers() });
  const blue = M(0x3a73a8, { roughness: .6, side: THREE.DoubleSide }), water = M(0x5fb0d6, { roughness: .15, emissive: 0x143a50 });
  const D = new THREE.Object3D(), UP = new THREE.Vector3(0, 1, 0);

  /* ----- scene helpers ----- */
  const add = (geo, mat, x = 0, y = 0, z = 0, o = {}) => {
    const me = new THREE.Mesh(geo, mat); me.position.set(x, y, z);
    me.castShadow = o.cast ?? true; me.receiveShadow = o.recv ?? true; me.userData.id = id;
    (o.parent || g).add(me); if (o.pick ?? true) pickables.push(me); return me;
  };
  // fill(i, D) positions the dummy for instance i and may return a THREE.Color
  const inst = (geo, mat, n, fill, o = {}) => {
    const im = new THREE.InstancedMesh(geo, mat, n);
    for (let i = 0; i < n; i++) {
      D.position.set(0, 0, 0); D.quaternion.identity(); D.rotation.set(0, 0, 0); D.scale.set(1, 1, 1);
      const c = fill(i, D); D.updateMatrix(); im.setMatrixAt(i, D.matrix); if (c) im.setColorAt(i, c);
    }
    im.instanceMatrix.needsUpdate = true; im.computeBoundingSphere();
    im.castShadow = o.cast ?? false; im.receiveShadow = o.recv ?? true; im.userData.id = id;
    g.add(im); if (o.pick ?? true) pickables.push(im); return im;
  };
  const rods = (list, r, seg, mat, o) => {     // list of [x1,y1,z1,x2,y2,z2]
    const a = new THREE.Vector3(), c = new THREE.Vector3(), dir = new THREE.Vector3();
    return inst(new THREE.CylinderGeometry(r, r, 1, seg), mat, list.length, (i, d) => {
      const s = list[i]; a.set(s[0], s[1], s[2]); c.set(s[3], s[4], s[5]); dir.subVectors(c, a);
      const len = dir.length(); d.position.copy(a).add(c).multiplyScalar(.5);
      d.quaternion.setFromUnitVectors(UP, dir.normalize()); d.scale.set(1, len, 1);
    }, o);
  };
  const stepsSolid = (hx, hz) => colliders.push({ x: b.x + hx[0], z: b.z + hx[1], hw: hx[2], hd: hx[3] });

  /* =========================================================================
     1. PLINTH + DRUM WALLS
     ========================================================================= */
  const O = roundedRect(hw, hd, R, 22), n = O.length;
  add(extrudeXZ(roundedRect(hw + 1.2, hd + 1.2, R + 1.2, 22), PLINTH, 0), plinthMat, 0, 0, 0, { cast: false });

  // per-segment data: outward normals, cumulative arc length
  const segN = [], cum = [0];
  for (let i = 0; i < n; i++) {
    const [x0, z0] = O[i], [x1, z1] = O[(i + 1) % n], dx = x1 - x0, dz = z1 - z0, len = Math.hypot(dx, dz);
    let nx = dz / len, nz = -dx / len; if (nx * (x0 + x1) + nz * (z0 + z1) < 0) { nx = -nx; nz = -nz; }
    segN.push([nx, nz]); cum.push(cum[i] + len);
  }
  const L = cum[n];
  const isGlassSeg = i => { const m = (O[i][1] + O[(i + 1) % n][1]) / 2, mx = (O[i][0] + O[(i + 1) % n][0]) / 2; return m > hd - .01 && Math.abs(mx) <= FW + .01; };
  const glassSeg = [...Array(n).keys()].find(isGlassSeg);
  const sA = cum[glassSeg], sB = cum[glassSeg + 1];    // arc-length span of the glass front

  // custom wall strip: smooth normals, metre-based UVs so the stone courses tile correctly
  {
    const pos = [], nor = [], uvs = [], idx = [];
    const vn = k => { const a = segN[(k - 1 + n) % n], c = segN[k % n], x = a[0] + c[0], z = a[1] + c[1], l = Math.hypot(x, z) || 1; return [x / l, z / l]; };
    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n, [x0, z0] = O[i], [x1, z1] = O[j], n0 = vn(i), n1 = vn(j);
      const ranges = isGlassSeg(i) ? [[Y_CAN - .1, Y_CAN + CAN_T + .1], [Y_GLASS_TOP, H]] : [[PLINTH, H]];
      // is the segment direction to the viewer's right? (decides triangle winding)
      const tx = x1 - x0, tz = z1 - z0, right = tx * segN[i][1] - tz * segN[i][0] > 0;
      for (const [ya, yb] of ranges) {
        const o = pos.length / 3;
        pos.push(x0, ya, z0, x1, ya, z1, x1, yb, z1, x0, yb, z0);
        nor.push(n0[0], 0, n0[1], n1[0], 0, n1[1], n1[0], 0, n1[1], n0[0], 0, n0[1]);
        uvs.push(cum[i] / 3, ya / 2.4, cum[i + 1] / 3, ya / 2.4, cum[i + 1] / 3, yb / 2.4, cum[i] / 3, yb / 2.4);
        if (right) idx.push(o, o + 1, o + 2, o, o + 2, o + 3); else idx.push(o + 1, o, o + 3, o + 1, o + 3, o + 2);
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    geo.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
    geo.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2)); geo.setIndex(idx);
    add(geo, stoneMat);
  }

  // parapet + coping + roof deck
  const outerP = roundedRect(hw + .1, hd + .1, R + .1, 22), innerP = roundedRect(hw - .55, hd - .55, R - .55, 22);
  add(extrudeXZ(outerP, .8, H, [innerP]), M(0xb9ae9d));
  add(extrudeXZ(roundedRect(hw + .3, hd + .3, R + .3, 22), .14, H + .8, [roundedRect(hw - .6, hd - .6, R - .6, 22)]), copingMat);
  add(extrudeXZ(innerP, .15, H - .1), roofMat, 0, 0, 0, { cast: false });

  /* =========================================================================
     2. STONE FINS (the stepped slabs round both ends) + glowing slits
     ========================================================================= */
  const at = s => { // point + outward normal at arc length s
    s = ((s % L) + L) % L; let i = 0; while (cum[i + 1] < s) i++;
    const f = (s - cum[i]) / (cum[i + 1] - cum[i]), [x0, z0] = O[i], [x1, z1] = O[(i + 1) % n];
    return { x: x0 + (x1 - x0) * f, z: z0 + (z1 - z0) * f, nx: segN[i][0], nz: segN[i][1] };
  };
  const cd = (a, c) => { const d = Math.abs(a - c); return Math.min(d, L - d); };
  const nFin = Math.round(L / FIN_STEP), sp = L / nFin, FIN_T = 1.0, finW = sp - .42;
  const fins = [];
  for (let k = 0; k < nFin; k++) {
    const s = (k + .5) * sp; if (s > sA - .7 && s < sB + .7) continue;
    const dist = Math.min(cd(s, sA), cd(s, sB)), step = Math.min(7, Math.max(0, Math.floor((dist - .7) / sp)));
    fins.push({ ...at(s), h: H + .8 + (7 - step) * .32 });       // tallest beside the glass, tapering round the ends
  }
  { // stacked stone blocks: real geometry, one block per course
    let total = 0; fins.forEach(f => { f.nb = Math.ceil((f.h - PLINTH) / .6); total += f.nb; });
    const geo = new THREE.BoxGeometry(1, 1, 1); let fi = 0, bi = 0; const col = new THREE.Color();
    inst(geo, blockMat, total, (i, d) => {
      while (bi >= fins[fi].nb) { bi = 0; fi++; }
      const f = fins[fi], bh = (f.h - PLINTH) / f.nb, jit = (hash(fi, bi, 4) - .5) * .1;
      d.position.set(f.x + f.nx * (FIN_T / 2 - .1 + jit), PLINTH + bh * (bi + .5), f.z + f.nz * (FIN_T / 2 - .1 + jit));
      d.rotation.y = Math.atan2(f.nx, f.nz); d.scale.set(finW, bh - .035, FIN_T);
      bi++; const k = .9 + hash(fi, bi, 8) * .16; return col.setRGB(k, k * .99, k * .96);
    }, { cast: true });
    // light stone caps
    inst(new THREE.BoxGeometry(1, 1, 1), M(0xe4ddd0), fins.length, (i, d) => {
      const f = fins[i]; d.position.set(f.x + f.nx * (FIN_T / 2 - .1), f.h + .08, f.z + f.nz * (FIN_T / 2 - .1));
      d.rotation.y = Math.atan2(f.nx, f.nz); d.scale.set(finW + .14, .16, FIN_T + .14);
    }, { cast: true });
    // warm light slits between fins
    const slits = []; for (let k = 0; k < nFin; k++) { const s = k * sp; if (s > sA - .3 && s < sB + .3) continue; slits.push(at(s)); }
    inst(new THREE.BoxGeometry(.2, 1, .05), slitMat, slits.length, (i, d) => {
      const f = slits[i]; d.position.set(f.x + f.nx * .03, PLINTH + (H - PLINTH - .6) / 2 + .2, f.z + f.nz * .03);
      d.rotation.y = Math.atan2(f.nx, f.nz); d.scale.set(1, H - PLINTH - .6, 1);
    }, { cast: false, pick: false });
  }

  /* =========================================================================
     3. GLASS FRONT: foyer + upper band, mullions, doors, interior glow
     ========================================================================= */
  const GZ = hd - .9;                               // glass plane (recessed under the canopy)
  const lowH = Y_CAN - PLINTH, lowY = PLINTH + lowH / 2, upH = Y_GLASS_TOP - (Y_CAN + CAN_T), upY = Y_CAN + CAN_T + upH / 2;
  add(new THREE.PlaneGeometry(FW * 2, lowH), glassMat, 0, lowY, GZ, { cast: false });
  add(new THREE.PlaneGeometry(FW * 2, upH), glassMat, 0, upY, GZ, { cast: false });
  { // mullions: 21 per band
    const nM = 21, xs = i => -FW + i * (2 * FW / (nM - 1));
    inst(new THREE.BoxGeometry(.09, 1, .24), frameMat, nM * 2, (i, d) => {
      const up = i >= nM, k = up ? i - nM : i; d.position.set(xs(k), up ? upY : lowY, GZ + .02); d.scale.y = up ? upH : lowH;
    }, { cast: false });
    // horizontal rails (sill, head, canopy line, band top) + a mid transom on the foyer
    [PLINTH + .08, Y_CAN - .08, Y_CAN + CAN_T + .08, Y_GLASS_TOP - .08, PLINTH + lowH * .52].forEach(y =>
      add(new THREE.BoxGeometry(FW * 2, .12, .28), frameMat, 0, y, GZ + .02, { cast: false }));
    // entrance doors: 3 bays with heavier frames, push bars and a transom
    [-3.9, -1.3, 1.3, 3.9].forEach(x => add(new THREE.BoxGeometry(.16, 3.8, .32), steelMat, x, PLINTH + 1.9, GZ + .06, { cast: false }));
    add(new THREE.BoxGeometry(8.2, .2, .34), steelMat, 0, PLINTH + 3.85, GZ + .06, { cast: false });
    [-2.6, 0, 2.6].forEach(x => [-.28, .28].forEach(dx => add(new THREE.CylinderGeometry(.03, .03, 1.1, 8), steelMat, x + dx, PLINTH + 1.1, GZ + .22, { cast: false })));
  }
  { // glowing interior (MeshBasic = self-lit). Boxes are drawn from the inside only; the front face is invisible.
    const hide = BASIC(0xffffff, { visible: false, side: THREE.BackSide });
    const mk = (map, c) => map ? BASIC(0xffffff, { map, side: THREE.BackSide }) : BASIC(c, { side: THREE.BackSide });
    const foyer = new THREE.BoxGeometry(FW * 2 - .3, lowH - .1, 8);
    add(foyer, [mk(null, 0xeedcb4), mk(null, 0xeedcb4), mk(null, 0xfff2cc), mk(null, 0xcfc6b6), hide, mk(foyerGlow())], 0, lowY, GZ - 4.1, { cast: false, pick: false });
    const hall = new THREE.BoxGeometry(FW * 2 - .3, upH, 3);
    add(hall, [mk(null, 0xe8a561), mk(null, 0xe8a561), mk(null, 0xffd9a0), mk(null, 0xd9a066), hide, mk(hallGlow())], 0, upY, GZ - 1.6, { cast: false, pick: false });
    // white columns behind the glass (round, with base and capital rings)
    const nC = 9, cx = i => -FW + 2 + i * ((FW * 2 - 4) / (nC - 1)), cz = GZ - 2.4, cMat = BASIC(0xfff7e8);
    inst(new THREE.CylinderGeometry(.42, .46, lowH - .1, 24), cMat, nC, (i, d) => { d.position.set(cx(i), lowY, cz); }, { cast: false });
    inst(new THREE.CylinderGeometry(.62, .62, .18, 24), cMat, nC * 2, (i, d) => { d.position.set(cx(i % nC), i < nC ? PLINTH + .12 : Y_CAN - .2, cz); }, { cast: false, pick: false });
    // pendant lights in the foyer
    inst(new THREE.SphereGeometry(.28, 12, 8), BASIC(0xfff0b8), 12, (i, d) => { d.position.set(-FW + 1.5 + (i % 6) * 4.6, Y_CAN - 1.1, GZ - 1.6 - Math.floor(i / 6) * 3.2); }, { cast: false, pick: false });
  }
  // door-jambs closing the recessed pocket
  [-1, 1].forEach(sg => add(new THREE.BoxGeometry(.3, Y_CAN - PLINTH + .2, .95), stoneMat, sg * (FW + .02), (PLINTH + Y_CAN) / 2, hd - .45, { cast: false }));

  /* =========================================================================
     4. CANOPY: white rim, timber-orange soffit with downlights, tension struts
     ========================================================================= */
  const CX = 23.5, CZ = hd - 3, CD = 9.5;               // half-width, back line, depth of the "D" shaped canopy
  const canopyPts = []; for (let i = 0; i <= 72; i++) {
    const t = PI - i / 72 * PI, c = Math.cos(t), s = Math.sin(t);
    canopyPts.push([CX * Math.sign(c) * Math.pow(Math.abs(c), .5), CZ + CD * Math.pow(Math.abs(s), .5)]);
  }
  const zEdge = x => CZ + CD * Math.pow(Math.max(0, 1 - Math.pow(Math.abs(x) / CX, 4)), .25);
  const inner = scalePoly(canopyPts, 0, CZ, (CX - .5) / CX, (CD - .5) / CD);
  add(extrudeXZ(canopyPts, CAN_T, Y_CAN - .05, [inner]), whiteMat);               // thick white rim
  add(extrudeXZ(inner, CAN_T - .35, Y_CAN + .1), M(0xc9cbcc));                    // slab between the rim
  add(extrudeXZ(inner, .08, Y_CAN - .08), underMat, 0, 0, 0, { cast: false });     // orange soffit
  {
    const pts = []; for (let x = -CX + 1; x <= CX - 1; x += 1.45) for (let z = CZ + .8; z < CZ + CD - .6; z += 1.45)
      if (pointInPoly(x + (Math.round((z - CZ) / 1.45) % 2) * .7, z, inner)) pts.push([x + (Math.round((z - CZ) / 1.45) % 2) * .7, z]);
    const cg = new THREE.CircleGeometry(.15, 10); cg.rotateX(PI / 2);
    inst(cg, lightMat, pts.length, (i, d) => d.position.set(pts[i][0], Y_CAN - .1, pts[i][1]), { cast: false, pick: false });
    // Wi-Fi access points under the canopy (network layer)
    const ap = [[-12, 3], [-6, 5], [0, 4], [6, 5], [12, 3]].map(([x, o]) => [x, CZ + o + 1.5]);
    inst(new THREE.CylinderGeometry(.34, .38, .12, 16), whiteMat, ap.length, (i, d) => d.position.set(ap[i][0], Y_CAN - .15, ap[i][1]), { cast: false });
    inst(new THREE.SphereGeometry(.05, 8, 6), ledMat, ap.length, (i, d) => d.position.set(ap[i][0], Y_CAN - .23, ap[i][1]), { cast: false, pick: false });
  }
  { // diagonal tension struts: canopy edge up and back to the roof beam
    const list = [], nodes = [];
    for (let x = -FW + 1; x <= FW - 1 + .01; x += 2.4) {
      const ze = zEdge(x) - .35, top = [x, H + .75, hd - .1], bot = [x, Y_CAN + CAN_T - .1, ze];
      list.push([...bot, ...top]); nodes.push(bot, top);
    }
    rods(list, .1, 12, whiteMat, { cast: true });
    inst(new THREE.SphereGeometry(.22, 12, 8), steelMat, nodes.length, (i, d) => d.position.set(...nodes[i]), { cast: true });
    // roof-edge beam the struts hang from
    add(new THREE.BoxGeometry(FW * 2 + 1, .5, .6), whiteMat, 0, H + .55, hd - .1);
  }

  /* =========================================================================
     5. ROOF: skylights, plant, solar array, comms mast
     ========================================================================= */
  [-9, 0, 9].forEach(x => { // glass vault skylights
    const sk = new THREE.CylinderGeometry(2.2, 2.2, 6, 20, 1, false, PI / 2, PI); sk.rotateX(PI / 2);
    add(sk, M(0x9fd0e4, { transparent: true, opacity: .55, roughness: .1 }), x, H, -2, { cast: false });
    add(new THREE.BoxGeometry(4.6, .25, 6.3), whiteMat, x, H + .05, -2, { cast: false });
  });
  [[-18, -6], [18, -6], [-17, 6], [17, 6], [0, -10.5]].forEach(([x, z], i) => { // HVAC units with fans
    add(new THREE.BoxGeometry(2.6, 1.3, 1.6), M(0xb4b8bb, { metalness: .3, roughness: .6 }), x, H + .75, z);
    add(new THREE.CylinderGeometry(.5, .5, .1, 18), M(0x333a40), x - .6, H + 1.45, z, { cast: false });
    add(new THREE.CylinderGeometry(.5, .5, .1, 18), M(0x333a40), x + .6, H + 1.45, z, { cast: false });
  });
  {
    const rows = 3, cols = 7, N = rows * cols, tilt = -.28;
    inst(new THREE.BoxGeometry(2.1, .06, 1.2), M(0x1f3350, { roughness: .3, metalness: .2 }), N, (i, d) => {
      const r = Math.floor(i / cols), c = i % cols; d.position.set(-10.5 + c * 3.5, H + .55, -13 + r * 1.9 - 0); d.rotation.x = tilt;
    }, { cast: true });
  }
  { // comms mast with dishes (campus network)
    const mx = -14, mz = -2;
    add(new THREE.CylinderGeometry(.07, .12, 4.2, 8), steelMat, mx, H + 2.1, mz);
    [[1.6, .6], [2.6, -.8]].forEach(([y, a]) => {
      const dish = new THREE.SphereGeometry(.55, 14, 8, 0, TAU(), 0, PI / 2.2); dish.rotateX(PI / 2);
      const m = add(dish, whiteMat, mx, H + y + 1, mz); m.rotation.y = a; m.position.x += Math.sin(a) * .3; m.position.z += Math.cos(a) * .3;
    });
    add(new THREE.SphereGeometry(.14, 8, 6), BASIC(0xff4040), mx, H + 4.3, mz, { cast: false, pick: false });
  }

  /* =========================================================================
     6. ENTRANCE STEPS (wide curved), forecourt, fountain, kerbs, planting
     ========================================================================= */
  const SZ = hd - 1;    // steps are half-ellipses centred on this z
  const stepDef = [[27, 9.5, .14], [25.3, 7.8, .28], [23.6, 6.1, .42], [21.9, 4.4, .56]];
  stepDef.forEach(([A, B, h]) => {
    const pts = []; for (let i = 0; i <= 56; i++) { const t = PI - i / 56 * PI; pts.push([A * Math.cos(t), SZ + B * Math.sin(t)]); }
    add(extrudeXZ(pts, h, 0), stepMat, 0, 0, 0, { cast: true });
  });
  const stepY = (x, z) => { for (let k = 3; k >= 0; k--) { const [A, B, h] = stepDef[k]; if (z >= SZ && (x / A) ** 2 + ((z - SZ) / B) ** 2 <= 1) return h; } return .08; };

  const PZ0 = SZ + 9.2, PZ1 = hd + 22.4, PW = 64;    // forecourt paving
  add(boxUV(new THREE.BoxGeometry(PW, .1, PZ1 - PZ0, 1, 1, 1), PW, .1, PZ1 - PZ0, 2.4, 2.4), paverMat, 0, .05, (PZ0 + PZ1) / 2, { cast: false });
  add(new THREE.BoxGeometry(PW + .8, .12, .5), M(0x77716a), 0, .06, PZ1 + .1, { cast: false });       // edge band

  // fountain planter: blue drum wall, water, shrubs, bronze pedestal + statue
  const FZ = PZ0 + 5.2;
  add(new THREE.CylinderGeometry(3.4, 3.5, .85, 40, 1, true), blue, 0, .48, FZ, { recv: true });
  add(new THREE.RingGeometry(3.15, 3.55, 40).rotateX(-PI / 2), M(0x9bb7cf), 0, .91, FZ, { cast: false });
  add(new THREE.CircleGeometry(3.15, 40).rotateX(-PI / 2), water, 0, .78, FZ, { cast: false });
  add(new THREE.CylinderGeometry(1.5, 1.6, .75, 24), M(0x8d9298), 0, .75, FZ);
  add(new THREE.CylinderGeometry(.55, .75, 1.3, 14), M(0xa9a79f), 0, 1.7, FZ);
  add(new THREE.CapsuleGeometry(.28, .9, 4, 10), M(0x8a6a3c, { metalness: .5, roughness: .45 }), 0, 2.9, FZ);
  add(new THREE.SphereGeometry(.22, 12, 8), M(0x8a6a3c, { metalness: .5, roughness: .45 }), 0, 3.75, FZ);
  { // shrubs + flowers in the planter ring
    const geo = new THREE.IcosahedronGeometry(.55, 1), N = 14;
    inst(geo, M(0x3f7d3b), N, (i, d) => { const a = i / N * PI * 2; d.position.set(Math.cos(a) * 2.55, 1.15, FZ + Math.sin(a) * 2.55); d.scale.set(1, .8, 1); return new THREE.Color().setHSL(.3, .45, .25 + hash(i, 1, 1) * .12); }, { cast: true });
    inst(new THREE.IcosahedronGeometry(.17, 0), M(0xb06ad0), N * 3, (i, d) => { const a = (i / (N * 3)) * PI * 2; d.position.set(Math.cos(a) * 2.55, 1.6, FZ + Math.sin(a) * 2.55); }, { cast: false });
  }
  // lawn island with ornamental grass
  const LZ = FZ + 6.4;
  add(new THREE.CylinderGeometry(3.5, 3.6, .3, 40), M(0x7a746c), 0, .2, LZ, { cast: false });
  add(new THREE.CylinderGeometry(3.25, 3.25, .34, 40), M(0x6aa95c), 0, .22, LZ, { cast: false });
  {
    const gr = new THREE.ConeGeometry(.16, 1.3, 4); gr.translate(0, .65, 0);
    inst(gr, M(0xb4c24e), 36, (i, d) => { const a = i * 2.4, r = Math.sqrt(i / 36) * 1.7; d.position.set(Math.cos(a) * r, .38, LZ + Math.sin(a) * r); d.rotation.set((hash(i, 2) - .5) * .6, hash(i, 3) * 6, (hash(i, 4) - .5) * .6); d.scale.set(1, .8 + hash(i, 5) * .7, 1); }, { cast: false });
  }
  { // yellow/black kerbs along two diagonal planter beds (a funnel narrowing toward the fountain)
    const A = [15, SZ + 11], B = [32, SZ + 20], len = Math.hypot(B[0] - A[0], B[1] - A[1]), cnt = Math.round(len / 1.1);
    const sides = [-1, 1].map(sg => {
      const d = new THREE.Vector2(sg * (B[0] - A[0]), B[1] - A[1]).normalize();
      let p = new THREE.Vector2(-d.y, d.x); if (p.x * sg < 0) p.negate();            // points away from the centre line
      return { sg, d, p, ang: Math.atan2(d.x, d.y), at: t => new THREE.Vector2(sg * (A[0] + (B[0] - A[0]) * t), A[1] + (B[1] - A[1]) * t) };
    });
    const kerbs = []; sides.forEach(S => { for (let k = 0; k < cnt; k++) { const q = S.at((k + .5) / cnt); kerbs.push({ x: q.x, z: q.y, a: S.ang, k }); } });
    const kg = new THREE.BoxGeometry(.4, .28, 1.08);
    [0, 1].forEach(par => { const list = kerbs.filter(s => s.k % 2 === par);
      inst(kg, M(par ? 0x25272a : 0xe9b91d, { roughness: .6 }), list.length, (i, d) => { d.position.set(list[i].x, .24, list[i].z); d.rotation.y = list[i].a; }, { cast: false }); });
    sides.forEach(S => {      // planter bed behind the kerb: red soil + low hedge
      const m = S.at(.5), bed = add(new THREE.BoxGeometry(2.6, .22, len), M(0x8a4b3b), m.x + S.p.x * 1.6, .15, m.y + S.p.y * 1.6, { cast: false });
      bed.rotation.y = S.ang;
      const hc = Math.round(len / 1.2);
      inst(new THREE.IcosahedronGeometry(.5, 1), M(0x3e8a45), hc, (i, d) => { const q = S.at((i + .5) / hc); d.position.set(q.x + S.p.x * 1.6, .5, q.y + S.p.y * 1.6);
        d.scale.set(1, .85, 1); return new THREE.Color().setHSL(.3, .5, .24 + hash(i, S.sg + 3, 7) * .1); }, { cast: true });
    });
  }
  { // marigold + shrub border at the front edge of the forecourt
    const N = 30, xs = i => -PW / 2 + 2 + i * ((PW - 4) / (N - 1)), z = PZ1 - .8;
    inst(new THREE.IcosahedronGeometry(.62, 1), M(0x3d6b2f), N, (i, d) => { d.position.set(xs(i), .55, z); d.scale.set(1.2, .8, 1); }, { cast: true });
    inst(new THREE.IcosahedronGeometry(.17, 0), M(0xf2b81f, { emissive: 0x5a3f00 }), N * 5, (i, d) => { const k = Math.floor(i / 5), j = i % 5; d.position.set(xs(k) + (j - 2) * .26, .98 + hash(i, 1) * .1, z + (hash(i, 2) - .5) * .8); }, { cast: false });
  }
  { // lamp posts
    const spots = [[-8, FZ + 1.5], [8, FZ + 1.5], [-21, FZ - 3], [21, FZ - 3], [-27, SZ + 5], [27, SZ + 5], [-9, LZ + 1.6], [9, LZ + 1.6]];
    const pole = new THREE.CylinderGeometry(.07, .12, 6.5, 8), head = new THREE.BoxGeometry(1.0, .16, .4);
    spots.forEach(([x, z]) => {
      add(pole, frameMat, x, 3.25, z, { cast: true }); add(new THREE.CylinderGeometry(.22, .3, .5, 8), frameMat, x, .3, z, { cast: false });
      add(head, frameMat, x, 6.55, z, { cast: false }); add(new THREE.BoxGeometry(.8, .06, .3), BASIC(0xfff2c0), x, 6.45, z, { cast: false, pick: false });
      stepsSolid([x, z, .35, .35]);
    });
  }

  /* =========================================================================
     7. PLANTING AROUND THE DRUM, PALMS, TREES
     ========================================================================= */
  { // shrub ring round the plinth (not across the entrance)
    const pts = []; for (let s = 0; s < L; s += 1.9) { const p = at(s); const x = p.x + p.nx * (FIN_T + 2.1), z = p.z + p.nz * (FIN_T + 2.1); if (z > hd - 6) continue; pts.push([x, z]); }
    inst(new THREE.IcosahedronGeometry(.8, 1), M(0x3a7a3f), pts.length, (i, d) => { d.position.set(pts[i][0], .55, pts[i][1]); d.scale.set(1.2, .8, 1.2); return new THREE.Color().setHSL(.3, .45, .22 + hash(i, 4, 4) * .1); }, { cast: true });
  }
  { // palms: curved trunk, serrated fronds, coconuts
    const palms = [[-31, 24, 1.1], [31, 22, 1.05], [-33, 11, 1.2], [33, 10, 1.15], [-30, 36, .95], [30, 37, 1], [-24, 41, .9], [24, 41, .95], [-13, 43, .85], [13, 43, .9]];
    const nSeg = 8, trunkL = 8;
    const segs = []; palms.forEach(([x, z, s], p) => {
      const lean = (hash(p, 1) - .5) * 1.8, lz = (hash(p, 2) - .5) * 1.8, pts = [];
      for (let k = 0; k <= nSeg; k++) { const t = k / nSeg; pts.push([x + lean * t * t * s, trunkL * s * t, z + lz * t * t * s]); }
      for (let k = 0; k < nSeg; k++) segs.push({ a: pts[k], c: pts[k + 1], r0: (.42 - k * .018) * s, p });
      palms[p].crown = pts[nSeg];
    });
    const a = new THREE.Vector3(), c = new THREE.Vector3(), dv = new THREE.Vector3();
    inst(new THREE.CylinderGeometry(1, 1.12, 1, 8), M(0x8a6a4a), segs.length, (i, d) => {
      const s = segs[i]; a.set(...s.a); c.set(...s.c); dv.subVectors(c, a); const len = dv.length();
      d.position.copy(a).add(c).multiplyScalar(.5); d.quaternion.setFromUnitVectors(UP, dv.normalize()); d.scale.set(s.r0, len * 1.04, s.r0);
    }, { cast: true });
    // frond: arched strip with serrated edges
    const fg = (() => {
      const N = 14, pos = [], idx = []; const Ln = 4.6;
      for (let k = 0; k <= N; k++) {
        const t = k / N, x = Ln * t, y = 1.5 * t - 3.1 * t * t, w = .62 * Math.sin(PI * Math.min(1, t * 1.08 + .04)) * (k % 2 ? .55 : 1);
        pos.push(x, y, -w, x, y, w);
      }
      for (let k = 0; k < N; k++) { const o = k * 2; idx.push(o, o + 1, o + 2, o + 1, o + 3, o + 2); }
      const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); geo.setIndex(idx); geo.computeVertexNormals(); return geo;
    })();
    const FR = 11, fm = M(0x4c9a4a, { side: THREE.DoubleSide, roughness: .8 });
    inst(fg, fm, palms.length * FR, (i, d) => {
      const p = Math.floor(i / FR), k = i % FR, [, , s] = palms[p], cr = palms[p].crown;
      d.position.set(cr[0], cr[1], cr[2]); d.rotation.set(0, k / FR * PI * 2 + hash(p, k, 1) * .4, .35 + hash(p, k, 2) * .55, 'YXZ'); d.scale.setScalar(s * (.9 + hash(p, k, 3) * .25));
      return new THREE.Color().setHSL(.3 + hash(p, k, 4) * .04, .5, .27 + hash(p, k, 5) * .1);
    }, { cast: true });
    inst(new THREE.IcosahedronGeometry(.2, 0), M(0x6b7d3a), palms.length * 4, (i, d) => { const p = Math.floor(i / 4), k = i % 4, cr = palms[p].crown; d.position.set(cr[0] + Math.cos(k * 1.6) * .32, cr[1] - .3, cr[2] + Math.sin(k * 1.6) * .32); }, { cast: false });
  }
  { // broadleaf trees round the sides and back
    const spots = []; [[-34, -4], [-33, -17], [-27, -28], [-12, -31], [8, -32], [22, -29], [32, -20], [36, -6], [38, 6], [-38, 4], [-37, 16]]
      .forEach(([x, z]) => spots.push([x + (rng() - .5) * 2, z + (rng() - .5) * 2, 2.8 + rng() * 1.4]));
    inst(new THREE.CylinderGeometry(.35, .55, 3.4, 7), M(0x6e4e32), spots.length, (i, d) => { d.position.set(spots[i][0], 1.7, spots[i][1]); d.scale.setScalar(spots[i][2] / 4); }, { cast: true });
    const bl = new THREE.IcosahedronGeometry(1, 1), q = bl.attributes.position;
    for (let k = 0; k < q.count; k++) { const x = Math.round(q.getX(k) * 100), y = Math.round(q.getY(k) * 100), z = Math.round(q.getZ(k) * 100), f = .82 + hash(x, y, z) * .36; q.setXYZ(k, q.getX(k) * f, q.getY(k) * f * .85, q.getZ(k) * f); }
    bl.computeVertexNormals();
    inst(bl, M(0x3f8a47, { flatShading: true }), spots.length * 3, (i, d) => {
      const t = Math.floor(i / 3), k = i % 3, [x, z, h] = spots[t]; d.position.set(x + (k - 1) * h * .3, h + 1.2 + (k === 1 ? h * .25 : 0), z + (k === 2 ? h * .22 : -h * .1));
      d.scale.setScalar(h * (.5 + hash(t, k, 6) * .18)); return new THREE.Color().setHSL(.28 + hash(t, k, 7) * .06, .5, .26 + hash(t, k, 8) * .1);
    }, { cast: true });
  }

  /* =========================================================================
     8. PEOPLE AND CARS
     ========================================================================= */
  { // standing figures (instanced torso / legs / head)
    const P = [[-3, 20], [-1.4, 20.6], [6, 17.6], [7.1, 17.9], [-9, 18.2], [11.5, 21.3], [12.4, 21.1], [-15, 22.5], [2.5, 25.5], [-5.5, 26.5], [5.8, 31.2], [4.6, 34]]
      .map(([x, z], i) => ({ x, z, y: stepY(x, z), s: i === 6 || i === 11 ? .72 : .92 + hash(i, 1) * .16, a: hash(i, 2) * 6.28, c: [0xc0392b, 0x2e86c1, 0xf4d03f, 0x1e8449, 0x884ea0, 0xe67e22, 0x34495e, 0xecf0f1][i % 8] }));
    inst(new THREE.CapsuleGeometry(.23, .5, 3, 8), M(0xffffff), P.length, (i, d) => { const p = P[i]; d.position.set(p.x, p.y + 1.15 * p.s, p.z); d.scale.setScalar(p.s); d.rotation.y = p.a; return new THREE.Color(p.c); }, { cast: true });
    inst(new THREE.CylinderGeometry(.15, .17, .9, 8), M(0x2b2f36), P.length, (i, d) => { const p = P[i]; d.position.set(p.x, p.y + .45 * p.s, p.z); d.scale.setScalar(p.s); }, { cast: true });
    inst(new THREE.SphereGeometry(.14, 10, 8), M(0xffffff), P.length, (i, d) => { const p = P[i]; d.position.set(p.x, p.y + 1.78 * p.s, p.z); d.scale.setScalar(p.s); return new THREE.Color([0x8d5524, 0xc68642, 0xe0ac69, 0x6b4423][i % 4]); }, { cast: false });
  }
  const car = (x, z, rot, body) => {
    const grp = new THREE.Group(); grp.position.set(x, .1, z); grp.rotation.y = rot; g.add(grp);
    const A = (geo, m, px, py, pz, o = {}) => add(geo, m, px, py, pz, { parent: grp, ...o });
    const prof = pts => { const sh = new THREE.Shape(pts.map(([a, c]) => new THREE.Vector2(a, c))); return sh; };
    const bodyG = new THREE.ExtrudeGeometry(prof([[-2.25, .35], [2.25, .35], [2.3, .85], [2.0, 1.0], [1.1, 1.08], [.55, 1.7], [-1.55, 1.72], [-2.1, 1.1], [-2.28, .95]]), { depth: 1.85, bevelEnabled: true, bevelSize: .06, bevelThickness: .06, bevelSegments: 2 });
    bodyG.translate(0, 0, -.925); A(bodyG, M(body, { roughness: .35, metalness: .3 }), 0, 0, 0);
    const winG = new THREE.ExtrudeGeometry(prof([[-1.9, 1.14], [1.0, 1.14], [.6, 1.62], [-1.5, 1.62]]), { depth: 1.98, bevelEnabled: false }); winG.translate(0, 0, -.99);
    A(winG, M(0x1b2a38, { roughness: .15, metalness: .4 }), 0, 0, 0, { cast: false });
    [[1.4, .95], [1.4, -.95], [-1.4, .95], [-1.4, -.95]].forEach(([wx, wz]) => {
      const w = new THREE.CylinderGeometry(.38, .38, .3, 18); w.rotateX(PI / 2); A(w, M(0x1a1a1a), wx, .38, wz, { cast: false });
      const h = new THREE.CylinderGeometry(.2, .2, .32, 12); h.rotateX(PI / 2); A(h, steelMat, wx, .38, wz, { cast: false });
    });
    A(new THREE.BoxGeometry(.06, .16, 1.4), BASIC(0xfff7d0), 2.34, .82, 0, { cast: false, pick: false });
    A(new THREE.BoxGeometry(.06, .16, 1.4), BASIC(0xc0392b), -2.32, .9, 0, { cast: false, pick: false });
    stepsSolid([x, z, 2.4, 2.4]);
  };
  car(-14.5, FZ + 3.6, .3, 0xf4f4f2); car(14.5, FZ + 5.2, -.45, 0x7d8791);

  /* ----- walk-mode collision (rounded drum approximated by 3 boxes) + keep random trees off the forecourt ----- */
  colliders.push({ x: b.x, z: b.z, hw, hd: hd - R + 1 }, { x: b.x, z: b.z, hw: FW + 1, hd }, { x: b.x, z: b.z, hw: hw - 3, hd: hd - 3 });
  stepsSolid([0, FZ, 3.7, 3.7]);

  return {
    top: H + 1,
    keepClear: [[b.x - 36, b.x + 36, b.z + hd, b.z + PZ1 + 3]],
  };
}
function TAU() { return PI * 2; }
