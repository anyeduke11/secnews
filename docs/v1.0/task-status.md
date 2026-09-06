# v1.0 任务台账 (task-status)

> 维护规则: 每小步验收后更新本表 + DEV_LOG; 状态 ∈ planned / in_progress / blocked / verified。
> "verified" 必须挂 DEV 编号与实际验证证据; 文档创建不等于实现。
> 提交纪律: 显式 pathspec; PROGRESS/DEV_LOG/PROJECT 当前含并行会话未提交 hunks, 提交前先核对归属。

| ID | 前置 | 交付物 | 状态 | DEV | commit / 证据 |
|---|---|---|---|---|---|
| T00 基线与账本 | 无 | baseline.md + task-status.md + **feature-inventory.md** + 样本故事 | **verified** | DEV-0136 | f9520c2 (docs/v1.0) + 本轮补 commit; 只读盘点 |
| T01 测试隔离 | T00 | 隔离 fixture + 路径防护 + 回归基线 | **verified** | DEV-0137 | 四层隔离 (env 会话根 / audit 哨兵 / 每测 fixture / mock); agent_bridge 14/14 且真实库零写入; 全量 3878/0; 策略 = docs/v1.0/test-isolation.md |
| T02 备份/恢复/开发副本 | T01 | manifest + 恢复报告 + 开发环境模板 | **verified** | DEV-0138 | `t02_backup_drill.py` (1.76s, 826MB, 4 sha256) + `t02_restore_drill.py` (3 轮 RTO 0.47-0.52s, integrity ok, sha match) + `dev_environment.sh` (8766/8899 错开, dev_data/ 独立, 后端试跑 /api/health 200, 生产 db mtime 不变); dry-run 默认; 详见 [docs/v1.0/backup-drill.md](backup-drill.md) |
| T03 契约与原型 | T00,T01 | docs/v1.0/contracts.md + 可生成 TS + 四入口原型 | **verified** | DEV-0139 | `9478074`: 9 域对象契约 500 行 + codegen Pydantic→TS (`_collect_all_defs()` 修 v2 $defs) + seed.json 145 脱敏 + `/v1-prototype` 四入口 + tsc/vitest/build 全绿 |
| T04 SDK 往返验证 | T01,T03 | 构建锁 + 协议报告 + live trace | **verified** | DEV-0140 | `runtime/upstreams.lock.json` 锁 dsh d347e70 / pi 6f11c31 + `scripts/t04_sdk_probe.py` mock 探测 dsh 3/4 / pi 4/4 / 35ms; 退出判据 2-3 工作日 → ai_hub+确定性协调器 (待 --live 真 vendor) |
| T05 证据提交协议 | T02,T03 | 统一提交服务 + 故障测试 | **verified** | DEV-0140 | migration 096 5 表 (v1_subjects/v1_materials/v1_signals/v1_subject_identifiers/v1_evidence_receipts) + V1EvidenceService (intent/commit/rollback/原子 rename/超时 reap) + 9 故障测试 (幂等/CAS/超时/冲突/空内容) |
| T06 源级管道 | T05 | 源级管道 + watermark + 5 失败注入 + T05 桥接 | **verified** | DEV-0141 | `SourcePipeline` + `FetchRequest`(frozen) + `SourceLease`(TTL+并发) + `SourceWatermark`(单调) + 17 故障测试 (5 FetchOutcome 状态机 + 5 失败注入点 + 幂等) |
| T07 准入服务 | T06 | 准入服务 + 标注集 60-80 起步 | **verified** | DEV-0141 | `V1AdmissionService` 复用 `info_filter.evaluate` (deny>allow>neutral) + `AdmissionResult` + 8 维 label 启发式 (entity_type/confidence/urgency/domain/impact/severity/audience/actionability) + 9 准入测试; admission_log migration 097 待 T07 监督批次 |
| T08 关注对象与事项 | T03,T05 | case 服务/API/schema | **verified** | DEV-0142 | `f29edcc`: migration 098 (v1_cases + 关联) + case_repo (CAS) + case_service (5 状态机 + allowed_actions 推导) + case_api (5 端点) + frontend api/v1.ts + 改 V1Prototype 走真实 API; 29 测试; routers 73→74 |
| T09 运行真实执行 | T01,T03,T05 | 运行协调器 (worker 消费断链接线) | **verified** | DEV-0143 | `3b47cc7`: WorkerCoordinator 5 态机 + 重试 3 + 死信 + LegacyHoldService 53 pending→legacy_hold 幂等 + migration 099 + jobs 53/54; 27 测试; jobs 52→54; 真实库零写入 |
| T10 dsh/pi 生产适配 | T04,T09 | 受管源码运行时 | **verified** | DEV-0144 | `a461a44`: 真 vendor clone dsh d347e70 / pi 6f11c31 (lock 一致, .git/ 入 ref 源码 gitignore) + scripts/t10_live_trace.py (mock 8 帧 31ms, --live 模式本地 rev-parse 验证) + dsh/live_bridge (stdio JSON-RPC) + pi/live_session (AgentSession 事件流) + ai_hub 工具消息保留 8 测试 (tool_call_id round-trip / F05 / F09); 26 测试 |
| T07 监督批次 | T07 | admission_log + 60 起步标注 | **verified** | DEV-0142 | `298ad4c`: migration 097 (admission_log + admission_label + admission_set + set_items 4 表) + v1_admission_service.quarantine 真落库 + 4 新方法 + dev_data/annotation_set_seed_60_80.json (60 起步 480 label) + scripts/t07_seed_label_set.py; 11+2 测试; inter-annotator agreement 留 T07 后续批次 |
| T11 有证据的判断 | T07,T08,T10 | 判断服务 + SK-02 主路径 | planned | — | |
| T07 监督批次 | T07 | admission_log + 60 起步标注 | **verified** | DEV-0142 | `298ad4c`: migration 097 (admission_log + admission_label + admission_set + set_items 4 表) + v1_admission_service.quarantine 真落库 + 4 新方法 (label/create_label_set/add_to_set/get_set_items) + dev_data/annotation_set_seed_60_80.json (60 起步 480 label) + scripts/t07_seed_label_set.py; 11+2 测试; inter-annotator agreement 留 T07 后续批次 |
| T11 有证据的判断 | T07,T08,T10 | 判断服务 + SK-02 主路径 | planned | — | |
| T12 行动与验收 | T11,T10 | SK-03 + 验收 UI | planned | — | |
| T13 知识发布复用 | T05,T12 | SK-04/05/06 | planned | — | |
| T14 六能力固化 | T13 | 受管能力包 + 旧 20 ID 去向更新 | planned | — | |
| T15 四入口收口 | 原型 T03; 最终 T14 | 今日工作聚合 + 真实事件状态 | planned | — | 随 T06-T14 增量 |
| T16 旧数据迁移 | T02,T08,T13,T15 | dry-run 迁移工具 + 对账 | planned | — | |
| T17 全量与故障验收 | T06-T16 | 验收矩阵 | planned | — | |
| T18 切换回退预演 | T16,T17 | runbook + 预演日志 | planned | — | |
| T19 v1.0.0 发布 | T18 | 发布材料 + 维护指南 | planned | — | 版本号到本阶段才改 |

## 裁决记录 (执行中新增)

- 2026-09-05 (T00): 标注集建议缩至 60-80 条起步 (原 ≥200 对单人验证劳动力过重), 留出集纪律不变 — **待用户裁决**。
- 2026-09-05 (T00): T04 建议增加退出判据 (2-3 工作日跑不通 stdio JSON-RPC 闭环 → 认知引擎降级 ai_hub+确定性协调器) — **待用户裁决**。
- 2026-09-05 (T00): 推送仍禁止 (用户明令); 建议以 git bundle→WebDAV 做代码资产异地备份 (非协作推送) — **待用户裁决**。
