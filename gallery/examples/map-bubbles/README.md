# Waste disposed, by province

Total waste sent to disposal in 2024 by province and territory as proportional circles: a circle's area is its tonnes, so Ontario's is four times Alberta's when it disposes four times as much. The legend gives the largest circle's value; the territories' combined figure has no single point and says so.

- **App:** Map
- **Replaces:** a bar chart of provinces that loses the geography, or a choropleth of totals that rewards big provinces for being big.
- **Shows:** `{type: points, size: {property, max}}`: circle area ∝ value (sqrt scale), largest drawn under smaller ones, label from a property.
- **Data:** `../map-bivariate/provinces.json`: diversion rates from ECCC's Canadian Environmental Sustainability Indicators, figure 5 (2002 and 2022); disposal tonnes from Statistics Canada table 38-10-0032-01 (2024) and population from 17-10-0009-01. CESI: Open Government Licence – Canada ("Contains information licensed under the Open Government Licence – Canada"). Statistics Canada: Statistics Canada Open Licence ("Adapted from Statistics Canada, *Disposal of waste, by source*, Table 38-10-0032-01, 2024, and *Population estimates, quarterly*, Table 17-10-0009-01, 2024-07-01. This does not constitute an endorsement by Statistics Canada of this product."). PEI's and the territories' diversion is suppressed by Statistics Canada and shown as no data, never 0. Shapes: Natural Earth (public domain), 1:50m admin-1.
