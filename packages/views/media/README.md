# media

The media cards of docs/peps/0005-dashboard-cards.md: `type: video`, `type: video-compare` and `type: image`. One
lazy bundle (`dist/views/media.js`); the stock parts are the browser's `<video>` and `<img>` and CSS (clip-path,
opacity, mix-blend-mode). Not img-comparison-slider (images only), not `HTMLMediaElement.mediaGroup` (removed from
browsers).

```yaml
- type: video
  from: media
  filters: 'situation == "tuned"'
  video: { src: src, label: situation, primary: true }
- type: video-compare
  from: media
  overlay: { by: situation, a: tuned, b: factory, mode: wipe, split: 0.5 }
- type: image
  from: media
  image: poster          # Bases' own key (the image property)
  caption: [note]
```

A card whose view leaves it no row says the view's own **`empty:`** text, else "No rows match this view." (kit gap 9,
2026-10-29: the camera template's depth and hyperspectral cards say none is captured yet, and only while none is).

The rows are PEP 0005 §3's media rows: `src` (resolved against the data file's URL), `poster`, `t0` (the clock time
at frame 0), `fps`, `duration`, `width`, `height`, `basis` (`real-camera`, `sim-render`, `screen-capture`,
`illustrative`) and `note`.

- **video:** the first row its filters leave, as `<video muted playsinline preload="none" data-t0>`. No native
  controls: the dashboard's clock is the control, a click (or Space / Enter) on the picture plays or pauses it, and
  a slim overlay shows a play glyph while paused and the clock's time. Every video follows the clock with core's
  `followVideo` (paused: exact seek to t − t0; playing: jump past 0.1 s, nudge the rate within it). `primary: true`
  makes this video drive t while the clock plays (`requestVideoFrameCallback` → `clock.drive(mediaTime + t0)`); a
  seek, a loop or a step puts it on the new instant, and a pause lands it exactly on t. Once its metadata is in it
  reports `clock.extent(t0, t0 + duration)`. The caption is the `label` column with its palette colour, the basis
  badge and the row's note on hover; an illustrative clip is also tagged on the picture ("Illustrative · not a
  recording").
- **video-compare:** rows A and B by `by` = `a` / `b` (default: the first two rows), two followers (never primary).
  `wipe` clips A to `inset(0 (1 − split)·100% 0 0)` over B with a draggable handle (pointer, or ← / → by 5 %,
  Shift by 10 %, Home / End); `onion` sets A's opacity to `split` (a slider on the letterbox); `difference` blends A
  with `mix-blend-mode: difference`; `side` puts them in two equal columns. The segmented switch and the handle write
  `overlay.mode` / `overlay.split` back with `host.setView` (the split once the drag rests 250 ms), so the view entry
  keeps them. The caption names both clips and their basis: one badge when they agree, "sim render vs real camera"
  (dashed, warn colour) when they differ. A value no row has is "—" with the reason, never a stand-in clip.
- **image:** `<img loading="lazy" decoding="async">`, `object-fit: contain`, the caption column under it (two lines,
  the whole text on hover); several rows make a horizontal strip that scrolls inside the card.
- **Lazy:** a video's `src` is set, and `preload` turns `auto`, only when its card comes within 240 px of the
  viewport (IntersectionObserver). The clip's URL is on `data-src`.
- **A server without HTTP Range** (python's `http.server`, some static hosts) serves a clip Chrome cannot seek
  (`seekable` stays [0, 0]); the card then fetches that one file into a `blob:` URL so it can still follow the clock.
- **Look:** the picture sits on a dark letterbox from the tokens (the page's ink in light, its background in dark)
  with the card's `style.radius`; no box of its own. Light DOM, classes `dv-media-*`.

Checks: `gallery/examples/dashboard-cards/checks_media.py` (seek and play sync within one frame, the overlay's modes
and handle measured, lazy loading at 390 px, the image card, light and dark); `tests/unit/media.test.mjs`.
