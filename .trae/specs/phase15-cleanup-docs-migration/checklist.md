# Checklist — Phase 15 清理 + 文档 + 迁移

## Migration 051
- [x] `digests.last_read_at` 列添加成功
- [x] kv_cache 中 `digest_last_read_at` 数据迁移到 digests 表
- [x] `kv_cache` 表 DROP 成功
- [x] `digest_service.py` 改用 digests.last_read_at 判断已读状态

## MCP 工具清理
- [x] `MCP_TOOL_OPERATION_IDS` 中 4 个 operation_id 已移除
- [x] `mcp_types.py` 中 4 个 Pydantic 模型和 MCP_TOOLS 条目已移除
- [x] MCP 工具总数变为 9 (5 读 + 4 写)
- [x] 底层 API 端点保留不变

## 文档
- [x] `docs/v1_to_v2_migration.md` 创建完成
- [x] `docs/hotspot_v2_user_guide.md` 创建完成
- [x] `docs/CHANGELOG.md` 创建完成
- [x] README 版本号更新为 v2.0
- [x] README MCP 工具数更新为 9
- [x] README 子系统描述同步到 v2.0

## 测试
- [x] `test_phase5_table_cleanup.py` 更新 kv_cache 断言
- [x] pytest 全部后端测试通过 (2185 passed, 4 skipped)
- [x] 前端 vitest 通过 (270 passed)
- [x] TypeScript 编译通过 (tsc --noEmit 无错误)