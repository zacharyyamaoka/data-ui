# robotparts releases and lanes

robotparts' six releases from 2026-10-22 to 2026-10-25 and the 24 branches merged into them, from git: a release
is a point at its tag, a lane, integration or contract branch is a bar from the first commit its merge brought in
to the merge. Lanes by kind, coloured by the release they shipped in; or by release, nested by kind.

- **App:** robotparts
- **Replaces:** reading `git log --graph` and the release tags by hand; robotparts has no timeline page.
- **Shows:** the timeline view (vis-timeline) with `start`/`end`, `groupBy` lanes in `groupOrder`, `subGroupBy`
  nested lanes, `color` from a property, `zoom` limits as ISO 8601 durations, points beside bars, and the same rows
  as a table.
- **Data:** `timeline.json`, written by `source/build.py` from `git -C ~/robotparts log --merges` and
  `tag -l 'release/*'`: hashes, dates and subjects only. Dependency arrows are not drawn: the grammar has no key
  for them yet.
