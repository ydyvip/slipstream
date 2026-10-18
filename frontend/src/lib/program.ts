/**
 * Pure helpers for the multi-dimensional test program (v10). Factored out of
 * NewRunView (previously TestProgramView) so they stay unit-testable in the
 * node vitest environment.
 */

/** A sweep dimension of the multi-dim case matrix (5-DOF Cartesian product). */
export type SweepKey =
  | "alpha_deg"
  | "beta_deg"
  | "delta_e_deg"
  | "delta_a_deg"
  | "delta_r_deg";

/**
 * One-click F-16 build-up envelopes. Numbers are exact ranges from the real
 * F-16 JSBSim aero table (α −10…45°/5°, β ±30°/5°, control deflections
 * ±25°/12.5°) — bit-for-bit what the preset chips fill into the sweep boxes.
 * Do not "improve" these values.
 */
export const F16_BUILDUP: Record<SweepKey, number[]> = {
  alpha_deg: [-10, -5, 0, 5, 10, 15, 20, 25, 30, 35, 40, 45],
  beta_deg: [-30, -25, -20, -15, -10, -5, 0, 5, 10, 15, 20, 25, 30],
  delta_e_deg: [-25, -12.5, 0, 12.5, 25],
  delta_a_deg: [-25, -12.5, 0, 12.5, 25],
  delta_r_deg: [-25, -12.5, 0, 12.5, 25],
};

/** Text-box value for an F-16 preset dimension (space-separated, matches parseDegList). */
export function f16PresetList(key: SweepKey): string {
  return F16_BUILDUP[key].join(" ");
}

/**
 * Split one sweep-dimension input box into floats. Accepts comma- and/or
 * whitespace-separated values ("-5, 0 5" and "-5,0,5" both give [-5, 0, 5]).
 * A token that isn't a finite number is carried through as NaN so callers can
 * flag the exact bad input instead of silently dropping it.
 */
export function parseDegList(raw: string): number[] {
  return raw
    .split(/[\s,]+/)
    .filter((s) => s.trim() !== "")
    .map((s) => Number(s));
}

/**
 * Number of matrix cases = product of the non-empty lists, the way the backend
 * fans one run out per combination. Returns 0 when every list is empty (no
 * sweep dimensions -> not a valid program).
 */
export function matrixCaseCount(lists: number[][]): number {
  const nonEmpty = lists.filter((l) => l.length > 0);
  if (nonEmpty.length === 0) return 0;
  return nonEmpty.reduce((acc, l) => acc * l.length, 1);
}

/** Unique values of a per-member dimension, ascending. */
export function uniqueSorted(values: (number | null | undefined)[]): number[] {
  return [...new Set(values.filter((v): v is number => v != null && Number.isFinite(v)))].sort(
    (a, b) => a - b,
  );
}
