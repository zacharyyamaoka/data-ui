/* The live cards (docs/peps/0012-live-data.md §6, docs/CONTRACT.md §26): `plot` (uPlot) and `levels`.
   WHY one bundle for both: a live dashboard usually shows both, and neither needs Vega; the registry constructs the
   module's default class for each type, and the element's class says which it is (as the chart bundle does). */

import css from './live.css';
import uplotCss from 'uplot/dist/uPlot.min.css';
import { PlotView } from './plot.js';
import { LevelsView } from './levels.js';

const all = `${uplotCss}\n${css}`;
export { all as css };
export { PlotView, LevelsView };
export { levelBins, worstOf, LEVELS } from './levels-model.js';

export default class LiveView {
  constructor(host, el) {
    if (el.classList.contains('dv-view-levels')) return new LevelsView(host, el);
    return new PlotView(host, el);
  }
}
