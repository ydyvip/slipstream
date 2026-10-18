/** Test-program view + matrix panel strings. Keys prefixed `program.`/`matrix.`. */
export const program: Record<string, string> = {
  // TestProgramView header.
  "program.title": "Multi-dimensional test program",
  "program.backToNew": "← back to single run",
  "program.note":
    "Define sweeps over angle of attack (α), sideslip (β) and control deflections (δe / δa / δr), then run them all as one matrix program — every combination becomes its own run in the same group.",

  // Step 1: model & flow.
  "program.stepModel": "1 · Model & flow",
  "program.modelFile": "STL model",
  "program.baseName": "Base case name",
  "program.baseNamePlaceholder": "e.g. wing v2 matrix",
  "program.modelLine": "{name} · {tris} tris · {dims} {unit}",

  // Step 2: sweep dimensions.
  "program.stepSweeps": "2 · Sweep dimensions (Cartesian product)",
  "program.sweepHint": "comma- or space-separated degrees — blank skips this dimension",
  "program.fieldAlpha": "α — angle of attack (deg)",
  "program.fieldBeta": "β — sideslip (deg)",
  "program.fieldDeltaE": "δe — elevator (deg)",
  "program.fieldDeltaA": "δa — aileron (deg)",
  "program.fieldDeltaR": "δr — rudder (deg)",
  "program.errNumber":
    "{field}: use comma- or space-separated numbers, e.g. -5, 0, 5",
  "program.needSweep": "Add at least one sweep dimension — α, β, δe, δa or δr.",
  "program.errName": "Name the base case — every matrix run is named from it.",
  "program.estimate": "{n} cases",
  "program.estimateEq": "= product of the non-empty dimensions",
  "program.estimateWarn": " — that's a lot of full CFD solves",
  "program.starting": "Starting…",
  "program.btnRun": "Run program ({n} cases)",
  "program.startFailed": "Failed to start the program: {msg}",

  // MatrixPanel.
  "matrix.title": "Test program",
  "matrix.loading": "loading program…",
  "matrix.loadFailed": "Failed to load program: {message}",
  "matrix.gridTitle": "α × β matrix — click a cell to open the run",
  "matrix.cornerTitle": "α (rows) × β (columns)",
  "matrix.alphaValue": "α {deg}°",
  "matrix.betaValue": "β {deg}°",
  "matrix.alphaTitle": "angle of attack",
  "matrix.betaTitle": "sideslip",
  "matrix.exportCsvTitle": "Download the whole program as CSV",
  "matrix.exportCsv": "export csv",
  "matrix.cellTitle": "α {a}° · β {b}° — open run",
  "matrix.listTitle": "Program cases",
  "matrix.listHint":
    "No α × β grid — this program sweeps only control deflections.",
  "matrix.deltaValue": "{mark} {deg}°",
  "matrix.caseLabel": "case",
};
