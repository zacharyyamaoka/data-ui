# Play the day back

The same synthetic pickups on a time bar: press play and each stop appears when its truck reaches it, with the last three hours kept as a trail. Scrub to any minute; the status of the bar says how many pickups have happened by then. When the page has data-ui's dashboard clock the map follows it.

- **App:** Map
- **Replaces:** a fleet tracker's replay, or kepler.gl's time filter.
- **Shows:** `time: {property, trail}`: a play/scrub bar that filters the layer on the GPU (MapLibre setFilter), following a dashboard's clock when its `.base` declares `clock:`, and running by its own `speed:` otherwise.
- **Data:** `../map-collection-routes/day.json`: SYNTHETIC times and kilograms over real OpenStreetMap food courts (© OpenStreetMap contributors, ODbL).
