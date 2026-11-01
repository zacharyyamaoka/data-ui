# PEP 0013: navigation — a dataset read per pick, one-way links, presets and picker tables

- **Status:** accepted 2026-10-29 on `lane/p3-nav` (PEP 0010 P3, the navigation barrier; CONTRACT §33). Not merged.
- **Asked by:** PEP 0010 §8 (Zach's four levels: deployments → one deployment → one run → matching performance) and
  sim2real's gaps #7 ("a selection cannot be preset in the `.base`") and #8 ("links are always two-way",
  reports/backlog-sim2real-gaps-2026-10-28.md).
- **Why now:** the robotics templates worked around all three: an unlinked copy of runs.json so the runs table lists
  every run (and then cannot pick one: the P1c deviation), the newest run hard-coded into a `filters:` the build has to
  rewrite, every run's samples in one file, and links whose far side emptied the run picker (the kit gaps' driver
  fixture listed 7 of 27 runs). sim2real's app rewrites `{deployment}` and `{run}` into each `.base` in a fetch hook and
  pushes `#s.runs=` into the URL itself.

## The decision

1. **A dataset whose `data:` names a placeholder is read per pick.** `samples: {data: 'runs/{run}.json'}` is the one
   file the dashboard's picks leave: the value of `run` is what the other datasets' picks carry to `samples.run` along the
   links (the semi-join keys, met), and the file is read only when exactly one value is left; none, two or more show
   "Pick one run" in its panels. The file is fetched once and kept (12 at most), so flipping back costs nothing. Its rows
   are one run's, so they never narrow another dataset. The placeholder is filled as one URL path segment (CONTRACT
   §24's `origin.url` rule).
2. **A link may be one-way.** `{from, to, direction: one-way}`: the from side's picks narrow the to side and never the
   other way; two-way stays the default, so every dashboard before this filters as it did.
3. **A view's `selected:` presets its `select:`.** `first` (the first row it draws: newest first under `sort: started
   DESC`), a value or a list; written into the URL as the selection it made; a cleared one is `s.<panel>=`.
4. **A `select:` on a property its dataset's rail picks one value of is a picker:** its click moves the rail's pick, and
   it lists every value the rest of the rail leaves. One state, two editors.
5. **A pick is a history entry.** Back and Forward restore the picks and t, as a fresh load of that URL would.

## Criteria (weights sum to 100)

| # | Criterion | Weight |
|---|---|---|
| C1 | Zach's levels on one page, the run loaded on a pick, the newest by default (PEP 0010 §8) | 25 |
| C2 | One state per pick: the rail, the table, the URL and the history agree | 20 |
| C3 | No existing dashboard changes (default two-way, no new required key) | 15 |
| C4 | data-ui stays a file reader: no server, no query language, no host code | 15 |
| C5 | The rules already proven (semi-joins, the rail's counts, the clock's span) carry over unchanged | 15 |
| C6 | Stock parts and prior art first | 10 |

## Options considered

Scores run from 1 to 5; the total is the weighted mean.

**How one run's data reaches the page.**

| Option | C1 | C2 | C3 | C4 | C5 | C6 | Score |
|---|---|---|---|---|---|---|---|
| **A: a placeholder in `data:`, filled from the links' keys** | 5 | 5 | 5 | 5 | 5 | 4 | **4.9** |
| B: the host rewrites the `.base` text (sim2real's app today) | 4 | 2 | 5 | 2 | 3 | 2 | 3.1 |
| C: one file of every run (the templates today) | 2 | 4 | 5 | 5 | 5 | 3 | 3.9 |
| D: a named variable (`$run`, Grafana's) the template reads | 5 | 3 | 5 | 5 | 2 | 5 | 4.2 |
| E: a query endpoint (`?run=`) or Arrow partitions | 4 | 4 | 5 | 1 | 3 | 4 | 3.6 |

- **A wins** because the template is the semi-join it already was: the samples' file is the partition of a dataset
  that is conceptually whole, so every rule that reads a dataset (rails, links, layers, the clock, roll-ups) applies
  unchanged, and a run can be picked on a rail, in a table or through a chain (deployment → run).
- **D** adds a second kind of state beside the rail and the selections, with its own URL and its own rules for what a
  click sets: two states for one pick is the bug P3 removes.
- **B** works today but puts the routing in each host and re-reads the `.base` per run; **C** does not scale to a
  deployment (1,001 rack runs, 720,765 samples); **E** makes data-ui fetch from something other than files.
- PEP 0010 §8 drafted `key: run` beside the template. The placeholder already names the column, so there is no `key:`.

**Which way a link filters.**

| Option | For | Against |
|---|---|---|
| **`direction: one-way` on the link** (Power BI's single cross-filter direction) | the relation is the link's; one word, the default unchanged | none found |
| Per-panel scoping ("this panel ignores dataset X", Superset's filter scopes) | fine-grained | every panel of the far side must say it; a rail's counts have no panel |
| Unlinked copies (the templates' workaround) | no kit change | the copy cannot pick, and a second state for one pick |

**Where a preset lives.** On the view, `selected:` beside the `select:` it presets (Superset's "select first filter
value by default"), not a top-level `selections:` keyed by panel (keys change with titles) and not hash-only (what
sim2real does by hand).

**One pick, two editors.** The templates' frozen checks pick a run on the rail's radio, and PEP 0010 §6 wants the runs
table on top to pick too. A `select:` that added a cross-filter under a rail that already picks one value could only
repeat the pick or empty every panel, so on a one-choice facet the table edits the rail (Grafana's data links that set
a variable). Under a several-value facet a selection still narrows within it, as before.

## Consequences

- **History** changes for every dashboard: a pick (rail, selection, picker) pushes one entry. A search facet's typing,
  t, the range, tabs and the legend replace the entry they are on. WHY: Back must restore a pick (PEP 0010 §11 P3), and
  McMaster's rail, Zach's reference, is a URL per pick.
- The chips name a value by its row's title only where the value is a key (it named the first row sharing a value).
- A selection still narrows its own dataset's rail counts (PEP 0004 §5): with a run selected, the runs rail counts that
  run. A parent-style rule for selections (the rail's facets left out of a selection made below them) is not in P3.
- Not yet: a placeholder filled from the rail of the per-pick dataset itself, and a live (`live:`) or timed (`refresh:`)
  per-pick dataset; both checkers refuse them.
