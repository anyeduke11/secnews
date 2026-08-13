# Checklist

- [x] `bid_utils.py` 创建并导出 `is_security_bid()`，行为与原有函数一致
- [x] `bid_collector.py` 从 `bid_utils.py` 导入 `is_security_bid()`，本地定义被移除
- [x] `bid_search.py` 已删除，无 dangling import
- [x] `test_bid_search.py` 已删除
- [x] `telegram_collector.py` 和 `item_builder.py` 中 `bid_status` 的 import 未受影响
- [x] `collection_service.py` 中 module-level `bid_extractor` import 已移除
- [x] `test_bid_collector.py` 中 `is_security_bid` import 指向 `bid_utils`
- [x] `test_collectors.py` 中 `BidCollector` 引用未受影响（仍为活跃 collector）
- [x] `test_bug_fixes_published_at.py` 中 `BidCollector` 引用未受影响（仍为活跃 collector）
- [x] 编译检查通过（所有修改文件）
- [x] 全部测试通过（86 个现有测试 + 19 个 bid_collector 测试 + 21 个 collectors 测试）
- [x] 无 dangling import 引用已删除模块