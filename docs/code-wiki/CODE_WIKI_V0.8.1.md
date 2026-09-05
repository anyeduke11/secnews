# SecNews Hotspot — Code Wiki

> 版本: **v5.0** | 基准代码: **v0.8.1 (2026-09-05)** | 生成日期: 2026-09-05
> 目标读者: 开发者 / AI Agent / 维护者

本版对齐 v0.8.1 Day 0 开闸 + 运行时弹性层通电后的代码现状。相对 v4.0 (v0.7.4) 的重大变化:

- **七 gate 开闸** — info_filter / skill_registry / trigger_gate / agent_loop /
  playbook_engine / user_skills / skill_eval 演练通过后保持全开
- **运行时弹性层通电** — ProviderHealth 唯一判定源 + CircuitBreaker 薄状态机 +
  gateway/image 集中记账 + `/api/observability/llm/health` + reset 端点
- **优雅停机落地** — SIGTERM drain (drain_in_flight) + WAL checkpoint +
  crawl4ai/Playwright 单例关闭 + DSH 子进程防孤儿
- **deep 场景权重重排** — `quality/scenario_router.py` 已调整 (quality/scenario_router.py)
- **架构数字更新** — 73 routers / 107 services / 51 jobs / 14 collectors
  (由 `scripts/generate_meta.py` AST 反推维护)

## 文档导航

| 文档 | 内容 |
|------|------|
| [00-CODE-WIKI.md](00-CODE-WIKI.md) | 总索引与快速概览 (本文件) |
| [01-architecture.md](01-architecture.md) | 项目整体架构、分层与依赖、Feature Gates、核心数据流、存储模型 |
| [02-backend.md](02-backend.md) | 后端详解：启动生命周期、路由注册、服务层、数据层、采集器、质量管线、KL 管线、调度器、安全图谱、MCP |
| [03-frontend.md](03-frontend.md) | 前端详解：技术栈、路由表、Hooks 数据层、API 客户端、组件目录树、i18n、测试 |
| [04-subsystems.md](04-subsystems.md) | 子系统：哨兵终端 / SecNews 统一工作台 / Knowledge LLM-Wiki / CodeGarden / Security Graph / Sync / MCP / DSH / CRM / Observability |
| [05-running.md](05-running.md) | 运行方式：环境要求、安装、启动、配置、测试、CI 门禁、运维 API、开发约定 |
| [06-crawler-comparison.md](06-crawler-comparison.md) | 与 firecrawl / crawl4ai 的批判性对比 (定位/架构/采集/质量/调度/存储/LLM/生态) |

## 快速概览

### 产品定位

面向 **AI + 安全从业者** 的单人本地工作站: 一个人 · 一台电脑 · 零外部服务。
安全与 AI 是双核心领域 (安全数据源最广, 知识库中安全 + AI 内容合计约 65%),
金融 / 创业 / 招标 / 科技 / GitHub 为辅助领域。AI 安全交叉内容 (OWASP LLM Top 10、
对抗 ML、prompt injection、AI 红队) 是差异化方向。

v0.8.1 起新增看板型 AI 智能体层: Skill 商店 + Playbook YAML 双轨 (非 chatbox),
常用对话 / prompt / skill 固化为主面板可启停功能。

### 子系统矩阵 (v0.8.1)

| # | 子系统 | 说明 | 前端入口 |
|---|--------|------|----------|
| 01 | **哨兵终端 (Sentinel)** | 独立全屏首页 (唯一 `*` fallback): 态势 / 判断 / 行动 / 花园 / 图谱 / 设置 | `/` `/judge` `/judge/graph` `/action` `/garden` `/settings` |
| 02 | **SecNews 统一工作台** | 8 分类采集 · 30+ 数据源 · 12 同步质量门禁 · 6 tab 工作台 (feed/pipeline/knowledge/analyze/analytics/settings) | `/secnews` |
| 03 | **Knowledge LLM-Wiki** | 文件为真相源的知识库 (`llm-wiki-2.0/` 唯一根) · KL 5 阶段 · DeepRead/Review 双主路径 · 注意力评分 · SM-2 · FTS5 | `/knowledge` |
| 04 | **CodeGarden** | 项目生命周期 M1 + 服务网格 M2 + 资源中枢 M3 + 联动引擎 M4 (gate 已开) | `/codegarden` `/codegarden/phase2b` |
| 05 | **Security Graph** | MITRE ATT&CK · NVD CVE · 合规矩阵 (等保 2.0 / GDPR / ISO 27001) (gate 已开) | `/judge/graph` `/secnews/analytics` |
| 06 | **Observability** | API/LLM/Job/Agent/Process/Audit 全链路观测 + 阈值告警 (5 通道) + 采样 + LLM health | `/secnews/observability` |
| 07 | **CRM 业绩座舱** | 客户 / 商机状态机 / KPI (gate `crm`=true) | `/crm` |
| 08 | **v0.8 Skills** | 看板型 AI 智能体 (20 内置 skill + 自建 + 评测 + Playbook YAML 编排) | `/skill-store` `/dashboard` |

### 技术栈

```
┌────────────────────────────────────────────────────────────────┐
│ Frontend: React 18 + TypeScript + Vite 5 + Tailwind 3.4        │
│           react-router-dom v6 · ECharts · Vitest + jsdom       │
│           i18n: 0 依赖 I18nContext (zh-CN/en-US)               │
│           Port: 8898 (strictPort, 占用即报错)                   │
│           首页: 哨兵终端全屏 (SentinelShell)                     │
├────────────────────────────────────────────────────────────────┤
│ Backend:  FastAPI + Uvicorn (单进程单 worker)                   │
│           SQLite WAL (thread-local 连接, autocommit)            │
│           APScheduler (51 jobs, 进程内) · loguru 结构化日志      │
│           Observability: TraceIDContextVar + record_* 落表      │
│           Port: 8000 (CORS 白名单: 8000/8898/8899)              │
├────────────────────────────────────────────────────────────────┤
│ Storage:  SQLite (hotspot.db, 92 正向迁移 001–095)              │
│           llm-wiki-2.0/*.md 文件 (真相源) + FTS5 投影            │
│           WebDAV (坚果云) zip 容器 + Fernet 加密同步              │
│           观测表: api_events(7d) / api_metrics_hourly(30d)      │
│                   job_runs(30d) / agent_runs(30d)               │
│                   process_events(14d) / audit_log(90d)          │
│                   observability_alerts(30d)                     │
└────────────────────────────────────────────────────────────────┘
```

### 关键设计决策

- **单用户、单进程、零外部服务** — 显式不引入 Redis / PostgreSQL / Celery / Elasticsearch / Docker / Prometheus
- **SQLite WAL 模式** — 线程本地连接 + autocommit; `WORKERS=1` 避免多 worker 锁竞争
- **文件优先** — Knowledge 以 `llm-wiki-2.0/` `.md` 为唯一真相源, SQLite 是投影索引
- **Core / Extension 软分层** — `backend/config/feature_gates.toml` 单一开关源 (16 gate);
  关闭扩展只隐藏路由 / job / 前端 tab, 不删代码; core 白名单永不消失
- **哨兵终端单入口** — 旧报纸版 EditorialView 已物理删除; 独立全屏页不走 PageLayout;
  `*` fallback 与根路径均落哨兵首页
- **观测即基础设施** — TraceID contextvar 全链路 (HTTP→job→agent→LLM), `record_*` 全部
  `def` 同步 + 失败 swallow (永不阻塞业务响应)
- **LLM 双四级链** — provider: env `AI_PROVIDER` > settings.kv `llm.default_provider` > router > yaml
  default_provider; key: env > llm_secrets (provider 维度) > fail-soft
- **优雅退化** — 单源失败不阻塞整轮采集; feature_gates.toml 损坏回退"全部开启";
  DSH 子进程不可达自动降级 LLM 直连; 观测写表失败双层 swallow
- **运行时弹性** — ProviderHealth 唯一健康度真相源; CircuitBreaker 薄状态机;
  gateway/image 集中记账; `/api/observability/llm/health` + reset
- **优雅停机** — SIGTERM drain (drain_in_flight) + WAL checkpoint + crawl4ai 单例关闭 +
  DSH 子进程防孤儿 (autostart 拉起的才管)
- **同步包 ASCII 命名** — 坚果云 WebDAV quirk, 固定 `config-YYYY-MM-DD.zip`
- **前端端口固定 8898** — `--strictPort`, 禁止自动漂移

### 快速开始

```bash
# 后端 (Python 3.11+)
pip install -r backend/requirements.txt
python run.py                        # http://127.0.0.1:8000

# 前端 (Node 18+)
cd frontend && npm install && npm run dev   # http://localhost:8898 → 哨兵终端首页

# 测试
python -m pytest backend/tests/ --tb=short -q          # 3818+ passed / 0 skipped
cd frontend && npx tsc --noEmit && npx vitest run      # 425+ passed
```

完整说明 (代理配置、环境变量、CI 门禁、运维 API) 见 [05-running.md](05-running.md)。
与 firecrawl / crawl4ai 的深度对比见 [06-crawler-comparison.md](06-crawler-comparison.md)。
