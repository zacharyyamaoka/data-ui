# SystemSketch blocks

One SystemSketch board, the communication-projection prototype (camera, perception, planner, mission behaviour
tree, motion controller, telemetry UI and two value blocks), as rows plus edges: a block is a row with its input
and output ports, a connection is an edge named by the output port it leaves. The mission BT and motion controller
keep all six of their connections, each with its own line and label.

- **App:** SystemSketch
- **Replaces:** the hand-placed tldraw board (`systemsketch/sketches/review/communication-projection-prototype.systemsketch`)
  for reading the system's structure; SystemSketch stays the editor.
- **Shows:** the graph view laid out left to right by dagre, parallel edges between one pair spread apart, a second
  preset grouped by block type (subflows, top to bottom), and the blocks as a table.
- **Data:** `blocks.json`, written by `source/build.py` from the board's block shapes and connection bindings.
