"""Browser checks for this case (run by tests/browser/checks.py): the calendar view on releases and daily-note
dates. It opens on the newest month, colours by group, a click opens the record, a drag proposes a new date (kept
date-only, or with its own UTC offset) that the editable page applies and a read-only page refuses, a toolbar
button writes calendarView back, light / dark at 1280 and 390 px."""

V = "#example"
CASE = "robotparts-calendar"


def _open(ctx, path, view, **kw):
    """ctx.page() waits for the status line; then wait for the view the element says it drew."""
    page = ctx.page(path, **kw)
    page.wait_for_selector(f"{V}[data-view='{view}'] .ec", timeout=15000)
    page.wait_for_timeout(300)
    return page


def _frame(page):
    """Scroll the view to the top of the window, below the site's sticky header, for a screenshot."""
    page.evaluate("""() => {
      const el = document.querySelector('#example'), bar = document.querySelector('header.top, .top');
      window.scrollTo(0, el.getBoundingClientRect().top + scrollY - (bar ? bar.offsetHeight : 0) - 8);
    }""")
    page.wait_for_timeout(150)


def _day(page, n):
    """The centre of this month's day-n cell (not a day from the month before or after)."""
    return page.evaluate("""(n) => {
      for (const d of document.querySelectorAll('#example .ec-day:not(.ec-other-month)')) {
        const head = d.querySelector('.ec-day-head');
        if (head && head.textContent.trim() === String(n)) { const r = d.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height * 0.75]; }
      }
      return null;
    }""", n)


def _drag(page, selector, to):
    box = page.locator(selector).first.bounding_box()
    page.mouse.move(box["x"] + 12, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(to[0], to[1], steps=12)
    page.mouse.up()
    page.wait_for_timeout(500)


def _cell_of(page, title):
    """The day an event is drawn on: Event Calendar draws events in a layer over the cells, so by geometry."""
    return page.evaluate("""(t) => {
      const ev = [...document.querySelectorAll('#example .ec-event')].find((e) => e.textContent.includes(t));
      if (!ev) return null;
      const r = ev.getBoundingClientRect(), x = r.x + r.width / 2, y = r.y + 2;
      for (const d of document.querySelectorAll('#example .ec-day:not(.ec-other-month)')) {
        const b = d.getBoundingClientRect();
        if (x >= b.left && x <= b.right && y >= b.top && y <= b.bottom) return d.querySelector('.ec-day-head').textContent.trim();
      }
      return null;
    }""", title)


def run(ctx, path):
    check = ctx.check
    page = _open(ctx, path, "calendar")
    title = page.inner_text(f"{V} .ec-title")
    events = page.locator(f"{V} .ec-event").count()
    colours = page.evaluate("[...new Set([...document.querySelectorAll('#example .ec-event')].map(e => e.style.getPropertyValue('--dv-item')))]")
    check("calendar: opens on the newest event's month, daily notes and releases in two group colours", title == "October 2026" and events >= 25 and len(colours) == 2, f"{title}, {events} events, colours {colours}")
    _frame(page)
    page.locator(f"{V} .ec-event:has-text('Daily Note - Oct 8 2026')").click()
    page.wait_for_selector(f"{V} .dv-peek:not([hidden])")
    check("calendar: a click on an event opens its record", page.inner_text(f"{V} .dv-peek h2") == "Daily Note - Oct 8 2026", page.inner_text(f"{V} .dv-peek h2"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)

    # ---- drag to reschedule: the editable page applies the proposal
    note = "Daily Note - Oct 14 2026"
    page.evaluate("window.__proposals = []; document.querySelector('#example').addEventListener('data-views-propose', (e) => window.__proposals.push({id: e.detail.id, set: e.detail.set, ok: e.detail.result.ok, reason: e.detail.result.reason}))")
    _drag(page, f"{V} .ec-event:has-text('{note}')", _day(page, 15))
    moved = page.evaluate("document.querySelector('#example').row('note-daily-note-oct-14-2026').date")
    check("calendar: dragging a date-only event proposes the new date, date-only, and the editable page applies it",
          moved == "2026-10-15" and _cell_of(page, note) == "15", f"{page.evaluate('window.__proposals')}; drawn on day {_cell_of(page, note)}")
    release = "robotparts 2026.10.25 "
    page.evaluate("window.__proposals = []")
    _drag(page, f"{V} .ec-event:has-text('3:02')", _day(page, 24))
    moved = page.evaluate("document.querySelector('#example').row('release-2026.10.25').date")
    check("calendar: dragging a timed event keeps its time and its own UTC offset", moved == "2026-10-24T15:02:18-07:00", f"{release.strip()}: {moved}")

    # ---- a read-only page refuses, and the event goes back
    page.evaluate("document.querySelector('#example').removeAttribute('editable'); window.__proposals = []")
    note = "Daily Note - Oct 7 2026"
    _drag(page, f"{V} .ec-event:has-text('{note}')", _day(page, 9))
    status = page.inner_text(f"{V} .dv-status")
    proposals = page.evaluate("window.__proposals")
    check("calendar: a read-only page refuses the drag, the event goes back, the status says why",
          proposals and not proposals[0]["ok"] and _cell_of(page, note) == "7" and "Not moved" in status and "read-only" in status, status.split(" · ")[-1])

    page.click(f"{V} .ec-button:has-text('List')")
    page.wait_for_timeout(400)
    view = page.evaluate("document.querySelector('#example').view.calendarView")
    check("calendar: a toolbar grid button writes calendarView back to the view", view == "list" and page.locator(f"{V} .ec-list").count() == 1, view)
    page.click(f"{V} .dv-tab[data-name='Release week']")
    page.wait_for_timeout(500)
    timed = page.locator(f"{V} .ec-time-grid .ec-event").count()
    check("calendar: the Release week preset opens a week grid on the newest release", timed >= 1 and "Oct" in page.inner_text(f"{V} .ec-title"), page.inner_text(f"{V} .ec-title"))
    page.context.close()

    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            page = _open(ctx, path, "calendar", width=width, height=900 if width > 400 else 844, dark=dark, mobile=mobile)
            scheme = "dark" if dark else "light"
            bg = page.eval_on_selector(f"{V} .ec-button", "el => getComputedStyle(el).backgroundColor")
            want = page.eval_on_selector(V, "el => getComputedStyle(el).backgroundColor")
            scroll = page.evaluate("document.scrollingElement.scrollWidth")
            drawn = page.locator(f"{V} .ec-event").count()
            check(f"calendar, {scheme}, {width} px: the grid's controls take the theme's background, no sideways page scroll", bg == want and drawn > 0 and scroll <= width, f"{drawn} events, grid {bg}, scrollWidth {scroll}")
            _frame(page)
            ctx.shot(page, f"{CASE}-{scheme}-{width}")
            page.context.close()
