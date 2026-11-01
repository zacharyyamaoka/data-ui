"""Browser checks for the admin-shopify case (run by tests/browser/checks.py): the summary card's numbers against the
data file (read here, not through the kit), its hairlines and its definition tooltip; the table card (frame="card"),
its pager under the card, the avatar chips, "+N" tags and short dates; search="expand" (Search and filter, Cancel, the
"+ Kind" chip and its values); the app page's rail (the Deals count from the data, sub-destinations); the gallery page's
<data-summary>; light and dark at 1280 px and the phone at 390 px (docs/CONTRACT.md §43)."""

import datetime
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
ORGS = json.loads((HERE / "organizations.json").read_text())["rows"]
DEALS = json.loads((HERE / "deals.json").read_text())["rows"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
V = "#list"


def short(iso, today):
    """The oracle for the date display: "Apr 10" in this year, "Jul 25, 2023" in another (Today/Yesterday/Tomorrow)."""
    d = datetime.date.fromisoformat(iso)
    diff = (d - today).days
    if diff in (-1, 0, 1):
        return {-1: "Yesterday", 0: "Today", 1: "Tomorrow"}[diff]
    md = f"{MONTHS[d.month - 1]} {d.day}"
    return md if d.year == today.year else f"{md}, {d.year}"


def app(ctx, path, hash_, dark=False, width=1280, height=900, mobile=False):
    """The app page. WHY not ctx.page(): it waits for a visible status line, and the app turns it off (status="off"),
    as Shopify has none; the same foreign-request and script-error gates are kept here."""
    url = f"{path.rsplit('/', 1)[0]}/app/index.html?theme={'dark' if dark else 'light'}{hash_}"
    context = ctx.browser.new_context(viewport={"width": width, "height": height}, color_scheme="dark" if dark else "light",
                                      device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    page = context.new_page()
    page.ctx = ctx
    page.on("request", lambda r: ctx.foreign.append(r.url) if not r.url.startswith(ctx.base) and not r.url.startswith(("data:", "blob:")) else None)
    page.on("pageerror", lambda e: ctx.errors.append(f"{url}: {e}"))
    page.on("console", lambda m: ctx.errors.append(f"{url}: console {m.text}") if m.type == "error" else None)
    page.goto(f"{ctx.base}/{url}")
    page.wait_for_load_state("networkidle")
    ctx.until(page, "() => { const s = document.querySelector('data-summary'); return s && s.cells.length && document.querySelector('#list .dv-row'); }")
    ctx.frames(page)
    return page


def summary(page):
    return page.evaluate("""() => [...document.querySelectorAll('data-summary .dv-summary-cell')].map((c) => ({
      label: c.querySelector('.dv-summary-label').textContent, value: c.querySelector('.dv-summary-value').textContent,
      top: Math.round(c.getBoundingClientRect().top), left: Math.round(c.getBoundingClientRect().left),
      rule: getComputedStyle(c).borderLeftWidth, dotted: getComputedStyle(c.querySelector('.dv-summary-label')).borderBottomStyle }))""")


def rows(page):
    return page.evaluate(f"() => [...document.querySelectorAll('{V} tbody tr.dv-row')].map((tr) => [...tr.querySelectorAll('td:not(.dv-selcol)')].map((td) => td.textContent.trim()))")


def run(ctx, path):
    check = ctx.check
    today = datetime.date.today()
    kinds = {k: sum(1 for r in ORGS if r["kind"] == k) for k in ("Customer", "Prospect", "Competitor")}
    want_orgs = [["Organizations", str(len(ORGS))], ["Customers", str(kinds["Customer"])], ["Prospects", str(kinds["Prospect"])], ["Competitors", str(kinds["Competitor"])]]

    for dark in (False, True):
        tag = "dark" if dark else "light"
        page = app(ctx, path, "#organizations", dark=dark)
        cells = summary(page)
        check(f"admin {tag}: the summary card reads the counts of organizations.json (14, then each kind)", [[c["label"], c["value"]] for c in cells] == want_orgs, [[c["label"], c["value"]] for c in cells])
        check(f"admin {tag}: the cells sit side by side, a 1 px hairline before each but the first, every label dotted",
              len({c["top"] for c in cells}) == 1 and [c["rule"] for c in cells] == ["0px", "1px", "1px", "1px"] and all(c["dotted"] == "dotted" for c in cells), cells)
        got = rows(page)
        first = got[0] if got else []
        alder = next(r for r in ORGS if r["name"] == "Alderbank Medical Waste")
        check(f"admin {tag}: 14 rows A to Z, the first an avatar chip AM before the bold name",
              len(got) == 14 and [r[0][2:] for r in got] == sorted(r["name"] for r in ORGS) and first[0] == "AMAlderbank Medical Waste"
              and page.evaluate(f"() => {{ const a = document.querySelector('{V} .dv-avatar'), r = a.getBoundingClientRect(); return r.width === 20 && r.height === 20 && getComputedStyle(a).borderRadius === '50%' && +getComputedStyle(a.nextElementSibling).fontWeight >= 600; }}"),
              first)
        avatars = page.evaluate(f"() => [...document.querySelectorAll('{V} tbody tr.dv-row')].map((tr) => [tr.querySelector('td:nth-child(3)').textContent.trim(), getComputedStyle(tr.querySelector('.dv-avatar')).backgroundColor])")
        by = {}
        for kind, colour in avatars:
            by.setdefault(kind, set()).add(colour)
        check(f"admin {tag}: an avatar's colour follows the organization's kind (avatar.colors): one colour per kind, three kinds, three colours",
              all(len(v) == 1 for v in by.values()) and len({next(iter(v)) for v in by.values()}) == 3, {k: sorted(v) for k, v in by.items()})
        tags = page.evaluate(f"() => {{ const td = document.querySelector('{V} tbody tr.dv-row td[data-col=tags]'); return [td.querySelectorAll('.dv-badge').length, td.querySelector('.dv-badge-more').textContent, td.title]; }}")
        check(f"admin {tag}: a tag list shows two pills then +2, every tag in its title (maxBadges: 2)",
              tags == [2, "+2", ", ".join(alder["tags"])], tags)
        dates = {r[0][2:]: r[7] for r in got}
        want_dates = {r["name"]: short(r["last_activity"], today) if r["last_activity"] else "—" for r in ORGS}
        check(f"admin {tag}: Last activity reads as the admin writes it (Apr 10 this year, Jul 25, 2023 in another), the stored date in the title",
              dates == want_dates and page.evaluate(f"() => document.querySelector('{V} tbody tr.dv-row td[data-col=last_activity]').title") == alder["last_activity"], dates)
        card = page.evaluate(f"""() => {{ const el = document.querySelector('{V}'), b = getComputedStyle(el, '::before'), sc = el.querySelector('.dv-scroll').getBoundingClientRect(),
          p = el.querySelector('.dv-pager'), pr = p.getBoundingClientRect(), er = el.getBoundingClientRect();
          return {{ radius: b.borderTopLeftRadius, cardBottom: Math.round(er.bottom - parseFloat(b.bottom)), scrollBottom: Math.round(sc.bottom), pagerTop: Math.round(pr.top), pagerLeft: Math.round(pr.left - er.left),
            text: p.querySelector('.dv-pager-range').textContent, prev: p.querySelector('[data-page=\"-1\"]').disabled, next: p.querySelector('[data-page=\"1\"]').disabled }}; }}""")
        check(f"admin {tag}: the table card is one 12 px-rounded card ending at the last row; the pager ‹ 1–14 › floats 12 px under it at its left, both arrows off",
              card["radius"] == "12px" and abs(card["cardBottom"] - card["scrollBottom"]) <= 1 and card["pagerTop"] - card["cardBottom"] == 12 and card["pagerLeft"] == 0
              and card["text"] == "1–14" and card["prev"] and card["next"], card)
        page.hover("data-summary .dv-summary-cell:nth-child(2) .dv-summary-label")
        ctx.frames(page, 12)
        tip = page.evaluate("() => { const t = document.querySelector('data-summary .dv-summary-cell:nth-child(2) .dv-summary-tip'); return [getComputedStyle(t).visibility, t.textContent, t.getBoundingClientRect().top > document.querySelector('data-summary .dv-summary-cell:nth-child(2) .dv-summary-label').getBoundingClientRect().bottom - 4]; }")
        check(f"admin {tag}: hovering a dotted label shows its definition under it", tip[0] == "visible" and tip[1].startswith("Organizations that buy from us") and tip[2], tip)
        ctx.shot(page, f"admin-shopify-organizations-{tag}-1280")
        page.mouse.move(5, 5)

        # search="expand": the quiet line opens into the box, Cancel and the facet chips
        rest = page.evaluate(f"() => [document.querySelector('{V} .dv-qinput').placeholder, getComputedStyle(document.querySelector('{V} .dv-qbox')).borderTopColor, getComputedStyle(document.querySelector('{V} .dv-qbox')).backgroundColor]")
        page.click(f"{V} .dv-qinput")
        ctx.frames(page, 4)
        st = page.evaluate(f"""() => {{ const el = document.querySelector('{V}'); return [el.querySelector('.dv-bar').classList.contains('dv-search-active'), el.querySelector('.dv-qinput').placeholder,
          !el.querySelector('.dv-qcancel').hidden && el.querySelector('.dv-qcancel').getBoundingClientRect().width > 0, el.querySelector('.dv-bar-tools').getBoundingClientRect().width,
          [...el.querySelectorAll('.dv-fchip')].map((c) => c.textContent.trim()), !el.querySelector('.dv-suggest') || el.querySelector('.dv-suggest').hidden]; }}""")
        check(f"admin {tag}: Search and filter rests as a borderless line, then opens into 'Searching all organizations' with Cancel in Display's place, a + chip per facet and no hint list until typing",
              rest[0] == "Search and filter" and rest[1] in ("rgba(0, 0, 0, 0)", "transparent") and st[0] and st[1] == "Searching all organizations" and st[2] and st[3] == 0
              and st[4] == ["Kind", "Stage", "Place", "Tags"] and st[5], {"rest": rest, "open": st})
        page.click(f"{V} .dv-fchip-body[data-p=kind]")
        ctx.frames(page, 3)
        menu = page.evaluate(f"() => [...document.querySelectorAll('{V} .dv-fchip-menu label')].map((l) => l.textContent.trim())")
        ctx.drawn(page, lambda: page.check(f"{V} .dv-fchip-menu input[value=Customer]"), scope=V)
        ctx.frames(page, 3)
        after = page.evaluate(f"() => [document.querySelectorAll('{V} tbody tr.dv-row').length, document.querySelector('{V} .dv-fchip-on') && document.querySelector('{V} .dv-fchip-on').textContent.trim(), document.querySelector('{V} .dv-pager-range').textContent, document.querySelector('data-summary .dv-summary-value').textContent]")
        if not dark:
            ctx.shot(page, "admin-shopify-search-light-1280")
        check(f"admin {tag}: + Kind lists each kind with its count; ticking Customer leaves its 3 rows, the chip reads 'Kind: Customer', the pager 1–3, the summary's totals stay 14",
              sorted(menu) == sorted(f"{k}{n}" for k, n in kinds.items()) and after == [kinds["Customer"], "Kind: Customer", "1–3", "14"], {"menu": menu, "after": after})
        page.keyboard.press("Escape")
        ctx.drawn(page, lambda: page.click(f"{V} .dv-qcancel"), scope=V)
        ctx.frames(page, 3)
        back = page.evaluate(f"() => [document.querySelectorAll('{V} tbody tr.dv-row').length, document.querySelector('{V} .dv-bar').classList.contains('dv-search-active'), document.querySelector('{V} .dv-fchips').hidden, document.querySelector('{V} .dv-qinput').placeholder, JSON.stringify(document.querySelector('{V}').filters ?? null)]")
        check(f"admin {tag}: Cancel clears the facet filter and the words and folds the search back to its line", back[:4] == [14, False, True, "Search and filter"] and back[4] in ("null", '{"and":[]}', "[]"), back)
        # the chip is the view picker: Competitors is a saved table view of the file
        ctx.drawn(page, lambda: page.evaluate(f"() => document.querySelector('{V}').selectView('Competitors')"), scope=V)
        chip = page.evaluate(f"() => [document.querySelector('{V} .dv-viewchip').textContent.trim(), document.querySelectorAll('{V} tbody tr.dv-row').length]")
        check(f"admin {tag}: the view chip shows the open view's name and switches the table's saved views (Competitors: 5 rows)", chip == ["Competitors", kinds["Competitor"]], chip)
        page.context.close()

        # the Deals page: its summary from deals.json, the rail's Deals count and sub-destinations
        page = app(ctx, path, "#pipeline", dark=dark)
        open_ = [r for r in DEALS if r["stage"] not in ("Won", "Lost")]
        this_month = sum(1 for r in open_ if r["due"] and r["due"][:7] == today.isoformat()[:7])
        upcoming = sorted(r["due"] for r in open_ if r["due"] and r["due"] >= today.isoformat())
        want = [["Open deals", str(len(open_))], ["Due this month", str(this_month)], ["Next due", short(upcoming[0], today) if upcoming else "—"], ["Won", str(sum(1 for r in DEALS if r["stage"] == "Won"))]]
        cells = summary(page)
        check(f"admin {tag}: the Deals summary reads deals.json against today ({today}): open, due this month, the next due date, won", [[c["label"], c["value"]] for c in cells] == want, {"got": [[c["label"], c["value"]] for c in cells], "want": want})
        nav = page.evaluate("""() => { const r = document.querySelector('#nav'); const vis = (id) => { const a = r.querySelector(`.dv-rail-dest[data-id="${id}"]`); return !!a && a.getBoundingClientRect().height > 0; };
          return { badge: r.querySelector('.dv-rail-dest[data-id=deals] .dv-rail-badge') && r.querySelector('.dv-rail-dest[data-id=deals] .dv-rail-badge').textContent,
            current: r.querySelector('[aria-current=page]') && r.querySelector('[aria-current=page]').dataset.id, section: r.querySelector('.dv-rail-section') && r.querySelector('.dv-rail-section').dataset.id,
            subs: ['pipeline', 'won', 'lost', 'organizations', 'people'].map(vis) }; }""")
        check(f"admin {tag}: the rail's Deals row counts the open deals in the data ({len(open_)}); Pipeline is current under the Deals section; only Deals' subs show",
              nav == {"badge": str(len(open_)), "current": "pipeline", "section": "deals", "subs": [True, True, True, False, False]}, nav)
        wrap = page.evaluate(f"() => [...document.querySelectorAll('{V} tbody td:not(.dv-selcol)')].every((td) => getComputedStyle(td).whiteSpace === 'nowrap' && td.getBoundingClientRect().height <= 45)")
        check(f"admin {tag}: a long deal title stays on one line with an ellipsis (no wrapped rows in the card)", wrap, wrap)
        ctx.shot(page, f"admin-shopify-deals-{tag}-1280")
        # the rail's wide style is a side panel (CONTRACT §11, §27): a drag moves its edge, measured
        handle = page.locator("#nav + .dv-splitter, .dv-splitter").first
        before = page.evaluate("() => document.querySelector('#nav').getBoundingClientRect().width")
        box = handle.bounding_box()
        if box:
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 200)
            page.mouse.down()
            page.mouse.move(box["x"] + 40, box["y"] + 200, steps=6)
            page.mouse.up()
        after = page.evaluate("() => document.querySelector('#nav').getBoundingClientRect().width")
        check(f"admin {tag}: the sidebar's edge drags (240 → about 280 px, measured)", box is not None and 30 <= after - before <= 50, [before, after])
        page.evaluate("() => { try { localStorage.removeItem('data-ui/panel-width/app-rail:admin-shopify'); } catch {} }")
        page.context.close()

    # the phone: the rail folded to icons, no sideways page scroll, the summary two by two
    page = app(ctx, path, "#organizations", width=390, height=844, mobile=True)
    page.evaluate("() => { document.querySelector('#nav').mode = 'collapsed'; }")
    ctx.frames(page, 4)
    phone = page.evaluate("""() => ({ scroll: document.scrollingElement.scrollWidth, tops: [...document.querySelectorAll('data-summary .dv-summary-cell')].map((c) => Math.round(c.getBoundingClientRect().top)),
      pager: !!document.querySelector('#list .dv-pager:not([hidden])') })""")
    check("admin 390 px: no sideways page scroll; the summary wraps to two rows of two; the pager shows",
          phone["scroll"] <= 390 and len(set(phone["tops"])) == 2 and phone["tops"][0] == phone["tops"][1] and phone["pager"], phone)
    ctx.shot(page, "admin-shopify-organizations-light-390")
    page.context.close()

    # the gallery page: the same file, its <data-summary> above the case's <data-views>
    page = ctx.page(path, width=1280)
    ctx.until(page, "() => { const s = document.querySelector('data-summary'); return s && s.cells.length; }")
    g = page.evaluate("() => { const s = document.querySelector('data-summary'), v = document.querySelector('#example'); return [s.cells.map((c) => c.value), s.getBoundingClientRect().bottom <= v.getBoundingClientRect().top, v.getAttribute('frame')]; }")
    check("admin gallery page: the case page draws the file's summary card above its card-framed table", g == [[14, 3, 6, 5], True, "card"], g)
    ctx.shot(page, "admin-shopify-gallery-light-1280")
    page.context.close()
