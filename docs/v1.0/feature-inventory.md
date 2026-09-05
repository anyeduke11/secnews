# v1.0 旧功能清单 (T00 交付 — 逐域处置)

> 处置裁定依据 = DEVELOPMENT_PLAN §2.1 冲突裁决 + §8 旧入口迁移表; 20 Skill 逐 ID 去向 = EXECUTION_GUIDE §5。
> 处置含义: **保留**=原样继续服务 / **适配**=进入 v1.0 对应任务改造, 旧 ID/入口映射保留 / **后置**=v1.0 首发不含, 功能与数据不删除。
> 路由数对账: core 45 + 扩展域 28 = 73 (generate_meta 2026-09-05 实测)。

| 域 | 现状入口 (router 模块 / 前端) | 数据根 | 处置 | v1.0 落点 |
|---|---|---|---|---|
| 采集与源 | 14 collectors (security/ai_security/finance/bid/gdelt/github/hn/openbb/ossinsight/reddit/sogou/tech/telegram/ai) + collection_service + source_scheduler_service; `/api/sources` `refresh` `catchup` | HOT hotspots/raw_items | **适配** | T06 统一源任务 (parser 复用, 不可变 FetchRequest/租约/游标) |
| 质量门禁 | quality + quality_hook + source_quality; `/api/quality/*` | HOT + quality 规则 | **适配** | T07 基础准入与岗位精选拆开 (quarantine 保留原文) |
| 资讯筛选 | info_filter_api + InfoFilterCard (gate on) | info_filter_rules | **适配** | T07 (并入精选拆分; deny>allow 语义保留) |
| KL 知识管线 | kl_pipeline_api + kl_compounding/metrics/planning/rollback + knowledge* + wiki_tools; `/knowledge` | Wiki 单根 + FTS | **适配** | T05 提交协议 + T13; ⚠️ 生命周期命名不当作类 SAG 算法实现 |
| AI/LLM 出站 | ai_hub (gateway/service/image) + llm_status + secrets; `/api/settings/llm-provider` | settings.kv + llm.yaml + llm_secrets | **保留+适配** | T10 (增 tool 消息/usage/cancel; 弹性层 v0.8.1+v0.8.2 直接复用) |
| Agent/Skills | skill_registry(+runs) + skill_builder + skill_runner + agent_loop + agent_memory + trigger_gate(+webhook) + playbook_engine + skill_eval; `/skill-store*` `/dashboard` | trigger_tickets/skill_runs/user_skills/playbook_* | **适配/重构** | T09-T12; ⚠️ worker 消费断链 (F01) + pi 假阳性 (F05) 在此修复; agent_loop 退役为兼容 checkpoint |
| dsh 认知 | dsh_api + dsh_control_api; `/secnews/settings` 控制卡; settings KV 三态 | settings + codegarden/<project>/ 工作区 | **适配** | T04 协议验证 → T10 源码受管运行时 (旧 CLI 只作兼容诊断) |
| 观测与告警 | observability_router + alert_api + alerts + events + catchup; 阈值规则引擎 | api_events/api_metrics_hourly/observability_* | **保留** | T15 (删除 mock 指标, 真 snapshot/revision; SSE 复用 batch⑧D3) |
| 运维 | maintenance + health + proxy + mode; `/api/maintenance/*` (含 backup-verify) | HOT + backups/ | **保留** | 设置/运维入口 (T02 备份演练复用 backup_service) |
| CodeGarden | codegarden + codegarden_ops + codegarden_phase14; `/codegarden*` `/garden` | cg_* 表 + codegarden/<project>/ | **保留** | 扩展入口原功能不动 (M1/M2/M3/M4) |
| CRM | crm_customers/opportunities/stats; `/crm` | crm_* 表 | **保留** | 扩展入口 (岗位可替换模板, 不硬编码进采集/领域模型) |
| TODO | todos; `/todo` (workbench 内) | todos 表 | **适配** | T08/T16 (有上下文才关联 Case, 不批量重写) |
| 安全情报 | security + bid_alert + attention_events_api; `/bid-alert` | security 实体/STIX | **保留** | 资产/实体与 T08 subject 域衔接 |
| 同步 | sync (WebDAV+Fernet); Mon 10:30 job | sync 状态 | **保留** | 密钥继续既有加密 |
| 报告/导出 | export + reports + weekly_report + editorial; `/report` `/editorial` `/export` | export 缓存 + Wiki | **保留/适配** | 导出证据包并入 T13; 旧入口兼容 |
| 收藏/阅读/搜索 | favorites + search + history + annotations + reviews + digests; `/search` `/history` `/reviews` | favorites/阅读状态 (HOT) | **保留** | T16 按 ID 映射迁情报/知识, 用户状态不丢 |
| 认证/密钥 UI | secrets + mode; `/secrets` `/sentinel/settings`(已 redirect) | llm_secrets | **保留** | 已知 UX 遗留 (明文主密钥输入) 后置修复 |
| MCP | mcp×4 调试路由 (gate off) + server (feature_mcp=True, 19 tools) | mcp_tool_registry | **保留** | server 开关语义契约化 (v0.8.2 X-B3); v1.0 不扩面 |
| 前端旧入口 | `/secnews` `/judge` `/action` `/garden` `/deep/:type/:id` `/extract` `/quality/rejection` 等 | — | **适配** | 四入口映射: `/secnews`→`/intel`; `/judge`/`/action`→`/cases` 带筛选视图; `/knowledge` 保留; 今日工作新增。旧深链接 (query/hash/选中 ID) 回放纳入 T16 测试 |
