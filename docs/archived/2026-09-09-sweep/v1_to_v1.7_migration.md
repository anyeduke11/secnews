# v1.x → v1.7 迁移指南

> **日期**: 2026-08-01
> **适用版本**: v1.7 (Phase 8-15)

## 概述

本文档指导从 v1.x 升级到 v1.7 的迁移步骤。

## 5 阶段 KL 状态机映射

v1.7 旧值 → v1.7 新值映射：

| v1.7 旧值 | v1.7 新值 | 说明 |
|-----------|-----------|------|
| `signal` | `kl:raw` | 原始信号 |
| `amplify:tagged` | `kl:refine` | 已提炼 |
| `generate` | `kl:link` | 已关联 |
| (新) | `kl:structure` | 已结构化 |
| (新) | `kl:publish` | 已发布 |

迁移脚本 `046_lifecycle_v2.sql` 自动执行旧值升级。

## 触发器启用步骤

v1.7 新增 5 个自动化触发器，默认随调度器启动：

| 触发器 | 调度频率 | 动作 |
|--------|---------|------|
| T1 (kl:raw→kl:refine) | 60s | simhash 去重 + 评分 + 标签提取 |
| T2 (kl:refine→kl:link) | 120s | concept 关联 + knowledge_links 写入 |
| T3 (kl:link→kl:structure) | 600s | 关联≥3 的 items 推进 |
| T4 (kl:structure→kl:publish) | 1800s | 评分≥8 的 items 自动发布 |
| T5 (kl:publish→kl:refine) | 手动 | 回滚已发布的 items |

## 破坏性变更清单

### kv_cache 表删除
- **变更**: `kv_cache` 表在 migration 051 中被删除
- **影响**: `digest_last_read_at` 状态迁移到 `digests.last_read_at` 列
- **操作**: 无需手动操作，迁移自动执行

### MCP 工具减少 (13→9)
- **变更**: 4 个低频工具从 MCP 注册表移除（trigger_extract_tags、trigger_cubox_sync、create_alert_rule、mark_digest_read）
- **影响**: 外部 AI Agent 无法再发现和使用这 4 个工具
- **操作**: 底层 REST API 端点保留，可直接通过 HTTP 调用