import { describe, expect, it } from "vitest";
import { refinementLabel } from "./refinementText";
import { en } from "../i18n/en";

/** English router used as a stub `t`: resolves against the real English dict. */
function tString(key: string, vars?: Record<string, string | number>): string {
  let s = en[key] ?? key;
  if (vars) {
    s = s.replace(/\{(\w+)\}/g, (m, k: string) =>
      vars[k] !== undefined ? String(vars[k]) : m,
    );
  }
  return s;
}

describe("refinementLabel", () => {
  it("is empty without refinement", () => {
    expect(refinementLabel(undefined, undefined, tString)).toBe("");
    expect(refinementLabel({}, null, tString)).toBe("");
  });

  it("names requested options before meshing", () => {
    expect(
      refinementLabel({ long_wake: true, prop_slipstream: true }, null, tString),
    ).toBe(" · long wake · slipstreams");
  });

  it("reports zone count and finest cell once meshed", () => {
    const zone = (cell_mm: number) => ({
      level: 3,
      cell_mm,
      direction: [1, 0, 0] as [number, number, number],
    });
    expect(
      refinementLabel(
        { prop_slipstream: true },
        { long_wake: null, slipstreams: [zone(7.5), zone(3.75), zone(7.5), zone(7.5)] },
        tString,
      ),
    ).toBe(" · slipstreams (4 zones, 3.8 mm cells)");
    expect(
      refinementLabel(
        { prop_slipstream: true },
        { long_wake: null, slipstreams: [zone(7.5)] },
        tString,
      ),
    ).toBe(" · slipstreams (1 zone, 7.5 mm cells)");
  });
});
