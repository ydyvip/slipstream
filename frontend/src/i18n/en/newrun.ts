/** New-run setup panel strings. Keys must be prefixed `newrun.`. */
export const newrun: Record<string, string> = {
  // Flow-model helper text (flowModelHint) + quality time hints.
  "newrun.flowHintIncompressible":
    "Density is held constant — right for almost everything, but it stops " +
    "being true past about Mach 0.3.",
  "newrun.flowHintTransonic":
    "Solves density and temperature too, steadily. Runs take a few times " +
    "longer than incompressible.",
  "newrun.flowHintSupersonic":
    "Density-based and shock-capturing, so shocks stay sharp. Transient and " +
    "Courant-limited: expect tens of minutes, not minutes.",
  "newrun.qualityCoarse": "~2–4 min",
  "newrun.qualityMedium": "~8–15 min",
  "newrun.qualityFine": "~30+ min",

  // Validation + error messages.
  "newrun.errBackend": "Backend unreachable — is the server running on :8000?",
  "newrun.errStartRun": "Failed to start run: {msg}",
  "newrun.errNotStl": "\"{name}\" is not an .stl file",
  "newrun.errParse": "Could not parse STL: {msg}",
  "newrun.errRepair": "Repair failed: {msg}",
  "newrun.errWindSpeed": "Wind speed must be a positive number",
  "newrun.errSweepAngles":
    "A sweep needs 2–8 comma-separated angles, e.g. 0, 15, 30, 45",
  "newrun.errTrimWeight":
    "Enter the craft's weight in grams — the trim attitude and thrust depend on it",
  "newrun.errTrimWeightNum": "Craft weight must be a positive number of grams",
  "newrun.errMeshTol":
    "Mesh sweep tolerance must be a percentage above 0 and at most 50",
  "newrun.errAnglesNum": "Roll, pitch and yaw must be numbers",
  "newrun.errPropRows":
    "Each propeller needs finite X/Y/Z, a positive diameter and thrust ≥ 0",
  "newrun.errRefArea": "Reference area must be a positive number (cm²)",
  "newrun.errSupersonic":
    "Supersonic needs Mach 1.05 or more (about 357 m/s). At and just " +
    "below Mach 1 the flow is transonic — pressure still travels " +
    "upstream, which this solver's boundaries assume it cannot. Use " +
    "the transonic model there.",
  "newrun.errCompressible":
    "Above 200 m/s pick a compressible flow model — the incompressible " +
    "solver ignores the density changes that dominate there.",
  "newrun.errLayerRange":
    "Layer {key} must be a number between {lo} and {hi}",
  "newrun.errYPlus": "Target y+ must be a number between 1 and 1000",
  "newrun.errYPlusLayers":
    "Aiming for a y+ needs between 1 and {max} layers",

  // Viewer overlay.
  "newrun.replace": "replace",
  "newrun.boundingBoxTitle":
    "model bounding box in the selected unit — check this looks right",
  "newrun.unitWarn":
    "Read as {unit}, this model is {size} across — the STL was probably exported in a different unit.",
  "newrun.useUnit": "use {unit}",
  "newrun.repairing": "Repairing model · {stage}",
  "newrun.tryAgain": "try again",
  "newrun.repaired": "Repaired: {summary}",
  "newrun.restoreOriginal": "restore original",
  "newrun.notClosed":
    "Not a closed surface ({problem}). It may mesh badly or stall the solver.",
  "newrun.repairModel": "repair model",

  // STL inspection / repair summary fragments.
  "newrun.inspOpenEdges": "{n} open edges",
  "newrun.inspNonManifold": "{n} edges shared by 3+ faces",
  "newrun.inspNotClosed": "surface isn't closed",
  "newrun.repClosed": "closed surface",
  "newrun.repOpen": "surface still open",
  "newrun.repBodies": "{n} bodies",
  "newrun.repTris": "{n} triangles",
  "newrun.repShift": "avg shift {shift} {unit}",
  "newrun.repMax": "max {max} {unit}",

  // Viewer hint.
  "newrun.hintSelected":
    "rotate with the axis controls · click empty space to deselect",
  "newrun.hintProps":
    "click the model to rotate it · drag disks to move (⇧ = height) · wind flows along +X",
  "newrun.hintDefault":
    "click the model to rotate it · drag to orbit · wind flows along +X",

  // Rotate panel.
  "newrun.rotate": "Rotate",
  "newrun.rotateReset": "reset",
  "newrun.axisLockTrim": "solved by trim",
  "newrun.axisLockSwept": "swept",
  "newrun.axisRoll": "roll",
  "newrun.axisPitch": "pitch",
  "newrun.axisYaw": "yaw",
  "newrun.axisDegreesAria": "{axis} degrees",

  // Dropzone.
  "newrun.dropTitle": "Drop an STL here",
  "newrun.dropSub": "or click to browse · try a sample:",
  "newrun.sampleQuad": "quad",
  "newrun.sampleCar": "car",
  "newrun.sampleWing": "wing",
  "newrun.haveMesh": "already have a volume mesh?",
  "newrun.importMesh": "import a Gmsh, Fluent or OpenFOAM mesh",
  "newrun.step1": "drop your STL",
  "newrun.step2": "set wind speed & quality",
  "newrun.step3": "run — get drag, lift & flow",

  // Config panel.
  "newrun.panelTitle": "Analysis setup",
  "newrun.fieldName": "Run name",
  "newrun.placeholderName": "e.g. quad frame v2",
  "newrun.fieldUnit": "STL unit",
  "newrun.unitMm": "millimeters (mm)",
  "newrun.unitCm": "centimeters (cm)",
  "newrun.unitM": "meters (m)",
  "newrun.unitIn": "inches (in)",
  "newrun.fieldFlowModel": "Flow model",
  "newrun.flowIncompressible": "Incompressible — up to ~Mach 0.3 (110 m/s)",
  "newrun.flowTransonic": "Transonic — compressible, steady, to ~Mach 1.2",
  "newrun.flowSupersonic": "Supersonic — shock-capturing, Mach 1.05+",
  "newrun.fieldWindSpeed": "Wind speed (m/s)",
  "newrun.fieldYawAngles": "Yaw angles (deg)",
  "newrun.fieldYaw": "Yaw (deg)",
  "newrun.fieldPitchAngles": "Pitch angles (deg)",
  "newrun.fieldPitch": "Pitch (deg)",
  "newrun.fieldRoll": "Roll (deg)",
  "newrun.sweepYawTitle": "2–8 comma-separated yaw angles in degrees",
  "newrun.sweepPitchTitle": "2–8 comma-separated pitch angles in degrees",
  "newrun.pitchTitle": "positive pitch = nose-down forward-flight tilt",
  "newrun.rollTitle":
    "roll about the model's X axis, applied before pitch and yaw",
  "newrun.sweepLabel": "Sweep — queue one run per angle of",
  "newrun.sweepYaw": "yaw",
  "newrun.sweepPitch": "pitch",
  "newrun.sweepTrimUnavail": "unavailable while solving trim",
  "newrun.meshSweepTitle":
    "Rerun at coarse, medium and fine meshes until Cd stops changing",
  "newrun.meshSweepLabel": "Mesh independence — refine until Cd changes ≤",
  "newrun.meshTolAria": "Cd change tolerance (percent)",
  "newrun.propsLabel": "Propeller disks — powered flow",
  "newrun.propThrust": "thrust g",
  "newrun.removeProp": "remove propeller",
  "newrun.addProp": "+ add propeller",
  "newrun.findMotorsTitle":
    "Find the motors in the model and place one disk on each",
  "newrun.findingMotors": "finding motors…",
  "newrun.detectMotors": "detect motors",
  "newrun.propNote": "positions/ø in STL units · thrust axis = model +Z",
  "newrun.propTrimNote": "thrust solved by trim",
  "newrun.foundMotors": "found {n} motors — disks placed on top of them",
  "newrun.noMotors":
    "no motors recognized ({reason}) — disks placed at the frame corners",
  "newrun.detectUnavail":
    "motor detection unavailable — disks placed at the frame corners",
  "newrun.trimLabel": "Solve trim attitude",
  "newrun.trimWeightLabel": "Craft weight (g) — required",
  "newrun.trimWeightPlaceholder": "all-up weight, e.g. 650",
  "newrun.trimHint":
    "iterates pitch + per-prop thrust until thrust balances drag and weight",
  "newrun.refAreaLabel": "Reference area (cm²) — optional",
  "newrun.refAreaPlaceholder": "auto (frontal area)",
  "newrun.refAreaTitle":
    "Coefficient reference area. Leave blank to use frontal area; set planform area for a wing's lift coefficient.",
  "newrun.groundPlaneLabel":
    "Ground plane (rolling road) — for cars & vehicles",
  "newrun.symmetryLabel":
    "Half-model symmetry (≈2× faster) — symmetric models, 0° yaw only",
  "newrun.symmetryDisabled": "disabled: needs 0° yaw, no props/trim",
  "newrun.refineLabel": "Extra mesh refinement — optional",
  "newrun.longWakeLabel":
    "Longer wake — refine 4 body lengths behind the model",
  "newrun.slipstreamLabel":
    "Prop slipstreams — refine the flow through each prop disk",
  "newrun.slipstreamNeeds": "needs propeller disks",
  "newrun.refineHint":
    "more cells and a longer run; the slipstream zones tilt with the wind speed and thrust",
  "newrun.layersLabel": "Boundary layers",
  "newrun.layersCustom": "Custom…",
  "newrun.targetYPlus": "Target y+",
  "newrun.layers": "Layers",
  "newrun.expansionRatio": "Expansion ratio",
  "newrun.finalThickness": "Final layer thickness",
  "newrun.yplusBandNote":
    "30–300 is the band the wall functions are valid in; 100 is a safe middle. The first layer is sized from a flat-plate friction estimate, so treat it as aiming, not hitting — the run reports the y+ it actually achieved.",
  "newrun.customLayersNote":
    "Thickness is a fraction of the surface cell, not a length. More layers and a thinner final layer lower y+; the run reports the y+ it actually achieved.",
  "newrun.groundLayersLabel": "Also grow layers on the floor",
  "newrun.groundLayersHint":
    "Only worth it with a static floor — a rolling road moves with the air, so it has no boundary layer to resolve.",
  "newrun.meshQuality": "Mesh quality",
  "newrun.meshSweepQualityNote":
    "set by the mesh sweep: coarse, then medium and fine only if needed",

  // Run button + footer.
  "newrun.btnStarting": "Starting…",
  "newrun.btnMeshSweep": "Run mesh independence sweep",
  "newrun.btnTrim": "Run trim solve",
  "newrun.btnSweep": "Run {param} sweep",
  "newrun.btnRun": "Run analysis",
  "newrun.runsSerial":
    "Runs execute one at a time — a new run queues behind any active one.",
};
