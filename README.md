# TimeCut 智能监控录像系统

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://www.docker.com/)

<p align="center">
  <img src="logo.png" width="140" alt="TimeCut Logo">
</p>

一个跑在 NAS Docker 上的监控摄像头录像管理系统。接入摄像头实时流，支持**循环录像**、**按天保留**、**每日精华视频自动剪辑**，并提供浏览器 Web 管理界面。

## ✨ 功能特性

- **📺 实时画面**：通过 go2rtc 接入摄像头 RTSP/小米流，浏览器低延迟实时查看（MSE/WebRTC）
- **📹 循环录像**：FFmpeg 分段录制，按天保留策略自动清理过期录像
- **🔍 精华检测**：每日凌晨自动分析前一日录像，运动检测筛选活跃片段
- **✂️ 自动剪辑**：将活跃片段智能拼接为精华视频，永久保存
- **🌐 Web 管理**：浏览器访问面板，配置摄像头、录像策略、精华参数
- **🔄 自动恢复**：录制进程异常退出后自动重启，保证录像连续性
- **🐳 Docker 部署**：Docker Compose 一键启动，适配群晖/威联通等主流 NAS

## 🏗 系统架构

```
┌──────────┐    RTSP     ┌──────────┐    WebSocket/MSE    ┌──────────┐
│  摄像头   │ ──────────→ │ go2rtc   │ ──────────────────→ │  浏览器   │
└──────────┘             └────┬─────┘                     └──────────┘
                              │ RTSP (Docker 内网)
                         ┌────▼─────┐
                         │  app     │ (Python + FFmpeg)
                         │          │
                         │  ├─ recorder    循环录像
                         │  ├─ highlighter 精华检测+剪辑
                         │  └─ web         FastAPI + Web UI
                         └────┬─────┘
                              │
                   ┌──────────┴──────────┐
                   │  /data/recordings/   │ 循环录像（按天删除）
                   │  /data/highlights/   │ 精华视频（永久保存）
                   │  /data/db/           │ SQLite 数据库
                   └─────────────────────┘
```

## 🚀 快速开始

### Docker 部署（推荐，免编译）

> 镜像已通过 GitHub Actions 自动构建并发布到 GHCR，NAS 上**无需编译**，直接拉取运行。
> 需要 NAS 已安装 Docker 与 Docker Compose（群晖 Container Manager / 威联通 Container Station / 绿联极空间 Docker 界面）。

**1. 获取部署文件**

只需 3 个文件：`docker-compose.yml`、`go2rtc.yaml.example`、`.env.example`

```bash
git clone https://github.com/foodpm/timecut.git
cd timecut

# 复制配置模板
cp go2rtc.yaml.example go2rtc.yaml
cp .env.example .env
```

**2. 启动服务**（自动拉取预构建镜像）

```bash
docker compose up -d
```

> 首次会自动拉取 `ghcr.io/foodpm/timecut:latest` 与 go2rtc 镜像，无需本地构建。
> 如需自行编译镜像，将 `docker-compose.yml` 中 `image:` 一行注释、取消 `build:` 注释，再执行 `docker compose up -d --build`。

**3. 访问管理面板**

打开浏览器访问 `http://你的NAS地址:8090`

> 摄像头、录像策略、精华检测等配置均可在 Web 管理面板的「系统设置」中完成，**无需手动编辑配置文件**。

### 离线部署（国内 / 无外网环境）

> 国内拉取 ghcr.io 镜像经常超时，可直接从 GitHub Releases 下载镜像包，全程无需访问 ghcr.io。
> go2rtc 镜像来自 Docker Hub，一般可正常拉取；如遇拉取慢，可给 Docker 配置国内镜像加速器。

**1. 下载镜像包**

到 [Releases](https://github.com/foodpm/timecut/releases) 页面，按 NAS 的 CPU 架构下载对应文件：

| NAS 架构 | 下载文件 |
|---------|---------|
| x86_64（Intel/AMD，群晖、威联通、绿联的大部分机型） | `timecut-amd64.tar` |
| ARM（群晖/威联通等 ARM 机型） | `timecut-arm64.tar` |

> 不确定架构时，在 NAS 终端执行 `uname -m`：输出 `x86_64` 选 amd64，输出 `aarch64` 选 arm64。

**2. 上传并导入镜像**

将 tar 文件上传到 NAS，然后执行：

```bash
docker load -i timecut-amd64.tar   # 按实际下载的文件名调整
```

**3. 修改 compose 文件中的镜像版本**

按上文「步骤一」准备 `docker-compose.yml`、`go2rtc.yaml`、`.env` 后，把 `docker-compose.yml` 里的镜像改为与下载版本一致（**不带 `v` 前缀**）：

```yaml
image: ghcr.io/foodpm/timecut:0.3.1   # 替换为下载时对应的版本号，如 0.3.1
```

**4. 启动**

```bash
docker compose up -d
```

浏览器访问 `http://你的NAS地址:8090`

### 本地开发

> 需要 Python 3.12+、FFmpeg、go2rtc

```bash
# 启动 go2rtc（拉流转码）
go2rtc -config go2rtc.yaml

# 启动 Web 服务（虚拟环境）
python3 -m venv .venv && source .venv/bin/activate
pip install -r app/requirements.txt
cd app && python main.py
```

浏览器访问 `http://localhost:8090`

## ⚙️ 配置说明

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `CAMERA_RTSP_URL` | - | 摄像头 RTSP 地址 |
| `CAMERA_NAME` | 摄像头 | 摄像头显示名称 |
| `RECORDING_RETENTION_DAYS` | 7 | 录像保留天数，超期自动清理 |
| `RECORDING_SEGMENT_MINUTES` | 60 | 录像分段时长（分钟） |
| `RECORDING_INTERVAL_MINUTES` | 0 | 录制间隔（分钟，0=连续录制；如 30=每录一段后间隔 30 分钟再录） |
| `RECORDING_START_TIME` | 00:00 | 每天开始录制时间（24 小时制，支持跨午夜） |
| `RECORDING_END_TIME` | 23:59 | 每天结束录制时间（24 小时制） |
| `HIGHLIGHT_DURATION_MINUTES` | 5 | 精华视频时长（分钟） |
| `HIGHLIGHT_SCHEDULE_TIME` | 03:00 | 每日精华检测时间（24 小时制） |
| `HIGHLIGHT_ENABLED` | true | 是否启用精华检测 |
| `DETECTION_SENSITIVITY` | 30 | 运动检测灵敏度（1-100，越小越灵敏） |
| `WEB_PORT` | 8090 | Web 管理端口 |
| `DATA_DIR` | /data | 数据存储目录（Docker 内勿改） |
| `TZ` | Asia/Shanghai | 时区 |

## ❓ 常见问题

**Q：浏览器无法查看实时画面？**
- 确认 `go2rtc.yaml` 中 `api.origin: "*"` 已配置（Web UI 与 go2rtc 跨端口访问必需）
- 确认 go2rtc 端口 `1984` 与 Web 端口 `8090` 均可访问
- 按 `F12` 查看控制台错误信息

**Q：录像文件被切成几秒的碎片？**
- 碎片通常出现在录制启动初期（流不稳定）。系统会自动过滤时长 <10 秒的无效片段
- 可适当调大 `RECORDING_SEGMENT_MINUTES` 减少切割频率

**Q：go2rtc 重启后录像中断？**
- 录制进程异常退出后会自动重启（5 秒后），无需手动干预

## 📁 目录结构

```
timecut/
├── app/                      # 后端应用
│   ├── main.py               # FastAPI 入口
│   ├── config.py             # 配置管理
│   ├── database.py           # SQLite 数据模型
│   ├── recorder/             # 录像模块（FFmpeg 循环录制）
│   ├── highlighter/          # 精华检测与剪辑模块
│   └── web/                  # Web UI（FastAPI 路由 + 静态资源）
├── go2rtc.yaml.example       # go2rtc 配置模板（含摄像头流）
├── docker-compose.yml        # Docker 编排
├── Dockerfile                # 后端镜像构建
├── .env.example              # 环境变量模板
└── README.md
```

## 🛠 技术栈

- **go2rtc** — 摄像头流管理（拉流、转码、MSE/WebRTC/HLS）
- **FFmpeg** — 录像录制、视频分析、片段剪辑
- **Python / FastAPI** — 后端 API 与业务逻辑
- **SQLite** — 录像元数据存储
- **Tailwind CSS** — 前端界面
- **Docker Compose** — 容器编排

## 📄 License

[MIT](LICENSE)
