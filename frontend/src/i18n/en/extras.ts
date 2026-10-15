/** SweepPanel / LogPanel / LineChart / Stepper strings.
 *  Prefixes: `sweep.` `log.` `chart.` `stepper.`. */
export const extras: Record<string, string> = {
  // SweepPanel: load states + panel titles.
  "sweep.title": "Sweep",
  "sweep.loading": "loading sweep…",
  "sweep.loadFailed": "Failed to load sweep: {message}",
  "sweep.trimTitle": "Trim solve",
  "sweep.meshTitle": "Mesh independence",
  "sweep.pitchTitle": "Pitch sweep",
  "sweep.yawTitle": "Yaw sweep",

  // SweepPanel: header meta + CSV export.
  "sweep.metaSpeed": "{speed} m/s",
  "sweep.metaTol": "tol {pct}",
  "sweep.metaFinished": "{settled}/{total} finished",
  "sweep.exportCsvTitle": "Download sweep as CSV",
  "sweep.exportCsv": "export csv",

  // SweepPanel: trim-solver strip.
  "sweep.trimming": "trimming… iteration {n}",
  "sweep.trimFailed": "TRIM FAILED after {n} iteration{s} — {msg}",
  "sweep.trimDone": "TRIM",
  "sweep.trimMaxIter": "TRIM (max iterations)",
  "sweep.trimLine": "tilt {tilt}° · thrust {thrust} g/prop · drag {drag} N",

  // SweepPanel: chart titles + axis labels.
  "sweep.chartCdMesh": "Cd vs mesh size",
  "sweep.chartCd": "Cd vs {param}",
  "sweep.chartCl": "Cl vs {param}",
  "sweep.chartLD": "Lift-to-drag vs {param}",
  "sweep.chartDragMesh": "Drag vs mesh size",
  "sweep.chartDrag": "Drag vs {param}",
  "sweep.xCells": "mesh cells (millions)",
  "sweep.xAngle": "{param} (deg)",
  "sweep.dragN": "drag (N)",

  // SweepPanel: results table headers.
  "sweep.headerMesh": "mesh",
  "sweep.headerCells": "cells",
  "sweep.headerDrag": "drag",
  "sweep.headerCdChange": "Cd change",

  // LogPanel.
  "log.title": "Log",
  "log.lines": "{n} lines",
  "log.empty": "no log output yet",

  // LineChart.
  "chart.xLabelDefault": "iteration",
  "chart.empty": "waiting for data…",
  "chart.tooltipIter": "iter {x}",

  // Stepper: short pipeline stage labels + failure label.
  "stepper.queued": "Queued",
  "stepper.preparing": "Prepare",
  "stepper.meshing": "Mesh",
  "stepper.solving": "Solve",
  "stepper.postprocessing": "Post",
  "stepper.done": "Done",
  "stepper.failed": "failed",
};
