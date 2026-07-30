# SecNews Hotspot — Code Wiki

> 版本: v1.7 | 生成日期: 2026-07-23 | 目标读者: 开发者 / AI Agent

## 导航

| 文档 | 内容 |
|------|------|
| [01-architecture.md](01-architecture.md) | 项目整体架构、设计原则、技术栈、部署拓扑 |
| [02-backend.md](02-backend.md) | 后端详解：API 路由、服务层、数据层、采集器、质量管线、调度器 |
| [03-frontend.md](03-frontend.md) | 前端详解：路由、组件树、状态管理、Hook 体系 |
| [04-subsystems.md](04-subsystems.md) | 子系统：Knowledge LLM-Wiki、CodeGarden、Security Graph |

## 快速概览

### 产品定位
面向 **AI + 安全从业者** 的单人本地工作站。三大子系统：
- **SecNews**: 多域热点聚合（8 大分类，30+ 数据源）
- **Knowledge**: 文件系统 LLM-Wiki 知识库
- **CodeGarden**: 个人代码项目全生命周期管理

### 技术栈
```
┌─────────────────────────────────────────────────────┐
│  Frontend: React 18 + TypeScript + Vite + Tailwind  │
│            ECharts / Recharts / react-router-dom v6 │
│            Port: 8898 (strict)                      │
├─────────────────────────────────────────────────────┤
│  Backend:  FastAPI + Uvicorn (single worker)        │
│            SQLite WAL (thread-local connections)     │
│            APScheduler (19 scheduled jobs)           │
│            Port: 8000                                │
├─────────────────────────────────────────────────────┤
│  Storage:  SQLite (hotspot.db) + 文件系统 (knowledge/) │
│  Cache:    In-process TTLCache (LRU + TTL)           │
│  Sync:     WebDAV (坚果云) + Fernet 加密             │
└─────────────────────────────────────────────────────┘
```

### 关键设计决策
- **单用户、单进程、零外部依赖** — 无 Redis/PostgreSQL/Celery/Docker
- **SQLite WAL 模式** — 线程本地连接，autocommit 模式
- **文件优先** — Knowledge 以 .md 为 source of truth，SQLite 为读缓存
- **优雅退化** — 单个数据源失败不阻塞，外部网络故障不阻塞缓存读取
- **前端端口固定 8898** — `--strictPort`，占用即报错