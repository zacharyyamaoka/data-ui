# scene3d · trajectory3d · voxels

Three view types from one bundle (docs/CONTRACT.md §25, §32; docs/peps/0010-robotics-playback.md §5):

- **`scene3d`**, Layer 1: 3D primitives drawn from any columns, named as Rerun's archetypes are, on a stage (unit, up,
  projection, the view cube, axes, the trail, density, workspace). PEP 0005's path keys (`x, y, z, series, target, t,
  skeleton, robot, up`) stay a binding onto it and draw as they did.
- **`trajectory3d`**, Layer 2: the trajectory contract's viewer (gallery/robotics/CONTRACT.md). "A very particular
  viewer for a very particular dataclass" (Zach, 2026-10-28): every key defaults to the contract's column name, so a
  template may write the block empty. It is a binding (src/bind.js) plus its controls (src/controls.js); it has no
  drawing code of its own.
- **`voxels`** (PEP 0010 P2): the discretised space, Rerun's `VoxelGridMap` and BAM Reach's 3D heatmaps. Rows binned
  into cells, boxes in 3D, the slice an image heatmap from a face (below). It shares the stage (src/voxels/).

data-ui knows no robotics word: "situation", "source", "run", "frame" are the contract's default names, and a `.base`
names others. data-ui never computes a difference, a metric or forward kinematics: compare reads the difference rows
and robots read the link poses a producer wrote.

```yaml
- type: scene3d
  scene3d:
    unit: mm                     # m (default) | cm | mm: every column read; a glTF (metres) is scaled to it
    t: t                         # the time column every primitive is windowed by
    projection: perspective      # perspective | top | bottom | front | back | left | right | {dir: [x, y, z], up: [x, y, z]}
    show: trail                  # all (default) | trail
    decay: 0.5                   # seconds behind t (show: trail); inf (default) everything up to t; 0 the marker alone
    fade: true                   # the trail fades with age
    axes: auto                   # ticks on a face-aligned 2D view | none
    density: 20                  # markers per path: samples 0, s, 2s, … with s = ⌊n / density⌋, plus the last
    workspace: { box: [[x0, y0, z0], [x1, y1, z1]], opacity: 0.12 }   # or { model: reach.glb }
    layers:
      - { primitive: lines, x: x_mm, y: y_mm, z: z_mm, by: [run, situation], color: situation, dash: [target] }
      - { primitive: points, x: x_mm, y: y_mm, z: z_mm, density: 20 }
      - { primitive: frames, x: x_mm, y: y_mm, z: z_mm, quat: [quat_w, quat_x, quat_y, quat_z], axes: xyz }   # or z
      - { primitive: arrows, data: diff, from: [x_mm, y_mm, z_mm], to: [ref_x_mm, ref_y_mm, ref_z_mm], scale: 10 }
      - { primitive: arcs, data: diff, at: [x_mm, y_mm, z_mm], from: [quat_w, …], to: [ref_quat_w, …] }
      - { primitive: meshes, data: links, model: ur5e_links.glb, links: [base, …], by: situation }
      - { primitive: boxes, min: [x0_mm, y0_mm, z0_mm], max: [x1_mm, y1_mm, z1_mm] }

- type: trajectory3d
  trajectory3d:
    modes: { real: [line, frames-z], twin: [line] }     # per series: line | points | frames | frames-z (default [line])
    compare: { data: diff, pairs: [[real, target]], scale: 1 }   # arrows a(t) → b(t); Z-arcs where a draws frames-z
    robots: { data: links, model: media/ur5e_links.glb, links: [base, …], series: { twin: { color: 2, opacity: 0.5 } } }
    opacity: auto                # exactly 1/n over a family's n paths (no floor; PEP 0010 P2)
    color: err_mm                # path_overlay (CONTRACT §35): paint each non-target path by this column, per vertex
    tolerance: 5                 # path_overlay: the target's path again as a translucent tube of this radius (stage unit)
    # poses {x, y, z, quat, frame, body}, series (situation), family (style.families.property, else source), run,
    # t, target (the series whose family is target): the contract's names by default; and the stage keys above
```

```yaml
- type: voxels
  voxels:
    x: x_mm                      # the columns (required), in `unit`
    'y': y_mm
    z: z_mm
    cell: 25                     # the cell's edge in `unit` (required)
    value: time                  # count (default) | time (Σ w ÷ hz) | runs (distinct `run`) | <property> (pre-gridded rows)
    hz: 20                       # the rows' display rate (value: time needs it)
    summary: Average             # a property's summary: Average | Median | Min | Max | Sum
    slice: { axis: z, at: 137.5 } # or at: all, the projection along the axis
    min: 1                       # cells below it are not drawn
    projection: top              # a face draws the slice as an image heatmap; perspective the boxes
    # w (weight, default w), run (default run), unit, up, axes, workspace: as the stage
```

**voxels.** Raw rows (count, time, runs) bin on cells anchored at the frame's origin: cell k spans [k·cell,
(k + 1)·cell) along each axis, the edges the float64 products k·cell, so a value on an edge is in the cell it starts
(numpy.histogramdd's rule; P2's check holds every cell to it exactly). Pre-gridded rows (`value: <property>`, the
contract's `grid.json`) bin on their own lattice (origin = the smallest centre − cell / 2), so each centre stays its
cell's centre. `time` is Σ w ÷ hz (w is 1 on the time grid, 0 on a run's kept extremes; a row without one weighs 1),
`runs` how many distinct runs passed through a cell, the exact count that blending at 1/n cannot give past a few
hundred runs. `slice: {axis, at}` picks the cell holding `at`; `at: all` bins with the axis dropped, a 2D histogram of
the projection (count and time sum through the depth; runs counts a run once per column). **3D** (perspective, or a
`{dir}`): a box per cell at 0.8 × the cell, two `InstancedMesh`es, the slice's cells solid and every other cell faded
(all solid without a numeric slice). **2D** (a face): the plane across the view through the slice (or the projection,
when the slice is on another axis or `all`), one quad with a `DataTexture` (`NearestFilter`, unlit), so the cells are
crisp pixels with the stage's axes in `unit`; hover reads a cell (its ranges and its value) in the foot. The strip under
the stage steps the slice one cell at a time (◀ ▶, a range, All; in 3D an axis select), each change `host.setView`
(the URL, Save view). **Colour**: one sequential ramp (src/voxels/ramp.js) over the grid's [min(0, smallest), largest],
the projection's own with `at: all`, so stepping keeps colours comparable: one family in the rows (`style.families`'
property has one value, listed in its map) takes that family's hue, anything else grey; light to dark on a light
surface and the other way on a dark one (a cell near zero recedes toward the surface); built in OKLab with the hue held
in OKLCH and chroma reduced to stay in sRGB. Never red or green outside `scale: verdict` (the gates overlay's, P5):
that colours the cells from the bad tone through the warn tone to the good tone (`tokens.tone`, OKLab, two straight
runs so the middle is the warn tone itself), `better: higher` (default) or `lower`, and its bar carries ✕ at the bad
end and ✓ at the good end. The legend is the ramp's bar with its two ends.

**Layers.** One primitive per layer, one draw call per layer (src/primitives/). A layer reads its own `data:` (another
dataset of the dashboard, `input.layers[<name>]`, filtered as a panel on it would be) or the view's rows. `by` makes
paths; `color` (default the first `by` column) picks each group's colour through `seriesColor` and, with `by`, splits
the groups, so one group is one colour. `dash` lists colour values drawn dashed. A layer naming a dataset the page does
not have draws nothing and the card's foot says so.

**trajectory3d.** One path per (series, run, body), in time order, broken at a missing value. Its hue is its family's
(`style.families`; `seriesColor`): a family's members in natural order draw solid, long dash 8 4, then dash-dot
8 3 2 3; four or more draw one hue at `opacity: auto` with one legend entry; the target is dashed 5 4 and muted, drawn
on top; a family the map does not list is muted, dotted and "unclassified" in the legend. `opacity: auto` is exactly
1/n over a family's n paths, with no floor (Zach's brief for P2: "draw all of the runs with 1/n opacity so you can see
where they went most often"); each path's "now" marker takes its path's alpha, so 137 markers stacked where every run is
at t read as one dot. Every path is one item of the layer's one `LineSegments2` and the markers are one `InstancedMesh`
per look, so 137 runs are a handful of draw calls, not 137. The known limit: the shared renderer blends into an 8-bit
canvas, where each blend rounds to a whole level. Measured (2026-10-29, N runs of one family, N − 1 stacked on one
line and one alone, the canvas alpha at a segment joint): N = 137, stacked 187/255 and alone 4/255; N = 250, 131 and 2
(the stack now falls short and its red and green round away first, so it reads pure blue); N = 400, 56 and 2;
N = 500, 6 and 2; N = 1,001, nothing at all. So 1/n holds to about 200 runs; the rack's 1,000 need a float
accumulation target (not built) or `voxels` with `value: runs`, which counts instead of blending. Rows of the pose table in two
frames draw nothing and the card names both (frames are declared, never guessed). Compare's default pairs are every
pair present in the difference rows whose b is the target. An arrow runs from a(t) to b(t) as the difference row writes
them (at `scale: 1` its tip is b(t) itself, never a + (b − a)); a Z-arc draws a's Z in the series' colour, b's Z muted
and the arc between their tips. `scale` lengthens the arrows only, and the card says so in its own label, "arrows ×N",
which stays on a narrow card where the hint folds away (P1d: within 1e-6 mm of the difference fixture, arcs within
0.1° of both Z axes; tests/browser/p1d_checks.py). One robot per series, posed at t from its link rows (its first run; the foot says so when a series has several),
in its colour (`series`, `muted`, a slot 1-8, a CSS colour) and opacity (target 0.25 by default); the stick through the
link origins stands in while the GLB loads, and for good if it fails.

**path_overlay** (P5, CONTRACT §35; trajectory3d only). `color: <column>` paints each non-target path per vertex by
that column of its own rows (in time order) on a straight OKLab line from series 1 (`tokens.series[0]`) to the warn tone
(`tokens.tone.warn`) over the drawn rows' [min, max]; each segment runs from its start vertex's colour to its end
vertex's, and the bar (the legend's last row, titled with the column's label and unit) names the two ends. A flat range
(min = max) is the low end; a vertex with no number wears the path's own colour; the target is not painted; the view
never computes the number. `tolerance: <n>` (> 0, the stage's unit) draws the target path's points again as one
translucent tube per run of points (three's `TubeGeometry` along a `CurvePath` of `LineCurve3`, 12 sides, up to 2,000
rings, opacity 0.16, depthWrite off, drawn before the lines): in a face view it projects to a band 2 × n wide, and the
legend says "± n unit" beside the target. The tube is built once per rebuild, so a clock tick still touches no geometry;
CurvePath's lookup is linear in the points, so a target of tens of thousands of points builds slowly.

**The controls** (trajectory3d, a strip under the stage, never a side panel): per trajectory its modes (Line, Points,
Frames, Z only; at least one stays on: show/hide is the rail's job) and its robot (on/off, colour, opacity); Show (all
time steps | decay) with the decay in seconds and its sample count at the data's rate; the density dial (traj_compare's
log dial, 4 to 400); compare's arrow scale ×1, ×10, ×30, ×100. Every change is `host.setView`, so it rides in the URL
(`v=`) and Save view, and a filter change never resets it.

**The stage.** Perspective orbits (OrbitControls; drag orbits, the wheel zooms, right-drag pans; on a phone a vertical
swipe scrolls the page). A face or `{dir}` is orthographic: drag pans, the wheel zooms about the pointer, a double-click
fits, nothing rotates, and one world size per pixel serves both screen axes (equal scale by construction). The view
cube is three r186's `ViewHelper`, drawn through the page's one WebGL context into the card's own canvas (+0 contexts);
a click on a ball turns the camera to that side (the contract's face table: top looks along −z with +y up, the four
sides keep the scene's up; with `up: y` turned by (x, y, z) → (x, z, −y)) and makes it orthographic at the end of the
turn. Under it: the projection menu (also the keyboard's way: Enter on the cube steps through the faces), Fit, and 3D.
On a face-aligned 2D view: tick labels in the scene's unit at their values' projections, the axis titled with its
unit and the frame ("x (mm) · frame: base"), the grid behind the canvas. **The trail** is Rerun's visible time range:
every item carries its time, and the shaders discard what lies outside [t − decay, t] and fade the rest; a clock tick
writes two uniforms (src/primitives/window.js) and builds no geometry. Primitives draw at `clock.hover ?? clock.t`, so
a time series hover previews that instant here.

**Tokens** (every stage size and colour, so a design round restyles with tokens alone): `--data-scene3d-line` (2px),
`-target-line` (1.5px), `-frame` (1.5px), `-point` (5px), `-cube` (72px), `-axis-x` / `-axis-y` / `-axis-z` (the frame
axes: RGB = XYZ, always labelled, never a series), `-grid`, `-label`, `-workspace`, `-control`; series colours are
`--data-series-*` and `--data-muted`.

**For checks:** the card's `.dv-scene3d` carries `scene3d` (tests/browser/p1b_checks.py lists it): `camera()` (view and
projection matrices, canvas size, projection, ortho, animating), `markers()`, `visible()`, `joints()`, `colors()` (as
drawn), `renders()`, `robot()` (the GLB, PEP 0005's shape), `window()`, `drawn()`, `builds()`, `size()`, `counts()`,
`geometry(series, mode)` (read back from the buffers), `robots()` (each robot's material), `problem()`, and compare's
`arrows()` (each arrow drawn now: series, t, `from`, `to` and `tip` as read, float64, and `drawn`, the shaft read back
from the GPU buffer) and `arcs()` (each Z-arc drawn now: its anchor, a's and b's quaternions, and `drawn`: the own Z,
the reference Z and the arc's points). DOM: `[data-compare-label]` ("arrows ×N" while the scale is not 1),
`[data-marker][data-series]` rings, `[data-cube]`, `[data-tick][data-axis][data-value]`, `[data-axis-title]`, and the
controls' `[data-t3-series]`, `[data-mode]`, `[data-robot-color]`, `[data-robot-opacity]`, `[data-show]`, `[data-decay]`,
`[data-density]`, `[data-compare-scale]`. `globalThis.__dataUiGL.stats()` gives `{contexts, scenes, renders, …}`.
P2 (tests/browser/p2_checks.py) adds `calls()` (renderer.info.render.calls of the last frame, before the cube),
`drawables()` (the visible drawn objects, each with its role: line, target, markers, workspace-fill, voxels-solid, …),
`frame()` (draw now), `paths()` and `opacity()` (each series' paths and their alpha as the shader multiplies it, the line
material's opacity × the uploaded dvAlpha), `workspace()` (the outline's fill and edge vertices in world units); and
for voxels `cells()` (every cell holding rows: index and value), `slice()` (the drawn plane's values), `ramp()` (its two
ends, domain and family) and `boxes()` (each box read back from its instance matrix). P5 adds `overlay()` (`{color, min, max, segments: [{series,
value, color}]}`: each painted segment's start value and its start vertex colour from the GPU buffer, sRGB hex), `tube()`
(`{radius, path, paths, rings: [{center, points}]}`: each ring a cross-section of the TubeGeometry) and, for voxels,
`cellColours()` (`[i, j, k, value, '#rrggbb']` per drawn cell, from the instance colour buffer in 3D, the texel in 2D). DOM: `[data-slice-step]`,
`[data-slice]`, `[data-slice-all]`, `[data-slice-axis]`, `[data-slice-at]`, `[data-ramp]`.

**Robot accuracy** (PEP 0005's): link poses are exact at the rows; between rows the card lerps positions and slerps
orientations, ≤ 1.34 mm from true forward kinematics on pid-tuning's tape (gallery/examples/pid-tuning/source/
measure_robot_interp.py). A producer that needs better between rows bakes them denser.

**Stock parts:** three 0.186.1: WebGLRenderer (one per page, src/gl.js), LineSegments2 / LineSegmentsGeometry /
LineMaterial, Points / PointsMaterial, InstancedMesh / ConeGeometry, OrbitControls, OrthographicCamera, ViewHelper,
GridHelper, EdgesGeometry, GLTFLoader (src/robot.js). **Ours:** the bindings (src/bind.js), the trail's shader lines
(src/primitives/window.js), the density rule, faces, 2D fit and ticks (src/math.js, unit-tested in
tests/unit/scene3d-stage.test.mjs and scene3d-bind.test.mjs), the cube's face table and turn (src/stage.js), the
controls, render on demand.

**Workspace.** `workspace: {box}` or `{model}` (a GLB, metres by its spec, scaled to `unit`) is a translucent fill and
its edges (`EdgesGeometry`, 30°), drawn in 3D and from every face; a model joins the framed box once it loads, and the
camera refits to it unless the reader has moved it (P2's check: its top-view outline within 1 px of the model's hull).

**Not yet** (later phases): "Open in Rerun" writing voxels as
a `VoxelGridMap` and the trail's `VisibleTimeRange` (tools/rerun_export.py), a legend or table pick lifting one run to
full opacity (PEP 0010 §7), a float accumulation target for `opacity: auto` past ~500 runs,
3D tick labels on the perspective view (the arm mock's matplotlib-style axes: the 3D view shows the ground grid), the
labelled view cube (PEP 0010 Q1), and a display frame switch (`frames.json`, P3+).
