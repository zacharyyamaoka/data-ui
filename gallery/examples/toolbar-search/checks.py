"""Browser checks for the bar's Notion pattern (docs/CONTRACT.md §15): search="icon" and the filters default that follows
the views (views visible => filters folded; views in a dropdown => filters may expand). Run by tests/browser/checks.py.
Every claim is measured: widths and x positions (getBoundingClientRect), focus, elementFromPoint."""

import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location("toolbar_bar_checks", pathlib.Path(__file__).resolve().parents[1] / "toolbar-bar" / "checks.py")
bar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bar)
V = bar.V

STATE = """() => { const v = document.querySelector('#example'); const r = (s) => { const e = v.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect();
    return { x: Math.round(b.left), right: Math.round(b.right), w: Math.round(b.width), shown: b.width > 0 && getComputedStyle(e).visibility !== 'hidden' }; };
  const icon = v.querySelector('.dv-bar [data-bar=search]'), input = v.querySelector('.dv-bar-query input');
  return { icon: r('.dv-bar [data-bar=search]'), expanded: icon && icon.getAttribute('aria-expanded'), label: icon && icon.getAttribute('aria-label'),
    box: r('.dv-bar-query > *'), focused: !!(input && document.activeElement === input), chip: r('.dv-viewchip'), tabs: r('.dv-viewtabs'),
    filter: r('.dv-bar-tools [data-bar=menu][data-name=filter]'), display: r('.dv-bar-tools [data-bar=display]'),
    words: [...v.querySelectorAll('.dv-bar-tools [data-bar=menu]')].map((b) => b.dataset.name), sw: document.scrollingElement.scrollWidth }; }"""


def state(page):
    return page.evaluate(STATE)


def run(ctx, path):
    bar.CTX = ctx
    check = ctx.check
    for dark in (False, True):
        page = ctx.page(path, width=1280, dark=dark)
        a = state(page)
        check(f"search=icon ({'dark' if dark else 'light'}, 1280): at rest the query box is collapsed (0 px or hidden) and a Search icon button shows, aria-expanded=false",
              a["icon"] and a["icon"]["shown"] and a["label"] == "Search" and a["expanded"] == "false" and (not a["box"] or a["box"]["w"] <= 1 or not a["box"]["shown"]), a)
        check(f"filters default ({'dark' if dark else 'light'}, 1280): the four views show as tabs, so the filters fold into one Filter button (no Sort / Group / Properties words)",
              a["tabs"] and a["tabs"]["shown"] and a["words"] == ["filter"] and (a["chip"] is None or not a["chip"]["shown"]), {"words": a["words"], "tabs": a["tabs"]})
        ctx.shot(page, f"toolbar-search-{'dark' if dark else 'light'}-1280")
        if not dark:
            # click the icon: the box grows in place, focused; nothing else in the bar moves
            page.click(f"{V} .dv-bar [data-bar=search]")
            bar.still(page)
            b = state(page)
            moved = {k: (a[k]["x"], b[k]["x"]) for k in ("tabs", "filter", "display", "icon") if a[k] and b[k] and abs(a[k]["x"] - b[k]["x"]) > 0.5}
            check("search=icon: a click grows the box in place (over 150 px), focused, aria-expanded=true; the tabs, Filter, Display and the icon do not move",
                  b["box"]["w"] > 150 and b["focused"] and b["expanded"] == "true" and not moved, {"box": b["box"], "focused": b["focused"], "moved": moved})
            ctx.shot(page, "toolbar-search-open-light-1280")
            # typed text keeps it open through a blur; cleared, a blur collapses it
            page.keyboard.type("gim")
            page.locator("main h1").click()
            bar.still(page)
            typed = state(page)
            page.click(f"{V} .dv-bar-query input")
            page.fill(f"{V} .dv-bar-query input", "")
            page.locator("main h1").click()
            bar.still(page)
            cleared = state(page)
            check("search=icon: with text it stays open after a blur; emptied, a blur collapses it again",
                  typed["box"]["w"] > 150 and not typed["focused"] and (cleared["box"]["w"] <= 1 or not cleared["box"]["shown"]) and cleared["expanded"] == "false",
                  {"typed": typed["box"], "cleared": cleared["box"]})
            # "/" opens it; Escape on the empty box collapses it
            page.keyboard.press("/")
            bar.until(page, "() => document.activeElement === document.querySelector('#example .dv-bar-query input')")
            bar.still(page)
            slash = state(page)
            # Escape: the first closes the suggestions if they are open (the combobox's own Escape), the next folds the box
            presses = 0
            for presses in (1, 2):
                page.keyboard.press("Escape")
                bar.still(page)
                if state(page)["expanded"] == "false":
                    break
            esc = state(page)
            check("search=icon: '/' opens the box focused; Escape on the empty box folds it (after closing the suggestions, if open)",
                  slash["focused"] and slash["box"]["w"] > 150 and esc["expanded"] == "false" and not esc["focused"] and (not esc["box"] or esc["box"]["w"] <= 1 or not esc["box"]["shown"]),
                  {"/": [slash["focused"], slash["box"]["w"]], "esc": esc["expanded"], "presses": presses})
            # tokens keep it open (query-tokens): a typed clause becomes a token, the box stays
            page.evaluate("document.querySelector('#example').setAttribute('filters', 'query-tokens')")
            bar.settle(page)
            page.evaluate("document.querySelector('#example').setQuery('brand:Steadywin')")
            bar.until(page, "() => document.querySelector('#example .dv-qtoken')")
            page.locator("main h1").click()
            bar.still(page)
            tok = state(page)
            check("search=icon: with a token shown (filters=query-tokens) the box stays open, so the token is never hidden", tok["box"]["w"] > 150 and tok["expanded"] == "true", tok["box"])
            page.evaluate("(() => { const el = document.querySelector('#example'); el.setQuery(''); el.removeAttribute('filters'); })()")
            bar.settle(page)
            # the filters default flips with auto: narrowed (the element's own width) until the views fold into the chip,
            # the filters spread out as words (shown, or in "…" when the row has no room for them)
            page.evaluate("(() => { const el = document.querySelector('#example'); el.style.width = '240px'; el.style.justifySelf = 'start'; })()")
            bar.until(page, "() => document.querySelector('#example .dv-viewchip')")
            bar.settle(page)
            n = state(page)
            page.evaluate("document.querySelector('#example').style.width = ''")
            bar.until(page, "() => document.querySelector('#example .dv-viewtabs')")
            bar.settle(page)
            w = state(page)
            check("filters default follows auto: narrowed until the views fold into the chip, the filters spread out as Sort · Group · Filter · Properties; widened, tabs and one Filter button again",
                  n["chip"] and n["chip"]["shown"] and n["words"] == ["sort", "group", "filter", "properties"] and w["words"] == ["filter"] and w["tabs"] and w["tabs"]["shown"],
                  {"narrow": n["words"], "wide": w["words"]})
            # an explicit filters attribute always wins: pills while the views are the chip
            page.evaluate("document.querySelector('#example').setAttribute('views', 'dropdown')")
            bar.until(page, "() => document.querySelector('#example .dv-viewchip')")
            page.evaluate("document.querySelector('#example').setAttribute('filters', 'pills')")
            bar.settle(page)
            x = state(page)
            check("filters default: an explicit filters attribute wins (filters='pills' keeps one Filter button while the views are the chip)",
                  x["words"] == ["filter"] and x["chip"] and x["chip"]["shown"], {"words": x["words"], "chip": bool(x["chip"])})
        page.context.close()

    for dark in (False, True):
        page = ctx.page(path, width=390, height=844, mobile=True, dark=dark)
        a = state(page)
        page.click(f"{V} .dv-bar [data-bar=search]")
        bar.still(page)
        b = state(page)
        moved = {k: (a[k]["x"], b[k]["x"]) for k in ("tabs", "chip", "filter", "display", "icon") if a[k] and b[k] and abs(a[k]["x"] - b[k]["x"]) > 0.5}
        # with no room in the one row the open box lies over the views, up to the tools; nothing moves
        check(f"search=icon at 390 px ({'dark' if dark else 'light'}): the views stay tabs (the open one and 'N more'), so the filters stay folded; collapsed at rest, a tap grows the box (focused) without moving the bar's other controls; no sideways scroll",
              a["tabs"] and a["tabs"]["shown"] and a["words"] == ["filter"] and (not a["box"] or a["box"]["w"] <= 1 or not a["box"]["shown"])
              and b["box"]["w"] > 150 and b["focused"] and not moved and a["sw"] <= 390 and b["sw"] <= 390, {"rest": a["box"], "open": b["box"], "moved": moved, "words": a["words"], "sw": [a["sw"], b["sw"]]})
        ctx.shot(page, f"toolbar-search-open-{'dark' if dark else 'light'}-390")
        page.context.close()

    bar.one_row(ctx, path, check, "toolbar-search")
    bar.long_names(ctx, path, check, "tabs")
    bar.long_names(ctx, path, check, "auto")
