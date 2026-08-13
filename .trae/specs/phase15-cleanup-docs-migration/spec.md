# Phase 15: 清理 + 文档 + 迁移 Spec

## Why

v2.0 开发过程中积累了遗留代码（kv_cache 表、已废弃的 MCP 工具）和过时的文档（README 仍标 v1.8、MCP 工具数仍为 13）。在进入 Phase 16 Hybrid AI 开发前，需要清理技术债务并同步文档到 v2.0 状态，作为发布门禁。

## What Changes

### 15.1 删 kv_cache 表
- 创建 migration `051_v2.0_drop_kv_cache.sql`:
  - `digests` 表增加 `last_read_at` 列
  - 迁移 kv_cache 中 `digest_last_read_at` 数据到 digests 表
  - DROP TABLE `kv_cache`
- 修改 `backend/services/digest_service.py`:
  - `has_unread_digest()`: 改用 `digests.last_read_at` 替代 kv_cache 查询
  - `mark_digest_read()`: 改用 `UPDATE digests SET last_read_at=?` 替代 kv_cache 写入
- 删除 `digest_repo.py` 中 kv_cache 相关注释
- 更新测试: `test_phase5_table_cleanup.py` 中 kv_cache 保留断言改为不存在断言

### 15.2 从 MCP 注册表移除 4 个低频工具
- 从 `backend/api/mcp_config.py` 的 `MCP_TOOL_OPERATION_IDS` 移除 4 个 operation_id:
  - `trigger_extract_tags_api_extract_auto_post`
  - `trigger_cubox_sync_api_cubox_sync_post`
  - `create_rule_api_alerts_rules_post`
  - `mark_read_api_digests_read_put`
- 从 `backend/api/mcp_types.py` 移除对应的 4 个 Pydantic 模型和 `MCP_TOOLS` 条目:
  - `TriggerExtractTagsInput`, `TriggerCuboxSyncInput`, `CreateAlertRuleInput`, `MarkDigestReadInput`
  - 对应 4 个 tool 注册条目
- 更新 `mcp_tool_registry_seed` 说明: 9 个工具 (5 读 + 4 写)
- **保留底层 API 端点不变**（仅移除 MCP 暴露，REST 接口继续可用）
- 更新 README 中 MCP 工具列表（13 → 9）

### 15.3 写 v2.0 迁移指南
- 创建 `docs/v1_to_v2_migration.md`:
  - 5 阶段 KL 状态机映射（旧 `signal/generate` → `kl:raw/kl:refine/...`）
  - 触发器启用步骤（T1-T5 调度器配置）
  - 破坏性变更清单（kv_cache 删除、MCP 工具减少）

### 15.4 写 v2.0 用户文档
- 创建 `docs/hotspot_v2_user_guide.md`:
  - 5 触发器说明（T1-T5 功能、触发条件、调度频率）
  - 4 认知模式使用（简报/扫描/深度/告警）
  - 复利仪表盘操作说明
  - 子系统联动（drift 评估、CVE 同步）

### 15.5 更新 CHANGELOG
- 创建 `docs/CHANGELOG.md`:
  - v2.0 新增功能汇总（Phase 8-14）
  - 破坏性变更（kv_cache 删除、MCP 工具 13→9）

### 15.6 更新 README
- 版本号: v1.8 → v2.0
- 子系统: 5 子系统描述同步到 v2.0 实际状态
- MCP 工具: 13 → 9（5 读 + 4 写）
- 调度器: 31 → 30 jobs（v2.0 实际数量）
- 测试: 67 → 80+ pytest 文件（v2.0 实际增量）
- 路线图: 更新到 v2.0 里程碑

## Impact

- **Affected code**:
  - `backend/repository/migrations/051_v2.0_drop_kv_cache.sql` (新文件)
  - `backend/services/digest_service.py` (修改)
  - `backend/api/mcp_config.py` (修改)
  - `backend/api/mcp_types.py` (修改)
  - `backend/tests/test_phase5_table_cleanup.py` (修改)
  - `docs/v1_to_v2_migration.md` (新文件)
  - `docs/hotspot_v2_user_guide.md` (新文件)
  - `docs/CHANGELOG.md` (新文件)
  - `README.md` (修改)
- **Breaking changes**: kv_cache 表删除、MCP 工具从 13 减少到 9
- **No API contract changes**: 所有底层 REST 端点保留

## Requirements

### Migration 051 — Drop kv_cache
- `digests` 表增加 `last_read_at TEXT` 列
- 迁移 kv_cache 中 `digest_last_read_at` 值到最新 digests 记录
- `DROP TABLE IF EXISTS kv_cache`
- `digest_service.py` 改用 `digests.last_read_at` 判断已读状态

#### Scenario: Migration 051 执行成功
- **GIVEN** 数据库已有 kv_cache 表且有 `digest_last_read_at` 记录
- **WHEN** 执行 migration 051
- **THEN** kv_cache 表被删除，`digests.last_read_at` 包含迁移后的值
- **AND** `has_unread_digest()` 和 `mark_digest_read()` 正常工作

### MCP 工具清理
- 4 个低频工具从 MCP 注册表移除
- 底层 API 端点保留
- 总工具数: 13 → 9 (5 读 + 4 写)

#### Scenario: MCP 工具列表更新
- **GIVEN** 启动后的 MCP server
- **WHEN** 外部 Agent 发现工具列表
- **THEN** 只暴露 9 个工具 (5 读 + 4 写)
- **AND** `trigger_extract_tags`、`trigger_cubox_sync`、`create_alert_rule`、`mark_digest_read` 不在列表中

### 文档
- v2.0 迁移指南覆盖 5 阶段映射 + 触发器启用步骤
- v2.0 用户指南覆盖 5 触发器 + 4 模式 + 复利仪表盘
- CHANGELOG 覆盖 Phase 8-14 全部变更
- README 版本号 v2.0