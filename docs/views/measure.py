"""Measure every candidate library in docs/VIEWS.md the same way, and record its npm metadata.

  ~/psu-atlas/.venv/bin/python docs/views/measure.py <scratch-dir>            # install, then measure
  ~/psu-atlas/.venv/bin/python docs/views/measure.py <scratch-dir> --no-install

Size: an esbuild bundle of the documented entry, minified, gzip -9 (React/ReactDOM external, counted once as the
'react-island' row). CSS: the shipped stylesheet, gzipped, with its count of custom-property definitions (--x:) and
var() uses, as evidence for theming. Metadata: registry.npmjs.org's latest version, its publish date, licence, peers.
The scratch dir gets an npm install with --ignore-scripts (no package code runs; esbuild only reads it).
Writes docs/views/measurements.json. Stdlib only; needs node + npm and docs/views' own esbuild (npm install there).
"""
import concurrent.futures as cf
import gzip
import json
import os
import re
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ESBUILD = os.path.join(HERE, 'node_modules', '.bin', 'esbuild')
OUT = os.path.join(HERE, 'measurements.json')
REACT = ['react', 'react-dom', 'react/jsx-runtime', 'react-dom/client', 'react/jsx-dev-runtime']

# exact versions measured on 2026-10-25 (the latest on npm that day)
INSTALL = {
    "@atlaskit/pragmatic-drag-and-drop": "4.0.0",
    "@atlaskit/pragmatic-drag-and-drop-hitbox": "3.0.0",
    "@awesome.me/webawesome": "3.14.0",
    "@dagrejs/dagre": "3.1.3",
    "@dnd-kit/core": "6.3.1",
    "@dnd-kit/dom": "0.5.1",
    "@egjs/hammerjs": "2.0.17",
    "@event-calendar/build": "5.18.1",
    "@event-calendar/core": "5.18.1",
    "@fancyapps/ui": "6.1.15",
    "@full-ui/headless-calendar": "7.1.3",
    "@fullcalendar/core": "7.1.3",
    "@headless-tree/core": "1.8.0",
    "@hello-pangea/dnd": "18.0.1",
    "@json-editor/json-editor": "2.17.3",
    "@jsonforms/core": "3.8.0",
    "@jsonforms/react": "3.8.0",
    "@jsonforms/vanilla-renderers": "3.8.0",
    "@kanaries/graphic-walker": "0.5.3",
    "@observablehq/plot": "0.6.17",
    "@preact/signals": "2.11.3",
    "@rjsf/core": "6.11.0",
    "@rjsf/utils": "6.11.0",
    "@rjsf/validator-ajv8": "6.11.0",
    "@schedule-x/calendar": "4.9.1",
    "@schedule-x/theme-default": "4.9.1",
    "@svar-ui/react-gantt": "2.8.1",
    "@tanstack/table-core": "9.3.1",
    "@tanstack/virtual-core": "3.19.7",
    "@toast-ui/calendar": "2.1.3",
    "@tremor/react": "3.18.7",
    "@xyflow/react": "12.12.0",
    "@xyflow/svelte": "1.7.0",
    "@xyflow/system": "0.0.83",
    "chart.js": "4.6.1",
    "component-emitter": "2.0.0",
    "cytoscape": "3.34.4",
    "d3-force": "3.0.0",
    "d3-hierarchy": "3.1.2",
    "dhtmlx-gantt": "10.0.3",
    "echarts": "6.1.0",
    "force-graph": "1.52.0",
    "frappe-gantt": "1.2.2",
    "fullcalendar": "7.1.3",
    "glightbox": "3.3.1",
    "graphology": "0.26.0",
    "graphology-types": "0.24.8",
    "img-comparison-slider": "8.0.7",
    "jkanban": "1.3.1",
    "jquery": "4.0.0",
    "justified-layout": "4.1.0",
    "keycharm": "0.4.0",
    "leaflet": "1.9.4",
    "lightgallery": "3.0.0",
    "maplibre-gl": "6.16.0",
    "masonry-layout": "4.2.2",
    "muuri": "0.9.5",
    "ol": "10.11.0",
    "photoswipe": "5.4.4",
    "pivottable": "2.23.0",
    "plotly.js-dist-min": "4.1.2",
    "pmtiles": "4.5.0",
    "preact": "11.0.2",
    "react": "19.3.1",
    "react-arborist": "4.0.1",
    "react-dnd": "16.0.1",
    "react-dnd-html5-backend": "16.0.1",
    "react-dom": "19.3.1",
    "react-hook-form": "7.91.0",
    "sigma": "4.0.3",
    "sortablejs": "1.15.7",
    "svelte": "5.57.2",
    "tabulator-tables": "6.7.1",
    "temporal-polyfill": "1.0.6",
    "uplot": "1.6.32",
    "uuid": "14.0.3",
    "vega": "6.4.0",
    "vega-embed": "7.3.0",
    "vega-interpreter": "2.3.2",
    "vega-lite": "6.5.0",
    "vega-tooltip": "1.1.0",
    "virtua": "0.53.6",
    "vis-data": "8.0.6",
    "vis-network": "10.1.3",
    "vis-timeline": "8.5.5",
    "vis-util": "6.0.3",
    "xstate": "5.33.3",
}

# packages whose registry metadata is recorded (some are too big or proprietary to install)
REGISTRY = [
    "react",
    "react-dom",
    "@atlaskit/pragmatic-drag-and-drop",
    "@atlaskit/pragmatic-drag-and-drop-hitbox",
    "@awesome.me/webawesome",
    "@dagrejs/dagre",
    "@dnd-kit/core",
    "@dnd-kit/dom",
    "@event-calendar/build",
    "@event-calendar/core",
    "@fancyapps/ui",
    "@finos/perspective",
    "@finos/perspective-viewer",
    "@full-ui/headless-calendar",
    "@fullcalendar/core",
    "@headless-tree/core",
    "@hello-pangea/dnd",
    "@json-editor/json-editor",
    "@jsonforms/core",
    "@jsonforms/vanilla-renderers",
    "@kanaries/graphic-walker",
    "@observablehq/framework",
    "@observablehq/plot",
    "@perspective-dev/client",
    "@perspective-dev/viewer",
    "@perspective-dev/viewer-d3fc",
    "@perspective-dev/viewer-datagrid",
    "@rjsf/core",
    "@schedule-x/calendar",
    "@schedule-x/drag-and-drop",
    "@svar-ui/react-gantt",
    "@tanstack/table-core",
    "@tanstack/virtual-core",
    "@toast-ui/calendar",
    "@tremor/react",
    "@xyflow/react",
    "@xyflow/svelte",
    "@xyflow/system",
    "ag-charts-community",
    "ag-grid-community",
    "chart.js",
    "clusterize.js",
    "cytoscape",
    "d3-force",
    "d3-hierarchy",
    "datatables.net",
    "dhtmlx-gantt",
    "diff",
    "echarts",
    "elkjs",
    "flexmonster",
    "force-graph",
    "frappe-gantt",
    "fullcalendar",
    "glightbox",
    "graphology",
    "img-comparison-slider",
    "jkanban",
    "justified-layout",
    "leaflet",
    "lightgallery",
    "maplibre-gl",
    "masonic",
    "masonry-layout",
    "muuri",
    "ol",
    "photoswipe",
    "pivottable",
    "plotly.js-dist-min",
    "pmtiles",
    "react-arborist",
    "react-hook-form",
    "sigma",
    "sortablejs",
    "tabulator-tables",
    "temporal-polyfill",
    "uplot",
    "vega",
    "vega-embed",
    "vega-interpreter",
    "vega-lite",
    "vega-tooltip",
    "virtua",
    "vis-network",
    "vis-timeline",
    "webdatarocks"
]

ALL = lambda p: f"import * as m from '{p}'; globalThis.__m = m;"
ITEMS = [
    # id, entry js, externals, css paths (relative to node_modules)
    ('tanstack-table-core', ALL('@tanstack/table-core'), [], []),
    ('tanstack-virtual-core', ALL('@tanstack/virtual-core'), [], []),
    ('virtua-core', ALL('virtua/unstable_core'), [], []),
    ('masonry-layout', ALL('masonry-layout'), [], []),
    ('muuri', ALL('muuri'), [], []),
    ('photoswipe', "import PhotoSwipeLightbox from 'photoswipe/lightbox'; import PhotoSwipe from 'photoswipe'; globalThis.__m=[PhotoSwipeLightbox,PhotoSwipe];", [], ['photoswipe/dist/photoswipe.css']),
    ('glightbox', ALL('glightbox'), [], ['glightbox/dist/css/glightbox.min.css']),
    ('lightgallery', ALL('lightgallery'), [], ['lightgallery/css/lightgallery.css']),
    ('fancybox', "import { Fancybox } from '@fancyapps/ui'; globalThis.__m=Fancybox;", [], ['@fancyapps/ui/dist/fancybox/fancybox.css']),
    ('justified-layout', ALL('justified-layout'), [], []),
    ('img-comparison-slider', ALL('img-comparison-slider'), [], []),
    ('vega+vega-lite+vega-embed', "import embed from 'vega-embed'; globalThis.__m=embed;", [], []),
    ('vega+vega-lite', "import * as vega from 'vega'; import * as vl from 'vega-lite'; globalThis.__m=[vega,vl];", [], []),
    ('vega-runtime-only', ALL('vega'), [], []),
    ('vega-interpreter', ALL('vega-interpreter'), [], []),
    ('echarts-full', ALL('echarts'), [], []),
    ('echarts-subset', """import * as echarts from 'echarts/core';
import { ScatterChart, LineChart, BarChart, BoxplotChart, CustomChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, DatasetComponent, TransformComponent, DataZoomComponent, MarkLineComponent, TitleComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
echarts.use([ScatterChart, LineChart, BarChart, BoxplotChart, CustomChart, GridComponent, TooltipComponent, LegendComponent, DatasetComponent, TransformComponent, DataZoomComponent, MarkLineComponent, TitleComponent, CanvasRenderer]);
globalThis.__m = echarts;""", [], []),
    ('observable-plot', ALL('@observablehq/plot'), [], []),
    ('uplot', ALL('uplot'), [], ['uplot/dist/uPlot.min.css']),
    ('chart.js-auto', "import Chart from 'chart.js/auto'; globalThis.__m=Chart;", [], []),
    ('plotly.js-dist-min', "import * as m from 'plotly.js-dist-min'; globalThis.__m=m;", [], []),
    ('graphic-walker', ALL('@kanaries/graphic-walker'), REACT, []),
    ('tremor-react', ALL('@tremor/react'), REACT, []),
    ('react-island(react+react-dom/client)', "import * as R from 'react'; import { createRoot } from 'react-dom/client'; globalThis.__m=[R,createRoot];", [], []),
    ('dnd-kit-dom', ALL('@dnd-kit/dom'), [], []),
    ('dnd-kit-core(react)', ALL('@dnd-kit/core'), REACT, []),
    ('sortablejs', ALL('sortablejs'), [], []),
    ('pragmatic-dnd(element+hitbox+autoscroll)', """import { draggable, dropTargetForElements, monitorForElements } from '@atlaskit/pragmatic-drag-and-drop/element/adapter';
import { combine } from '@atlaskit/pragmatic-drag-and-drop/combine';
import { attachClosestEdge, extractClosestEdge } from '@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge';
globalThis.__m=[draggable, dropTargetForElements, monitorForElements, combine, attachClosestEdge, extractClosestEdge];""", [], []),
    ('jkanban', "import 'jkanban'; ", [], ['jkanban/dist/jkanban.min.css']),
    ('hello-pangea-dnd(react)', ALL('@hello-pangea/dnd'), REACT, []),
    ('fullcalendar7(daygrid+timegrid+list+interaction+classic)', """import { Calendar } from 'fullcalendar';
import dayGridPlugin from 'fullcalendar/daygrid'; import timeGridPlugin from 'fullcalendar/timegrid';
import listPlugin from 'fullcalendar/list'; import interactionPlugin from 'fullcalendar/interaction';
import classic from 'fullcalendar/themes/classic';
globalThis.__m=[Calendar, dayGridPlugin, timeGridPlugin, listPlugin, interactionPlugin, classic];""", ['temporal-polyfill', 'temporal-polyfill/*'], ['fullcalendar/skeleton.css', 'fullcalendar/themes/classic/theme.css', 'fullcalendar/themes/classic/palette.css']),
    ('temporal-polyfill', "import 'temporal-polyfill/global';", [], []),
    ('event-calendar-build', "import '@event-calendar/build';", [], ['@event-calendar/build/dist/event-calendar.min.css']),
    ('schedule-x-calendar(+preact)', ALL('@schedule-x/calendar'), ['temporal-polyfill', 'temporal-polyfill/*'], ['@schedule-x/theme-default/dist/index.css']),
    ('toast-ui-calendar', ALL('@toast-ui/calendar'), [], ['@toast-ui/calendar/dist/toastui-calendar.min.css']),
    ('frappe-gantt', ALL('frappe-gantt'), [], ['frappe-gantt/dist/frappe-gantt.css']),
    ('vis-timeline-standalone', ALL('vis-timeline/standalone'), [], ['vis-timeline/styles/vis-timeline-graph2d.min.css']),
    ('dhtmlx-gantt', ALL('dhtmlx-gantt'), [], ['dhtmlx-gantt/codebase/dhtmlxgantt.css']),
    ('svar-react-gantt', ALL('@svar-ui/react-gantt'), REACT, []),
    ('maplibre-gl', ALL('maplibre-gl'), [], ['maplibre-gl/dist/maplibre-gl.css']),
    ('leaflet', ALL('leaflet'), [], ['leaflet/dist/leaflet.css']),
    ('openlayers(Map+View+Tile+Vector)', """import Map from 'ol/Map'; import View from 'ol/View'; import TileLayer from 'ol/layer/Tile'; import VectorLayer from 'ol/layer/Vector';
import VectorSource from 'ol/source/Vector'; import XYZ from 'ol/source/XYZ'; import GeoJSON from 'ol/format/GeoJSON';
globalThis.__m=[Map,View,TileLayer,VectorLayer,VectorSource,XYZ,GeoJSON];""", [], ['ol/ol.css']),
    ('pmtiles', ALL('pmtiles'), [], []),
    ('headless-tree-core', ALL('@headless-tree/core'), [], []),
    ('react-arborist(react)', ALL('react-arborist'), REACT, []),
    ('d3-hierarchy', ALL('d3-hierarchy'), [], []),
    ('webawesome-tree', "import '@awesome.me/webawesome/dist/components/tree/tree.js'; import '@awesome.me/webawesome/dist/components/tree-item/tree-item.js';", [], []),
    ('cytoscape', ALL('cytoscape'), [], []),
    ('sigma+graphology', "import Sigma from 'sigma'; import Graph from 'graphology'; globalThis.__m=[Sigma,Graph];", [], []),
    ('xyflow-react(react external)', ALL('@xyflow/react'), REACT, ['@xyflow/react/dist/style.css']),
    ('xyflow-react+react island', "import * as X from '@xyflow/react'; import * as R from 'react'; import { createRoot } from 'react-dom/client'; globalThis.__m=[X,R,createRoot];", [], []),
    ('xyflow-system', ALL('@xyflow/system'), [], []),
    ('vis-network-standalone', ALL('vis-network/standalone'), [], []),
    ('force-graph', ALL('force-graph'), [], []),
    ('jsonforms-core', ALL('@jsonforms/core'), [], []),
    ('jsonforms-vanilla(react)', "import * as a from '@jsonforms/vanilla-renderers'; import * as b from '@jsonforms/react'; globalThis.__m=[a,b];", REACT + ['@jsonforms/core'], []),
    ('react-hook-form(react)', ALL('react-hook-form'), REACT, []),
    ('rjsf-core(react)', "import * as a from '@rjsf/core'; import * as b from '@rjsf/utils'; import v from '@rjsf/validator-ajv8'; globalThis.__m=[a,b,v];", REACT, []),
    ('json-editor', ALL('@json-editor/json-editor'), [], []),
    ('pivottable(+jquery)', "import $ from 'jquery'; globalThis.jQuery=$; import 'pivottable';", [], ['pivottable/dist/pivot.min.css']),
    ('dagre', ALL('@dagrejs/dagre'), [], []),
    ('d3-force', ALL('d3-force'), [], []),
    ('tabulator', "import {TabulatorFull} from 'tabulator-tables'; globalThis.__m=TabulatorFull;", [], ['tabulator-tables/dist/css/tabulator.min.css']),
]



def gz(b):
    return len(gzip.compress(b, 9))


def css_stats(root, paths):
    total = b''
    for p in paths:
        f = os.path.join(root, 'node_modules', p)
        if not os.path.exists(f):
            return {'missing': p}
        total += open(f, 'rb').read()
    text = total.decode('utf-8', 'replace')
    return {'css_bytes': len(total), 'css_gz': gz(total), 'custom_props_defined': len(set(re.findall(r'(--[A-Za-z0-9_-]+)\s*:', text))),
            'var_uses': len(re.findall(r'var\(--', text))}


def registry(name):
    url = 'https://registry.npmjs.org/' + name.replace('/', '%2F')
    d = json.load(urllib.request.urlopen(url, timeout=60))
    latest = d['dist-tags']['latest']
    v = d['versions'][latest]
    lic = v.get('license') or d.get('license')
    return name, {'latest': latest, 'published': d['time'].get(latest), 'license': lic.get('type') if isinstance(lic, dict) else lic,
                  'peer': sorted((v.get('peerDependencies') or {}).keys()), 'deps': len(v.get('dependencies') or {}),
                  'dist_tags': d['dist-tags'], 'url': 'https://www.npmjs.com/package/' + name}


def main():
    root = os.path.abspath(sys.argv[1])
    os.makedirs(root, exist_ok=True)
    if '--no-install' not in sys.argv:
        json.dump({'name': 'measure', 'private': True, 'dependencies': INSTALL}, open(os.path.join(root, 'package.json'), 'w'), indent=1)
        subprocess.run(['npm', 'install', '--ignore-scripts', '--legacy-peer-deps', '--no-audit', '--no-fund'], cwd=root, check=True)
    entries = os.path.join(root, '_entries')
    os.makedirs(entries, exist_ok=True)
    sizes = {}
    for ident, code, ext, css in ITEMS:
        slug = re.sub(r'[^a-z0-9]+', '-', ident.lower()).strip('-')
        entry, out = os.path.join(entries, slug + '.mjs'), os.path.join(entries, slug + '.out.js')
        open(entry, 'w').write(code + '\n')
        cmd = [ESBUILD, entry, '--bundle', '--minify', '--format=esm', '--platform=browser', '--log-level=error', '--loader:.css=empty',
               '--loader:.svg=dataurl', '--loader:.woff2=empty', '--loader:.wasm=file', '--define:process.env.NODE_ENV="production"', '--outfile=' + out]
        cmd += ['--external:' + e for e in ext]
        r = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
        rec = {'externals': ext}
        if r.returncode:
            rec['error'] = r.stderr.strip()[:400]
        else:
            b = open(out, 'rb').read()
            rec.update({'min_bytes': len(b), 'min_gz': gz(b)})
        if css:
            rec['css'] = css_stats(root, css)
        sizes[ident] = rec
        print(ident, rec.get('error') or f"{rec['min_bytes'] / 1024:.1f} KB min, {rec['min_gz'] / 1024:.1f} KB gz")
    meta = {}
    with cf.ThreadPoolExecutor(12) as ex:
        for name, rec in ex.map(registry, REGISTRY):
            meta[name] = rec
    installed = {n: json.load(open(os.path.join(root, 'node_modules', n, 'package.json')))['version'] for n in INSTALL}
    json.dump({'measured_on': '2026-10-25', 'method': __doc__.strip().splitlines()[0], 'installed': installed, 'sizes': sizes,
               'registry': dict(sorted(meta.items()))}, open(OUT, 'w'), indent=1)
    print('wrote', OUT)


if __name__ == '__main__':
    main()
