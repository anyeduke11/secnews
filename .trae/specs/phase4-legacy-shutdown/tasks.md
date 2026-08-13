# Tasks

- [x] Task 1: 提取 `is_security_bid()` 到 `bid_utils.py`
  - 新建 `backend/collectors/bid_utils.py`
  - 从 `bid_collector.py` 复制：`NON_SECURITY_BLACKLIST`、`SECURITY_KEYWORD_SET`、`_SECURITY_RE`、`_PROCUREMENT_RE_LIST`、`_INDUSTRY_RE_LIST`、`is_security_bid()` 函数
  - 导出 `__all__ = ["is_security_bid"]`
  - 更新 `bid_collector.py`：删除本地定义，改为 `from backend.collectors.bid_utils import is_security_bid`，保留 `SECURITY_KEYWORD_SET`、`SECURITY_KEYWORDS`、`PROCUREMENT_KEYWORDS`、`INDUSTRY_KEYWORDS` 的导出（`__all__`）

- [x] Task 2: 删除 `bid_search.py` 和 `test_bid_search.py`
  - 删除 `backend/collectors/bid_search.py`
  - 删除 `backend/tests/test_bid_search.py`
  - 检查 `telegram_collector.py` 和 `item_builder.py` 中 `bid_status` 的 import（仅引用 `bid_status.py`，非 `bid_search.py`）

- [x] Task 3: 清理 `collection_service.py` module-level import
  - 移除 `from backend.parsers.bid_extractor import extract_all as extract_bid_fields`
  - 该函数已在 `_run_once_locked()` 方法内局部导入，module-level 是冗余的

- [x] Task 4: 更新测试文件
  - `test_bid_collector.py`：将 `is_security_bid` 的 import 从 `bid_collector` 改为 `bid_utils`
  - `test_collectors.py`：移除对 `BidCollector` 的引用（如 `test_bid_collector_returns_hotspot_items` 等）
  - `test_bug_fixes_published_at.py`：移除 `BidCollector` 的 import

- [x] Task 5: 最终验证
  - 编译检查所有修改文件
  - 运行全部测试（86 个现有测试 + 新测试）
  - 确认无 dangling import

# Task Dependencies
- Task 2 依赖 Task 1（bid_search.py 依赖 bid_collector.is_security_bid，需先提取 bid_utils）
- Task 4 依赖 Task 1（测试文件需从 bid_utils 导入 is_security_bid）
- Task 5 依赖 Task 1-4（最终验证需所有修改完成）