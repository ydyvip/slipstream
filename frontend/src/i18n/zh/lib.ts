/** Shared lib labels (format/layers). Keys must be prefixed `lib.`. */
export const lib: Record<string, string> = {
  "lib.layersTarget": "以 y+ 为目标",
  "lib.layersNone": "无",
  "lib.layersStandard": "标准 — 3 层",
  "lib.layersFine": "精细 — 6 层",
  "lib.layersVeryFine": "极精细 — 10 层",
  "lib.layersHintTarget":
    "以毫米为单位设置第一层厚度，使其落在你要求的目标 y+ 上，而不是按表面单元的比例计算。这是唯一能真正把 y+ 移入有效范围的模式。",
  "lib.layersHintNone":
    "不生成边界层单元。网格生成最快、最稳健，但壁面剪切力——以及由此得到的阻力粘性部分——解析得很差。",
  "lib.layersHintStandard":
    "默认选项。适用于汽车、无人机机架等以压差阻力为主的钝体。",
  "lib.layersHintFine":
    "为流线型外形——机翼、船体、整流罩——提供解析更好的壁面层，这些地方摩擦阻力和分离很重要。y+ 大约只降低四分之一；见下方说明。",
  "lib.layersHintVeryFine":
    "层数最多的方案。网格生成较慢，而且在复杂几何上 snappyHexMesh 可能无法在整个表面生成全部边界层，这比干净生成较少层更糟——请随后检查 y+ 报告和覆盖率。",
  "lib.layersYplusCaveat":
    "预设最多只能把 y+ 改变约三分之一。它们无法把严重偏离范围的 y+ 拉入有效区间——那需要更细的表面网格。",
};
