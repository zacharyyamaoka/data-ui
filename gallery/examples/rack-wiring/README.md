# 1-DOF rack wiring

The parts of BAM's one-DoF test rack as a graph: the supply, regen clamp and XT30 junction feed the two moteus
boards, the fdcanusb and PH-3 junction carry CAN to them, each board drives its motor, and the D405 sits beside it.
Power, CAN and phase wires each keep their own colour; click a part for its ports, cables, Splice's voltage and
current at load, and its findings.

- **App:** robotparts
- **Replaces:** Splice's hand-drawn rack canvas (robotparts `reports/media/rack/splice-rack-2026-10-22.png`) for
  browsing the wiring. Not its analysis: the voltages, currents and findings here are Splice's own results, copied.
- **Shows:** the graph view (React Flow + dagre) with `edges: {property: feeds, label: wire}`, `groupBy` as
  subflows (Power, CAN, Boards, Motors, Sensing), a top-to-bottom power path from a filter, edge colours from the
  `wire` column's `colors`, rich cells (derived V and A with their source) on the node cards, and the same rows as
  a table. In a part's peek, "Wires to" links to the parts it feeds: follow them and the peek keeps the trail
  (supply › regen clamp › XT30 junction), as Notion's side peek does.
- **Data:** `rack.json`, written by `source/build.py` from robotparts' `rack.splice.json` and `rack-analysis.json`
  (target layout, release 2026.10.22.2, Splice engine @ 93b27023). The motors come from the analysis's
  `rack.motors`; the D405 has no wire because none is recorded.
