---
type: analysis
title: Analytic or tuned gains, robot by robot
question: Does the tuning rung beat the analytic rung on every robot, or should some ship with analytic gains?
status: decided
parts: [conveyor, five_bar, gantry, hand_2, hand_3, hand_6, hand_9, lever, ur5e]
author: pidtuna (example)
date: 2026-10-26
visibility: public
tags: [pid, tuning]
---

> [!illustrative] Simulated robots
> The pid-tuning case's robots are **simulated with illustrative parameters** (pidtuna, commit 63c33ba): the numbers are
> real outputs of the tuner on those models, not hardware. Tracking error is RMS, as pidtuna reports it.

## Tracking error by rung

| Robot | Factory | Analytic | Tuned | Oracle | Tuned ÷ oracle |
|---|---|---|---|---|---|
| Conveyor belt | 90.5411 | 1.3232 | **0.3182** | 0.1698 | 1.874 |
| Five-bar arm | 70.7665 | 0.7356 | **0.4013** | 0.3957 | 1.014 |
| Cartesian gantry | 18.106 | 0.0989 | **0.0752** | 0.0624 | 1.205 |
| Robot hand, 2 motors | 257.3729 | 0.8405 | 0.8405 | 0.6347 | 1.324 |
| Robot hand, 3 motors | 272.9714 | 0.8295 | 0.8295 | 0.6128 | 1.354 |
| Robot hand, 6 motors | 284.8154 | 1.6098 | **0.8082** | 0.721 | 1.121 |
| Robot hand, 9 motors | 276.6301 | 1.5353 | **0.7395** | 0.6062 | 1.22 |
| Actuator on a lever | 80.3594 | **1.7372** | 4.1721 | 1.5542 | 2.684 |
| Six-axis arm (UR5e-class) | 41.5632 | 0.3104 | **0.1787** | 0.1678 | 1.065 |

Tuning beats the analytic rung on six robots, ties it on the two small hands (the tuner kept the analytic gains), and
is **worse on the lever**: 4.1721 against 1.7372.

## The dashboard

![[../pid-tuning/views.base]]

> [!decision] Chosen: tuned gains, except the lever
> - Ship tuned gains on the six robots where they win; on the two small hands they equal the analytic ones.
> - The lever ships **analytic** gains until its tuning regression (2.4× worse than analytic) is found.
