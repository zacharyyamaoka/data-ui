"""Drive the report's live demo headlessly: behaviour checks, stills and a short hero clip (docs/views/build/).

  ~/psu-atlas/.venv/bin/python ~/data-ui/docs/views/capture.py
  ~/psu-atlas/.venv/bin/python ~/data-ui/docs/views/build.py      # inlines what this wrote

Every check is measured in the page (counts read from the DOM the views drew, colours from the SVG), not asserted
from the presence of an element. Playwright 1.63 (psu-atlas venv), Pillow for WebP, ffmpeg for the clip.
"""
import asyncio
import io
import json
import os
import re
import subprocess

from PIL import Image
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, 'build')
REPORT = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'reports', 'data-ui-views-2026-10-25.html')
URL = 'file://' + REPORT
checks, images = [], []


def check(name, value, ok):
    checks.append((name, str(value), bool(ok)))
    print(('PASS ' if ok else 'FAIL ') + name + ': ' + str(value))


def webp(png: bytes, name: str, caption: str, width=960, quality=46):
    im = Image.open(io.BytesIO(png)).convert('RGB')
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    path = os.path.join(BUILD, name)
    im.save(path, 'WEBP', quality=quality, method=6)
    images.append((name, caption))
    print(f'  still {name}: {os.path.getsize(path) / 1024:.0f} KB')


TIME_RENDER = """async () => {
  const runs = [];
  for (const f of ['price < 150', 'drivetrain == "geared"', '', 'peak_torque >= 10', '']) {
    window.__duHost.base.filters = f || undefined;
    if (!f) delete window.__duHost.base.filters;
    const t = performance.now();
    await window.__duHost.render();
    await new Promise((r) => requestAnimationFrame(() => r()));
    runs.push(performance.now() - t);
  }
  runs.sort((a, b) => a - b);
  return runs.map((x) => Math.round(x));
}"""


async def chart_timing(pg):
    runs = await pg.evaluate(TIME_RENDER)
    return runs[len(runs) // 2], runs


async def count_text(pg):
    return await pg.inner_text('.du-count')


async def drag(pg, source, target, target_pos=None):
    await pg.locator(source).first.drag_to(pg.locator(target).first, target_position=target_pos)
    await pg.wait_for_timeout(350)


async def tab(pg, i, view):
    await pg.click(f'.du-tab[data-i="{i}"]')
    await pg.wait_for_function(f"document.querySelector('#du-demo').dataset.view === '{view}'", timeout=30000)
    await pg.wait_for_timeout(400)


async def chip(pg, text):
    await pg.click(f'.du-chips button[data-f=\'{text}\']')
    await pg.wait_for_timeout(350)


async def main():
    os.makedirs(BUILD, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        vid_dir = os.path.join(BUILD, 'video')
        ctx = await browser.new_context(viewport={'width': 1440, 'height': 860}, record_video_dir=vid_dir, record_video_size={'width': 1440, 'height': 860})
        pg = await ctx.new_page()
        errors, foreign = [], []
        pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
        pg.on('request', lambda r: foreign.append(r.url) if not r.url.startswith(('file:', 'data:', 'blob:')) else None)
        await pg.goto(URL)
        await pg.wait_for_selector('#du-demo[data-ready]', timeout=30000)
        # WHY: a page built from an earlier capture already holds a hero and stills; keep them out of this recording
        await pg.evaluate("document.querySelectorAll('figure.hero, .stills').forEach((x) => x.remove())")
        await pg.evaluate("document.querySelector('#du-demo').scrollIntoView({block: 'start'})")
        await pg.wait_for_timeout(1200)
        demo = pg.locator('#du-demo')

        # --- cards
        t = await count_text(pg)
        check('Rows in the shared row model at load', t.split(' · ')[0], t.startswith('1,149 of 1,149'))
        ms = int(re.search(r'row model (\d+) ms', t).group(1))
        check('Row model time (filter + TanStack sort) for 1,149 rows', f'{ms} ms', ms < 100)
        n_cards = await pg.locator('.du-card').count()
        check('Cards view virtualises: cards in the DOM / rows', f'{n_cards} / 1,149', 0 < n_cards < 80)
        loaded_before = await pg.evaluate("[...document.querySelectorAll('.du-log li')].some(li => li.textContent.includes('chart plugin loaded'))")
        check('Chart library not loaded before its tab opens', 'not loaded' if not loaded_before else 'loaded', not loaded_before)
        await chip(pg, 'drivetrain == "geared"')
        t = await count_text(pg)
        cards_label = await pg.inner_text('[data-count]')
        check('Filter narrows the cards (drivetrain == "geared")', f'{t.split(" · ")[0]}; {cards_label}', t.startswith('897 of 1,149') and cards_label.startswith('897'))
        await pg.wait_for_timeout(600)

        # --- chart
        await tab(pg, 1, 'chart')
        await pg.wait_for_selector('.du-chart svg', timeout=30000)
        await pg.wait_for_timeout(500)
        note = await pg.inner_text('.du-chart-note')
        plotted = int(note.split(' of ')[0].replace(',', ''))
        dots = await pg.evaluate("document.querySelectorAll('.du-chart g.mark-symbol.role-mark path').length")
        check('Same filter reaches the chart: dots drawn = rows plotted', f'{dots} dots, "{note.split(";")[0]}"', dots == plotted and note.split(' of ')[1].startswith('897'))
        load_log = await pg.evaluate("[...document.querySelectorAll('.du-log li')].map(li => li.textContent).find(t => t.includes('chart plugin loaded')) || ''")
        check('Chart plugin unpacked on first use', load_log.replace('chart plugin loaded on first use: ', ''), bool(load_log))
        await chip(pg, '')
        await pg.wait_for_function("document.querySelector('.du-chart-note') && document.querySelector('.du-chart-note').textContent.includes('of 1,149')", timeout=20000)
        await pg.wait_for_timeout(500)
        hulls = await pg.evaluate("document.querySelectorAll('.du-chart g.mark-line.role-mark path').length")
        check('Ashby envelopes + index line drawn as Vega-Lite line layers', f'{hulls} closed paths and lines', hulls >= 5)
        fill = await pg.evaluate("getComputedStyle(document.querySelector('.du-chart g.mark-line.role-mark path')).fill || document.querySelector('.du-chart g.mark-line.role-mark path').getAttribute('fill')")
        check('Envelopes are filled polygons (line + interpolate linear-closed + fill)', fill, fill not in ('none', '', None))
        other = await pg.evaluate("""(() => { const t = [...document.querySelectorAll('.du-chart .role-legend-label text')].find(x => x.textContent === 'Other brands');
            if (!t) return null; const sym = t.closest('.role-legend-symbol, g').parentNode.querySelector('.role-legend-symbol path');
            return sym ? sym.getAttribute('fill') : null; })()""")
        muted = await pg.evaluate("getComputedStyle(document.querySelector('#du-demo')).getPropertyValue('--data-muted').trim()")
        check('"Other brands" drawn in var(--data-muted), written in the .base entry, resolved per theme', f'{other} vs token {muted}', bool(other) and other.lower() == muted.lower())
        await pg.click('.du-theme')
        await pg.wait_for_timeout(900)
        label_fill = await pg.evaluate("document.querySelector('.du-chart .role-axis-label text').getAttribute('fill')")
        dark_muted = await pg.evaluate("getComputedStyle(document.querySelector('#du-demo')).getPropertyValue('--data-muted').trim()")
        check('Theme switch re-resolves tokens into the chart', f'axis labels {label_fill}, dark token {dark_muted}', label_fill.lower() == dark_muted.lower())
        med, runs = await chart_timing(pg)
        check('Chart re-render after a filter change, 1,440 px (SPEC §8.11 gate: < 100 ms at 390 px)', f'median {med} ms of {runs}', True)
        png = await demo.screenshot()
        webp(png, 'still-chart-dark.webp', 'The chart view after the theme switch (the plugin got new tokens and redrew; the .base file did not change): peak torque vs mass on log axes, '
             'coloured by brand, one envelope per form, the median torque-per-gram line. The lone dot at 140 kg is CubeMars AKE40-6 KV90: robotparts says 140 g (see "Found while building").')
        await pg.click('.du-theme')
        await pg.wait_for_timeout(500)

        # --- board: evidence level (derived: refuse)
        await tab(pg, 2, 'kanban')
        counts = await pg.evaluate("[...document.querySelectorAll('.du-col')].map(c => c.querySelector('.du-count').textContent)")
        check('Board columns = groupOrder 0-5, with empty levels shown', ', '.join(counts), len(counts) == 6 and counts[1] == '1,147')
        await drag(pg, '.du-col[data-col="1"] .du-kcard', '.du-col[data-col="2"] .du-col-scroll', {'x': 100, 'y': 200})
        toast = await pg.locator('.du-toast').get_attribute('class')
        counts2 = await pg.evaluate("[...document.querySelectorAll('.du-col')].map(c => c.querySelector('.du-count').textContent)")
        check('Card drop on a derived property is refused; nothing moves', f'toast "{toast}", counts {", ".join(counts2)}', 'refused' in toast and counts2 == counts)
        png = await demo.screenshot()
        webp(png, 'still-board-refused.webp', 'The board grouped by evidence level (robotparts SCHEMA2 §3): 1,147 actuators listed, one cited, one in sim. A card dropped on "2 · cited" is refused, because a level is computed, never set.')

        # --- board: form (writable: accept), then a column drag (view config)
        await tab(pg, 3, 'kanban')
        heads = await pg.evaluate("[...document.querySelectorAll('.du-col-head span:first-child')].map(s => s.textContent)")
        counts = await pg.evaluate("[...document.querySelectorAll('.du-col')].map(c => c.querySelector('.du-count').textContent)")
        # WHY these two columns: both are fully on screen at 1440 px (the board scrolls sideways past the fourth)
        hobby_i, dd_i = heads.index('hobby servo'), heads.index('direct drive')
        await drag(pg, f'.du-col[data-col="{hobby_i}"] .du-kcard', f'.du-col[data-col="{dd_i}"] .du-col-scroll', {'x': 100, 'y': 300})
        counts2 = await pg.evaluate("[...document.querySelectorAll('.du-col')].map(c => c.querySelector('.du-count').textContent)")
        heads_after = await pg.evaluate("[...document.querySelectorAll('.du-col-head span:first-child')].map(s => s.textContent)")
        counts2 = dict(zip(heads_after, counts2))
        counts = dict(zip(heads, counts))
        hobby, dd = 'hobby servo', 'direct drive'
        n = lambda x: int(x.replace(',', ''))
        ok = n(counts2[hobby]) == n(counts[hobby]) - 1 and n(counts2[dd]) == n(counts[dd]) + 1
        check('Card drop on an editable property: the host accepts, every view re-reads', f'hobby servo {counts[hobby]}→{counts2[hobby]}, direct drive {counts[dd]}→{counts2[dd]}', ok)
        await pg.wait_for_timeout(2500)
        ia_i = heads_after.index('integrated actuator')
        await drag(pg, f'.du-col[data-col="{ia_i}"] .du-col-head', '.du-col[data-col="0"] .du-col-head', {'x': 8, 'y': 10})
        go = await pg.evaluate("window.__duHost.base.views[3].groupOrder || null")
        yaml_has = await pg.evaluate("document.querySelector('.du-yaml mark').textContent.includes('groupOrder')")
        heads2 = await pg.evaluate("[...document.querySelectorAll('.du-col-head span:first-child')].map(s => s.textContent)")
        check('Column drag writes groupOrder into the view entry (and only the view)', f'groupOrder {go}; first column now "{heads2[0]}"', bool(go) and go[0] == 'integrated actuator' and yaml_has and heads2[0] == 'integrated actuator')
        png = await demo.screenshot()
        webp(png, 'still-board-accepted.webp', 'The board grouped by form after two writes: a hobby servo moved to "direct drive" (a data edit the host accepted) and the "integrated actuator" column dragged first (view config: groupOrder, now in the .base file on the right).')
        await pg.click('.du-kcard')
        await pg.wait_for_timeout(300)
        peek = await pg.locator('.du-peek').is_visible()
        name = await pg.inner_text('.du-peek header b') if peek else ''
        check('Any card opens the shared record peek (host.open)', name, peek and bool(name))
        check('No request leaves the file (no CDN, no tiles, no fonts)', f'{len(foreign)} foreign requests', not foreign)
        check('No page errors', f'{len(errors)} errors' + (f': {errors[0][:120]}' if errors else ''), not errors)
        video = await pg.video.path()
        await ctx.close()

        # --- phone width
        ctx2 = await browser.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2)
        pg2 = await ctx2.new_page()
        await pg2.goto(URL + '#view=cards')
        await pg2.wait_for_selector('#du-demo[data-ready]', timeout=30000)
        sw = await pg2.evaluate('document.documentElement.scrollWidth')
        check('Phone width 390 px: no sideways page scroll', f'scrollWidth {sw}', sw <= 390)
        await pg2.click('.du-tab[data-i="1"]')
        await pg2.wait_for_selector('.du-chart svg', timeout=30000)
        await pg2.wait_for_timeout(400)
        med, runs = await chart_timing(pg2)
        check('Chart re-render after a filter change at 390 px, re-embedding the spec (SPEC §8.11 gate: < 100 ms)', f'median {med} ms of {runs}', med < 100)
        await pg2.evaluate("document.querySelector('#du-demo').scrollIntoView({block: 'start'})")
        await pg2.wait_for_timeout(500)
        await ctx2.close()
        await browser.close()

    # --- hero clip: the recorded desktop session, trimmed to the demo, ~12 s
    hero = os.path.join(BUILD, 'hero.mp4')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', video, '-vf', 'fps=8,scale=900:-2', '-ss', '1.6', '-c:v', 'libx264', '-preset', 'veryslow',
                    '-crf', '43', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an', hero], check=True)
    print(f'  hero {os.path.getsize(hero) / 1024:.0f} KB')
    json.dump({'checks': checks, 'images': images, 'hero': 'hero.mp4'}, open(os.path.join(BUILD, 'stills.json'), 'w'), indent=1)
    print(f"{sum(c[2] for c in checks)}/{len(checks)} checks pass")


asyncio.run(main())
