# Changelog

## v0.3.0 (2026-08-01)

### 新增功能 (Phase 8-14)

#### Phase 8: 复利基础设施
- 数据模型: 4 张新表 (content_fingerprints, ai_scores, item_entities, knowledge_links)
- 资讯收藏聚合视图: 5 数据源合并+去重+分页
- AI 评分 MCP tool: score_item

#### Phase 10: T1/T2 触发器
- 5 阶段 KL 状态机引擎 (raw→refine→link→structure→publish)
- T1 触发器: raw→refine (60s)
- T2 触发器: refine→link (120s)
- 死信队列 + 重试策略

#### Phase 11: 抓取层现代化
- BackendSession 统一代理注入
- 6 新 collector: HN, Reddit, OpenBB, Telegram, GDELT, OSS Insight
- 可读 ID 格式 {source}:{subtype}:{native_id}

#### Phase 12: T3/T4/T5 触发器 + 告警系统
- T3 触发器: link→structure (600s)
- T4 触发器: structure→publish (1800s)
- T5 回滚: publish→refine
- 3 类告警规则: tech_stack 影响, 关键 CVE (CVSS≥9.0), 标讯命中

#### Phase 13: 复利可视化 + 4 模式 + 规划引导
- KnowledgeCompoundingDashboard 仪表盘
- 4 认知模式 UI: 简报/扫描/深度/告警
- KnowledgePlanningPanel 规划引导

#### Phase 14: 子系统联动
- Tech Stack Drift 评估
- CVE 双向同步 (Knowledge ↔ Security)
- 跨域 entity 命名空间统一

#### Phase 15: AI 混合推理
- LLMService 统一接口 (OpenAI/Anthropic/本地)
- Crawl4AI 解析器集成
- Hybrid AI 降级策略 (AI → 规则 → 空)

#### Phase 16: Hybrid AI 完整
- T1 评分延迟降低 ≥60% (AI 缓存命中率 ≥30%)
- T3 摘要生成延迟降低 ≥40%
- 代理健康检查 + 自动切换

#### Phase 17: Chunks + Attention
- knowledge_chunks 表 (paragraph 级) + FTS5 全文搜索
- 5 维度注意力评分 (view/dwell/scroll/favorite/annotation)
- 30×24 注意力热力图
- 6 认知模式完整 (简报/扫描/深度/告警/整理/复习)

### 破坏性变更
- kv_cache 表删除 → digest 已读状态迁移到 digests.last_read_at
- MCP 工具从 13 减少到 9 (移除 4 个低频工具)
- 底层 REST API 端点保留不变

### 详细变更

各 Phase 详细变更日志见对应 spec 目录:
- Phase 7 (MCP): `.trae/specs/phase7-mcp-server/`
- Phase 8 (复利基础设施): `.trae/specs/phase8-compounding/`
- Phase 9 (抓取标准化): `.trae/specs/phase9-crawl-standardize/`
- Phase 10 (T1/T2 触发器): `.trae/specs/phase10-t1t2-triggers/`
- Phase 11-17 (v1.7): `.trae/specs/phase17-chunks-attention/` 及对应 spec 目录
## v0.4.0 (2026-08-16) — 审计重构 Phase 0-6 全部落地

> 依据 docs/audit_first_principles_plan.md 的第一性原理审计与批判性审计,
> 修复全部发现的断裂/死代码/安全缺口, 版本 0.3.0 → 0.4.0。

### 知识闭环数据流 (P1)
- KL 状态落真相源: md 写入 lifecycle, full_sync 不再抹除 kl:* 状态; 回填 4,117 个既有 md
- T4 触发器修复 content 列崩溃 + 评分 fallback → kl:publish 死锁解除
- 生命周期统一为 KL 五阶段 (sag/extract/compiler 改写 kl:* 值)
- knowledge_watcher 改单文件增量同步 (不再全目录重扫)
- 新增 knowledge_classify_job (每 30min 500 条规则分类)

### 采集管道 (P2)
- run_one_source 真单源化 (collect 支持 only_source 过滤)
- run_one/run_one_source 与 run_once 统一并发锁
- 去重窗口改滚动 7 天; 指纹入库后补写 (FK 失效修复)
- catchup since 窗口透传生效; unreachable 加入复检候选
- 门禁语义对齐 (hard 仅 strict 拒绝; 崩溃 fail-closed)
- 接线 6 个未注册 collector (HN/Reddit/Telegram/OSSInsight/GDELT/OpenBB)
- 稳定 ID (可读前缀+URL 哈希); upsert 不再刷新 ingested_at; 富化摘要复检

### 内化/输出闭环 (P3)
- 注意力事件自动创建 SM-2 复习记录; DeepReadMode 埋点 view/dwell/scroll
- ItemDetailDialog 标注 UI; 内容草稿生成 job (kl:publish/高注意力 → drafts)
- 复利仪表盘改读真实数据 + 挂载到 /knowledge/compound

### 同步与安全 (P4)
- bundle 构建失败即中止 (表缺失=空, 真失败=raise 防误删)
- secrets merge 排除密文字段; 冲突裁决生效; sm2 due_at 晚者胜
- rotate_master_key 主密钥轮换; Playbook 危险命令黑名单
- 备份纳入 knowledge/ 源文件 + restore 流程; MCP 路径穿越校验

### 导航与操作流 (P5)
- 死组件清理 (Sidebar/TopBar); Header "更多"菜单 (知识/Skill/密钥/同步)
- ErrorBoundary 挂载; 主题状态统一; 收藏→知识库单步导入
- 数据源健康汇总; ReviewMode 空态引导

### 兼容性
- 后端 2288+ → 2,400+ 测试全绿; 前端 292 测试全绿
- 数据库迁移无需新增 (全部修复为代码层)

### v0.4.0 收尾 (2026-08-16 补)

#### Chunk + FTS5 全文检索落地 (此前 0 行)
- `chunk_service` 段落切分生成器 (char_start/end 原文定位, 超长段落句切)
- `knowledge_chunk_generation_job` 每 30min 处理 200 条
- 迁移 061: FTS5 trigram 表 → 中文子串检索 (unicode61 不切 CJK)
- 搜索端点路由: CJK≥3字→trigram / ASCII→unicode61 / 短查询→LIKE
- 存量回填: 258 个有正文条目全部生成 chunks

#### Security ↔ Knowledge 实体统一命名空间 (PRD A.3.2)
- `security_enrichment_job` 重构为持续回填 (去掉 24h 限制 + 空结果打标)
- 富化实体写入 `item_entities` 桥接表 (此前 0 行, 全库无写入方)
- `security_entity_concept_sync_job`: item 实体→security_entities + 高频
  实体→knowledge concept 互引 (external_id/external_ref)
- 实测: 34 桥接关联 / 28 CVE 入 security 库 / 2 高频概念互引
