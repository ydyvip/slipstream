/** 测试程序视图 + 矩阵面板字符串。键前缀 `program.`/`matrix.`。 */
export const program: Record<string, string> = {
  // TestProgramView 页头。
  "program.title": "多维测试程序",
  "program.backToNew": "← 返回单算例",
  "program.note":
    "对迎角 (α)、侧滑角 (β) 与舵面偏角 (δe / δa / δr) 定义扫描，并作为一个矩阵程序整体运行——每个组合都是同一组内的一个算例。",

  // 第 1 步：模型与来流。
  "program.stepModel": "1 · 模型与来流",
  "program.modelFile": "STL 模型",
  "program.baseName": "基准算例名称",
  "program.baseNamePlaceholder": "例如：机翼 v2 矩阵",
  "program.modelLine": "{name} · {tris} 个三角形 · {dims} {unit}",

  // 第 2 步：扫描维度。
  "program.stepSweeps": "2 · 扫描维度（笛卡尔积）",
  "program.sweepHint": "以逗号或空格分隔的角度——留空则跳过该维度",
  "program.fieldAlpha": "α —— 迎角 (°)",
  "program.fieldBeta": "β —— 侧滑角 (°)",
  "program.fieldDeltaE": "δe —— 升降舵 (°)",
  "program.fieldDeltaA": "δa —— 副翼 (°)",
  "program.fieldDeltaR": "δr —— 方向舵 (°)",
  "program.errNumber": "{field}：请输入以逗号或空格分隔的数字，例如 -5, 0, 5",
  "program.needSweep": "至少添加一个扫描维度——α、β、δe、δa 或 δr。",
  "program.errName": "请为基准算例命名——每个矩阵算例都会以它命名。",
  "program.estimate": "{n} 个算例",
  "program.estimateEq": "＝ 非空维度之积",
  "program.estimateWarn": " —— 这需要大量完整 CFD 求解",
  "program.starting": "正在启动…",
  "program.btnRun": "运行程序（{n} 个算例）",
  "program.startFailed": "启动程序失败：{msg}",

  // MatrixPanel。
  "matrix.title": "测试程序",
  "matrix.loading": "正在加载程序…",
  "matrix.loadFailed": "加载程序失败：{message}",
  "matrix.gridTitle": "α × β 矩阵——点击单元格打开算例",
  "matrix.cornerTitle": "α（行）× β（列）",
  "matrix.alphaValue": "α {deg}°",
  "matrix.betaValue": "β {deg}°",
  "matrix.alphaTitle": "迎角",
  "matrix.betaTitle": "侧滑角",
  "matrix.exportCsvTitle": "将整个程序下载为 CSV",
  "matrix.exportCsv": "导出 CSV",
  "matrix.cellTitle": "α {a}° · β {b}° —— 打开算例",
  "matrix.listTitle": "程序算例",
  "matrix.listHint": "无 α × β 网格——该程序仅扫描舵面偏角。",
  "matrix.deltaValue": "{mark} {deg}°",
  "matrix.caseLabel": "算例",
};
