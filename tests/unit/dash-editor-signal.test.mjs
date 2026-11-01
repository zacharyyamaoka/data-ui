// Found recording the hero: a KPI of a text column (Held-out runs counts `run`) showed "Plots: Duration", a number it does not
// plot, because the list held only number columns. WHY a test: the options pane must say what the file says (memory
// feedback_truthful_property_rendering), whatever the view plots. Failing first.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { signalChoices } from '../../packages/dashboard/src/edit/ops.js';

const COLUMNS = { numbers: ['t', 'duration_s', 'q_rms_mrad'], texts: ['run'], labels: {} };

test('the signals on offer are the number columns, the time column aside', () => {
  assert.deepEqual(signalChoices(COLUMNS, 'q_rms_mrad'), ['duration_s', 'q_rms_mrad']);
});

test('what the view plots now is always among them, first when it is no number column', () => {
  assert.deepEqual(signalChoices(COLUMNS, 'run'), ['run', 'duration_s', 'q_rms_mrad']);
  assert.deepEqual(signalChoices({ ...COLUMNS, numbers: [] }, 'run'), ['run']);
});
