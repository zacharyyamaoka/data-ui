"""Browser checks for this case (run by tests/browser/checks.py): the illustrative transactions as a list grouped kind
-> category, a table with a sum per category, the recategorise form (a select over money's accounts) refused on a
read-only page and taken by a host's acceptEdit; light and dark at 1280 and 390 px."""

V = "#example"


def open_page(ctx, path, width=1280, height=900, dark=False, mobile=False):
    """ctx.page, then until the view's own code has drawn (the host sets data-view after it)."""
    page = ctx.page(path, width=width, height=height, dark=dark, mobile=mobile)
    page.wait_for_selector(f"{V}[data-view]", timeout=15000)
    return page


def tab(page, name):
    page.click(f"{V} .dv-tab[data-name='{name}']")
    page.wait_for_selector(f"{V} .dv-view")
    page.wait_for_timeout(250)


def run(ctx, path):
    check = ctx.check
    page = open_page(ctx, path)
    page.evaluate("localStorage.clear()")
    heads = page.locator(f"{V} .dv-list-group.dv-depth0 .dv-gname").all_inner_texts()
    subs = page.locator(f"{V} .dv-list-group.dv-depth1").count()
    check("list: 19 illustrative transactions under kind -> category headings", heads == ["Expenses", "Income", "Transfers"] and subs >= 8
          and page.inner_text(f"{V} .dv-status").startswith("19 of 19"), f"{heads}, {subs} categories")
    titles = page.locator(f"{V} .dv-list-title").all_inner_texts()
    check("list: inside a category, newest first (Expenses:Food: Safeway on Oct 12 before Uber Eats on Oct 3)",
          "SAFEWAY #4402" in titles and "UBER EATS" in titles and titles.index("SAFEWAY #4402") < titles.index("UBER EATS"), titles[:6])
    tab(page, "By category")
    rev = page.locator(f"{V} tr.dv-group:has(.dv-gname:text-is('Income:Revenue')) td[data-col], {V} tr.dv-group:has(.dv-gname:text-is('Income:Revenue')) .dv-summary").all_inner_texts()
    check("table: a sum per category (a view summary, from the rows): revenue 20,000 CAD", any("20,000" in t for t in rev), rev)
    tab(page, "Categorise")
    opts = page.locator(f"{V} select[name='category'] option").all_inner_texts()
    check("form: the category is a select over money's accounts; what the bank reported is read-only",
          "Expenses:Food" in opts and "Expenses:Other" in opts and page.locator(f"{V} .dv-form [name='amount'], {V} .dv-form [name='date']").count() == 0, f"{len(opts)} options")
    page.select_option(f"{V} select[name='category']", "Expenses:Other")
    page.click(f"{V} .dv-form [type=submit]")
    page.wait_for_selector(f"{V} .dv-form-msg.dv-refused")
    check("form: this static page refuses the edit and says why", "read-only" in page.inner_text(f"{V} .dv-form-msg"), page.inner_text(f"{V} .dv-form-msg"))
    # WHY in a statement: page.evaluate calls an expression that returns a function
    page.evaluate("""(() => { document.querySelector('#example').acceptEdit = async ({ set, row }) => { Object.assign(row, set); return { ok: true }; }; return true; })()""")
    page.click(f"{V} .dv-form [type=submit]")
    page.wait_for_function("document.querySelector('#example .dv-form-msg').textContent.startsWith('Saved')")
    first = page.inner_text(f"{V} .dv-record-head h2")
    check("form: a host's acceptEdit takes it; the row moves to its new category",
          page.evaluate(f"document.querySelector('#example').row('{page.eval_on_selector(f'{V} .dv-record-pick select', 'e => e.value')}').category") == "Expenses:Other", first)
    page.evaluate("localStorage.clear()")
    page.context.close()

    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            name = f"{'dark' if dark else 'light'}, {width} px"
            page = open_page(ctx, path, width=width, height=900 if width > 400 else 844, dark=dark, mobile=mobile)
            sw = page.evaluate("document.scrollingElement.scrollWidth")
            check(f"money list, {name}: the list draws, no sideways page scroll", page.locator(f"{V} .dv-list-line").count() > 5 and sw <= width, f"scrollWidth {sw}")
            page.locator(V).scroll_into_view_if_needed()  # the shot shows the views, not the README above them
            ctx.shot(page, f"money-{'dark' if dark else 'light'}-{width}")
            tab(page, "Categorise")
            sw = page.evaluate("document.scrollingElement.scrollWidth")
            check(f"money form, {name}: the form draws, no sideways page scroll", page.locator(f"{V} select[name='category']").is_visible() and sw <= width, f"scrollWidth {sw}")
            page.locator(V).scroll_into_view_if_needed()  # the shot shows the views, not the README above them
            ctx.shot(page, f"money-form-{'dark' if dark else 'light'}-{width}")
            page.context.close()
