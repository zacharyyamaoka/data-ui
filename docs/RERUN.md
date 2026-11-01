# Open in Rerun

Every analysis dashboard has a backdoor: the same rows it draws, written into one Rerun `.rrd` with a layout that
mirrors the dashboard, opened in Rerun with no account (docs/peps/0005-dashboard-cards.md §6; the decision is the
vault note *Tracking-Run Data — data-ui vs Rerun (2026-10-26)*, § Layer 3).

- **One pin: rerun-sdk 0.40.0.** A `.rrd` must be opened by the viewer version of the SDK that wrote it, so the
  exporter (`SDK_VERSION` in `tools/rerun_export.py`), the hosted viewer URL and the native command all say 0.40.0.
  A `.base` that declares `rerun: {sdk: …}` with another version is refused by the exporter.
- **Build-time only.** rerun-sdk is never a dependency of data-ui: the exporter is a `uv run --script` with a PEP 723
  header, and the page only links to the file it wrote.

## The button's three forms

A dashboard with `rerun: {rrd: rerun/<case>.rrd, sdk: 0.40.0}` shows "Open in Rerun" with three actions, all built
from the `.rrd`'s absolute URL:

1. **Open in the hosted viewer**: a new tab on
   `https://app.rerun.io/version/0.40.0/index.html?url=<absolute .rrd URL>`. The viewer page (on `app.rerun.io`)
   fetches the `.rrd` from our origin with a plain `GET` (no preflight), so that response carries
   `Access-Control-Allow-Origin: https://app.rerun.io`. The deployed site gets it from `dist/site/_headers`, which
   the build writes (`SITE_HEADERS` in `site/build-site.mjs`); data-ui.dev is an assets-only Worker, so Cloudflare
   applies the file ([static assets headers](https://developers.cloudflare.com/workers/static-assets/headers/)):

   ```text
   /*.rrd
     Access-Control-Allow-Origin: https://app.rerun.io
   ```

   The file must also be at most 25 MiB, Cloudflare's per-file cap; the exporter warns past it.
2. **Copy the native command**: `uvx --from rerun-sdk==0.40.0 rerun <.rrd URL or path>`. The native viewer opens a
   local path or an `http(s)://` URL to an `.rrd` (`rerun --help`), and needs no CORS header. A page cannot start a
   process, so the button copies the one line and the reader runs it.
3. **Download** the `.rrd`, for any installed 0.40.0 viewer.

### Locally

`npm run serve` (`tools/serve.mjs`) sends the same header on every `.rrd`, and answers a preflight (`OPTIONS`) for
one with 204, the origin, `GET, HEAD`, the headers asked for and, when asked, `Access-Control-Allow-Private-Network:
true` (older Chrome's Private Network Access preflight). `python3 -m http.server` sends no CORS header, so form 1
fails from it.

From `http://127.0.0.1:<port>/…` Chrome also asks the reader once to let `app.rerun.io` reach the local network
(Local Network Access, Chrome 142+); until it is allowed the fetch fails with "Permission was denied for this
request to access the `loopback` address space". Allow it, or use forms 2 and 3, which always work locally.

Verified 2026-10-27 in headless Chromium 153 (Playwright, `local-network-access` granted to `https://app.rerun.io`):
the 0.40.0 viewer fetched `http://127.0.0.1:<port>/gallery/dashboard-cards/rerun/dashboard-cards.rrd` with one
`GET`, status 200, `access-control-allow-origin: https://app.rerun.io`, and drew the dashboard's layout; the same
page against the old server (no header) failed with "No 'Access-Control-Allow-Origin' header is present". The
deployed `_headers` rule is checked as a file (`tests/unit/serve-headers.test.mjs`), not against the live site.

## Regenerate

```bash
uv run --script ~/data-ui/tools/rerun_export.py ~/data-ui/gallery/examples/dashboard-cards/views.base
```

It writes `rerun.rrd` from the file when the `.base` names one, else `<case dir>/rerun/<case>.rrd`
(`--out FILE` overrides), and prints the size, every entity and every card it could not carry. The `.rrd` is
generated, never hand-edited, and git-ignored (`/gallery/examples/*/rerun/*.rrd`): regenerate it before
`node build.mjs` so the site build copies `rerun/` beside the case.

## What is in the file

One recording, application id `data-ui-<case>` (0.40 rewrites an id with `/` or `.` to a hashed one), named
`<case> · views.base` (the distinguishing part first: Rerun truncates recording names). One timeline, the clock's
time column (`t`), a duration in seconds; a date-valued x column goes on a timestamp timeline `date`.

| Card | Entities | Rerun view |
|---|---|---|
| `timeseries` | `/timeseries/<view>/<series>`: Scalars on `t`, one per `series` value (and per `y` column when several), coloured by `style.palette`; `rules` and the edges of y `bands` as constant series under `…/rules/`; `scale: log` adds `/timeseries/<view>-log10/<series>` = log10\|y\|, because Rerun has no log axis ([#6773](https://github.com/rerun-io/rerun/issues/6773)) | TimeSeriesView per card |
| `trajectory` | `/world/<view>/<series>/path` (static LineStrips3D) and `…/marker` (Points3D on `t`); the 2D path lies in z = 0, seen from above | Spatial3DView |
| `scene3d` | the same, plus `…/skeleton` (LineStrips3D on `t`, base → tool); `RIGHT_HAND_Z_UP` | Spatial3DView |
| `video`, `video-compare` | `/video/<label>`: AssetVideo + one VideoFrameReference per frame on `t` = the row's `t0` + the frame's timestamp; a clip two cards show is logged once | Spatial2DView per clip (a compare card: its two clips side by side) |
| `kpi`, `table`, text panels | `/notes`: one markdown TextDocument with the text panels, each KPI (value, unit, target, basis, source) and each table's rows | TextDocumentView |

The blueprint is saved into the `.rrd` (`RecordingStream.save(path, default_blueprint=…)`): a Vertical of
Horizontals, 3D views, then time series, then videos, then the notes, in layout order; the time panel expanded on
`t` at the clock's `fps` and `rate`.

Rows are the card's rows: the dataset's `filters` (or the file's top-level `filters` for the default dataset), then
the view's `filters`, then `sort` and `limit`. The exporter reads filters written with `==`, `!=`, `<`, `>`, `<=`,
`>=`, `&&`, `||`, `!` and parentheses over properties and literals, and `{and | or | not: [...]}`; a card whose
filter uses anything else (method calls, `file.*`, formulas, dates) is left out and named in `/notes`.

**Not carried** (listed in `/notes` under "Not in this recording", never dropped silently): the stat cards (`gauge`,
`bullet`, `barlist`, `status`), Vega `chart`s, `image`, the wipe / onion / difference overlay (Rerun shows the two
clips side by side), dashed series, annotations, x bands, a trajectory's `tolerance` tube, `color` and `trail`.

## The test

`python3 -m unittest discover -s tools -p 'test_rerun_export.py'` exports the dashboard-cards case into a temp dir
through `uv run --script` and reads it back with the SDK (`rerun.chunk.RrdReader`; when the plain python3 cannot
import rerun, through `uv run --script tools/test_rerun_export.py --summarize <rrd>`). It checks every time series
entity against the case's JSON (same samples, same t, same values, with the filters written out by hand in the
test), one frame reference per video frame, the paths, markers, skeletons and notes, and the blueprint's view count;
a copy of the case with one sample changed must fail the same comparison. A series must be on exactly one timeline,
`t` as a duration (seconds) or `date` as a timestamp (nanoseconds, compared exactly), with as many times as values as
the case has samples, each (time, value) pair in time order. The comparison is mutation-tested in the same file:
emptied times, a renamed timeline (or the right name with the wrong kind), a dropped sample, and a shifted or swapped
time must each be reported. It skips, saying why, when neither rerun nor uv is available.
