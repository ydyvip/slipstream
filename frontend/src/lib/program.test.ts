import { describe, expect, it } from "vitest";
import {
  F16_BUILDUP,
  f16PresetList,
  matrixCaseCount,
  parseDegList,
  uniqueSorted,
  type SweepKey,
} from "./program";

describe("parseDegList", () => {
  it("splits on commas, spaces and mixes of both", () => {
    expect(parseDegList("-5, 0, 5")).toEqual([-5, 0, 5]);
    expect(parseDegList("-5 0 5")).toEqual([-5, 0, 5]);
    expect(parseDegList("0, 15,30 45")).toEqual([0, 15, 30, 45]);
  });

  it("parses decimals and negatives", () => {
    expect(parseDegList("2.5\t-0.5")).toEqual([2.5, -0.5]);
  });

  it("returns an empty list for blank input", () => {
    expect(parseDegList("")).toEqual([]);
    expect(parseDegList("   ,  ")).toEqual([]);
  });

  it("marks non-numeric tokens as NaN rather than dropping them", () => {
    expect(parseDegList("5, abc, 7").map((n) => Number.isNaN(n))).toEqual([
      false,
      true,
      false,
    ]);
  });
});

describe("matrixCaseCount", () => {
  it("is the product of the non-empty lists", () => {
    expect(matrixCaseCount([[1, 2, 3, 4], [5, 6, 7]])).toBe(12);
    expect(matrixCaseCount([[0, 1], [2, 3, 4], [5]])).toBe(6);
    expect(matrixCaseCount([[], [1, 2, 3], [4, 5]])).toBe(6);
  });

  it("is 0 when every list is empty", () => {
    expect(matrixCaseCount([[], []])).toBe(0);
    expect(matrixCaseCount([])).toBe(0);
  });

  it("counts single-dimension programs too", () => {
    expect(matrixCaseCount([[], [1, 2, 3]])).toBe(3);
  });
});

describe("uniqueSorted", () => {
  it("dedupes and sorts ascending, ignoring null/undefined/non-finite", () => {
    expect(uniqueSorted([5, -2, 5, 0, null, undefined, -2, NaN])).toEqual([-2, 0, 5]);
  });
});

describe("F16_BUILDUP", () => {
  it("has the alpha envelope: 12 values, -10..45 step 5", () => {
    const a = F16_BUILDUP.alpha_deg;
    expect(a).toHaveLength(12);
    expect(a[0]).toBe(-10);
    expect(a[a.length - 1]).toBe(45);
    for (let i = 1; i < a.length; i++) expect(a[i] - a[i - 1]).toBe(5);
  });

  it("has the beta envelope: 13 values, ±30 step 5", () => {
    const b = F16_BUILDUP.beta_deg;
    expect(b).toHaveLength(13);
    expect(b[0]).toBe(-30);
    expect(b[b.length - 1]).toBe(30);
    for (let i = 1; i < b.length; i++) expect(b[i] - b[i - 1]).toBe(5);
  });

  it("has the control-deflection envelopes: 5 values, -25..25 step 12.5", () => {
    for (const k of ["delta_e_deg", "delta_a_deg", "delta_r_deg"] as const) {
      const d = F16_BUILDUP[k];
      expect(d).toHaveLength(5);
      expect(d[0]).toBe(-25);
      expect(d[d.length - 1]).toBe(25);
      for (let i = 1; i < d.length; i++) expect(d[i] - d[i - 1]).toBe(12.5);
    }
  });
});

describe("f16PresetList", () => {
  it("round-trips through parseDegList for every dimension", () => {
    for (const key of Object.keys(F16_BUILDUP) as SweepKey[]) {
      expect(parseDegList(f16PresetList(key))).toEqual(F16_BUILDUP[key]);
    }
  });

  it("is space-separated and idempotent (fill-twice is a no-op)", () => {
    expect(f16PresetList("alpha_deg")).toBe("-10 -5 0 5 10 15 20 25 30 35 40 45");
    expect(f16PresetList("beta_deg")).toBe("-30 -25 -20 -15 -10 -5 0 5 10 15 20 25 30");
    expect(f16PresetList("delta_e_deg")).toBe("-25 -12.5 0 12.5 25");
    expect(f16PresetList("alpha_deg")).toBe(f16PresetList("alpha_deg"));
  });

  it("gives the expected matrix size for the alpha × beta build-up (156)", () => {
    const alpha = parseDegList(f16PresetList("alpha_deg"));
    const beta = parseDegList(f16PresetList("beta_deg"));
    expect(matrixCaseCount([alpha, beta])).toBe(156);
  });
});
