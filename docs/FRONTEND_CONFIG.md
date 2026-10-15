# Slipstream 前端风洞可配置参数

本文档整理前端「新分析 / 重解 / 导入网格」三个配置入口的**全部可配置参数**，字段名与后端 API 契约（`frontend/src/api.ts`、`backend/app/main.py`）一致。

- 前端主页：`frontend/src/components/NewRunView.tsx`
- 重解面板：`frontend/src/components/ResolvePanel.tsx`
- 导入网格面板：`frontend/src/components/MeshImportView.tsx`
- 边界层定义：`frontend/src/lib/layers.ts`

---

## 目录

1. [新分析（上传 STL）](#一、新分析上传-stl)
   - [基本 & 模型](#1-基本--模型)
   - [姿态](#2-姿态)
   - [扫描 / 自动优化](#3-扫描--自动优化)
   - [螺旋桨](#4-螺旋桨动力流)
   - [参考面积 / 地面 / 对称](#5-参考面积--地面--对称)
   - [可选细化 & 边界层 & 网格质量](#6-可选细化--边界层--网格质量)
2. [已有网格重解](#二、已有网格重解resolvepanel)
3. [导入自有网格](#三、导入自有网格meshimportview)
4. [API 支持但 UI 未暴露的参数](#四、api-支持但前端-ui-未直接暴露)

---

## 一、新分析（上传 STL）

> 入口：首页 `NewRunView`。上传（拖拽/点击/示例模型）STL 后在左侧面板配置，点 **Run analysis** 提交。

### 1. 基本 & 模型

| 参数 | 字段名 | 选项 / 范围 | 默认 | 说明 |
|---|---|---|---|---|
| 运行名称 | `name` | 任意文本 | 取自 STL 文件名 | — |
| STL 单位 | `unit` | `mm` / `cm` / `m` / `in` | `mm` | 单位明显错误时 UI 提示并建议更换 |
| 流模型 | `flow_model` | `incompressible` / `transonic` / `supersonic` | `incompressible` | 见下方求解器说明 |
| 风速 | `wind_speed` | 正数 m/s；不可压 ≤ 200 m/s | `15` | 快选按钮 10 / 15 / 25 / 40；实时换算 Mach |

**流模型（求解器）对照：**

| 流模型 | 求解器 | 适用区间 | 备注 |
|---|---|---|---|
| `incompressible` | simpleFoam（稳态 RANS，k-ω SST） | ~Mach 0.3 以内（≤110 m/s 附近） | 默认，密度恒定，最快 |
| `transonic` | rhoSimpleFoam（可压缩稳态） | ~Mach 1.2 以内 | 解密度与温度，耗时约为不可压的数倍 |
| `supersonic` | rhoCentralFoam（密度基、激波捕捉） | Mach ≥ 1.05 | 瞬态 + Courant 限制，动辄几十分钟 |

### 2. 姿态

> 先点击模型选中，再通过旋转面板逐轴设置；后端施加顺序为 `Rz(−yaw) · Ry(pitch) · Rx(roll)`。

| 参数 | 字段名 | 范围 | 说明 |
|---|---|---|---|
| 滚转 | `roll_deg` | -180° ~ 180° | 绕模型 X 轴，最先施加；开启半模型对称时不可用 |
| 俯仰 | `pitch_deg` | -180° ~ 180° | 绕模型 Y 轴，正值=低头前飞姿态；被 trim 或 pitch 扫描接管时锁死 |
| 偏航 | `yaw_deg` | -180° ~ 180° | 绕模型 Z 轴；开启 yaw 扫描时锁死 |

每轴提供 `-90° / -15° / +15° / +90°` 快捷微调。

### 3. 扫描 / 自动优化

| 参数 | 字段名 | 选项 / 范围 | 默认 | 说明 |
|---|---|---|---|---|
| 角度扫描 | `yaw_sweep` / `pitch_sweep` | 2–8 个逗号分隔角度（deg） | 关（示例 `0,15,30,45`） | 每个角度创建一个 run，共享 `group_id`；yaw/pitch 二选一 |
| 网格无关性扫描 | `mesh_sweep.tol_pct` | 0.1% – 50% | 2% | 按 coarse→medium→fine 逐级重算，直到 Cd 变化 ≤ 公差即停 |
| 配平求解 | `trim.weight_g` | 正数（g），必填 | 关 | 需先开启 propeller disks；自动迭代俯仰角 + 每桨推力至推力平衡阻力与重量 |

约束：trim 与扫描/网格扫描互斥；网格扫描由后端按成员分别设置 `quality`。

### 4. 螺旋桨（动力流）

| 参数 | 字段名 | 选项 / 范围 | 说明 |
|---|---|---|---|
| 启用 | `props`（数组） | 开 / 关 | 开启后自动生成 4 个桨盘，可调用「detect motors」识别电机位 |
| 桨盘坐标 | `props[].center` | x / y / z（STL 单位） | 3D 预览可拖拽移动（Shift=调高度，步进 0.5） |
| 桨盘直径 | `props[].diameter` | > 0 | 与单位一致 |
| 单桨推力 | `props[].thrust_g` | ≥ 0（g） | 推力轴 = 模型 +Z；trim 开启时由配平求解接管 |
| 数量 | — | 最多 8 个 | 可增删 |

### 5. 参考面积 / 地面 / 对称

| 参数 | 字段名 | 选项 / 范围 | 默认 | 说明 |
|---|---|---|---|---|
| 参考面积 | `ref_area_cm2` | 正数 cm² | 留空 = 正面投影面积 | 机翼可填机翼平面面积以获得翼型 Cl |
| 地面 | `ground_plane` | 开 / 关 | 关 | 车辆、地面效应模型；UI 为滚动道路（对应 `ground: moving`） |
| 半模型对称 | `symmetry` | 开 / 关 | 关 | ≈2× 提速；仅限左右对称模型 + 0° yaw + 无 props/trim/yaw 扫描（pitch 允许） |

> UI 仅暴露 `ground_plane`，滚动道路为后端默认；API 的 `ground: "static"`（固定地面）未在 UI 暴露。

### 6. 可选细化 & 边界层 & 网格质量

**可选网格细化 `refinement`：**

| 参数 | 字段名 | 选项 | 说明 |
|---|---|---|---|
| 长尾流细化 | `refinement.long_wake` | 开 / 关 | 在模型后方 4 倍体长范围内加密尾流 |
| 桨滑流细化 | `refinement.prop_slipstream` | 开 / 关（需 props） | 沿每个桨盘的滑流加密圆柱区域 |

**边界层 `layers`（棱柱层，决定 y+）：**

| 预设 | 对应配置 | 说明 |
|---|---|---|
| `None` | `{ count: 0 }` | 无层，最快但壁面剪切（粘性阻力）解析差 |
| `Standard — 3 层`（默认） | 不发送，走后端默认 `{ count:3, expansion:1.2, final_thickness:0.3, min_thickness:0.1 }` | 压力主导钝体（车、机架）够用 |
| `Fine — 6 层` | `{ count:6, expansion:1.2, final_thickness:0.4 }` | 翼型/船体/整流罩等流线型 |
| `Very fine — 10 层` | `{ count:10, expansion:1.15, final_thickness:0.5 }` | 深层堆叠，网格慢，复杂几何可能长不满 |
| `Aim for a y+` | `{ count, expansion:1.2, target_y_plus }` | 按 y+ 目标反算首层厚度（mm） |
| `Custom…` | `{ count, expansion, final_thickness, min_thickness }` | 手动指定 |

**自定义 / y+ 目标取值区间：**

| 参数 | 字段名 | 范围 |
|---|---|---|
| 层数 | `count` | 0 – 12 |
| 膨胀比 | `expansion` | 1.0 – 2.0 |
| 末层厚度（相对面胞比例） | `final_thickness` | 0.05 – 1.0 |
| 最小厚度 | `min_thickness` | 0.001 – 0.5 |
| 目标 y+ | `target_y_plus` | 1 – 1000 |

**其他：**

| 参数 | 字段名 | 选项 | 说明 |
|---|---|---|---|
| 地面层 | `layers.ground` | 开 / 关（需地面） | 仅固定地面（static）值得开 |
| 网格质量 | `quality` | `coarse` / `medium` / `fine` | 默认 `medium`；估计耗时 ~2-4min / ~8-15min / ~30+min；被网格扫描接管时禁用 |

---

## 二、已有网格重解（ResolvePanel）

> 对已完成 run 点 Re-solve：**复用现有网格、跳过 meshing**，仅允许改变不涉及网格的输入。

| 参数 | 字段名 | 选项 / 范围 | 说明 |
|---|---|---|---|
| 风速 | `wind_speed` | 0 – 200 m/s | 必填 |
| 每桨推力 | `thrust_g` | ≥ 0（g） | 仅当原 run 含 props；多桨时对所有桨统一生效 |

其余（姿态、质量、细化、地面、对称）全部继承原 run。

---

## 三、导入自有网格（MeshImportView）

> 上传 Gmsh / Fluent / OpenFOAM polyMesh，转换检查后为每个 patch 指定角色再求解。

| 参数 | 字段名 | 选项 / 范围 | 说明 |
|---|---|---|---|
| 网格文件 | — | `.msh` / `.msh|.cas` / zip 的 OpenFOAM polyMesh | 支持 Gmsh v2 ASCII、ASCII Fluent、polyMesh zip |
| 网格单位 | `unit` | `m` / `mm` / `cm` / `in` | 上传时选择，后端统一换算为米 |
| 边界角色 | `roles` | 见下方角色表 | **inlet、outlet、model 三者至少各一个** |
| 运行名称 | `name` | 文本 | 默认取文件名 |
| 风速 | `wind_speed` | 0 – 200 m/s | 必填 |
| 求解预算 | `quality` | `coarse` / `medium` / `fine` | 分别对应 250 / 500 / 800 迭代 |
| 参考面积 | `ref_area_cm2` | 正数 cm² | 可选，默认正面投影 |

**边界角色（`MeshRole`）：**

| 角色 | 含义 |
|---|---|
| `inlet` | 入口（来流进入） |
| `outlet` | 出口 |
| `model` | 模型（作用力测量面） |
| `slip` | 隧道壁（滑移） |
| `wall` | 壁面（无滑移，如地板） |
| `symmetry` | 对称面 |

---

## 四、API 支持但前端 UI 未直接暴露

以下字段在后端 `main.py` / `api.ts` 契约中存在，但当前 UI 未提供控件（可经由 POST `/api/runs` 直接下发）：

| 参数 | 字段名 | 默认 | 说明 |
|---|---|---|---|
| 来流密度 | `rho` | 1.225 | kg/m³ |
| 运动粘度 | `nu` | 1.5e-5 | m²/s |
| 静温 | `temperature` | 288.15 K | 仅可压缩流模型使用 |
| 地面类型 | `ground` | `moving` | `moving`（滚动道路）/ `static`（固定地面） |
| 配平控制 | `trim.max_iters` / `trim.tol_deg` | 10 / 0.5 | 配平最大迭代 / 俯仰收敛容差（deg） |

---

## 附：提交的配置 JSON 示例（等效于 UI 默认 + 开启地面）

```json
{
  "name": "quad frame v2",
  "unit": "mm",
  "wind_speed": 15.0,
  "yaw_deg": 0,
  "pitch_deg": 0,
  "quality": "medium",
  "flow_model": "incompressible",
  "ground_plane": true,
  "refinement": { "long_wake": true }
}
```
