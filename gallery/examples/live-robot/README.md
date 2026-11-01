# Robot arm, live (simulated)

A live dashboard on a **simulated** three-joint arm: positions and motor currents at 500 samples a second per joint,
temperatures, five health checks and a log, all streaming into data-ui's live tier. It follows the newest data like
Rerun; drag the time bar back to rewind while rows keep arriving, and ● LIVE comes back.

- **App:** RobotDx
- **Replaces:** RobotDx's State tab (live values and their 60 s sparklines), its Activity log's live tail and its
  health bars (io-diagnostics `web/d6.js`, `web/activity/log.js`, `web/health.js`), here on made-up data;
  the rebuild of RobotDx itself on data-ui is its own lane (io-diagnostics `docs/peps/0001-robotdx-on-data-ui.md`).
- **Shows:** four live datasets (`live:` in the `.base`), two uPlot plots drawing the minimum and maximum of every pixel
  column, KPI cards at the clock's t, a level history per check, a log that holds while you scroll ("N new · Resume"),
  the playback bar with ● LIVE and the lag, the connection line, `#t=live` in the URL.
- **Data:** none on disk. `simulate.js` (this folder) makes every row in the page: smooth joint motions with noise, a
  current from the motion, a first-order motor temperature, and a collision on the elbow about every 30 s (a current
  spike, an error in the log, the check turning red). The JSON files hold only the fields. **Simulated, not a robot.**
