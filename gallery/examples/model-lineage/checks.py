"""Browser checks for the lineage view on a second, non-brand dataset (run by tests/browser/checks.py): the actuator
model ladder, label nodes and no pictures. The oracle and the measuring script are the brand-lineage case's."""

import importlib.util
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("brand_lineage_checks", HERE.parent / "brand-lineage" / "checks.py")
bl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bl)
V = bl.V


def run(ctx, path):
    check = ctx.check
    rows = json.loads((HERE / "ladder.json").read_text(encoding="utf-8"))["rows"]
    kept = {"status": ["measured"]}
    o = bl.lineage_oracle(rows, kept=kept, focus="m4-ripple-c1")

    page = bl.open_view(ctx, path)
    m = bl.measure(page)
    groups = [n for n in m["nodes"] if n["group"]]
    shown = {n["id"] for n in m["nodes"] if not n["group"]}
    check("model ladder collapse: the 7 alive models show (4 measured + their ancestors); '+N' groups stand for the 4 with no runs",
          shown == o["alive"] and sum(n["count"] for n in groups) == len(rows) - len(o["alive"]) and len(o["alive"]) == 7,
          f"{len(rows)} models -> {len(shown)} marks + {[n['label'] for n in groups]}")
    labels = {n["id"]: n["label"] for n in m["nodes"] if not n["group"]}
    want = {r["id"]: r["variant"] for r in rows if r["id"] in shown}
    check("model ladder: no image property, so every mark is its label (the full text, or an ellipsis with the full text one hover away)",
          not any(n["image"] for n in m["nodes"]) and all(labels[i] == t or (labels[i].endswith("…") and t.startswith(labels[i][:-1])) for i, t in want.items())
          and all(page.evaluate("(id) => document.querySelector(`#example g.dv-lineage-node[data-id=\"${id}\"] title`).textContent", i).startswith(t) for i, t in want.items()),
          list(labels.values())[:4])
    bl.edge_checks(check, "model ladder", m, o)
    bl.trunk_checks(check, "model ladder", m, o)

    bl.set_extinct(ctx, page, True)
    m = bl.measure(page)
    check("model ladder show extinct: all 11 models", {n["id"] for n in m["nodes"]} == o["ids"], len(m["nodes"]))
    bl.edge_checks(check, "model ladder show extinct", m, o)
    sp = [(e["from"], e["to"]) for e in m["edges"] if e["splice"]]
    check("model ladder: the one splice is the c1 soft-friction twin's second parent, M2 (dashed)", sp == [("m2-coulomb-viscous", "m4-ripple-c1-soft")], sp)
    page.context.close()

    page = bl.open_view(ctx, path, "Ladder, radial")
    m = bl.measure(page)
    o2 = bl.lineage_oracle(rows, kept=kept, focus="m4-ripple-c1-soft")
    bl.edge_checks(check, "model ladder radial", m, o2)
    bl.trunk_checks(check, "model ladder radial (the splice's trunk takes both parents' ancestries)", m, o2)
    page.context.close()

    for dark in (False, True):
        p = bl.open_view(ctx, path, width=390, height=844, dark=dark, mobile=True)
        sw = p.evaluate("document.scrollingElement.scrollWidth")
        check(f"model ladder, {'dark' if dark else 'light'}, 390 px: no sideways page scroll", sw <= 390, sw)
        ctx.shot(p, f"model-lineage-{'dark' if dark else 'light'}-390")
        p.context.close()
