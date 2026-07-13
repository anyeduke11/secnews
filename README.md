# 热点地图 Hotspot Map

覆盖科技/AI、网络安全、金融/投资、独立开发/创业、综合热点五大领域的热点聚合看板，支持分类筛选与原文下钻。

## 功能特性

- **五大领域覆盖**：科技/AI、网络安全、金融/投资、独立开发/创业、综合热点
- **分类筛选**：点击分类标签快速切换
- **时间范围**：24小时 / 3天 / 7天
- **关键词搜索**：全文本搜索热点标题和摘要
- **原文下钻**：点击卡片直达原文链接
- **实时统计**：分类数据柱状图 + 热点总数
- **自动刷新**：每5分钟自动更新
- **暗色主题**：数据看板风格，视觉舒适

## 快速开始

### 环境要求

- Node.js 18+
- Python 3.10+
- 后端依赖（详见 `backend/requirements.txt`）：
  - `fastapi>=0.100` · `uvicorn[standard]>=0.23` · `aiohttp>=3.8`
  - `pydantic>=2.0` · `pydantic-settings>=2.0` · `python-dateutil>=2.8`
  - `loguru>=0.7`（结构化 JSON Lines 日志）
  - `cachetools>=5.3`（进程内 LRU 缓存）
  - `APScheduler>=3.10`（后台调度）
  - 开发依赖：`pytest>=7.4` · `pytest-asyncio>=0.21` · `pytest-cov>=4.1`

### 启动后端

```bash
# 根目录启动脚本（推荐）
python run.py

# 或等价命令
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

可通过环境变量自定义：
- `HOST`（默认 `0.0.0.0`）
- `PORT`（默认 `8000`）
- `WORKERS`（默认 `1`，SQLite WAL 模式下多 worker 会有锁竞争）

后端运行在 http://127.0.0.1:8000

### 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端运行在 http://127.0.0.1:8898

### 访问

打开浏览器访问 http://localhost:8898

### ⚠️ 代理配置（必读）

`backend/proxy_config.json` 在 `.gitignore` 中,不会随仓库分发。**首次安装后必须自行配置**,否则 `security_collector` (搜狗/sogou.com/web) 和 `github_collector` (GitHub) 会拿不到数据,出现"24h security/github 数据为空"。

**最小配置**(编辑 `backend/proxy_config.json`):

```json
{
  "mode": "manual",
  "http_proxy": "http://127.0.0.1:7897",
  "https_proxy": "http://127.0.0.1:7897",
  "socks_proxy": "http://127.0.0.1:7897",
  "no_proxy": "localhost,127.0.0.1,::1"
}
```

把 `7897` 改成你的代理端口(Clash 默认 7890、V2RayN 默认 10809、Surge 默认 6152)。如果你没装代理客户端,改为 `"mode": "off"`(此时 sogou.com/web 厂商漏洞源会被 anti-bot 限流,但 weixin.sogou.com 微信公众号源仍可用)。

也可通过前端 `/api/proxy/settings` 端点运行时修改,无需重启。

## 数据源

| 领域 | 数据源 |
|------|--------|
| 科技/AI | aihot.virxact.com |
| 网络安全 | 阿里云漏洞库(AVD) / CNNVD / 备用数据 |
| 金融/投资 | 新浪财经 / 腾讯证券 |
| 独立开发/创业 | Hacker News / Product Hunt |

## 技术栈

- **前端**：React 18 + Vite 5 + Tailwind CSS 3 + TypeScript
- **后端**：Python FastAPI + aiohttp
- **设计**：暗色数据看板风格，JetBrains Mono 等宽字体

## 目录结构

```
hotspot-map/
├── backend/           # FastAPI 后端
│   ├── main.py        # API 入口
│   └── collectors/    # 数据采集器
├── frontend/          # React 前端
│   └── src/
│       ├── components/  # 组件
│       ├── hooks/       # Hooks
│       └── types/       # 类型定义
└── README.md
```

## API 接口

- `GET /api/hotspots?category=all&time_range=7d&keyword=&limit=100` - 获取热点数据
- `GET /api/categories` - 获取分类列表
- `GET /api/health` - 健康检查
