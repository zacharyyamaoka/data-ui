// scene3d's meshed robot (docs/peps/0005-dashboard-cards.md §2b scene3d.robot): slerp and the pose at t (src/math.js),
// and the GLB cache and clones (src/robot.js) on the case's real model. three's own Quaternion.slerpQuaternions is the
// oracle for our slerp; fetch is counted, so "once per URL" is measured, not assumed.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { Quaternion, MeshBasicMaterial } from 'three';
import { sampler, slerp, poseAt, linkColumns } from '../../packages/views/scene3d/src/math.js';
import { loadModel, cachedModels, linkNode, linkBoxes, instance } from '../../packages/views/scene3d/src/robot.js';

const GLB = fileURLToPath(new URL('../../gallery/examples/pid-tuning/media/ur5e_links.glb', import.meta.url));
const LINKS = ['base', 'shoulder_link', 'upper_arm_link', 'forearm_link', 'wrist_1_link', 'wrist_2_link', 'wrist_3_link'];

const rng = (() => { let s = 7; return () => ((s = (s * 16807) % 2147483647) / 2147483647); })();
const randomQuat = () => { const q = [rng() - 0.5, rng() - 0.5, rng() - 0.5, rng() - 0.5]; const l = Math.hypot(...q); return q.map((c) => c / l); };
const three = (wxyz) => new Quaternion(wxyz[1], wxyz[2], wxyz[3], wxyz[0]);
const sameRotation = (a, b) => Math.min(Math.max(...a.map((c, i) => Math.abs(c - b[i]))), Math.max(...a.map((c, i) => Math.abs(c + b[i]))));

test('slerp: equals three\'s Quaternion.slerpQuaternions (wxyz in, wxyz out), large angles and both hemispheres', () => {
  for (let k = 0; k < 200; k++) {
    const a = randomQuat(), b = randomQuat(), f = rng();
    const got = slerp(a, b, f);
    const want = new Quaternion().slerpQuaternions(three(a), three(b), f);
    assert.ok(sameRotation(got, [want.w, want.x, want.y, want.z]) < 1e-12, `pair ${k}`);
  }
});

test('slerp: is a slerp, not a normalised lerp (a 120° turn at f = 0.25 differs by > 1e-3)', () => {
  const a = [1, 0, 0, 0], b = [Math.cos(Math.PI / 3), 0, 0, Math.sin(Math.PI / 3)];   // 120° about z
  const got = slerp(a, b, 0.25);
  const nl = a.map((c, i) => c + (b[i] - c) * 0.25), l = Math.hypot(...nl);
  assert.ok(Math.abs(got[3] - Math.sin(Math.PI / 12)) < 1e-12);   // 30° about z: sin(15°)
  assert.ok(Math.abs(got[3] - nl[3] / l) > 1e-3);
});

test('slerp: takes the short way round when the second quaternion is in the other hemisphere', () => {
  const a = [1, 0, 0, 0], b = [-Math.cos(0.1), 0, 0, -Math.sin(0.1)];   // −q of a 0.2 rad turn
  const got = slerp(a, b, 0.5);
  assert.ok(sameRotation(got, [Math.cos(0.05), 0, 0, Math.sin(0.05)]) < 1e-12);
});

test('slerp: normalises its inputs and returns null for a missing or zero quaternion', () => {
  assert.ok(sameRotation(slerp([2, 0, 0, 0], [0, 0, 0, 3], 0.5), [Math.SQRT1_2, 0, 0, Math.SQRT1_2]) < 1e-12);
  assert.equal(slerp([1, 0, 0, null], [1, 0, 0, 0], 0.5), null);
  assert.equal(slerp([0, 0, 0, 0], [1, 0, 0, 0], 0.5), null);
});

test('linkColumns: <link>_x/_y/_z then the wxyz quaternion', () => {
  assert.deepEqual(linkColumns('wrist_3_link'), ['wrist_3_link_x', 'wrist_3_link_y', 'wrist_3_link_z', 'wrist_3_link_qw', 'wrist_3_link_qx', 'wrist_3_link_qy', 'wrist_3_link_qz']);
});

const half = [Math.cos(Math.PI / 8), 0, Math.sin(Math.PI / 8), 0];   // 45° about y
const rows = [
  { t: 0, path: 1, a_x: 0, a_y: 0, a_z: 0, a_qw: 1, a_qx: 0, a_qy: 0, a_qz: 0, b_x: 1, b_y: 1, b_z: 1, b_qw: 1, b_qx: 0, b_qy: 0, b_qz: 0 },
  { t: 1, path: 3, a_x: 2, a_y: 4, a_z: 6, a_qw: half[0], a_qx: 0, a_qy: half[2], a_qz: 0, b_x: 1, b_y: 1, b_z: null, b_qw: 1, b_qx: 0, b_qy: 0, b_qz: 0 },
  { t: 2, path: 5, a_x: 2, a_y: 4, a_z: 6, a_qw: half[0], a_qx: 0, a_qy: half[2], a_qz: 0, b_x: 1, b_y: 1, b_z: 1, b_qw: 1, b_qx: 0, b_qy: 0, b_qz: 0 },
];
const cols = ['path', ...linkColumns('a'), ...linkColumns('b')];

test('sampler.around: the two samples around t and the fraction, as at() picks them (clamped outside the span)', () => {
  const s = sampler(rows, 't', cols);
  const { a, b, f } = s.around(0.25);
  assert.equal(f, 0.25);
  assert.equal(a[0] + (b[0] - a[0]) * f, s.at(0.25)[0]);
  assert.deepEqual(s.around(-1), { a: s.points[0].v, b: s.points[0].v, f: 0 });
  assert.deepEqual(s.around(9), { a: s.points[2].v, b: s.points[2].v, f: 0 });
  assert.equal(sampler([], 't', cols).around(0), null);
});

test('poseAt: origins lerped, orientations slerped, per link from the offset', () => {
  const s = sampler(rows, 't', cols);
  const [pa] = poseAt(s, 0.5, 1, 1);
  assert.deepEqual(pa.p, [1, 2, 3]);
  assert.ok(sameRotation(pa.q, [Math.cos(Math.PI / 16), 0, Math.sin(Math.PI / 16), 0]) < 1e-12);   // half of 45°
  const both = poseAt(s, 2, 1, 2);
  assert.deepEqual(both.map((x) => x.p), [[2, 4, 6], [1, 1, 1]]);
});

test('poseAt: a link missing a value on either neighbour leaves the robot unposed at t (null), never a stale pose', () => {
  const s = sampler(rows, 't', cols);
  assert.equal(poseAt(s, 0.5, 1, 2), null);   // b_z is null at t = 1
  assert.equal(poseAt(s, 1.5, 1, 2), null);
  assert.equal(poseAt(sampler([], 't', cols), 0, 1, 1), null);
});

test('loadModel: the GLB is fetched once per URL however many cards ask; every link is a node, clones share the meshes', async () => {
  let fetches = 0;
  const realFetch = globalThis.fetch;
  // three's FileLoader reports progress with the browser's ProgressEvent, which node lacks
  globalThis.ProgressEvent ??= class extends Event { constructor(type, init = {}) { super(type); Object.assign(this, init); } };
  globalThis.fetch = async () => { fetches++; return new Response(readFileSync(GLB), { status: 200 }); };
  try {
    const url = 'http://example.test/media/ur5e_links.glb';
    const [m1, m2] = await Promise.all([loadModel(url), loadModel(url)]);
    const m3 = await loadModel(url);
    assert.equal(fetches, 1);
    assert.equal(cachedModels(), 1);
    assert.ok(m1 === m2 && m2 === m3);
    assert.equal(m1.triangles, 121783);   // build_robot.py's count: every Menagerie visual triangle
    for (const l of LINKS) assert.ok(linkNode(m1.root, l), l);

    const solid = instance(m1, LINKS);
    const ghostMat = new MeshBasicMaterial();
    const ghost = instance(m1, LINKS, ghostMat);
    assert.equal(solid.nodes.length, 7);
    assert.ok(solid.nodes.every((n) => n) && solid.nodes.every((n, k) => n !== linkNode(m1.root, LINKS[k])));
    const meshes = (root) => { const out = []; root.traverse((o) => { if (o.isMesh) out.push(o); }); return out; };
    const orig = meshes(m1.root), a = meshes(solid.root), g = meshes(ghost.root);
    assert.ok(a.every((o, i) => o.geometry === orig[i].geometry && o.material === orig[i].material));
    assert.ok(g.every((o) => o.material === ghostMat) && orig.every((o) => o.material !== ghostMat));

    // each link's box in its own frame: the upper arm is the 0.425 m link (Menagerie's forearm_link pos z)
    const boxes = linkBoxes(m1, LINKS);
    const len = (l) => Math.max(...[0, 1, 2].map((i) => boxes[l][1][i] - boxes[l][0][i]));
    assert.ok(len('upper_arm_link') > 0.425 && len('upper_arm_link') < 0.6, String(len('upper_arm_link')));
    assert.ok(len('wrist_3_link') < 0.12, String(len('wrist_3_link')));
  } finally {
    globalThis.fetch = realFetch;
  }
});
