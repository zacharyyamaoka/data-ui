# Where Metro Vancouver's garbage goes

Garbage moving from transfer stations to the Vancouver Landfill, the Burnaby Waste-to-Energy Facility and out-of-region landfills, as arcs whose width grows with tonnes. Two flows are published figures; the rest are a synthetic split that adds up to each station's published total, and every row says which.

- **App:** Map
- **Replaces:** a Sankey diagram that loses where the facilities are, or a deck.gl ArcLayer.
- **Shows:** `{type: flows, from, to, width}`: Turf bezier arcs bowed so opposite flows separate, width ∝ √tonnes, › arrows along each arc, hollow origin and filled destination dots, colour from `basis`.
- **Data:** `flows.json`: Metro Vancouver's 2024 solid waste system fact sheet and ISWRMP biennial report (metrovancouver.org) and the City of Vancouver's 2024 Vancouver Landfill annual report (vancouver.ca); figures restated with attribution (Source: Metro Vancouver; City of Vancouver). 2 rows published, 15 a SYNTHETIC proportional split (basis: synthetic); the contingency landfills are unnamed by Metro Vancouver, so their rows have no destination point and are counted, not drawn. Facility points © OpenStreetMap contributors, ODbL. One station is left out of the public data on purpose (map-waste-flows/source/SOURCES.md).
