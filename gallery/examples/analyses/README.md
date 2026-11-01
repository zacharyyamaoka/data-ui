# Analyses · reports that mix text with live views

Three analyses, each one Markdown file: prose, ```base fences and ![[x.base]] embeds drawn as live views and
dashboards, a decision callout, and a table of contents from the headings. The list is a data-ui view over their
frontmatter; open one to read it. data-ui's third tier: views, then dashboards, then analyses.

- **App:** data-ui
- **Replaces:** robotparts.dev's own analysis renderer (its PEP 0002), now the kit's `<data-analysis>` and `<data-analyses>`
  (docs/peps/0007-analyses.md); W&B reports, as a file format an agent writes.
- **Shows:** a list as Gallery, Table and Board by status; a report with a resizable contents column; ```base fences
  filtered by `this.parts` (the note's frontmatter, as in Obsidian); a whole dashboard embedded with one line
  (`![[../sim-to-real/views.base]]`); one view of another case's file (`![[../actuator-charts/views.base#Ashby · torque vs mass]]`);
  [!decision], [!illustrative], [!example] and [!warning] callouts.
- **Data:** the sibling cases' data, read where it lies: robotparts' actuators (**real** catalog values), the rack's
  sim-to-real twins (**real** hardware runs), pidtuna's robots (**simulated**, illustrative parameters, and said so).
  Every number in the prose is copied from those files; the arm's load in the shoulder analysis is illustrative and
  marked. `analyses.json` (the list's rows) is written by `source/build.py` with data_ui_analysis.py.
