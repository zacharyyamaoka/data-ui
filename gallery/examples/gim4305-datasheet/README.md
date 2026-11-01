# GIM4305-10 datasheet

One part, one row per field: what SteadyWin states, what BAM's one-DoF rack measured, what the board reports and
what is derived, grouped by section. Click a value for every value behind it.

- **App:** robotparts
- **Replaces:** the datasheet proposal's hand-built tables (robotparts `lane/datasheet`).
- **Shows:** units in their own column or next to each value, a distribution in a cell, badges, presets that filter
  (Measured vs datasheet, Twin-ready for M2, To measure next), and the side peek's "every value behind it".
- **Data:** `datasheet.json`, from the lane's snapshot in `source/`. CAN 14's torque values carry robotparts'
  2026-10-25 Kt correction: coulomb friction 0.0551 N·m, ripple 25.8 / 12.3 / 11.1 mN·m (k14 / k28 / k24).
