# SecNews Hotspot — Code Wiki

> 版本: **v4.0** | 基准代码: **v0.7.4-cleanup (Batch ⑨, 2026-09-01)** | 生成日期: 2026-09-01 | 目标读者: 开发者 / AI Agent
>
> 本版对齐 v0.7.0 → v0.7.4 全部批次后的代码现状。相对 v3.0 (v0.7.0) 的重大变化:
>
> - **首页已换** — 根路径 `/` 直接渲染**哨兵终端**全屏页 (v0.7.1 起, 报纸版 EditorialView 退役仅留重定向),
>   哨兵域页面 `/` `/judge` `/judge/graph` `/action` `/garden` 独立全屏, 不走 PageLayout; `/sentinel/settings` 已 redirect 到 `/settings?cat=sentinel` (v0.7.x SettingsHub)
> - **设置入口统一** (v0.7.x SettingsHub): 原 `/secnews/settings` `/secnews/image` `/sentinel/settings` 三处孤页
>   已合并到 `/settings?cat=pipeline|image_models|sentinel` 统一入口, 永久 redirect 保留外部书签兼容
> - **SecNews 为统一工作台** — workbench 5 视图在 v0.6.3 已并入 `/secnews`, 现为 7 子 tab:
>   feed / pipeline / knowledge / analyze / analytics / **observability (v0.7.3 新增)** / settings
> - **Observability 观测闭环落地** (Batch 1-5): api_events / api_metrics_hourly / job_runs / agent_runs /
>   process_events / audit_log / observability_alerts 7 张观测表 + 阈值规则引擎 + 告警 5 通道 +
>   SSE 推送 + 采样降级
> - **LLM 密钥链完整** (Batch ⑥⑦): provider 四级链 (env > settings.kv > router > yaml) + key 四级链
>   (env > llm_secrets > fail-soft) + secrets TTL / 强制轮换 / admin-user 分级 / OAuth 解锁
> - **扩展域开闸** (Batch ⑧): `codegarden_phase2b` / `tech_stack` / `security_graph` gate 全部
>   **开启**; `dsh` 内置化为受管子进程 + 前端一键启停
> - **i18n + a11y** (Batch ⑧⑨): 0 依赖 I18nContext (zh-CN / en-US) + LocaleToggle + a11y 系统化
>
> 架构数字 (51 jobs / 14 collectors / 68 routers / 105 services) 由
> `scripts/generate_meta.py` AST 反推维护。⚠️ 注意: 本 wiki 生成时 `generate_meta --check` 检出
> `docs/ARCHITECTURE.md` jobs 为 50 (代码实际 51, 差 `secrets_rotation_check`), 属文档滞后 1 项,
> 详见 [05-running.md](05-running.md) §4 与 §8。

## 导航

| 文档 | 内容 |
|------|------|
| [01-architecture.md](01-architecture.md) | 项目整体架构、分层与依赖、Feature Gates、核心数据流、存储模型、横切关注点 |
| [02-backend.md](02-backend.md) | 后端详解：启动生命周期、路由注册、服务层 (ai_hub / observability / secrets)、数据层、采集器、质量管线、KL 管线、调度器 51 job 全表、安全图谱、MCP |
| [03-frontend.md](03-frontend.md) | 前端详解：技术栈、路由表全量 (哨兵终端首页)、Hooks 数据层、API 客户端、组件目录树、i18n、测试 |
| [04-subsystems.md](04-subsystems.md) | 子系统：哨兵终端 / SecNews 统一工作台 / Knowledge LLM-Wiki / CodeGarden / Security Graph / Sync / MCP / DSH / CRM / Observability |
| [05-running.md](05-running.md) | 运行方式：环境要求、安装、启动、配置、测试、CI 门禁、运维 API、开发约定、首页变更与回退、已知注意事项 |
| [06-firecrawl-comparison.md](06-firecrawl-comparison.md) | 与 [firecrawl/firecrawl](https://github.com/firecrawl/firecrawl) 的对比分析 (定位/架构/采集/质量/调度/存储/LLM/生态) |

## 快速概览

### 产品定位

面向 **AI + 安全从业者** 的单人本地工作站: 一个人 · 一台电脑 · 零外部服务。
安全与 AI 是双核心领域 (安全数据源最广, 知识库中安全 + AI 内容合计约 65%),
金融 / 创业 / 招标 / 科技 / GitHub 为辅助领域。AI 安全交叉内容 (OWASP LLM Top 10、
对抗 ML、prompt injection、AI 红队) 是差异化方向。

### 子系统矩阵 (v0.7.4)

| # | 子系统 | 说明 | 前端入口 |
|---|--------|------|----------|
| 01 | **哨兵终端 (Sentinel)** | 独立全屏首页 (唯一 `*` fallback): 态势 / 判断 / 行动 / 花园 / 图谱 / 设置 | `/` `/judge` `/judge/graph` `/action` `/garden` `/sentinel/settings` |
| 02 | **SecNews 统一工作台** | 8 分类采集 · 30+ 数据源 · 12 同步质量门禁 · 7 tab 工作台 (feed/pipeline/knowledge/analyze/analytics/observability/settings) | `/secnews` |
| 03 | **Knowledge LLM-Wiki** | 文件为真相源的知识库 (`llm-wiki-2.0/` 唯一根) · KL 5 阶段 · DeepRead/Review 双主路径 · 注意力评分 · SM-2 · FTS5 | `/knowledge` |
| 04 | **CodeGarden** | 项目生命周期 M1 + 服务网格 M2 + 资源中枢 M3 + 联动引擎 M4 (gate 已开) | `/codegarden` `/codegarden/phase2b` |
| 05 | **Security Graph** | MITRE ATT&CK · NVD CVE · 合规矩阵 (等保 2.0 / GDPR / ISO 27001) (gate 已开) | `/judge/graph` `/secnews/analytics` |
| 06 | **Observability** (v0.7.3 起) | API/LLM/Job/Agent/Process/Audit 全链路观测 + 阈值告警 (5 通道) + 采样 | `/secnews/observability` |
| 07 | **CRM 业绩座舱** | 客户 / 商机状态机 / KPI (gate `crm`=true) | `/crm` |

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
│ Storage:  SQLite (hotspot.db, 85 正向迁移 001–088)              │
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
  (对比 firecrawl 的多服务微服务栈见 [06](06-firecrawl-comparison.md))
- **SQLite WAL 模式** — 线程本地连接 + autocommit; `WORKERS=1` 避免多 worker 锁竞争
- **文件优先** — Knowledge 以 `llm-wiki-2.0/` `.md` 为唯一真相源, SQLite 是投影索引
  (Watchdog 双向同步; v0.6.3 P4 已删除旧根 `knowledge/`)
- **Core / Extension 软分层** — `backend/config/feature_gates.toml` 单一开关源;
  关闭扩展只隐藏路由 / job / 前端 tab, 不删代码; core 白名单永不消失
- **哨兵终端单入口 (v0.7.1)** — 旧报纸版 EditorialView 已物理删除; 独立全屏页不走 PageLayout;
  `*` fallback 与根路径均落哨兵首页
- **观测即基础设施** — TraceID contextvar 全链路 (HTTP→job→agent→LLM), `record_*` 全部
  `def` 同步 + 失败 swallow (永不阻塞业务响应, PRD §10 红线)
- **LLM 双四级链** — provider: env `AI_PROVIDER` > settings.kv `llm.default_provider` > router > yaml
  default_provider; key: env > llm_secrets (provider 维度) > fail-soft
- **优雅退化** — 单源失败不阻塞整轮采集; feature_gates.toml 损坏回退"全部开启";
  DSH 子进程不可达自动降级 LLM 直连; 观测写表失败双层 swallow
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
python -m pytest backend/tests/ --tb=short -q          # 3234+ passed / 6 skipped
cd frontend && npx tsc --noEmit && npx vitest run      # 345+ passed
```

完整说明 (代理配置、环境变量、CI 门禁、运维 API、首页变更回退) 见 [05-running.md](05-running.md)。
与 firecrawl 的深度对比见 [06-firecrawl-comparison.md](06-firecrawl-comparison.md)。