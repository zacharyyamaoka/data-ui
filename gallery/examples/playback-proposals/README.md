# Playback proposals

Five proposals for the dashboard clock's control (docs/peps/0005-dashboard-cards.md §4b), each a `playback.variant`,
beside today's bar, all driving one clock: Rerun's toolbar (`rerun`) and its time panel with the STREAMS tree
(`rerun-streams`), YouTube's bar with real-frame hover thumbnails and chapters (`youtube`), a video editor's
multi-track timeline with filmstrips (`tracks`), Foxglove's playback bar (`foxglove`) and an overview with a brushed
zoom window (`range`). The switcher on the card under the video (bottom-right) swaps them in place and remembers the pick.

- **App:** data-ui
- **Replaces:** the single playback bar of the card catalog (`gallery/examples/dashboard-cards`, `variant: bar`,
  Zach's screenshot of the old "Synced playback: one clock, three followers" bar); Zach, 2026-10-26: "Playback bar:
  5 proposals, as a placeable card with a switcher."
- **Data:** `samples.json`, `tool.json`, `media.json` and `media/` copied by `source/build.py` from the card catalog
  (itself pidtuna's UR5e replay via pid-tuning): the elbow joint's step response, the tool path, the three MuJoCo
  renders. SIMULATION: the videos are sim renders and say so.
- **Not real:** nothing is invented; the chapters on the YouTube bar are computed from the target's moves.
