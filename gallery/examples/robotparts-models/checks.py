"""Browser checks for robotparts' actuator models (run by tests/browser/checks.py): the pivot first, then the leaderboard
and the parameters, as tabs of one .base, and each model's page. What they hold the page to (CONTRACT §16):

- every tab opens with its answer (KPI cards where it has them) and its reading guide one click away (the About note,
  CONTRACT §28: never an inline paragraph between the cards and the rows);
- the roll-up: the rolled-up cells equal aggregates recomputed from the rack's raw budget files (source/oracle.py,
  never models.json); the Roll up menu un-rolls and re-rolls; a per-column aggregate changes the cell; a click on a
  rolled-up cell or row lists exactly the rows behind it;
- the sub-headers span exactly their columns (getBoundingClientRect);
- alignment: down a column, every number's right edge and every mark's left edge sit at one x (getBoundingClientRect);
- a model's name links to its page; its peek and its page show the twin code's real README at the fit commit;
- the rail drags wider (measured); light and dark at 1440 and 390 px with no sideways scroll.
"""

import importlib.util
import json
import pathlib
import urllib.parse

HERE = pathlib.Path(__file__).parent
DATA = json.loads((HERE / "models.json").read_text(encoding="utf-8"))
_spec = importlib.util.spec_from_file_location("models_oracle", HERE / "source" / "oracle.py")
oracle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(oracle)
V = "#example"
TABS = ["Benches", "Benches · every actuator", "Leaderboard", "Rung ladder", "Parameters", "Parameters · with CI", "What each rung adds", "What each rung adds · columns", "Runs"]
HELD = "Held-out tapes · Oct 23"


def tab(page, name):
    page.click(f"{V} .dv-tab[data-name='{name}']")
    page.wait_for_function(f"() => document.querySelector('#example').view.name === {json.dumps(name)} && document.querySelector('#example').dataset.view")
    page.wait_for_timeout(500)


def cell(page, variant, col):
    """The cell of a row by its model's name (a JS lookup: the name may sit inside a link)."""
    return page.evaluate_handle(f"""() => {{ const tr = [...document.querySelectorAll('#example tbody tr.dv-row')].find((t) => (t.querySelector('td[data-col=variant]') || {{}}).textContent?.trim() === {json.dumps(variant)});
      return tr ? tr.querySelector(`td[data-col="${{CSS.escape({json.dumps(col)})}}"]`) : null; }}""").as_element()


def edges(page, selector):
    """[left, right] of every element matching selector (visible rows only)."""
    return page.evaluate(f"""() => [...document.querySelectorAll({json.dumps(selector)})].map((e) => {{ const r = e.getBoundingClientRect(); return [r.left, r.right, r.width]; }}).filter((x) => x[2] > 0)""")


def run(ctx, path):
    check = ctx.check
    page = ctx.page(path, width=1440, height=1000)

    # every tab, and its intro
    seen = {}
    for name in TABS:
        tab(page, name)
        seen[name] = page.evaluate("""() => { const v = document.querySelector('#example'); const i = v.querySelector('.dv-intro');
          const about = v.querySelector('.dv-status [data-about]'); const t = i && i.querySelector('.dv-intro-text');
          return { text: about ? ((v.view.intro || {}).text || '').trim().slice(0, 40) : '', inline: !!(t && !t.hidden && t.textContent.trim()),
            cards: i && !i.hidden ? i.querySelectorAll('data-kpi').length : 0 }; }""")
    want_cards = {"Benches": 4, "Leaderboard": 8, "Parameters": 8, "What each rung adds": 4}
    bad = {n: s for n, s in seen.items() if (n != "Rung ladder" and n != "Runs" and not s["text"]) or s["inline"] or (n in want_cards and s["cards"] != want_cards[n])}
    check("models: the pivot is the first tab, and every table tab opens with its answer (KPI cards on Benches, Leaderboard, Parameters, What each rung adds; its reading guide behind ⓘ About, never inline)",
          page.eval_on_selector(f"{V} .dv-tab", "e => e.dataset.name") == "Benches" and not bad, bad or {n: s["cards"] for n, s in seen.items()})

    # roll-up: Benches is rolled up across actuators by default; its cells against the archive
    tab(page, "Benches")
    status = page.inner_text(f"{V} .dv-status")
    cells = page.evaluate("""() => { const m = document.querySelector('#example').model.pivot; const r = m.rows.find((x) => x.variant === 'M2.coulomb_viscous');
      return Object.fromEntries(m.columns.filter((c) => r[c.id]).map((c) => [c.path.join(' / '), [r[c.id].v, r[c.id].records.length]])); }""")
    tests = ["staircase", "sine", "tape slow", "tape medium", "tape fast"]
    if oracle.available():
        bad = []
        for t in tests:
            want, n = oracle.rolled_identified(t)
            got = cells.get(f"{HELD} / {t}")
            if not got or abs(got[0] - want) > 1e-6 or got[1] != n:  # models.json keeps 6 decimals
                bad.append((t, got, (want, n)))
        check("models: rolled up across actuators by default; M2.coulomb_viscous's held-out cells equal the median and count of every run of all 8 actuators, recomputed from the raw budget files",
              "rolled up across Actuator" in status and not bad, bad or {t: cells.get(f"{HELD} / {t}") for t in tests})
    else:
        check("models: rolled up across actuators by default (rack archive absent: the oracle is skipped, not faked)", "rolled up across Actuator" in status, status)
    drawn = page.evaluate(f"""() => {{ const tr = [...document.querySelectorAll('#example tbody tr.dv-row')].find((t) => t.querySelector('td[data-col=variant]').textContent.trim() === 'M2.coulomb_viscous');
      const td = tr.querySelector('td[data-col="@{HELD} / staircase"]'); return [td.querySelector('.dv-v').textContent.trim(), td.querySelector('.dv-c').textContent.trim()]; }}""")
    sw, sn = oracle.rolled_identified("staircase") if oracle.available() else (cells[f"{HELD} / staircase"][0], cells[f"{HELD} / staircase"][1])
    check("models: the drawn rolled-up cell says the same: its median (2 decimals) and its count of runs", drawn == [f"{sw:.2f}", str(sn)], {"drawn": drawn, "want": [f"{sw:.2f}", sn]})

    # drill back down: a rolled-up cell lists the runs of every actuator behind it
    cell(page, "M2.coulomb_viscous", f"@{HELD} / staircase").click()
    page.wait_for_selector(f"{V} .dv-peek:not([hidden]) .dv-peektable", timeout=10000)
    listed = page.locator(f"{V} .dv-peek .dv-peektable tbody tr").count()
    check("models: clicking a rolled-up cell drills back down: the peek lists every run behind it", listed == sn, {"listed": listed, "want": sn})
    page.keyboard.press("Escape")
    ctx.shot(page, "models-benches-rolled-light-1440")

    # the Roll up menu: tick Actuator back (un-roll), then untick it (roll up again)
    page.click(f"{V} .dv-tools [data-menu=rollup]")
    page.wait_for_selector(f"{V} .dv-pop [data-dim=actuator]")
    page.check(f"{V} .dv-pop [data-dim=actuator]")
    page.wait_for_timeout(400)
    unrolled = page.inner_text(f"{V} .dv-status").split(" · ")[0]
    url = page.evaluate("location.hash")
    page.uncheck(f"{V} .dv-pop [data-dim=actuator]")
    page.wait_for_timeout(400)
    rerolled = page.inner_text(f"{V} .dv-status").split(" · ")[0]
    page.keyboard.press("Escape")
    check("models: the Roll up menu keeps actuators (35 model rows) and rolls them away again (12), and the changed view rides in the URL",
          unrolled.startswith("35 rows") and rerolled.startswith("12 rows") and "v=" in url, {"unrolled": unrolled, "rerolled": rerolled, "hash": url[:40]})

    # the leaderboard: rolled up, then the aggregate per column changed from the menu
    tab(page, "Leaderboard")
    page.click(f"{V} .dv-tools [data-menu=rollup]")
    page.wait_for_selector(f"{V} .dv-pop select[data-agg=headline_x]")
    page.select_option(f"{V} .dv-pop select[data-agg=headline_x]", "max")
    page.wait_for_timeout(400)
    page.keyboard.press("Escape")
    got = page.evaluate("""() => { const r = document.querySelector('#example').model.rows.find((x) => x.variant === 'M2.coulomb_viscous'); return [r.headline_x.value, r.headline_x.summary, r._records.length]; }""")
    want = oracle.identified_per_actuator_max() if oracle.available() else None
    check("models: the aggregate is chosen per column: Held-out error set to max is the worst actuator's median, recomputed from the budget files",
          got[1] == "Max" and got[2] == 8 and (want is None or abs(got[0] - want) < 1e-6), {"got": got, "want": want})
    cell(page, "M2.coulomb_viscous", "rung").click()
    page.wait_for_selector(f"{V} .dv-peek:not([hidden]) .dv-peektable", timeout=10000)
    rows = page.locator(f"{V} .dv-peek .dv-peektable tbody tr").count()
    check("models: clicking a rolled-up row lists the 8 actuators' rows behind it", rows == 8, rows)
    page.keyboard.press("Escape")
    page.click(f"{V} .dv-reset")
    page.wait_for_timeout(300)

    # alignment, measured: Benches' distribution columns (counts beside some) and the leaderboard's
    tab(page, "Benches")
    al = {}
    for col in [f"@{HELD} / staircase", f"@{HELD} / tape fast", "@Dataset · Oct 24 / cycle"]:
        rights = [round(e[1], 1) for e in edges(page, f'#example tbody td[data-col="{col}"] .dv-v')]
        marks = [round(e[0], 1) for e in edges(page, f'#example tbody td[data-col="{col}"] .dv-m')]
        al[col] = (len(rights), max(rights) - min(rights) if rights else None, max(marks) - min(marks) if marks else None)
    tab(page, "Parameters")
    rights = [round(e[1], 1) for e in edges(page, '#example tbody td[data-col="coulomb"] .dv-v')]
    marks = [round(e[0], 1) for e in edges(page, '#example tbody td[data-col="coulomb"] .dv-basis')]
    al["coulomb"] = (len(rights), max(rights) - min(rights) if rights else None, max(marks) - min(marks) if marks else None)
    ok = all(n >= 5 and r is not None and r <= 0.5 and m is not None and m <= 0.5 for n, r, m in al.values())
    check("models: aligned down a column: every number's right edge and every mark's left edge share one x (Benches' strips with and without counts, Parameters' basis marks), within 0.5 px",
          ok, {k: {"cells": n, "number spread px": r, "mark spread px": m} for k, (n, r, m) in al.items()})

    # sub-headers span exactly their columns
    spans = page.evaluate("""() => {
      const th = (sel) => document.querySelector(sel).getBoundingClientRect();
      const group = [...document.querySelectorAll('#example thead tr.dv-hgroup th')].find((t) => t.textContent.trim() === 'Friction');
      const g = group.getBoundingClientRect();
      return { colspan: group.colSpan, left: g.left - th('#example thead th[data-col="coulomb"]').left, right: g.right - th('#example thead th[data-col="weakening"]').right }; }""")
    tab(page, "Parameters · with CI")
    ci = page.evaluate("""() => {
      const th = (sel) => document.querySelector(sel).getBoundingClientRect();
      // the header over a stats column's parts says its unit once, "Coulomb (N·m)" (CONTRACT §28): found by its property
      const group = document.querySelector('#example thead th.dv-hg[data-prop="coulomb"]');
      const g = group.getBoundingClientRect();
      const leaves = [...document.querySelectorAll('#example thead th[data-sort="coulomb"][data-col]')].map((t) => t.querySelector('.dv-th-label').textContent.trim());
      return { colspan: group.colSpan, leaves, left: g.left - th('#example thead th[data-col="coulomb:value"]').left, right: g.right - th('#example thead th[data-col="coulomb:basis"]').right }; }""")
    check("models: sub-headers span exactly their columns (Friction over its 5 terms; Coulomb over value | 95% CI low | high | basis), measured",
          spans["colspan"] == 5 and abs(spans["left"]) < 1 and abs(spans["right"]) < 1 and ci["colspan"] == 4 and ci["leaves"] == ["value", "95% CI low", "high", "basis"] and abs(ci["left"]) < 1 and abs(ci["right"]) < 1,
          {"friction": spans, "coulomb": ci})
    ctx.shot(page, "models-parameters-ci-light-1440")

    # a model name links to its page (pivot), and its peek shows the README at the fit commit (leaderboard)
    tab(page, "Benches")
    href = page.evaluate("""() => { const a = [...document.querySelectorAll('#example tbody td[data-col=variant] a')].find((x) => x.textContent.trim() === 'M4.ripple.c1'); return a ? a.getAttribute('href') : null; }""")
    check("models: a model's name in the pivot is a real link to its page", href is not None and href.endswith("robotparts-model/index.html?variant=" + urllib.parse.quote("M4.ripple.c1", safe="")), href)
    page.check("data-facets input[data-p=actuator][data-value='CAN 14 · GIM4305-10']")
    tab(page, "Leaderboard")
    page.click(f"{V} .dv-tools [data-menu=rollup]")
    page.click(f"{V} .dv-pop [data-roll=none]")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    cell(page, "M4.ripple.c1", "rung").click()
    page.wait_for_selector(f"{V} .dv-peek:not([hidden]) .dv-md", timeout=10000)
    peek = page.inner_text(f"{V} .dv-peek")
    rev, line = oracle.readme_line(14) if oracle.available() else ("", "")
    check("models: a model's peek shows what it is, its fit commit and the twin code's README at that commit (read with git, not from models.json)",
          (not rev or (rev[:10] in peek and line[:60] in " ".join(peek.split()))) and "ripple_map" in peek, {"commit": rev[:10], "readme": line[:60], "peek starts": peek[:120]})
    ctx.shot(page, "models-peek-readme-light-1440")
    page.context.close()

    # the model's own page
    page = ctx.page("gallery/robotparts-model/index.html?variant=" + urllib.parse.quote("M4.ripple.c1", safe=""), width=1440, height=1000)
    page.wait_for_selector(f"{V} .dv-record-sheet .dv-md", timeout=15000)
    sheet = " ".join(page.inner_text(f"{V} .dv-record-sheet").split())
    heads = page.eval_on_selector_all(f"{V} .dv-record-sheet .dv-md :is(h2, h3)", "hs => hs.map((h) => h.textContent)")
    on = sorted({r["actuator"] for r in DATA["rows"] if r["kind"] == "model" and r["variant"] == "M4.ripple.c1"})
    check("model page: ?variant=M4.ripple.c1 opens its record with the README rendered as markdown (its headings, its first paragraph) and its commit",
          (not rev or (line[:60] in sheet and rev[:10] in sheet)) and "bam_rack_twin" in heads and "Run it" in heads and page.inner_text(f"{V} .dv-status").startswith(f"{len(on)} of"),
          {"headings": heads[:4], "status": page.inner_text(f"{V} .dv-status")[:30], "actuators": on})
    ctx.shot(page, "model-page-light-1440")
    page.context.close()

    # the rail drags wider, measured
    page = ctx.page(path, width=1440, height=1000)
    page.evaluate("try { localStorage.clear(); } catch {}")
    w0 = page.locator("data-facets").bounding_box()["width"]
    h = page.locator(".dv-splitter-right").bounding_box()
    page.mouse.move(h["x"] + h["width"] / 2, h["y"] + 200)
    page.mouse.down()
    page.mouse.move(h["x"] + 120, h["y"] + 200, steps=8)
    page.mouse.up()
    page.wait_for_timeout(200)
    w1 = page.evaluate("document.querySelector('data-facets').getBoundingClientRect().width")
    check("models: the rail is drag-resizable (+120 px drag, measured)", w1 - w0 > 100, {"before": w0, "after": w1})
    page.context.close()

    for dark in (False, True):
        for width, mobile in ((1440, False), (390, True)):
            p = ctx.page(path, width=width, height=1000 if width > 400 else 844, dark=dark, mobile=mobile)
            if width == 390:
                sw_ = p.evaluate("document.scrollingElement.scrollWidth")
                check(f"models, {'dark' if dark else 'light'}, 390 px: no sideways page scroll", sw_ <= 390, f"scrollWidth {sw_}")
            p.evaluate("document.querySelector('section.live').scrollIntoView()")
            ctx.shot(p, f"models-{'dark' if dark else 'light'}-{width}")
            p.context.close()
