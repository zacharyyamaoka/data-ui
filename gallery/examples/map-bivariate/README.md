# Diversion now × how much it improved

Two numbers per province on one map: how much waste it diverted from disposal in 2022 (across) and how many percentage points that rose since 2002 (up). A 3 × 3 grid of colours, each axis cut at its own tertiles: dark means high on both. PEI and the territories are suppressed and hatched.

- **App:** Map
- **Replaces:** two side-by-side choropleths that make you compare by eye.
- **Shows:** `{type: regions, bivariate: {x, y, count: 3}}`: Joshua Stevens' bivariate scheme mixed from two series tokens, so it reads in light and dark; the legend is the grid with both axes' breaks.
- **Data:** `provinces.json`: diversion rates from ECCC's Canadian Environmental Sustainability Indicators, figure 5 (2002 and 2022); disposal tonnes from Statistics Canada table 38-10-0032-01 (2024) and population from 17-10-0009-01. CESI: Open Government Licence – Canada ("Contains information licensed under the Open Government Licence – Canada"). Statistics Canada: Statistics Canada Open Licence ("Adapted from Statistics Canada, *Disposal of waste, by source*, Table 38-10-0032-01, 2024, and *Population estimates, quarterly*, Table 17-10-0009-01, 2024-07-01. This does not constitute an endorsement by Statistics Canada of this product."). PEI's and the territories' diversion is suppressed by Statistics Canada and shown as no data, never 0. Shapes: Natural Earth (public domain), 1:50m admin-1.
