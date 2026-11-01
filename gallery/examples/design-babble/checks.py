"""Browser checks for this case (run by tests/browser/checks.py): the ten proposals as cards ranked by the babble's
score, their stills loading, the lightbox caption with the still's source, every still grouped by proposal, and the
page light and dark at 1280 and 390 px."""

V = "#example"


def open_page(ctx, path, width=1280, height=900, dark=False, mobile=False):
    """ctx.page() waits for the status line; the view's own code loads after it, so wait for its first card too."""
    page = ctx.page(path, width=width, height=height, dark=dark, mobile=mobile)
    page.wait_for_selector(f"{V} .dv-cards-card", timeout=15000)
    return page


def lum(rgb):
    r, g, b = (int(x) for x in rgb[rgb.index("(") + 1:rgb.index(")")].split(",")[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def run(ctx, path):
    check = ctx.check
    page = open_page(ctx, path)
    page.locator(V).evaluate("el => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 64)")
    status = page.inner_text(f"{V} .dv-status")
    heads = page.locator(f"{V} .dv-cards-head").all_inner_texts()
    first = page.locator(f"{V} .dv-cards-card").first.locator(".dv-cards-title").inner_text()
    check("babble: ten proposals as cards, round 2 first, each round ranked by its weighted score (R2 v3 Views + Offers, 92, leads)",
          status.startswith("10 of 30 rows · 2 groups") and heads[0].startswith("Round 2") and first == "R2 v3 · Views + Offers",
          f"{status.split(' · Unfold')[0]}; first card {first}")
    stills = page.evaluate("[...document.querySelectorAll('#example .dv-cards-img img')].filter((i) => i.complete).map((i) => i.naturalWidth)")
    check("babble: the landing stills load (WebP, 960 px)", stills and all(w == 960 for w in stills), f"{len(stills)} stills, widths {sorted(set(stills))}")
    page.locator(f"{V} .dv-cards-card [data-zoom]").first.click()
    page.wait_for_selector(".pswp--open img.pswp__img", timeout=5000)
    page.wait_for_timeout(450)
    cap = page.inner_text(".dv-cards-caption")
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    check("babble: a still opens full screen with its round, score and thesis, then its source file and date", "92 / 100" in cap and "shots/landing-1280.png · accessed 2026-10-22" in cap,
          cap.replace("\n", " | ")[:140])
    page.click(f"{V} .dv-tab[data-name='Every still']")
    page.wait_for_timeout(300)
    status = page.inner_text(f"{V} .dv-status")
    check("babble: 'Every still' groups all 30 stills by proposal", status.startswith("30 of 30 rows · 10 groups"), status.split(" · Unfold")[0])
    page.click(f"{V} .dv-tab[data-name='Phones']")
    page.wait_for_timeout(300)
    box = page.evaluate("(() => { const b = document.querySelector('#example .dv-cards-img').getBoundingClientRect(); return [b.width, b.height]; })()")
    check("babble: imageAspectRatio 1.8 gives the phone stills tall wells (height ÷ width)", abs(box[1] / box[0] - 1.8) < 0.02, f"{box[0]:.0f} x {box[1]:.0f}")
    page.context.close()

    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            name = f"design-babble-{'dark' if dark else 'light'}-{width}"
            p = open_page(ctx, path, width=width, height=900 if not mobile else 844, dark=dark, mobile=mobile)
            p.locator(V).evaluate("el => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 64)")
            p.wait_for_timeout(150)
            scroll = p.evaluate("document.scrollingElement.scrollWidth")
            bg = p.evaluate("getComputedStyle(document.querySelector('#example .dv-cards-card')).backgroundColor")
            check(f"babble, {'dark' if dark else 'light'}, {width} px: no sideways scroll; cards in the theme", scroll <= width and (lum(bg) < 40 if dark else lum(bg) > 240), f"page {scroll}, card {bg}")
            ctx.shot(p, name)
            p.context.close()
