"""Browser checks for this case (run by tests/browser/checks.py): models x benches. The pivot, the strip of every run
with the floor and twin-grade lines, the median bars against an oracle computed here from the data file, and a bar's
click listing the runs behind it; light and dark at 1280 and 390 px."""

import json
import pathlib
import statistics

V = "#example"
DATA = json.loads((pathlib.Path(__file__).parent / "models.json").read_text(encoding="utf-8"))

# the page coordinates of every bar (Vega rect items under the plot's padding and origin) with its datum
BARS = """() => {
  const el = document.querySelector('#example .dv-view-chart'); const view = el.vegaView;
  const box = el.querySelector('canvas').getBoundingClientRect(); const [ox0, oy0] = view.origin(); const pad = view.padding();
  const out = [];
  const walk = (mark, gx, gy) => {
    for (const item of mark.items || []) {
      if (mark.marktype === 'group') { for (const m of item.items || []) walk(m, gx + (item.x || 0), gy + (item.y || 0)); }
      else if (mark.marktype === 'rect' && item.datum && item.datum.variant) out.push({ variant: item.datum.variant, median: item.datum.median_q_rms_mrad,
        x: box.left + pad.left + ox0 + gx + (item.bounds.x1 + item.bounds.x2) / 2, y: box.top + pad.top + oy0 + gy + (item.bounds.y1 + item.bounds.y2) / 2 });
    }
  };
  walk(view.scenegraph().root, 0, 0);
  return out.filter((b) => Number.isFinite(b.x) && Number.isFinite(b.y));
}"""


def show(page):
    page.evaluate("window.scrollTo(0, document.querySelector('#example').getBoundingClientRect().top + window.scrollY - 70)")
    page.wait_for_timeout(200)


def tab(page, name, view):
    page.click(f"{V} .dv-tab[data-name='{name}']")
    page.wait_for_selector(f"{V}[data-view={view}]", timeout=15000)
    if view == "chart":
        page.wait_for_selector(f"{V} .dv-view-chart[data-drawn]", timeout=15000)
    page.wait_for_timeout(400)


def run(ctx, path):
    check = ctx.check
    page = ctx.page(path, width=1280)
    status = page.inner_text(f"{V} .dv-status")
    check("models x benches: the pivot is 11 models x 10 tests over the 100 records", status.startswith("11 rows × 10 columns · from 100 of 100 records"), status)

    tab(page, "Every run per model", "chart")
    strip = page.evaluate("""() => { const v = document.querySelector('#example .dv-view-chart').vegaView;
      return { n: v.data('rows').length, rules: [v.data('rule0x'), v.data('rule1x'), v.data('rule2x')].map((d) => d.length) }; }""")
    st = page.inner_text(f"{V} .dv-status")
    check("models x benches: every scored run drawn per model on a log axis, the 7 models with no run counted out, the floor and twin-grade lines drawn",
          strip["n"] == 93 and strip["rules"] == [1, 1, 1] and "7 without q RMS" in st, f"{strip}; {st}")

    tab(page, "Median per model", "chart")
    show(page)
    bars = page.evaluate(BARS)
    runs = {}
    for r in DATA["rows"]:
        if r["q_rms_mrad"] is not None:
            runs.setdefault(r["variant"], []).append(r["q_rms_mrad"])
    oracle = {v: statistics.median(q) for v, q in runs.items()}
    check("models x benches: one bar per scored model, each the median q RMS computed from models.json",
          len(bars) == len(oracle) and all(abs(b["median"] - oracle[b["variant"]]) < 1e-9 for b in bars), {b["variant"]: round(b["median"], 3) for b in bars})
    target = max(bars, key=lambda b: len(runs[b["variant"]]))
    page.mouse.move(target["x"], target["y"])
    page.wait_for_timeout(400)
    card = page.evaluate("(() => { const c = document.querySelector('#example .dv-chart-hover'); return c.hidden ? null : c.innerText; })()")
    page.mouse.click(target["x"], target["y"])
    page.wait_for_selector(f"{V} .dv-peek:not([hidden])")
    listed = page.locator(f"{V} .dv-peek .dv-peektable tbody tr").count()
    check("models x benches: hovering a bar says what it summarises; clicking it lists the runs behind it",
          card and f"{len(runs[target['variant']])} rows" in card and listed == len(runs[target["variant"]]), f"{target['variant']}: card {card and card.splitlines()[-1]!r}, {listed} runs listed")
    ctx.shot(page, "models-benches-bar-peek-light-1280")
    page.context.close()

    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            p = ctx.page(path, width=width, height=900 if width > 400 else 844, dark=dark, mobile=mobile)
            name = f"models-benches-{'dark' if dark else 'light'}-{width}"
            scroll = p.evaluate("document.scrollingElement.scrollWidth")
            if width == 390:
                check(f"models x benches, {'dark' if dark else 'light'}, 390 px: no sideways page scroll", scroll <= 390, f"scrollWidth {scroll}")
            show(p)
            ctx.shot(p, name)
            tab(p, "Every run per model", "chart")
            show(p)
            ctx.shot(p, name.replace("models-benches", "models-benches-strip"))
            p.context.close()
