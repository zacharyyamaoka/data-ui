---
title: Broken
status: maybe
parts: [p1]
decision: p9
---

```base
data: data/parts.json
views:
  - { type: table, name: T, order: [name, prise] }
```

![[missing.base]]

```base
data: data/nope.json
views:
  - { type: table, name: U }
```
