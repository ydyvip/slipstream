# OpenFOAM 风洞数据到 JSBSim 气动模型：调研与实施方案

-   版本：1.0
-   日期：2026-10-16
-   适用对象：固定翼飞机/无人机；目标是把 OpenFOAM CFD
    风洞工况结果转成可验证的 JSBSim 气动模型。
-   原则：先建立可追溯的气动数据库，再生成 XML；不要把 CFD
    原始场直接当作 JSBSim 模型。

## 1. 结论与总体流程

OpenFOAM 的数据不能直接"导入"JSBSim。正确流程为：

1.  为迎角、侧滑角、舵偏角、速度/马赫数、必要时雷诺数设计 CFD 工况。
2.  在 OpenFOAM
    中对飞机壁面积分压力和黏性应力，提取有量纲力/力矩，并计算无量纲气动系数。
3.  统一坐标系、符号、力矩参考点、参考面积/长度和单位。
4.  形成标准 CSV 气动数据库，并保留原始结果、收敛信息和工况元数据。
5.  将系数曲线/曲面生成 JSBSim `<aerodynamics>` 下的
    `<axis>`、`<function>`、`<table>`。
6.  用相同 CFD 工况对比 JSBSim 查表结果，之后进行配平和飞行动力学验证。

**高风险提示：OpenFOAM 的 `forceCoeffs` 中 `Cl` 表示升力系数；JSBSim
模型中 `Cl`
常被用作滚转力矩系数命名的一部分。不能按字段名称直接映射，必须按物理意义映射。**

## 2. JSBSim 气动模型属性与结构

### 2.1 飞机模型相关部分

常见 JSBSim 飞机模型 XML 包括：

-   `metrics`：参考面积、参考翼展、平均气动弦长等。
-   `mass_balance`：质量、重心、惯性矩/惯性积。
-   `aerodynamics`：气动力和力矩函数。
-   `flight_control`：控制输入、舵机响应、舵面限位与混控。
-   `propulsion`：发动机、螺旋桨等推进系统。
-   `ground_reactions`：起落架和地面接触。

本方案主要自动生成 `aerodynamics`，但它依赖正确的
`metrics`、控制面属性、机体坐标约定与质量/重心设置。

### 2.2 气动轴

JSBSim 官方手册支持以下常用气动轴：

  `<axis name>`   物理含义           最终量纲
  --------------- ------------------ -----------------------------
  `DRAG`          阻力方向的力贡献   lbf（常见 JSBSim 英制模型）
  `SIDE`          侧向力贡献         lbf
  `LIFT`          升力方向的力贡献   lbf
  `ROLL`          滚转力矩贡献       lbf·ft
  `PITCH`         俯仰力矩贡献       lbf·ft
  `YAW`           偏航力矩贡献       lbf·ft

也可使用 `X/Y/Z` 或 `AXIAL/SIDE/NORMAL`
等轴组，但不能随意混用不兼容的轴组。每个轴中的函数通常定义最终力/力矩贡献，而非只存一个无量纲系数。典型结构是系数乘以动压和参考面积/长度。

官方文档： - JSBSim Forces and
Moments：<https://jsbsim-team.github.io/jsbsim-reference-manual/user/concepts/forces-and-moments/> -
官方 XML
模板：<https://github.com/JSBSim-Team/jsbsim/blob/master/aircraft/aircraft_template.xml>

### 2.3 常用气动属性

下表为官方飞机模型中常见属性示例，不保证每架飞机都全部定义；应以目标
JSBSim 版本及目标飞机 XML 为准。

  ----------------------------------------------------------------------------------------------------------------------
  属性                          含义                                       单位/备注
  ----------------------------- ------------------------------------------ ---------------------------------------------
  `aero/alpha-rad`              迎角 (`\alpha`{=tex})                      rad

  `aero/beta-rad`               侧滑角 (`\beta`{=tex})                     rad

  `aero/qbar-psf`               动压                                       psf，即 lbf/ft²

  `aero/qbar-area`              动压与参考面积的组合量                     常用于构造力

  `aero/bi2vel`                 与参考翼展、速度有关的角速度无量纲化因子   常用于滚转/偏航角速度导数项；按目标版本核实

  `aero/ci2vel`                 与平均气动弦长、速度有关的无量纲化因子     常用于俯仰角速度/迎角变化率导数项

  `aero/alphadot-rad_sec`       迎角变化率                                 rad/s

  `velocities/p-aero-rad_sec`   气动轴滚转角速度                           rad/s

  `velocities/q-aero-rad_sec`   气动轴俯仰角速度                           rad/s

  `velocities/r-aero-rad_sec`   气动轴偏航角速度                           rad/s

  `velocities/mach`             马赫数                                     无量纲

  `metrics/Sw-sqft`             参考机翼面积                               ft²

  `metrics/bw-ft`               参考翼展                                   ft

  `metrics/cbarw-ft`            平均气动弦长                               ft

  `fcs/elevator-pos-rad`        升降舵位置（常见命名）                     rad

  `fcs/left-aileron-pos-rad`    左副翼位置（常见命名）                     rad

  `fcs/rudder-pos-rad`          方向舵位置（常见命名）                     rad

  `fcs/flap-pos-deg`            襟翼位置（部分模型使用）                   deg
  ----------------------------------------------------------------------------------------------------------------------

控制面属性取决于飞机 XML 的 `flight_control`
定义。不能假设所有模型都使用相同名称、正方向和单位。生成器应将属性映射写入配置文件并进行存在性检查。

参考： - JSBSim Math /
tables：<https://jsbsim-team.github.io/jsbsim-reference-manual/user/concepts/math/> -
官方 C172X
XML：<https://github.com/JSBSim-Team/jsbsim/blob/master/aircraft/c172x/c172x.xml>

### 2.4 JSBSim 表格结构

JSBSim 支持一维、二维、三维查表。`<independentVar>`
指定自变量，`<tableData>`
存放断点和结果值。下面仅演示一维系数表，数值为虚构示例：

``` xml
<function name="aero/coefficient/CL_from_alpha">
  <description>Lift coefficient from CFD</description>
  <table>
    <independentVar lookup="row">aero/alpha-rad</independentVar>
    <tableData>
      -0.174533 -0.45
      -0.087266  0.05
       0.000000  0.50
       0.087266  0.95
       0.174533  1.30
    </tableData>
  </table>
</function>
```

正式的升力贡献通常还需乘以 `aero/qbar-psf` 与
`metrics/Sw-sqft`。滚转/偏航力矩还涉及 `metrics/bw-ft`，俯仰力矩涉及
`metrics/cbarw-ft`。具体 XML 结构必须按目标 JSBSim
版本验证；不能只凭片段认定整机模型已完成。

概念公式：

\[ F=q\_`\infty `{=tex}S C,`\quad`{=tex}
M\_{`\mathrm{roll/yaw}`{=tex}}=q\_`\infty `{=tex}S b C,`\quad`{=tex}
M\_{`\mathrm{pitch}`{=tex}}=q\_`\infty `{=tex}S`\bar `{=tex}c C \]

## 3. OpenFOAM 能输出哪些气动数据？

### 3.1 `forceCoeffs`：整体无量纲系数

OpenFOAM 官方 `forceCoeffs` 功能对象可对指定壁面 patch
计算整体力系数和力矩系数。常见系数如下：

  OpenFOAM 输出字段   物理意义       标准化数据库字段   注意
  ------------------- -------------- ------------------ -----------------------------
  `Cd`                阻力系数       `CD`               检查 `dragDir` 与阻力正方向
  `Cs`                侧力系数       `CY`               侧力正方向必须统一
  `Cl`                升力系数       `CL`               OpenFOAM 的 `Cl` 是 lift
  `CmRoll`            滚转力矩系数   `Cl_roll`          不要映射成升力
  `CmPitch`           俯仰力矩系数   `Cm_pitch`         与参考点、参考弦长有关
  `CmYaw`             偏航力矩系数   `Cn_yaw`           检查 yaw 轴和符号

具体文件列名/顺序可能随版本与配置变化，解析器必须读取输出文件头，不要写死列序。

参考： - OpenFOAM 2306
forceCoeffs：<https://doc.openfoam.com/2306/tools/post-processing/function-objects/forces/forceCoeffs/> -
OpenFOAM API
forceCoeffs：<https://api.openfoam.com/2606/classFoam_1_1functionObjects_1_1forceCoeffs.html>

### 3.2 `forces`：有量纲力与力矩

`forces` 功能对象对指定 patch 的压力与黏性应力积分。通常可得到：

-   总力向量。
-   压力贡献力、黏性贡献力。
-   总力矩向量。
-   压力贡献力矩、黏性贡献力矩。
-   可选多孔阻力贡献。
-   可选力/力矩体场输出。
-   可选沿指定方向的空间分箱数据。

常见输出路径形式为
`postProcessing/<functionObjectName>/<time>/force.dat` 与
`moment.dat`；实际文件名和目录以所用版本、并行设置与字典为准。

重要参数： - `patches`：被积分的飞机表面 patch。 -
`p`、`U`、`rho`：场变量名。 - `pRef`：参考压力。 -
`CofR`：力矩参考点。 - `writeFields`：是否写出体场形式。 -
`coordinateSystem`：可选局部坐标系。 - 对不可压缩求解器，`p`
可能是运动学压力；必须根据求解器和版本正确处理密度，不能将运动学压力直接当
Pa。

参考： - OpenFOAM
Forces：<https://doc.openfoam.com/2306/tools/post-processing/function-objects/forces/forces/> -
OpenFOAM API
Forces：<https://api.openfoam.com/2606/classFoam_1_1functionObjects_1_1forces.html>

### 3.3 表面与流场分布

整体系数不足以诊断气动机理，建议同时保留：

  数据                         用途
  ---------------------------- ----------------------------------------
  表面静压 `p`                 压力分布、吸力峰、分离迹象
  压力系数 `Cp`                不同迎角下的翼面压力分布
  壁面剪切应力/摩擦相关量      摩擦阻力、分离区域判断
  `wallShearStress` 等壁面量   壁面剪切分布；字段和单位需按求解器核对
  表面采样                     翼型弦向、翼展方向负荷
  切面 `U`、`p`、涡量等        尾迹、涡结构和流动诊断
  非定常力/力矩时序            力振荡、动态响应、周期现象

`surfaces` 采样功能对象可将场采样到切面/其他表面，并可输出 VTK、EnSight
等场数据格式。STL/OBJ 通常是几何输出格式，不代表自动包含场值。

参考：<https://doc.openfoam.com/2306/tools/post-processing/function-objects/sampling/surfaces/>

### 3.4 非定常 CFD 的边界

非定常计算可以输出随时间变化的力/力矩和局部流场，但**固定姿态的非定常时序不自动等价于完整动态气动导数**。要识别角速度或迎角变化率导数，需设计规定运动、振荡输入或其他可识别的动态工况，并记录振幅、频率、相位和运动输入。

## 4. OpenFOAM 配置和工况设计

### 4.1 `forceCoeffs` 配置骨架

下面仅为配置结构示意，不是可直接复制的完整字典。OpenFOAM Foundation 与
OpenCFD/OpenFOAM.com
分支、版本和求解器可能存在字段差异，应以目标版本文档为准。

``` foam
functions
{
    aeroCoeffs
    {
        type            forceCoeffs;
        libs            ("libforces.so");
        patches         (aircraft);

        p               p;
        U               U;

        // 按当前版本配置参考密度、参考速度和方向
        // Aref、lRef、magUInf、CofR
        // dragDir、sideDir、liftDir
        // rollAxis、pitchAxis、yawAxis
    }
}
```

正式配置必须核实该版本要求的必要字段、参考密度、参考速度、面积/长度、参考点和方向轴；不要依赖默认轴方向。

### 4.2 需要固定的参考参数

-   `Aref`：参考面积，固定翼通常用机翼参考面积 (S)。
-   `lRef`：力矩参考长度；需按对应力矩系数定义设置。
-   `magUInf`：参考来流速度。
-   `rhoInf` 或求解器相关密度配置。
-   `CofR`：力矩参考点。
-   `dragDir`、`sideDir`、`liftDir`：力方向。
-   `rollAxis`、`pitchAxis`、`yawAxis`：力矩轴。
-   `patches`：仅选飞机表面，避免把风洞壁面等不相关表面算入。

所有工况必须使用一致的参考参数和方向，若确需改变则必须记录并进行转换。

### 4.3 工况矩阵建议

  阶段         工况变量                                       目的
  ------------ ---------------------------------------------- ------------------------------------------
  A 基线       设计速度，(`\alpha=0`{=tex},`\beta=0`{=tex})   检查网格、方向、参考参数
  B 迎角扫描   (`\alpha`{=tex})                               得到 (C_L,C_D,C_m)，覆盖线性区和失速附近
  C 侧滑扫描   (`\beta`{=tex}) 正负扫描                       得到 (C_Y,C_l,C_n)
  D 舵面扫描   升降舵、副翼、方向舵偏角                       识别操纵效率和符号
  E 飞行包线   速度/Mach/必要时 Re                            表达可压缩性和黏性影响
  F 组合工况   关键变量组合                                   识别显著耦合项
  G 动态工况   规定运动/角速度/振荡频率                       识别动态导数

先做低维工况验证整条链路，再根据误差逐步扩展。不要一开始就建立巨大的全因子多维表。

## 5. 标准气动数据库规范

### 5.1 必须保存的元数据

每个工况至少保存：

-   `case_id`、几何版本/哈希、网格版本/哈希。
-   OpenFOAM 版本、求解器、湍流模型、稳态/非定常。
-   `alpha_deg`、`beta_deg`、`delta_e_deg`、`delta_a_deg`、`delta_r_deg`。
-   `V_inf_mps`、`rho_kgm3`、`mu_Pas`、`Mach`、`Re`。
-   `S_ref_m2`、`b_ref_m`、`cbar_ref_m`。
-   力矩参考点 `moment_ref_x_m/y_m/z_m`。
-   坐标系和正方向定义。
-   `Fx_N`、`Fy_N`、`Fz_N`、`Mx_Nm`、`My_Nm`、`Mz_Nm`（若有量纲积分数据）。
-   `CD`、`CY`、`CL`、`Cl_roll`、`Cm_pitch`、`Cn_yaw`。
-   压力/黏性分量、收敛状态、残差/力历史摘要、来源文件、备注。

推荐标准 CSV 字段：

``` text
case_id,geometry_revision,foam_version,solver,turbulence_model,
alpha_deg,beta_deg,delta_e_deg,delta_a_deg,delta_r_deg,
V_inf_mps,rho_kgm3,mu_Pas,Mach,Re,
S_ref_m2,b_ref_m,cbar_ref_m,
moment_ref_x_m,moment_ref_y_m,moment_ref_z_m,
Fx_N,Fy_N,Fz_N,Mx_Nm,My_Nm,Mz_Nm,
CD,CY,CL,Cl_roll,Cm_pitch,Cn_yaw,
CD_pressure,CD_viscous,CL_pressure,CL_viscous,
convergence_status,source_file,notes
```

实际 CSV 应将字段名写在同一行；此处为可读性换行展示。

### 5.2 系数公式

动压：

\[
q\_`\infty`{=tex}=`\frac{1}{2}`{=tex}`\rho`{=tex}*`\infty `{=tex}V*`\infty`{=tex}\^2
\]

力系数：

\[
C_D=`\frac{D}{q_\infty S}`{=tex},`\quad `{=tex}C_Y=`\frac{Y}{q_\infty S}`{=tex},`\quad `{=tex}C_L=`\frac{L}{q_\infty S}`{=tex}
\]

力矩系数：

\[
C_l=`\frac{l}{q_\infty S b}`{=tex},`\quad `{=tex}C_m=`\frac{m}{q_\infty S\bar c}`{=tex},`\quad `{=tex}C_n=`\frac{n}{q_\infty S b}`{=tex}
\]

这里 (C_l) 为滚转力矩系数，(C_m) 为俯仰力矩系数，(C_n)
为偏航力矩系数。若 `forceCoeffs`
已经按正确参考参数输出系数，不要再次归一化；若从 `forces`
得到有量纲力/力矩，则由脚本统一计算系数，并检查压力定义、密度和方向。

## 6. 坐标、符号、参考点和单位

### 6.1 物理意义映射

  标准数据库字段   OpenFOAM 常见输出   JSBSim 目标轴
  ---------------- ------------------- ---------------
  `CD`             `Cd`                `DRAG`
  `CY`             `Cs`                `SIDE`
  `CL`             `Cl`                `LIFT`
  `Cl_roll`        `CmRoll`            `ROLL`
  `Cm_pitch`       `CmPitch`           `PITCH`
  `Cn_yaw`         `CmYaw`             `YAW`

此表只规定物理意义，不自动决定符号。符号由方向向量、坐标变换和轴定义共同决定。

### 6.2 必须书面定义的坐标规范

1.  CFD 几何坐标系。
2.  OpenFOAM 全局轴与局部气动轴。
3.  JSBSim 机体系/气动轴约定。
4.  迎角、侧滑角正方向。
5.  三分力和三分力矩正方向。
6.  舵面偏转正方向。
7.  力矩参考点。
8.  CFD 到 JSBSim 的旋转/符号变换矩阵。

至少用对称直飞、正迎角、正侧滑三个工况验证方向。不要假设两套工具的默认轴向完全相同。

### 6.3 力矩参考点

如果 CFD 力矩以 (O) 点为参考，而 JSBSim 使用 (C)
点，应进行平移。按位置向量从 (O) 指向 (C) 的定义，常见形式为：

\[
`\mathbf{M}`{=tex}*{C}=`\mathbf{M}`{=tex}*{O}-(`\mathbf{r}`{=tex}*{C}-`\mathbf{r}`{=tex}*{O})`\times`{=tex}`\mathbf{F}`{=tex}
\]

实施时必须统一位置向量和力矩定义，并用已知力臂的单元测试核验。最佳做法通常是在
OpenFOAM 后处理时将 `CofR` 直接设为模型使用的重心参考点。

### 6.4 单位转换

OpenFOAM 常用 SI：m、m²、m/s、kg/m³、Pa、N、N·m。许多 JSBSim
示例模型使用英制属性：

-   `aero/qbar-psf`：psf。
-   `metrics/Sw-sqft`：ft²。
-   `metrics/bw-ft`：ft。
-   `metrics/cbarw-ft`：ft。
-   力：lbf。
-   力矩：lbf·ft。

数据库层建议统一 SI；生成 XML 时根据 JSBSim
目标模型的属性约定转换。不能把以 m² 表示的面积直接写进
`metrics/Sw-sqft`。角度属性的 `rad`/`deg` 后缀也必须严格匹配。

## 7. 气动表拟合策略

### 7.1 分层建立

**第一层：基础静态气动** - (C_L(`\alpha`{=tex})) - (C_D(`\alpha`{=tex}))
或 (C_D(C_L)) - (C_m(`\alpha`{=tex})) - (C_Y(`\beta`{=tex})) -
(C_l(`\beta`{=tex})) - (C_n(`\beta`{=tex}))

**第二层：控制面效应** -
(C_L(`\alpha`{=tex},`\delta`{=tex}\_e))、(C_m(`\alpha`{=tex},`\delta`{=tex}\_e)) -
(C_l(`\beta`{=tex},`\delta`{=tex}\_a)) -
(C_Y(`\beta`{=tex},`\delta`{=tex}\_r))、(C_n(`\beta`{=tex},`\delta`{=tex}\_r)) -
仅在数据支持时加入交叉耦合项。

**第三层：飞行状态效应** - Mach 依赖。 - 必要时 Re 依赖。 -
襟翼、起落架、扰流板等构型。 - 近地效应（需要时）。

**第四层：动态气动** - (C\_{lp})：滚转阻尼。 - (C\_{mq})：俯仰阻尼。 -
(C\_{nr})：偏航阻尼。 - 侧力相关角速度导数。 -
(C\_{m`\dot{\alpha}`{=tex}}) 等迎角变化率项。 -
动态失速/迟滞模型（需专门证据）。

### 7.2 静态数据的限制

固定姿态 CFD
扫描主要支持静态系数。它不能仅凭数据自动唯一确定所有动态导数。动态导数需要专门的非定常/规定运动
CFD、风洞试验或有依据的工程估算，并应记录运动输入、频率、振幅、相位和数据处理方法。

### 7.3 插值建议

-   一维曲线：分段线性或保形插值；避免在失速附近使用容易过冲的高阶多项式。
-   二维/三维表：优先规则网格；明确各维断点、单位和表格布局。
-   稀疏数据：如采用回归模型，必须保留独立验证集。
-   失速区：保留非线性，不能无依据地镜像正负迎角。
-   超出 CFD 覆盖范围：明确限制、外推模型或警告，不要默默无限外推。

### 7.4 避免重复乘系数

系数表输出的是无量纲系数；JSBSim
函数常将系数乘以动压和参考参数。若输入数据已是 N 或 N·m，就不能再乘 (qS)
或 (qS`\ell`{=tex})。生成器必须通过单位测试验证最终力/力矩量纲。

## 8. 自动化转换工具架构

建议建立独立 Python 工具，而非手工拼 XML：

``` text
cfd2jsbsim/
├── config/
│   ├── aircraft_geometry.yaml
│   ├── coordinate_mapping.yaml
│   ├── jsbsim_properties.yaml
│   └── cfd_case_matrix.yaml
├── raw/
│   ├── forceCoeffs/
│   ├── forces/
│   └── surface_samples/
├── database/
│   ├── aero_raw.csv
│   ├── aero_normalized.csv
│   └── metadata.json
├── src/
│   ├── parse_force_coeffs.py
│   ├── parse_forces.py
│   ├── transform_coordinates.py
│   ├── normalize_coefficients.py
│   ├── fit_aero_tables.py
│   ├── generate_jsbsim_xml.py
│   ├── validate_tables.py
│   └── compare_jsbsim_cfd.py
├── templates/aerodynamics.xml.j2
├── generated/aerodynamics.xml
├── tests/
│   ├── test_units.py
│   ├── test_axis_signs.py
│   ├── test_moment_reference.py
│   └── test_xml_load.py
└── reports/
    ├── coefficient_comparison.csv
    ├── coefficient_plots/
    └── validation_report.md
```

配置至少包括参考面积/翼展/弦长、重心、坐标变换、轴向、舵面属性映射、单位规则和目标
JSBSim 版本。

生成器必须检查： - 必需列存在、无 NaN/Inf。 - 工况键无冲突重复。 -
查表断点排序正确。 - 单位、参考参数和坐标定义一致。 -
覆盖范围足以支持目标飞行包线。 - XML 能由目标版本加载。 -
属性名在实际模型中存在。 - 查表维度和 `<independentVar>` 数量匹配。 -
力/力矩量纲和符号测试通过。 - 同样输入可复现同样 XML。

## 9. 验证与验收

### 9.1 CFD 数据质量

-   保存残差历史和力/力矩历史。
-   稳态计算不仅看残差，还要确认积分力/力矩进入稳定平台。
-   代表工况进行网格独立性检查。
-   关键工况评估湍流模型、近壁处理、边界条件和计算域尺寸影响。
-   保存压力力/黏性力分量以诊断异常。

### 9.2 系数回归

对每个 CFD 工况： 1. 从统一数据库取出状态变量。 2. 查询生成后的 JSBSim
表。 3. 比较同一物理量的系数/力矩贡献。 4.
输出绝对误差、相对误差、最大误差位置。 5.
对误差过大的区域加密工况或修正映射。

项目开始前需按线性区、失速区、侧向和动态区分别制定误差门限；不能用一个百分比掩盖不同区域的误差来源。

### 9.3 飞行动力学验证

-   XML 成功加载且无未知属性/表格结构错误。
-   对称直飞工况的力方向正确。
-   配平时升力、重量、推力和阻力关系合理。
-   小扰动的俯仰/侧向响应方向正确。
-   舵面正向输入产生的力矩方向符合 FCS 定义。
-   失速附近趋势与 CFD 一致。
-   动态导数通过独立动态工况或试验验证。

### 9.4 验收交付物

1.  OpenFOAM 工况矩阵与版本信息。
2.  `forceCoeffs`、`forces` 原始输出。
3.  标准化 `aero_database.csv`。
4.  坐标/单位转换配置。
5.  转换器源代码与自动化测试。
6.  JSBSim 气动 XML。
7.  CFD 与 JSBSim 对比报告和曲线。
8.  数据覆盖范围、已知限制、动态导数来源和未验证项。

## 10. 实施阶段

### P0：单工况闭环

-   选一个飞机模型和设计速度。
-   明确坐标、参考参数、重心和单位。
-   配置 `forceCoeffs` 与 `forces`。
-   人工复核一次有量纲力/力矩与系数。
-   验收：符号、量纲、参考点正确。

### P1：迎角扫描

-   计算迎角扫描，提取 (C_L,C_D,C_m)。
-   生成 `LIFT/DRAG/PITCH` 基础表。
-   用同一工况回归 JSBSim 系数。
-   验收：XML 可加载，回归误差满足项目门限。

### P2：侧滑与舵面

-   增加正负侧滑和控制面偏角。
-   生成侧力、滚转、偏航及操纵相关表。
-   验收：侧向与操纵力矩符号正确。

### P3：Mach/Re 与构型

-   按实际飞行包线增加速度、Mach、必要时 Re 维度。
-   避免在数据稀疏时盲目增加表格维度。
-   验收：覆盖范围内插值稳定，外推策略明确。

### P4：动态导数与飞行验证

-   设计规定运动/非定常 CFD 或引入可信试验数据。
-   识别角速度和迎角变化率相关导数。
-   进行配平、扰动响应和飞行轨迹验证。
-   验收：动态数据来源可追溯且通过独立验证。

## 11. 常见错误排查

  -------------------------------------------------------------------------------------------------
  症状                    可能原因                           处理方式
  ----------------------- ---------------------------------- --------------------------------------
  升力符号反              `liftDir` 或坐标轴错误             用正迎角工况核对力向量

  阻力为负                `dragDir` 与定义不一致             明确阻力正方向并检查力投影

  力矩量级异常            `CofR`、参考长度错误或重复归一化   从有量纲 moment 复算

  JSBSim 力过大/过小      重复乘动压/面积或单位错误          检查 (qS C) 与英制转换

  `Cl` 映射错             OpenFOAM/JSBSim 字段语义混淆       用 `CL` 与 `Cl_roll` 分离

  曲线抖动                收敛差、采样稀疏、插值过冲         检查力历史、加密工况、换插值

  XML 加载失败            属性名/表格维度/语法错误           用目标版本官方示例最小化测试

  不同速度结果不一致      Mach/Re 或边界条件不同             保留 Mach、Re 和设置元数据

  失速不真实              数据覆盖不足或动态效应缺失         加密迎角、检查模型并单独处理动态效应
  -------------------------------------------------------------------------------------------------

## 12. 工程原则

1.  先标准化数据库，再生成 XML。
2.  分清有量纲力/力矩与无量纲系数。
3.  显式定义坐标系、符号和参考点。
4.  固定参考参数；改变时必须记录和转换。
5.  不把静态 CFD 当成动态气动导数。
6.  每个查表记录覆盖范围和外推策略。
7.  自动化生成必须配套回归测试。
8.  记录网格、湍流模型、边界条件和收敛不确定度。
9.  在目标 JSBSim 版本上验证，不假设示例跨版本完全兼容。
10. 气动 XML 不等于完整飞机模型；质量/惯量、FCS、推进系统仍需独立建模。

## 13. 官方参考资料

### JSBSim

1.  Forces and
    Moments：<https://jsbsim-team.github.io/jsbsim-reference-manual/user/concepts/forces-and-moments/>
2.  Math /
    Tables：<https://jsbsim-team.github.io/jsbsim-reference-manual/user/concepts/math/>
3.  官方飞机 XML
    模板：<https://github.com/JSBSim-Team/jsbsim/blob/master/aircraft/aircraft_template.xml>
4.  C172X
    示例（气动轴、查表和动态导数示例）：<https://github.com/JSBSim-Team/jsbsim/blob/master/aircraft/c172x/c172x.xml>

### OpenFOAM

5.  OpenFOAM 2306
    `forceCoeffs`：<https://doc.openfoam.com/2306/tools/post-processing/function-objects/forces/forceCoeffs/>
6.  OpenFOAM 2306
    `forces`：<https://doc.openfoam.com/2306/tools/post-processing/function-objects/forces/forces/>
7.  OpenFOAM 2306 surface
    sampling：<https://doc.openfoam.com/2306/tools/post-processing/function-objects/sampling/surfaces/>
8.  API
    `forceCoeffs`：<https://api.openfoam.com/2606/classFoam_1_1functionObjects_1_1forceCoeffs.html>
9.  API
    `forces`：<https://api.openfoam.com/2606/classFoam_1_1functionObjects_1_1forces.html>

由于 OpenFOAM Foundation 与 OpenCFD/OpenFOAM.com
发行版及版本之间存在字典细节差异，落地前应选定具体版本并核对对应文档。

## 14. 最终建议

先实现"单工况 → 迎角扫描 → `LIFT/DRAG/PITCH` →
系数回归"的最小闭环，尽早发现坐标、参考参数、单位、XML
查表和重复乘系数问题。之后逐步增加侧滑、舵面、Mach/Re
和动态导数。每个机型都应保留独立几何版本、参考参数、数据来源和验证报告；只有通过回归测试的
XML 才进入后续飞行仿真。
