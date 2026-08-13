# Phase 4 — 旧系统下线

## Why

Phase 1-3 完成了爬虫系统的新架构建设（基础设施、标讯修复、质量门禁升级、源级调度+健康管理），
但旧系统中的已废弃代码（P3 搜索引擎路径、未解耦的 `is_security_bid` 函数、冗余的 module-level import）
仍然存在，造成维护负担和潜在的 import 循环风险。

Phase 4 的目标是清理这些已废弃/已迁移的代码，完成新旧系统的最终切割。

## What Changes

1. **移除 `bid_search.py`** — P3 搜索引擎路径已在 Phase 1.5 废弃，该文件仅被 `test_bid_search.py` 引用
2. **移除 `test_bid_search.py`** — 关联测试文件
3. **提取 `is_security_bid()` 到 `bid_utils.py`** — 从 `bid_collector.py` 拆分出独立工具模块，解耦依赖链
4. **更新 `bid_collector.py`** — 从 `bid_utils.py` 导入 `is_security_bid()`
5. **清理 `collection_service.py`** — 移除 module-level 的 `bid_extractor` import（已在 `_run_once_locked` 中局部导入）
6. **更新 `crawler_seed.py`** — `BID_SOURCES` 种子数据继续保留，但 import 路径调整为从 `bid_utils.py` 或保持现状
7. **更新测试文件** — 将 `is_security_bid` 的 import 指向 `bid_utils.py`
8. **最终验证** — 编译检查 + 全部测试通过

## Impact

- Affected specs: crawler-v2-technical-spec Phase 4
- Affected files:
  - `backend/collectors/bid_search.py` — 删除
  - `backend/collectors/bid_utils.py` — 新建
  - `backend/collectors/bid_collector.py` — 修改（import 替代本地定义）
  - `backend/services/collection_service.py` — 修改（移除 module-level import）
  - `backend/services/crawler_seed.py` — 可能修改
  - `backend/tests/test_bid_search.py` — 删除
  - `backend/tests/test_bid_collector.py` — 修改
  - `backend/tests/test_collectors.py` — 可能修改
  - `backend/tests/test_bug_fixes_published_at.py` — 可能修改

## Requirements

### Requirement: 移除 P3 搜索引擎路径
The system SHALL remove `bid_search.py` and its associated test file `test_bid_search.py`.

#### Scenario: 删除后编译检查
- **WHEN** `bid_search.py` 和 `test_bid_search.py` 被删除
- **THEN** 编译检查无报错，引用这些文件的 import 全部被清理

### Requirement: 提取 is_security_bid 工具函数
The system SHALL extract `is_security_bid()` and its helper constants (`NON_SECURITY_BLACKLIST`, `_SECURITY_RE`, `SECURITY_KEYWORD_SET`, `PROCUREMENT_KEYWORDS`, `INDUSTRY_KEYWORDS`) from `bid_collector.py` into a new module `backend/collectors/bid_utils.py`.

#### Scenario: 模块可独立导入
- **WHEN** `from backend.collectors.bid_utils import is_security_bid` 被执行
- **THEN** 返回的 `is_security_bid` 函数行为与原有函数完全一致

### Requirement: 清理 collection_service module-level import
The system SHALL remove the module-level `from backend.parsers.bid_extractor import extract_all as extract_bid_fields` from `collection_service.py`, since it's already imported locally inside `_run_once_locked()`.

#### Scenario: 编译通过
- **WHEN** module-level import 被移除
- **THEN** 编译检查通过，无 `NameError`

### Requirement: 最终验证
The system SHALL verify that:
- 编译检查通过（所有修改的文件）
- 现有测试全部通过（86 个现有测试 + 新测试）
- 无 dangling import 引用已删除的模块