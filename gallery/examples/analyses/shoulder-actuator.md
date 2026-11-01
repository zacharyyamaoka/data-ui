---
type: analysis
title: Shoulder actuator for a 1-DOF arm
question: Which actuator should drive the shoulder of a 1-DOF arm holding 0.3 kg at 0.25 m, under $150?
status: decided
parts:
  - aifitlab-8541438771336
  - aifitlab-8542347853960
  - aifitlab-8565793194120
  - jmc-60asm400-5-1024c
decision: aifitlab-8541438771336
author: robotparts.dev (example)
date: 2026-10-26
visibility: public
tags: [actuator, arm]
---

> [!example] An analysis on real catalog data
> The candidates' values are robotparts.dev's actuator rows (the robotparts-actuators case's `actuators.json`). The arm
> and its load are **illustrative**. This file is one Markdown file; the views below are its ```base fences.

## The requirement

> [!illustrative] The load (assumed, not measured)
> - Payload 0.30 kg at 0.25 m: 0.30 × 9.81 × 0.25 = **0.74 N·m**
> - Link 0.12 kg, centre of mass at 0.125 m: **0.15 N·m**
> - **Holding torque 0.88 N·m**: rated torque at least 0.9 N·m, peak at least 1.8 N·m, under $150

## The candidates

The catalog's own rows, filtered to this note's `parts:` (`this` is the note, as in Obsidian):

```base
data: ../robotparts-actuators/actuators.json
filters: 'this.parts.contains(id)'
views:
  - type: table
    name: Candidates
    order: [name, price, rated_torque, peak_torque, torque_density, mass]
    sort:
      - { property: price, direction: ASC }
  - type: compare
    name: Side by side
    order: [price, rated_torque, peak_torque, torque_density, mass]
    compare:
      better: { price: lower, mass: lower, peak_torque: higher, rated_torque: higher, torque_density: higher }
```

| Candidate | Rated ≥ 0.9 N·m | Peak ≥ 1.8 N·m | ≤ $150 | Passes |
|---|---|---|---|---|
| [[aifitlab-8541438771336\|Steadywin GIM4305-10]] | 1.05 (1.2×) | 3.82 | $70 | yes, slim thermal margin |
| [[aifitlab-8542347853960\|Steadywin GIM6010-8]] | 5.0 (5.7×) | 11.0 | $70 | yes |
| [[aifitlab-8565793194120\|Damiao DM-J4310-2EC]] | 3.5 (4.0×) | 12.5 | $125 | yes |
| [[jmc-60asm400-5-1024c\|JMC 60ASM400-5-1024C]] | 1.27 (1.4×) | 3.8 | — | no: no price on record |

## Where it sits in the whole catalog

The actuator-charts case's Ashby chart, embedded from its file: every actuator's peak torque against its mass.

![[../actuator-charts/views.base#Ashby · torque vs mass]]

> [!decision] Chosen: [[aifitlab-8541438771336|Steadywin GIM4305-10]]
> - Passes every gate at $70, the price of the GIM6010-8, at 150 g against 388 g.
> - **The risk is heat:** its rated torque is 1.2× the holding torque. If the arm holds at full extension for minutes,
>   take the [[aifitlab-8542347853960|Steadywin GIM6010-8]]: same price, 5.7× margin, 238 g heavier.
