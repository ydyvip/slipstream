/** Shared lib labels (format/layers). Keys must be prefixed `lib.`. */
export const lib: Record<string, string> = {
  "lib.layersTarget": "Aim for a y+",
  "lib.layersNone": "None",
  "lib.layersStandard": "Standard — 3 layers",
  "lib.layersFine": "Fine — 6 layers",
  "lib.layersVeryFine": "Very fine — 10 layers",
  "lib.layersHintTarget":
    "Sizes the first cell in millimeters to land at the y+ you ask for, instead of as a fraction of the surface cell. This is the only mode that can actually move y+ into the valid band.",
  "lib.layersHintNone":
    "No layer cells. Fastest and most robust to mesh, but the wall shear — and so the viscous part of drag — is badly resolved.",
  "lib.layersHintStandard":
    "The default. Enough for pressure-dominated bluff bodies like a car or a drone frame.",
  "lib.layersHintFine":
    "A better-resolved wall layer for streamlined shapes — wings, hulls, fairings — where skin friction and separation matter. Lowers y+ only about a quarter; see the note below.",
  "lib.layersHintVeryFine":
    "Deepest stack. Slow to mesh, and on awkward geometry snappyHexMesh may fail to grow it over the whole surface, which is worse than fewer layers grown cleanly — check the y+ report and the coverage afterwards.",
  "lib.layersYplusCaveat":
    "Layer presets change y+ by about a third at most. They cannot pull a badly out-of-range y+ into the valid band — that needs a finer surface mesh.",
};
