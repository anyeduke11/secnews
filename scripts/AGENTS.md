# scripts — Agent Context

> **就近作用域**:此文件仅承载 `scripts/` 子树进入时即时需要的约束。
> 跨项目路由、设计技能选择、根级命令见根 `AGENTS.md`。
> **本目录不属于 pytest 自动发现范围**,脚本通过 `python scripts/<name>.py`
> 直接调用,而非 `from scripts.xxx import ...`。

## 子树身份

60+ 独立运维 / 数据修复 / 审计 / 元数据生成脚本(扁平结构 + `common/` 共享)。
`scripts/generate_meta.py` 是 CI 的事实来源(FoS)— 它反推 `docs/ARCHITECTURE.md`
中的 jobs/collectors/routers/services 计数,**绝不允许手改文档数字**。

| 类别前缀 | 角色 | 互斥命名 |
|---------|------|----------|
| `audit_*.py` | 只读审计,扫真实 DB 统计覆盖率 | 严禁 `audit_*` 写入或修改 DB |
| `check_*.py` | 一次性检查(端点、链、schema、留存衰减) | 严禁修复副作用 — 只报告 |
| `cleanup_*.py` | **破坏性**,删除/归档数据 | 必须支持 `--dry-run`,默认 dry-run |
| `collect_*.py` | 一次性采集/回填任务(不属 collectors/ 生产路径) | 严禁替换 `backend/collectors/*` 日常调度 |
| `debug_*.py` | 临时诊断脚本(本地运行,不进 CI) | 跑通后必须删除或迁到 `backend/tests/` |
| `fix_*.py` | 数据修复脚本 | 同 cleanup,必须 dry-run + 备份链路 |
| `generate_*.py` | 元数据生成(目前只有 `generate_meta.py`) | 严禁改 docs 数字 — 数字必须 AST 反推 |
| `backfill_*.py` | 历史数据补齐 | 同 cleanup |
| `find_*.py` | 去重 / 重查找 | 仅打印,不写 |
| `common/` | 跨脚本共享 helpers(常量、客户端封装) | 不放独立可执行脚本 |
| `chaostest/` | 故障注入测试目录 | 子目录命名固定,禁止散落到顶层 |

## 就近 Owner / 测试入口

- **本目录无 pytest** — 脚本是 standalone 可执行,不写 `test_*.py`。
  验收方式: 跑通 + diff DB / 文件确认副作用符合预期。
- **CI 强制脚本**(`generate_meta.py --check`):
  ```bash
  python scripts/generate_meta.py --check    # 校验 docs/ARCHITECTURE.md 数字
  ```
  改了 `backend/scheduler/jobs.py`、`backend/collectors/*`、`backend/api/__init__.py`、
  `backend/services/*` 任一注册点后,只要新增/删除 `add_job`、`BaseCollector` 子类、
  `include_router`、`*_service.py` 文件,CI 会 fail,必须重跑无 `--check` 让它更新数字。
- **审计脚本入口**:
  ```bash
  python scripts/audit_quality_gates.py        # 扫 DB,统计 6 大分类质量门禁覆盖
  python scripts/audit_bid_sources.py          # 标讯源覆盖审计
  python scripts/check_endpoints.py            # 端点可达性
  python scripts/check_graph_schema.py         # 图谱 schema 漂移
  python scripts/check_retention_decay.py      # 留存衰减
  python scripts/check_backup_chain.py         # 备份链路完整性
  ```
- **数据修复脚本**(cleanup / fix / backfill):
  ```bash
  python scripts/<name>.py --dry-run    # 必须先跑,确认输出
  python scripts/<name>.py              # 真实运行
  ```
  跑前必须有 `backups/` 时间戳归档;失败回滚: 看脚本自身的 rollback 段或 restore。

## 进入此目录的硬约束

1. **不要写跨脚本 import 形成 DAG** — 脚本应当 standalone,
   只 `from scripts.common import ...` 共享常量/客户端,禁止 `script_a` import `script_b`。
2. **`generate_meta.py` 是只读数字反推工具** — 禁止修改它去"忽略"某些
   文件以绕过 CI;若需排除,在脚本顶部 `_EXCLUDED_FILES` 集合内显式登记 + 注释理由。
3. **破坏性脚本必带 `--dry-run`** — `cleanup_*.py` / `fix_*.py` / `backfill_*.py`
   必须解析 `--dry-run`(默认 True)并在 dry-run 模式下不调用任何 DELETE/UPDATE/INSERT。
4. **审计脚本不写 DB** — `audit_*.py` / `check_*.py` 必须只执行 SELECT,
   否则与 cleanup 边界模糊,违反单一职责。
5. **删除临时 `debug_*.py`** — 调试脚本跑通后必须删除或迁到 `backend/tests/`,
   长期堆在 scripts/ 会让审计扫描噪声放大。
6. **不改 docs 数字** — `docs/ARCHITECTURE.md` 中的架构计数
   (70 routers / 51 jobs / 14 collectors / 107 services)
   一律来自 `scripts/generate_meta.py`,手改会立刻被 `--check` 拦下;
   各 AGENTS.md 中 `N routers/services/jobs/collectors` 形式的数字声明
   同样纳入 `--check` 校验,漂移即 CI fail。
7. **共享 helpers 进 `common/`** — DB 连接、HTTP 客户端、Cubox/WebDAV 封装
   等重复 ≥2 个脚本用到的代码必须落 `scripts/common/`,禁止各脚本自实现副本。
8. **chaostest/ 子目录独立** — 故障注入测试不要散落顶层,放在 `chaostest/` 子目录。

## 命名约定互斥速查

| 类别 | 唯一合法形态 | 禁止形态 |
|------|-------------|----------|
| 审计 | `audit_<noun>.py` | `audit_<X>.sh`、`<X>_audit.py`(动词后置) |
| 检查 | `check_<noun>.py` | `<noun>_check.py`、单 `<noun>.py`(看不出意图) |
| 清理 | `cleanup_<noun>.py` | `clean_<noun>.py`、`purge_<noun>.py` |
| 修复 | `fix_<noun>.py` | `<noun>_fix.py`、`repair_<noun>.py` |
| 回填 | `backfill_<noun>.py` | `refill_<noun>.py`、`<noun>_backfill.py` |
| 调试(临时) | `debug_<noun>.py` | `tmp_<X>.py`、`<X>.debug.py`(调试完删除) |
| 元数据生成 | `generate_<noun>.py` | `gen_<noun>.py`、`build_<noun>.py`(语义模糊) |
| 共享 helpers | `scripts/common/<helper>.py` | 在每个脚本内重复实现 |
| 故障注入 | `scripts/chaostest/<scenario>.py` | `scripts/<X>_chaos.py` 散落顶层 |