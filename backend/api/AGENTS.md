# backend/api — Agent Context

> **就近作用域**:此文件仅承载 `backend/api/` 子树进入时即时需要的约束。
> 跨项目路由、设计技能选择、根级命令、Feature Gates 总览见根 `AGENTS.md`。
> 架构数字(`67 routers`)由 `scripts/generate_meta.py` AST 反推维护,不要手改。

## 子树身份

FastAPI 路由层(67 routers,`include_router` 注册入口),**唯一对外 HTTP 入口**。
位于 `services/` 之上、`main.py` 之下,通过 `register_routers(app)` 一次性挂载。
所有 `__init__.py` 内的 import 必须 lazy,否则会触发循环。

| 子目录 | 角色 | 互斥命名 |
|--------|------|----------|
| `<feature>.py` | 主路由文件,`APIRouter` + 路由清单注释 | 单文件 ≤150 行(超出即拆分);严禁 `router_<X>.py` |
| `<phase>_<feature>_api.py` | 跨阶段复合 API(如 `kl_compounding_api.py`、`knowledge_chunks_api.py`) | 严禁与 `<feature>.py` 同名共存(防重叠断言见根 AGENTS.md) |
| `middleware.py` | FastAPI 中间件 | 不允许混编业务路由 |
| `mcp_*.py` | MCP 扩展域路由,默认关闭(`feature_gates.toml`) | 关闭时本目录服务**不注册**;不要硬依赖 |
| `codegarden*.py` | CodeGarden 路由,默认关闭 | 同上 |
| `maintenance.py` / `settings.py` / `cache.py` / `health.py` | 基础设施路由 | 关闭任何一项会破坏运维面板,**禁止纳入 feature gate** |

## 就近 Owner / 测试入口

- **Owner 模块**: 新增/修改路由后必须跑:
  ```bash
  python -m pytest backend/tests/ --tb=short -q -k "test_<feature>_api"    # 单路由回归
  python -m pytest backend/tests/ --tb=short -q                             # 全量回归
   python scripts/generate_meta.py --check                                    # CI 校验 67 routers 计数
  ```
- **本地起服务**: 根 AGENTS.md 已列 `python run.py` / `uvicorn backend.main:app`。
  修改后访问 `http://127.0.0.1:8000/docs` 看 Swagger 是否列出新路由。
- **Feature Gate 路由调试**(`codegarden*` / `mcp_*` / `tech_stack*` / `security_graph*`):
  默认关闭,本机需 `HOTSPOT_FEATURE_GATES='{"extensions":{"<name>":true}}'`
  或编辑 `backend/config/feature_gates.toml`。**关闭时 Swagger 应 404**;
  若仍 200 即 `register_routers` 未守住门禁,立即修复。

## 进入此目录的硬约束

1. **路由文件 ≤150 行** — 超出必须在同目录拆分 `<feature>_v2.py` / `<feature>_<sub>.py`,
   或拆为 service + router 组合,不要塞 Pydantic model 与 handler 于一文件。
2. **顶部必写路由清单注释** — 文件头注释列出全部 `@router.*` 路径,
   格式参考 `backend/api/annotations.py`(便于 swagger 自动生成与人肉 review)。
3. **依赖方向固定**: router 可 `import backend.services.*`、
   `import backend.core.*`,**严禁** `import backend.collectors.*`、
   `import backend.repository.*`(DB 操作必须经 service)。
4. **Lazy import 协议**: `__init__.py` 必须用 `import backend.api.xxx as xxx_api`
   或 `from backend.api import (...)` 在 `register_routers` 函数体内,
   不能在模块顶部 import(否则 `from __future__ import annotations` 会
   把 `annotations` 绑定成 `_Feature`,而不是子模块 — 历史踩坑)。
5. **Feature Gate 路由注册**: 必须在 `register_routers` 内 `if is_extension_enabled("xxx"):`
   守卫后才 `app.include_router(xxx.router)`;否则关闭后仍 200,违反设计意图。
6. **Pydantic model 就近**: 路由专属的 `BaseModel` 必须定义在该路由文件顶部,
   不要放 `backend/types/` 全局目录(已废用)。
7. **`core/` 43 个 core router 白名单**: 任何新 router 不允许与
   `backend/core/routers.py` 内已声明路径前缀重叠,否则启动时断言失败。

## 命名约定互斥速查

| 类别 | 唯一合法形态 | 禁止形态 |
|------|-------------|----------|
| 普通业务路由 | `<feature>.py`(`APIRouter` 在文件内) | `router_<X>.py`、`<feature>_router.py`(后缀重复) |
| 跨阶段复合 API | `<phase>_<feature>_api.py` | `<feature>_api.py`(无 phase 限定)、`<phase>_<feature>.py`(无 `_api` 后缀) |
| 中间件 | `middleware.py` 唯一 | 散落多个 `*_middleware.py` |
| 测试文件 | `backend/tests/test_<feature>_api.py` | `tests/api/<feature>.py`(路径错误) |

> **历史豁免名单 (v0.7.0 审计登记)**: 以下存量文件不符合 `<phase>_<feature>_api.py`
> 规范但已稳定运行、改名会牵动 import/测试/generate_meta 链路, 暂不改名 —
> 新增文件仍必须按上表规范: `secnews_dashboard_api.py`、`agents_api.py`、
> `dsh_api.py`、`dsh_control_api.py`、`crm_customers_api.py`、`crm_stats_api.py`、
> `crm_opportunities_api.py`、`alert_api.py`。若后续重构触碰其中文件, 顺带迁移到规范名。