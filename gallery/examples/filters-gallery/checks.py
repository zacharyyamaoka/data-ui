"""Browser checks for the Filters case (run by tests/browser/checks.py): every facet kind is used once, the way a
person uses it (a click, a key, a drag's release), and the table's row count must equal the count this file works out
from actuators.json itself, in Python: an oracle that shares no code with the rail. Then the URL, a reload, the
recipes, an unknown kind, keyboard focus, and each kind's group in light and dark at 1280 and 390 px."""

from __future__ import annotations

import datetime
import json
import pathlib
import re

V = "#example"
R = "data-facets"
HERE = pathlib.Path(__file__).resolve().parent
ROWS = json.loads((HERE / "actuators.json").read_text(encoding="utf-8"))["rows"]


def val(row, p):
    v = row.get(p)
    return v.get("value") if isinstance(v, dict) and "value" in v else v


def n(pred):
    return sum(1 for r in ROWS if pred(r))


def num(row, p):
    v = val(row, p)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def shown(page):
    text = page.inner_text(f"{V} .dv-status")
    m = re.match(r"([\d,]+) of", text)
    return int(m.group(1).replace(",", "")) if m else -1


def settle(page):
    page.wait_for_timeout(260)


def clear(page):
    if page.locator(f"{R} .df-box > summary [data-clear]").count():
        page.click(f"{R} .df-box > summary [data-clear]")
        settle(page)


def group(kind, prop=None):
    sel = f"{R} .df-group.df-as-{kind}"
    return sel + (f"[data-p='{prop}']" if prop else "")


def param(page, key):
    return page.evaluate(f"new URLSearchParams(location.search).getAll({json.dumps(key)})")


def run(ctx, path):
    check = ctx.check
    page = ctx.page(path)
    page.wait_for_selector(f"{R} .df-group", timeout=15000)
    kinds = page.evaluate(f"[...new Set([...document.querySelectorAll('{R} .df-group')].map(g => [...g.classList].find(c => c.startsWith('df-as-')).slice(6)))]")
    check("filters: one rail draws all 21 kinds", len(kinds) == 21, f"{len(kinds)}: {kinds}")

    def kind(name, act, expected, extra=""):
        clear(page)
        act()
        settle(page)
        got = shown(page)
        check(f"filters · {name}: the rows equal the oracle's count", got == expected, f"{got} shown, {expected} expected{extra}")

    kind("values (a brand)", lambda: page.check(f"{group('values', 'brand')} input[data-value=Steadywin]"), n(lambda r: r["brand"] == "Steadywin"))
    kind("values, exclude (not KST)", lambda: page.click(f"{group('values', 'brand')} [data-act=exclude][data-value=KST]"), n(lambda r: r["brand"] != "KST"))
    check("filters · exclude reads as brand!=KST in the URL", param(page, "brand!") == ["KST"] and "brand!=KST" in page.evaluate("location.search"), page.evaluate("location.search"))
    kind("select (Stock: no)", lambda: page.check(f"{group('select', 'in_stock')} input[data-value=no]"), n(lambda r: r["in_stock"] == "no"))
    kind("toggle (In stock only)", lambda: page.click(f"{group('toggle', 'in_stock')} .df-switch"), n(lambda r: r["in_stock"] == "yes"))
    kind("toggle on a list (Has CAD)", lambda: page.click(f"{group('toggle', 'checks')} .df-switch"), n(lambda r: "cad" in (r["checks"] or [])))
    kind("has, all of (photo and price)", lambda: (page.check(f"{group('has')} input[data-has=photo]"), settle(page), page.check(f"{group('has')} input[data-has=price]")),
         n(lambda r: val(r, "photo") and num(r, "price") is not None))
    kind("has, any of (photo or price)", lambda: (page.check(f"{group('has')} input[data-has=photo]"), settle(page), page.check(f"{group('has')} input[data-has=price]"), settle(page),
                                                  page.check(f"{group('has')} input[value=any]")), n(lambda r: val(r, "photo") or num(r, "price") is not None))
    kind("buckets (price 50–100)", lambda: page.click(f"{group('buckets', 'price')} .df-chip:has-text('50–100')"), n(lambda r: num(r, "price") is not None and 50 <= num(r, "price") < 100))
    kind("range with choices (Zillow: price 100 to 500)", lambda: (page.select_option(f"{group('range', 'price')} select[data-min]", "100"), settle(page),
                                                                   page.select_option(f"{group('range', 'price')} select[data-max]", "500")), n(lambda r: num(r, "price") is not None and 100 <= num(r, "price") <= 500))
    kind("range with a diagram (OD 50 to 100 mm)", lambda: (page.fill(f"{group('range', 'od')} input[data-min]", "50"), page.dispatch_event(f"{group('range', 'od')} input[data-min]", "change"), settle(page),
                                                           page.fill(f"{group('range', 'od')} input[data-max]", "100"), page.dispatch_event(f"{group('range', 'od')} input[data-max]", "change")),
         n(lambda r: num(r, "od") is not None and 50 <= num(r, "od") <= 100))

    # sliders: the keyboard moves a thumb (the platform's own range input), release commits; the URL says where to
    clear(page)
    thumb = f"{group('slider-histogram', 'peak_torque')} input[data-side=min]"
    page.focus(thumb)
    for _ in range(4):
        page.keyboard.press("PageUp")
    settle(page)
    lo = param(page, "peak_torque")
    low = float(lo[0].split("..")[0]) if lo else None
    check("filters · slider-histogram: PageUp on the min thumb sets a bound; the rows equal the oracle's count",
          low is not None and shown(page) == n(lambda r: num(r, "peak_torque") is not None and num(r, "peak_torque") >= low), f"peak_torque={lo}; {shown(page)} shown")
    bars = page.evaluate(f"[document.querySelectorAll('{group('slider-histogram')} .df-bar').length, document.querySelectorAll('{group('slider-histogram')} .df-bar.df-in').length]")
    check("filters · slider-histogram: 24 bars, those outside the range dimmed; each bar's count on hover (title)",
          bars[0] == 24 and 0 < bars[1] < 24 and page.locator(f"{group('slider-histogram')} svg title").count() == 24, bars)
    check("filters · slider: focus stays on the thumb across the redraw (keyboard users keep their place)",
          page.evaluate("document.activeElement && document.activeElement.dataset.side") == "min")
    clear(page)
    page.focus(f"{group('slider', 'mass')} input[data-side=max]")
    for _ in range(3):
        page.keyboard.press("PageDown")
    settle(page)
    hi = param(page, "mass")
    high = float(hi[0].split("..")[1]) if hi else None
    check("filters · slider (log mass): PageDown on the max thumb; the rows equal the oracle's count",
          high is not None and shown(page) == n(lambda r: num(r, "mass") is not None and num(r, "mass") <= high), f"mass={hi}; {shown(page)} shown")

    kind("rating (level ≥ 2 & up)", lambda: page.click(f"{group('rating', 'level')} [data-level='2']"), n(lambda r: (num(r, "level") or 0) >= 2))
    week = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    kind("date (last 7 days)", lambda: page.click(f"{group('date', 'listed')} [data-act=date-from]:has-text('Last 7 days')"), n(lambda r: r["listed"] and r["listed"] >= week), f"; since {week}")
    old = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
    kind("date (older than 14 days)", lambda: page.click(f"{group('date', 'listed')} [data-act=date-older]:has-text('14 days')"), n(lambda r: r["listed"] and r["listed"] < old))
    kind("chips (CAN or EtherCAT)", lambda: (page.click(f"{group('chips', 'buses')} [data-value=can]"), settle(page), page.click(f"{group('chips', 'buses')} [data-value=ethercat]")),
         n(lambda r: bool({"can", "ethercat"} & set(r["buses"] or []))))
    kind("swatch (a brand's logo)", lambda: page.click(f"{group('swatch', 'brand')} [data-value=Steadywin]"), n(lambda r: r["brand"] == "Steadywin"))
    check("filters · swatch and values share one state: the Steadywin box is ticked too", page.is_checked(f"{group('values', 'brand')} input[data-value=Steadywin]"))
    logos = page.evaluate(f"[...document.querySelectorAll('{group('swatch')} img')].map(i => i.complete && i.naturalWidth > 0)")
    check("filters · swatch: robotparts' brand logos load (the rest are monograms)", len(logos) >= 1 and all(logos), logos)
    kind("gallery (form: hobby servo)", lambda: page.click(f"{group('gallery', 'form')} [data-value='hobby servo']"), n(lambda r: r["form"] == "hobby servo"))
    kind("picture-list (drivetrain: direct drive)", lambda: page.click(f"{group('picture-list', 'drivetrain')} [data-value=direct_drive]"), n(lambda r: r["drivetrain"] == "direct_drive"))
    kind("grid (gear ratio 9)", lambda: page.click(f"{group('grid', 'gear_ratio')} [data-value='9']"), n(lambda r: num(r, "gear_ratio") == 9))
    kind("listbox (voltage 24 and 48)", lambda: page.select_option(f"{group('listbox', 'voltage')} select", ["24", "48"]), n(lambda r: num(r, "voltage") in (24, 48)))
    kind("tree (hobby servo › Feetech)", lambda: (page.click(f"{group('tree')} [data-level='0'][data-value='hobby servo']"), settle(page), page.click(f"{group('tree')} [data-level='1'][data-value=Feetech]")),
         n(lambda r: r["form"] == "hobby servo" and r["brand"] == "Feetech"))
    kind("search (model or name contains 'gim')", lambda: (page.fill(f"{group('search')} input", "gim"), page.wait_for_timeout(300)),
         n(lambda r: "gim" in str(r["model"] or "").lower() or "gim" in str(r["name"] or "").lower()))
    check("filters · search reads as model~=gim in the URL", "model~=gim" in page.evaluate("location.search"), page.evaluate("location.search"))
    kind("popular (Under $100)", lambda: page.check(f"{group('popular')} input[data-i='2']"), n(lambda r: num(r, "price") is not None and num(r, "price") < 100))

    # current refinements: two picks, remove one by its chip, then Clear all
    clear(page)
    page.check(f"{group('values', 'brand')} input[data-value=Steadywin]")
    settle(page)
    page.click(f"{group('chips', 'buses')} [data-value=can]")
    settle(page)
    chips = page.locator(f"{group('current')} .df-chip").all_inner_texts()
    page.click(f"{group('current')} .df-chip:has-text('Steadywin')")
    settle(page)
    check("filters · current: a chip per pick; its ✕ removes just that one", len(chips) == 2 and shown(page) == n(lambda r: "can" in (r["buses"] or [])), f"{chips}; then {shown(page)}")

    # the URL, then a reload
    clear(page)
    page.check(f"{group('values', 'brand')} input[data-value=Steadywin]")
    settle(page)
    page.click(f"{group('buckets', 'price')} .df-chip:has-text('50–100')")
    settle(page)
    search = page.evaluate("decodeURIComponent(location.search)")
    before = shown(page)
    page.reload()
    page.wait_for_selector(f"{R} .df-group")
    settle(page)
    check("filters · the URL is readable (?brand=Steadywin&price=50..<100) and a reload keeps the selection",
          "brand=Steadywin" in search and "price=50..<100" in search and shown(page) == before and page.locator(f"{group('buckets', 'price')} [aria-pressed=true]").count() == 1, f"{search}; {before} -> {shown(page)}")

    # ⓘ and fold
    clear(page)
    page.click(f"{group('gallery', 'form')} .df-info")
    settle(page)
    help_text = page.inner_text(f"{group('gallery', 'form')} .df-help") if page.locator(f"{group('gallery', 'form')} .df-help").count() else ""
    page.click(f"{group('gallery', 'form')} .df-fold")
    settle(page)
    folded = page.locator(f"{group('gallery', 'form')} .df-tile").count() == 0 and page.get_attribute(f"{group('gallery', 'form')} .df-fold", "aria-expanded") == "false"
    check("filters · ⓘ shows the facet's help; the heading folds the group (aria-expanded)", "hobby servo" in help_text and folded, help_text[:40])
    check("filters · collapsed: true starts a group folded", page.get_attribute(f"{group('range', 'length')} .df-fold", "aria-expanded") == "false")
    check("filters · diagram: the OD facet draws its dimension drawing", page.locator(f"{group('range', 'od')} .df-diagram").count() == 1)

    # recipes: a view's own facets: replace the rail
    def recipe(name):
        page.click(f"{V} .dv-tab[data-name='{name}']")
        settle(page)
        return page.evaluate(f"[...document.querySelectorAll('{R} .df-group')].map(g => [...g.classList].find(c => c.startsWith('df-as-')).slice(6))")
    mc = recipe("McMaster-style")
    check("filters · McMaster recipe: form as a picture gallery, a diagram on the diameter, grids, a searchable brand list",
          mc[:2] == ["gallery", "picture-list"] and "grid" in mc and page.locator(f"{group('grid', 'od')} .df-diagram").count() == 1 and page.locator(f"{group('values', 'brand')} .df-find").count() == 1, mc)
    az = recipe("Amazon-style")
    check("filters · Amazon recipe: current, toggle, rating, buckets, values", az == ["current", "toggle", "rating", "buckets", "values"], az)
    dk = recipe("Digi-Key-style")
    check("filters · Digi-Key recipe: an in-stock toggle and multi-select listboxes", dk[0] == "toggle" and dk[1:] == ["listbox"] * 6, dk)
    ob = recipe("Obsidian-style")
    note = page.inner_text(R)
    check("filters · Obsidian recipe: no rail; the view's own filter is the builder's (Filter menu)", ob == [] and "No rail filters" in note, note[:80])
    page.click(f"{V} .dv-tab[data-name='Every kind']")
    settle(page)

    # the all-views filter holds a clause no facet draws: it shows as custom, never dropped
    page.evaluate("document.querySelector('#example').filters = { and: ['brand == \"KST\"', 'rated_torque > 0.5'] }")
    settle(page)
    custom = page.inner_text(f"{R} .df-custom") if page.locator(f"{R} .df-custom").count() else ""
    check("filters · a clause the rail cannot draw stays as '+1 custom filter'", "+1 custom filter" in custom and shown(page) == n(lambda r: r["brand"] == "KST" and (num(r, "rated_torque") or 0) > 0.5), f"{custom!r}; {shown(page)}")
    clear(page)

    # an unknown kind: drawn as values with a warning, nothing breaks
    page.evaluate("""() => { const el = document.querySelector('#example'); el.base = { ...el.base, facets: [{ property: 'brand', as: 'slidr' }, ...el.base.facets] }; }""")
    page.wait_for_selector(f"{R} .df-warn", timeout=5000)
    check("filters · an unknown kind ('slidr') draws as values and says so", "Unknown kind 'slidr'" in page.inner_text(f"{R} .df-warn") and page.locator(f"{R} .df-group").first.locator("input[type=checkbox]").count() > 3)
    page.context.close()

    # every kind's group, light and dark, desktop and phone: drawn, inside the rail, no sideways scroll
    out = []
    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            pg = ctx.page(path, width=width, height=900 if width > 400 else 844, dark=dark, mobile=mobile)
            pg.wait_for_selector(f"{R} .df-box")
            closed = pg.evaluate(f"!document.querySelector('{R} details').open")
            if width < 700:
                pg.click(f"{R} .df-box > summary")
                settle(pg)
            got = pg.evaluate(f"""() => {{
              const rail = document.querySelector('{R}').getBoundingClientRect();
              const groups = [...document.querySelectorAll('{R} .df-group')];
              const bad = groups.filter((g) => {{ const b = g.getBoundingClientRect(); return b.height < 20 || b.left < rail.left - 1 || b.right > rail.right + 1 || g.scrollWidth > g.clientWidth + 1; }})
                .map((g) => g.className);
              return {{ groups: groups.length, bad, sw: document.scrollingElement.scrollWidth, fg: getComputedStyle(document.querySelector('{R}')).color }};
            }}""")
            ok = got["groups"] == 25 and not got["bad"] and got["sw"] <= width and (closed if width < 700 else not closed)
            out.append((dark, width, ok, got["bad"][:3], got["sw"]))
            pg.context.close()
    check("filters · every kind's group draws inside the rail, light and dark, at 1280 and 390 (a closed disclosure on the phone)", all(o[2] for o in out), [o for o in out if not o[2]] or None)

    # every kind's readable link (kinds.html "Try it") opens the case with that filter on, and the panel lists them all
    kinds = json.loads((HERE / "source" / "kinds.json").read_text(encoding="utf-8"))["kinds"]
    bad = []
    for k in kinds:
        pg = ctx.page(path + k["try"])
        pg.wait_for_selector(f"{R} .df-group")
        settle(pg)
        got = shown(pg)
        if not 0 < got < len(ROWS) or "custom filter" in pg.inner_text(R):
            bad.append((k["kind"], k["try"], got))
        pg.context.close()
    check("filters · every kind's link (?brand=…, ?price=50..<100, ?model~=gim …) opens with that filter drawn in the rail", not bad, bad or len(kinds))
    pg = ctx.page(path.replace("index.html", "kinds.html"))
    listed = pg.locator(".kind").count()
    snippets = pg.evaluate("[...document.querySelectorAll('.kind pre code')].filter(c => c.textContent.includes('as:') || c.textContent.includes('diagram:')).length")
    check("filters · kinds.html lists every kind with the site it copies and its .base snippet", listed == len(kinds) and snippets == len(kinds), f"{listed} kinds, {snippets} snippets")
    pg.context.close()
