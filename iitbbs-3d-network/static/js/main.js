import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { buildAuditorium } from './buildings/auditorium.js';
import { buildLectureHall, buildAmphitheatre } from './buildings/lecturehall.js';
import { buildGate } from './buildings/gate.js';
import { createLife } from './life.js';
import { MOODS, MOOD_ORDER, STATUS_EMOJI, moodOf, createStatusMarkers } from './status.js';

const $ = s => document.querySelector(s);
const COL = { ok: 0x4ed08a, warn: 0xf2b84b, down: 0xee5d5d, unk: 0x8a96a3 };
const LABEL = { noc: 'NOC', gate: 'Main Gate', admin: 'Main Building', aud: 'Auditorium', lib: 'Library',
  acad: 'Academic Complex', sbs: 'Basic Sciences', seocs: 'Earth, Ocean & Climate', soi: 'Infrastructure',
  sms: 'Mechanical Sciences', sports: 'Sports Complex', lalitgiri: 'Lalitgiri Hall', ratnagiri: 'Ratnagiri Hall', pushpagiri: 'Pushpagiri Hall' };
const rand = (a => () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a);
  t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; })(7);

/* ---------- renderer / scene ---------- */
const canvas = $('#c');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const SKY = 0xa9cfe6;
const scene = new THREE.Scene();
scene.background = new THREE.Color(SKY);
scene.fog = new THREE.Fog(SKY, 350, 950);
const camera = new THREE.PerspectiveCamera(58, 1, 0.5, 2500);
const HOME_POS = new THREE.Vector3(330, 250, 330), HOME_TGT = new THREE.Vector3(20, 0, 10);
camera.position.copy(HOME_POS);

const controls = new OrbitControls(camera, canvas);
controls.target.copy(HOME_TGT);
controls.enableDamping = true;
controls.maxPolarAngle = Math.PI / 2 - 0.03;
controls.minDistance = 20; controls.maxDistance = 750;

scene.add(new THREE.HemisphereLight(0xffffff, 0x6b8a5a, 1.0));
const sun = new THREE.DirectionalLight(0xfff3dc, 1.6);
sun.position.set(170, 260, 120);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -300, right: 300, top: 300, bottom: -300, near: 10, far: 700 });
sun.shadow.bias = -0.0005;
scene.add(sun);

const mat = (c, o = {}) => new THREE.MeshStandardMaterial({ color: c, flatShading: true, roughness: .88, metalness: 0, ...o });
const flat = (c, off = -2) => mat(c, { polygonOffset: true, polygonOffsetFactor: off, polygonOffsetUnits: off });

/* ---------- ground, hills, clouds ---------- */
{
  const g = new THREE.PlaneGeometry(1800, 1800, 90, 90); g.rotateX(-Math.PI / 2);
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const d = Math.hypot(p.getX(i) - 20, p.getZ(i) - 20);
    const k = Math.min(Math.max((d - 330) / 200, 0), 1);
    p.setY(i, (rand() - .3) * 9 * k);
  }
  g.computeVertexNormals();
  const ground = new THREE.Mesh(g, mat(0x77a068)); ground.receiveShadow = true; scene.add(ground);
  const hash = (x, y, z) => { const v = Math.sin(x * 12.9898 + y * 78.233 + z * 37.719) * 43758.5453; return v - Math.floor(v); };
  for (let i = 0; i < 22; i++) {            // sharp low-poly mountains
    const a = (i / 22) * Math.PI * 2 + rand() * .2, r = 520 + rand() * 220, rad = 90 + rand() * 90, hh = 70 + rand() * 120;
    const mg = new THREE.ConeGeometry(rad, hh, 5 + Math.floor(rand() * 3), 2), q = mg.attributes.position;
    for (let k = 0; k < q.count; k++) { const x = q.getX(k), y = q.getY(k), z = q.getZ(k);
      if (y < hh / 2 - 1) q.setXYZ(k, x + (hash(x, y, z) - .5) * rad * .35, y + (hash(z, x, y) - .5) * hh * .25, z + (hash(y, z, x) - .5) * rad * .35); }
    mg.computeVertexNormals();
    const mm = new THREE.Mesh(mg, mat(new THREE.Color().setHSL(.25 + rand() * .05, .28, .26 + rand() * .14)));
    mm.position.set(20 + Math.cos(a) * r, hh / 2 - 8, 20 + Math.sin(a) * r); mm.rotation.y = rand() * 6; scene.add(mm);
  }
}
const clouds = [];
for (let i = 0; i < 9; i++) {
  const c = new THREE.Group();
  for (let j = 0; j < 4; j++) {
    const m = new THREE.Mesh(new THREE.IcosahedronGeometry(14 + rand() * 10, 0), mat(0xffffff, { roughness: 1 }));
    m.position.set(j * 18 - 27, rand() * 6, rand() * 10); m.scale.y = .6; c.add(m);
  }
  c.position.set(-500 + rand() * 1000, 150 + rand() * 60, -500 + rand() * 1000); scene.add(c); clouds.push(c);
}

/* ---------- data ---------- */
const buildings = await (await fetch('/api/buildings')).json();
const byId = Object.fromEntries(buildings.map(b => [b.id, b]));
buildings.forEach(b => { b.top = b.shape === 'dome' ? 23 : b.shape === 'library' ? b.h + 6 : b.shape === 'mainbuilding' ? 34 : b.shape === 'lecturehall' ? 22 : b.shape === 'courtyard' ? b.h + 4 : b.shape === 'school' ? b.h + 4 : b.id === 'noc' ? b.h + 12 : b.id === 'gate' ? 14.5 : b.id === 'sports' ? 3 : b.h + 1; });

/* ---------- roads, pond ---------- */
const roadRects = [];
function road(x1, z1, x2, z2, w) {
  const len = Math.hypot(x2 - x1, z2 - z1);
  const m = new THREE.Mesh(new THREE.BoxGeometry(len, .1, w), flat(0x4a5560));
  m.position.set((x1 + x2) / 2, .06, (z1 + z2) / 2); m.rotation.y = -Math.atan2(z2 - z1, x2 - x1);
  m.receiveShadow = true; scene.add(m);
  roadRects.push({ x0: Math.min(x1, x2) - w / 2, x1: Math.max(x1, x2) + w / 2, z0: Math.min(z1, z2) - w / 2, z1: Math.max(z1, z2) + w / 2 });
}
road(0, -250, 0, -166, 26);                       // wide apron in front of the gate
{ const tp = new THREE.Shape([new THREE.Vector2(-13, 166), new THREE.Vector2(13, 166), new THREE.Vector2(4.5, 136), new THREE.Vector2(-4.5, 136)]);
  const tg = new THREE.ShapeGeometry(tp); tg.rotateX(-Math.PI / 2);   // taper from 26 m to 9 m
  const tm = new THREE.Mesh(tg, flat(0x4a5560, -3)); tm.position.y = .116; tm.receiveShadow = true; scene.add(tm);
  roadRects.push({ x0: -13, x1: 13, z0: -166, z1: -136 }); }
road(0, -137, 0, -120, 9); road(-50, -120, 190, -120, 8); road(-18, -120, -18, 45, 8);
road(-60, 45, 120, 45, 8); road(-60, 45, -60, 235, 6); road(75, -120, 75, -62, 6);
road(-18, 18, -50, 18, 5);   // path from the main road to the amphitheatre stage
const ring = new THREE.Mesh(new THREE.RingGeometry(59.5, 64.5, 48), flat(0x4a5560, -3)); ring.rotation.x = -Math.PI / 2; ring.position.set(75, .12, 0); scene.add(ring);
const pond = new THREE.Mesh(new THREE.CircleGeometry(7, 12), flat(0x5aa3c8, -3)); pond.rotation.x = -Math.PI / 2; pond.position.set(-40, .14, -95); scene.add(pond);

/* ---------- buildings ---------- */
const pickables = [], colliders = [], groups = {}, waves = [], labels = [];
const markers = createStatusMarkers(scene);
const winMat = mat(0x2b4a66, { roughness: .35, emissive: 0x0d2236 });
function part(g, geo, m, x, y, z, cast = true) {
  const me = new THREE.Mesh(geo, m); me.position.set(x, y, z); me.castShadow = cast; me.receiveShadow = true;
  me.userData.id = g.userData.id; g.add(me); pickables.push(me); return me;
}
function makeLabel(text) {
  const c = document.createElement('canvas'), x = c.getContext('2d'), f = '600 34px "Segoe UI",Arial,sans-serif';
  x.font = f; const w = Math.ceil(x.measureText(text).width) + 36; c.width = w; c.height = 56;
  x.font = f; x.fillStyle = 'rgba(12,24,40,.88)'; x.beginPath(); x.roundRect(0, 0, w, 56, 12); x.fill();
  x.fillStyle = '#fff'; x.textBaseline = 'middle'; x.fillText(text, 18, 29);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), sizeAttenuation: false, depthTest: false, transparent: true, fog: false }));
  s.scale.set(w / 56 * .034, .034, 1); s.renderOrder = 10; return s;
}
function block(g, w, h, d, x, y, z, col, bands = true) {
  part(g, new THREE.BoxGeometry(w, h, d), mat(col), x, y + h / 2, z);
  part(g, new THREE.BoxGeometry(w + 1, .7, d + 1), mat(new THREE.Color(col).multiplyScalar(.7)), x, y + h + .35, z);
  if (bands) for (let i = 0; i < Math.max(1, Math.floor(h / 3.4)); i++) part(g, new THREE.BoxGeometry(w + .2, 1.2, d + .2), winMat, x, y + 2.3 + i * 3.4, z, false);
}
const solarMat = mat(0x1f3350, { roughness: .3 });
let gateRes = null;
for (const b of buildings) {
  const g = new THREE.Group(); g.position.set(b.x, 0, b.z); g.userData.id = b.id; scene.add(g); groups[b.id] = g;
  const col = new THREE.Color(b.color || '#ddd');
  if (b.shape === 'field') {
    part(g, new THREE.BoxGeometry(b.w, .4, b.d), mat(0x7aa56a), 0, .2, 0, false);
    const tr = new THREE.Mesh(new THREE.RingGeometry(.72, .95, 40), flat(0xb5694a, -4)); tr.scale.set(b.w / 2, b.d / 2, 1); tr.rotation.x = -Math.PI / 2; tr.position.y = .45; g.add(tr);
    const inf = new THREE.Mesh(new THREE.CircleGeometry(.7, 32), flat(0x8dbb7b, -4)); inf.scale.set(b.w / 2, b.d / 2, 1); inf.rotation.x = -Math.PI / 2; inf.position.y = .46; g.add(inf);
  } else if (b.shape === 'gate') {           // detailed model lives in js/buildings/gate.js
    gateRes = buildGate({ g, b, pickables, colliders });
    gateRes.keepClear.forEach(([x0, x1, z0, z1]) => roadRects.push({ x0, x1, z0, z1 }));
  } else if (b.shape === 'courtyard') {      // boys hostel: U-shaped courtyard block, stair towers, solar roof
    const W = b.w, D = b.d, H = b.h, t = 11, cream = 0xeeeae0, wx = W / 2 - t / 2;
    block(g, W, H, t, 0, 0, D / 2 - t / 2, cream);
    block(g, t, H, D - t, -wx, 0, -t / 2, cream);
    block(g, t, H, D - t, wx, 0, -t / 2, cream);
    colliders.push({ x: b.x, z: b.z + D / 2 - t / 2, hw: W / 2, hd: t / 2 }, { x: b.x - wx, z: b.z - t / 2, hw: t / 2, hd: (D - t) / 2 }, { x: b.x + wx, z: b.z - t / 2, hw: t / 2, hd: (D - t) / 2 });
    const lawn = new THREE.Mesh(new THREE.BoxGeometry(W - 2 * t - 1, .3, D - t - 1), mat(0x6fa862)); lawn.position.set(0, .15, -t / 2); lawn.receiveShadow = true; g.add(lawn);
    [-1, 1].forEach(sg => {
      part(g, new THREE.BoxGeometry(5, H + 3, 5), mat(0xead7a6), sg * (W / 2 - 2.5), (H + 3) / 2, -D / 2 + 2.5);
      part(g, new THREE.BoxGeometry(.5, H + 3, 3.6), mat(0xb5452f), sg * (W / 2 + .1), (H + 3) / 2, -D / 2 + 2.8);
      part(g, new THREE.ConeGeometry(3.9, 2.8, 4), mat(0xb5452f), sg * (W / 2 - 2.5), H + 4.4, -D / 2 + 2.5, false).rotation.y = Math.PI / 4;
    });
    for (let i = 0; i < 5; i++) part(g, new THREE.BoxGeometry(5, .3, 2.4), solarMat, (i - 2) * 7.5, H + 1, D / 2 - t / 2, false);
    for (let j = 0; j < 2; j++) [-wx, wx].forEach(px => part(g, new THREE.BoxGeometry(2.4, .3, 5), solarMat, px, H + 1, -D / 2 + 12 + j * 8, false));
  } else if (b.shape === 'auditorium') {     // detailed model lives in js/buildings/auditorium.js
    const res = buildAuditorium({ g, b, pickables, colliders });
    res.keepClear.forEach(([x0, x1, z0, z1]) => roadRects.push({ x0, x1, z0, z1 }));   // keep random pines off the forecourt
  } else if (b.shape === 'lecturehall') {    // Lalitgiri / Ratnagiri / Pushpagiri: js/buildings/lecturehall.js
    const res = buildLectureHall({ g, b, pickables, colliders });
    res.keepClear.forEach(([x0, x1, z0, z1]) => roadRects.push({ x0, x1, z0, z1 }));
  } else if (b.shape === 'library') {        // faceted octagonal tower with glass roof and two wings
    const white = 0xf2f0ea, r = Math.min(b.w, b.d) * .3;
    part(g, new THREE.CylinderGeometry(r, r, b.h, 8), mat(white), 0, b.h / 2, 0);
    for (let i = 0; i < 4; i++) part(g, new THREE.CylinderGeometry(r + .15, r + .15, 1.3, 8), winMat, 0, 2.6 + i * 3.6, 0, false);
    part(g, new THREE.ConeGeometry(r + 1.2, 5, 8), mat(0x7fb0cf, { roughness: .25, emissive: 0x16303f }), 0, b.h + 2.5, 0);
    [-1, 1].forEach(sg => block(g, b.w * .34, 9, b.d * .7, sg * b.w * .33, 0, 0, white));
    colliders.push({ x: b.x, z: b.z, hw: b.w / 2, hd: b.d / 2 });
  } else if (b.shape === 'mainbuilding') {   // stepped cream tiers, columned entrance, golden faceted dome
    const W = b.w, D = b.d, cream = 0xf1e8d6, fz = D / 2, zf = D * .3, glass = mat(0x1f3a52, { roughness: .25, emissive: 0x0a1a2a });
    block(g, W, 6, D, 0, 0, 0, cream);
    block(g, W * .8, 5, D * .78, 0, 6.7, 0, cream);
    block(g, W * .56, 5, D * .6, 0, 12.4, 0, cream);
    block(g, W * .34, 4, D * .42, 0, 18.1, 0, cream);
    part(g, new THREE.BoxGeometry(W * .34, 3.4, .5), glass, 0, 14.6, zf + .3, false);
    for (let i = -3; i <= 3; i++) part(g, new THREE.BoxGeometry(.5, 3.6, .7), mat(cream), i * (W * .34 / 7), 14.6, zf + .4, false);
    part(g, new THREE.BoxGeometry(W * .5, 5, .6), glass, 0, 2.8, fz + .2, false);
    part(g, new THREE.BoxGeometry(W * .6, .9, 8), mat(0xe9e0cc), 0, 6.4, fz + 4);
    for (let i = 0; i < 6; i++) part(g, new THREE.CylinderGeometry(.6, .6, 6, 8), mat(0xffffff), -W * .25 + i * (W * .5 / 5), 3, fz + 7);
    part(g, new THREE.CylinderGeometry(7.5, 8, 1.8, 12), mat(0xe6dcc6), 0, 23.7, 0);
    part(g, new THREE.SphereGeometry(6.5, 12, 6, 0, Math.PI * 2, 0, Math.PI / 2), mat(0xd4b25a, { metalness: .4, roughness: .4 }), 0, 24.6, 0);
    part(g, new THREE.ConeGeometry(.5, 2.5, 4), mat(0xd4b25a), 0, 32.3, 0, false);
    part(g, new THREE.CylinderGeometry(.12, .12, 6, 5), mat(0xcccccc), -9, 25.8, -4, false);
    [[0xff9933, 6.6], [0xffffff, 6.1], [0x138808, 5.6]].forEach(([c, y]) => part(g, new THREE.BoxGeometry(1.8, .5, .1), new THREE.MeshBasicMaterial({ color: c }), -8, 22.8 + y - 3.4 + 3, -4, false));
    const pav = new THREE.Mesh(new THREE.BoxGeometry(W * .9, .1, 16), flat(0xd69a5c, -3)); pav.position.set(0, .08, fz + 12); pav.receiveShadow = true; g.add(pav);
    const fb = new THREE.Mesh(new THREE.CylinderGeometry(5, 5, .7, 12), mat(0x9aa1a8)); fb.position.set(0, .45, fz + 13); g.add(fb);
    const fw = new THREE.Mesh(new THREE.CylinderGeometry(4, 4, .75, 12), mat(0x5aa3c8)); fw.position.set(0, .5, fz + 13); g.add(fw);
    const rg = new THREE.Mesh(new THREE.TorusGeometry(2.4, .35, 5, 8), mat(0xb8c2cc, { metalness: .5 })); rg.position.set(0, 3, fz + 13); rg.rotation.y = .6; g.add(rg);
    colliders.push({ x: b.x, z: b.z + 4, hw: W / 2, hd: D / 2 + 4 });
  } else if (b.shape === 'school') {         // cream wings with a tall red entrance block
    block(g, b.w, b.h, b.d, 0, 0, 0, 0xf1dcc8);
    part(g, new THREE.BoxGeometry(b.w * .3, b.h + 3, b.d + 2), mat(0xc0392f), 0, (b.h + 3) / 2, 1);
    part(g, new THREE.BoxGeometry(b.w * .26, 5, .5), mat(0x2b4a66, { roughness: .3, emissive: 0x0d2236 }), 0, 3.5, b.d / 2 + 2.1);
    part(g, new THREE.BoxGeometry(b.w * .26, 2.2, .5), winMat, 0, b.h - 2, b.d / 2 + 2.1);
    colliders.push({ x: b.x, z: b.z + 1, hw: b.w / 2, hd: b.d / 2 + 2 });
  } else {
    const bodyH = b.shape === 'dome' ? 12 : b.h;
    part(g, new THREE.BoxGeometry(b.w, bodyH, b.d), mat(col), 0, bodyH / 2, 0);
    part(g, new THREE.BoxGeometry(b.w + 1.2, .8, b.d + 1.2), mat(col.clone().multiplyScalar(.68)), 0, bodyH + .4, 0);
    for (let i = 0; i < Math.max(1, Math.floor(bodyH / 4)); i++) part(g, new THREE.BoxGeometry(b.w + .2, 1.3, b.d + .2), winMat, 0, 2.6 + i * 4, 0, false);
    if (b.shape === 'dome') [[0, 10], [-27, 7], [27, 7]].forEach(([dx, r]) => part(g, new THREE.SphereGeometry(r, 10, 6, 0, Math.PI * 2, 0, Math.PI / 2), mat(0xf4efe4), dx, bodyH + .8, 0));
    if (b.id === 'noc') { part(g, new THREE.CylinderGeometry(.35, .5, 12, 5), mat(0x9aa7b3), 0, b.h + 6.8, 0); part(g, new THREE.SphereGeometry(1, 6, 4), mat(0xffffff, { emissive: 0x6fa8c7 }), 0, b.h + 12.6, 0); }
    colliders.push({ x: b.x, z: b.z, hw: b.w / 2, hd: b.d / 2 });
  }
  // status emoji (map-pin style, billboarded) + wifi rings for hostels
  const by = b.top + 3.2;
  const fc = markers.add(b.id, b.x, b.z, by, b.type !== 'hostel'); pickables.push(fc);
  if (b.type === 'hostel') for (let i = 0; i < 3; i++) { // wifi waves
    const w = new THREE.Mesh(new THREE.TorusGeometry(5, .22, 5, 28), new THREE.MeshBasicMaterial({ color: COL.unk, transparent: true }));
    w.rotation.x = Math.PI / 2; w.position.y = by; g.add(w); waves.push({ mesh: w, id: b.id, off: i / 3 });
  }
  const short = b.type === 'hostel' ? 'Boys Hostel ' + b.id.slice(1) : LABEL[b.id] || b.name;
  const lab = makeLabel(short); lab.position.set(b.x, by + 14, b.z); lab.userData.id = b.id; scene.add(lab); labels.push(lab);
}
{ // amphitheatre shared by the three lecture halls
  const am = buildAmphitheatre({ scene, cx: -92, cz: 18, R: 27 });
  am.keepClear.forEach(([x0, x1, z0, z1]) => roadRects.push({ x0, x1, z0, z1 }));
}
const sel = new THREE.Mesh(new THREE.RingGeometry(1, 1.06, 56), new THREE.MeshBasicMaterial({ color: 0x7cc4e8, side: THREE.DoubleSide, transparent: true, opacity: .95 }));
sel.rotation.x = -Math.PI / 2; sel.position.y = .3; sel.visible = false; scene.add(sel);

/* ---------- pine trees and palms ---------- */
{
  const inB = (x, z, m) => buildings.some(b => Math.abs(x - b.x) < b.w / 2 + m && Math.abs(z - b.z) < b.d / 2 + m);
  const blocked = (x, z) => inB(x, z, 7)
    || roadRects.some(r => x > r.x0 - 4 && x < r.x1 + 4 && z > r.z0 - 4 && z < r.z1 + 4)
    || Math.abs(Math.hypot(x - 75, z) - 62) < 8 || Math.hypot(x + 40, z + 95) < 12 || Math.hypot(x - 75, z) < 58;
  const pts = [];
  for (let i = 0; i < 4000 && pts.length < 170; i++) {
    const x = -210 + rand() * 440, z = -180 + rand() * 430;
    if (!blocked(x, z)) pts.push([x, z, .8 + rand() * .7]);
  }
  const trunk = new THREE.InstancedMesh(new THREE.CylinderGeometry(.45, .6, 2.6, 5), mat(0x7a5236), pts.length);
  const f1 = new THREE.InstancedMesh(new THREE.ConeGeometry(3, 5, 6), mat(0xffffff), pts.length);
  const f2 = new THREE.InstancedMesh(new THREE.ConeGeometry(2.1, 4.4, 6), mat(0xffffff), pts.length);
  [trunk, f1, f2].forEach(m => m.castShadow = true);
  const d = new THREE.Object3D(), greens = [0x3e7d4a, 0x4f9150, 0x2f6b43];
  pts.forEach(([x, z, s], i) => {
    d.rotation.set(0, rand() * 6.28, 0); d.scale.setScalar(s);
    d.position.set(x, 1.3 * s, z); d.updateMatrix(); trunk.setMatrixAt(i, d.matrix);
    d.position.y = 4.6 * s; d.updateMatrix(); f1.setMatrixAt(i, d.matrix);
    d.position.y = 7.2 * s; d.updateMatrix(); f2.setMatrixAt(i, d.matrix);
    const c = new THREE.Color(greens[i % 3]); f1.setColorAt(i, c); f2.setColorAt(i, c.clone().offsetHSL(0, 0, .05));
  });
  scene.add(trunk, f1, f2);

  const palms = [];
  const line = (x1, z1, x2, z2, gap, off) => {
    const len = Math.hypot(x2 - x1, z2 - z1), nx = -(z2 - z1) / len, nz = (x2 - x1) / len;
    for (let t = 0; t <= len; t += gap) { const x = x1 + (x2 - x1) * t / len, z = z1 + (z2 - z1) * t / len;
      palms.push([x + nx * off, z + nz * off]); if (off) palms.push([x - nx * off, z - nz * off]); }
  };
  line(0, -145, 0, -125, 14, 10); line(-18, -118, -18, 40, 16, 8); line(-60, 50, -60, 230, 16, 6);
  line(-55, -120, 190, -120, 18, 8); line(46, -112, 46, -60, 9, 0); line(-60, 45, 120, 45, 16, 8);
  const P = palms.filter(([x, z]) => !inB(x, z, 2));
  const pt = new THREE.InstancedMesh(new THREE.CylinderGeometry(.3, .5, 7, 5), mat(0x8a6a4a), P.length);
  const fg = new THREE.ConeGeometry(.8, 5, 3); fg.translate(0, 2.5, 0);
  const fr = new THREE.InstancedMesh(fg, mat(0x4c9a4a), P.length * 7);
  pt.castShadow = fr.castShadow = true;
  P.forEach(([x, z], i) => {
    const s = .85 + rand() * .4;
    d.rotation.set(0, 0, 0); d.scale.setScalar(s); d.position.set(x, 3.5 * s, z); d.updateMatrix(); pt.setMatrixAt(i, d.matrix);
    for (let k = 0; k < 7; k++) {
      d.rotation.set(1.05 + rand() * .3, k * .9 + rand() * .3, 0, 'YXZ'); d.scale.set(1.3 * s, s, .28 * s);
      d.position.set(x, 7 * s, z); d.updateMatrix(); fr.setMatrixAt(i * 7 + k, d.matrix);
    }
  });
  scene.add(pt, fr);
}

/* ---------- network links and packets ---------- */
const links = {}, noc = byId.noc, nocTop = new THREE.Vector3(noc.x, noc.top + 3.2, noc.z);
for (const b of buildings) {
  if (b.id === 'noc') continue;
  const to = new THREE.Vector3(b.x, b.top + 3.2, b.z), mid = nocTop.clone().lerp(to, .5);
  mid.y += nocTop.distanceTo(to) * .22 + 8;
  const curve = new THREE.QuadraticBezierCurve3(nocTop, mid, to);
  const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 48, b.type === 'hostel' ? .28 : .2, 4), new THREE.MeshBasicMaterial({ color: COL.unk, transparent: true, opacity: .8 }));
  scene.add(tube);
  const packets = [];
  for (let i = 0; i < 4; i++) {
    const p = new THREE.Mesh(new THREE.SphereGeometry(.95, 6, 4), new THREE.MeshBasicMaterial({ color: 0xffffff }));
    scene.add(p); packets.push({ mesh: p, t: i / 4, dir: i % 2 ? -1 : 1 });
  }
  links[b.id] = { curve, tube, packets };
}

/* ---------- campus life: walking people, cyclists, guards at the gate ---------- */
const life = createLife({ scene, rand });
life.populate({
  routes: [
    [[0, -250], [0, -120], [-18, -120], [-18, 45]],      // gate road and main avenue
    [[-50, -120], [190, -120]],
    [[-18, 45], [-60, 45], [-60, 235]],
    [[-60, 45], [120, 45]],
    [[75, -120], [75, -62]],
    [[-18, 18], [-50, 18]],
  ],
  walkers: 30, cyclists: 11,
});
{ const GZ = byId.gate.z, guard = { shirt: 0x3b6fb0, pants: 0x1f2937, cap: 0x1c2b4a, bag: false, female: false };
  life.addIdle(-8.9, GZ - 2.2, -Math.PI / 2, guard); life.addIdle(8.9, GZ - 2.2, -Math.PI / 2, guard);   // guards at the two bays
  life.addIdle(-14.3, GZ + 5.7, 0, guard); life.addIdle(14.3, GZ + 5.7, Math.PI, guard);                  // at the cabins
  life.addIdle(-6.4, GZ - 14, Math.PI / 2, { female: false, shirt: 0xc0392f });                           // visitor in a red shirt
  life.addIdle(-7.4, GZ - 14.6, Math.PI / 2 + .4); life.addIdle(-5.5, GZ - 14.8, Math.PI / 2 - .4, { female: true });
  life.addIdle(7.8, GZ - 24, -Math.PI / 2 - .3); life.addIdle(8.9, GZ - 23.4, -Math.PI / 2 + .3, { female: true });
  life.addIdle(-16.5, GZ - 10, Math.PI / 2, { female: true }); life.addIdle(19, GZ - 12, Math.PI * .75); }

/* ---------- UI: list, panel ---------- */
let net = {}, selected = null, mode = 'orbit';
const list = $('#list'), rows = {};
function buildList() {
  const mk = (title, arr) => {
    const h = document.createElement('h2'); h.textContent = title; list.appendChild(h);
    arr.forEach(b => {
      const r = document.createElement('button'); r.className = 'row';
      r.innerHTML = '<span class="status-emoji" role="img"></span><span class="nm"></span><small></small>';
      r.querySelector('.nm').textContent = b.name.length > 24 ? (LABEL[b.id] || b.name) : b.name;
      r.onclick = () => { select(b.id); flyTo(b.id); };
      list.appendChild(r); rows[b.id] = r;
    });
    return h;
  };
  window._hostelH = mk('Hostel blocks', buildings.filter(b => b.type === 'hostel'));
  mk('Campus buildings', buildings.filter(b => b.type !== 'hostel'));
}
buildList();

const T = { ok: 'Healthy', warn: 'Degraded', down: 'Down' };
function select(id) {
  selected = id; const b = byId[id];
  sel.visible = true; sel.position.x = b.x; sel.position.z = b.z; sel.scale.setScalar(Math.max(b.w, b.d) / 2 + 5);
  $('#pName').textContent = b.name; $('#pDesc').textContent = b.desc; $('#steps').textContent = '';
  $('#panel').style.display = 'block'; renderPanel();
}
function renderPanel() {
  if (!selected) return; const m = net[selected]; if (!m) return;
  const bd = $('#pBadge'), mood = moodOf(m); bd.className = 'badge ' + m.status;
  bd.textContent = (STATUS_EMOJI[m.status] || STATUS_EMOJI.unk) + ' ' + (T[m.status] || 'Waiting for data') + ' - ' + MOODS[mood].label;
  $('#pFace').textContent = MOODS[mood].emoji; $('#pFace').setAttribute('aria-label', MOODS[mood].label);
  const items = [['Latency', m.latency_ms + ' ms'], ['Packet loss', m.loss_pct + ' %'], ['Download', m.down_mbps + ' Mbps'],
    ['Upload', m.up_mbps + ' Mbps'], ['Clients', m.clients], ['Access points', m.aps_online + ' / ' + m.aps_total]];
  const grid = $('#pGrid'); grid.textContent = '';
  items.forEach(([k, v]) => { const d = document.createElement('div'); d.className = 'stat'; const b = document.createElement('b'); b.textContent = v; const s = document.createElement('span'); s.textContent = k; d.append(b, s); grid.appendChild(d); });
}
$('#pClose').onclick = () => { $('#panel').style.display = 'none'; sel.visible = false; selected = null; };
$('#pRun').onclick = async () => {
  if (!selected) return; const ul = $('#steps'); ul.textContent = ''; const li = document.createElement('li'); li.textContent = 'Running checks...'; ul.appendChild(li);
  try {
    const r = await (await fetch('/api/diagnose/' + selected, { method: 'POST' })).json(); ul.textContent = '';
    r.forEach(s => { const l = document.createElement('li'); const i = document.createElement('span'); i.textContent = s.ok ? 'Pass' : 'Fail'; i.style.color = s.ok ? '#4ed08a' : '#ee5d5d'; i.style.width = '34px';
      const n = document.createElement('span'); n.textContent = s.step; const e = document.createElement('em'); e.textContent = s.detail; l.append(i, n, e); ul.appendChild(l); });
  } catch { li.textContent = 'Could not reach the backend.'; }
};

function applyNet(data) {
  net = data.blocks; $('#src').textContent = 'Data: ' + data.source;
  let healthy = 0, hostels = 0;
  for (const [id, m] of Object.entries(net)) {
    const c = COL[m.status];
    const mood = moodOf(m); markers.set(id, mood);
    const L = links[id]; if (L) { L.tube.material.color.setHex(c); L.packets.forEach(p => p.mesh.material.color.setHex(m.status === 'ok' ? 0xffffff : c)); }
    const r = rows[id]; if (r) {
      const icon = r.querySelector('.status-emoji'); icon.className = 'status-emoji ' + m.status;
      icon.textContent = STATUS_EMOJI[m.status] || STATUS_EMOJI.unk;
      icon.setAttribute('aria-label', T[m.status] || 'Waiting for data');
      r.querySelector('small').textContent = m.latency_ms + ' ms';
    }
    if (byId[id].type === 'hostel') { hostels++; if (m.status === 'ok') healthy++; }
  }
  waves.forEach(w => w.mesh.material.color.setHex(COL[net[w.id]?.status || 'unk']));
  window._hostelH.textContent = `Hostel blocks (${healthy} of ${hostels} healthy)`;
  renderPanel();
}
async function poll() { try { applyNet(await (await fetch('/api/network')).json()); } catch { $('#src').textContent = 'Backend offline'; } }
$('#legend').innerHTML = MOOD_ORDER.map(k => `<span title="${MOODS[k].hint}"><span class="legend-emoji" role="img" aria-label="${MOODS[k].label}">${MOODS[k].emoji}</span>${MOODS[k].label}</span>`).join('') + '<span id="src"></span>';
await poll(); setInterval(poll, 2000);

/* ---------- camera: fly, walk ---------- */
let fly = null;
const ease = t => t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
const walk = { yaw: Math.PI, pitch: 0, keys: new Set(), saved: null };
function flyTo(id) {
  const b = byId[id];
  if (mode === 'walk') { const out = id === 'gate'; camera.position.set(b.x, 1.7, out ? b.z - 30 : b.z + b.d / 2 + 10); walk.yaw = out ? Math.PI : 0; walk.pitch = 0; return; }
  const tgt = new THREE.Vector3(b.x, b.h / 2, b.z), len = Math.max(b.w, b.d) * 1.1 + 55;
  const dirv = id === 'gate' ? new THREE.Vector3(.3, .22, -.9) : new THREE.Vector3(.5, .6, .9);   // gate: view it from the road outside, like the photos
  const to = tgt.clone().add(dirv.normalize().multiplyScalar(id === 'gate' ? 95 : len));
  fly = { t: 0, p0: camera.position.clone(), p1: to, t0: controls.target.clone(), t1: tgt };
}
function setMode(m) {
  if (m === mode) return; mode = m;
  $('#bOrbit').classList.toggle('on', m === 'orbit'); $('#bWalk').classList.toggle('on', m === 'walk');
  if (m === 'walk') {
    walk.saved = { p: camera.position.clone(), t: controls.target.clone() }; controls.enabled = false; fly = null;
    camera.position.set(0, 1.7, -228); walk.yaw = Math.PI; walk.pitch = .02;   // start on the road outside, looking at the gate camera.fov = 70;
  } else {
    controls.enabled = true; camera.fov = 58; camera.position.copy(walk.saved.p); controls.target.copy(walk.saved.t);
  }
  camera.updateProjectionMatrix(); hint();
}
function hint() {
  $('#hint').textContent = mode === 'orbit'
    ? 'Drag to rotate, scroll to zoom, right-drag to pan. Click a building to see its network.'
    : 'W A S D or arrow keys to move, drag to look around, Shift to run, G to open/close the gate, Esc to leave walk mode.';
}
function toggleGate() { if (!gateRes) return; gateRes.setOpen(!gateRes.isOpen()); $('#bGate').textContent = gateRes.isOpen() ? 'Close gate' : 'Open gate'; }
$('#bGate').onclick = toggleGate;
$('#bOrbit').onclick = () => setMode('orbit'); $('#bWalk').onclick = () => setMode('walk');
$('#bReset').onclick = () => { if (mode === 'walk') setMode('orbit'); fly = { t: 0, p0: camera.position.clone(), p1: HOME_POS, t0: controls.target.clone(), t1: HOME_TGT }; };
addEventListener('keydown', e => { if (e.code === 'Escape' && mode === 'walk') setMode('orbit'); if (e.code === 'KeyG') toggleGate(); walk.keys.add(e.code); });
addEventListener('keyup', e => walk.keys.delete(e.code));
addEventListener('blur', () => walk.keys.clear());

/* pointer: look in walk mode, click to select */
const ray = new THREE.Raycaster(), ndc = new THREE.Vector2(); let down = null;
canvas.addEventListener('pointerdown', e => { down = { x: e.clientX, y: e.clientY, t: performance.now() }; canvas.setPointerCapture(e.pointerId); });
canvas.addEventListener('pointermove', e => {
  if (mode === 'walk' && e.buttons) { walk.yaw -= e.movementX * .004; walk.pitch = Math.max(-1.3, Math.min(1.3, walk.pitch - e.movementY * .004)); }
});
canvas.addEventListener('pointerup', e => {
  if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 6) { down = null; return; } down = null;
  ndc.set(e.clientX / innerWidth * 2 - 1, -(e.clientY / innerHeight) * 2 + 1); ray.setFromCamera(ndc, camera);
  const hit = ray.intersectObjects(pickables, false)[0]; if (hit) select(hit.object.userData.id);
});

function stepWalk(dt) {
  const k = walk.keys, f = (k.has('KeyW') || k.has('ArrowUp') ? 1 : 0) - (k.has('KeyS') || k.has('ArrowDown') ? 1 : 0);
  const s = (k.has('KeyD') || k.has('ArrowRight') ? 1 : 0) - (k.has('KeyA') || k.has('ArrowLeft') ? 1 : 0);
  const sp = (k.has('ShiftLeft') || k.has('ShiftRight') ? 22 : 10) * dt, sy = Math.sin(walk.yaw), cy = Math.cos(walk.yaw);
  const p = camera.position;
  p.x += (-sy * f + cy * s) * sp; p.z += (-cy * f - sy * s) * sp;
  p.x = Math.max(-240, Math.min(260, p.x)); p.z = Math.max(-262, Math.min(252, p.z)); p.y = 1.7;
  for (const c of colliders) { // push out of building footprints
    if (c.off) continue;
    const dx = p.x - c.x, dz = p.z - c.z, ox = c.hw + 1.2 - Math.abs(dx), oz = c.hd + 1.2 - Math.abs(dz);
    if (ox > 0 && oz > 0) { if (ox < oz) p.x += Math.sign(dx || 1) * ox; else p.z += Math.sign(dz || 1) * oz; }
  }
  camera.rotation.set(walk.pitch, walk.yaw, 0, 'YXZ');
}

/* ---------- loop ---------- */
function resize() { renderer.setSize(innerWidth, innerHeight, false); camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); }
addEventListener('resize', resize); resize(); hint();
const clock = new THREE.Clock(), tmp = new THREE.Vector3();
function frame() {
  const dt = Math.min(clock.getDelta(), .1), t = clock.elapsedTime;
  if (fly) { fly.t = Math.min(1, fly.t + dt / 1.2); const e = ease(fly.t); camera.position.lerpVectors(fly.p0, fly.p1, e); controls.target.lerpVectors(fly.t0, fly.t1, e); if (fly.t >= 1) fly = null; }
  if (mode === 'walk') stepWalk(dt); else controls.update();
  const mk = markers.update(camera, dt, t);
  labels.forEach(l => { const it = mk[l.userData.id]; if (it) l.position.set(it.x, it.top + 2.2, it.z); });
  gateRes?.update(dt); life.update(dt);
  for (const w of waves) {
    const down = net[w.id]?.status === 'down', f = down ? .3 : (t * .5 + w.off) % 1;
    w.mesh.scale.setScalar(1 + f * 2.6); w.mesh.material.opacity = down ? .5 : (1 - f) * .9;
  }
  for (const [id, L] of Object.entries(links)) {
    const m = net[id], sp = !m || m.status === 'down' ? .02 : .1 + Math.min(m.down_mbps, 1000) / 1000 * .25;
    for (const p of L.packets) { p.t = (p.t + sp * dt) % 1; L.curve.getPoint(p.dir > 0 ? p.t : 1 - p.t, tmp); p.mesh.position.copy(tmp); }
  }
  clouds.forEach(c => { c.position.x += dt * 3; if (c.position.x > 600) c.position.x = -600; });
  if (mode === 'walk') labels.forEach(l => l.visible = l.position.distanceTo(camera.position) < 160); else labels.forEach(l => l.visible = true);
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}
frame();
const ld = $('#load'); ld.style.opacity = 0; setTimeout(() => ld.remove(), 600);
