# Decisions (Vibe Tracks)

Vibe Tracks' fifteen decision records (its PEPs 0001 to 0013, with 0011a and 0011b), newest first, and the tree of
what each one depends on: an edge only where a record names another in its header (builds on, amends, supersedes).
The same rows and edges drawn by both graph engines: React Flow to pan and zoom, Mermaid as a static map. Click a
decision for its record.

- **App:** Vibe Tracks
- **Replaces:** nothing (new): Vibe Tracks has no Decisions page yet; its records are read as files in `docs/peps/`.
- **Shows:** a table sorted by `date` descending; `type: graph` with `edges: {property: depends_on}` and `layout:
  {engine: flow, direction: BT}` (React Flow + dagre) beside the same graph with `layout: {engine: mermaid}` (a
  Mermaid flowchart, loaded only when that view opens); relation properties (`relation: true`), so a record's peek
  links to the records it depends on and keeps the trail.
- **Data:** `decisions.json`, copied verbatim from Vibe Tracks' hand-read acceptance oracle
  (`tests/fixtures/decisions/oracle.json` on branch `claude/vibetracks-decisions`, commit 59b4073): 15 records and
  23 declared dependency edges, none inferred. `decisions.schema.json` names its fields (title, date, the four
  relations) and points at it.
