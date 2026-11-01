/* The cards view's lightbox (`lightbox: true`): PhotoSwipe 5.4.4 and its stylesheet, in their own file.
   WHY its own file (review 2026-10-26 item 8): every cards view loaded PhotoSwipe before anyone opened an image; now
   cards.js imports this the first time a photo is opened (build.mjs splits it into views/cards-lightbox-<hash>.js). */
import PhotoSwipe from 'photoswipe';
import css from 'photoswipe/style.css';

export { PhotoSwipe, css };
