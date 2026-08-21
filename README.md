# video-strm 任务调度

从 Navly 个人导航页中提取的 **OpenList 任务调度模块**独立项目（前后端一体），面向本地部署：
扫描 OpenList 云端目录，为视频生成 `.strm` 下载链接并下载字幕。

- **无登录**：本地直接访问，无 JWT/权限体系
- **SQLite**：数据存本地文件，无需 MySQL/Redis
- **前后端一体**：FastAPI 后端 + Vue 3 前端，官方镜像 `yyc001207/video-strm:latest` 开箱即用

## 快速部署（开箱即用）

使用已发布的 Docker 镜像 `yyc001207/video-strm:latest`，无需安装 Python / Node，只需 Docker。

### 环境要求

- 已安装 [Docker](https://www.docker.com/)（含 Docker Compose，Docker Desktop / 群晖 Container Manager 均已内置）

### 1. 准备 docker-compose.yml

创建部署目录并新建 `docker-compose.yml`：

```bash
mkdir video-strm && cd video-strm
```

内容如下（也可直接复制仓库内的 `docker-compose.example.yml`）：

```yaml
services:
  video-strm:
    image: yyc001207/video-strm:latest
    container_name: video-strm
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data                 # SQLite 数据库
      - ./openlist_logs:/app/openlist_logs  # 执行日志
      - ./output:/app/output             # STRM/字幕输出目录
    environment:
      - TZ=Asia/Shanghai
```

三个目录的作用：

| 主机目录 | 容器目录 | 说明 |
|----------|----------|------|
| `./data` | `/app/data` | SQLite 数据库（任务/服务器/预设等配置） |
| `./openlist_logs` | `/app/openlist_logs` | 每次执行的日志文件 |
| `./output` | `/app/output` | STRM/字幕输出目录，任务输出目录以 `/` 开头（如 `/emby/电视剧`）时生成到 `/app/output/emby/电视剧` |

### 2. 启动服务

```bash
docker compose up -d
```

首次启动会自动拉取镜像并创建容器，查看状态：

```bash
docker compose ps          # 状态为 Up 即正常
docker compose logs -f     # 实时查看日志
```

### 3. 验证访问

- 前端页面：http://127.0.0.1:8000（远程服务器则用 `http://<服务器IP>:8000`）
- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/health（返回 `{"code": 200, ...}`）

> 首次访问后按「[使用流程](#使用流程)」配置：添加 OpenList 服务器 → 创建任务 → 执行生成。

### 4. 升级更新

重新发布后执行以下命令即可更新到最新镜像（数据保留在 `./data` 等目录中）：

```bash
docker compose pull && docker compose up -d
```

### 常见问题

- **端口被占用**：把 `ports` 改为 `"8080:8000"`，访问地址相应变为 `http://127.0.0.1:8080`
- **生成的文件属主是 root**：容器以 root 运行，映射目录内文件属主为 uid 0，与媒体库共用目录时注意权限
- **想要直写宿主绝对路径**：任务输出目录以 `/` 开头会被统一收敛到 `/app/output` 下（安全设计）；如需输出到任意宿主路径，可把宿主媒体目录挂载到容器并调整任务输出目录

## 功能

| 模块 | 说明 |
|------|------|
| 全局配置 | 视频/字幕格式、并发度（`max_concurrent`）、生成限流（`pause_count`/`pause_time`）、处理路径前缀、输出目录前缀（选择预设时自动拼接，默认空）、SSL 校验开关、日志落库开关 |
| 服务器 | 多服务器配置（地址/Token/启停），执行时按需选择 |
| 预设 | 预设路径模板，任务创建时自动填充 |
| 任务 | 处理路径/输出目录/限流参数，复制、单删、批量删除 |
| 执行管理 | 选服务器 + 多选任务批量执行（事务性）、取消 |
| 任务历史 | 每任务最近执行 + 全部执行记录 + 日志回放/下载 |
| 实时日志 | WebSocket 实时推送，多任务切换查看 |
| 界面主题 | 浅色 / 深色 / 跟随系统一键切换（localStorage 记忆，首屏无闪烁） |

## 项目结构

```
video-strm/
├── backend/               # FastAPI 后端（SQLite）
│   ├── app/
│   │   ├── main.py            # 应用入口（仅 OpenList 路由）
│   │   ├── api/openlist.py    # 路由
│   │   ├── business/openlist/ # 业务（执行引擎/STRM 生成/日志泵/服务）
│   │   ├── core/              # settings（SQLite）/ database / models
│   │   ├── utils/             # 响应/工具
│   │   └── websocket/         # 实时日志连接管理
│   ├── tests/                 # pytest 冒烟测试
│   ├── requirements.txt
│   └── run.py
├── frontend/              # Vue 3 + Vite + Element Plus 前端
│   └── src/
│       ├── views/OpenList/    # 六页签（配置/预设/任务/执行/历史/实时日志）
│       ├── components/        # 通用组件（如主题切换）
│       ├── stores/            # Pinia（openlist 业务 / theme 主题）
│       ├── api / types / utils
│       └── styles
├── Dockerfile             # 多阶段构建：前端构建 + 后端运行（前后端一体镜像）
├── .dockerignore
├── docker-compose.example.yml  # Docker Compose 部署示例
├── .github/workflows/     # GitHub Actions：自动构建并发布 Docker Hub
├── LICENSE                # MIT 许可证
└── README.md
```

## 本地开发（快速开始）

### 环境要求

- Python >= 3.11
- Node.js >= 18 + npm / pnpm

### 1. 后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

cp .env.example .env            # 可选，默认值即可运行

python run.py                   # 启动 http://127.0.0.1:8000（DEBUG=true 开启热重载）
```

- Swagger 文档：http://127.0.0.1:8000/docs
- 首次启动自动创建 SQLite 数据库（`backend/data/video_strm.db`）与默认全局配置，无需迁移
- 配置项见 `backend/.env.example`（SQLite 路径 / 日志目录 / CORS）

### 2. 前端

```bash
cd frontend
npm install          # 或 pnpm install
npm run dev          # 开发服务器 :5173（/api 代理 → http://127.0.0.1:8000，含 WebSocket）
```

生产构建：

```bash
npm run build        # vue-tsc 类型检查 + vite build，产出 frontend/dist/
npm run preview      # 本地预览构建产物
```

构建产物可由任意静态服务器托管（后端 API 地址通过 `VITE_API_BASE_URL` 配置，默认 `/api`，需自行反代或同源部署）。
后端在检测到 `backend/frontend/dist` 存在时也会自动托管前端页面（含 SPA 回退），Docker 镜像已内置该产物，开箱即用。

## 镜像构建与自动发布

### 本地构建镜像

```bash
# 构建镜像（Dockerfile 多阶段：先构建前端，再打包后端运行时）
docker build -t video-strm .

# 运行：挂载数据、日志与输出目录以便持久化
docker run -d --name video-strm \
  -p 8000:8000 \
  -v /path/to/data:/app/data \
  -v /path/to/openlist_logs:/app/openlist_logs \
  -v /path/to/output:/app/output \
  video-strm
```

- 访问 `http://<主机>:8000` 即前端页面；API 文档 `http://<主机>:8000/docs`
- 容器内默认 `ALLOWED_ORIGINS` 为空（同源访问无需跨域）；如前端与后端分离部署，可传环境变量覆盖：`-e 'ALLOWED_ORIGINS=["http://your-frontend:5173"]'`

### GitHub Actions 自动发布 Docker Hub

仓库已内置 `.github/workflows/docker-publish.yml`：**仅当推送 `v*` 标签（如 `v1.2.3`）时**自动构建并推送镜像。

#### 触发规则与镜像标签

| 触发 | 镜像标签 |
|------|----------|
| 推送标签 `v1.2.3` | `yyc001207/video-strm:latest`、`1.2.3`、`1.2`、`sha-<短哈希>` |
| 手动 `workflow_dispatch` | 按当前 ref 生成（分支上手动触发时仅 `latest` + `sha-<短哈希>`） |

- `latest` 始终指向最近一次发布的版本，便于稳定拉取
- 默认构建 **linux/amd64 + linux/arm64** 双架构，可直接在 x86 服务器与 ARM 群晖/NAS 上运行
- 如需单架构加速构建，删去工作流中 `platforms` 一行即可

#### 配置步骤（一次性）

1. 在 [Docker Hub](https://hub.docker.com/settings/security) 创建访问令牌（Access Token）
2. 仓库 → **Settings → Secrets and variables → Actions** 添加两个 Secret：
   - `DOCKERHUB_USERNAME`：Docker Hub 用户名
   - `DOCKERHUB_TOKEN`：上面创建的访问令牌
3. 推送标签（如 `git tag v1.0.0 && git push origin v1.0.0`）触发，镜像即发布到 `Docker Hub/yyc001207/video-strm`

#### 拉取部署

```bash
docker pull yyc001207/video-strm:latest
docker run -d --name video-strm -p 8000:8000 \
  -v /path/to/data:/app/data \
  -v /path/to/openlist_logs:/app/openlist_logs \
  -v /path/to/output:/app/output \
  yyc001207/video-strm:latest
```

## 测试

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest -v             # 覆盖配置自动 seed / 服务器 CRUD / 批量删除 / 执行创建与取消
```

## 使用流程

1. **全局配置**：确认视频/字幕格式与并发度（默认并发 1，可调大）
2. **服务器配置**：添加 OpenList 服务器地址与 Token（如 `http://127.0.0.1:5244`）
3. **预设/任务**：创建预设（如 `/电视剧`），再建任务（选择预设自动填充处理路径与输出目录；需要前缀时先在「全局配置」设置处理路径前缀/输出目录前缀，默认空不拼接）
4. **执行管理**：选择服务器 → 勾选任务 → 批量执行
5. **实时日志**：自动切换展示第一个任务日志，可下拉切换；完成后前往「任务历史」查看回放与下载

> 任务输出目录为 STRM/字幕落盘目录；远程 OpenList 服务器仅提供目录列表与下载接口，STRM 为链接文件不占媒体空间。

## 许可证

本项目采用 [MIT License](LICENSE)，可自由使用、修改与分发（含商用），需保留版权声明。
