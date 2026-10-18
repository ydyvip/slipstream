# aero/ — OpenFOAM 风洞数据 → JSBSim 气动模型工具链

按 `docs/OpenFOAM_to_JSBSim_aerodynamic_model_plan.md`（§8 架构）实现的落地工具。
把 OpenFOAM 风洞工况结果（`forceCoeffs` + `forces` post-processing 输出）转换为
可追溯的 SI 气动数据库，再生成 JSBSim `<aerodynamics>` XML，并对生成结果做回归验证。

> 当前仓库内的 `raw/` 数据是 **CH-3 真实 OpenFOAM-2512 跑出来的收敛结果**
> （10 个工况：alpha −4…16° + beta ±5/±10°），不是合成样例。想自己重跑或
> 换机型，按下面的「全流程使用说明」走一遍即可。

```
aero/
├── config/
│   ├── aircraft_geometry.yaml     参考面积/翼展/弦长、重心、飞行包线（SI）
│   ├── coordinate_mapping.yaml    坐标系、符号约定、力矩参考点、FO 列映射
│   ├── jsbsim_properties.yaml    JSBSim 属性映射、输出轴、系数→轴对应
│   └── cfd_case_matrix.yaml      工况矩阵（alpha/beta/舵偏，支持 grids 展开）
├── raw/                           OpenFOAM 原始输出（按 case 分目录）
│   ├── forceCoeffs/<case>/coefficient.dat
│   └── forces/<case>/forces.dat
├── database/
│   ├── aero_raw.csv               未经处理的原始量（含收敛信息/元数据）
│   ├── aero_normalized.csv        归一化后的 SI 数据库（坐标/单位/力矩参考点统一）
│   ├── aero_tables.json           拟合的 1D/2D 气动表（含舵面 build-up）
│   └── metadata.json              生成元数据
├── src/                           工具链源码（每步一个模块，见下）
│   └── geometry_ref.py            真实 CH-3 参考几何 + α/β→后端俯仰/偏航角映射
├── templates/aerodynamics.xml.j2  JSBSim <aerodynamics> Jinja2 模板
├── generated/aerodynamics.xml     生成的 JSBSim 气动模型
├── tests/                         单元 + 端到端测试（pytest）
├── reports/                       回归对比报告
│   ├── coefficient_comparison.csv
│   └── validation_report.md
└── scripts/
    ├── run_real_cases.py          真实 CFD 驱动：Docker OpenFOAM-2512 跑工况矩阵
    ├── run_pipeline.py            主流程：raw → DB → tables → XML → 验证
    └── make_sample_force_coeffs.py  合成样例数据生成器（无 OpenFOAM 时自测用）
```

## 全流程使用说明

整个链路分四步：**配置 → 跑真实 CFD → 跑主流程 → 测试/JSBSim 验证**。

```
┌─────────────────────────────────────────────────────────────────────┐
│ ① 配置：aircraft_geometry.yaml（几何/重心/包线）                      │
│         cfd_case_matrix.yaml（工况矩阵/条件）                         │
│         coordinate_mapping.yaml（坐标系/符号/FO 列映射）              │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ ② 真实 CFD：python aero/scripts/run_real_cases.py --all             │
│     → 逐 case：STL repair → prepare_stl（α/β 姿态）→ generate_case   │
│       → Docker OpenFOAM-2512（blockMesh→snappy→reconstruct→simpleFoam│
│         auto-stop）→ 合成 forces.dat → 写入 aero/raw/<case>/         │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ ③ 主流程：python aero/scripts/run_pipeline.py                       │
│     → raw → DB（归一化/力矩参考点/坐标变换）→ 1D/2D 表 → aerodynamics.xml│
│       → 结构校验 + 回归对比报告                                      │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ ④ 验证：cd aero && python -m pytest -q tests                        │
│     含 jsbsim 1.3.3 真实加载测试（FGFDMExec 加载生成的 aerodynamics）│
└─────────────────────────────────────────────────────────────────────┘
```

### ① 配置

换机型 / 改工况时第一站是三个 yaml（详见「配置说明」）：

- `aircraft_geometry.yaml` — 参考面积/翼展/弦长、CofR、重心、飞行包线（SI）。
  本仓库填的是 CH-3 实测（S=6.6 m²、b=8 m、cbar=0.856 m），重心为翼 25% MAC
  估计值（`center_of_gravity_m: [-1.386, 0, 0]`，替换真实重心前请勿直接用于飞行仿真）。
- `cfd_case_matrix.yaml` — 工况矩阵（alpha/beta/舵偏扫描）+ 统一来流条件。也可用
  `grids:` 块声明多根轴的笛卡尔积工况（自动展开成 case 列表，未扫的舵偏默认 0）。
  **case id 必须与 `raw/forceCoeffs/<id>/` 目录名一致**。
- `coordinate_mapping.yaml` — 坐标系旋转、符号约定、力矩参考点、FO 列映射
  （v2512 列语义，见下）。

### ② 跑真实 CFD（重跑 / 换机型时）

环境要求：

- Python 3.12+（numpy/scipy/trimesh/skimage，即 `py312` 环境，含后端依赖）
- Docker + OpenFOAM 2512 镜像：`opencfd/openfoam-default:latest`
- 机型 STL：`assets/ch-3/CH3_00_assembly_all.stl`（路径在 `run_real_cases.py` 顶部 `STL_SRC`）

```sh
# 查看矩阵内的 case id
python aero/scripts/run_real_cases.py --list

# 跑单个 case（先只跑一个验证通过再 --all）
python aero/scripts/run_real_cases.py --case ch3_a00_b00

# 整个矩阵（10 case，每 case 约 5–13 分钟，取决于机器核数）
python aero/scripts/run_real_cases.py --all

# 常用选项
--quality medium|fine     # 网格质量，默认 coarse
--skip-mesh               # 复用已在 aero/runs/ 的 case + 网格，只重解（改攻角/速度时）
--repair-only             # 只做 STL 修复并缓存到 aero/runs/repair/，不求解
--cleanup                 # 删除 aero/runs/（强制回收，谨慎）
--timeout <s>             # 单段求解超时
```

每个 case 完成后，`coefficient.dat` + `forces.dat` 会落到 `aero/raw/<case>/`；
`solve 日志在 `aero/runs/<case>/case/log.simpleFoam`。失败/未收敛的 case
不会覆盖 `raw/` 里的旧数据，解决后再重跑该 case 即可。

**v2512 列语义（务必知道）**：OpenFOAM v2512 `forceCoeffs` 输出的列是
`Cd Cd(f) Cd(r) Cl Cl(f) Cl(r) CmPitch CmRoll CmYaw Cs Cs(f) Cs(r)`——
**不带后缀的列是总量**，`(f)`/`(r)` 是前后半劈分（`Cd(f)=0.5·Cd+CmRoll`），
**并不是压力/粘性拆分**。v2512 `forces` 则输出标量列的 `force.dat`/`moment.dat`，
由驱动合成单文件 `forces.dat`（4 个向量组 `[Fp,Fv,Mp,Mv]`）供 `parse_forces` 使用。
`coordinate_mapping.yaml` 中的 `force_coeffs_columns` 已按此配置（压力/粘性列禁用），
换 OpenFOAM 版本时同步核对这里。

**符号约定（已被真实 CFD 实证）**：CH-3 机头建在 x=0、机尾 x=+4400 mm，
`prepare_stl` 居中后**机头在 −X**。因此后端姿态角映射为
`pitch_deg = +alpha`、`yaw_deg = +beta`（`geometry_ref.py` 内有完整推导）。
首版误用 `−alpha/−beta` 造成 CL 斜率、CY 符号反向，修正后实证正常。
`coordinate_mapping.yaml` 的 sign 块保持 `+1`。

### ③ 跑主流程

```sh
# 数据已在 raw/ 时，只跑流程
python aero/scripts/run_pipeline.py

# 没有真实数据时，用合成样例快速自测整条链路（会覆盖 raw/！见下警告）
python aero/scripts/run_pipeline.py --generate-raw
```

产出：`database/aero_raw.csv`、`aero_normalized.csv`、`aero_tables.json`、
`metadata.json`、`generated/aerodynamics.xml`、
`reports/coefficient_comparison.csv`、`reports/validation_report.md`。

> ⚠️ `--generate-raw`（以及测试套件里的 fixture，见下）会用合成数据**覆盖
> `raw/`**。跑测试做过 `--generate-raw` 后想恢复真实结果，需重新执行
> `run_real_cases.py --all`，或事先备份 `raw/`。

### ④ 测试与 JSBSim 验证

```sh
cd aero && python -m pytest -q tests
```

- 纯 Python 跑，不需要 OpenFOAM；59 个用例全绿（最新实测，含 `test_2d_buildup.py`
  端到端覆盖 grid 展开/2D 拟合/舵面 build-up/XML 结构/回归对比）。
- 测试里 `conftest.py` 的 pipeline fixture 用 `--generate-raw` 生成合成数据，
  所以**每次跑测试都会覆盖 `raw/` 与派生产物**。跑完若要保持真实数据，
  重跑 `run_real_cases.py --all` 即可（或跑测试前备份 `raw/`）。
- `test_xml_load.py` 里如果装了 python `jsbsim`（1.3.3 已装），会自动追加**真实
  加载测试**：用 `FGFDMExec` 包一个最小 aircraft 模型、让它的
  `<aerodynamics file="aerodynamics.xml"/>` 去加载生成的 XML。这能抓住纯结构
  校验抓不到的问题（本仓库早期版本就因此发现过表格行被压成一行、JSBSim 直接
  报 "too many columns" 的 bug）。

## 流程（每步一个 src 模块）

| 步骤 | 模块 | 输入 → 输出 |
|---|---|---|
| 1. 解析 `forceCoeffs` 输出 | `parse_force_coeffs.py` | `coefficient.dat` → 系数 dict（列语义按 `coordinate_mapping.yaml` 的 `force_coeffs_columns`，配置整体覆盖默认列；`[]`=该场不可用） |
| 2. 解析 `forces` 输出 | `parse_forces.py` | `forces.dat` → 有量纲力/力矩（CofR，CFD 系） |
| 3. 坐标变换 + 力矩参考点 | `transform_coordinates.py` | CFD 系 → aero 系；CofR → CG（`M_C = M_O − (r_C − r_O) × F`） |
| 4. 归一化 | `normalize_coefficients.py` | → `aero_normalized.csv`（CD/CY/CL/Cl_roll/Cm_pitch/Cn_yaw） |
| 5. 拟合 1D/2D 表 | `fit_aero_tables.py` | → `aero_tables.json`（1D：alpha/beta 干净扫描；2D：LIFT/DRAG/PITCH→(alpha,delta_e)、SIDE/ROLL/YAW→(alpha,beta)，横轴还附加 delta_a/delta_r 舵面影响项） |
| 6. 生成 XML | `generate_jsbsim_xml.py` | → `generated/aerodynamics.xml`（1D 表格每行 x y 单独一行、row-lookup；2D 轴以 `<sum>` 输出 FGTable2 网格表——首行是列断点、后继行是行断点+各列值，断点为弧度） |
| 7. 结构/物理校验 | `validate_tables.py` | NaN/Inf、断点单调、重复 case、包线覆盖 |
| 8. 回归对比 | `compare_jsbsim_cfd.py` | → `reports/*`（JSBSim 查表 vs CFD 系数） |

## 关键约定（与 plan 一致）

- **单位**：数据库 SI（N、N·m、m、Pa）；XML 输出英制（lbf、lbf·ft、ft、psf），
  换算集中在 `src/_units.py`。数据库系数已是无量纲（按 q·S 及其参考长度归一）。
- **"只乘一次"规则**：生成的 `<axis>` 函数 `力 = CL(α) · qbar_psf · Sw_sqft`，
  力矩再乘 `cbarw-ft`/`bw-ft`。系数已含归一化，绝不重复乘 q·S（`test_units.py` 兜底）。
- **二维 build-up**：配了 `col_var` 的轴拟合 2D 面（纵轴 LIFT/DRAG/PITCH →
  (alpha, delta_e)；横轴 SIDE/ROLL/YAW → (alpha, beta)），横轴另加 delta_a/delta_r
  舵面效应项（中性态 1D 表）。XML 中 2D 轴以 `<sum>` 输出 FGTable2 网格表
  （row+column 双查找、断点弧度），仍只做单次 qbar·Sw（·len）缩放，
  `test_2d_buildup.py` 覆盖整条链路。
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
- **可复现**：在相同输入下生成产物逐字节一致（plan §8 验收项）。默认时间戳取
  wall-clock；设环境变量 `SOURCE_DATE_EPOCH`（unix 秒或 ISO-8601）可固定生成
  时间戳实现完全确定性复现（`test_reproducibility.py` 验证）。

## 配置说明

| 文件 | 内容 | 改什么 |
|---|---|---|
| `aircraft_geometry.yaml` | S_ref / b / cbar、CofR、CG、envelope | 换真实机型的第一站 |
| `coordinate_mapping.yaml` | rotation、sign、moment_reference、FO 列名映射（`force_coeffs_columns`）、forces 行布局 | 坐标系/符号/日志格式变化 |
| `jsbsim_properties.yaml` | property_map、axes（独立变量+因子）、table_to_axis | 新气动轴 / 轴名调整 |
| `cfd_case_matrix.yaml` | 工况矩阵（`cases:` + `grids:` 笛卡尔积展开）+ 统一条件/参考值默认 | 加工况（alpha/beta/舵偏/速度） |

## 限制与后续

- **重生成依赖真实 OpenFOAM**：`raw/` 现在是 CH-3 真实收敛结果，但重跑需要
  Docker + OpenFOAM-2512 镜像（见 ②）。无 OpenFOAM 时可用
  `make_sample_force_coeffs.py`（或 `run_pipeline.py --generate-raw`）生成合成
  数据来自测工具链。
- `forces` 输出解析支持 OpenFOAM v2512 单文件 `forces.dat`（4 个向量组）布局；
  旧版多文件布局需扩展 `parse_forces`。
- `test_xml_load.py` 在装有 jsbsim 1.3.3 时会做**真实加载测试**
  （`FGFDMExec` + 最小 aircraft wrapper）；jsbsim < 1.3 则走 `ElementLoader`
  旧 API 分支。两者都没装时仅做 XML 结构校验。
- **重心是估计值**：`center_of_gravity_m: [-1.386, 0, 0]` 取翼 25% MAC，
  未实测。把生成模型用于真实飞行仿真前，请用实测重心替换并重跑主流程。
- **静态导数表**：动导数（Cq、Cp、依赖角速度的项）、螺旋桨滑流耦合、动态失速
  属后续增量。俯仰/滚转/偏航舵面（delta_e/delta_a/delta_r）已通过 2D build-up
  建模（见「关键约定」）。
