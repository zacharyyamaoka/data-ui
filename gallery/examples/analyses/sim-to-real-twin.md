---
type: analysis
title: Which motor's twin to tune controllers on
question: Of the rack's eight motor twins, which is close enough to its real motor to tune a controller in simulation first?
status: decided
parts: [CAN 14, CAN 15, CAN 4, CAN 1, CAN 13, CAN 12, CAN 21, CAN 11]
decision: CAN 14
author: BAM rig (example)
date: 2026-10-26
visibility: public
tags: [sim-to-real, rack]
---

> [!example] An analysis on real hardware runs
> Every number is the sim-to-real case's data: the rack's eight motors, Oct 23–25 2026. The whole dashboard is embedded
> below with one line, `![[../sim-to-real/views.base]]`; a click on a motor there narrows every panel.

## The ruler

A twin cannot beat its **measurement floor**: how much the real motor disagrees with itself run to run. So the fair
score is the twin's RMS error divided by that floor: 1× would be perfect.

> [!warning] Only one floor is measured
> CAN 14's floor comes from repeated identical tapes. The other seven are a sine cycle-to-cycle **proxy**, so their
> ratios are softer.

## Twin error over floor

| Motor | Part | Twin RMS | Floor | Twin ÷ floor | Floor kind |
|---|---|---|---|---|---|
| CAN 14 | GIM4305-10 | 1.1169 | 0.522 | **2.14** | measured repeats |
| CAN 15 | small arm (unidentified) | 1.617 | 0.5438 | 2.973 | proxy |
| CAN 4 | JMC 60ASM400 | 24.4206 | 5.2841 | 4.622 | proxy |
| CAN 1 | GIM4305-10 | 2.5866 | 0.4471 | 5.786 | proxy |
| CAN 13 | JMC 60ASM200 | 7.9327 | 0.9432 | 8.41 | proxy |
| CAN 12 | JMC 60ASM200 | 9.7424 | 0.9414 | 10.349 | proxy |
| CAN 21 | JMC 60ASM400 | 3.617 | 0.3342 | 10.822 | proxy |
| CAN 11 | JMC 60ASM200 | 13.2106 | 1.1323 | 11.668 | proxy |

## The dashboard

![[../sim-to-real/views.base]]

> [!decision] Chosen: CAN 14
> - The lowest twin-to-floor ratio, 2.14×, and the only one measured against a real repeat floor.
> - It also passes the most acceptance gates of the eight (3 pass, 4 partial, 2 fail, 2 not run), tied on passes with CAN 4.
> - Next: CAN 15 (2.97×). The JMC 60ASM200 twins (8.4–11.7×) are not ready to tune on.
