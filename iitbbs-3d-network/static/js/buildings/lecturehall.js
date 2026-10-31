/* ============================================================================
   IIT Bhubaneswar - Lecture Hall Complexes (Lalitgiri, Ratnagiri, Pushpagiri)
   plus the shared amphitheatre they surround.

   Built from the satellite view + street photos:
     - three-storey rounded-rectangle drum clad in cream/tan stone panels
     - ribbon glazing on every floor, wrapping round both curved ends
     - parapet, rooftop solar-panel ring, big silver lens-shaped metal roof with seams
     - cantilevered steel pergola (rafters + rim + braces) round the curved ends
     - variant "hall"       (Lalitgiri / Ratnagiri): tall cream pilasters across the front,
                            green banners, full-width stone steps, tan paver forecourt
     - variant "pushpagiri": glass curtain wall, tall white columns, balconies with glass
                            railings, diagonal braces, floating ring canopy, red-carpet entrance
     - amphitheatre: terraced concentric rings with stone kerbs, cross paths, east stage with
                     stepped half-rings and a hexagon floor

   Local coordinates: building centre = (0,0,0), FRONT faces +z, y up, 1 unit = 1 m.
   The group is rotated by b.rot so the front faces the amphitheatre.
   b.w / b.d are the WORLD-axis footprint (so rotated halls swap them).
   ============================================================================ */
import * as THREE from 'three';

const PI = Math.PI, X_AXIS = new THREE.Vector3(1, 0, 0), UPV = new THREE.Vector3(0, 1, 0);

/* ---------- procedural textures (shared, built once) ---------- */
const hash = (a, b = 0, c = 0) => {
  let h = Math.imul(a | 0, 374761393) ^ Math.imul(b | 0, 668265263) ^ Math.imul(c | 0, 1274126177);
  h = Math.imul(h ^ (h >>> 13), 1103515245);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
};
function dataTex(w, h, fn) {
  const d = new Uint8Array(w * h * 4);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const [r, g, b] = fn(x / w, y / h, x, y), i = (y * w + x) * 4;
    d[i] = r; d[i + 1] = g; d[i + 2] = b; d[i + 3] = 255;
  }
  const t = new THREE.DataTexture(d, w, h, THREE.RGBAFormat);
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace;
  t.generateMipmaps = true; t.minFilter = THREE.LinearMipmapLinearFilter; t.magFilter = THREE.LinearFilter;
  t.anisotropy = 8; t.needsUpdate = true; return t;
}
let TX = null;
function textures() {
  if (TX) return TX;
  // cladding: tile = 2.4 m wide x 4 m tall, 2 panels across, 4 rows, soft per-panel variation + dark joints
  const clad = dataTex(256, 256, (u, v, px, py) => {
    const col = Math.floor(u * 2), row = Math.floor(v * 4), fu = u * 2 - col, fv = v * 4 - row;
    const k = (.93 + hash(col, row, 11) * .1) * (.97 + hash(px, py, 5) * .05) * ((fu < .03 || fv < .035) ? .78 : 1);
    return [226 * k, 208 * k, 182 * k];
  });
  clad.repeat.set(1 / 2.4, 1 / 4);
  // pavers: tile = 2.4 m, 4 x 8 bricks, running bond
  const pave = dataTex(256, 256, (u, v, px, py) => {
    const row = Math.floor(v * 8), cu = u * 4 + (row & 1) * .5, bi = Math.floor(cu), fu = cu - bi, fv = v * 8 - row;
    const k = (.9 + hash(((bi % 4) + 4) % 4, row, 2) * .16) * (.96 + hash(px, py, 7) * .06) * ((fv < .07 || fu < .05) ? .8 : 1);
    return [184 * k, 176 * k, 164 * k];
  });
  // metal roof: radial standing seams + concentric panel rings
  const roof = dataTex(256, 256, (u, v, px, py) => {
    const a = (u * 36) % 1, b = (v * 7) % 1;
    const k = ((a < .035 || a > .97) ? .62 : 1) * ((b < .03) ? .72 : 1) * (.96 + hash(px >> 2, py >> 2, 3) * .06);
    return [204 * k, 209 * k, 214 * k];
  });
  // amphitheatre dry-grass rings
  const grass = dataTex(128, 128, (u, v, px, py) => { const k = .86 + hash(px, py, 4) * .3; return [160 * k, 128 * k, 92 * k]; });
  return (TX = { clad, pave, roof, grass });
}

/* ---------- geometry helpers ---------- */
function roundedRect(hw, hd, r, seg = 14) {
  const cs = [[hw - r, hd - r, 0], [-(hw - r), hd - r, PI / 2], [-(hw - r), -(hd - r), PI], [hw - r, -(hd - r), PI * 1.5]], p = [];
  for (const [cx, cz, a0] of cs) for (let j = 0; j <= seg; j++) { const a = a0 + j / seg * PI / 2; p.push([cx + r * Math.cos(a), cz + r * Math.sin(a)]); }
  return p;
}
function extrudeXZ(pts, depth, y0, holes = []) {
  const V = ([x, z]) => new THREE.Vector2(x, -z), sh = new THREE.Shape(pts.map(V));
  holes.forEach(h => sh.holes.push(new THREE.Path(h.map(V))));
  const geo = new THREE.ExtrudeGeometry(sh, { depth, bevelEnabled: false, curveSegments: 1 });
  geo.rotateX(-PI / 2); geo.translate(0, y0, 0); return geo;
}
function resample(poly, step) {            // equal-spacing points round a closed polygon, with tangent + outward normal
  const n = poly.length, segs = []; let L = 0;
  for (let i = 0; i < n; i++) { const a = poly[i], c = poly[(i + 1) % n], l = Math.hypot(c[0] - a[0], c[1] - a[1]); segs.push([a, c, l, L]); L += l; }
  const cnt = Math.max(8, Math.round(L / step)), out = [];
  for (let k = 0; k < cnt; k++) {
    const s = k / cnt * L, q = segs.find(q => q[2] > 0 && s >= q[3] && s < q[3] + q[2]) || segs[n - 1], l = q[2] || 1, t = (s - q[3]) / l;
    const x = q[0][0] + (q[1][0] - q[0][0]) * t, z = q[0][1] + (q[1][1] - q[0][1]) * t, tx = (q[1][0] - q[0][0]) / l, tz = (q[1][1] - q[0][1]) / l;
    let nx = tz, nz = -tx; if (nx * x + nz * z < 0) { nx = -nx; nz = -nz; }
    out.push({ x, z, tx, tz, nx, nz });
  }
  return out;
}
function uvScale(geo, su, sv) { const uv = geo.attributes.uv; for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * su, uv.getY(i) * sv); return geo; }
const qYaw = a => new THREE.Quaternion().setFromAxisAngle(UPV, a);
const beam = (a, b) => {                  // unit-length-x box stretched between two points
  const v = new THREE.Vector3(b[0] - a[0], b[1] - a[1], b[2] - a[2]), len = v.length();
  return { p: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2], q: new THREE.Quaternion().setFromUnitVectors(X_AXIS, v.normalize()), s: [len, 1, 1] };
};
const M = (c, o = {}) => new THREE.MeshStandardMaterial({ color: c, roughness: .85, metalness: 0, ...o });
const BASIC = (c, o = {}) => new THREE.MeshBasicMaterial({ color: c, ...o });
function instanced(parent, geo, mat, items, cast = false) {
  const m = new THREE.InstancedMesh(geo, mat, Math.max(1, items.length)), d = new THREE.Object3D(), col = new THREE.Color();
  items.forEach((it, i) => {
    d.position.set(...it.p); d.quaternion.copy(it.q || new THREE.Quaternion()); d.scale.set(...(it.s || [1, 1, 1])); d.updateMatrix(); m.setMatrixAt(i, d.matrix);
    if (it.c !== undefined) m.setColorAt(i, col.set(it.c));
  });
  m.count = items.length; m.castShadow = cast; m.receiveShadow = true; m.instanceMatrix.needsUpdate = true; parent.add(m); return m;
}
function namePlate(text, w, h) {
  if (typeof document === 'undefined') return BASIC(0xe9dfca);
  const c = document.createElement('canvas'); c.width = 1024; c.height = Math.round(1024 * h / w);
  const x = c.getContext('2d'); x.fillStyle = '#ece3d0'; x.fillRect(0, 0, c.width, c.height);
  x.fillStyle = '#6b4a2e'; x.fillRect(0, 0, c.width, 8); x.fillRect(0, c.height - 8, c.width, 8);
  x.fillStyle = '#2b2118'; x.font = '600 ' + Math.round(c.height * .5) + 'px "Segoe UI",Arial,sans-serif'; x.textAlign = 'center'; x.textBaseline = 'middle';
  x.fillText(text, c.width / 2, c.height / 2 + 3);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  return new THREE.MeshBasicMaterial({ map: t });
}

/* ============================================================================ */
export function buildLectureHall({ g, b, pickables, colliders }) {
  const T = textures(), variant = b.variant || 'hall', rot = b.rot || 0, odd = Math.abs(Math.sin(rot)) > .5;
  const W = odd ? b.d : b.w, D = odd ? b.w : b.d, H = b.h, hw = W / 2, hd = D / 2;
  const R = Math.min(13, hw - 4, hd - 4), FW = hw - R, FL = (H - .5) / 3, Y0 = .5;
  g.rotation.y = rot;

  const add = (geo, m, x = 0, y = 0, z = 0, cast = true) => {
    const me = new THREE.Mesh(geo, m); me.position.set(x, y, z); me.castShadow = cast; me.receiveShadow = true;
    me.userData.id = b.id; g.add(me); pickables.push(me); return me;
  };
  const deco = (geo, m, x = 0, y = 0, z = 0, cast = false) => { const me = new THREE.Mesh(geo, m); me.position.set(x, y, z); me.castShadow = cast; me.receiveShadow = true; g.add(me); return me; };
  const box = (w, h, d) => new THREE.BoxGeometry(w, h, d);
  const outline = (h, d, r) => roundedRect(h, d, r, 14);

  /* ----- materials ----- */
  const tint = variant === 'pushpagiri' ? 0xf4f0e6 : 0xffffff;
  const cladMat = M(tint, { map: T.clad, roughness: .8 });
  const plinthMat = M(0x8d877d), copingMat = M(0xe3d8c2), deckMat = M(0x8e9193);
  const whiteMat = M(0xf6f4ef, { roughness: .55 }), steelMat = M(0xd7dbde, { roughness: .45, metalness: .1 });
  const glassMat = M(0x23465e, { roughness: .12, metalness: .25, emissive: 0x0b2030, emissiveIntensity: .8 });
  const solarMat = M(0x1b3358, { roughness: .28, metalness: .15 });
  const roofMat = M(0xffffff, { map: T.roof, roughness: .38, metalness: .1 });
  const stepMat = M(0xcdc6b8), paverMat = M(0xffffff, { map: T.pave });
  const lampMat = BASIC(0xffe2a0), carpet = M(0xb8322a, { roughness: .9 });

  /* ----- mass: plinth, cladded drum, ribbon glazing, parapet, roof deck ----- */
  add(extrudeXZ(outline(hw + 1.2, hd + 1.2, R + 1.2), Y0, 0), plinthMat);
  add(extrudeXZ(outline(hw, hd, R), H - Y0, Y0), cladMat);
  for (let f = 0; f < 3; f++) add(extrudeXZ(outline(hw + .1, hd + .1, R + .1), 1.9, Y0 + f * FL + 1.05), glassMat, 0, 0, 0, false);
  add(extrudeXZ(outline(hw + .25, hd + .25, R + .25), .9, H, [outline(hw - .45, hd - .45, R - .45)]), copingMat);
  add(extrudeXZ(outline(hw - .4, hd - .4, R - .4), .14, H - .06), deckMat, 0, 0, 0, false);

  /* ----- roof: seamed silver lens, ridge, rooftop solar ring ----- */
  const rx = hw * .62, rz = hd * .55, ry = 3.8, by = H + .14;
  const drum = deco(new THREE.CylinderGeometry(1, 1, 1.1, 64), M(0xd9d1c0), 0, by + .55, 0, true); drum.scale.set(rx * 1.02, 1, rz * 1.02);
  const dome = add(new THREE.SphereGeometry(1, 72, 24, 0, PI * 2, 0, PI / 2), roofMat, 0, by + 1.1, 0); dome.scale.set(rx, ry, rz);
  deco(box(rx * 2.02, .2, .55), M(0x6e7479, { roughness: .5 }), 0, by + 1.1 + ry - .08, 0, false);
  const P = resample(outline(hw - 3.4, hd - 3.4, R - 3.4), 2.6), panels = [];
  P.forEach(p => {
    const yaw = -Math.atan2(p.tz, p.tx), s = (-p.tz * p.nx + p.tx * p.nz) > 0 ? 1 : -1;
    panels.push({ p: [p.x, H + .45, p.z], q: qYaw(yaw).multiply(new THREE.Quaternion().setFromAxisAngle(X_AXIS, .32 * s)) });
  });
  instanced(g, box(2.3, .07, 1.5), solarMat, panels, true);

  /* ----- cantilevered steel pergola round the curved ends (not across the front) ----- */
  {
    const S = resample(outline(hw, hd, R), 1.5), raf = [], rim = [], brace = [], YP = H + .95, OUT = 2.6;
    const keep = S.map(p => !(p.nz > .85 && p.z > 0));
    S.forEach((p, i) => {
      if (!keep[i]) return;
      const o = [p.x + p.nx * OUT, YP + .12, p.z + p.nz * OUT], inn = [p.x, YP, p.z];
      raf.push(beam(inn, o));
      if (i % 2 === 0) brace.push(beam(o, [p.x + p.nx * .4, H - .6, p.z + p.nz * .4]));
      const j = (i + 1) % S.length;
      if (keep[j]) { const q = S[j]; rim.push(beam(o, [q.x + q.nx * OUT, YP + .12, q.z + q.nz * OUT])); rim.push(beam(inn, [q.x, YP, q.z])); }
    });
    instanced(g, box(1, .13, .13), steelMat, raf, true);
    instanced(g, box(1, .17, .17), whiteMat, rim, true);
    instanced(g, box(1, .09, .09), steelMat, brace, false);
  }

  /* ----- front: entrance steps, forecourt ----- */
  const stepW = variant === 'pushpagiri' ? 16 : 2 * FW + 3, zs = hd + 1.2;
  for (let j = 1; j <= 3; j++) { const ext = (4 - j) * .6; add(box(stepW, .16 * j, ext), stepMat, 0, .08 * j, zs + ext / 2); }
  deco(uvScale(box(2 * FW + 20, .1, 15), (2 * FW + 20) / 2.4, 15 / 2.4), paverMat, 0, .05, hd + 1.2 + 7.5 + .4);
  add(box(3.4, .06, 8), carpet, 0, .08, zs + 1.9 + 2.4, false);

  const door = BASIC(0xf3d59a);
  if (variant === 'pushpagiri') {
    /* glass curtain wall, mullions, warm lit entrance */
    const zc = hd + .35, cw = 2 * FW + .6;
    add(box(cw, H - Y0, .25), glassMat, 0, Y0 + (H - Y0) / 2, zc, false);
    const mull = [], n = Math.round(cw / 1.7);
    for (let i = 0; i <= n; i++) { const x = -cw / 2 + cw * i / n; mull.push(beam([x, Y0, zc + .18], [x, H, zc + .18])); }
    for (let f = 0; f <= 3; f++) mull.push(beam([-cw / 2, Y0 + f * FL + .02, zc + .18], [cw / 2, Y0 + f * FL + .02, zc + .18]));
    instanced(g, box(1, .12, .16), whiteMat, mull, false);
    deco(box(6.4, FL - .6, .12), door, 0, Y0 + (FL - .6) / 2 + .1, zc + .22);
    /* tall white columns, balconies, glass railing, braces */
    const nc = 6, cz = hd + 2.4, ctop = H + 3.2, cols = [], braces = [];
    for (let i = 0; i < nc; i++) {
      const x = -FW - .6 + (2 * FW + 1.2) * i / (nc - 1);
      add(box(.85, ctop - Y0, .85), whiteMat, x, Y0 + (ctop - Y0) / 2, cz);
      braces.push(beam([x, ctop - .3, cz], [x, H + .8, hd + .5]));
    }
    for (let f = 1; f <= 2; f++) {
      const y = Y0 + f * FL;
      add(box(2 * FW + 3, .4, 3.2), whiteMat, 0, y, hd + 1.7);
      deco(box(2 * FW + 3, .95, .07), M(0x8fbfd3, { transparent: true, opacity: .35, roughness: .1 }), 0, y + .9, hd + 3.25);
    }
    instanced(g, new THREE.CylinderGeometry(.06, .06, 1, 6).rotateZ(PI / 2), steelMat, braces, true);
    /* floating ring canopy above the roof edge */
    add(extrudeXZ(outline(hw + 2.4, hd + 2.4, R + 2.4), .38, ctop - .2, [outline(hw - .8, hd - .8, R - .8)]), whiteMat);
  } else {
    /* tall cream pilasters across the front, cornice, green banners */
    const fins = [], n = Math.floor(2 * FW / 2.3);
    for (let i = 0; i <= n; i++) {
      const x = -FW + 2 * FW * i / n; if (Math.abs(x) < 2.2) continue;
      add(box(.85, H + .9 - Y0, 1.1), M(0xe6d6b8, { map: T.clad, roughness: .8 }), x, Y0 + (H + .9 - Y0) / 2, hd + .1);
    }
    add(box(2 * FW + 2.6, .8, 1.9), copingMat, 0, H + .45, hd + .6);
    deco(box(5, FL - .5, .3), BASIC(0xe8cf98), 0, Y0 + (FL - .5) / 2 + .2, hd + .3);
    [-3, 3].forEach(x => deco(box(.55, 4.4, .08), M(0x2f9e57, { roughness: .7 }), x, Y0 + 2.6, hd + .78));
  }
  /* name plate above the entrance */
  deco(new THREE.PlaneGeometry(9, 1.15), namePlate(b.name, 9, 1.15), 0, Y0 + FL + .75, hd + (variant === 'pushpagiri' ? .52 : 1.2));

  /* ----- forecourt dressing: lamps, flower pots, small trees, people ----- */
  const lampX = [-FW - 3, -FW * .35, FW * .35, FW + 3], lamps = [], poles = [];
  lampX.forEach(x => { poles.push({ p: [x, 2.1, hd + 9] }); lamps.push({ p: [x, 4.3, hd + 9] }); });
  instanced(g, new THREE.CylinderGeometry(.08, .1, 4.2, 6), M(0x3a3f45, { metalness: .3 }), poles, true);
  instanced(g, new THREE.SphereGeometry(.3, 10, 8), lampMat, lamps);
  const pots = [], blooms = [];
  for (let i = 0; i < 12; i++) {
    const x = -stepW / 2 + 1 + (stepW - 2) * i / 11; if (Math.abs(x) < 2.6) continue;
    pots.push({ p: [x, .5, zs + 2.3], c: 0xa8603c }); blooms.push({ p: [x, 1.05, zs + 2.3], s: [1, .8, 1], c: [0xf2a51c, 0xe4572e, 0xf6d04d][i % 3] });
  }
  instanced(g, new THREE.CylinderGeometry(.3, .22, .6, 8), M(0xffffff), pots);
  instanced(g, new THREE.SphereGeometry(.38, 10, 8), M(0xffffff), blooms);
  const trees = [], tops = [];
  [[-FW - 8, hd + 8], [FW + 8, hd + 8], [-FW - 12, hd + 1], [FW + 12, hd + 1]].forEach(([x, z], i) => {
    trees.push({ p: [x, 1.6, z] }); tops.push({ p: [x, 4.4, z], s: [1, .85, 1], c: [0x3f8a45, 0x4c9a4a, 0x35763f][i % 3] });
  });
  instanced(g, new THREE.CylinderGeometry(.22, .3, 3.2, 6), M(0x7a5236), trees, true);
  instanced(g, new THREE.IcosahedronGeometry(2.1, 1), M(0xffffff), tops, true);
  const ppl = [], heads = [], cols = [0x2d5f8b, 0xb5452f, 0xe8e2d4, 0x3b7d4f, 0x7a4a8c, 0xd6a02a];
  for (let i = 0; i < 6; i++) {
    const x = (hash(i, 3, 1) - .5) * (2 * FW + 8), z = hd + 5 + hash(i, 4, 2) * 7;
    ppl.push({ p: [x, .95, z], c: cols[i] }); heads.push({ p: [x, 1.68, z], c: [0x8d5524, 0xc68642, 0xe0ac69][i % 3] });
  }
  instanced(g, new THREE.CapsuleGeometry(.23, .5, 3, 8), M(0xffffff), ppl, true);
  instanced(g, new THREE.SphereGeometry(.15, 10, 8), M(0xffffff), heads);

  colliders.push({ x: b.x, z: b.z, hw: b.w / 2, hd: b.d / 2 });
  return { keepClear: [[b.x - b.w / 2 - 12, b.x + b.w / 2 + 12, b.z - b.d / 2 - 12, b.z + b.d / 2 + 12]] };
}

/* ============================================================================
   Amphitheatre: five terraced grass rings (descending to the centre) with stone
   kerbs and a cross of paths, and a stepped semicircular stage on the east side.
   Called with the WORLD centre; opens towards +x where the stage sits.
   ============================================================================ */
export function buildAmphitheatre({ scene, cx, cz, R }) {
  const T = textures(), g = new THREE.Group(); g.position.set(cx, 0, cz); scene.add(g);
  const grass = M(0xffffff, { map: T.grass, roughness: 1 }), kerb = M(0xd3cbbb, { roughness: .8 }), path = M(0xc4bba9, { roughness: .85 });
  const arcPts = (r, a0, a1, n = 64) => { const p = []; for (let i = 0; i <= n; i++) { const a = a0 + (a1 - a0) * i / n; p.push([r * Math.cos(a), r * Math.sin(a)]); } return p; };
  const full = r => arcPts(r, 0, PI * 2, 72).slice(0, -1);
  const mk = (geo, m, x = 0, y = 0, z = 0, cast = false) => { const me = new THREE.Mesh(geo, m); me.position.set(x, y, z); me.castShadow = cast; me.receiveShadow = true; g.add(me); return me; };

  const N = 5, r0 = R * .16, bw = (R - r0) / N;
  for (let k = 0; k < N; k++) {                    // k = 0 outermost / highest
    const ro = R - k * bw, ri = ro - bw, h = .22 + (N - 1 - k) * .0 + (N - k) * .2;
    mk(extrudeXZ(full(ro), h, 0, [full(ri + .55)]), grass);
    mk(extrudeXZ(full(ri + .55), h + .1, 0, [full(ri)]), kerb);
    for (let a = 0; a < 4; a++) {                  // cross of paths, stepping down with the terraces
      const ang = a * PI / 2, rm = (ro + ri) / 2;
      const s = mk(new THREE.BoxGeometry(bw, h + .06, 2.6), path, Math.cos(ang) * rm, (h + .06) / 2, Math.sin(ang) * rm); s.rotation.y = -ang;
    }
  }
  mk(new THREE.CylinderGeometry(r0, r0, .22, 48), kerb, 0, .11, 0);
  const hexA = mk(new THREE.CylinderGeometry(r0 * .62, r0 * .62, .3, 6), M(0xd9a98a), 0, .15, 0);

  /* stage: stepped half-discs on the east rim, hexagon floor in the middle */
  const SX = R + 1, st = new THREE.Group(); st.position.set(SX, 0, 0); g.add(st);
  [[15, .3, 0xcfc7b8], [12, .5, 0xd8d0c2], [9.2, .7, 0xcfc7b8]].forEach(([r, h, c]) => {
    const e = new THREE.Mesh(extrudeXZ([...arcPts(r, -PI / 2, PI / 2, 32)], h, 0), M(c, { roughness: .8 })); e.castShadow = e.receiveShadow = true; st.add(e);
  });
  [[6.2, 0xd9a98a, .86], [4.8, 0xc98f6f, .9], [3.3, 0xe1b79a, .94]].forEach(([r, c, y]) => {
    const e = new THREE.Mesh(new THREE.CylinderGeometry(r, r, y, 6), M(c, { roughness: .8 })); e.position.set(1.5, y / 2, 0); e.receiveShadow = true; st.add(e);
  });
  const lampItems = [];
  [-PI / 2, -PI / 4, PI / 4, PI / 2].forEach(a => lampItems.push({ p: [Math.cos(a) * 15.5, 1.8, Math.sin(a) * 15.5] }));
  instanced(st, new THREE.CylinderGeometry(.08, .1, 3, 6), M(0x3a3f45), lampItems, true);
  instanced(st, new THREE.SphereGeometry(.28, 10, 8), BASIC(0xffe2a0), lampItems.map(l => ({ p: [l.p[0], 3.3, l.p[2]] })));

  return { keepClear: [[cx - R - 8, cx + R + 22, cz - R - 8, cz + R + 8]] };
}
