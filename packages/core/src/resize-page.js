/* dist/resize.js: resizable side panels on a page that loads nothing else of the kit (docs/CONTRACT.md §11).

     <script type="module" src="/static/vendor/data-ui/resize.js"></script>
     <nav class="side" data-resizable="right">…</nav>        the host's CSS: .side { width: var(--data-panel-width, 14rem) }

   It adds its own stylesheet (the handle), once, and gives every [data-resizable="left|right"] its handle. A page with
   data-ui.js already has both; loading this beside it is harmless (one handle per panel). */

import { autoResize } from './resize.js';
import css from '../styles/resize.css';

export { makeResizable, autoResize } from './resize.js';

if (typeof document !== 'undefined') {
  if (!document.querySelector('style[data-ui-resize]')) {
    const style = document.createElement('style');
    style.dataset.uiResize = '';
    style.textContent = css;
    document.head.append(style);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => autoResize(), { once: true });
  else autoResize();
}
