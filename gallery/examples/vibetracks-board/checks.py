"""Browser checks for this case (run by tests/browser/checks.py): the kanban view's columns and counts, both drags
(a card proposes, a column writes groupOrder), the refusals (a read-only page, a derived property), the keyboard
moves, virtualisation, and the page light and dark at 1280 and 390 px."""

V = "#example"
STATUSES = ["backlog", "ready", "running", "waiting", "review", "frontier", "done", "archived", "todo"]


def open_page(ctx, path, width=1280, height=900, dark=False, mobile=False):
    """ctx.page() waits for the status line; the view's own code loads after it, so wait for its first card too."""
    page = ctx.page(path, width=width, height=height, dark=dark, mobile=mobile)
    page.wait_for_selector(f"{V} .dv-kanban-card", timeout=15000)
    return page


def lum(rgb):
    r, g, b = (int(x) for x in rgb[rgb.index("(") + 1:rgb.index(")")].split(",")[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def heads(page):
    return [h.replace("\n", " ") for h in page.locator(f"{V} .dv-kanban-head").all_inner_texts()]


def drag(page, source, target, dy=200):
    """A real mouse drag (Chromium's native drag and drop, which Pragmatic listens to), with the board in view."""
    page.locator(V).evaluate("el => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 64)")
    a, b = source.bounding_box(), target.bounding_box()
    page.mouse.move(a["x"] + a["width"] / 2, a["y"] + 12)
    page.mouse.down()
    page.mouse.move(a["x"] + a["width"] / 2 + 12, a["y"] + 20, steps=4)
    page.mouse.move(b["x"] + b["width"] * 0.3, b["y"] + min(dy, b["height"] - 10), steps=12)
    page.wait_for_timeout(80)
    page.mouse.up()
    page.wait_for_timeout(300)


def run(ctx, path):
    check = ctx.check
    page = open_page(ctx, path)
    page.evaluate("window._proposals = []; document.querySelector('#example').addEventListener('data-views-propose', (e) => window._proposals.push(e.detail.result))")
    got = heads(page)
    check("kanban: one column per status in groupOrder, each with its count; an empty named status is a column, an unnamed one follows",
          [h.split()[0] for h in got] == STATUSES and got[0] == "backlog 32" and got[5] == "frontier 0", got)
    drawn = page.locator(f"{V} [data-col='0'] .dv-kanban-card").count()
    check("kanban: each column is virtualised (backlog's 32 cards, only the visible ones drawn)", 0 < drawn < 32, f"{drawn} of 32 in the DOM")
    page.locator(f"{V} [data-col='0'] .dv-kanban-scroll").evaluate("el => el.scrollTo(0, el.scrollHeight)")
    page.wait_for_timeout(200)
    last = int(page.locator(f"{V} [data-col='0'] .dv-kanban-card").last.get_attribute("data-i"))
    check("kanban: a column scrolls to its last card", last == 31, f"last drawn index {last}")
    page.locator(f"{V} [data-col='0'] .dv-kanban-scroll").evaluate("el => el.scrollTo(0, 0)")

    # ---- site.json makes this page editable; without the attribute the same host is read-only
    check("kanban: the case's site.json renders <data-views editable>", page.evaluate("document.querySelector('#example').hasAttribute('editable')"))
    page.evaluate("document.querySelector('#example').removeAttribute('editable')")
    card = page.locator(f"{V} [data-col='0'] .dv-kanban-card").first
    title = card.locator(".dv-kanban-title").inner_text()
    drag(page, card, page.locator(f"{V} [data-col='1']"))
    msg = page.inner_text(f"{V} .dv-kanban-msg")
    check("kanban: a card dropped on another column proposes the edit; a read-only page refuses it, with its reason, and nothing moves",
          page.evaluate("window._proposals.length") == 1 and "read-only" in msg and heads(page)[0] == "backlog 32", msg.split("\n")[0])

    # ---- editable again (as site.json has it): the same drag lands, drawn only after ok
    page.evaluate("document.querySelector('#example').setAttribute('editable', '')")
    drag(page, page.locator(f"{V} [data-col='0'] .dv-kanban-card").first, page.locator(f"{V} [data-col='1']"))
    got = heads(page)
    moved = page.locator(f"{V} [data-col='1'] .dv-kanban-card", has_text=title).count()
    check("kanban: on an editable host the drag lands: the card's status changes, both counts move, the card shows in its new column",
          got[0] == "backlog 31" and got[1] == "ready 9" and moved == 1 and page.evaluate("window._proposals.at(-1).ok"), f"{got[0]}, {got[1]}; '{title}' in ready: {moved == 1}")

    # ---- the keyboard: Alt+→ moves a card one column, M opens the Move menu
    page.locator(f"{V} [data-col='1'] .dv-kanban-card").first.focus()
    first_ready = page.locator(f"{V} [data-col='1'] .dv-kanban-card").first.get_attribute("data-id")
    page.keyboard.press("Alt+ArrowRight")
    page.wait_for_timeout(300)
    got = heads(page)
    focused = page.evaluate("document.activeElement && document.activeElement.dataset.id")
    check("kanban: Alt+→ moves the focused card to the next column, and focus follows it", got[1] == "ready 8" and got[2] == "running 8" and focused == first_ready,
          f"{got[1]}, {got[2]}; focus on {focused}")
    page.keyboard.press("m")
    page.wait_for_timeout(150)
    items = page.locator(f"{V} .dv-kanban-menu [role=menuitem]").count()
    disabled = page.locator(f"{V} .dv-kanban-menu [role=menuitem][disabled]").inner_text()
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)
    back = page.evaluate("document.activeElement && document.activeElement.dataset.id")
    check("kanban: M opens 'Move to' with every column (its own disabled); Esc closes it and focus returns to the card",
          items == len(STATUSES) and disabled.startswith("running") and page.locator(f"{V} .dv-kanban-menu").is_hidden() and back == first_ready,
          f"{items} items, current: {disabled.split()[0]}")
    page.keyboard.press("m")
    page.wait_for_timeout(150)
    page.locator(f"{V} .dv-kanban-menu [role=menuitem]", has_text="done").click()
    page.wait_for_timeout(300)
    check("kanban: choosing a column in the Move menu proposes the move (the touch screen's way)", heads(page)[6] == "done 18", heads(page)[6])

    # ---- a column drag writes groupOrder (the .base file's key)
    page.locator(f"{V} .dv-kanban-board").evaluate("el => { el.scrollLeft = 0; }")  # the Move above scrolled to its card
    drag(page, page.locator(f"{V} [data-col='1'] .dv-kanban-head"), page.locator(f"{V} [data-col='0']"), dy=30)
    order = page.evaluate("document.querySelector('#example').view.groupOrder")
    yaml = page.evaluate("document.querySelector('#example').viewYaml()")
    check("kanban: dragging a column header onto another's left edge writes the new order as groupOrder, and the view's YAML carries it",
          order[:3] == ["ready", "backlog", "running"] and heads(page)[0].startswith("ready") and "groupOrder" in yaml, order[:3])
    page.locator(f"{V} [data-col='0'] .dv-kanban-head").focus()
    page.keyboard.press("Alt+ArrowRight")
    page.wait_for_timeout(250)
    order = page.evaluate("document.querySelector('#example').view.groupOrder")
    focused = page.evaluate("document.activeElement.closest('[data-col]') && document.activeElement.closest('[data-col]').dataset.col")
    check("kanban: Alt+→ on a focused column header moves the column back (groupOrder again), focus staying on it",
          order[:2] == ["backlog", "ready"] and focused == "1", f"{order[:3]}; focus on column {focused}")

    # ---- a derived group property locks the board
    page.click(f"{V} .dv-tab[data-name='By proof (derived)']")
    page.wait_for_selector(f"{V} .dv-kanban-card")
    page.wait_for_timeout(200)
    before = heads(page)
    n = page.evaluate("window._proposals.length")
    drag(page, page.locator(f"{V} [data-col='0'] .dv-kanban-card").first, page.locator(f"{V} [data-col='1']"))
    refused = page.evaluate("document.querySelector('#example').host.propose({ id: 'VT-001', set: { proof: 'none' } })")
    check("kanban: grouped by a derived property, cards do not drag, the status line says why, and the host refuses the edit",
          heads(page) == before and page.evaluate("window._proposals.length") == n + 1 and not refused["ok"] and "derived" in refused["reason"]
          and "derived" in page.inner_text(f"{V} .dv-status") and page.locator(f"{V} .dv-kanban-move").count() == 0,
          f"{before[0]}; {refused['reason'][:46]}")
    page.click(f"{V} [data-menu=layout]")
    page.wait_for_timeout(250)
    opts = page.locator(f"{V} .dv-pop [data-opt]").count()
    page.keyboard.press("Escape")
    check("kanban: Layout shows the board's own settings (column width, image, fit, aspect)", opts == 4, f"{opts} settings")
    page.context.close()

    # ---- light and dark, 1280 and 390
    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            name = f"vibetracks-board-{'dark' if dark else 'light'}-{width}"
            p = open_page(ctx, path, width=width, height=900 if not mobile else 844, dark=dark, mobile=mobile)
            p.locator(V).scroll_into_view_if_needed()
            scroll = p.evaluate("document.scrollingElement.scrollWidth")
            board = p.locator(f"{V} .dv-kanban-board").evaluate("el => [el.scrollWidth, el.clientWidth]")
            col = p.locator(f"{V} [data-col='0']").bounding_box()
            bg = p.evaluate("getComputedStyle(document.querySelector('#example .dv-kanban-card')).backgroundColor")
            ok = scroll <= width and board[0] > board[1] and col["width"] >= 200 and (lum(bg) < 40 if dark else lum(bg) > 240)
            if mobile:
                ok = ok and p.locator(f"{V} .dv-kanban-move").first.evaluate("el => getComputedStyle(el).opacity") == "1"
            check(f"kanban, {'dark' if dark else 'light'}, {width} px: columns {col['width']:.0f} px wide scroll inside the board, not the page"
                  + ("; the Move button shows on touch" if mobile else ""), ok, f"page scrollWidth {scroll}, board {board[0]} > {board[1]}, card {bg}")
            ctx.shot(p, name)
            p.context.close()
