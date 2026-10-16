# aero/ — OpenFOAM 风洞数据 → JSBSim 气动模型工具链

按 `docs/OpenFOAM_to_JSBSim_aerodynamic_model_plan.md`（§8 架构）实现的落地工具。
把 OpenFOAM 风洞工况结果（`forceCoeffs` + `forces` post-processing 输出）转换为
可追溯的 SI 气动数据库，再生成 JSBSim `<aerodynamics>` XML，并对生成结果做回归验证。

```
aero/
├── config/
│   ├── aircraft_geometry.yaml     参考面积/翼展/弦长、重心、飞行包线（SI）
│   ├── coordinate_mapping.yaml    坐标系、符号约定、力矩参考点、FO 列映射
│   ├── jsbsim_properties.yaml    JSBSim 属性映射、输出轴、系数→轴对应
│   └── cfd_case_matrix.yaml      工况矩阵（alpha/beta 扫描）
├── raw/                           OpenFOAM 原始输出（按 case 分目录）
│   ├── forceCoeffs/<case>/coefficient.dat
│   └── forces/<case>/forces.dat
├── database/
│   ├── aero_raw.csv               未经处理的原始量（含收敛信息/元数据）
│   ├── aero_normalized.csv        归一化后的 SI 数据库（坐标/单位/力矩参考点统一）
│   ├── aero_tables.json           拟合的 1D 气动表
│   └── metadata.json              生成元数据
├── src/                           工具链源码（每步一个模块，见下）
├── templates/aerodynamics.xml.j2  JSBSim <aerodynamics> Jinja2 模板
├── generated/aerodynamics.xml     生成的 JSBSim 气动模型
├── tests/                         单元 + 端到端测试（pytest）
├── reports/                       回归对比报告
│   ├── coefficient_comparison.csv
│   └── validation_report.md
└── scripts/
    ├── make_sample_force_coeffs.py  合成 OpenFOAM 输出的示例数据生成器
    └── run_pipeline.py             主流程：raw → DB → tables → XML → 验证
```

## 快速开始

```sh
# 生成示例原始数据（10 个工况：alpha 扫描 + beta 扫描）并跑完整流程
python aero/scripts/run_pipeline.py --generate-raw

# 只跑流程（数据已在 raw/ 时）
python aero/scripts/run_pipeline.py

# 测试（无需 OpenFOAM / jsbsim）
cd aero && python -m pytest -q tests
```

产出：`database/aero_raw.csv`、`aero_normalized.csv`、`aero_tables.json`、
`generated/aerodynamics.xml`、`reports/coefficient_comparison.csv`、
`reports/validation_report.md`。

## 流程（每步一个 src 模块）

| 步骤 | 模块 | 输入 → 输出 |
|---|---|---|
| 1. 解析 `forceCoeffs` 输出 | `parse_force_coeffs.py` | `coefficient.dat` → 系数 dict（含 `(f)` 全量/压力拆分） |
| 2. 解析 `forces` 输出 | `parse_forces.py` | `forces.dat` → 有量纲力/力矩（CofR，CFD 系） |
| 3. 坐标变换 + 力矩参考点 | `transform_coordinates.py` | CFD 系 → aero 系；CofR → CG（`M_C = M_O − (r_C − r_O) × F`） |
| 4. 归一化 | `normalize_coefficients.py` | → `aero_normalized.csv`（CD/CY/CL/Cl_roll/Cm_pitch/Cn_yaw） |
| 5. 拟合 1D 表 | `fit_aero_tables.py` | → `aero_tables.json`（alpha 轴取 beta=0 干净扫描，反之亦然） |
| 6. 生成 XML | `generate_jsbsim_xml.py` | → `generated/aerodynamics.xml` |
| 7. 结构/物理校验 | `validate_tables.py` | NaN/Inf、断点单调、重复 case、包线覆盖 |
| 8. 回归对比 | `compare_jsbsim_cfd.py` | → `reports/*`（JSBSim 查表 vs CFD 系数） |

## 关键约定（与 plan 一致）

- **单位**：数据库 SI（N、N·m、m、Pa）；XML 输出英制（lbf、lbf·ft、ft、psf），
  换算集中在 `src/_units.py`。数据库系数已是无量纲（按 q·S 及其参考长度归一）。
- **"只乘一次"规则**：生成的 `<axis>` 函数 `力 = CL(α) · qbar_psf · Sw_sqft`，
  力矩再乘 `cbarw-ft`/`bw-ft`。系数已含归一化，绝不重复乘 q·S（`test_units.py` 兜底）。
- **命名风险（plan §1）**：OpenFOAM `forceCoeffs` 的 `Cl` 是**升力**系数；JSBSim
  的 `Cl` 习惯上是滚转力矩。一律按物理意义经 `jsbsim_properties.yaml` 的
  `table_to_axis` 映射（CL→LIFT、CD→DRAG、CY→SIDE、Cm_pitch→PITCH、
  Cn_yaw→YAW、Cl_roll→ROLL），不按名字硬配。
- **符号约定**：`coordinate_mapping.yaml` 的 `sign` 块默认各系数 `+1`
  （CD 向后、CL 向上、Cm 抬头为正即静稳定方向）。改符号会整体翻转系数，
  `test_axis_signs.py` 会校验物理方向（α 增 → CL 增；dCm/dα < 0 静稳定；
  β 增 → CY/Cl/Cn 随风标配置）。
- **力矩参考点**：默认 `moment_reference: "cg"` —— CofR 力矩先平移到重心再归一化；
  用 `"cofr"` 则保留 CFD 积分参考点。`test_moment_reference.py` 用交叉叉积验证平移。
- **源优先级**：有 `forces` 输出时，系数由**有量纲力/力矩**推导（权威路径）；
  否则回退 `forceCoeffs` 列（`coefficient_source` 列记录来源）。

## 配置说明

| 文件 | 内容 | 改什么 |
|---|---|---|
| `aircraft_geometry.yaml` | S_ref / b / cbar、CofR、CG、envelope | 换真实机型的第一站 |
| `coordinate_mapping.yaml` | rotation、sign、moment_reference、FO 列名映射、forces 行布局 | 坐标系/符号/日志格式变化 |
| `jsbsim_properties.yaml` | property_map、axes（独立变量+因子）、table_to_axis | 新气动轴 / 轴名调整 |
| `cfd_case_matrix.yaml` | 工况矩阵 + 统一条件/参考值默认 | 加工况（alpha/beta/舵偏/速度） |

## 限制与后续

- `raw/` 当前为**合成示例数据**（`make_sample_force_coeffs.py` 解析模型），
  用于验证工具链本身；接真实 OpenFOAM 输出前请替换（并更新
  `aircraft_geometry.yaml` 为实测量）。
- `forces` 输出解析支持 OpenFOAM v2306 单文件 `forces.dat`（4 个向量组）布局；
  旧版多文件布局需扩展 `parse_forces`。
- 本仓库未安装 python `jsbsim` 包，`test_xml_load.py` 只做 XML 结构校验
  （断点单调、因子只乘一次、包线覆盖、与 DB 数值一致）；
  若安装 `jsbsim`，同文件会自动追加真实加载测试。
- 动导数（Cq、Cp、依赖角速度的项）、舵面效率、螺旋桨滑流耦合、动态失速
  属后续增量，当前生成稳态静导数表。
