"""Static mocks for PEP 0010 (robotics playback): one per stock dashboard, plus the deployment page.

Proposals to react to, not the product: no data-ui code draws these. Each panel says where its numbers come from:
- REAL: the 1-DOF rack's runs (/archive/datasets/bam_rig/rack_2026-10-2{3,4,5}, 1,001 npz) and its twin replay
  (sim2real dashboards/source/rack_replays.json), the rack's gates (sim2real dashboards/rack/gates.json), the RealSense
  frame stamps, BAM Reach's reach map.
- STAND-IN: the UR5e "real" is sim2real's perturbed MuJoCo stand-in (dashboards/arm/*.json), labelled as such.
- ILLUSTRATIVE: the gripper, depth and hyperspectral panels, which have no logged data yet.

Run (matplotlib comes from uv; read-only over the archive and the other repos):
    uv run --no-project --with matplotlib --with numpy python -I ~/data-ui/.wt/robotics-plan/docs/peps/0010-robotics-playback/make_mocks.py
Writes <this folder>/*.png and copies them to ~/data-ui/reports/media/robotics-plan/.
"""

from __future__ import annotations

import datetime as dt
import glob
import json
import math
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import patches  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

HERE = Path(__file__).resolve().parent
MEDIA = Path("~/data-ui/reports/media/robotics-plan")
ARCHIVE = Path("/archive/datasets/bam_rig")
SIM2REAL = Path("~/sim2real/dashboards")
REACH = Path("~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/bam_reach/out/workcell_analysis/reach_maps/reach-001-reach_map.reach.npz")

# WHY these values: data-ui's dark tokens (tokens.css) and the dashboard surface PEP 0005 §5 names; real and sim are
# data-ui's own validated slots 1 and 2 (PEP 0010 §7), target the muted ink, fail the crimson the templates set.
PAGE, CARD, BORDER, INK, MUTED, FAINT = "#111113", "#1c1c1f", "#2a2a2e", "#e6e6e8", "#8b9099", "#4a4d55"
REAL, SIM, TARGET = "#3987e5", "#d95926", "#8b9099"
GOOD, WARN, BAD = "#4cc38a", "#e5a93b", "#e0437f"
TONE = {"pass": (GOOD, "✓"), "partial": (WARN, "!"), "fail": (BAD, "✕"), "not_run": ("#3a3d44", "–")}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8.5, "text.color": INK, "axes.labelcolor": MUTED,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.edgecolor": BORDER, "axes.facecolor": CARD,
    "figure.facecolor": PAGE, "savefig.facecolor": PAGE, "axes.titlecolor": INK, "axes.titlesize": 9.5,
    "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.titlepad": 6, "legend.frameon": False,
    "legend.fontsize": 7.5, "grid.color": "#26272c", "grid.linewidth": 0.6,
})


# ------------------------------------------------------------------------------------------------ data


def rack_runs(can_id: int) -> list[dict]:
    """Every rack run of one motor across Oct 23-25: meta, arrays in display units (deg, deg/s, N·m, A, V, °C)."""
    out = []
    for meta_path in sorted(glob.glob(str(ARCHIVE / "rack_2026-10-2[345]" / "**" / "runs" / "*.json"), recursive=True)):
        try:
            meta = json.loads(Path(meta_path).read_text())
        except (OSError, ValueError):
            continue
        if meta.get("can_id") != can_id:
            continue
        npz_path = Path(meta_path).with_suffix(".npz")
        if not npz_path.exists():
            continue
        with np.load(npz_path) as a:
            if a["t"].size < 20:
                continue
            t = np.asarray(a["t"], float)
            run = {
                "id": str(npz_path.relative_to(ARCHIVE)), "kind": meta.get("kind") or "?", "t": t - t[0],
                "wall": float(a["wall"][0]), "q": np.degrees(a["q"]), "q_target": np.degrees(a["q_target"]),
                "qd": np.degrees(a["qd"]), "tau": np.asarray(a["tau"], float), "i_q": np.asarray(a["i_q"], float),
                "i_d": np.asarray(a["i_d"], float), "v_bus": np.asarray(a["voltage"], float),
                "temp": np.asarray(a["temp_c"], float), "mode": np.asarray(a["mode"], float),
                "fault": np.asarray(a["fault"], float),
            }
        # qdd is not logged: derived at full rate (PEP 0010 §4.3, basis: derived)
        run["qdd"] = np.gradient(run["qd"], run["t"]) if run["t"].size > 2 else np.zeros_like(run["qd"])
        out.append(run)
    return out


def decimate(runs: list[dict], channels: list[str], hz: float = 20.0) -> dict:
    """PEP 0010 §4.4: uniform time grid (w = 1) plus each run's argmin/argmax per channel (w = 0). Returns columns."""
    cols = defaultdict(list)
    for run in runs:
        t = run["t"]
        grid = np.arange(0, t[-1], 1 / hz)
        picks = np.unique(np.clip(np.searchsorted(t, grid), 0, t.size - 1))
        extremes = set()
        for ch in channels:
            v = run[ch]
            if np.isfinite(v).any():
                extremes.update([int(np.nanargmin(v)), int(np.nanargmax(v))])
        extremes -= set(picks.tolist())
        idx = np.concatenate([picks, np.array(sorted(extremes), int)])
        w = np.concatenate([np.ones(picks.size), np.zeros(len(extremes))])
        for ch in channels:
            cols[ch].append(run[ch][idx])
        cols["w"].append(w)
        cols["kind"].extend([run["kind"]] * idx.size)
        cols["run"].extend([run["id"]] * idx.size)
    return {k: (np.concatenate(v) if k not in ("kind", "run") else np.array(v)) for k, v in cols.items()}


def replay(motor: str) -> dict:
    doc = json.loads((SIM2REAL / "source" / "rack_replays.json").read_text())
    rec = next(r for r in doc["runs"] if r["motor"] == motor)
    s = {k: np.array([np.nan if x is None else x for x in v], float) if v is not None else None for k, v in rec["samples"].items()}
    for k in ("q_target", "q_real", "q_twin"):
        s[k] = np.degrees(s[k])
    return {"rec": rec, **s}


def table_rows(path: Path) -> list[dict]:
    return json.loads(path.read_text())["rows"]


# ------------------------------------------------------------------------------------------------ chrome


def page(title: str, subtitle: str, provenance: str):
    fig = plt.figure(figsize=(16, 10), dpi=100)
    fig.text(0.012, 0.972, "MOCK · PEP 0010 proposal, not built", fontsize=8, color="#f2b35b", weight="bold")
    fig.text(0.012, 0.948, title, fontsize=15, weight="bold")
    fig.text(0.012 + 0.0085 * len(title) + 0.03, 0.951, subtitle, fontsize=9.5, color=MUTED)
    fig.text(0.988, 0.972, provenance, fontsize=7.5, color=MUTED, ha="right")
    return fig


def rail(fig, groups, x=0.012, top=0.915, width=0.118, label="Filters"):
    """The data-ui rail: one group per facet; ● ○ radio (as: select), ☑ ☐ checkbox (as: values)."""
    ax = fig.add_axes([x, 0.03, width, top - 0.03])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(patches.FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.02", fc=CARD, ec=BORDER, lw=0.8, transform=ax.transAxes))
    y = 0.965
    ax.text(0.07, y, label, fontsize=10, weight="bold", va="top")
    y -= 0.045
    for name, kind, items in groups:
        ax.text(0.07, y, "▾ " + name, fontsize=8.5, weight="bold", va="top")
        y -= 0.033
        for text, on, count in items:
            mark = ("●" if on else "○") if kind == "radio" else ("☑" if on else "☐")
            ax.text(0.09, y, mark, fontsize=8.5, va="top", color=REAL if on else MUTED)
            ax.text(0.2, y, text, fontsize=8, va="top", color=INK if on else "#c4c6cc")
            if count is not None:
                ax.text(0.95, y, str(count), fontsize=7.5, va="top", ha="right", color=MUTED)
            y -= 0.03
        y -= 0.018
    ax.text(0.07, 0.012, "drag edge to resize · remembered", fontsize=6.5, color=FAINT, va="bottom")
    return ax


def card(ax, title, note=None, grid=True):
    ax.set_facecolor(CARD)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(title)
    if grid:
        ax.grid(axis="y")
    ax.tick_params(length=0, labelsize=7.5)
    if note:
        ax.text(1.0, 1.02, note, transform=ax.transAxes, ha="right", va="bottom", fontsize=6.8, color=MUTED)
    return ax


def boxed(fig, rect):
    """A card-shaped background behind a group of axes (the dashboard tile)."""
    bg = fig.add_axes(rect, zorder=-1)
    bg.axis("off")
    bg.add_patch(patches.FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.015", fc=CARD, ec=BORDER, lw=0.8, transform=bg.transAxes))
    return bg


def overlay(ax):
    """A transparent 2D axes over `ax` (a 3D axes cannot take axes-fraction text or lines)."""
    over = ax.figure.add_axes(ax.get_position(), zorder=9)
    over.set_xlim(0, 1)
    over.set_ylim(0, 1)
    over.axis("off")
    over.patch.set_alpha(0)
    return over


def legend_chips(ax, items, y=0.94, x=0.012):
    """items: (label, colour, dash), left to right inside the plot's top-left (data-ui's legend: click hides, Alt
    isolates). Drawn on a card-coloured pill so a line under it never reads as part of the legend."""
    if hasattr(ax, "get_zlim"):
        ax = overlay(ax)
    width = sum(0.06 + 0.0105 * len(label) for label, _, _ in items)
    ax.add_patch(patches.FancyBboxPatch((x - 0.006, y - 0.035), width + 0.004, 0.07, boxstyle="round,pad=0,rounding_size=0.02",
                                        transform=ax.transAxes, fc=CARD, ec=BORDER, lw=0.5, alpha=0.92, zorder=20, clip_on=False))
    for label, colour, dash in items:
        ax.plot([x, x + 0.03], [y] * 2, transform=ax.transAxes, color=colour, lw=2, ls=dash, clip_on=False, zorder=21)
        ax.text(x + 0.037, y, label, transform=ax.transAxes, fontsize=7.3, va="center", color="#c9cbd1", clip_on=False, zorder=21)
        x += 0.06 + 0.0105 * len(label)


def playback_bar(fig, rect, t, span, extra=""):
    ax = fig.add_axes(rect)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(patches.FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.18", fc=CARD, ec=BORDER, lw=0.8, transform=ax.transAxes))
    ax.text(0.012, 0.5, "|◀    ◀    ▶    ▶|    ⟳    1.00×", va="center", fontsize=9.5, color=INK)
    x0, x1 = 0.16, 0.86
    ax.plot([x0, x1], [0.5, 0.5], color=FAINT, lw=4, solid_capstyle="round")
    f = x0 + (x1 - x0) * t / span
    ax.plot([x0, f], [0.5, 0.5], color=REAL, lw=4, solid_capstyle="round")
    ax.plot([f], [0.5], "o", color=INK, ms=6)
    ax.text(0.875, 0.5, f"{t:.2f} / {span:.2f} s   {extra}", va="center", fontsize=8.5, color=MUTED)


def view_cube(ax, kind="helper", where=(0.86, 0.06), size=0.12, face=None):
    """The view cube's corner: three's ViewHelper (X/Y/Z balls; RGB = XYZ, the one red/green outside status).
    Drawn in its own square inset over `ax` (works over 2D and 3D axes alike)."""
    fig = ax.figure
    box = ax.get_position()
    w = size * box.width
    h = w * fig.get_figwidth() / fig.get_figheight()
    inset = fig.add_axes([box.x0 + where[0] * box.width, box.y0 + where[1] * box.height, w, h], zorder=10)
    inset.set_xlim(-1, 1)
    inset.set_ylim(-1, 1)
    inset.axis("off")
    inset.add_patch(patches.Circle((0, 0), 0.98, fc="#15161a", ec=BORDER, lw=0.6))
    for (dx, dy, c, lab) in [(0.72, -0.2, "#ff3653", "X"), (0.12, 0.72, "#2c8fff", "Z"), (-0.5, -0.5, "#8adb00", "Y")]:
        inset.plot([0, dx], [0, dy], color=c, lw=1.6)
        inset.add_patch(patches.Circle((dx, dy), 0.17, fc=c, ec="none"))
        inset.text(dx, dy, lab, fontsize=5.5, ha="center", va="center", color="#111", weight="bold")
    lab = "Fit · 3D" if face is None else f"{face} · Fit · 3D"
    inset.text(0, -1.12, lab, fontsize=6.5, ha="center", va="top", color=MUTED, clip_on=False)


def save(fig, name):
    path = HERE / name
    fig.savefig(path, dpi=100)
    plt.close(fig)
    # WHY a 256-colour palette: these PNGs are committed beside the PEP; a flat dark UI quantises without visible loss
    # at about a third of the bytes (Pillow comes with matplotlib)
    from PIL import Image
    Image.open(path).convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT).save(path, optimize=True)
    MEDIA.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, MEDIA / name)
    print("wrote", path)


def runs_table(ax, rows, cols, widths, title, note=None):
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.add_patch(patches.FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.03", fc=CARD, ec=BORDER, lw=0.8, transform=ax.transAxes))
    ax.text(0.012, 0.93, title, fontsize=9.5, weight="bold", va="top")
    if note:
        ax.text(0.988, 0.93, note, fontsize=7, color=MUTED, ha="right", va="top")
    n = len(rows) + 1
    step = 0.72 / n
    y = 0.78
    x = 0.012
    for c, w in zip(cols, widths):
        ax.text(x, y, c, fontsize=7.5, color=MUTED, weight="bold", va="center")
        x += w
    ax.plot([0.012, 0.988], [y - step / 2] * 2, color=BORDER, lw=0.8)
    for i, row in enumerate(rows):
        y -= step
        if i == 0:
            ax.add_patch(patches.Rectangle((0.006, y - step / 2), 0.988, step, fc="#23314a", ec="none"))
        x = 0.012
        for v, w in zip(row, widths):
            ax.text(x, y, str(v), fontsize=7.5, va="center", color=INK)
            x += w


# ------------------------------------------------------------------------------------------------ mocks


def mock_servo(can12: list[dict], cov: dict, rp: dict, counts: dict[int, int]):
    fig = page("Servo", "Use case: Robotics · Playback · 1-DOF rack, CAN 12 (one actuator + its encoder)",
               "REAL rack runs Oct 23-25 · twin = bam_rack_twin replay (sim2real rack_replays.json)")
    kinds = Counter(r["kind"] for r in can12)
    rail(fig, [
        ("Run", "radio", [("s09 · waypoints · 10-25", True, None), ("s08 · waypoints · 10-25", False, None), ("s07 · sine · 10-25", False, None), ("… 219 more", False, None)]),
        ("Servo", "radio", [("Any", False, sum(counts.values()))] + [(f"CAN {c}", c == 12, n) for c, n in sorted(counts.items())]),
        ("Show (situation)", "check", [("target", True, None), ("real", True, None), ("twin", True, None)]),
        ("Run kind", "check", [(k, True, n) for k, n in kinds.most_common(5)]),
    ])
    X0 = 0.142
    runs = sorted(can12, key=lambda r: -r["wall"])[:5]
    rows = [(dt.datetime.fromtimestamp(r["wall"]).strftime("%b %d %H:%M"), r["id"].split("/runs/")[0][-34:] + "/" + r["id"].split("/")[-1][:-4], r["kind"], f"{r['t'][-1]:.1f} s",
             "real · twin" if r["id"].endswith(rp["rec"]["run_path"].split("bam_rig/")[-1]) else "real") for r in runs]
    runs_table(fig.add_axes([X0, 0.775, 0.846, 0.155]), rows, ["Started", "Run", "Kind", "Duration", "Situations"], [0.1, 0.5, 0.11, 0.1, 0.15],
               f"Runs · newest first · {len(can12)} runs", f"click a row = pick that run (select: run) · {sum(counts.values()):,} runs on this rack (≥ 20 samples)")
    playback_bar(fig, [X0, 0.722, 0.846, 0.04], 2.4, rp["t"][-1], "· #t=2.40")
    t, tnow = rp["t"], 2.4

    ax = card(fig.add_axes([X0 + 0.025, 0.43, 0.5, 0.235]), "Angle q (deg)", "timeseries · series: situation")
    ax.plot(t, rp["q_target"], color=TARGET, ls=(0, (5, 4)), lw=1.3)
    ax.plot(t, rp["q_real"], color=REAL, lw=1.6)
    ax.plot(t, rp["q_twin"], color=SIM, lw=1.3)
    ax.axvline(tnow, color=INK, lw=0.8, alpha=0.7)
    legend_chips(ax, [("target", TARGET, (0, (3, 2))), ("real", REAL, "-"), ("twin", SIM, "-")])
    ax.set_xlim(0, t[-1])

    ax = card(fig.add_axes([X0 + 0.575, 0.43, 0.27, 0.235]), "Angle error e_q = target − x (mrad)", "diff_samples.json · difference(a, b)")
    for s, c in (("q_real", REAL), ("q_twin", SIM)):
        ax.plot(t, np.radians(rp["q_target"] - rp[s]) * 1e3, color=c, lw=1.2)
    ax.axhline(0, color=FAINT, lw=0.8)
    ax.axvline(tnow, color=INK, lw=0.8, alpha=0.7)
    legend_chips(ax, [("real", REAL, "-"), ("twin", SIM, "-")])
    ax.set_xlim(0, t[-1])

    # coverage: CAN 12's runs, decimated to 20 Hz + extremes (w)
    w = cov["w"]
    ax = card(fig.add_axes([X0 + 0.025, 0.07, 0.25, 0.27]), "q coverage · all CAN 12 runs", "time at angle (s) · sum(w)/20 Hz")
    edges = np.linspace(np.nanmin(cov["q"]), np.nanmax(cov["q"]), 61)
    h, _ = np.histogram(cov["q"], bins=edges, weights=w)
    ax.stairs(h / 20.0, edges, color=REAL, lw=1.5, fill=True, alpha=0.25)
    ax.stairs(h / 20.0, edges, color=REAL, lw=1.5)
    ax.axvline(np.nanmin(cov["q"]), color=INK, lw=0.8, ls=":")
    ax.axvline(np.nanmax(cov["q"]), color=INK, lw=0.8, ls=":")
    ax.text(0.02, 0.92, f"min {np.nanmin(cov['q']):.1f}°  max {np.nanmax(cov['q']):.1f}° (exact: w = 0 rows)", transform=ax.transAxes, fontsize=6.8, color=MUTED)
    ax.set_xlabel("q (deg)")

    ax = card(fig.add_axes([X0 + 0.31, 0.07, 0.25, 0.27]), "qd coverage by run kind", "box · extent: min-max")
    ks = [k for k, _ in Counter(cov["kind"]).most_common(5)]
    data = [cov["qd"][cov["kind"] == k] for k in ks]
    bp = ax.boxplot(data, whis=(0, 100), widths=0.5, patch_artist=True, showfliers=False)
    for b in bp["boxes"]:
        b.set(facecolor=REAL + "55", edgecolor=REAL)
    for part in ("whiskers", "caps", "medians"):
        for line in bp[part]:
            line.set(color=REAL if part != "medians" else INK, lw=1)
    ax.set_xticks(range(1, len(ks) + 1), ks)
    ax.set_ylabel("qd (deg/s)")

    ax = card(fig.add_axes([X0 + 0.595, 0.07, 0.25, 0.27]), "Phase space q × qd", "2D bins · sum(w) · real ramp", grid=False)
    ramp = LinearSegmentedColormap.from_list("real", [CARD, "#1d3f6e", REAL, "#cfe2fb"])
    ok = np.isfinite(cov["q"]) & np.isfinite(cov["qd"])
    H, xe, ye = np.histogram2d(cov["q"][ok], cov["qd"][ok], bins=70, weights=w[ok])
    ax.pcolormesh(xe, ye, np.log1p(H.T), cmap=ramp)
    ax.set_xlabel("q (deg)")
    ax.set_ylabel("qd (deg/s)")
    fig.text(X0 + 0.025, 0.375, "COVERAGE · reads coverage_samples.json (unlinked: a run pick never empties it) · decimated 20 Hz + each run's extremes, "
             f"{len(w):,} rows ≤ 150k budget", fontsize=7.5, color=MUTED)
    save(fig, "servo.png")


def mock_driver(can12: list[dict], cov: dict, rp: dict):
    fig = page("BLDC driver", "Use case: Robotics · Playback · moteus board on CAN 12 (same npz, driver channels)",
               "REAL rack runs Oct 23-25 · torque twin = bam_rack_twin replay")
    rail(fig, [
        ("Run", "radio", [("s09 · waypoints · 10-25", True, None), ("… 221 more", False, None)]),
        ("Driver", "radio", [("CAN 12 · moteus-c1", True, len(can12)), ("CAN 13 · moteus-c1", False, 255), ("CAN 14 · moteus-c1", False, 58)]),
        ("Run kind", "check", [(k, True, n) for k, n in Counter(r["kind"] for r in can12).most_common(4)]),
    ])
    X0 = 0.142
    run = next(r for r in can12 if r["id"].endswith(rp["rec"]["run_path"].split("bam_rig/")[-1]))
    t = run["t"]
    playback_bar(fig, [X0, 0.885, 0.846, 0.04], 2.4, t[-1])
    panels = [("q-axis current i_q (A)", run["i_q"], REAL), ("d-axis current i_d (A)", run["i_d"], REAL),
              ("Bus voltage v_bus (V)", run["v_bus"], REAL), ("Winding temperature (°C)", run["temp"], REAL)]
    for i, (title, v, c) in enumerate(panels):
        ax = card(fig.add_axes([X0 + 0.025 + (i % 2) * 0.43, 0.69 - (i // 2) * 0.19, 0.39, 0.14]), title, "timeseries · real only (no twin current)" if i == 0 else None)
        ax.plot(t, v, color=c, lw=1.2)
        ax.axvline(2.4, color=INK, lw=0.8, alpha=0.7)
        ax.set_xlim(0, t[-1])
    ax = card(fig.add_axes([X0 + 0.025, 0.4, 0.82, 0.028]), "Mode · fault", "levels strip (lane/live) · events.json", grid=False)
    ax.set_yticks([])
    mode = run["mode"]
    strip = LinearSegmentedColormap.from_list("mode", [FAINT, REAL])
    ax.imshow((mode == 10)[None, :].astype(float), aspect="auto", cmap=strip, extent=[t[0], t[-1], 0, 1], vmin=0, vmax=1, interpolation="nearest")
    ax.axvline(2.4, color=INK, lw=0.8, alpha=0.7)
    ax.set_xlim(0, t[-1])
    ax.text(1.0, -1.3, f"blue = mode 10 (position) · {np.mean(mode == 10) * 100:.0f} % of the run · faults {int((run['fault'] != 0).sum())}", transform=ax.transAxes, ha="right", fontsize=7, color=MUTED)
    w = cov["w"]
    ax = card(fig.add_axes([X0 + 0.025, 0.07, 0.25, 0.25]), "i_q coverage · all CAN 12 runs", "sum(w)")
    edges = np.linspace(np.nanpercentile(cov["i_q"], 0.1), np.nanpercentile(cov["i_q"], 99.9), 61)
    h, _ = np.histogram(cov["i_q"], bins=edges, weights=w)
    ax.stairs(h / 20, edges, color=REAL, lw=1.5, fill=True, alpha=0.25)
    ax.set_xlabel("i_q (A)")
    ax = card(fig.add_axes([X0 + 0.31, 0.07, 0.25, 0.25]), "Operating map i_q × qd", "2D bins · sum(w)", grid=False)
    ramp = LinearSegmentedColormap.from_list("real", [CARD, "#1d3f6e", REAL, "#cfe2fb"])
    ok = np.isfinite(cov["i_q"]) & np.isfinite(cov["qd"])
    H, xe, ye = np.histogram2d(cov["qd"][ok], cov["i_q"][ok], bins=70, weights=w[ok], range=[np.nanpercentile(cov["qd"], [0.2, 99.8]), np.nanpercentile(cov["i_q"], [0.2, 99.8])])
    ax.pcolormesh(xe, ye, np.log1p(H.T), cmap=ramp)
    ax.set_xlabel("qd (deg/s)")
    ax.set_ylabel("i_q (A)")
    ax = card(fig.add_axes([X0 + 0.595, 0.07, 0.25, 0.25]), "Temperature by run kind", "box · extent: min-max")
    ks = [k for k, _ in Counter(cov["kind"]).most_common(5)]
    bp = ax.boxplot([cov["temp"][cov["kind"] == k] for k in ks], whis=(0, 100), widths=0.5, patch_artist=True, showfliers=False)
    for b in bp["boxes"]:
        b.set(facecolor=REAL + "55", edgecolor=REAL)
    for part in ("whiskers", "caps", "medians"):
        for line in bp[part]:
            line.set(color=REAL if part != "medians" else INK, lw=1)
    ax.set_xticks(range(1, len(ks) + 1), ks)
    fig.text(X0 + 0.025, 0.36, "COVERAGE · the same coverage_samples.json as Servo, driver columns", fontsize=7.5, color=MUTED)
    save(fig, "bldc-driver.png")


def mock_camera():
    fig = page("Camera", "Use case: Robotics · Playback · RGB · RGBD · hyperspectral",
               "REAL: RealSense 218622274411 on the rack (session_01a) · depth and hyperspectral: none captured yet")
    rail(fig, [
        ("Camera", "radio", [("RealSense 218622274411", True, 3), ("RealSense 218622276036", False, 3)]),
        ("Stream", "check", [("rgb", True, None), ("depth", True, None), ("band", False, None)]),
        ("Band (nm)", "radio", [("— no hyperspectral", False, None)]),
    ])
    X0 = 0.142
    playback_bar(fig, [X0, 0.885, 0.846, 0.04], 12.0, 36.0)
    still = next(iter(sorted((SIM2REAL / "rack" / "media").glob("*.jpg"))), None)
    ax = fig.add_axes([X0 + 0.01, 0.43, 0.41, 0.42])
    ax.set_title("RGB · real camera (video.primary)")
    ax.axis("off")
    if still is not None:
        ax.imshow(plt.imread(still))
    ax.text(0.01, -0.04, "media.json · kind: rgb · t0 = −0.300 s · basis real-camera · its frames drive the clock (video.primary)", transform=ax.transAxes, fontsize=7, color=MUTED)
    for i, (title, body) in enumerate([("Depth · RGBD", "No depth captured yet.\nThis card plays the producer's colourised depth video\n(media.json kind: depth) on the same clock."),
                                       ("Hyperspectral band", "No hyperspectral capture yet.\nA band image picked by the rail's band_nm slider,\nwith the spectrum of the hovered pixel beside it.")]):
        ax = fig.add_axes([X0 + 0.45 + i * 0.205, 0.43, 0.19, 0.42])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        ax.add_patch(patches.FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.03", fc=CARD, ec=BORDER, lw=0.8, ls="--"))
        ax.text(0.05, 0.94, title, fontsize=9.5, weight="bold", va="top")
        ax.text(0.5, 0.5, "—", fontsize=26, color=FAINT, ha="center", va="center")
        ax.text(0.05, 0.2, body, fontsize=7.2, color=MUTED, va="top")
    stamps = []
    for npz in sorted(glob.glob(str(ARCHIVE / "rack_2026-10-23" / "session_0*" / "cameras" / "cam_218622274411.npz"))):
        try:   # WHY: some session camera files are corrupt (sim-to-real README); a bad one is skipped, not faked
            with np.load(npz) as a:
                hw = np.asarray(a["hw_ms"], float)
        except (OSError, ValueError, KeyError, __import__("zipfile").BadZipFile):
            continue
        stamps.append((Path(npz).parts[-3], np.diff(hw)))
        if len(stamps) == 6:
            break
    ax = card(fig.add_axes([X0 + 0.025, 0.07, 0.38, 0.27]), "Frame interval (ms) · 30 fps nominal", "real hw_ms stamps · histogram")
    allv = np.concatenate([d for _, d in stamps]) if stamps else np.array([33.3])
    allv = allv[(allv > 0) & (allv < 200)]
    ax.hist(allv, bins=np.linspace(0, 120, 61), color=REAL, alpha=0.8)
    ax.axvline(1000 / 30, color=INK, lw=0.8, ls=":")
    ax.set_yscale("log")
    ax.set_xlabel("interval (ms)")
    ax = card(fig.add_axes([X0 + 0.46, 0.07, 0.38, 0.27]), "Dropped frames per session", "intervals > 1.5 × 33.3 ms")
    names = [n for n, _ in stamps]
    drops = [int((d > 50).sum()) for _, d in stamps]
    ax.bar(range(len(names)), drops, color=REAL, width=0.6)
    ax.set_xticks(range(len(names)), names, rotation=0)
    save(fig, "camera.png")


def mock_arm():
    eef = table_rows(SIM2REAL / "arm" / "samples_eef.json")
    scene = [r for r in table_rows(SIM2REAL / "arm" / "scene.json") if r["situation"] == "real"]
    servo = table_rows(SIM2REAL / "arm" / "samples_servo.json")
    by = defaultdict(list)
    for r in eef:
        if r.get("x_mm") is not None:
            by[r["situation"]].append(r)
    P = {s: (np.array([r["t"] for r in rs]), np.array([[r["x_mm"], r["y_mm"], r["z_mm"]] for r in rs])) for s, rs in by.items()}
    fig = page("Robot arm", "Use case: Robotics · Playback · UR5e, 6 DOF (works for 2 to 7+)",
               "STAND-IN: sim2real's perturbed MuJoCo UR5e (no real arm run exists) · reach map: BAM Reach")
    rail(fig, [
        ("Joint", "radio", [("Tool (EEF)", True, None), ("J1 shoulder pan", False, None), ("J2 shoulder lift", False, None), ("J3 elbow", False, None), ("J4 wrist 1", False, None), ("J5 wrist 2", False, None), ("J6 wrist 3", False, None)]),
        ("Show (situation)", "check", [("target", True, None), ("real", True, None), ("real B", True, None), ("twin", True, None)]),
    ])
    X0 = 0.142
    playback_bar(fig, [X0, 0.885, 0.846, 0.04], 4.4, 7.9, "· decay 0.6 s")
    tnow, decay = 4.4, 0.6
    style = {"target": (TARGET, (0, (5, 4)), 1.4), "real": (REAL, "-", 2.4), "real B": (REAL, (0, (8, 4)), 1.5), "twin": (SIM, "-", 1.8)}

    ax3 = fig.add_axes([X0 + 0.005, 0.475, 0.44, 0.39], projection="3d")
    ax3.set_facecolor(CARD)
    ax3.set_title("trajectory3d · 3D · show: trail, decay 0.6 s · compare real → target")
    for pane in (ax3.xaxis, ax3.yaxis, ax3.zaxis):
        pane.set_pane_color((0.11, 0.11, 0.12, 1))
        pane._axinfo["grid"]["color"] = (0.2, 0.2, 0.22, 1)
    for s_name, (t, p) in P.items():
        c, ls, lw = style.get(s_name, (MUTED, "-", 1))
        ax3.plot(p[:, 0], p[:, 1], p[:, 2], color=c, lw=0.8, ls=ls, alpha=0.3)            # the whole path, faint
        k = (t >= tnow - decay) & (t <= tnow)
        seg = p[k]
        for i in range(len(seg) - 1):                                                     # the contrail: fades with age
            ax3.plot(seg[i:i + 2, 0], seg[i:i + 2, 1], seg[i:i + 2, 2], color=c, lw=lw, ls=ls, alpha=0.2 + 0.8 * i / max(1, len(seg) - 2))
        if seg.size:
            ax3.scatter(*seg[-1], color=c, s=30, depthshade=False)
    tr, pr = P["real"]
    tt, pt = P["target"]
    stride = max(1, len(tr) // 20)                                                        # density 20 (traj_compare's rule)
    for i in range(0, len(tr), stride):                                                   # compare: real(t) → target(t)
        if tr[i] > tnow:
            break
        j = int(np.argmin(np.abs(tt - tr[i])))
        ax3.quiver(*pr[i], *(pt[j] - pr[i]), color=REAL, lw=1.0, arrow_length_ratio=0.18, alpha=0.95)
    # display mode frames-z on real: its tool Z axis at the same density (wrist_3's orientation, wxyz)
    for r in scene[::max(1, len(scene) // 20)]:
        w_, x_, y_, z_ = r["wrist_3_link_qw"], r["wrist_3_link_qx"], r["wrist_3_link_qy"], r["wrist_3_link_qz"]
        zaxis = np.array([2 * (x_ * z_ + w_ * y_), 2 * (y_ * z_ - w_ * x_), 1 - 2 * (x_ * x_ + y_ * y_)])
        o = np.array([r["px"], r["py"], r["pz"]]) * 1000
        ax3.plot(*np.stack([o, o + 45 * zaxis]).T, color=REAL, lw=1.1, alpha=0.8)
    row = min(scene, key=lambda r: abs(r["t"] - tnow))
    js = np.array([[row[f"{l}_x"], row[f"{l}_y"], row[f"{l}_z"]] for l in ("base", "shoulder_link", "upper_arm_link", "forearm_link", "wrist_1_link", "wrist_2_link", "wrist_3_link")]) * 1000
    ax3.plot(js[:, 0], js[:, 1], js[:, 2], "-o", color=REAL, lw=4, ms=4, alpha=0.45)
    pts = np.vstack([p for _, p in P.values()] + [js])
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    ax3.set_xlim(lo[0], hi[0])
    ax3.set_ylim(lo[1], hi[1])
    ax3.set_zlim(lo[2], hi[2])
    ax3.set_box_aspect(hi - lo)                                                           # equal scale on all three axes
    ax3.view_init(elev=22, azim=-62)
    ax3.tick_params(labelsize=6.5)
    ax3.set_xlabel("x (mm)", fontsize=7)
    ax3.set_ylabel("y (mm)", fontsize=7)
    ax3.set_zlabel("z (mm)", fontsize=7)
    view_cube(ax3, where=(0.87, 0.74), size=0.1)
    legend_chips(ax3, [("target", TARGET, (0, (3, 2))), ("real", REAL, "-"), ("real B", REAL, (0, (6, 3))), ("twin", SIM, "-")], y=0.95, x=0.02)
    # the per-trajectory menu (worded; show/hide stays on the rail): display mode, robot colour and opacity
    menu = fig.add_axes([X0 + 0.015, 0.385, 0.42, 0.085])
    menu.set_xlim(0, 1)
    menu.set_ylim(0, 0.2)
    menu.axis("off")
    menu.add_patch(patches.FancyBboxPatch((0.0, 0.0), 1.0, 0.2, boxstyle="round,pad=0,rounding_size=0.01", fc="#141518", ec=BORDER, lw=0.6))
    lines = [("real ▾", "Line ☑   Points ☐   Frames: Z only ☑   Robot ● 100 %", REAL),
             ("real B ▾", "Line ☑   Points ☐   Frames ☐          Robot off", REAL),
             ("twin ▾", "Line ☑   Points ☐   Frames ☐          Robot ● 50 %", SIM),
             ("", "Density ━━━●━━━ 20      Compare real → target ×1      robot drawn as its stick fallback here", MUTED)]
    for k, (who, what, colour) in enumerate(lines):
        menu.text(0.02, 0.165 - k * 0.042, who, fontsize=6.8, color=colour, weight="bold", va="center")
        menu.text(0.12, 0.165 - k * 0.042, what, fontsize=6.8, color="#c9cbd1", va="center")

    ax = card(fig.add_axes([X0 + 0.5, 0.43, 0.345, 0.42]), "trajectory3d · TOP (ortho, frame: base) · show: all", "the same card, cube → TOP", grid=False)
    for s, (t, p) in P.items():
        c, ls, lw = style.get(s, (MUTED, "-", 1))
        ax.plot(p[:, 0], p[:, 1], color=c, ls=ls, lw=lw)
    for i in range(0, len(tr), max(1, len(tr) // 20)):
        j = int(np.argmin(np.abs(tt - tr[i])))
        ax.annotate("", xy=pt[j, :2], xytext=pr[i, :2], arrowprops=dict(arrowstyle="-|>", color=REAL, lw=0.8, shrinkA=0, shrinkB=0, mutation_scale=7))
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True)
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    view_cube(ax, where=(0.84, 0.04), size=0.12, face="TOP")
    ax.text(0.01, 0.01, "density 20 · arrows real(t) → target(t), time-matched", transform=ax.transAxes, fontsize=6.5, color=MUTED)

    ax = card(fig.add_axes([X0 + 0.025, 0.07, 0.25, 0.25]), "EEF error |target − x| (mm)", "diff_poses.json · err_mm")
    for s in ("real", "real B", "twin"):
        rs = [r for r in eef if r["situation"] == s and r.get("err_mm") is not None]
        c, ls, lw = style[s]
        ax.plot([r["t"] for r in rs], [r["err_mm"] for r in rs], color=c, ls=ls, lw=1.1)
    ax.axvline(tnow, color=INK, lw=0.8, alpha=0.7)
    legend_chips(ax, [("real", REAL, "-"), ("real B", REAL, (0, (6, 3))), ("twin", SIM, "-")])

    ax = card(fig.add_axes([X0 + 0.31, 0.07, 0.25, 0.25]), "Joint error e_q, J3 elbow (mrad)", "rail pick · diff_samples.json")
    tgt = {r["t"]: r["q_deg"] for r in servo if r["device"] == "J3 elbow" and r["situation"] == "target" and r.get("q_deg") is not None}
    for s in ("real", "twin"):
        rs = [r for r in servo if r["device"] == "J3 elbow" and r["situation"] == s and r.get("q_deg") is not None and r["t"] in tgt]
        ax.plot([r["t"] for r in rs], [math.radians(tgt[r["t"]] - r["q_deg"]) * 1e3 for r in rs], color=style[s][0], lw=1.1)
    ax.axhline(0, color=FAINT, lw=0.8)
    ax.axvline(tnow, color=INK, lw=0.8, alpha=0.7)

    ax = card(fig.add_axes([X0 + 0.595, 0.07, 0.25, 0.25]), "voxels · slice z ≈ 143 mm", "reach fraction · BAM Reach grid.json", grid=False)
    with np.load(REACH) as a:
        pos = a["positions"]
        valid = a["ik_success"] & a["fk_checked"] & a["fk_success"] & a["consistent"] & ~(a["collision_checked"] & a["collisions"])
    score = valid.mean(axis=1)
    zs = np.round(pos[:, 2], 4)
    zk = np.unique(zs)[np.argmin(np.abs(np.unique(zs) - 0.1429))]
    sel = zs == zk
    ramp = LinearSegmentedColormap.from_list("seq", [CARD, "#3b3f48", "#9aa3b2", "#f2f3f5"])
    sc = ax.scatter(pos[sel, 0] * 1000, pos[sel, 1] * 1000, c=score[sel], cmap=ramp, marker="s", s=95, vmin=0, vmax=1, edgecolors="none")
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    cb = fig.colorbar(sc, ax=ax, fraction=0.04, pad=0.02)
    cb.ax.tick_params(labelsize=6, colors=MUTED)
    cb.outline.set_visible(False)
    ax.text(0.01, 0.01, "slice ◀ ▶ one cell · red→green only in the gates layer", transform=ax.transAxes, fontsize=6.3, color=MUTED)
    save(fig, "arm.png")


def mock_arm_gripper():
    eef = table_rows(SIM2REAL / "arm" / "samples_eef.json")
    fig = page("Arm + gripper", "Use case: Robotics · Playback · the arm's panels + the gripper's",
               "STAND-IN arm (sim2real MuJoCo UR5e) · ILLUSTRATIVE gripper: no gripper has been logged yet")
    rail(fig, [
        ("Device", "radio", [("Tool (EEF)", False, None), ("J1 … J6", False, None), ("Gripper", True, None)]),
        ("Show (situation)", "check", [("target", True, None), ("real", True, None), ("twin", True, None)]),
        ("Event", "check", [("grasp", True, None), ("release", True, None), ("contact", True, None)]),
    ])
    X0 = 0.142
    playback_bar(fig, [X0, 0.885, 0.846, 0.04], 4.4, 7.9)
    ax = card(fig.add_axes([X0 + 0.025, 0.5, 0.39, 0.33]), "EEF z (mm) · arm, condensed", "trajectory3d sits here at full size (see arm.png)")
    for s, c, ls in (("target", TARGET, (0, (5, 4))), ("real", REAL, "-"), ("twin", SIM, "-")):
        rs = [r for r in eef if r["situation"] == s and r.get("z_mm") is not None]
        ax.plot([r["t"] for r in rs], [r["z_mm"] for r in rs], color=c, ls=ls, lw=1.3)
    ev = [(1.6, "contact"), (1.9, "grasp"), (5.2, "release")]
    for k, (tev, lab) in enumerate(ev):
        ax.axvline(tev, color=MUTED, lw=0.8, ls=":")
        ax.text(tev, 0.86 - 0.07 * k, " " + lab, transform=ax.get_xaxis_transform(), fontsize=6.5, color=MUTED, va="top")
    legend_chips(ax, [("target", TARGET, (0, (3, 2))), ("real", REAL, "-"), ("twin", SIM, "-")])
    ax.axvline(4.4, color=INK, lw=0.8, alpha=0.7)
    t = np.linspace(0, 7.9, 400)
    width_t = np.where(t < 1.6, 85, np.where(t < 1.9, 85 - (t - 1.6) / 0.3 * 47, np.where(t < 5.2, 38, np.minimum(85, 38 + (t - 5.2) / 0.4 * 47))))
    force_t = np.where((t > 1.9) & (t < 5.2), 22 + 1.5 * np.sin(6 * t), 0)
    for i, (title, tgt_v, real_v, unit) in enumerate([("Gripper width (mm)", width_t, width_t + np.where(t > 1.9, 0.8, 0), "mm"),
                                                       ("Grip force (N)", force_t * 0 + np.where((t > 1.9) & (t < 5.2), 20, 0), force_t, "N")]):
        ax = card(fig.add_axes([X0 + 0.455 + 0 * i, 0.5 - i * 0.0, 0.39, 0.33]) if i == 0 else fig.add_axes([X0 + 0.455, 0.1, 0.39, 0.3]), title, "ILLUSTRATIVE")
        ax.plot(t, tgt_v, color=TARGET, ls=(0, (5, 4)), lw=1.2)
        ax.plot(t, real_v, color=REAL, lw=1.5)
        for tev, lab in ev:
            ax.axvline(tev, color=MUTED, lw=0.8, ls=":")
        ax.axvline(4.4, color=INK, lw=0.8, alpha=0.7)
    ax = card(fig.add_axes([X0 + 0.025, 0.1, 0.39, 0.3]), "Grip width at grasp · coverage", "ILLUSTRATIVE · histogram, sum(w)")
    rng = np.random.default_rng(3)
    ax.hist(rng.normal(38, 4, 300), bins=30, color=REAL, alpha=0.8)
    ax.set_xlabel("width at grasp (mm)")
    save(fig, "arm-gripper.png")


def mock_deployment(all_runs: dict[int, list[dict]], cov12: dict):
    fig = page("Deployment · 1-DOF rack", "one dashboard: runs newest first · coverage · (later) the gates overlay",
               "REAL: 1,001 rack runs Oct 23-25 · gates: sim2real rack gates.json (acceptance T1-T11)")
    # the app rail (data-ui <data-rail>, wide style): deployments as destinations
    ax = fig.add_axes([0.0, 0.03, 0.105, 0.885])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.add_patch(patches.Rectangle((0, 0), 1, 1, fc="#16171a", ec=BORDER, lw=0.8))
    ax.text(0.1, 0.96, "sim2real", fontsize=10.5, weight="bold", va="top")
    ax.text(0.1, 0.91, "DEPLOYMENTS", fontsize=7, color=MUTED, va="top")
    for i, (name, on, n) in enumerate([("1-DOF rack", True, "1,001"), ("UR5e cell", False, "stand-in"), ("Sensor suite", False, "stand-in")]):
        y = 0.87 - i * 0.05
        if on:
            ax.add_patch(patches.FancyBboxPatch((0.05, y - 0.03), 0.9, 0.04, boxstyle="round,pad=0,rounding_size=0.02", fc="#23314a", ec="none"))
        ax.text(0.1, y - 0.01, name, fontsize=8.5, va="center", color=INK)
        ax.text(0.92, y - 0.01, n, fontsize=6.5, va="center", ha="right", color=MUTED)
    kinds = Counter(r["kind"] for runs in all_runs.values() for r in runs)
    rail(fig, [
        ("Device", "radio", [("Any", False, sum(len(v) for v in all_runs.values()))] + [(f"CAN {c}", c == 12, len(all_runs[c])) for c in (1, 4, 11, 12, 13, 14, 15, 21)]),
        ("Run kind", "check", [(k, k == "waypoints", n) for k, n in kinds.most_common(7)]),
    ], x=0.112, width=0.105)
    X0 = 0.225
    newest = sorted((r for runs in all_runs.values() for r in runs), key=lambda r: -r["wall"])[:6]
    def session(run_id):
        day, *rest = run_id.split("/runs/")[0].split("/")
        return f"{day[-5:]} · " + "/".join(rest)[-34:]
    rows = [(dt.datetime.fromtimestamp(r["wall"]).strftime("%b %d %H:%M"), session(r["id"]), r["id"].split("/")[-1][:-4], r["kind"], f"{r['t'][-1]:.1f} s") for r in newest]
    runs_table(fig.add_axes([X0, 0.715, 0.765, 0.2]), rows, ["Started", "Session", "Run", "Kind", "Duration"], [0.12, 0.33, 0.25, 0.11, 0.1],
               "Runs · newest first", "a click picks the run → playback (P3: loads runs/<run>.json)")
    way12 = [r for r in all_runs[12] if r["kind"] == "waypoints"]
    ax = card(fig.add_axes([X0 + 0.02, 0.38, 0.35, 0.27]), f"q(t) · {len(way12)} CAN 12 waypoint runs at opacity auto", "max(1/n, 0.04) · real family")
    alpha = max(1 / len(way12), 0.04)
    for r in way12:
        ax.plot(r["t"], r["q"], color=REAL, lw=0.8, alpha=alpha)
    ax.set_xlim(0, 12)
    ax.set_xlabel("t (s)")
    ax.set_ylabel("q (deg)")
    devs = [1, 4, 11, 12, 13, 14, 15, 21]
    nway = sum(1 for c in devs for r in all_runs[c] if r["kind"] == "waypoints")
    ax = card(fig.add_axes([X0 + 0.41, 0.38, 0.355, 0.27]), f"q range per device · {nway} waypoint runs", "box · extent: min-max · x: device")
    data = [np.concatenate([r["q"] for r in all_runs[c] if r["kind"] == "waypoints"]) for c in devs]
    bp = ax.boxplot(data, whis=(0, 100), widths=0.5, patch_artist=True, showfliers=False)
    for b in bp["boxes"]:
        b.set(facecolor=REAL + "55", edgecolor=REAL)
    for part in ("whiskers", "caps", "medians"):
        for line in bp[part]:
            line.set(color=REAL if part != "medians" else INK, lw=1)
    ax.set_xticks(range(1, 9), [f"CAN {c}" for c in devs])
    ax.set_ylabel("q (deg)")
    # the gates overlay (P5): devices × gates, glyph + word, fail in crimson
    gates = table_rows(SIM2REAL / "rack" / "gates.json")
    order = ["CAN 14", "CAN 15", "CAN 1", "CAN 4", "CAN 11", "CAN 12", "CAN 13", "CAN 21"]
    cols = sorted({(r["gate"], r.get("gate_name") or "") for r in gates if r["device"] in order}, key=lambda g: int(g[0][1:]))
    status = {(r["device"], r["gate"]): r["status"] for r in gates}
    ax = fig.add_axes([X0, 0.035, 0.765, 0.29])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.add_patch(patches.FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.02", fc=CARD, ec="#f2b35b", lw=1, ls="--"))
    ax.text(0.012, 0.95, "Gate matrix · Playback + Diagnostics/Gates layer (P5: an overlay .base over the same data)", fontsize=9.5, weight="bold", va="top")
    ax.text(0.988, 0.95, "tracker · column: gate · a cell opens its evidence", fontsize=7, color=MUTED, ha="right", va="top")
    gx0, gw = 0.11, 0.875 / len(cols)
    for j, (g, name) in enumerate(cols):
        ax.text(gx0 + gw * (j + 0.5), 0.8, f"{g}\n{name[:12]}", fontsize=6.3, ha="center", va="center", color=MUTED)
    for i, dev in enumerate(order):
        y = 0.66 - i * 0.078
        ax.text(0.012, y, dev, fontsize=7.8, va="center")
        for j, (g, _) in enumerate(cols):
            st = status.get((dev, g), "not_run")
            colour, glyph = TONE.get(st, TONE["not_run"])
            ax.add_patch(patches.FancyBboxPatch((gx0 + gw * j + 0.003, y - 0.03), gw - 0.006, 0.06, boxstyle="round,pad=0,rounding_size=0.006", fc=colour, ec="none", alpha=0.9 if st != "not_run" else 1))
            ax.text(gx0 + gw * (j + 0.5), y, glyph, fontsize=8, ha="center", va="center", color="#101012" if st != "not_run" else MUTED, weight="bold")
    ax.text(0.11, 0.02, "✓ pass   ! partial   ✕ fail   – not run      glyph + word always; fail is crimson, never the sim orange", fontsize=7, color=MUTED)
    save(fig, "deployment.png")


def main() -> int:
    all_runs = {c: rack_runs(c) for c in (1, 4, 11, 12, 13, 14, 15, 21)}
    print({c: len(v) for c, v in all_runs.items()}, "runs")
    can12 = all_runs[12]
    cov = decimate(can12, ["q", "qd", "qdd", "tau", "i_q", "temp"])
    print("coverage rows", cov["w"].size, "w=1", int(cov["w"].sum()))
    rp = replay("CAN 12")
    mock_servo(can12, cov, rp, {c: len(v) for c, v in all_runs.items()})
    mock_driver(can12, cov, rp)
    mock_camera()
    mock_arm()
    mock_arm_gripper()
    mock_deployment(all_runs, cov)
    return 0


if __name__ == "__main__":
    sys.exit(main())
