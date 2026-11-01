# Dashboard card catalog

Every card type data-ui dashboards offer, on real rows: KPI tiles, gauge, bullet, bar list, status tracker, time
series, bar / histogram / scatter / heatmap, trajectory 2D and 3D, video, video overlay, image, markdown and the
playback card that drives the one clock (docs/peps/0005-dashboard-cards.md).

- **App:** data-ui
- **Replaces:** the round-1 dashboards' one-off widgets (a KPI strip, a table and a Vega chart per panel, no time series, video or 3D) and the bespoke synced players in traj_compare's and pidtuna.com's reports, for the cards a dashboard can place
- **Data:** slices of the real fixtures in pid-tuning (UR5e replays from pidtuna, sim; MuJoCo renders) and
  vibetracks-dashboard (Zach's Vibe Tracks producers), cut by `source/build.py`; each file names its source.
- **Not real:** nothing is invented. The UR5e numbers and videos are simulation (pidtuna's replay), labelled as such.
