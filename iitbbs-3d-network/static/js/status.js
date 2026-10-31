/* ============================================================================
   Status emoji:
     red    -> angry (critical outage)   and  sad (down)
     yellow -> neutral (degraded)
     green  -> smile (good)              and  grin (excellent)
   Each face is drawn on a canvas, so no image files are needed and it stays sharp.
   ============================================================================ */
import * as THREE from 'three';

export const MOODS = {
  angry:   { label: 'Critical outage', emoji: '😠', hint: 'No access points or heavy packet loss' },
  sad:     { label: 'Down',            emoji: '😟', hint: 'Link failing or very slow' },
  neutral: { label: 'Degraded',        emoji: '😐', hint: 'Slow, lossy or some APs offline' },
  smile:   { label: 'Good',            emoji: '🙂', hint: 'Healthy, normal latency' },
  grin:    { label: 'Excellent',       emoji: '😊', hint: 'Fast, no loss, all APs online' },
  unk:     { label: 'Waiting for data', emoji: '⏳', hint: '' },
};
export const MOOD_ORDER = ['grin', 'smile', 'neutral', 'sad', 'angry'];
export const STATUS_EMOJI = { ok: '😊', warn: '😐', down: '😠', unk: '⏳' };

/* Decide the face from the metrics the backend sends (status, latency_ms, loss_pct, aps_*). */
export function moodOf(m) {
  if (!m) return 'unk';
  if (m.status === 'down') return (m.aps_online === 0 || m.loss_pct > 12 || m.latency_ms > 220) ? 'angry' : 'sad';
  if (m.status === 'warn') return 'neutral';
  return (m.latency_ms < 20 && m.loss_pct < .5 && m.aps_online >= m.aps_total) ? 'grin' : 'smile';
}

const INK = '#13202e';

function drawFace(x, cx, cy, r, mood) {
  x.save();
  x.font = `${r * 1.9}px "Segoe UI Emoji", "Apple Color Emoji", sans-serif`;
  x.textAlign = 'center'; x.textBaseline = 'middle';
  x.fillText(MOODS[mood].emoji, cx, cy);
  x.restore();
}

/* round face only, for the legend, building list and panel */
const urlCache = {};
export function faceURL(mood, size = 96) {
  const k = mood + size; if (urlCache[k]) return urlCache[k];
  const c = document.createElement('canvas'); c.width = c.height = size;
  drawFace(c.getContext('2d'), size / 2, size / 2, size * .42, mood);
  return (urlCache[k] = c.toDataURL('image/png'));
}

/* map-pin style texture for the 3D sprite: the tail tip sits on the bottom edge of the texture */
function pinTexture(mood) {
  const W = 256, H = 320, c = document.createElement('canvas'); c.width = W; c.height = H;
  const x = c.getContext('2d');
  x.fillStyle = '#fff'; x.beginPath(); x.moveTo(W / 2 - 52, 200); x.lineTo(W / 2, H - 2); x.lineTo(W / 2 + 52, 200); x.closePath(); x.fill();
  x.fillStyle = '#fff'; x.strokeStyle = INK; x.lineWidth = 8; x.lineJoin = 'round';
  x.beginPath(); x.moveTo(W / 2 - 38, 206); x.lineTo(W / 2, H - 14); x.lineTo(W / 2 + 38, 206); x.closePath(); x.fill(); x.stroke();
  drawFace(x, W / 2, 124, 104, mood);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; t.generateMipmaps = true; t.minFilter = THREE.LinearMipmapLinearFilter; return t;
}
function haloTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 128; const x = c.getContext('2d');
  const g = x.createRadialGradient(64, 64, 4, 64, 64, 64); g.addColorStop(0, 'rgba(255,255,255,.9)'); g.addColorStop(.45, 'rgba(255,255,255,.35)'); g.addColorStop(1, 'rgba(255,255,255,0)');
  x.fillStyle = g; x.fillRect(0, 0, 128, 128); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

/* ---------- 3D markers ---------- */
export function createStatusMarkers(scene) {
  const faceMat = {}; for (const k of Object.keys(MOODS)) faceMat[k] = new THREE.SpriteMaterial({ map: pinTexture(k), transparent: true, fog: false, depthWrite: false });
  const haloTex = haloTexture(), items = {};
  const ASPECT = 256 / 320, DISC = 124 / 320;                 // sprite aspect, disc centre as a fraction of height (from the top)

  function add(id, x, z, anchorY, big = false) {
    const face = new THREE.Sprite(faceMat.unk); face.center.set(.5, 0); face.renderOrder = 12; face.userData.id = id;
    const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: haloTex, color: 0xffffff, transparent: true, opacity: .5, depthWrite: false, blending: THREE.AdditiveBlending, fog: false }));
    halo.renderOrder = 11; face.position.set(x, anchorY, z); halo.position.copy(face.position);
    scene.add(face, halo);
    items[id] = { face, halo, x, z, anchorY, mood: 'unk', pop: 0, phase: Math.random() * 6.28, big, scale: 6 };
    return face;
  }
  function set(id, mood) {
    const it = items[id]; if (!it || it.mood === mood) return;
    it.mood = mood; it.face.material = faceMat[mood]; it.pop = 1;
  }
  /* call every frame; returns the world-space top of each marker so labels can sit above it */
  function update(camera, dt, t) {
    for (const [id, it] of Object.entries(items)) {
      const d = camera.position.distanceTo(it.face.position);
      const target = Math.min(Math.max(d * .03, 4.2), 12) * (it.big ? 1.15 : 1);
      it.scale += (target - it.scale) * Math.min(1, dt * 8);
      it.pop = Math.max(0, it.pop - dt * 2.2);
      const bounce = 1 + Math.sin(it.pop * Math.PI) * .45 * it.pop;
      const s = it.scale * bounce, bad = it.mood === 'sad' || it.mood === 'angry';
      const bob = Math.sin(t * (bad ? 5 : 2) + it.phase) * (bad ? .5 : .35);
      const jitter = it.mood === 'angry' ? Math.sin(t * 38 + it.phase) * s * .025 : 0;
      it.face.scale.set(s * ASPECT, s, 1);
      it.face.position.set(it.x + jitter, it.anchorY + bob, it.z);
      const cy = it.anchorY + bob + s * (1 - DISC);
      it.halo.position.set(it.x, cy, it.z);
      const pulse = bad ? .75 + .25 * Math.sin(t * 6 + it.phase) : .5;
      it.halo.scale.setScalar(s * (bad ? 2.1 + .25 * Math.sin(t * 6 + it.phase) : 1.8));
      it.halo.material.opacity = pulse * (it.mood === 'unk' ? .2 : .55);
      it.top = it.anchorY + s + bob;
    }
    return items;
  }
  return { add, set, update, items };
}
