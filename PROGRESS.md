# PROGRESS.md — 执行进度台账（仅活跃段）

> **当前阶段 (2026-09-09)**: v0.8.5 已合入 main 打本地 tag；反向收敛 + D1-D4 批次落地；审查修复批 F1-F11 与全仓整洁批完成（分支 `fix/v085-review-p0` 待评审合入）。开放项: B1 信号观察窗调优 / 生产 warm 库 853 行迁移（待授权+备份前置）/ B0-B7 业务闭环整改。
> 接手顺序: 根 `AGENTS.md` → `PROJECT.md` → 本文件活跃段。历史完整段见 `docs/progress-archive/`，docs/ 全景见 `docs/README.md`。

## 历史索引

| 阶段 | 时间 | 归档文件 | 内容摘要 |
|---|---|---|---|
| **v0.5 baseline** | 2026-08-20/21 | [v0.5-baseline.md](docs/progress-archive/v0.5-baseline.md) (83 行) | 基线档案（347MB DB / 4.31M 行）+ 任务清单 |
| **v0.5 execution** | 2026-08-23/24 | [v0.5-execution.md](docs/progress-archive/v0.5-execution.md) (348 行) | M3.5 落地 + 整合 dsh 方案定稿 + 三层架构裁决 |
| **v0.6 records** | 2026-08-24/26 | [v0.6-records.md](docs/progress-archive/v0.6-records.md) (856 行) | 里程碑验收 + Phase 7 数据迁移 + P0-P3 治理全记录 |
| **v0.7 时代** | 2026-08-25 ~ 09-02 | [v0.7-records.md](docs/progress-archive/v0.7-records.md) | SettingsHub V2 + 观测批次 ①-⑨ + v0.6.3 性能/双根合并 |
| **v1.0 轨道** | 2026-09-03 ~ 09-08 | [v1.0-track-records.md](docs/progress-archive/v1.0-track-records.md) (1320 行) | T00-T19 / C01-C14 / v1.0.1 融合方案（路线已被 v0.8.5 反向收敛取代）+ REVIEW 20 项阻断 B0-B7 整改路径 |

> 原 v0.5 时代的「规格与文档 / 5 文件用法」小节随 v0.5 spec 一并归档（`docs/archived/2026-09-09-sweep/v0.5_refactor_plan/`），不再维护。

## 当前活跃段 (2026-09-03 起)

### 2026-09-09 审查修复批 F1-F11 + 全仓整洁批 (分支 `fix/v085-review-p0`, 待评审合入)

- **卡顿六因修复** (根因=采集管线稳态资源, 非 v0.8.5 前端): F4 门禁前 URL 预去重 (重复 item 不再每轮重付全量门禁) / F2 crawl4ai 连续超时指数退避 (300s×2^(n-1) 封顶 1800s) / F3 日志降噪 (实测 90s 窗口 2.2 万条) / F1 pipeline_stats 同步查询入 to_thread / F5 `HOTSPOT_DISABLE_SCHEDULER=1` dev 并行禁调度 / F6 compounding 30s TTL 缓存。
- **预存回归修复** (v1.0.1 融合带入, main 树复现): F11 unified_search 默认 sources 契约 + warm 限定名自适应 — **上条 D4 记录的 32 个 search/fts "pre-existing 基线" 已清零** (4285+32 → 4329 全绿) / F10 job 计数测试回写 55→58。
- **一致性漂移修正** (F7-F9): spec 路由算术双计 (85+11=96 → 85 总量含 v1 前缀 7 模块) + services 126→127 + ACCEPTANCE V1Prototype 措辞 + .gitignore runtime/upstreams 整目录。
- **整洁批**: docs 49 项归档 `archived/2026-09-09-sweep/` (git mv 全 100% rename) + 活跃指针修正 10 文件 + 新增 `docs/README.md` 导读; 磁盘垃圾 272MB (backend/logs / 杂散 DB / archify 截图); AGENTS.md 19.1→13.6KB; PROGRESS 本番规整 (v1.0 轨道 1315 行切出归档, 本条为新活跃头)。
- 验证: pytest 4329/0 · ruff 触碰文件 0 错 · generate_meta --check 过。
- **Mimosa 首次密封深扫贯通** (scan `scan-2026-09-09T14-26-59.592Z-434b9a445258`, seal sha256:3755…0e33, coverage=partial/inconclusive): 378 findings (HIGH 246 其中 250 条属 vendored dsh 上游)。生产路径响应批 `1797b47`+`a62acb5`+`63adec7`: ①真阳性 skill_runner wiki 写任意路径 → wiki root 包含性收口 ②假阳性源头措辞修正 (playbook ast 解释器自述/webdav 示例占位) ③dump_schema PRAGMA 拼接保持原状 (标识符来自自家 DB 自省; 两轮参数化重写被写入门误拦, 记人工验证接受风险) ④依赖通告 2 包命中但包名未随密封产物序列化, 待有 Semgrep 的复扫定位。

### 2026-09-08 v0.8.5 — 反向收敛: 三层 Sentinel 唯一壳 + v1.0 能力区块 (demo 评审通过, tag v0.8.5)

- [x] 用户裁决: v1.0.1 (C09-C13) 删三层路由换 v1 四入口的路线方向错误; **恢复 v0.8 Sentinel 为唯一壳**, v1.0 九对象/三类 receipt 降级为嵌入三层的能力区块。第一性依据: 复利的前提是日活, 日活的前提是顺手。上一条 v1.0.1 融合记录的方向正确、粒度不足, 其执行入口角色由 [v0.8.5 方案](docs/v0.8.5/V0.8.5_PLAN.md) 接续 (该文档已挂 superseded 横幅)。
- [x] 阶段一 spec: 路由表 §5 / 三层接口消费表 §6 / 实现验证分离 (五类独立 agent) / 方向固化机制 / 飞轮一等验收 (点火 D1 + 自动召回 D3)。
- [x] 阶段二 demo (分支 `feat/v0.8.5-demo` 10 commits, merge `a92effe`): 三层路由恢复 (SentinelLayout) + v1 四入口重定向透传 query + `/cases/:caseId` 深链 + `/knowledge/v1` + SignalPanel/CaseQueuePanel/ExecOverviewPanel 三区块 + CaseDetail 提取 + 守卫反转 `v085_route_shell.test.tsx` + 版本 0.8.5 + `V1SentinelShell` 物理删除。
- [x] 独立验证四门: FactCheck 9/9 · G1 codegen 0 drift · G2 端点 parity 74/74 · G3 黄金走查 13 PASS/1 DEGRADED/0 FAIL · code-review APPROVE · 视觉走查三层/深链/390 (judge 工具章程不含 web UI, 由主会话执行)。**独立验证战果: 抓到 `/api/skill-registry/v1` 被 legacy 参数路由运行时遮蔽 404 (openapi 静态门测不出, main 即坏), 已修。**
- [x] 收尾: tag `v0.8.5` (本地) + CHANGELOG 段 + 本条留痕。已知边界 (spec §9 明示 demo 不主张): 真实源信号供给 (B1) / dsh 真实出稿 (B2) — 分别是 D1/D2 的验收项; **B0-B7 前置阻断仍有效**, 排入 D1-D4 对应批次。
- [ ] **D1 (已开工, 开发项全部落地, 仅剩观察窗)**: **点火已贯通** — `v1_ingest_bridge.py` 编排 T06/T07/T05 (RSS→SourcePipeline→准入→v1_materials+v1_signals), job `v1_signal_intake_tick` 300s (默认 security:SecWiki), 实弹 10→10→0 失败 (`7c8f990`/`92042f4`)。**D1.2 立项携带证据**: migration 108 `v1_case_materials` + create_case 自动绑定 + aggregate `evidence_materials` + CaseDetail 证据区块 (`4217cd2`)。**D1.3 Subject 抽屉**: signals API +subject_id 过滤 + SignalPanel 抽屉下钻 (`4217cd2`)。仅剩: 准入规则观察窗 (job 自动积累 admission_log, 数日后调优, 无代码)。
- [ ] **D2 (已完成, `ee2228c`)**: 端口固定 (`npm run dev:demo`=8898→8000 固定对; 修 dev_environment.sh 代理 env 变量 bug); R09 artifact API 级 CAS (verify/accept/reject +expected_revision, 不符 409); CaseDetail 真实出稿按钮 (生成判断 SK-02 需证据+CVE 解析 / draft 发布 / 生成行动 SK-03 需 published 判断 §10.1, 失败如实报错); P2 修复 (aggregate 竞态守卫 + V1Prototype 死代码清理 698→330 行)。R05/R07 已在 C07 修好。
- [ ] **D3 (已完成, `d4664d9`)**: SK-05 自动召回 — `auto_recall_for_case` 已发布知识 × case 文本读时匹配 (CVE +5 / 关键词 +1 需 ≥2 分, 非 published 不参与, 候选带 reasons 诚实可解释); aggregate +recall_candidates; CaseDetail 召回区块 + 采用免手填 (case 页发起自动带 case_id)。**一等验收实弹**: 第二个同类 Case (无手动关联) 自动浮现 FastGate 处置手册, API 采用 → 回执 id=3 (total=3, adopted=3)。
- [ ] **D4 (已完成, `410c2e4`)**: 路由对账 (ROUTE_REGISTRY v0.8.5 重写); 复利卡诚实计数 (aggregate `reuse_summary`, adoption 真实回执, 不做无基线估算); **验收矩阵 `docs/v0.8.5/ACCEPTANCE.md`** (一致性门/§13/D1-D3 逐条对真实证据); legacy 对账 (dev mapping=0, 生产 853 行迁移需授权+备份前置)。后端全量回归 4285 passed (32 failed=pre-existing search/fts 基线)。
- **关联记录**: DEV-0162。方向固化: 改方向必须显式重写 `v085_route_shell.test.tsx` + 撤 spec 横幅, 不允许静默漂移。
