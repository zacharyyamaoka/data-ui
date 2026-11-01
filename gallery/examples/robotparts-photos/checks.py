"""Browser checks for this case (run by tests/browser/checks.py): the cards view (lanes, group headings, a logo
drawn as an image, the peek, keyboard moves, its Layout settings), virtualisation at 1,149 cards (the actuators
case's data), the media grid's lightbox and its provenance caption, and the page light and dark at 1280 and 390 px."""

import time

V = "#example"


def open_page(ctx, path, width=1280, height=900, dark=False, mobile=False):
    """ctx.page() waits for the status line; the view's own code loads after it, so wait for its first card too."""
    page = ctx.page(path, width=width, height=height, dark=dark, mobile=mobile)
    page.wait_for_selector(f"{V} .dv-cards-card", timeout=15000)
    return page


def lum(rgb):
    r, g, b = (int(x) for x in rgb[rgb.index("(") + 1:rgb.index(")")].split(",")[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def boxes(page, sel):
    return page.evaluate(f"[...document.querySelectorAll('{sel}')].map((e) => {{ const b = e.getBoundingClientRect(); return [b.left, b.top, b.width, b.height]; }})")


def run(ctx, path):
    check = ctx.check
    page = open_page(ctx, path)
    page.locator(V).evaluate("el => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 64)")
    # the cards' photos and the logos load lazily, after the scroll: wait for them to finish (or fail), not a pause
    ctx.until(page, "() => { const imgs = [...document.querySelectorAll('#example .dv-cards-img img, #example img.dv-cards-inline')]; return imgs.some((i) => i.complete && i.naturalWidth) && imgs.filter((i) => i.getBoundingClientRect().top < innerHeight).every((i) => i.complete); }")
    status = page.inner_text(f"{V} .dv-status")
    cards = boxes(page, f"{V} .dv-cards-card")
    heads = page.locator(f"{V} .dv-cards-head").all_inner_texts()
    rows = sorted({round(b[1]) for b in cards})
    overlap = any(a is not b and a[0] < b[0] + b[2] - 1 and b[0] < a[0] + a[2] - 1 and a[1] < b[1] + b[3] - 1 and b[1] < a[1] + a[3] - 1 for a in cards for b in cards)
    check("cards: the Actuators view draws 96 cards in lanes under brand headings, no two overlapping, each at least cardSize (190 px) wide",
          status.startswith("96 of 175") and len(cards) < 40 and heads and not overlap and min(b[2] for b in cards) >= 190 and len(rows) < len(cards),
          f"{status.split(' · ')[0]}; {len(cards)} in the DOM, {len(heads)} headings, first {heads[0].replace(chr(10), ' ') if heads else '-'}, card {cards[0][2]:.0f}x{cards[0][3]:.0f}")
    loaded = page.evaluate("[...document.querySelectorAll('#example .dv-cards-img img')].filter((i) => i.complete).map((i) => i.naturalWidth > 0)")
    logos = page.evaluate("[...document.querySelectorAll('#example img.dv-cards-inline')].filter((i) => i.complete).map((i) => i.naturalWidth)")
    check("cards: the hosted photos load, and a brand's logo draws inside the card (display: image)", loaded and all(loaded) and logos and all(logos),
          f"{sum(loaded)} photos, {len(logos)} logos loaded")

    # ---- the media grid: lightbox, caption with provenance, arrows, Esc
    page.locator(f"{V} .dv-cards-card [data-zoom]").first.click()
    page.wait_for_selector(".pswp--open img.pswp__img", timeout=30000)
    ctx.until(page, "() => { const i = document.querySelector('.pswp__item[aria-hidden=false] img.pswp__img'); const c = document.querySelector('.dv-cards-caption'); return i && i.complete && i.naturalWidth > 0 && c && c.innerText.includes('accessed'); }")
    cap1 = page.inner_text(".dv-cards-caption")
    counter = page.inner_text(".pswp__counter")
    img = page.evaluate("(() => { const i = document.querySelector('.pswp__item[aria-hidden=false] img.pswp__img'); return i && [i.naturalWidth, i.getBoundingClientRect().width]; })()")
    check("media grid: a photo opens full screen (PhotoSwipe inside <data-views>), its caption naming the part, a property and 'source · accessed date'",
          "accessed 2026-" in cap1 and " · " in cap1.split("\n")[0] and counter.endswith("/ 96") and img and img[0] > 0 and page.locator(f"{V} .pswp").count() == 1,
          cap1.replace("\n", " | "))
    page.keyboard.press("ArrowRight")
    ctx.until(page, "(before) => { const c = document.querySelector('.dv-cards-caption'); return c && c.innerText !== before; }", cap1)
    cap2 = page.inner_text(".dv-cards-caption")
    page.keyboard.press("Escape")
    # WHY the state: Esc closes PhotoSwipe after its own fade; a fixed 600 ms missed it under load (2026-10-26 run)
    ctx.until(page, "() => !document.querySelector('.pswp--open') && document.activeElement && document.activeElement.matches('[data-zoom]')")
    focus = page.evaluate("document.activeElement && document.activeElement.matches('[data-zoom]')")
    check("media grid: → shows the next card's photo and caption; Esc closes and returns focus to a card's image",
          cap2 != cap1 and page.locator(".pswp--open").count() == 0 and focus, cap2.split("\n")[0])

    # ---- the peek, the keyboard and the Layout settings
    page.locator(f"{V} .dv-cards-card .dv-cards-title").first.click()
    page.wait_for_selector(f"{V} .dv-peek:not([hidden])")
    peek = page.inner_text(f"{V} .dv-peek h2")
    first = page.locator(f"{V} .dv-cards-card").first
    check("cards: clicking a card's text opens the shared peek, and the card is marked", peek == first.locator(".dv-cards-title").inner_text() and "dv-active" in first.get_attribute("class"), peek)
    page.keyboard.press("Escape")
    first.focus()
    i0 = int(first.get_attribute("data-i"))
    page.keyboard.press("ArrowRight")
    ctx.until(page, "(i0) => +document.activeElement.dataset.i > i0", i0)
    i1 = page.evaluate("+document.activeElement.dataset.i")
    page.keyboard.press("ArrowDown")
    ctx.until(page, "(i1) => +document.activeElement.dataset.i > i1", i1)
    i2 = page.evaluate("+document.activeElement.dataset.i")
    check("cards: → and ↓ move focus card by card and lane by lane", i1 > i0 and i2 > i1, f"focus {i0} → {i1} → {i2}")
    page.click(f"{V} [data-menu=layout]")
    ctx.until(page, "() => document.querySelector('#example .dv-pop:not([hidden]) input[type=range]')")
    opts = page.locator(f"{V} .dv-pop [data-opt]").count()
    ctx.drawn(page, lambda: page.locator(f"{V} .dv-pop input[type=range]").last.evaluate("(el) => { el.value = 320; el.dispatchEvent(new Event('change', { bubbles: true })); }"))
    page.keyboard.press("Escape")
    wide = boxes(page, f"{V} .dv-cards-card")
    check("cards: Layout shows the cards' settings (image, fit, aspect, card size, lightbox); Card size 320 redraws wider cards",
          opts == 6 and page.evaluate("document.querySelector('#example').view.cardSize") == 320 and min(b[2] for b in wide) >= 320, f"{opts} settings; cards now {wide[0][2]:.0f} px")
    page.context.close()

    # ---- virtualisation at 1,149 cards: the actuators case's own data
    page = open_page(ctx, path)
    ms = page.evaluate("""async () => {
      const el = document.querySelector('#example');
      const data = await (await fetch('../robotparts-actuators/actuators.json')).json();
      el.data = data;
      const t = performance.now();
      const drawn = new Promise((done) => el.addEventListener('data-views-render', (e) => done(performance.now() - t), { once: true }));
      el.base = { views: [{ type: 'cards', name: 'Every actuator', order: ['model', 'brand', 'peak_torque', 'mass'], cardSize: 180 }] };
      return drawn;
    }""")
    ctx.frames(page)
    status = page.inner_text(f"{V} .dv-status")
    dom = page.locator(f"{V} .dv-cards-card").count()
    page.locator(f"{V} .dv-cards-scroll").evaluate("el => el.scrollTo(0, el.scrollHeight)")
    ctx.until(page, "() => [...document.querySelectorAll('#example .dv-cards-card')].some((c) => +c.dataset.i === 1148)")
    last = page.evaluate("Math.max(...[...document.querySelectorAll('#example .dv-cards-card')].map((c) => +c.dataset.i))")
    dom_end = page.locator(f"{V} .dv-cards-card").count()
    check("cards: 1,149 actuators as cards keep only the visible ones in the DOM, and scrolling reaches the last",
          "1,149 of 1,149" in status and dom < 100 and dom_end < 100 and last == 1148, f"{dom} cards in the DOM at the top, {dom_end} at the bottom; last index {last}; drawn in {ms:.0f} ms")
    page.context.close()

    # ---- light and dark, 1280 and 390
    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            name = f"robotparts-photos-{'dark' if dark else 'light'}-{width}"
            p = open_page(ctx, path, width=width, height=900 if not mobile else 844, dark=dark, mobile=mobile)
            p.locator(V).evaluate("el => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 64)")
            ctx.frames(p)
            scroll = p.evaluate("document.scrollingElement.scrollWidth")
            inner = p.locator(f"{V} .dv-cards-scroll").evaluate("el => [el.scrollWidth, el.clientWidth]")
            bg = p.evaluate("getComputedStyle(document.querySelector('#example .dv-cards-card')).backgroundColor")
            card = boxes(p, f"{V} .dv-cards-card")[0]
            check(f"cards, {'dark' if dark else 'light'}, {width} px: no sideways scroll on the page or in the grid; cards in the theme",
                  scroll <= width and inner[0] <= inner[1] and (lum(bg) < 40 if dark else lum(bg) > 240) and card[2] >= 190,
                  f"page {scroll}, grid {inner[0]}/{inner[1]}, card {card[2]:.0f} px, {bg}")
            ctx.shot(p, name)
            p.context.close()
