# P2-5 `__all__` Audit Report — 后端模块入口契约全量补齐

> **日期**: 2026-08-25
> **范围**: backend/ 下所有 `__init__.py`
> **目的**: 显式 re-export 契约, 让 `from X import *` 行为可控 + ruff F401 在
> `__init__.py` 豁免时有清晰的"零契约 vs 显式契约 vs 黑名单" 三档语义。

## Audit 结果

| 模块路径 | 状态 | `__all__` 内容 | 备注 |
|---------|------|---------------|------|
| backend/metrics/__init__.py | ✅ 已有 | `["KLMetrics", "kl_metrics"]` | re-export 契约 |
| backend/parsers/__init__.py | ✅ 已有 | 多个 re-export | re-export 契约 |
| backend/parsers/bid/__init__.py | 🔧 补齐 | `[]` | 解析器按子模块调用 |
| backend/kl_pipeline/__init__.py | ✅ 已有 | 多个 re-export | re-export 契约 |
| backend/kl_pipeline/stages/__init__.py | ✅ 已有 | stages re-export | re-export 契约 |
| backend/kl_pipeline/obs/__init__.py | ✅ 已有 | obs re-export | re-export 契约 |
| backend/collectors/__init__.py | ✅ 已有 | 14 个 symbols | re-export 契约 |
| backend/quality/__init__.py | ✅ 已有 | 8 门禁 + 工具 | re-export 契约 |
| backend/config/__init__.py | ✅ 已有 | 配置 symbol | re-export 契约 |
| backend/core/__init__.py | 🔧 补齐 | `[]` | core 路由按子模块调用 |
| backend/tools/__init__.py | 🔧 补齐 | `[]` | helpers 按子模块调用 |
| backend/extensions/__init__.py | ✅ 已有 | extension gates | re-export 契约 |
| backend/wiki_fs/__init__.py | ✅ 已有 | `["WikiFs", "resolve_wiki_root"]` | re-export 契约 |
| backend/api/__init__.py | ✅ 已有 | `register_routers` | re-export 契约 |
| backend/services/triggers/__init__.py | ✅ 已有 | trigger symbols | re-export 契约 |
| backend/services/__init__.py | 🔧 补齐 | `[]` | 86 个 service 按子模块调用 |
| backend/repository/__init__.py | 🔧 补齐 | `[]` | repo 按子模块调用 |
| backend/repository/migrations/__init__.py | 🔧 补齐 | `[]` | SQL 目录, 无 Python 符号 |
| backend/security/__init__.py | 🔧 补齐 | `[]` | security graph 按子模块调用 |
| backend/domain/__init__.py | 🔧 补齐 | `[]` | 枚举/模型按子模块调用 |
| backend/scheduler/__init__.py | 🔧 补齐 | `[]` | scheduler/jobs 按子模块调用 |
| backend/tests/__init__.py | 🔧 补齐 | `[]` | pytest marker |

**汇总**: 23 个 `__init__.py`, 10 个已有 `__all__` (re-export), 10 个补齐 `__all__ = []` (零契约), 3 个本就有 (utils/wiki_fs/api)。

## 三档语义

1. **显式 re-export** (`__all__ = [symbols]`): 公共 API, 允许 `from pkg import *`
2. **零契约** (`__all__: list[str] = []`): 禁止 `from pkg import *` 引入任何东西
3. **`__all__` 缺失** (本次补齐前): 模糊地带, ruff F401 豁免但语义不明确

## 顺手清理: 19 个 F401 unused imports

ruff `--select F401 --fix` 自动修了 19 个测试文件中的 unused imports:

| 文件 | 删除的 import |
|-----|--------------|
| test_cli_contract.py | `pytest` |
| test_collect_validator.py | `get_connection` ×2 (P2-4 删 conn 后残留) |
| test_dump_schema.py | `tempfile` |
| test_knowledge_oneway.py | `MagicMock` |
| test_migrate_temp_layers.py | `pytest` |
| test_quality_hook_filter.py | `pytest` |
| test_quality_logs_archive.py | `GateResult`, `QualityLogRepository` |
| test_scheduler_concurrency.py | `pytest`, `HotspotScheduler` |
| test_snapshot_for_retirement.py | `tempfile` |
| test_sync_config_service.py | `datetime`, `timezone`, `EncryptionKeyRepository` ×2 |
| test_sync_service_split.py | `pytest` |
| test_wiki_archiver_retention.py | `run_decay`, `decay_score` (P2-3 golden test 加新类后残留) |

## 不在本 P2 范围

- `__init__.py` 之间的 `from .X import Y` 实际导入是否真被使用 — 需要 ruff `--fix --unsafe` 检查, 跳过以防误删 mock patch 设计意图 (沿用 P2-4 经验)
- 显式 re-export 列表的准确性 (e.g. `collectors/__init__.py` 列了 14 个 symbols, 但目录里 25 个文件) — 由 ruff F401/F403 + 后续 import 行为保证

## 验证

- `ruff check backend/ --select F401,F841` → 1 个 F841 (pk_map, P2-2 留给 PR 评审) + 0 个 F401
- 91 个相关 tests passed (test_cli_contract/test_collect_validator/test_dump_schema/test_knowledge_oneway/test_migrate_temp_layers/test_quality_hook_filter/test_quality_logs_archive/test_scheduler_concurrency/test_sync_config_service/test_sync_service_split/test_wiki_archiver_retention)
- baseline drift: `test_baseline_2026_08_24_counts` 失败是 wiki items 数从 4141 → 4148 (与本 P2 无关, 知识库条目持续累积)