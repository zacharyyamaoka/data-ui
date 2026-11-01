"""Draw the Filters case's line icons and dimension diagrams, in McMaster-Carr's line style (one stroke weight, no
fill, no colour: the rail draws a .svg in the text colour, so one file reads in light and dark).

    python3 gallery/examples/filters-gallery/source/icons.py     # rewrites ../icons/*.svg and ../diagrams/*.svg

icons/form-<value>.svg       one per robotparts actuator form (hobby_servo, integrated_actuator, direct_drive,
                             bare_gearmotor, wheel_hub), for the `gallery` and `picture-list` facets
icons/drivetrain-<value>.svg one per drivetrain (geared, direct_drive, motor)
diagrams/od.svg, length.svg  which dimension a facet measures: the outer diameter across an actuator's face, the axial
                             length along its side (McMaster's "Head Diameter" and "Thread Pitch" drawings)
"""

from __future__ import annotations

import math
import pathlib

CASE = pathlib.Path(__file__).resolve().parent.parent
STROKE = 'fill="none" stroke="#000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
THIN = 'fill="none" stroke="#000" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"'


def svg(w: int, h: int, body: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">\n{body}\n</svg>\n'


def gear(cx: float, cy: float, r: float, teeth: int, depth: float, turn: float = 0.0) -> str:
    """A spur gear's outline: `teeth` flat-topped teeth of `depth` around a root circle of radius r - depth."""
    points = []
    for k in range(teeth):
        a = turn + 2 * math.pi * k / teeth
        step = 2 * math.pi / teeth
        for frac, rad in ((0.0, r - depth), (0.18, r - depth), (0.3, r), (0.62, r), (0.74, r - depth)):
            t = a + frac * step
            points.append(f"{cx + rad * math.cos(t):.2f},{cy + rad * math.sin(t):.2f}")
    return f'<polygon points="{" ".join(points)}" {STROKE}/>'


def bolts(cx: float, cy: float, r: float, n: int, hole: float, turn: float = 0.0) -> str:
    return "".join(f'<circle cx="{cx + r * math.cos(turn + 2 * math.pi * k / n):.2f}" cy="{cy + r * math.sin(turn + 2 * math.pi * k / n):.2f}" r="{hole}" {THIN}/>' for k in range(n))


ICONS = {
    # a hobby servo from the side: the case with its two mounting ears, the output spline and a horn on top
    "form-hobby_servo": svg(64, 48, f"""<rect x="14" y="16" width="36" height="24" rx="2" {STROKE}/>
<path d="M14 22 H6 V27 H14 M50 22 H58 V27 H50" {STROKE}/>
<circle cx="8.5" cy="24.5" r="1" {THIN}/><circle cx="55.5" cy="24.5" r="1" {THIN}/>
<path d="M22 16 V12 H30 V16" {STROKE}/>
<path d="M17 9 H40 a2.5 2.5 0 0 1 0 5 H17 a2.5 2.5 0 0 1 0 -5 Z" {STROKE}/>
<circle cx="26" cy="11.5" r="1.2" {THIN}/><circle cx="35" cy="11.5" r="0.9" {THIN}/>
<path d="M28 40 V44 M32 40 V44 M36 40 V44" {THIN}/>"""),
    # an integrated (quasi-direct-drive) actuator face on: housing, bolt circle, output flange, a connector
    "form-integrated_actuator": svg(64, 48, f"""<circle cx="30" cy="24" r="19" {STROKE}/>
<circle cx="30" cy="24" r="9" {STROKE}/>{bolts(30, 24, 14, 8, 1.3, math.pi / 8)}{bolts(30, 24, 6, 6, 0.9)}
<circle cx="30" cy="24" r="2.2" {THIN}/>
<path d="M48 18 H56 V30 H48" {STROKE}/><path d="M56 21 H59 M56 27 H59" {THIN}/>"""),
    # a direct-drive (frameless) motor: a thin wide ring around a large hollow bore
    "form-direct_drive": svg(64, 48, f"""<circle cx="32" cy="24" r="21" {STROKE}/>
<circle cx="32" cy="24" r="13" {STROKE}/>
<circle cx="32" cy="24" r="17" stroke-dasharray="2.2 2.6" {THIN}/>{bolts(32, 24, 19, 12, 0.9)}"""),
    # a bare gearmotor from the side: the motor can, the gearbox, the output shaft and the leads
    "form-bare_gearmotor": svg(64, 48, f"""<rect x="22" y="12" width="28" height="24" rx="4" {STROKE}/>
<rect x="8" y="15" width="14" height="18" rx="1.5" {STROKE}/>
<path d="M8 24 H2" {STROKE}/><path d="M12 15 V33 M17 15 V33" {THIN}/>
<path d="M50 20 h4 q4 0 6 -6 M50 28 h4 q4 0 6 6" {THIN}/>
<path d="M30 12 V36 M42 12 V36" stroke-dasharray="1.5 2.5" {THIN}/>"""),
    # a wheel-hub motor: the tyre, the rim and the hub with its spokes
    "form-wheel_hub": svg(64, 48, f"""<circle cx="32" cy="24" r="21" {STROKE}/>
<circle cx="32" cy="24" r="16" {STROKE}/>
<circle cx="32" cy="24" r="6" {STROKE}/>{bolts(32, 24, 3.6, 5, 0.7)}
{"".join(f'<path d="M{32 + 6 * math.cos(a):.2f} {24 + 6 * math.sin(a):.2f} L{32 + 16 * math.cos(a):.2f} {24 + 16 * math.sin(a):.2f}" {THIN}/>' for a in [k * math.pi / 3 for k in range(6)])}"""),
    # geared: a pinion driving a larger gear
    "drivetrain-geared": svg(64, 48, f"""{gear(22, 26, 15, 14, 3)}<circle cx="22" cy="26" r="3" {STROKE}/>
{gear(46, 18, 9.5, 9, 2.6, 0.2)}<circle cx="46" cy="18" r="2.2" {STROKE}/>"""),
    # direct drive: the rotor's magnets turn the load straight, no gears
    "drivetrain-direct_drive": svg(64, 48, f"""<circle cx="32" cy="24" r="19" {STROKE}/>
<circle cx="32" cy="24" r="12" {STROKE}/>
{"".join(f'<rect x="{32 + 15.5 * math.cos(a) - 2:.2f}" y="{24 + 15.5 * math.sin(a) - 2:.2f}" width="4" height="4" transform="rotate({math.degrees(a):.1f} {32 + 15.5 * math.cos(a):.2f} {24 + 15.5 * math.sin(a):.2f})" {THIN}/>' for a in [k * math.pi / 6 for k in range(12)])}
<path d="M26 14 A11 11 0 0 1 42 18" {STROKE}/><path d="M42 18 l-4.5 -0.6 M42 18 l-0.9 -4.4" {STROKE}/>"""),
    # motor: a bare motor's can and shaft, no reduction
    "drivetrain-motor": svg(64, 48, f"""<rect x="14" y="12" width="32" height="24" rx="5" {STROKE}/>
<path d="M46 24 H58" {STROKE}/><path d="M14 18 H10 M14 30 H10" {THIN}/>
<path d="M22 12 V36 M38 12 V36" stroke-dasharray="1.5 2.5" {THIN}/>"""),
}


def arrow(x1: float, y1: float, x2: float, y2: float) -> str:
    """A dimension line with an arrowhead at each end."""
    a = math.atan2(y2 - y1, x2 - x1)
    head = lambda x, y, d: f"M{x + 5 * math.cos(a + d * math.pi + 0.45):.2f} {y + 5 * math.sin(a + d * math.pi + 0.45):.2f} L{x:.2f} {y:.2f} L{x + 5 * math.cos(a + d * math.pi - 0.45):.2f} {y + 5 * math.sin(a + d * math.pi - 0.45):.2f}"
    return f'<path d="M{x1} {y1} L{x2} {y2} {head(x1, y1, 0)} {head(x2, y2, 1)}" {THIN}/>'


TEXT = 'font-family="Helvetica, Arial, sans-serif" font-size="11" text-anchor="middle"'

DIAGRAMS = {
    # outer diameter: the actuator's face, a dimension across it
    "od": svg(200, 92, f"""<circle cx="100" cy="54" r="32" {STROKE}/><circle cx="100" cy="54" r="14" {STROKE}/>{bolts(100, 54, 23, 8, 1.6, math.pi / 8)}
<path d="M68 54 V14 M132 54 V14" stroke-dasharray="3 3" {THIN}/>{arrow(68, 18, 132, 18)}
<text x="100" y="12" {TEXT}>OD</text>"""),
    # axial length: the actuator's side, a dimension along its axis (flange face to back face)
    "length": svg(200, 92, f"""<path d="M76 22 H124 V74 H76 Z" {STROKE}/><path d="M124 34 H132 V62 H124" {STROKE}/><path d="M68 40 H76 M68 56 H76" {THIN}/>
<path d="M100 22 V74" stroke-dasharray="6 3 1 3" {THIN}/>
<path d="M76 22 V14 M124 22 V14" stroke-dasharray="3 3" {THIN}/>{arrow(76, 18, 124, 18)}
<text x="100" y="12" {TEXT}>L</text>"""),
}


def main() -> None:
    for folder, files in (("icons", ICONS), ("diagrams", DIAGRAMS)):
        (CASE / folder).mkdir(exist_ok=True)
        for name, text in files.items():
            (CASE / folder / f"{name}.svg").write_text(text, encoding="utf-8")
            print(f"{folder}/{name}.svg")


if __name__ == "__main__":
    main()
