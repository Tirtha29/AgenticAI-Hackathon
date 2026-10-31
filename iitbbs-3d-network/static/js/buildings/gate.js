/* ============================================================================
   IIT Bhubaneswar - Main Gate (detailed model)
   Built from the two reference photos of the entrance:
     - long cream beam, five gold stripes, lettering "INDIAN INSTITUTE OF TECHNOLOGY BHUBANESWAR"
     - three round white columns each side, central pillar with emblem and gold bands
     - two bays of black wrought-iron gates (4 leaves) with gold spoked wheels and spear finials
     - stepped end blocks with gold bands, lower wings, boundary wall with pillars
     - guard cabins, planters, lamp posts, palms, paver aprons, white road markings

   Local coordinates: gate centre = (0,0,0). OUTSIDE (the road from Jatni) is -z,
   the campus is +z. y is up, 1 unit = 1 m. Overall width of the arch is 46 m.

   The four gate leaves swing open/closed. Walk-mode collision is switched off while open.
   ============================================================================ */
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

const PI = Math.PI;

/* ---------- CONFIG (tweak here) ---------- */
const CFG = {
  beamHW: 23, beamY0: 8.6, beamY1: 14.25,     // beam half width, bottom, top
  hingeOuter: 9.8, hingeInner: 1.5,           // x of the leaf hinges
  leafH: 4.3,
  text: 'INDIAN  INSTITUTE  OF  TECHNOLOGY  BHUBANESWAR',
  cream: 0xeee6cd, gold: 0xdcae2b,
};

/* ---------- canvas textures ---------- */
function canvasTex(w, h, draw, aniso = 8) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = aniso; t.needsUpdate = true; return t;
}
function signTexture(text) {
  return canvasTex(4096, 256, (x, w, h) => {
    x.clearRect(0, 0, w, h);
    let fs = 150; const font = s => `700 ${s}px "Trebuchet MS","Segoe UI",Arial,sans-serif`, sp = 0.16;
    x.font = font(fs);
    const measure = s => { x.font = font(s); let t = 0; for (const ch of text) t += x.measureText(ch).width + s * sp; return t; };
    while (measure(fs) > w * .94) fs -= 4;
    const total = measure(fs); let px = (w - total) / 2;
    x.textBaseline = 'middle'; x.font = font(fs);
    for (const ch of text) {
      x.fillStyle = 'rgba(255,250,235,.9)'; x.fillText(ch, px + 3, h / 2 + 4);   // soft emboss highlight
      x.fillStyle = '#2b2a28'; x.fillText(ch, px, h / 2 + 1);
      px += x.measureText(ch).width + fs * sp;
    }
  });
}
function emblemTexture() {
  return canvasTex(256, 256, (x, w, h) => {
    const c = w / 2;
    x.fillStyle = '#d9b24a'; x.beginPath(); x.arc(c, c, 124, 0, PI * 2); x.fill();
    x.fillStyle = '#12233b'; x.beginPath(); x.arc(c, c, 104, 0, PI * 2); x.fill();
    x.strokeStyle = '#e9d9a6'; x.lineWidth = 9;                       // ship's wheel
    x.beginPath(); x.arc(c, c - 18, 40, 0, PI * 2); x.stroke();
    for (let i = 0; i < 8; i++) { const a = i * PI / 4; x.beginPath(); x.moveTo(c + Math.cos(a) * 24, c - 18 + Math.sin(a) * 24); x.lineTo(c + Math.cos(a) * 62, c - 18 + Math.sin(a) * 62); x.stroke(); }
    x.fillStyle = '#e9d9a6'; x.beginPath(); x.moveTo(c - 70, c + 52); x.lineTo(c + 70, c + 52); x.lineTo(c + 48, c + 78); x.lineTo(c - 48, c + 78); x.closePath(); x.fill();
    x.strokeStyle = '#e9d9a6'; x.lineWidth = 6; x.beginPath(); x.moveTo(c - 80, c + 90); x.quadraticCurveTo(c, c + 108, c + 80, c + 90); x.stroke();
  });
}
function posterTexture() {
  return canvasTex(512, 320, (x, w, h) => {
    const g = x.createLinearGradient(0, 0, w, h); g.addColorStop(0, '#f4a23a'); g.addColorStop(1, '#e0572b');
    x.fillStyle = g; x.fillRect(0, 0, w, h);
    x.fillStyle = '#12335c'; x.fillRect(0, h - 90, w, 90);
    x.fillStyle = '#fff'; x.font = '700 54px "Segoe UI",Arial,sans-serif'; x.textAlign = 'center';
    x.fillText('WELCOME TO', w / 2, 96); x.fillText('IIT BHUBANESWAR', w / 2, 160);
    x.font = '600 32px "Segoe UI",Arial,sans-serif'; x.fillStyle = '#f7e7b0'; x.fillText('Odisha  |  Est. 2008', w / 2, h - 34);
    x.strokeStyle = '#fff'; x.lineWidth = 8; x.strokeRect(10, 10, w - 20, h - 20);
  });
}
function paverTexture(rx, ry) {
  const t = canvasTex(128, 128, (x, w, h) => {
    x.fillStyle = '#9a7c6b'; x.fillRect(0, 0, w, h);
    for (let r = 0; r < 8; r++) for (let c = 0; c < 4; c++) {
      const off = (r & 1) * 16, v = 168 + ((r * 7 + c * 13) % 5) * 5;
      x.fillStyle = `rgb(${v + 14},${v - 18},${v - 34})`; x.fillRect(c * 32 + off + 1, r * 16 + 1, 30, 14);
      if (off) x.fillRect(c * 32 - 31, r * 16 + 1, 30, 14);
    }
  }, 8);
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(rx, ry); return t;
}

/* ---------- gate leaf: one merged iron mesh + one merged gold mesh ---------- */
function leafGeometries(L, H) {
  const iron = [], gold = [];
  const bx = (w, h, d, x, y, z) => { const g = new THREE.BoxGeometry(w, h, d); g.translate(x, y, z); return g; };
  [[.2, .14], [1.0, .08], [3.15, .08], [H - .06, .14]].forEach(([y, t]) => iron.push(bx(L, t, .09, L / 2, y, 0)));
  const n = Math.round(L / .27);
  for (let i = 0; i <= n; i++) {
    const x = .03 + (L - .06) * i / n;
    iron.push(bx(.04, H - .2, .04, x, H / 2, 0));
    const f = new THREE.ConeGeometry(.036, .22, 4); f.translate(x, H + .08, 0); gold.push(f);
  }
  for (let i = 0; i < 7; i++) {                          // little scroll rings in the lower and upper panels
    const x = L * (i + .5) / 7;
    [.6, (3.15 + H - .06) / 2].forEach(y => { const t = new THREE.TorusGeometry(.11, .013, 5, 14); t.translate(x, y, 0); iron.push(t); });
  }
  const wc = [L / 2, 2.08];                             // gold spoked wheel
  const ring = new THREE.TorusGeometry(.72, .05, 8, 28); ring.translate(wc[0], wc[1], 0); gold.push(ring);
  const ring2 = new THREE.TorusGeometry(.22, .035, 6, 16); ring2.translate(wc[0], wc[1], 0); gold.push(ring2);
  const hub = new THREE.CylinderGeometry(.1, .1, .1, 12); hub.rotateX(PI / 2); hub.translate(wc[0], wc[1], 0); gold.push(hub);
  for (let k = 0; k < 6; k++) { const s = bx(.035, 1.44, .035, 0, 0, 0); s.rotateZ(k * PI / 6); s.translate(wc[0], wc[1], 0); gold.push(s); }
  return { iron: mergeGeometries(iron), gold: mergeGeometries(gold) };
}

export function buildGate({ g, b, pickables, colliders }) {
  const id = b.id, { beamHW: BW, beamY0: Y0, beamY1: Y1 } = CFG;
  const M = (c, o = {}) => new THREE.MeshStandardMaterial({ color: c, roughness: .82, metalness: 0, ...o });
  const cream = M(CFG.cream), creamDk = M(0xd8cdb0), gold = M(CFG.gold, { roughness: .42, metalness: .3 });
  const plinth = M(0xa9a190), ironM = M(0x16161a, { roughness: .45, metalness: .6 }), brass = M(0xcfa032, { roughness: .35, metalness: .65 });
  const glass = M(0x2b4a66, { roughness: .2, emissive: 0x0d2236 }), terracotta = M(0xa8603c), leafGreen = M(0x4c9a4a);
  const white = M(0xf6f3ea, { roughness: .6 });

  const add = (geo, mat, x = 0, y = 0, z = 0, o = {}) => {
    const me = new THREE.Mesh(geo, mat); me.position.set(x, y, z);
    me.castShadow = o.cast ?? true; me.receiveShadow = o.recv ?? true; me.userData.id = id;
    g.add(me); if (o.pick !== false) pickables.push(me); return me;
  };
  // box from extents: ext(material, x0,x1, y0,y1, z0,z1)
  const ext = (mat, x0, x1, y0, y1, z0, z1, o) => add(new THREE.BoxGeometry(Math.abs(x1 - x0), y1 - y0, Math.abs(z1 - z0)), mat, (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2, o);
  const col = (cx, cz, hw, hd, extra = {}) => { const c = { x: b.x + cx, z: b.z + cz, hw, hd, ...extra }; colliders.push(c); return c; };

  /* ===== the beam: cream with five gold stripes ===== */
  ext(gold, -BW - .2, BW + .2, Y0, 8.9, -3.15, 3.15);
  ext(cream, -BW, BW, 8.9, 10.7, -3, 3);
  ext(gold, -BW - .15, BW + .15, 10.7, 11.0, -3.1, 3.1);
  ext(cream, -BW, BW, 11.0, 13.4, -3, 3);
  ext(gold, -BW - .15, BW + .15, 13.4, 13.55, -3.1, 3.1);
  ext(cream, -BW, BW, 13.55, 14.0, -3, 3);
  ext(gold, -BW - .25, BW + .25, 14.0, Y1, -3.2, 3.2);
  const signMat = new THREE.MeshStandardMaterial({ map: signTexture(CFG.text), transparent: true, roughness: .7, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
  const signGeo = new THREE.PlaneGeometry(41, 2.56);
  add(signGeo, signMat, 0, 12.2, -3.016, { cast: false }).rotation.y = PI;      // front, reads from outside
  add(signGeo, signMat, 0, 12.2, 3.016, { cast: false });                       // back, reads from inside

  /* ===== stepped end blocks ===== */
  [-1, 1].forEach(s => {
    ext(plinth, s * 15.1, s * 23.1, 0, .7, -3.1, 3.1);
    ext(cream, s * 15.3, s * 23, .7, Y0, -2.8, 2.8);
    [[1.5, 1.8], [4.4, 4.7], [7.7, 8.0]].forEach(([a, c]) => ext(gold, s * 15.2, s * 23.1, a, c, -2.9, 2.9));
    [-1, 1].forEach(fz => {                                 // dark recessed panels + pilasters on both faces
      ext(creamDk, s * 17.0, s * 19.4, 2.0, 4.2, fz * 2.8, fz * 2.84, { cast: false });
      ext(creamDk, s * 17.0, s * 19.4, 5.0, 7.5, fz * 2.8, fz * 2.84, { cast: false });
      [s * 15.55, s * 22.75].forEach(px => ext(cream, px - .22, px + .22, .7, 7.7, fz * 2.8, fz * 3.0));
    });
    col(s * 19.15, 0, 3.95, 3.0);
    /* lower wing */
    ext(plinth, s * 23, s * 30.6, 0, .5, -2.7, 2.7);
    ext(cream, s * 23, s * 30.5, .5, 5.0, -2.5, 2.5);
    [[1.4, 1.7], [4.2, 4.5]].forEach(([a, c]) => ext(gold, s * 23, s * 30.6, a, c, -2.6, 2.6));
    ext(creamDk, s * 22.9, s * 30.7, 5.0, 5.35, -2.7, 2.7);
    col(s * 26.8, 0, 3.9, 2.75);
    /* boundary wall with pillars */
    ext(cream, s * 30.5, s * 48, 0, 2.2, -.3, .3);
    ext(gold, s * 30.5, s * 48, 2.2, 2.4, -.45, .45);
    for (let px = 33; px <= 47; px += 5.6) { ext(cream, s * px - .38, s * px + .38, 0, 2.75, -.5, .5); ext(gold, s * px - .45, s * px + .45, 2.75, 2.9, -.58, .58); }
    col(s * 39.3, 0, 8.8, .55);
  });
  const poster = add(new THREE.PlaneGeometry(5.2, 3.25), new THREE.MeshStandardMaterial({ map: posterTexture(), roughness: .6 }), -26.8, 2.9, -2.54, { cast: false });
  poster.rotation.y = PI;

  /* ===== column clusters: three round white columns each side ===== */
  [-1, 1].forEach(s => {
    const cx = s * 11.6;
    ext(plinth, cx - 2.4, cx + 2.4, 0, .5, -1.3, 1.3);
    for (let k = -1; k <= 1; k++) {
      const x = cx + k * 1.25, z = k === 0 ? -.25 : 0, r = k === 0 ? .52 : .44;
      add(new THREE.CylinderGeometry(r, r * 1.04, 8.0, 24), white, x, 4.5, z);
      add(new THREE.CylinderGeometry(r * 1.28, r * 1.28, .24, 24), white, x, .62, z);
      add(new THREE.CylinderGeometry(r * 1.22, r * 1.02, .32, 24), white, x, 8.34, z);
      add(new THREE.CylinderGeometry(r * 1.08, r * 1.08, .12, 24), gold, x, 7.7, z);
      add(new THREE.CylinderGeometry(r * 1.08, r * 1.08, .12, 24), gold, x, 1.1, z);
    }
    col(cx, 0, 2.0, .95);
  });

  /* ===== central pillar ===== */
  ext(plinth, -1.9, 1.9, 0, .8, -2.1, 2.1);
  ext(cream, -1.5, 1.5, .8, Y0, -1.8, 1.8);
  [[1.5, 1.8], [6.2, 6.5], [7.9, 8.2]].forEach(([a, c]) => ext(gold, -1.62, 1.62, a, c, -1.92, 1.92));
  const emb = new THREE.MeshStandardMaterial({ map: emblemTexture(), roughness: .5, metalness: .2 });
  [-1, 1].forEach(fz => {
    ext(creamDk, -.95, .95, 3.3, 4.9, fz * 1.8, fz * 1.835, { cast: false });
    const e = add(new THREE.CircleGeometry(.68, 32), emb, 0, 4.1, fz * 1.845, { cast: false }); if (fz < 0) e.rotation.y = PI;
  });
  col(0, 0, 1.95, 2.1);
  ext(terracotta, -1.45, 1.45, 0, .5, -2.9, -2.25);                   // planter at the foot of the pillar
  [-.9, 0, .9].forEach((px, i) => add(new THREE.IcosahedronGeometry(.42 + i % 2 * .08, 1), leafGreen, px, .72, -2.58));

  /* ===== wrought-iron gate leaves (open by default so you can walk through) ===== */
  const L = CFG.hingeOuter - CFG.hingeInner - .05, H = CFG.leafH, lg = leafGeometries(L, H);
  const defs = [   // [hinge x, closed angle, open angle] (angle = direction the leaf points in the x-z plane)
    [-CFG.hingeOuter, 0, 88], [-CFG.hingeInner, 180, 92], [CFG.hingeInner, 0, 88], [CFG.hingeOuter, 180, 92],
  ];
  const leaves = defs.map(([hx, a0, a1]) => {
    const grp = new THREE.Group(); grp.position.set(hx, .12, 0); g.add(grp);
    const mi = new THREE.Mesh(lg.iron, ironM), mg = new THREE.Mesh(lg.gold, brass);
    [mi, mg].forEach(m => { m.castShadow = true; m.receiveShadow = true; m.userData.id = id; grp.add(m); pickables.push(m); });
    return { grp, a0: a0 * PI / 180, a1: a1 * PI / 180 };
  });
  const bayCol = [-5.65, 5.65].map(x => col(x, 0, 4.2, .4, { off: true }));   // blocks walk mode only while closed
  const st = { open: 1, target: 1 };
  const pose = () => {
    leaves.forEach(l => { l.grp.rotation.y = -(l.a0 + (l.a1 - l.a0) * st.open); });
    bayCol.forEach(c => { c.off = st.open > .25; });
  };
  pose();

  /* ===== guard cabins just inside the wings ===== */
  [-1, 1].forEach(s => {
    const cx = s * 17.5;
    ext(cream, cx - 1.8, cx + 1.8, 0, 3.0, 4.2, 7.2);
    ext(gold, cx - 1.9, cx + 1.9, 2.5, 2.7, 4.1, 7.3);
    ext(creamDk, cx - 2.2, cx + 2.2, 3.0, 3.25, 3.9, 7.5);
    ext(glass, s * 15.7 - .02, s * 15.7 + .02, 1.1, 2.3, 4.7, 6.7, { cast: false });
    ext(glass, cx - 1.2, cx + 1.2, 1.1, 2.3, 4.18, 4.22, { cast: false });
    col(cx, 5.7, 2.0, 1.6);
  });

  /* ===== lamp posts, palms ===== */
  const post = new THREE.CylinderGeometry(.08, .12, 5.2, 8), lampG = new THREE.SphereGeometry(.32, 10, 8), lampM = new THREE.MeshBasicMaterial({ color: 0xffe9a8 });
  [[-14.6, -14], [14.6, -14], [-14.6, 14], [14.6, 14]].forEach(([x, z]) => { add(post, M(0x3a3f45, { metalness: .3 }), x, 2.6, z); add(lampG, lampM, x, 5.4, z, { cast: false, pick: false }); });
  const trunkG = new THREE.CylinderGeometry(.26, .45, 8.5, 7), frondG = new THREE.ConeGeometry(.8, 5.2, 3), trunkM = M(0x8a6a4a), frondM = M(0x4c9a4a, { side: THREE.DoubleSide });
  frondG.translate(0, 2.6, 0);
  const palm = (x, z, s = 1) => {
    add(trunkG, trunkM, x, 4.25 * s, z).scale.setScalar(s);
    for (let k = 0; k < 8; k++) { const f = add(frondG, frondM, x, 8.4 * s, z, { pick: false }); f.scale.set(1.3 * s, s, .28 * s); f.rotation.set(1.05 + (k % 3) * .1, k * .8, 0, 'YXZ'); }
  };
  [[-28.5, -6.2, 1], [28.5, -6.2, 1.05], [-35, -4.5, .95], [35, -4.5, 1], [-24.5, 6.5, 1], [24.5, 6.5, .95]].forEach(([x, z, s]) => palm(x, z, s));

  /* ===== ground: paver aprons and white road markings ===== */
  [-1, 1].forEach(s => {
    const mat = new THREE.MeshStandardMaterial({ map: paverTexture(8, 5), roughness: .9, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 });
    const p = ext(mat, s * 13.2, s * 31, 0, .12, -21, -3.3, { pick: false, cast: false });
    const kerb = M(0xcfc6b2); ext(kerb, s * 13, s * 13.25, 0, .2, -21, -3.3, { pick: false, cast: false });
  });
  const lineMat = new THREE.MeshStandardMaterial({ color: 0xf4f2ea, roughness: .8, polygonOffset: true, polygonOffsetFactor: -5, polygonOffsetUnits: -5 });
  const dashGeo = new THREE.PlaneGeometry(.2, 1.7); dashGeo.rotateX(-PI / 2);
  const dashes = []; for (const x of [0, -5.65, 5.65]) for (let z = -74; z < -5; z += 3.4) dashes.push([x, z]);
  const inst = new THREE.InstancedMesh(dashGeo, lineMat, dashes.length), D = new THREE.Object3D();
  dashes.forEach(([x, z], i) => { D.position.set(x, .13, z); D.updateMatrix(); inst.setMatrixAt(i, D.matrix); });
  inst.receiveShadow = true; g.add(inst);
  const strip = (x0, x1, z0, z1) => { const m = new THREE.Mesh(new THREE.PlaneGeometry(x1 - x0, z1 - z0).rotateX(-PI / 2), lineMat); m.position.set((x0 + x1) / 2, .13, (z0 + z1) / 2); m.receiveShadow = true; g.add(m); };
  strip(-12.5, -12.3, -75, -8); strip(12.3, 12.5, -75, -8);        // solid edge lines
  strip(1.9, 9.4, -8.3, -7.95); strip(-9.4, -1.9, -8.3, -7.95);    // stop bars in front of each bay

  return {
    keepClear: [[b.x - 50, b.x + 50, b.z - 75, b.z + 10]],
    update(dt) {
      if (Math.abs(st.target - st.open) < .001) return;
      st.open += (st.target - st.open) * (1 - Math.exp(-dt * 2.2));
      if (Math.abs(st.target - st.open) < .002) st.open = st.target;
      pose();
    },
    setOpen(v) { st.target = v ? 1 : 0; },
    isOpen() { return st.target === 1; },
  };
}
