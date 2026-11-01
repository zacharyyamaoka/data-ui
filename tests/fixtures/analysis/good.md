---
type: analysis
title: Which joint
question: Which of three joints for the shoulder?
status: decided
parts: [p1, p2, p3]
decision: p1
author: Test
date: 2026-10-26
---

## Candidates

```base
data: data/parts.json
filters: 'this.parts.contains(id)'
views:
  - { type: table, name: Candidates, order: [name, price, mass, peak_torque] }
```

![[dash.base]]

> [!decision] Chosen: [[p1|Alpha]]
> Cheapest that passes.
