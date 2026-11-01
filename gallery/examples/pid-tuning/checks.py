"""Browser checks for the PID tuning dashboard (PEP 0004, PEP 0005). Oracles from the case's JSON files and views.base:
round 1's gains.json, robots.json, fidelity.json; round 2's samples.json, step.json, tool.json, kpis.json, joints.json,
media.json and headline.json (kpis.json's cells copied beside each other, checked against kpis.json here)."""

import bisect
import contextlib
import pathlib
import re
import sys
from urllib.parse import urljoin

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from dashboard_helpers import D, card, counts, num, ready, rows  # noqa: E402

GAINS = rows(HERE, "gains.json")
ROBOTS = rows(HERE, "robots.json")
FID = rows(HERE, "fidelity.json")
SAMPLES = rows(HERE, "samples.json")
STEP = rows(HERE, "step.json")
TOOL = rows(HERE, "tool.json")
ROBOT = rows(HERE, "robot.json")   # the 3D card's data since scene3d.robot (source/build_robot.py: link poses at 25 Hz)
KPIS = rows(HERE, "kpis.json")
HEAD = rows(HERE, "headline.json")
JOINTS = rows(HERE, "joints.json")
MEDIA = rows(HERE, "media.json")
BASE = (HERE / "views.base").read_text(encoding="utf-8")
v = lambda c: c["value"] if isinstance(c, dict) else c
sig3 = lambda x: float(f"{x:.3g}")
K = {r["situation"]: r for r in KPIS}
RUNGS = [r["situation"] for r in sorted(KPIS, key=lambda r: r["order"])]
_p = re.search(r"palette: \{([^}]*)\}", BASE)
PALETTE = dict(re.findall(r'(\w+): "(#[0-9a-f]{6})"', _p.group(1))) if _p else {}

# the rail's default joint, as views.base writes it (datasets.samples.filters)
_m = re.search(r"  samples:\n(?:    .*\n)*?    filters: 'joint == \"([^\"]+)\"'", BASE)
DEFAULT_JOINT = _m.group(1) if _m else None
# the Error over time rule, as views.base writes it
_r = re.search(r"name: Error over time\n(?:.*\n)*?\s+rules: \[\{ y: ([\d.]+)", BASE)
RULE = float(_r.group(1)) if _r else None

# a panel's Vega plot: page px of data values through its own scales
AT = """([key, pts]) => {
  const el = document.querySelector(`#example .dd-panel[data-panel="${key}"] .dv-view`);
  const v = el.vegaView, r = el.querySelector('canvas').getBoundingClientRect(), p = v.padding(), o = [p.left + v.origin()[0], p.top + v.origin()[1]];
  return pts.map(([x, y]) => [r.left + o[0] + v.scale('x')(x), y === null ? null : r.top + o[1] + v.scale('y')(y)]); }"""

SERIES = """([key, rule]) => {
  const el = document.querySelector(`#example .dd-panel[data-panel="${key}"] .dv-view`);
  if (!el || !el.vegaView) return null;
  const out = {}, rules = [];
  const walk = (node) => {
    if (!node) return;
    if (node.marktype) {
      for (const i of node.items || []) {
        if (node.marktype === 'line' && i.datum && i.datum.series) {
          const s = out[i.datum.series] || (out[i.datum.series] = { n: 0, stroke: i.stroke, dash: i.strokeDash || null });
          s.n += 1;
        }
        if (node.marktype === 'rule' && /^layer_\\d+_marks$/.test(node.name || '')) rules.push(i.y);
        walk(i);
      }
    } else if (node.items) for (const i of node.items) walk(i);
  };
  walk(el.vegaView.scenegraph().root);
  const y = el.vegaView.scale('y');
  return { series: out, rules, scale: y && y.type, y: rule === null || !y ? null : [y(rule), y(-rule)], ydomain: y && y.domain() }; }"""

VIDEOS = """(s) => [...document.querySelectorAll(s + ' video[data-t0]')].map((v) => ({
  src: v.dataset.src || null, poster: v.poster, t0: Number(v.dataset.t0), ready: v.readyState, seeking: v.seeking, t: v.currentTime, paused: v.paused }))"""

TEXT = "([k, s]) => { const e = document.querySelector(`#example [data-panel=\"${k}\"] ${s}`); return e ? e.textContent.trim() : null; }"


@contextlib.contextmanager
def guard(ctx, what):
    """A section that cannot run (its panel is not there) is one failing check in its own words, not a crash."""
    try:
        yield
    except Exception as e:  # noqa: BLE001 -- reported, never hidden
        ctx.check(f"pid: {what} could not be measured", False, f"{type(e).__name__}: {str(e)[:300]}")


def seek(page, t):
    page.evaluate("(t) => document.querySelector('#example').clock.seek(t)", t)
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")


def clock(page):
    return page.evaluate("() => { const c = document.querySelector('#example').clock; return { t: c.t, start: c.start, end: c.end, playing: c.playing, driver: c.driver && c.driver.id }; }")


def loaded(ctx, page, key):
    page.locator(f"{D} .dd-panel[data-panel='{key}']").scroll_into_view_if_needed()
    return ctx.until(page, """(s) => { const vs = [...document.querySelectorAll(s + ' video[data-t0]')];
      return vs.length && vs.every((v) => v.dataset.src && v.readyState >= 2 && !v.seeking); }""", f"{D} .dd-panel[data-panel='{key}']", timeout=15000)


def settled(ctx, page, scope=D):
    return ctx.until(page, """(s) => [...document.querySelectorAll(s + ' video[data-t0]')].every((v) => v.readyState >= 2 && !v.seeking)""", scope, timeout=10000)


def interp(rs, t, cols):
    """Linear interpolation of cols at t over rows sorted by t: the oracle for a marker between samples."""
    ts = [r["t"] for r in rs]
    i = min(max(bisect.bisect_right(ts, t), 1), len(rs) - 1)
    a, b = rs[i - 1], rs[i]
    f = (t - a["t"]) / (b["t"] - a["t"])
    return [a[c] + (b[c] - a[c]) * f for c in cols]


def project(cam, p):
    """CSS px relative to the canvas of world point p, through the card's camera (column-major 4x4 matrices)."""
    def mul(m, x):
        return [sum(m[col * 4 + row] * x[col] for col in range(4)) for row in range(4)]
    clip = mul(cam["proj"], mul(cam["view"], [p[0], p[1], p[2], 1.0]))
    return ((clip[0] / clip[3] + 1) / 2 * cam["width"], (1 - clip[1] / clip[3]) / 2 * cam["height"])


def run(ctx, path):
    page = ctx.page(path, width=1440, height=1000)
    ready(page)
    got = counts(page)
    ctx.check("pid: 9 robot cards, 132 joint × rung rows in every gains panel, 10 real fidelity rows",
              got["tuned-against-the-oracle:cards"] == len(ROBOTS) and got["gain-vs-error"] == len(GAINS) and got["per-joint-and-motor"] == len(GAINS) and got["sim-vs-real-stop-p90"] == len(FID), got)
    fb = next(r for r in ROBOTS if r["robot_id"] == "five_bar")
    c = card(page, "tuned-against-the-oracle", "Five-bar arm")
    shown = num(c.locator(".dv-kpi-num").inner_text())
    exact = float(c.locator(".dv-kpi-num").get_attribute("data-exact") or "nan")
    # style.numbers (digits 3) rounds the drawn number since the round-2 rebuild; the stored value stays in data-exact
    ctx.check("pid: the five-bar card is the producer's tuned tracking RMS to 3 significant figures (the stored value in data-exact, as written)",
              shown == sig3(v(fb["tuned_tracking_rms"])) and exact == v(fb["tuned_tracking_rms"]), {"shown": shown, "exact": exact, "data": v(fb["tuned_tracking_rms"])})
    ur5e_before = {k: got.get(k) for k in ("joint-angle-vs-target", "error-over-time", "tool-path-3d-sim-fk", "stop-p90-tuned")}
    c.locator(".dv-kpi-label").click()
    page.wait_for_timeout(700)
    got = counts(page)
    n = sum(g["robot_id"] == "five_bar" for g in GAINS)
    ctx.check("pid cross-filter: clicking the five-bar card narrows both gains charts and the table to its 8 rows (through the link); the unlinked rack data keeps all 10",
              got["gain-vs-error"] == n and got["error-by-rung"] == n and got["per-joint-and-motor"] == n and got["sim-vs-real-stop-p90"] == len(FID), got)
    ctx.check("pid cross-filter: the five-bar selection leaves the UR5e's panels alone (no link from robots to the replay datasets)",
              {k: got.get(k) for k in ur5e_before} == ur5e_before and None not in ur5e_before.values(), {"before": ur5e_before, "after": {k: got.get(k) for k in ur5e_before}})
    page.click(f"{D} .dd-chip")
    page.wait_for_timeout(400)
    page.check("data-facets[data-dataset=gains] input[data-p=rung][data-value=oracle]")
    page.wait_for_timeout(700)
    got = counts(page)
    ctx.check("pid rail: rung = oracle narrows the gains panels to 33 rows; the robot cards stay 9 (every robot has an oracle rung)",
              got["per-joint-and-motor"] == sum(g["rung"] == "oracle" for g in GAINS) and got["tuned-against-the-oracle:cards"] == 9, got)
    page.context.close()

    page = ctx.page(path, width=1440, height=1000)
    ready(page)
    got = counts(page)

    # ---- the tiles: kpis.json's tuned numbers to 3 s.f., deltas against the factory and the oracle
    with guard(ctx, "the UR5e tiles"):
        ok = all(v(h[k]) == v(K[h["situation"]][k]) and v(h[f"{o}_{k}"]) == v(K[o][k])
                 for h in HEAD for k in ("stop_p90", "tracking_rms") for o in ("factory", "oracle"))
        ctx.check("pid headline.json: every cell is kpis.json's own (the rung's, the factory's and the oracle's), nothing recomputed",
                  ok and [h["situation"] for h in HEAD] == RUNGS, [h["situation"] for h in HEAD])
        t = {k: page.evaluate(TEXT, [k, s]) for k, s in (("stop-p90-tuned", ".dv-kpi-num"), ("tracking-rms-tuned", ".dv-kpi-num"), ("better-than-factory", ".dv-kpi-num"))}
        d = {k: page.evaluate("""(k) => { const e = document.querySelector(`#example [data-panel="${k}"] .dv-kpi-delta, #example [data-panel="${k}"] [class*=delta]`);
               return e ? { text: e.textContent.trim(), cls: e.className, dir: e.dataset.dir || null } : null; }""", k) for k in ("stop-p90-tuned", "tracking-rms-tuned")}
        tu = K["tuned"]
        want = {"stop-p90-tuned": sig3(v(tu["stop_p90"])), "tracking-rms-tuned": sig3(v(tu["tracking_rms"])), "better-than-factory": sig3(v(tu["vs_factory"]))}
        shown = {k: num(x) for k, x in t.items()}
        ctx.check("pid tiles: Stop p90, Tracking RMS and × better than factory show kpis.json's tuned numbers to 3 significant figures",
                  shown == want, {"shown": shown, "want": want})
        ds, dt = d["stop-p90-tuned"] or {}, d["tracking-rms-tuned"] or {}
        ctx.check("pid tiles: Stop p90 carries ▼ (tuned − factory) in the good tone 'vs Factory'; Tracking RMS carries ▲ (tuned − oracle) in the bad tone 'vs Oracle' (lower is better)",
                  num(ds.get("text")) == sig3(v(K["factory"]["stop_p90"]) - v(tu["stop_p90"])) and ds.get("dir") == "down" and "vs Factory" in ds.get("text", "") and "dv-kpi-good" in ds.get("cls", "")
                  and num(dt.get("text")) == sig3(v(tu["tracking_rms"]) - v(K["oracle"]["tracking_rms"])) and dt.get("dir") == "up" and "vs Oracle" in dt.get("text", "") and "dv-kpi-bad" in dt.get("cls", ""),
                  d)
        bl = page.evaluate("""() => [...document.querySelectorAll('#example [data-panel="tracking-rms-by-rung"] .dv-barlist-row')].map((r) => ({
          label: r.querySelector('.dv-barlist-label').textContent, value: r.querySelector('.dv-barlist-value').textContent,
          w: r.querySelector('.dv-barlist-bar').getBoundingClientRect().width, track: r.querySelector('.dv-barlist-track').getBoundingClientRect().width }))""")
        order = sorted(KPIS, key=lambda r: v(r["tracking_rms"]))
        ctx.check("pid tiles: Tracking RMS by rung lists the four rungs smallest first (oracle … factory), each kpis.json's value to 3 s.f., factory's bar the full track",
                  [b["label"] for b in bl] == [r["situation"] for r in order] and [num(b["value"]) for b in bl] == [sig3(v(r["tracking_rms"])) for r in order]
                  and bl and abs(bl[-1]["w"] - bl[-1]["track"]) <= 1, bl)

    # ---- the rail's joint: both time series draw it, target dashed, every rung in the palette's colour
    with guard(ctx, "the rail's joint and the time series"):
        ja = page.evaluate(SERIES, ["joint-angle-vs-target", None])
        n_joint = sum(r["joint"] == DEFAULT_JOINT for r in SAMPLES)
        sits = ["target"] + RUNGS
        ctx.check(f"pid rail: the joint rail starts on {DEFAULT_JOINT}; Joint angle draws its {n_joint} rows as target (dashed) and the four rungs, each in style.palette's colour",
                  DEFAULT_JOINT == "elbow_joint" and got["joint-angle-vs-target"] == n_joint and ja and sorted(ja["series"]) == sorted(sits)
                  and bool(ja["series"]["target"]["dash"]) and not any(ja["series"][s]["dash"] for s in RUNGS)
                  and {s: (ja["series"][s]["stroke"] or "").lower() for s in sits} == {s: PALETTE[s] for s in sits},
                  {"count": got["joint-angle-vs-target"], "want": n_joint, "series": ja and {k: (x["stroke"], bool(x["dash"])) for k, x in ja["series"].items()}})
        er = page.evaluate(SERIES, ["error-over-time", RULE])
        n_err = sum(r["joint"] == DEFAULT_JOINT and r["situation"] != "target" for r in SAMPLES)
        ctx.check("pid error: Error over time draws the four rungs' err_mrad (no target) on a symlog axis, its two rules on Vega's y(±rule) within 1 px, the rule kpis.json's tuned tracking RMS",
                  got["error-over-time"] == n_err and er and sorted(er["series"]) == sorted(RUNGS) and er["scale"] == "symlog"
                  and RULE == v(K["tuned"]["tracking_rms"]) and len(er["rules"]) == 2 and all(abs(a - b) <= 1 for a, b in zip(sorted(er["rules"]), sorted(er["y"]))),
                  {"count": got["error-over-time"], "want": n_err, "scale": er and er["scale"], "rules px": er and er["rules"], "y(±rule)": er and er["y"], "rule": RULE})
        page.locator(f"{D} data-facets[data-dataset=samples] input[data-p=joint][data-value=wrist_1_joint]").check(timeout=5000)
        page.wait_for_timeout(900)
        got2 = counts(page)
        ja2 = page.evaluate(SERIES, ["joint-angle-vs-target", None])
        w1 = [r["q_deg"] for r in SAMPLES if r["joint"] == "wrist_1_joint"]
        ctx.check("pid rail: picking wrist_1_joint narrows Joint angle and Error over time to its rows; the y axis now spans wrist 1's angles; tool, videos and tiles keep theirs",
                  got2["joint-angle-vs-target"] == len(w1) and got2["error-over-time"] == sum(r["joint"] == "wrist_1_joint" and r["situation"] != "target" for r in SAMPLES)
                  and ja2 and ja2["ydomain"][0] <= min(w1) and ja2["ydomain"][1] >= max(w1)
                  and all(got2[k] == got[k] for k in ("tool-path-3d-sim-fk", "tool-path-xz-sim-fk", "mujoco-replay-tuned-sim", "stop-p90-tuned")),
                  {"counts": got2, "ydomain": ja2 and ja2["ydomain"], "wrist_1": [min(w1), max(w1)]})

    # ---- the clock: its span, the videos and every playhead and marker on one t
    with guard(ctx, "the clock, the videos and the markers"):
        c = clock(page)
        ts = [r["t"] for r in SAMPLES]
        ctx.check("pid clock: the clock spans samples.json's t (clock: data samples)", [c["start"], c["end"]] == [min(ts), max(ts)], c)
        tuned = next(m for m in MEDIA if m["situation"] == "tuned")
        ok = loaded(ctx, page, "mujoco-replay-tuned-sim")
        vid = page.evaluate(VIDEOS, f"{D} .dd-panel[data-panel='mujoco-replay-tuned-sim']")
        cap = page.evaluate(TEXT, ["mujoco-replay-tuned-sim", ".dv-media-cap"]) or ""
        ctx.check("pid video: MuJoCo replay · tuned plays media.json's tuned clip (src, poster, t0), captioned 'tuned' and 'sim render'",
                  ok and len(vid) == 1 and vid[0]["src"] == urljoin(page.url, tuned["src"]) and vid[0]["poster"] == urljoin(page.url, tuned["poster"])
                  and vid[0]["t0"] == tuned["t0"] and "tuned" in cap and "sim render" in cap, {"video": vid, "caption": cap})
        frame = 1 / tuned["fps"]
        offs = []
        for t in (1.0, 3.5, 6.2):
            seek(page, t)
            settled(ctx, page, f"{D} .dd-panel[data-panel='mujoco-replay-tuned-sim']")
            cur = page.evaluate(VIDEOS, f"{D} .dd-panel[data-panel='mujoco-replay-tuned-sim']")[0]["t"]
            offs.append({"t": t, "currentTime": round(cur, 4), "off": round(abs(cur - (t - tuned["t0"])), 4)})
        ctx.check(f"pid sync: after seeks to 1.0, 3.5, 6.2 s the replay's currentTime is t − t0 within one frame ({frame:.4f} s)", all(o["off"] <= frame for o in offs), offs)
        keys = ("joint-angle-vs-target", "error-over-time", "lever-pick-and-place-sim")
        ph = page.evaluate("""(ks) => ks.map((k) => { const e = document.querySelector(`#example [data-panel="${k}"] [data-playhead]`);
          if (!e) return null; const b = e.getBoundingClientRect(); return b.left + b.width / 2; })""", list(keys))
        want_x = [page.evaluate(AT, [k, [[6.2, None]]])[0][0] for k in keys]
        ctx.check("pid sync: at t = 6.2 s the three time series' playheads (UR5e angle, error, lever) sit on their Vega x(6.2) within 1 px",
                  all(p is not None and abs(p - w) <= 1 for p, w in zip(ph, want_x)), {"playheads": ph, "x(6.2)": want_x})
        TM = 0.293  # off tool.json's 0.02 s grid where the tool moves fastest, so a marker must interpolate, not hold the sample before t
        page.locator(f"{D} .dd-panel[data-panel='tool-path-xz-sim-fk']").scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        seek(page, TM)
        rs = sorted((r for r in TOOL if r["situation"] == "tuned"), key=lambda r: r["t"])
        px, pz = interp(rs, TM, ["px", "pz"])
        mk = page.evaluate("""() => { const e = document.querySelector('#example [data-panel="tool-path-xz-sim-fk"] [data-marker][data-series="tuned"]');
          if (!e) return null; const b = e.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; }""")
        at = page.evaluate(AT, ["tool-path-xz-sim-fk", [[px, pz]]])[0]
        ctx.check("pid sync: at t = 0.293 s (off the 0.02 s grid) the XZ path's tuned marker sits on tool.json's tuned (px, pz) interpolated at 0.293 s, through the plot's own scales, within 1.5 px",
                  mk is not None and abs(mk[0] - at[0]) <= 1.5 and abs(mk[1] - at[1]) <= 1.5, {"marker": mk, "want": at, "tool": [px, pz]})
        k3 = "tool-path-3d-sim-fk"
        page.locator(f"{D} .dd-panel[data-panel='{k3}']").scroll_into_view_if_needed()
        # WHY robot.json as the oracle: since scene3d.robot the 3D card reads the link poses (25 Hz FK); its marker is that
        # dataset's tool point and its arm is Menagerie's meshes posed per link (the stick only while the GLB loads)
        drew = ctx.until(page, "(k) => { const h = (document.querySelector(`#example .dd-panel[data-panel='${k}'] .dv-scene3d`) || {}).scene3d; const r = h && h.robot && h.robot(); return !!h && h.renders() > 0 && !!r && r.state === 'ready' && r.drawn; }", k3, timeout=30000)
        seek(page, TM)
        s3 = page.evaluate("""(k) => { const root = document.querySelector(`#example .dd-panel[data-panel='${k}'] .dv-scene3d`); const h = root && root.scene3d;
          if (!h) return null; const c = root.querySelector('canvas').getBoundingClientRect(); const m = root.querySelector('[data-marker][data-series="tuned"]');
          const r = m && m.getBoundingClientRect(); const rob = h.robot();
          return { world: h.markers().tuned || null, links: (rob.links || {}).tuned || null, cam: h.camera(), dot: r ? [r.left + r.width / 2 - c.left, r.top + r.height / 2 - c.top] : null }; }""", k3)
        rr = sorted((r for r in ROBOT if r["situation"] == "tuned"), key=lambda r: r["t"])
        p3 = interp(rr, TM, ["px", "py", "pz"])
        LINKS = ["base", "shoulder_link", "upper_arm_link", "forearm_link", "wrist_1_link", "wrist_2_link", "wrist_3_link"]
        want_links = {l: interp(rr, TM, [f"{l}_x", f"{l}_y", f"{l}_z"]) for l in LINKS}
        got_links = (s3 or {}).get("links") or {}
        worst = max((max(abs(a - b) for a, b in zip(got_links[l]["p"], want_links[l])) for l in LINKS if l in got_links), default=None)
        want_px = project(s3["cam"], p3) if s3 and s3["cam"] else None
        ctx.check("pid 3D: at t = 0.293 s the 3D card's tuned marker is robot.json's interpolated tool point (within 1 µm), on screen through its own camera within 1.5 px, and the meshed UR5e's link nodes are exactly the 7 links and stand at robot.json's link positions lerped at t (within 1 µm of the interpolated rows; between rows that is ≤ 1.34 mm from true FK (max 1.335 mm over 104,804 link samples), source/measure_robot_interp.py)",
                  drew and s3 and s3["world"] and max(abs(a - b) for a, b in zip(s3["world"], p3)) <= 1e-6 and s3["dot"] and want_px
                  and abs(s3["dot"][0] - want_px[0]) <= 1.5 and abs(s3["dot"][1] - want_px[1]) <= 1.5
                  and set(got_links) == set(LINKS) and worst is not None and worst <= 1e-6,
                  {"drew": drew, "world": s3 and s3["world"], "want": p3, "dot": s3 and s3["dot"], "want px": want_px, "links": len(got_links), "worst link m": worst})

        factory = next(m for m in MEDIA if m["situation"] == "factory")
        loaded(ctx, page, "factory-vs-tuned-sim")
        pv = page.evaluate(VIDEOS, f"{D} .dd-panel[data-panel='factory-vs-tuned-sim']")
        pcap = page.evaluate(TEXT, ["factory-vs-tuned-sim", ".dv-media-cap"]) or ""
        mode = page.evaluate("() => (document.querySelector('#example [data-panel=\"factory-vs-tuned-sim\"] .dv-media-compare') || {}).dataset?.mode")
        ctx.check("pid overlay: Factory vs tuned wipes media.json's factory clip (A) over the tuned clip (B), both sim renders, and sits on the same t",
                  sorted(x["src"] for x in pv) == sorted(urljoin(page.url, m["src"]) for m in (factory, tuned)) and "A: factory" in pcap and "B: tuned" in pcap
                  and "sim render" in pcap and mode == "wipe" and all(abs(x["t"] - (TM - x["t0"])) <= frame for x in pv),
                  {"videos": pv, "caption": pcap, "mode": mode})
        seek(page, 1.0)
        settled(ctx, page)
        before = clock(page)["t"]
        page.evaluate("() => document.querySelector('#example').clock.play()")
        page.wait_for_timeout(700)
        driver = clock(page)["driver"]
        page.wait_for_timeout(500)
        page.evaluate("() => document.querySelector('#example').clock.pause()")
        settled(ctx, page)
        after = clock(page)
        vids = page.evaluate(VIDEOS, D)
        offs = [round(abs(x["t"] - (after["t"] - x["t0"])), 4) for x in vids]
        ctx.check("pid play: 1.2 s of play advances the clock ≥ 0.8 s with the tuned replay (primary) driving t; after the pause all three videos sit on t − t0 within one frame",
                  after["t"] - before >= 0.8 and not after["playing"] and driver is not None and len(vids) == 3 and all(o <= frame for o in offs),
                  {"t": [round(before, 3), round(after["t"], 3)], "driver": driver, "offs": offs})
        ctx.shot(page, "pid-tuning-media-1440")

    # ---- the ladder per joint: gates and saturation
    with guard(ctx, "gates and saturation"):
        tr = page.evaluate("""() => [...document.querySelectorAll('#example [data-panel="gates-per-joint-factory-oracle"] .dv-tracker-row')].map((r) => ({
          joint: r.querySelector('.dv-tracker-label').textContent, cells: [...r.querySelectorAll('.dv-tracker-block')].map((b) => [b.dataset.state, (b.className.match(/dv-tone-(\\w+)/) || [])[1]]) }))""")
        want = {}
        for j in sorted(JOINTS, key=lambda r: r["order"]):
            want.setdefault(j["joint"], []).append([str(j["admissible"]).lower(), "good" if j["admissible"] else "bad"])
        ctx.check("pid gates: one tracker row per joint, one block per rung factory → oracle, each joints.json's admissible in its tone",
                  {r["joint"]: r["cells"] for r in tr} == want and len(tr) == 6, {"drawn": tr[:2], "want": dict(list(want.items())[:2])})
        bu = page.evaluate("""() => [...document.querySelectorAll('#example [data-panel="torque-saturation-by-rung"] .dv-bullet-row')].map((r) => ({
          label: r.querySelector('.dv-bullet-label').textContent, value: r.querySelector('.dv-bullet-value').textContent }))""")
        ctx.check("pid saturation: one bullet per rung in ladder order, each kpis.json's worst-joint saturation to 3 s.f.",
                  [b["label"] for b in bu] == [K[s]["title"] for s in RUNGS] and [num(b["value"]) for b in bu] == [sig3(v(K[s]["saturation"])) for s in RUNGS], bu)
        ctx.check("pid UR5e gains: the gain-vs-error scatter and the gains table hold joints.json's 24 rows; the lever its 4,340",
                  got["ur5e-gain-vs-error"] == len(JOINTS) and got["ur5e-gains-per-joint"] == len(JOINTS) and got["lever-pick-and-place-sim"] == len(STEP),
                  {k: got.get(k) for k in ("ur5e-gain-vs-error", "ur5e-gains-per-joint", "lever-pick-and-place-sim")})
        ctx.check("pid text: the top text panel says the replay is simulation, the videos are MuJoCo renders, and no real UR5e run exists",
                  all(s in page.evaluate("() => document.querySelector('#example .dd-panel-text').textContent") for s in ("simulation", "MuJoCo renders (sim), not a camera", "No real UR5e run")))

    rr = page.evaluate("""async () => { const b = document.querySelector('#example .dd-rerun'); const u = new URL('rerun/pid-tuning.rrd', location.href).href;
      const h = await fetch(u, { method: 'HEAD' }); return { button: !!b, ok: h.ok, size: Number(h.headers.get('content-length')) }; }""")
    ctx.check("pid Open in Rerun: the dashboard offers it (rerun: key) and rerun/pid-tuning.rrd is served (HEAD 200, > 0 bytes)", rr["button"] and rr["ok"] and rr["size"] > 0, rr)
    page.context.close()
    looks(ctx, path)


def looks(ctx, path):
    """Light and dark at 1440 and 390 px. The tiles (the dashboard's surface, PEP 0005 §5) follow the theme; the view
    inside a tile is transparent by design, so the theme is measured on the tile, not on <data-views>."""
    for dark in (False, True):
        for width, mobile in ((1440, False), (390, True)):
            p = ctx.page(path, width=width, height=1000 if width > 400 else 844, dark=dark, mobile=mobile)
            ready(p)
            m = p.evaluate("""() => { const g = document.querySelector('#example .dd-grid').getBoundingClientRect();
              const ps = [...document.querySelectorAll('#example .dd-panel')].map((e) => Math.round(e.getBoundingClientRect().width));
              const tile = getComputedStyle(document.querySelector('#example .dd-panel:not(.dd-panel-text)')).backgroundColor;
              return { scroll: document.scrollingElement.scrollWidth, grid: Math.round(g.width), widths: ps, tile }; }""")
            # rgb(…) in 0-255, or color(srgb …) in 0-1 (a color-mix() token resolves to the latter)
            ch = [float(x) for x in re.findall(r"[\d.]+", m["tile"].replace("srgb", ""))[:3]]
            lum = (sum(ch) / 3 if "color(" in m["tile"] else sum(ch) / (3 * 255)) if len(ch) == 3 else None
            tag = f"pid-tuning {'dark' if dark else 'light'}, {width} px"
            if width == 390:
                ctx.check(f"{tag}: one column and no sideways page scroll", m["scroll"] <= 390 and all(abs(w - m["grid"]) <= 1 for w in m["widths"]), m)
            else:
                ctx.check(f"{tag}: panels side by side, no sideways scroll", len(set(m["widths"])) > 1 and m["scroll"] <= width, m["widths"])
            ctx.check(f"{tag}: the tiles follow the theme", lum is not None and (lum < 0.3) == dark, m["tile"])
            p.evaluate("window.scrollTo(0, document.querySelector('#example').getBoundingClientRect().top + window.scrollY - 70)")
            p.wait_for_timeout(200)
            ctx.shot(p, f"pid-tuning-{'dark' if dark else 'light'}-{width}")
            p.context.close()
