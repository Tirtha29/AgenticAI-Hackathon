/* ============================================================================
   Campus life: animated people and cyclists on the roads.
   - Walkers swing legs and arms, some in pairs, some with backpacks, long hair or caps.
   - Cyclists keep to the LEFT lane (India), pedal, and their wheels turn with the speed.
   - Idle people (guards, chatting students) can be placed with addIdle().

   Models face +x. Everything is built from a handful of shared geometries and cached
   materials so ~60 agents cost very little.
   ============================================================================ */
import * as THREE from 'three';

const PI = Math.PI;
const SKIN = [0x8d5524, 0xc68642, 0xe0ac69, 0x6b4423, 0xa56b3f, 0xd2a074];
const SHIRT = [0xb5452f, 0x2d5f8b, 0xe8e2d4, 0x3b7d4f, 0x7a4a8c, 0xd6a02a, 0xc0392f, 0x1f8a8a, 0xf08a5d, 0x233d6e, 0xd96c9a, 0x5b6b7a];
const PANTS = [0x2b2f3a, 0x3a3f55, 0x57534e, 0x1f2937, 0x4a5568, 0x6b5b45, 0x2f4a6b];
const HAIR = [0x161412, 0x2a1d14, 0x3a2a1c, 0x0e0d0d];
const BIKE = [0xc0392f, 0x2d5f8b, 0x1f8a5a, 0x222222, 0xd6a02a, 0x7a4a8c];

export function createLife({ scene, rand }) {
  const pick = a => a[Math.floor(rand() * a.length)];
  const cache = new Map();
  const M = c => { if (!cache.has(c)) cache.set(c, new THREE.MeshStandardMaterial({ color: c, roughness: .9, flatShading: true })); return cache.get(c); };

  /* ---------- shared geometry ---------- */
  const G = {
    leg: new THREE.BoxGeometry(.15, .82, .18).translate(0, -.41, 0),
    shoe: new THREE.BoxGeometry(.26, .08, .17).translate(.05, -.8, 0),
    torso: new THREE.BoxGeometry(.26, .58, .4),
    arm: new THREE.BoxGeometry(.09, .56, .11).translate(0, -.28, 0),
    head: new THREE.SphereGeometry(.115, 10, 8),
    hair: new THREE.SphereGeometry(.127, 10, 6, 0, PI * 2, 0, PI * .56),
    longHair: new THREE.BoxGeometry(.09, .36, .2).translate(-.07, -.14, 0),
    bag: new THREE.BoxGeometry(.14, .36, .3),
    cap: new THREE.CylinderGeometry(.125, .13, .07, 10),
    capPeak: new THREE.BoxGeometry(.12, .02, .17).translate(.1, 0, 0),
    wheelRing: new THREE.TorusGeometry(.35, .028, 6, 20),
    spoke: new THREE.BoxGeometry(.02, .68, .012),
    hubG: new THREE.CylinderGeometry(.04, .04, .06, 6).rotateX(PI / 2),
    thigh: new THREE.BoxGeometry(.13, .42, .15).translate(0, -.21, 0),
    shin: new THREE.BoxGeometry(.11, .42, .13).translate(0, -.21, 0),
    shoeB: new THREE.BoxGeometry(.26, .08, .17).translate(.05, -.4, 0),
    rod: new THREE.CylinderGeometry(.018, .018, 1, 5),
    bar: new THREE.CylinderGeometry(.016, .016, .5, 5).rotateX(PI / 2),
    seat: new THREE.BoxGeometry(.2, .04, .1),
    basket: new THREE.BoxGeometry(.2, .14, .26),
  };

  const mesh = (geo, mat, parent, x = 0, y = 0, z = 0, cast = false) => {
    const m = new THREE.Mesh(geo, mat); m.position.set(x, y, z); m.castShadow = cast; parent.add(m); return m;
  };

  /* ---------- a person (feet at y=0, facing +x) ---------- */
  function makePerson(o = {}) {
    const grp = new THREE.Group(), body = new THREE.Group(); grp.add(body);
    const female = o.female ?? rand() < .42, sc = (female ? .93 : 1) * (.94 + rand() * .12);
    const skin = M(o.skin ?? pick(SKIN)), shirt = M(o.shirt ?? pick(SHIRT)), pants = M(o.pants ?? pick(PANTS));
    const legs = [-1, 1].map(s => {
      const l = new THREE.Group(); l.position.set(0, .82, s * .1); body.add(l);
      mesh(G.leg, pants, l); mesh(G.shoe, M(0x1b1b1b), l); return l;
    });
    mesh(G.torso, shirt, body, 0, 1.11, 0, true);
    const arms = [-1, 1].map(s => {
      const a = new THREE.Group(); a.position.set(0, 1.37, s * .25); body.add(a);
      mesh(G.arm, shirt, a); const hand = mesh(new THREE.SphereGeometry(.05, 6, 5), skin, a, 0, -.58, 0); return a;
    });
    mesh(G.head, skin, body, 0, 1.55, 0, true);
    if (o.cap) { mesh(G.cap, M(o.cap), body, 0, 1.64, 0); mesh(G.capPeak, M(o.cap), body, 0, 1.62, 0); }
    else { mesh(G.hair, M(pick(HAIR)), body, -.01, 1.56, 0); if (female) mesh(G.longHair, M(0x161412), body, 0, 1.6, 0); }
    if (o.bag ?? rand() < .5) mesh(G.bag, M(pick([0x1f3b5c, 0x7a2f2f, 0x2f5a3a, 0x3a3a3a, 0xc9822b])), body, -.21, 1.14, 0);
    grp.scale.setScalar(sc);
    return { grp, body, legs, arms, kind: 'walk', sc };
  }

  /* ---------- a cyclist on a bicycle ---------- */
  function makeCyclist() {
    const grp = new THREE.Group(), body = new THREE.Group(); grp.add(body);
    const frameM = M(pick(BIKE)), dark = M(0x1d1d1f), steel = M(0xb8bec4);
    const wheels = [-.56, .56].map(x => {
      const w = new THREE.Group(); w.position.set(x, .36, 0); body.add(w);
      mesh(G.wheelRing, dark, w); mesh(G.hubG, steel, w);
      for (let k = 0; k < 3; k++) { const s = mesh(G.spoke, steel, w); s.rotation.z = k * PI / 3; }
      return w;
    });
    const rod = (ax, ay, bx, by, mat = frameM) => {      // thin tube between two points in the x-y plane
      const m = new THREE.Mesh(G.rod, mat); const dx = bx - ax, dy = by - ay, len = Math.hypot(dx, dy);
      m.scale.y = len; m.position.set((ax + bx) / 2, (ay + by) / 2, 0); m.rotation.z = -Math.atan2(dx, dy); m.castShadow = true; body.add(m);
    };
    rod(-.56, .36, -.1, .4); rod(-.1, .4, -.14, .98); rod(-.1, .4, .42, .8); rod(-.14, .98, .42, .84); rod(-.56, .36, -.14, .98); rod(.42, .84, .56, .36);
    mesh(G.bar, dark, body, .42, .98, 0); rod(.42, .84, .42, .98, dark);
    mesh(G.seat, dark, body, -.15, 1.0, 0);
    if (rand() < .35) mesh(G.basket, M(0x7a5a3a), body, .5, 1.1, 0);

    const skin = M(pick(SKIN)), shirt = M(pick(SHIRT)), pants = M(pick(PANTS)), female = rand() < .4;
    const hip = [-.1, .98];
    const torso = new THREE.Group(); torso.position.set(hip[0], hip[1], 0); torso.rotation.z = -.5; body.add(torso);
    mesh(G.torso, shirt, torso, 0, .3, 0, true);
    mesh(G.head, skin, torso, 0, .74, 0, true);
    mesh(G.hair, M(pick(HAIR)), torso, -.01, .75, 0); if (female) mesh(G.longHair, M(0x161412), torso, 0, .8, 0);
    if (rand() < .5) mesh(G.bag, M(pick([0x1f3b5c, 0x7a2f2f, 0x2f5a3a, 0x3a3a3a])), torso, -.17, .32, 0);
    const legs = [-1, 1].map(s => {
      const l = new THREE.Group(); l.position.set(hip[0], hip[1], s * .12); body.add(l);
      mesh(G.thigh, pants, l); const k = new THREE.Group(); k.position.set(0, -.42, 0); l.add(k); mesh(G.shin, pants, k); mesh(G.shoeB, M(0x1b1b1b), k);
      return { l, k };
    });
    const sh = [hip[0] + .56 * .48, hip[1] + .56 * .88], arms = [-1, 1].map(s => {
      const a = new THREE.Group(); a.position.set(sh[0], sh[1], s * .23); a.rotation.z = Math.atan2(.42 - sh[0], sh[1] - .98); body.add(a);
      mesh(G.arm, shirt, a).scale.y = .95; return a;
    });
    grp.scale.setScalar(.95 + rand() * .12);
    return { grp, body, wheels, legs, arms, kind: 'bike' };
  }

  /* ---------- routes: lists of [x,z] points, agents walk back and forth ---------- */
  const agents = [], idles = [];
  const segLen = R => R.slice(1).map((p, i) => Math.hypot(p[0] - R[i][0], p[1] - R[i][1]));
  const total = R => segLen(R).reduce((a, c) => a + c, 0);

  function place(agent, route, off, speed, startDist, dir) {
    const lens = segLen(route); let d = startDist, seg = 0;
    while (seg < lens.length - 1 && d > lens[seg]) { d -= lens[seg]; seg++; }
    Object.assign(agent, { route, lens, seg, s: Math.min(d, lens[seg]), dir, off, speed, heading: 0, init: false, phase: rand() * 6.28 });
    scene.add(agent.grp); agents.push(agent); return agent;
  }

  /* routeSet: [{ route, weight }]. Returns nothing; fills the world. */
  function populate({ routes, walkers = 30, cyclists = 10 }) {
    const W = routes.map(r => total(r)), sum = W.reduce((a, c) => a + c, 0);
    const choose = () => { let t = rand() * sum, i = 0; while (i < W.length - 1 && t > W[i]) { t -= W[i]; i++; } return i; };
    for (let n = 0; n < walkers; n++) {
      const ri = choose(), R = routes[ri], dir = rand() < .5 ? 1 : -1, d0 = rand() * W[ri], sp = 1.1 + rand() * .5, off = 3.0 + rand() * .5;
      place(makePerson(), R, off, sp, d0, dir);
      if (rand() < .35) place(makePerson(), R, off - .55, sp, d0 + .6, dir);                 // a friend walking beside
    }
    for (let n = 0; n < cyclists; n++) {
      const ri = choose(), R = routes[ri];
      place(makeCyclist(), R, 2.1 + rand() * .5, 3.6 + rand() * 1.8, rand() * W[ri], rand() < .5 ? 1 : -1);
    }
  }

  /* standing people: guards, small groups. heading is the direction they face, in radians on the x-z plane */
  function addIdle(x, z, heading, o = {}) {
    const p = makePerson(o); p.grp.position.set(x, 0, z); p.grp.rotation.y = -heading; scene.add(p.grp);
    p.idle = { phase: rand() * 6.28, speed: .8 + rand() * .6 }; idles.push(p); return p;
  }

  /* ---------- per-frame ---------- */
  const lerpAng = (a, b, k) => { let d = ((b - a + PI) % (PI * 2) + PI * 2) % (PI * 2) - PI; return a + d * k; };
  function update(dt) {
    for (const a of agents) {
      const len = a.lens[a.seg];
      a.s += a.speed * dt * a.dir;
      if (a.s > len) { if (a.seg < a.lens.length - 1) { a.seg++; a.s = 0; } else { a.s = len; a.dir = -1; } }
      else if (a.s < 0) { if (a.seg > 0) { a.seg--; a.s = a.lens[a.seg]; } else { a.s = 0; a.dir = 1; } }
      const q0 = a.route[a.seg], q1 = a.route[a.seg + 1], L = a.lens[a.seg];
      const ux = (q1[0] - q0[0]) / L * a.dir, uz = (q1[1] - q0[1]) / L * a.dir;
      const k = a.s / L, tx = q0[0] + (q1[0] - q0[0]) * k + uz * a.off, tz = q0[1] + (q1[1] - q0[1]) * k - ux * a.off;   // keep left
      const h = Math.atan2(uz, ux);
      if (!a.init) { a.grp.position.set(tx, 0, tz); a.heading = h; a.init = true; }
      const sm = 1 - Math.exp(-dt * 7);
      a.grp.position.x += (tx - a.grp.position.x) * sm; a.grp.position.z += (tz - a.grp.position.z) * sm;
      a.heading = lerpAng(a.heading, h, 1 - Math.exp(-dt * 6)); a.grp.rotation.y = -a.heading;
      if (a.kind === 'walk') {
        a.phase += a.speed * dt * 4.6; const s = Math.sin(a.phase);
        a.legs[0].rotation.z = s * .6; a.legs[1].rotation.z = -s * .6; a.arms[0].rotation.z = -s * .5; a.arms[1].rotation.z = s * .5;
        a.body.position.y = Math.abs(s) * .03;
      } else {
        a.phase += a.speed * dt * 2.3; const s = Math.sin(a.phase), c = Math.sin(a.phase + PI);
        a.wheels.forEach(w => { w.rotation.z -= a.speed * dt / .36; });
        a.legs[0].l.rotation.z = .5 + s * .5; a.legs[0].k.rotation.z = -.55 - Math.max(0, -s) * .5;
        a.legs[1].l.rotation.z = .5 + c * .5; a.legs[1].k.rotation.z = -.55 - Math.max(0, -c) * .5;
      }
    }
    for (const p of idles) {
      p.idle.phase += dt * p.idle.speed; const s = Math.sin(p.idle.phase);
      p.body.position.y = Math.abs(s) * .006; p.body.rotation.x = s * .015; p.arms[0].rotation.z = s * .05; p.arms[1].rotation.z = -s * .05;
    }
  }
  return { populate, addIdle, update, count: () => agents.length + idles.length };
}
