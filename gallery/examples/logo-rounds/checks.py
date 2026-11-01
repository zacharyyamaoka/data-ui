"""Browser checks for this case (run by tests/browser/checks.py): every round's SVGs as a media grid grouped by
round, the lightbox across all 203, a missing score with its reason, the paper-white wells in a dark theme, the
score ranking, and the page light and dark at 1280 and 390 px."""

V = "#example"


def open_page(ctx, path, width=1280, height=900, dark=False, mobile=False):
    """ctx.page() waits for the status line; the view's own code loads after it, so wait for its first card too."""
    page = ctx.page(path, width=width, height=height, dark=dark, mobile=mobile)
    page.wait_for_selector(f"{V} .dv-cards-card", timeout=15000)
    return page


def run(ctx, path):
    check = ctx.check
    page = open_page(ctx, path)
    page.locator(V).evaluate("el => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 64)")
    status = page.inner_text(f"{V} .dv-status")
    head = page.locator(f"{V} .dv-cards-head").first.inner_text().replace("\n", " ")
    svgs = page.evaluate("[...document.querySelectorAll('#example .dv-cards-img img')].filter((i) => i.complete).map((i) => i.naturalWidth > 0)")
    check("logo rounds: all 203 SVGs from 11 rounds, grouped by round, the visible ones drawn and loaded",
          status.startswith("203 of 203 rows · 11 groups") and head == "Round 1 40" and svgs and all(svgs) and page.locator(f"{V} .dv-cards-card").count() < 60,
          f"{status.split(' · Unfold')[0]}; first heading '{head}'; {sum(svgs)} SVGs loaded, {page.locator(f'{V} .dv-cards-card').count()} cards in the DOM")
    page.locator(f"{V} .dv-cards-scroll").evaluate("el => el.scrollTo(0, el.scrollHeight)")
    page.wait_for_timeout(300)
    ids = page.evaluate("[...document.querySelectorAll('#example .dv-cards-card')].sort((a, b) => a.dataset.i - b.dataset.i).map((c) => c.dataset.id)")
    check("logo rounds: scrolling the grid reaches round 11's last SVG", ids and ids[-1].startswith("r11-"), ids[-1] if ids else None)
    page.locator(f"{V} .dv-cards-scroll").evaluate("el => el.scrollTo(0, 0)")
    page.wait_for_timeout(200)
    score = page.locator(f"{V} .dv-cards-card").first.locator(".dv-cards-value .dv-none")
    check("logo rounds: round 1's missing score reads '—' with its reason, never 0", score.inner_text() == "—" and score.get_attribute("title") == "round 1 was not scored",
          score.get_attribute("title"))

    # ---- the lightbox over every round
    page.locator(f"{V} .dv-cards-card [data-zoom]").first.click()
    page.wait_for_selector(".pswp--open img.pswp__img", timeout=5000)
    page.wait_for_timeout(450)
    counter = page.inner_text(".pswp__counter")
    cap1 = page.inner_text(".dv-cards-caption")
    page.keyboard.press("ArrowLeft")
    page.wait_for_timeout(450)
    cap2 = page.inner_text(".dv-cards-caption")
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    check("logo rounds: the lightbox runs over all 203 logos; ← from the first wraps to round 11", counter == "1 / 203" and "Round 1" in cap1 and "Round 11" in cap2,
          f"{counter}; {cap1.split(chr(10))[0]} → {cap2.split(chr(10))[0]}")

    # ---- ranking
    page.click(f"{V} .dv-tab[data-name='Lockups by score']")
    page.wait_for_timeout(300)
    vals = [float(x.split()[0]) for x in page.locator(f"{V} .dv-cards-card .dv-cards-prop:nth-child(3) .dv-cards-value").all_inner_texts()]
    check("logo rounds: 'Lockups by score' ranks the 77 scored lockups, best first", vals and vals == sorted(vals, reverse=True) and page.inner_text(f"{V} .dv-status").startswith("77 of 203"),
          f"{page.inner_text(f'{V} .dv-status').split(' · ')[0]}; scores {vals[:6]}")
    page.context.close()

    # ---- light and dark, 1280 and 390
    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            name = f"logo-rounds-{'dark' if dark else 'light'}-{width}"
            p = open_page(ctx, path, width=width, height=900 if not mobile else 844, dark=dark, mobile=mobile)
            p.locator(V).evaluate("el => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 64)")
            p.wait_for_timeout(150)
            scroll = p.evaluate("document.scrollingElement.scrollWidth")
            well = p.evaluate("getComputedStyle(document.querySelector('#example .dv-cards-img')).backgroundColor")
            card = p.evaluate("getComputedStyle(document.querySelector('#example .dv-cards-card')).backgroundColor")
            check(f"logo rounds, {'dark' if dark else 'light'}, {width} px: no sideways scroll; the image wells stay paper-white (the skin) while the cards follow the theme",
                  scroll <= width and well == "rgb(255, 255, 255)" and (card != "rgb(255, 255, 255)") == dark, f"page {scroll}, well {well}, card {card}")
            ctx.shot(p, name)
            p.context.close()
