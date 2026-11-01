#!/usr/bin/env python3
"""The 3D thumbnail bench (docs/CONTRACT.md §13): data-ui's shared renderer against one WebGL renderer per card,
Google's <model-viewer> and pre-rendered turntable sprites, on the object-db-shelf case's real GLBs. The numbers in
reports/data-ui-object-db-2026-10-26.html come from this; it is the speed KPI's source.

    npm --prefix ~/data-ui/.wt/object-db run build
    ~/psu-atlas/.venv/bin/python docs/bench_3d/run_bench.py OUT.json [--model-viewer PATH/model-viewer.min.js]

It stages dist/site/bench/ (this folder's page, three from node_modules, a 2,454-card stress copy of the case's rows:
409 x 6), serves dist/site on a free 127.0.0.1 port, runs each mode three times (median kept) under SwiftShader and,
when headless reaches it, the GPU, and stops the server. <model-viewer> is not a data-ui dependency: pass the path of
@google/model-viewer@4.4.0's dist/model-viewer.min.js (npm install it anywhere) or that mode is skipped.
"""
import json, pathlib, shutil, socket, statistics, subprocess, sys, time, urllib.request
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
SITE = ROOT / "dist" / "site"
BENCH = SITE / "bench"
args = sys.argv[1:]
OUT = args[0]
MV = args[args.index("--model-viewer") + 1] if "--model-viewer" in args else None


def stage():
    BENCH.mkdir(parents=True, exist_ok=True)
    here = pathlib.Path(__file__).resolve().parent
    for f in ("index.html", "bench.js"):
        shutil.copyfile(here / f, BENCH / f)
    three = ROOT / "node_modules" / "three"
    (BENCH / "three" / "build").mkdir(parents=True, exist_ok=True)
    for f in ("three.module.js", "three.core.js"):
        shutil.copyfile(three / "build" / f, BENCH / "three" / "build" / f)
    shutil.copytree(three / "examples" / "jsm", BENCH / "three" / "examples" / "jsm", dirs_exist_ok=True)
    if MV:
        shutil.copyfile(MV, BENCH / "model-viewer.min.js")
    d = json.loads((ROOT / "gallery" / "examples" / "object-db-shelf" / "objects.json").read_text())
    rows = []
    for k in range(6):
        for r in d["rows"]:
            r2 = dict(r, id=f"{r['id']}~{k}")
            for p in ("thumbnail", "mesh", "soft_thumbnail"):
                if r2.get(p):
                    r2[p] = "../gallery/object-db-shelf/" + r2[p]
            rows.append(r2)
    (BENCH / "stress.json").write_text(json.dumps(dict(d, id="stress", rows=rows)))
    (BENCH / "stress.base").write_text("data: stress.json\nviews:\n  - type: cards\n    name: Stress\n    order: [name, type, mass_g]\n    image: thumbnail\n"
        "    mesh: mesh\n    imageFit: contain\n    cardSize: 170\n    sort:\n      - { property: geometry, direction: DESC }\n      - { property: type, direction: ASC }\n")
    (BENCH / "stress.html").write_text('<!doctype html><html><head><meta charset="utf-8"><title>stress</title><link rel="stylesheet" href="../site.css">'
        '<link rel="stylesheet" href="../kit/data-ui.css"><script type="module" src="../kit/data-ui.js"></script>'
        '<style>body{margin:0} data-views{height:100vh;--data-height:100vh}</style></head><body><data-views id="example" src="stress.base" no-url frame="flush"></data-views></body></html>')


RUNS = 3
GPU_ARGS = ['--enable-precise-memory-info', '--enable-gpu', '--ignore-gpu-blocklist', '--use-angle=vulkan', '--enable-features=Vulkan']

def renderer_name(page):
    return page.evaluate("""(() => { const c = document.createElement('canvas').getContext('webgl'); if (!c) return 'no webgl';
      const e = c.getExtension('WEBGL_debug_renderer_info'); return e ? c.getParameter(e.UNMASKED_RENDERER_WEBGL) : c.getParameter(c.RENDERER); })()""")

def bench_mode(browser, mode, n=40):
    out = []
    for _ in range(RUNS):
        ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = ctx.new_page()
        page.goto(f'{BASE}/bench/index.html?mode={mode}&n={n}')
        page.wait_for_function('window.__result', timeout=90000)
        out.append(page.evaluate('window.__result'))
        ctx.close()
    return out

def bench_ours(browser, path, hovers=12):
    res = []
    for _ in range(RUNS):
        ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
        ctx.add_init_script("""window.__gl = { made: 0 }; const o = HTMLCanvasElement.prototype.getContext;
          HTMLCanvasElement.prototype.getContext = function (k, ...r) { const c = o.call(this, k, ...r); if (c && /webgl/.test(String(k)) && !this.__c) { this.__c = 1; window.__gl.made++; } return c; };
          new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__lcp = e.startTime; }).observe({ type: 'largest-contentful-paint', buffered: true });""")
        page = ctx.new_page()
        t = time.time()
        page.goto(f'{BASE}/{path}')
        page.wait_for_function("document.querySelector('data-views .dv-status') && document.querySelector('data-views .dv-status').textContent.trim()", timeout=30000)
        ready_ms = round((time.time() - t) * 1000)
        page.wait_for_function("[...document.querySelectorAll('data-views .dv-cards-card .dv-mesh-poster')].length > 8 && [...document.querySelectorAll('data-views .dv-cards-card .dv-mesh-poster')].slice(0, 8).every(i => i.complete && i.naturalWidth)", timeout=30000)
        page.wait_for_timeout(600)
        first = page.evaluate("""(() => { const nav = performance.getEntriesByType('navigation')[0]; const imgs = performance.getEntriesByType('resource').filter(e => /thumbs\\//.test(e.name));
          return { domContentLoaded: Math.round(nav.domContentLoadedEventEnd), firstPosterMs: imgs.length ? Math.round(Math.min(...imgs.map(e => e.responseEnd))) : null, lcpMs: Math.round(window.__lcp || 0),
                   postersFetched: imgs.length, cardsInDom: document.querySelectorAll('data-views .dv-cards-card').length, rows: document.querySelector('data-views .dv-status').textContent.split(' · ')[0],
                   heapMB: +(performance.memory.usedJSHeapSize / 1048576).toFixed(1), contexts: window.__gl.made }; })()""")
        live = []
        for i in range(hovers):
            m = page.locator('data-views .dv-cards-card data-mesh').nth(i)
            m.scroll_into_view_if_needed()
            t = time.time()
            m.hover()
            page.wait_for_function(f"document.querySelectorAll('data-views .dv-cards-card data-mesh')[{i}].classList.contains('dv-mesh-live')", timeout=15000)
            live.append(round((time.time() - t) * 1000))
            page.wait_for_timeout(250)
        page.mouse.move(1, 1)
        st = page.evaluate("customElements.get('data-mesh').stats()")
        after = page.evaluate("({ heapMB: +(performance.memory.usedJSHeapSize / 1048576).toFixed(1), contexts: window.__gl.made })")
        res.append({**first, 'hoverToLiveFirstMs': live[0], 'hoverToLiveMedianMs': statistics.median(live[1:]), 'renderMsPerFrame': round(st['renderMs'], 2),
                    'modelsFetched': st['modelsLoaded'], 'modelKB': st['bytes'] // 1024, 'liveMax': st['liveMax'], 'heapAfterMB': after['heapMB'], 'contextsAfter': after['contexts']})
        ctx.close()
    return res

def med(runs):
    keys = runs[0].keys()
    out = {}
    for k in keys:
        vals = [r[k] for r in runs]
        out[k] = statistics.median(vals) if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals) else vals[0]
    return out

def main():
    global BASE
    stage()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(SITE)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    BASE = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(BASE + "/index.html", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        run()
    finally:
        server.terminate()
        server.wait(timeout=10)


def run():
    results = {}
    with sync_playwright() as p:
        for label, args in (('swiftshader', ['--enable-precise-memory-info']), ('gpu', GPU_ARGS)):
            b = p.chromium.launch(args=args)
            pg = b.new_page(); pg.goto(f'{BASE}/bench/index.html?mode=none'); name = renderer_name(pg); pg.close()
            print(label, name, flush=True)
            if label == 'gpu' and 'SwiftShader' in name:
                print('no GPU in headless; skipping the GPU pass', flush=True)
                b.close(); continue
            r = {'renderer': name}
            r['ours_409'] = med(bench_ours(b, 'gallery/object-db-shelf/index.html'))
            print('ours 409', r['ours_409'], flush=True)
            r['ours_2454'] = med(bench_ours(b, 'bench/stress.html'))
            print('ours 2454', r['ours_2454'], flush=True)
            for mode in ('percard', 'mv', 'sprite') if MV else ('percard', 'sprite'):
                r[mode] = med(bench_mode(b, mode))
                print(mode, r[mode], flush=True)
            results[label] = r
            b.close()
    json.dump(results, open(OUT, 'w'), indent=1)


if __name__ == "__main__":
    main()
