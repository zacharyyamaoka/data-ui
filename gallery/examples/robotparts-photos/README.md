# robotparts photos

175 of robotparts.dev's actuators and cameras as cards with their real hosted photos and their brands' logos, one
`.base` file: actuators and cameras grouped by brand, a photo wall, and the table over the same rows. Click a photo
for the lightbox; its caption says where the photo came from and when it was fetched.

- **App:** robotparts
- **Replaces:** robotparts' hand-rolled picture cards: the round-2 design babble's image-first card grid
  (`design/babble-2026-10-22b/w5-gallery/gallery.js`, `cardHtml` / `cardMedia`) and the PCPartPicker variant's
  photo cells (`w2-pcpartpicker/app.js`), each its own grid, image well and spec lines.
- **Shows:** `type: cards` with Bases' `image`, `imageFit`, `imageAspectRatio` and `cardSize`; group headings by
  brand inside a virtualised grid; a property drawn as an image (`logo` has `display: image`); the media grid
  (`lightbox: true`, `caption`) with the photo's source and fetch date from its rich cell `{value, source, asOf}`; the
  rail filtering every view.
- **Data:** `photos.json` and the `p-*.webp` / `logo-*` files in `media/`, written by `source/make.py` from robotparts'
  v2 catalog (release 2026.10.25.1) and its hosted media index (`media/photos.jsonl`, `media/brands.jsonl`): 175
  photos and 17 logos, 2.2 MB. robotparts hosts these under Zach's 2026-10-25 decision (`hosting_basis: owner`),
  linked to the source, removed on request.
