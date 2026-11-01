# robotparts design babble

The ten robotparts.dev design proposals from the two babbles of 2026-10-22 (five design languages, then five catalog
designs) as cards with their stills: each card the proposal's landing page, its weighted score out of 100 and when
it wins; open any still full screen and arrow through the rest. Other views show every still per proposal and the
phone layouts side by side.

- **App:** design work
- **Replaces:** the babble skill's hand-built comparison galleries for those rounds (`design/babble-2026-10-22*/
  build_gallery_spec.py` writing `gallery-spec.json`, whose `media` entries inline every still as base64 HTML).
- **Shows:** cards with `imageFit: cover` and `contain` on the same stills, a tall `imageAspectRatio` for phone
  shots, groups by round and by proposal, the lightbox with a caption (`caption: [round, score, thesis]`) and the
  still's source path and date, a derived score, a boolean (`default`, the babble's own pick).
- **Data:** `babble.json` and the `b1-*` / `b2-*` WebP stills in `stills/` (30 stills, 1.1 MB), written by
  `source/make.py` from each round's `gallery-spec.json` and the variants' `shots/` (desktop stills re-encoded at
  960 px, phones at 375 px). The score is the babble's own: sum(score × weight) / 5, which reproduces round 2's
  published 92.0 for Views + Offers.
