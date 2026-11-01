/* The trail (CONTRACT §32): every primitive carries a per-vertex (or per-instance) time, and its material discards what
   lies outside the card's time window and fades the rest by age. A clock tick sets two uniforms, `dvWin` and `dvFade`;
   no geometry is rebuilt and no shader recompiles (the PEP's "a tick changes uniforms only").

   The window is Rerun's visible time range (VisibleTimeRange; the trail never shows the future): show: all is
   [−∞, +∞]; show: trail is [t − decay, t], or [−∞, t] for decay: inf. Times are stored relative to the card's time
   origin (its data's first t), because a float32 holds a Unix-seconds time to about a minute and a run's seconds to
   a microsecond.

   STOCK PARTS: three's LineMaterial (examples/jsm/lines, the pixel-width line), PointsMaterial and MeshBasicMaterial,
   each patched in onBeforeCompile with a few lines. OURS: those lines, and per-item alpha (a series the legend hides,
   opacity: auto) and dash patterns (a family's members: solid, long dash 8 4, dash-dot 8 3 2 3; the target 5 4;
   unclassified dotted), so one draw call holds every path of a layer. */

import { Vector2, Vector3, PointsMaterial, MeshBasicMaterial } from 'three';
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js';

/** The card's shared uniforms: every primitive's material reads these objects, so one write moves them all.
    dvWin: [lo, hi] relative to the time origin. dvFade: (from, span, on): alpha × mix(FADE_MIN, 1, (t − from) / span).
    dvDashUnit: the world length of one dash unit (a pattern 8 4 is 8 units of dash, 4 of gap). */
export function windowUniforms() {
  return { dvWin: { value: new Vector2(-1e30, 1e30) }, dvFade: { value: new Vector3(0, 1, 0) }, dvDashUnit: { value: 1 } };
}

// WHY a floor, not 0: a trail that fades to nothing hides where it started; Rerun's and Foxglove's trails stay faintly
// visible to their end
export const FADE_MIN = 0.1;

const FADE_GLSL = `float dvFadeOf(float t) { return dvFade.z > 0.5 ? mix(${FADE_MIN.toFixed(3)}, 1.0, clamp((t - dvFade.x) / max(dvFade.y, 1e-6), 0.0, 1.0)) : 1.0; }`;

/** The pixel-width line (LineSegments2) with per-segment times (dvTime: start, end), alpha (dvAlpha), dash pattern
    (dvDash: dash, gap, dash, gap in dash units; 0 0 0 0 solid) and path length (dvDist: start, end). */
export function lineMaterial(uniforms, opts = {}) {
  const m = new LineMaterial({ vertexColors: true, transparent: true, toneMapped: false, ...opts });
  m.onBeforeCompile = (shader) => {
    shader.uniforms.dvWin = uniforms.dvWin;
    shader.uniforms.dvFade = uniforms.dvFade;
    shader.uniforms.dvDashUnit = uniforms.dvDashUnit;
    shader.vertexShader = shader.vertexShader.replace('void main() {', `
      uniform vec2 dvWin;
      attribute vec2 dvTime;
      attribute float dvAlpha;
      attribute vec4 dvDash;
      attribute vec2 dvDist;
      varying float vDvT;
      varying float vDvA;
      varying vec4 vDvDash;
      varying float vDvD;
      void main() {
        // CULL: a segment wholly outside the window (or hidden) never reaches the rasterizer, so a trail of 500
        // segments in a 150,000-segment path costs 500 segments of fragments, not 150,000 discarded ones
        if ( dvTime.y < dvWin.x || dvTime.x > dvWin.y || dvAlpha <= 0.0 ) { gl_Position = vec4( 2.0, 2.0, 2.0, 1.0 ); return; }
        vDvT = ( position.y < 0.5 ) ? dvTime.x : dvTime.y;
        vDvA = dvAlpha;
        vDvDash = dvDash;
        vDvD = ( position.y < 0.5 ) ? dvDist.x : dvDist.y;`);
    shader.fragmentShader = shader.fragmentShader
      .replace('void main() {', `
      uniform vec2 dvWin;
      uniform vec3 dvFade;
      uniform float dvDashUnit;
      varying float vDvT;
      varying float vDvA;
      varying vec4 vDvDash;
      varying float vDvD;
      ${FADE_GLSL}
      void main() {
        if ( vDvT < dvWin.x || vDvT > dvWin.y || vDvA <= 0.0 ) discard;
        float dvTotal = vDvDash.x + vDvDash.y + vDvDash.z + vDvDash.w;
        if ( dvTotal > 0.0 ) {
          if ( abs( vUv.y ) > 1.0 ) discard; // a dashed line has no round caps: they would fill its gaps
          float dvU = mod( vDvD / dvDashUnit, dvTotal );
          if ( dvU > vDvDash.x && dvU < vDvDash.x + vDvDash.y ) discard;
          if ( dvU > vDvDash.x + vDvDash.y + vDvDash.z ) discard;
        }`)
      .replace('gl_FragColor = vec4( diffuseColor.rgb, alpha );', `alpha *= vDvA * dvFadeOf( vDvT );
        gl_FragColor = vec4( diffuseColor.rgb, alpha );`);
  };
  m.customProgramCacheKey = () => 'dv-window-line';
  return m;
}

/** Round points (Points) with a per-vertex time (dvT) and alpha (dvA); sizeAttenuation off, `size` in device px. */
export function pointsMaterial(uniforms, opts = {}) {
  const m = new PointsMaterial({ vertexColors: true, transparent: true, sizeAttenuation: false, toneMapped: false, ...opts });
  m.onBeforeCompile = (shader) => {
    shader.uniforms.dvWin = uniforms.dvWin;
    shader.uniforms.dvFade = uniforms.dvFade;
    shader.vertexShader = shader.vertexShader.replace('void main() {', `
      uniform vec2 dvWin;
      attribute float dvT;
      attribute float dvA;
      varying float vDvT;
      varying float vDvA;
      void main() {
        if ( dvT < dvWin.x || dvT > dvWin.y || dvA <= 0.0 ) { gl_Position = vec4( 2.0, 2.0, 2.0, 1.0 ); gl_PointSize = 0.0; return; }
        vDvT = dvT;
        vDvA = dvA;`);
    shader.fragmentShader = shader.fragmentShader
      .replace('void main() {', `
      uniform vec2 dvWin;
      uniform vec3 dvFade;
      varying float vDvT;
      varying float vDvA;
      ${FADE_GLSL}
      void main() {
        if ( vDvT < dvWin.x || vDvT > dvWin.y || vDvA <= 0.0 ) discard;
        vec2 dvC = gl_PointCoord - vec2( 0.5 );
        if ( dot( dvC, dvC ) > 0.25 ) discard; // round, not three's square`)
      .replace('#include <opaque_fragment>', `diffuseColor.a *= vDvA * dvFadeOf( vDvT );
        #include <opaque_fragment>`);
  };
  m.customProgramCacheKey = () => 'dv-window-points';
  return m;
}

/** An InstancedMesh's material (the arrows' cones) with a per-instance time (dvT) and alpha (dvA); colours from
    instanceColor. */
export function instanceMaterial(uniforms, opts = {}) {
  const m = new MeshBasicMaterial({ transparent: true, toneMapped: false, ...opts });
  m.onBeforeCompile = (shader) => {
    shader.uniforms.dvWin = uniforms.dvWin;
    shader.uniforms.dvFade = uniforms.dvFade;
    shader.vertexShader = shader.vertexShader.replace('void main() {', `
      uniform vec2 dvWin;
      attribute float dvT;
      attribute float dvA;
      varying float vDvT;
      varying float vDvA;
      void main() {
        if ( dvT < dvWin.x || dvT > dvWin.y || dvA <= 0.0 ) { gl_Position = vec4( 2.0, 2.0, 2.0, 1.0 ); return; }
        vDvT = dvT;
        vDvA = dvA;`);
    shader.fragmentShader = shader.fragmentShader
      .replace('void main() {', `
      uniform vec2 dvWin;
      uniform vec3 dvFade;
      varying float vDvT;
      varying float vDvA;
      ${FADE_GLSL}
      void main() {
        if ( vDvT < dvWin.x || vDvT > dvWin.y || vDvA <= 0.0 ) discard;`)
      .replace('#include <opaque_fragment>', `diffuseColor.a *= vDvA * dvFadeOf( vDvT );
        #include <opaque_fragment>`);
  };
  m.customProgramCacheKey = () => 'dv-window-instance';
  return m;
}

/** The window the shaders test, as numbers on the card's clock (not relative): {lo, hi, fadeFrom, fadeSpan, fade}.
    lo / hi null are unbounded. `t` is the instant drawn (clock.hover ?? clock.t), `t0` the data's first time. */
export function timeWindow(stage, t, t0) {
  const now = Number.isFinite(t) ? t : 0;
  if (stage.show !== 'trail') return { lo: null, hi: null, fade: false, fadeFrom: 0, fadeSpan: 1 };
  if (stage.decay === 'inf') {
    const from = Number.isFinite(t0) ? t0 : now;
    return { lo: null, hi: now, fade: stage.fade !== false, fadeFrom: from, fadeSpan: Math.max(now - from, 1e-6) };
  }
  const d = Number.isFinite(stage.decay) && stage.decay >= 0 ? stage.decay : 0;
  return { lo: now - d, hi: now, fade: stage.fade !== false && d > 0, fadeFrom: now - d, fadeSpan: Math.max(d, 1e-6) };
}
