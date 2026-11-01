# Actuator model page

One actuator model's own page, the one every model name in the models case links to: what the model is (its
robotparts contract 2.3 kind and equation, what the twin actually runs), its error on each bench, its fitted terms,
the commit the rack's twin code was fitted with and that code's README at the commit, rendered as markdown.
Configuration only: a record view and a table over the models case's data file, the model picked by the rail.

- **App:** robotparts
- **Replaces:** nothing yet: the models proposal had no per-model page (Zach, 2026-10-26: "click it and get
  information on that actual model, perhaps … it renders the README of the model").
- **Shows:** `type: record` in sections (Model, Error, Fitted terms, Code) with `display: markdown` for the
  description and the README; the rail as a single-choice `select` on the model, opened by a readable link
  `?variant=M4.ripple.c1`; a table of the actuators it ran on.
- **Data:** `../robotparts-models/models.json`. The README is `src/dev/bam_rack_twin/README.md` read with `git show
  <commit>:…` from `~/bam_ws` at each actuator's fit commit (budget_can<N>.json `code.git_head`); none of
  those commits is on GitHub's origin, so the page links the local path and no hosted URL.
- **Skin:** robotparts' prototype "Catalog" light and "Signal" dark, mapped onto `--data-*`.
