# Tasks — Phase 15 清理 + 文档 + 迁移

## 任务列表

### Task 15.1: 创建 migration 051 (drop kv_cache + digests.last_read_at)
- [x] 创建 `backend/repository/migrations/051_v2.0_drop_kv_cache.sql`
  - `ALTER TABLE digests ADD COLUMN last_read_at TEXT`
  - 迁移 kv_cache 中 `digest_last_read_at` 值到最新 digests 记录
  - `DROP TABLE IF EXISTS kv_cache`
- [x] 修改 `backend/services/digest_service.py`
  - `has_unread_digest()`: 改用 `digests.last_read_at` 替代 kv_cache 查询
  - `mark_digest_read()`: 改用 `UPDATE digests SET last_read_at=?` 替代 kv_cache 写入
- [x] 删除 `digest_repo.py` 中 kv_cache 相关注释
- [x] 更新测试: `test_phase5_table_cleanup.py` 中 kv_cache 保留断言改为不存在断言

### Task 15.2: 从 MCP 注册表移除 4 个低频工具
- [x] 从 `backend/api/mcp_config.py` 的 `MCP_TOOL_OPERATION_IDS` 移除 4 个 operation_id
- [x] 从 `backend/api/mcp_types.py` 移除 4 个 Pydantic 模型和 4 个 MCP_TOOLS 条目
- [x] 更新 `mcp_tool_registry_seed` 中工具数量注释

### Task 15.3: 写 v2.0 迁移指南
- [x] 创建 `docs/v1_to_v2_migration.md`
  - 5 阶段 KL 状态机映射
  - 触发器启用步骤
  - 破坏性变更清单

### Task 15.4: 写 v2.0 用户文档
- [x] 创建 `docs/hotspot_v2_user_guide.md`
  - 5 触发器说明
  - 4 认知模式使用
  - 复利仪表盘操作
  - 子系统联动

### Task 15.5: 更新 CHANGELOG
- [x] 创建 `docs/CHANGELOG.md`
  - v2.0 新增功能汇总 (Phase 8-14)
  - 破坏性变更

### Task 15.6: 更新 README
- [x] 版本号 v1.8 → v2.0
- [x] MCP 工具 13 → 9
- [x] 调度器 31 → 30 jobs
- [x] 测试文件数量更新
- [ ] 路线图更新（图片资源，后续单独更新）

### Task 15.7: 运行测试验证
- [x] pytest 全部后端测试通过 (2185 passed, 4 skipped)
- [x] 前端 vitest 通过 (270 passed)
- [x] TypeScript 编译通过 (tsc --noEmit 无错误)

## 任务依赖关系
- Task 15.1 → Task 15.7 (migration 需要测试验证)
- Task 15.2 → Task 15.5/15.6 (MCP 工具数变化需反映在文档)
- Task 15.3/15.4/15.5/15.6 可并行
- Task 15.7 最后执行

## 并行化建议
- Task 15.1（migration）、Task 15.2（MCP 清理）、Task 15.3/15.4（文档）可并行
- Task 15.5/15.6（文档更新）在 Task 15.2 完成后可并行
- Task 15.7（测试）最后执行