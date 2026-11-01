# playback

The dashboard clock's control (docs/peps/0005-dashboard-cards.md §4, §4b), placed like any card. It only calls the
clock (`packages/core/src/clock.js`, the one writer of t) and redraws on its events; per tick it moves things by a
CSS variable (`--dv-pb-f`, t over the span) or a transform, never by a re-render. Every time-aware card follows the
clock, not this card.

```yaml
- type: playback
  name: Playback
  playback:
    speeds: [0.25, 0.5, 1, 2, 4]
    range: true          # bar: the loop-selection lane
    readout: true        # bar: "3.20 / 7.93 s"
    variant: bar         # bar | rerun | rerun-streams | youtube | tracks | foxglove | range
    switcher: false      # true: a drop-down at the card's bottom-right to try every variant live (remembered per reader)
```

The gallery case `gallery/examples/playback-proposals` puts all seven on one clock, beside two videos, two time series
and a tool path, with the switcher on its first card.

## The variants and their prior art

| variant | copied from | what it adds |
|---|---|---|
| `bar` (default) | Rerun's time panel, Foxglove's speed menu | start, ±1 frame, play, loop, speed, readout, a track with ticks, a loop-selection lane, the zoom window as a dashed band |
| `rerun` (P1) | [Rerun's timeline toolbar](https://rerun.io/docs/reference/viewer/timeline) (0.2x), Zach's screenshots 98–102 | play (blue while playing), step forward, the step menu (Forward/Backward 0.1 s and 1 s, Next/Previous event, End/Start of timeline, with Rerun's keys), the loop menu (off / loop all / loop selection), the timeline picker, the speed field `1.00x` and the time field `+3.20s` (typing seeks), and the collapsed panel's one-line scrubber |
| `rerun-streams` (P1) | the same, expanded | the STREAMS tree (one node per time-aware dataset, a child per numeric column or clip; fold, search, select, resizable), a `+0s +1s …` ruler, each stream's event bar from its first to its last sample with its event ticks, the loop selection band (Shift+drag the ruler), the playhead and its triangle across every row |
| `youtube` (P2) | [YouTube's player bar](https://support.google.com/youtube/answer/9884579) (chapters) and its [keyboard shortcuts](https://support.google.com/youtube/answer/7631406) | a bar that thickens on hover, a hover thumbnail of a real frame (the dashboard's primary video at that t, drawn from a hidden `<video>`, cached by frame), chapters, the buffered range, the gear (speed, loop), keys K, J/L, ←/→ 0.5 s, `,`/`.` one frame |
| `tracks` (P3) | a video editor's timeline: [Premiere Pro](https://helpx.adobe.com/premiere-pro/user-guide.html), [DaVinci Resolve's Edit page](https://www.blackmagicdesign.com/products/davinciresolve/edit), [CapCut](https://www.capcut.com/resource/how-to-use-capcut) | a transport with a `00:00:03:06` timecode, a work area over the ruler (the loop range, with handles), one track per clip with a filmstrip of its real frames, one per time series card with its sparkline, a playhead across them, resizable track headers |
| `foxglove` (P4) | [Foxglove's playback controls](https://docs.foxglove.dev/docs/visualization/playback) | a scrubber showing the loaded ranges and a hover time, the time display (seconds `3.200` or elapsed `00:03.200`), seek back / play / seek forward, the speed menu, loop |
| `range` (P5) | [Grafana's time-range zoom](https://grafana.com/docs/grafana/latest/dashboards/use-dashboards/#set-dashboard-time-range), [Highcharts Stock's navigator](https://www.highcharts.com/docs/stock/navigator), [uPlot's range selector demo](https://leeoniya.github.io/uPlot/demos/zoom-ranger.html) | a minimap of the whole span with the main time series, a brushable window that sets `clock.window` (every time series zooms to it), the playhead, a readout of t and the window |

What each reads from the dashboard (read-only, `host.element.closest('data-dashboard')`): **events** are the distinct
sample times of every dataset with a number in the clock's time column; **streams** add each dataset's numeric
columns and a clip dataset's clips; **chapters** (YouTube) start where the first time series card's first palette
series (the target) starts moving after holding still for 0.2 s, so a step target's moves become "Move 1", "Move 2" …;
the **primary video** is the clock's `primary` panel, else a `video.primary` view, else the first video view.

Keys: the dashboard owns Space, ←/→ (a frame), Shift+←/→, J/K/L, `[`/`]`, Home/End. A variant whose prior art has other
keys (`rerun`, `youtube`) adds a capture-phase keydown listener on the dashboard while it is in use, takes only its own
keys (stopImmediatePropagation) and removes it in `destroy()`. With several on one clock the one used last answers.

## Adding a variant: the registry

```js
import { registerPlaybackVariant } from './registry.js';

registerPlaybackVariant('live', {
  label: 'Live',
  create(host, el, clock, ctx) {      // el: fill it; clock: call it and listen to it; ctx: {name, dashboard}
    return { update(input) { /* input.view.playback */ }, destroy() { /* remove listeners */ } };
  },
});
```

Every built-in goes through it (`index.js`), so a new one is a module beside them plus one import in `index.js`. The
switcher lists every registered variant. A `.base` can name it once `schemas/view.schema.json`'s `playback.variant`
enum lists it (a contract change, PEP 0005 §4b). `base.js`' `Variant` class is the shared part the built-ins extend:
the clock's events, the dashboard's data (events, streams, clips, time series), owned keys, pointer scrubbing, menus.

## A live edge (a LIVE tier with rewind): what it needs from the clock

Not built here, and `clock.js` is unchanged. What a live variant can do today: listen to `state` (the span grows as
`extent()` unions new data, or a re-`setSpan()` after a refresh) and, while it is "following", `seek(clock.end)`;
any user seek below the end leaves following ("rewind"); a "Go live" button seeks to the end and follows again.

What it cannot do without the clock (a proposed amendment to PEP 0005 §4, for whoever lands the live tier):

- **One shared mode.** `clock.live: boolean` and `setLive(on)`, emitting `state`; otherwise each live control keeps
  its own idea of "live" and two of them disagree. `seek()` from any source other than the live follower clears it.
- **The live edge, separate from the span's end.** `clock.edge` (the newest t that exists) while `end` may be a
  declared span; a follower seeks to `edge`, the bar draws "behind live by N s".
- **Playing while live is wall-clock time**, rate pinned to 1; `play()` past the edge must not loop back to the start
  (today `_tick` loops or pauses at `bounds[1]`).
- **The URL** should write `live` instead of `t` while following (today the dashboard writes `#t=` on pause/seek).

## Stock parts

None (buttons, inputs, divs, SVG paths, pointer events, canvas `drawImage` from a hidden `<video>`); the resizable
side panels are core's `makeResizable`.
