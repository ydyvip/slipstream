# Slipstream Docker 部署指南

本目录（以及导出的 `dist-docker/` 部署包）用于在**离线或内网服务器**上部署
Slipstream：一个镜像同时包含 Web 前端、FastAPI 后端和 OpenFOAM v2512 求解器，
无需额外安装 OpenFOAM，也无需 Docker-in-Docker。

## 交付物

| 文件 | 说明 |
|---|---|
| `slipstream-<version>-linux-amd64.tar.gz` | `docker save` 导出的完整镜像 |
| `docker-compose.yml` | Compose 文件，格式版本 **3.8** |
| `deploy.sh` / `deploy.ps1` | 一键部署脚本（Linux/macOS、Windows） |
| `.env.example` | 部署参数模板 |
| `SHA256SUMS` | 镜像校验和 |

镜像内已包含：

- OpenFOAM v2512（来自 `opencfd/openfoam-default:2512`，Ubuntu 24.04）
- Python 3.12 + FastAPI 后端及全部依赖
- 已构建好的前端静态文件（由后端同源提供）

## 环境要求

- Docker Engine **20.10+**（Windows/macOS 使用 Docker Desktop）
- Docker Compose **v1.27+** 或 **v2+**（`docker compose` / `docker-compose` 均可）
- 架构：`linux/amd64`（导出包即此架构；ARM 服务器需自行提供对应架构的 OpenFOAM 基础镜像后重新构建）
- 内存：建议 **8 GB 以上**；磁盘：镜像约 3 GB + 运行数据
- CPU：每个分析固定使用 **6 个 MPI 进程**；建议 6 核以上

> **安全提示**：Slipstream 本身没有登录/权限系统，API 与 UI 对能访问该端口的人
> 完全开放。请只部署在可信内网，或在前置 Nginx/网关上加认证与 TLS，不要把
> `8000` 端口直接暴露到公网。

> Compose 3.8 文件在新版 Docker Compose 下会提示
> `the attribute version is obsolete`，这是**正常提示**，不影响部署。

## 快速部署

### Linux / macOS

```bash
# 1. 将部署包上传到服务器，例如：
#    scp -r dist-docker/ user@server:/opt/slipstream
cd /opt/slipstream

# 2. 可选：修改端口、数据目录、并发数
cp .env.example .env
vi .env

# 3. 一键加载镜像并启动
chmod +x deploy.sh
./deploy.sh
```

### Windows（PowerShell）

```powershell
cd C:\slipstream
Copy-Item .env.example .env   # 可选
.\deploy.ps1
```

脚本会：

1. 检查 Docker / Compose；
2. 首次运行时从 `.env.example` 生成 `.env`，并按 CPU 核数自动选择
   `SLIPSTREAM_WORKERS`（≥12 线程用 2，否则 1）；
3. 如果镜像不存在，从同目录的 `slipstream-*.tar.gz` 自动 `docker load`；
4. 执行 `docker compose up -d`；
5. 等待健康检查通过并打印访问地址。

启动后访问：`http://<服务器IP>:8000`

## 手动部署（不使用脚本）

```bash
docker load -i slipstream-0.2.0-linux-amd64.tar.gz

# 校验镜像
sha256sum -c SHA256SUMS

# 生成配置（Compose 会自动读取 .env）
cp .env.example .env

# 启动
docker compose up -d

# 查看状态 / 日志
docker compose ps
docker compose logs -f --tail=200
```

停止（保留数据）：

```bash
docker compose down
```

## 配置项（`.env`）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `COMPOSE_PROJECT_NAME` | `slipstream` | Compose 项目名，固定后移动部署目录不会丢失数据卷 |
| `SLIPSTREAM_HTTP_PORT` | `8000` | 宿主机端口 |
| `SLIPSTREAM_BIND_ADDR` | `0.0.0.0` | 绑定地址；`127.0.0.1` 仅本机 |
| `SLIPSTREAM_IMAGE` | `slipstream:0.2.0` | 使用的镜像标签 |
| `SLIPSTREAM_CONTAINER_NAME` | `slipstream` | 容器名 |
| `SLIPSTREAM_DATA_PATH` | 命名卷 `slipstream-data` | 设为宿主机绝对路径则改为 bind mount |
| `SLIPSTREAM_WORKERS` | `2` | 并发分析数；每个分析 6 个 MPI 进程 |
| `SLIPSTREAM_MAX_PROGRAM_MEMBERS` | `2000` | 单个矩阵程序的最大算例数 |
| `SLIPSTREAM_SHM_SIZE` | `1gb` | MPI 共享内存大小 |
| `SLIPSTREAM_CORS_ORIGINS` | 空 | 仅当前端由其他域名提供时需要 |
| `TZ` | `Asia/Shanghai` | 容器时区 |

### 并发与 CPU

每个分析固定使用 6 个 MPI rank。`SLIPSTREAM_WORKERS=2` 表示最多同时跑 2 个分析
（约 12 个忙线程）。8 核及以下机器建议设为 `1`；脚本已自动按核数选择。

### 数据持久化

默认使用 Docker 命名卷 `slipstream-data`，数据位于容器内 `/data`：

- `/data/runs/<run_id>/`：模型、配置、OpenFOAM 算例、日志、可视化缓存
- `/data/repairs/`：模型修复中间文件
- `/data/imports/`：导入网格中间文件

改为宿主机目录（便于备份）：

```dotenv
SLIPSTREAM_DATA_PATH=/srv/slipstream/data
```

首次使用 bind mount 时需要让容器内用户（uid/gid `10001`）可写：

```bash
sudo mkdir -p /srv/slipstream/data
sudo chown -R 10001:10001 /srv/slipstream/data
```

备份命名卷：

```bash
docker run --rm \
  -v slipstream-data:/data \
  -v "$PWD":/backup \
  slipstream:0.2.0 \
  tar -C /data -czf /backup/slipstream-data-$(date +%Y%m%d).tar.gz .
```

## 升级与回滚

```bash
# 1. 拿到新版本的 tar.gz 后加载
docker load -i slipstream-0.3.0-linux-amd64.tar.gz

# 2. 修改 .env 中的镜像标签
#    SLIPSTREAM_IMAGE=slipstream:0.3.0

# 3. 重新创建容器（数据卷保留）
docker compose up -d
```

回滚同理：改回旧标签并 `docker compose up -d`。旧镜像未被删除前可随时回滚。

## 常见问题

**1. 健康检查一直失败**

```bash
docker compose logs --tail=200
docker inspect --format '{{json .State.Health}}' slipstream
```

确认 `/api/health` 返回中 `"openfoam"` 不为 `null`：

```bash
curl http://localhost:8000/api/health
# {"ok":true,"openfoam":"/usr/bin/openfoam","data_dir":"/data/runs"}
```

**2. 端口被占用**

修改 `.env` 中 `SLIPSTREAM_HTTP_PORT`，然后 `docker compose up -d`。

**3. bind mount 报 Permission denied**

宿主机目录属主需为 `10001:10001`（见上文），或临时以 root 运行：

```yaml
# docker-compose.yml 的 service 下
user: "0:0"
```

**4. 分析很慢或 MPI 报 not enough slots**

减少并发（`SLIPSTREAM_WORKERS=1`），或给容器更多 CPU。求解器在 rank 数不足时会
自动回退到 `--oversubscribe`，但速度会下降。

**5. 内网无法访问**

检查 `SLIPSTREAM_BIND_ADDR=0.0.0.0`、宿主机防火墙是否放行端口，以及是否通过
`http://<IP>:<端口>` 访问（不要用 `localhost` 从其他机器访问）。

**6. 镜像体积较大**

基础镜像自带完整 OpenFOAM（约 2.2 GB），这是为了离线部署时无需再安装求解器。
导出后的压缩包实测约 **600 MB**（未压缩镜像约 2.8 GB）。

## 从源码重新构建 / 导出

在仓库根目录执行：

```bash
# Linux / macOS / Git Bash
./deploy/export-image.sh

# Windows PowerShell
.\deploy\export-image.ps1
```

国内网络可指定镜像源：

```bash
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
NPM_REGISTRY=https://registry.npmmirror.com \
./deploy/export-image.sh
```

```powershell
$env:PIP_INDEX_URL='https://pypi.tuna.tsinghua.edu.cn/simple'
$env:NPM_REGISTRY='https://registry.npmmirror.com'
.\deploy\export-image.ps1
```

构建其他架构（需要 buildx，且 `OPENFOAM_IMAGE` 必须提供该架构的镜像）：

```bash
SLIPSTREAM_PLATFORM=linux/arm64 SLIPSTREAM_VERSION=0.2.0 ./deploy/export-image.sh
```

> 直接 `docker build` 也可以（需先构建前端）：
> `cd frontend && npm ci && npm run build && cd ..`
> `docker build --build-arg OPENFOAM_IMAGE=opencfd/openfoam-default:2512 -t slipstream:0.2.0 .`
>
> 镜像基于已有的 OpenFOAM 基础镜像，不再拉取 Node 构建镜像；因此内网/离线环境
> 只需本机有 Node 20+（仅用于 `npm run build`），或者使用已构建好的 `frontend/dist`
> 并设置 `SLIPSTREAM_SKIP_FRONTEND_BUILD=1`。

## 技术说明

- 后端通过 `openfoam -c "<shell>"` 启动每个求解阶段；基础镜像恰好提供
  `/usr/bin/openfoam` 包装器，因此应用代码无需修改。
- 容器以非 root 用户 `openfoam`（uid/gid `10001`）运行；同时设置了
  `OMPI_ALLOW_RUN_AS_ROOT*`，便于需要时以 root 覆盖运行。
- `init: true` 由 Docker 内置 tini 回收 MPI 子进程，避免僵尸进程。
- 停止容器有 30 秒宽限期，正在运行的分析会被中断并在下次启动时标记为
  `interrupted by server restart`。
- OpenFOAM 是独立的 GPL 程序；对外分发本镜像时请遵守其许可证。
