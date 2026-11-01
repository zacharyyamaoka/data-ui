"""Browser checks for this case (run by tests/browser/checks.py): runs as rows. The leaderboard pivot, success rate by
round per environment, one KPI card per model whose pooled rate (Σ successes / Σ attempts) matches an oracle computed
here from the data file, light and dark at 1280 and 390 px."""

import datetime
import json
import pathlib

V = "#example"
DATA = json.loads((pathlib.Path(__file__).parent / "runs.json").read_text(encoding="utf-8"))


def show(page):
    page.evaluate("window.scrollTo(0, document.querySelector('#example').getBoundingClientRect().top + window.scrollY - 70)")
    page.wait_for_timeout(200)


def tab(page, name, view):
    page.click(f"{V} .dv-tab[data-name='{name}']")
    page.wait_for_selector(f"{V}[data-view={view}]", timeout=15000)
    if view == "chart":
        page.wait_for_selector(f"{V} .dv-view-chart[data-drawn]", timeout=15000)
    page.wait_for_timeout(400)


def oracle(grain):
    """[(label, count)] in time order, from the data file with Python's datetime (ISO weeks from Monday): the oracle for
    the row model's time groups, computed without the kit's bucketing."""
    counts = {}
    for r in DATA["rows"]:
        day = datetime.date.fromisoformat(r["started"][:10])  # the written date, never converted to another zone
        start = day - datetime.timedelta(days=day.weekday()) if grain == "week" else day.replace(day=1)
        counts[start] = counts.get(start, 0) + 1
    word = (lambda d: f"Week of {d.day} {d.strftime('%b')} {d.year}") if grain == "week" else (lambda d: f"{d.strftime('%b')} {d.year}")
    return [(word(d), n) for d, n in sorted(counts.items())]


def group_heads(page):
    """The table's group rows as drawn: [(label, count)], all folded so every one is on screen."""
    page.click(f"{V} .dv-status [data-fold=closed]")
    page.ctx.frames(page)
    return page.evaluate("""() => [...document.querySelectorAll('#example tr.dv-group')].map((tr) => [tr.querySelector('.dv-gname').textContent, Number(tr.querySelector('.dv-count').textContent)])""")


def by_week(ctx, path):
    """`groupBy: {property: started, by: week}`: the runs table grouped by ISO week, its counts equal to Python's
    datetime; the Group menu's grain picker regroups it by month; the chart's time axis counts the same weeks."""
    check = ctx.check
    page = ctx.page(f"{path}#view=runs-by-week", width=1280)
    page.wait_for_selector(f"{V}[data-view=table] tr.dv-group", timeout=15000)
    want = oracle("week")
    got = group_heads(page)
    check("ML runs by week: one group per ISO week (from Monday), labelled 'Week of …', in time order, each count equal to Python's datetime over runs.json",
          got == [[w, n] for w, n in want], {"drawn": got, "oracle": want})
    page.click(f"{V} [data-menu=group]")
    picker = page.locator(f"{V} .dv-pop select[data-k=b0]")
    check("ML runs by week: the Group menu offers a date grain for a date property, set to week", picker.count() == 1 and picker.input_value() == "week",
          picker.input_value() if picker.count() else "no picker")
    ctx.drawn(page, lambda: picker.select_option("month"))
    page.keyboard.press("Escape")
    got = group_heads(page)
    want = oracle("month")
    check("ML runs by week: picking month in the Group menu regroups the same runs by month ('Sep 2026', 'Oct 2026'), counts equal to the oracle",
          got == [[w, n] for w, n in want] and page.evaluate("document.querySelector('#example').view.groupBy.by") == "month", {"drawn": got, "oracle": want})
    page.click(f"{V} [data-menu=group]")
    ctx.drawn(page, lambda: page.locator(f"{V} .dv-pop select[data-k=g0]").select_option("model"))
    check("ML runs by week: grouping by a property that is not a date drops the grain and its picker",
          page.locator(f"{V} .dv-pop select[data-k=b0]").count() == 0 and "by" not in page.evaluate("document.querySelector('#example').view.groupBy"),
          page.evaluate("document.querySelector('#example').view.groupBy"))
    page.context.close()

    page = ctx.page(f"{path}#view=runs-per-week", width=1280)
    page.wait_for_selector(f"{V} .dv-view-chart[data-drawn]", timeout=15000)
    drawn = page.evaluate("""() => { const v = document.querySelector('#example .dv-view-chart').vegaView; const by = {};
      for (const d of v.data('rows')) by[d.started] = (by[d.started] || 0) + 1;
      let domain = null; try { domain = v.scale('x').domain(); } catch { /* no scale named x */ }
      return { by, domain }; }""")
    want = oracle("week")
    check("ML runs per week: the chart's axis is the ISO weeks in time order, one band each, every run in its week: the same counts as the table and Python's datetime",
          drawn["by"] == dict(want) and drawn["domain"] == [w for w, _ in want], {"drawn": drawn["by"], "axis": drawn["domain"], "oracle": want})
    ctx.drawn(page, lambda: page.evaluate("""() => document.querySelector('#example').setView({ filters: 'started < "2026-09-28" || started >= "2026-10-12"' })"""))
    page.wait_for_selector(f"{V} .dv-view-chart[data-drawn]", timeout=15000)
    gaps = page.evaluate("""() => { const v = document.querySelector('#example .dv-view-chart').vegaView; return { rows: [...new Set(v.data('rows').map((d) => d.started))], domain: v.scale('x').domain() }; }""")
    check("ML runs per week: filtered to the first and last week, the axis keeps the two weeks between as empty bands (a time axis shows its gaps)",
          gaps["rows"] == [want[0][0], want[-1][0]] and gaps["domain"] == [w for w, _ in want], gaps)

    # ---- change over time is a line (Zach, 2026-10-26; docs/SPEC.md §8.5): the drawn line's points, read back through
    # Vega's own scales, are every week's count, 0 in an empty week; gaps: true breaks the line there; mark: bar is bars
    LINE = """() => { const v = document.querySelector('#example .dv-view-chart').vegaView; const out = { line: [], rects: 0 };
      const walk = (n) => { if (!n) return; if (n.marktype === 'line' && n.role === 'mark') for (const it of n.items) out.line.push([it.datum && it.datum.started, Number.isFinite(it.y) && it.defined !== false ? Math.round(v.scale('y').invert(it.y) * 1000) / 1000 : null]);
        if (n.marktype === 'rect' && n.role === 'mark') out.rects += n.items.length; (n.items || []).forEach((c) => walk(c)); };
      walk(v.scenegraph().root); return out; }"""
    seen = page.evaluate(LINE)
    first, last = want[0], want[-1]
    expect_zero = [[first[0], first[1]]] + [[w, 0] for w, _ in want[1:-1]] + [[last[0], last[1]]]
    check("ML runs per week: with no mark the chart is a line over every week (no bars); an empty week is a count of 0 on the line",
          sorted(seen["line"]) == sorted(expect_zero) and seen["rects"] == 0, {"line": seen["line"], "want": expect_zero, "bars": seen["rects"]})
    ctx.drawn(page, lambda: page.evaluate("""() => { const el = document.querySelector('#example'); const c = el.view.chart;
      el.setView({ chart: { ...c, encoding: { ...c.encoding, x: { ...c.encoding.x, gaps: true } } } }); }"""))
    page.wait_for_selector(f"{V} .dv-view-chart[data-drawn]", timeout=15000)
    gapped = page.evaluate(LINE)
    check("ML runs per week: gaps: true breaks the line at the empty weeks (they draw no point), the two real weeks keep their counts",
          sorted([p for p in gapped["line"] if p[1] is not None]) == sorted([[first[0], first[1]], [last[0], last[1]]]) and gapped["rects"] == 0, gapped)
    ctx.drawn(page, lambda: page.evaluate("""() => { const el = document.querySelector('#example'); el.setView({ chart: { ...el.view.chart, mark: 'bar' } }); }"""))
    page.wait_for_selector(f"{V} .dv-view-chart[data-drawn]", timeout=15000)
    bars = page.evaluate(LINE)
    check("ML runs per week: bars stay one mark: bar away", bars["rects"] == 2 and not bars["line"], {"bars": bars["rects"], "line points": len(bars["line"])})
    page.context.close()


def run(ctx, path):
    check = ctx.check
    by_week(ctx, path)
    page = ctx.page(path, width=1280)
    status = page.inner_text(f"{V} .dv-status")
    check("ML runs: the leaderboard pivot is models x environments over the 120 runs", status.startswith("4 rows × 3 columns · from 120 of 120 records"), status)

    tab(page, "Success rate by round", "chart")
    chart = page.evaluate("""() => { const v = document.querySelector('#example .dv-view-chart').vegaView; const rows = v.data('rows');
      return { n: rows.length, envs: new Set(rows.map((d) => d.env)).size, models: v.scale ? null : null }; }""")
    check("ML runs: success rate against the step (round), one small multiple per environment, every run drawn", chart["n"] == 120 and chart["envs"] == 3, chart)

    tab(page, "Pooled success by model", "kpi")
    page.wait_for_timeout(300)
    got = page.evaluate("""() => [...document.querySelectorAll('#example data-kpi')].map((k) => ({ label: k.querySelector('.dv-kpi-label').textContent,
      num: k.querySelector('.dv-kpi-num').textContent, headline: k.classList.contains('dv-kpi-headline'), gate: (k.querySelector('.dv-kpi-gate') || {}).className || '' }))""")
    oracle = {}
    for r in DATA["rows"]:
        s, a = oracle.get(r["model"], (0, 0))
        oracle[r["model"]] = (s + r["successes"], a + r["attempts"])
    want = {m: s / a for m, (s, a) in oracle.items()}
    ok = len(got) == 4 and all(abs(float(c["num"]) - want[c["label"]]) < 5e-4 for c in got)
    held = all(("dv-kpi-held" in c["gate"]) == (want[c["label"]] >= 0.55) for c in got)
    check("ML runs: one card per model; each pooled success rate equals Σ successes / Σ attempts computed from runs.json", ok,
          {c["label"]: f"{c['num']} (oracle {want[c['label']]:.4f})" for c in got})
    check("ML runs: the 0.55 gate reads held or missed per model, and no model is promoted to a headline (plain group order)",
          held and not any(c["headline"] for c in got), {c["label"]: c["gate"].split()[-1] for c in got})

    tab(page, "Compute vs success", "chart")
    n = int(page.get_attribute(f"{V} .dv-view-chart", "data-drawn"))
    check("ML runs: compute vs success, every run a dot sized by attempts", n == 120, f"{n} dots")
    page.context.close()

    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            p = ctx.page(path, width=width, height=900 if width > 400 else 844, dark=dark, mobile=mobile)
            name = f"ml-experiments-{'dark' if dark else 'light'}-{width}"
            scroll = p.evaluate("document.scrollingElement.scrollWidth")
            if width == 390:
                check(f"ML runs, {'dark' if dark else 'light'}, 390 px: no sideways page scroll", scroll <= 390, f"scrollWidth {scroll}")
            show(p)
            ctx.shot(p, name)
            tab(p, "Success rate by round", "chart")
            show(p)
            ctx.shot(p, name.replace("ml-experiments", "ml-experiments-chart"))
            p.context.close()
