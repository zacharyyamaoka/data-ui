/* The KPI delta as a number fit to print. WHY its own module: a delta is computed by the view (value − reference), so
   binary floating point leaves noise in it (1.018 − 1.032 = −0.014000000000000012), which fmtNum's truthful rule
   ("every stored digit") would print. The noise is not a stored digit: round it away, to the value column's
   `decimals` when it has some, else to 12 significant digits. No imports, so tests/unit can load it directly. */

/** d rounded for display: to `decimals` places when given, else to 12 significant digits (float noise only). */
export function deltaValue(d, decimals) {
  if (typeof d !== 'number' || !Number.isFinite(d)) return d;
  if (decimals != null) return Number(d.toFixed(decimals));
  return Number(d.toPrecision(12));
}
