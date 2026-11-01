/* scene3d's meshed robot (docs/peps/0005-dashboard-cards.md §2b scene3d.robot): a GLB with one node per link, loaded
   once per URL for every card in this bundle, and cloned per series. The card poses each clone's link nodes from its
   rows; nothing here knows about time.

   STOCK PARTS: three's GLTFLoader (fetch, parse, materials from the file) and Object3D.clone (a clone shares the
   geometry and materials, so N robots cost one upload). OURS: the cache, finding the link nodes, the ghost's material.

   WHY flat shading, as GLTFLoader gives a GLB without normals: the build ships positions and indices only (1.5 MB for
   all 121,783 of Menagerie's triangles), and creasing normals in the page (BufferGeometryUtils.toCreasedNormals)
   took 375 ms of main thread for this model; at a card's size a facet is a pixel or two. */

import { PropertyBinding, Box3 } from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

const models = new Map();   // url → Promise<{root, triangles}>

/** The model at `url`, fetched and parsed once (a failed load stays failed until the page reloads). */
export function loadModel(url) {
  if (!models.has(url)) models.set(url, new GLTFLoader().loadAsync(url).then(prepare));
  return models.get(url);
}

/** For the unit tests: how many models this bundle holds. */
export const cachedModels = () => models.size;

function prepare(gltf) {
  const root = gltf.scene;
  let triangles = 0;
  root.traverse((o) => {
    if (!o.isMesh) return;
    const g = o.geometry;
    triangles += (g.index ? g.index.count : g.attributes.position.count) / 3;
    g.computeBoundingSphere();
  });
  return { root, triangles };
}

/** A link node of a model (or of a clone of it), by the name the .base gives it. GLTFLoader sanitises node names
    (PropertyBinding.sanitizeNodeName: '/' and '.' go, spaces become '_'), so the lookup does too. */
export function linkNode(root, link) {
  const name = PropertyBinding.sanitizeNodeName(link);
  return root.children.find((c) => c.name === name) || root.getObjectByName(name) || null;
}

/** Each link's meshes as a box in the link's own frame ({link: [min, max]}): the fitted camera poses its corners at
    every row, so the arm's whole sweep stays in frame (a sphere around the origin would count a 0.4 m upper arm as
    reaching 0.4 m every way). */
export function linkBoxes(model, links) {
  const out = {};
  const box = new Box3(), part = new Box3();
  for (const link of links) {
    const node = linkNode(model.root, link);
    if (!node) continue;
    node.updateWorldMatrix(true, true);
    const inv = node.matrixWorld.clone().invert();
    box.makeEmpty();
    node.traverse((o) => {
      if (!o.isMesh) return;
      if (!o.geometry.boundingBox) o.geometry.computeBoundingBox();
      box.union(part.copy(o.geometry.boundingBox).applyMatrix4(inv.clone().multiply(o.matrixWorld)));   // in its link's frame
    });
    if (!box.isEmpty()) out[link] = [box.min.toArray(), box.max.toArray()];
  }
  return out;
}

/** A clone of the model for one series: {root, nodes} with nodes in `links` order (null where the model lacks one).
    `material` (the ghost's, or a robot's own colour and opacity) replaces every mesh's own; without it the clone wears
    the file's colours. `scale` is the scene's unit per metre (CONTRACT §32 unit: mm draws a glTF, metres by its spec,
    1000 times as large): each link node scales its own meshes, so a pose row's position, written in the scene's unit,
    still places the link's origin. */
export function instance(model, links, material = null, scale = 1) {
  const root = model.root.clone(true);
  if (material) root.traverse((o) => { if (o.isMesh) o.material = material; });
  const nodes = links.map((l) => linkNode(root, l));
  if (scale !== 1) for (const n of nodes) if (n) n.scale.multiplyScalar(scale);
  return { root, nodes };
}
