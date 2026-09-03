# backend/services — Agent Context

> **就近作用域**:此文件仅承载 `backend/services/` 子树进入时即时需要的约束。
> 跨项目路由、设计技能选择、根级命令、Feature Gates 总览见根 `AGENTS.md`。
> 架构数字(`107 services`)由 `scripts/generate_meta.py` AST 反推维护,不要手改。

## 子树身份

Python 3 服务编排层(107 services,`*_service.py` + `triggers/` 子目录)。
位于 `collectors/`(采集)与 `repository/`(数据访问)之上、`api/`(路由)之下,
**严禁反向依赖**(service → api 反向 import 会触发循环导入)。

| 子目录 | 角色 | 互斥命名 |
|--------|------|----------|
| 顶层 `*_service.py` | 业务编排服务 | 严禁 `<feature>.py`(无 `_service` 后缀)、严禁 `Service_<X>.py` 类前缀 |
| `triggers/` | Phase 14 状态机触发器,`t<N>_<from>_to_<to>.py` 命名 | 严禁混编普通 service 文件、严禁 `trigger_<X>.py` |
| `ai_hub.py` | LLM 唯一入口(根 AGENTS.md 已声明权威性) | 禁止绕过 ai_hub 直接 import 各 provider SDK |
| `codegarden_*.py` | CodeGarden 扩展域,默认关闭(feature_gates.toml) | 关闭时本目录服务**不调用也不注册**,不要写硬依赖 |

## 就近 Owner / 测试入口

- **Owner 模块**: 单服务改动后必须跑:
  ```bash
  python -m pytest backend/tests/ --tb=short -q -k <service_name>    # 单服务回归
  python -m pytest backend/tests/ --tb=short -q                      # 全量回归
  ```
- **新服务模板**: 复制同领域最近的服务文件(同 repo 表、同 scheduler job)
  → 改类名/函数名 → 在 `backend/api/__init__.py` 配 router(若是 HTTP 入口)
  或在 `backend/scheduler/jobs.py` 配 job(若是定时任务)。
- **CodeGarden 服务(`codegarden_*.py`)**: 默认 feature_gate=false,
  本地调试需 `HOTSPOT_FEATURE_GATES='{"extensions":{"codegarden_phase2b":true}}'`
  或编辑 `backend/config/feature_gates.toml`,**关闭状态下不可触发测试**。
- **Trigger 脚本**: `python -m backend.services.triggers.t1_raw_to_refine`
  等命令直接运行,不入 pytest;输出到 `processing/` 后由调度器消费。

## 进入此目录的硬约束

1. **依赖方向固定**: service 可 `import backend.repository.*`、
   `import backend.collectors.*`、`import backend.core.*`,**严禁**
   `import backend.api.*`(反向会触发循环导入,违反现有 `__init__.py` 的 lazy import 协议)。
2. **新服务必须在 `__init__.py` 显式登记或被 router/job 引用** — 否则
   `scripts/generate_meta.py` AST 扫描不到,但服务本身仍是死的;CI 不会拦,
   但 review 会拦。
3. **架构数字不要手改 `docs/ARCHITECTURE.md`** — 改完服务注册后必须:
   ```bash
   python scripts/generate_meta.py            # 同步 docs/ARCHITECTURE.md
   python scripts/generate_meta.py --check    # CI 等价检查
   ```
4. **Feature Gate 服务(`codegarden_*`/`mcp_*`/`tech_stack_*`/`security_graph_*`)**:
   函数入口必须 `if not is_extension_enabled("xxx"): return` 守卫,
   否则关闭后调度器 / router 404 后仍会执行。
5. **ai_hub 唯一性**: 所有 LLM 调用必须经过 `from backend.services.ai_hub import ...`,
   禁止直接 `import openai` / `import anthropic` / `import google.generativeai`。
6. **Fernet 加密字段**(cg_resources、`sync_*` 加密列): 走
   `backend.services.sync_fernet_mixin` 提供的方法,禁止手写 `Fernet(...)`。

## 命名约定互斥速查

| 类别 | 唯一合法形态 | 禁止形态 |
|------|-------------|----------|
| 普通业务服务 | `<domain>_service.py` | `<domain>.py`、`Service_<X>.py`、`<feature>Service.py`(驼峰) |
| CodeGarden 服务 | `codegarden_<feature>_service.py` | `cg_<feature>.py`、`codegarden_<feature>.py`(无 service 后缀) |
| 触发器(仅 triggers/) | `t<N>_<from>_to_<to>.py`(N 是 1-5 数字) | `trigger_<X>.py`、`t<X>_<from>_to_<to>.py`(无数字) |
| 同步层 Fernet mixin | `sync_fernet_mixin.py` 唯一 | 复制加密逻辑到 service 内 |
| 测试文件 | `backend/tests/test_<service_name>.py` | `test_<X>.py` 散落其他目录 |