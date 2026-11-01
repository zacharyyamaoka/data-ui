"""Browser checks for this case (run by tests/browser/checks.py): the KPI section, as Vibe Tracks draws it. Five cards
in groupOrder, the headline first with its history drawn by the chart view, the producer's numbers, basis badges,
deltas coloured by which way is better, hollow marks for estimates, "—" with its reason, drill-down; light and dark
at 1280 and 390 px."""

import json
import pathlib

V = "#example"
DATA = json.loads((pathlib.Path(__file__).parent / "kpis.json").read_text(encoding="utf-8"))


def show(page):
    page.evaluate("window.scrollTo(0, document.querySelector('#example').getBoundingClientRect().top + window.scrollY - 70)")
    page.wait_for_timeout(200)


def cards(page):
    page.wait_for_selector(f"{V}[data-view=kpi] data-kpi", timeout=15000)
    page.wait_for_selector(f"{V} data-kpi.dv-kpi-has-history canvas", timeout=15000)
    page.wait_for_timeout(200)
    return page.evaluate("""() => [...document.querySelectorAll('#example data-kpi')].map((k) => ({
      label: k.querySelector('.dv-kpi-label').textContent, num: (k.querySelector('.dv-kpi-num') || {}).textContent || null,
      none: !!k.querySelector('.dv-kpi-none'), why: (k.querySelector('.dv-kpi-why') || {}).textContent || null,
      basis: k.dataset.basis, tone: k.dataset.tone, delta: (k.querySelector('.dv-kpi-delta') || {}).textContent || null,
      from: (k.querySelector('.dv-kpi-from') || {}).textContent || null, headline: k.classList.contains('dv-kpi-headline'),
      history: !!k.querySelector('.dv-kpi-history canvas'), hollow: k.querySelectorAll('.dv-spark .dv-spark-hollow').length,
      marks: k.querySelectorAll('.dv-spark circle').length }))""")


def run(ctx, path):
    check = ctx.check
    page = ctx.page(path, width=1280)
    got = cards(page)
    labels = [c["label"] for c in got]
    check("KPIs: five cards in the file's groupOrder, the SPPM headline first",
          labels == ["Successful picks per minute (SPPM)", "Computation time", "Grasp success", "Computation time p95", "Bench score"], labels)
    head = got[0]
    check("KPIs: the headline is bigger and draws its run history with the chart view (Vega-Lite, one engine on the page)",
          head["headline"] and head["history"] and not any(c["headline"] for c in got[1:]), {k: head[k] for k in ("headline", "history")})
    # the oracle: the newest champion reading per KPI, read from the data file, not from the view
    newest = {}
    for r in DATA["rows"]:
        if r["kpi"] != "bench_score" and (r["kpi"] not in newest or r["t"] > newest[r["kpi"]]["t"]):
            newest[r["kpi"]] = r
    sppm = newest["sppm"]["value"]
    check("KPIs: the headline is the producer's number, the newest reading as written (never recomputed), with its basis and run count",
          head["num"] == f"{sppm['value']:,}" and head["basis"] == sppm["basis"] and f"computed from {sppm['n']} runs" in head["from"],
          f"{head['num']} {head['basis']}; {head['from']}; data: {sppm['value']} {sppm['basis']} n={sppm['n']}")
    comp = got[1]
    check("KPIs: a delta is coloured by which way is better, not by its sign (SPPM up is good, computation time down is good)",
          head["delta"].startswith("+") and head["tone"] == "good" and comp["delta"].startswith("−") and comp["tone"] == "good",
          f"SPPM {head['delta']} ({head['tone']}); time {comp['delta']} ({comp['tone']})")
    check("KPIs: estimates draw hollow in the sparklines (filled = measured)", all(c["hollow"] > 0 for c in got[1:4]) and all(c["marks"] > c["hollow"] for c in got[1:4]),
          [(c["label"], c["hollow"], c["marks"]) for c in got[1:4]])
    bench = got[4]
    check("KPIs: the bench score has no value in the fixture, so its card says — with the reason, never 0", bench["none"] and bench["num"] is None and "not in the synthetic fixture" in (bench["why"] or ""), bench["why"])
    page.click(f"{V} data-kpi[data-i='1'] .dv-kpi-label")
    page.wait_for_selector(f"{V} .dv-peek:not([hidden])")
    behind = page.locator(f"{V} .dv-peek .dv-peektable tbody tr").count()
    check("KPIs: clicking a card opens the readings behind it", behind == 40, f"{behind} readings for Computation time")
    page.keyboard.press("Escape")
    page.check("data-facets input[data-p=model][data-value='M3.dense']")
    page.wait_for_timeout(500)
    after = cards(page)
    check("KPIs: the rail filters the cards (only M3.dense's readings)", after[0]["num"] != head["num"] and "48 of 161" in page.inner_text(f"{V} .dv-status"),
          f"SPPM now {after[0]['num']}; {page.inner_text(f'{V} .dv-status').split(' · ')[0]}")
    page.click("data-facets [data-clear]")
    page.wait_for_timeout(300)
    page.click(f"{V} .dv-tab[data-name='SPPM history']")
    page.wait_for_selector(f"{V}[data-view=chart] .dv-view-chart[data-drawn]")
    page.wait_for_timeout(300)
    hist = page.evaluate("""() => { const v = document.querySelector('#example .dv-view-chart').vegaView; const rows = v.data('rows');
      return { n: rows.length, hollow: rows.filter((d) => d._hollow).length, rule: v.data('rule0y').length }; }""")
    check("SPPM history: a chart view of the 40 readings, estimates hollow, the 30 picks/min reference line", hist["n"] == 40 and hist["hollow"] > 0 and hist["rule"] == 1, hist)
    page.context.close()

    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            p = ctx.page(path, width=width, height=900 if width > 400 else 844, dark=dark, mobile=mobile)
            cards(p)
            scroll = p.evaluate("document.scrollingElement.scrollWidth")
            if width == 390:
                check(f"vibetracks KPIs, {'dark' if dark else 'light'}, 390 px: no sideways page scroll", scroll <= 390, f"scrollWidth {scroll}")
            tone = p.evaluate("getComputedStyle(document.querySelector('#example data-kpi[data-tone=good] .dv-kpi-delta')).color")
            want = "rgb(111, 191, 139)" if dark else "rgb(47, 122, 74)"
            check(f"vibetracks KPIs, {'dark' if dark else 'light'}, {width} px: a good delta wears Vibe Tracks' success ink (--data-good from its skin)", tone == want, tone)
            show(p)
            ctx.shot(p, f"vibetracks-kpis-{'dark' if dark else 'light'}-{width}")
            p.context.close()
