import type { RunResult } from "../api";
import { useT } from "../i18n";
import {
  formatArea,
  formatCoeff,
  formatDuration,
  formatForce,
  formatInt,
  formatSpeed,
} from "../lib/format";
import { downloadText, resultToCsv, slugify } from "../lib/download";
import { layerCoverageWarning, yPlusRows, yPlusText } from "../lib/layers";

// Split-bar segment colors (match the chart palette).
const C_PRESSURE = "#3987e5";
const C_VISCOUS = "#199e70";

/** Results summary once a run is done: hero Cd + stat grid. */
export function ResultsPanel({ result, name }: { result: RunResult; name: string }) {
  const t = useT();
  // Reference area differs from frontal only when the user overrode it.
  const refDiffers =
    result.ref_area_m2 != null &&
    Math.abs(result.ref_area_m2 - result.frontal_area_m2) > 1e-9;

  const mach = result.mach ?? result.wind_speed / 340.3;
  const flowModel = result.flow_model ?? "incompressible";

  const stats: { label: string; value: string }[] = [
    { label: t("detail.liftCoeffCl"), value: formatCoeff(result.cl) },
    { label: t("detail.dragForce"), value: formatForce(result.drag_N) },
    { label: t("detail.liftForce"), value: formatForce(result.lift_N) },
    { label: t("detail.frontalArea"), value: formatArea(result.frontal_area_m2) },
    ...(refDiffers
      ? [{ label: t("detail.referenceArea"), value: formatArea(result.ref_area_m2!) }]
      : []),
    ...(result.reynolds
      ? [
          {
            label: t("detail.reynoldsNumber"),
            value:
              result.reynolds >= 1e6
                ? `${(result.reynolds / 1e6).toFixed(2)}M`
                : formatInt(Math.round(result.reynolds)),
          },
        ]
      : []),
    ...(result.flow_model && result.flow_model !== "incompressible"
      ? [{ label: t("detail.machNumber"), value: mach.toFixed(2) }]
      : []),
    { label: t("detail.meshCells"), value: formatInt(result.mesh_cells) },
    // One row per wall patch, model first. Absent on runs solved before y+
    // was measured, which is most older runs.
    ...yPlusRows(result).map((r) => ({
      label: t("detail.yPlusAvg", { patch: r.patch }),
      value: `${r.average.toFixed(r.average < 30 ? 1 : 0)} (${r.min.toFixed(
        1,
      )}–${r.max.toFixed(0)})`,
    })),
    { label: t("detail.runtime"), value: formatDuration(result.runtime_s) },
    {
      label: t("detail.cdStd"),
      value: `±${formatCoeff(result.cd_std_last20pct, 4)}`,
    },
    {
      label: t("detail.conditions"),
      value: `${formatSpeed(result.wind_speed)} · ρ ${result.rho}`,
    },
  ];

  const exportCsv = () =>
    downloadText(`${slugify(name)}_results.csv`, resultToCsv(name, result));
  const copyCsv = () =>
    void navigator.clipboard?.writeText(resultToCsv(name, result));

  // Advisories that affect how much to trust the numbers.
  const warnings: string[] = [];
  // Compressibility only matters when an INCOMPRESSIBLE solver is being used
  // outside its range. Saying it about a compressible run is simply wrong, and
  // that is what this warning used to do.
  if (flowModel === "incompressible" && mach > 0.3)
    warnings.push(
      t("detail.warnCompressible", {
        speed: formatSpeed(result.wind_speed),
        mach: mach.toFixed(2),
      }),
    );
  if (flowModel === "transonic" && mach > 1.2)
    warnings.push(t("detail.warnTransonic", { mach: mach.toFixed(2) }));
  const mq = result.mesh_quality;
  if (mq?.rating === "poor") warnings.push(t("detail.warnMeshQuality"));
  // The backend's own verdict wins when present; it decides against the same
  // number that gets averaged. Older runs fall back to the local estimate.
  const unconverged =
    result.converged === false ||
    (result.converged === undefined &&
      result.cd_std_last20pct > 0.02 * Math.max(Math.abs(result.cd), 0.1));
  if (unconverged)
    warnings.push(
      t("detail.warnUnconverged", {
        std: formatCoeff(result.cd_std_last20pct, 3),
      }),
    );

  // y+ outside the wall-function band is the most common reason a result is
  // confidently wrong, so it belongs with the warnings rather than buried in
  // the stat grid. An in-band y+ needs no warning.
  if (result.y_plus_verdict === "low" || result.y_plus_verdict === "high") {
    const t = yPlusText(result);
    if (t) warnings.push(t);
  }
  // Layers that were requested but didn't grow. Worth saying even when y+
  // looks fine, because the average hides the patchiness.
  const coverage = layerCoverageWarning(result);
  if (coverage) warnings.push(coverage);

  // v2 drag breakdown — null (or absent) for runs solved before the feature.
  const dragP = result.drag_pressure_N;
  const dragV = result.drag_viscous_N;
  const hasSplit = dragP != null && dragV != null && dragP + dragV > 0;
  const pctP = hasSplit ? (dragP / (dragP + dragV)) * 100 : 0;

  return (
    <section className="panel results-panel">
      <div className="panel-head results-head">
        <span>{t("detail.results")}</span>
        <div className="results-export">
          <button
            className="seg"
            onClick={copyCsv}
            title={t("detail.copyCsvTitle")}
          >
            {t("detail.copy")}
          </button>
          <button
            className="seg"
            onClick={exportCsv}
            title={t("detail.downloadCsvTitle")}
          >
            {t("detail.exportCsv")}
          </button>
        </div>
      </div>
      {warnings.length > 0 && (
        <div className="result-warnings">
          {warnings.map((w, i) => (
            <div key={i} className="result-warning">
              ⚠ {w}
            </div>
          ))}
        </div>
      )}
      <div className="results-body">
        <div className={`hero-stat${unconverged ? " hero-stat-untrusted" : ""}`}>
          <div className="hero-label">
            {t("detail.dragCoefficient")}
            {unconverged && t("detail.notConverged")}
          </div>
          <div className="hero-value mono">{formatCoeff(result.cd)}</div>
          <div className="hero-sub">
            {result.transient
              ? t("detail.avgTransient", {
                  time: result.end_time_s?.toPrecision(3) ?? "?",
                  steps: formatInt(result.iterations),
                })
              : t("detail.avgSteady", {
                  iterations: formatInt(result.iterations),
                })}
            {result.stopped_early && (
              <span className="converged-note">{t("detail.stoppedEarly")}</span>
            )}
          </div>
        </div>
        <div className="stat-grid">
          {stats.map((s) => (
            <div key={s.label} className="stat-tile">
              <div className="stat-label">{s.label}</div>
              <div className="stat-value mono">{s.value}</div>
            </div>
          ))}
        </div>
        {hasSplit && (
          <div className="drag-split">
            <div className="stat-label">{t("detail.dragBreakdown")}</div>
            <div
              className="drag-split-bar"
              title={t("detail.splitTitle", {
                pressure: formatForce(dragP),
                viscous: formatForce(dragV),
              })}
            >
              <div
                className="drag-split-pressure"
                style={{ width: `${pctP}%` }}
              />
              <div className="drag-split-viscous" />
            </div>
            <div className="drag-split-legend">
              <span className="legend-item">
                <span className="legend-swatch" style={{ background: C_PRESSURE }} />
                {t("detail.pressure")}{" "}
                <span className="mono">{formatForce(dragP)}</span> ·{" "}
                {pctP.toFixed(0)}%
              </span>
              <span className="legend-item">
                <span className="legend-swatch" style={{ background: C_VISCOUS }} />
                {t("detail.viscous")}{" "}
                <span className="mono">{formatForce(dragV)}</span> ·{" "}
                {(100 - pctP).toFixed(0)}%
              </span>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
