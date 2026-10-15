import type { RefinementInfo, RefinementOptions } from "../api";

/**
 * Suffix for a run's meta line describing its extra mesh refinement, e.g.
 * " · long wake · slipstreams (4 zones, 3.8 mm cells)". Uses what the backend
 * actually meshed when known, otherwise just the requested options.
 */
export function refinementLabel(
  requested: RefinementOptions | undefined,
  meshed: RefinementInfo | null | undefined,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string {
  const parts: string[] = [];
  if (requested?.long_wake) parts.push(t("detail.refine.longWake"));
  if (requested?.prop_slipstream) {
    const zones = meshed?.slipstreams ?? [];
    if (zones.length) {
      const finest = Math.min(...zones.map((z) => z.cell_mm));
      const n = zones.length;
      const mm = finest.toFixed(1);
      parts.push(
        n === 1
          ? t("detail.refine.slipstreamZone", { mm })
          : t("detail.refine.slipstreamZones", { n, mm }),
      );
    } else {
      parts.push(t("detail.refine.slipstream"));
    }
  }
  return parts.length ? ` · ${parts.join(" · ")}` : "";
}
