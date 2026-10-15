/** SweepPanel / LogPanel / LineChart / Stepper 字符串。
 *  前缀：`sweep.` `log.` `chart.` `stepper.`。 */
export const extras: Record<string, string> = {
  // SweepPanel：加载状态与面板标题。
  "sweep.title": "扫描",
  "sweep.loading": "正在加载扫描…",
  "sweep.loadFailed": "加载扫描失败：{message}",
  "sweep.trimTitle": "配平求解",
  "sweep.meshTitle": "网格无关性",
  "sweep.pitchTitle": "俯仰扫描",
  "sweep.yawTitle": "偏航扫描",

  // SweepPanel：标题栏元信息与 CSV 导出。
  "sweep.metaSpeed": "{speed} m/s",
  "sweep.metaTol": "容差 {pct}",
  "sweep.metaFinished": "已完成 {settled}/{total}",
  "sweep.exportCsvTitle": "将扫描结果下载为 CSV",
  "sweep.exportCsv": "导出 CSV",

  // SweepPanel：配平求解状态条。
  "sweep.trimming": "正在配平… 迭代 {n}",
  "sweep.trimFailed": "TRIM 失败：经过 {n} 次迭代 — {msg}",
  "sweep.trimDone": "TRIM",
  "sweep.trimMaxIter": "TRIM（已达最大迭代次数）",
  "sweep.trimLine": "倾角 {tilt}° · 推力 {thrust} g/prop · 阻力 {drag} N",

  // SweepPanel：图表标题与坐标轴标签。
  "sweep.chartCdMesh": "Cd vs 网格尺寸",
  "sweep.chartCd": "Cd vs {param}",
  "sweep.chartCl": "Cl vs {param}",
  "sweep.chartLD": "升阻比 vs {param}",
  "sweep.chartDragMesh": "阻力 vs 网格尺寸",
  "sweep.chartDrag": "阻力 vs {param}",
  "sweep.xCells": "网格单元（百万）",
  "sweep.xAngle": "{param} (deg)",
  "sweep.dragN": "阻力 (N)",

  // SweepPanel：结果表格表头。
  "sweep.headerMesh": "网格",
  "sweep.headerCells": "单元数",
  "sweep.headerDrag": "阻力",
  "sweep.headerCdChange": "Cd 变化",

  // LogPanel。
  "log.title": "日志",
  "log.lines": "{n} 行",
  "log.empty": "暂无日志输出",

  // LineChart。
  "chart.xLabelDefault": "迭代",
  "chart.empty": "等待数据…",
  "chart.tooltipIter": "迭代 {x}",

  // Stepper：流水线各阶段短标签与失败标签。
  "stepper.queued": "排队",
  "stepper.preparing": "准备",
  "stepper.meshing": "网格",
  "stepper.solving": "求解",
  "stepper.postprocessing": "后处理",
  "stepper.done": "完成",
  "stepper.failed": "失败",
};
