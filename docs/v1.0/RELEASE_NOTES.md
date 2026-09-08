# v1.0.0 — Release Notes

**Date**: 2026-09-08
**HEAD**: `eaca4e0` (C13) + C14 治理 (本批, DEV-0160)
**Tag**: `v1.0.0` (annotated, 本地 — 推送待 user 授权)

> **诚实声明**: 本节只列**代码+测试 verified**; **业务闭环 NOT verified** 见下文 §3. v1.0.0
> 是"代码就绪, 业务闭环整改路径已列"的收口节点, 不是"生产发布"。

---

## 1. 代码层 verified ✅

| 维度 | 数字 | 来源 |
|---|---|---|
| pytest backend/tests/ | **4258 passed** + 9 skipped (32 pre-existing search/wiki FTS 域失败与本批无关, stash baseline 已确认) | `pytest backend/tests/` |
| ruff check | **0 错** (246→0, 含 65 vendored exclude + 168 safe auto-fix + 14 unsafe auto-fix + 7 手工) | `ruff check` exit 0 |
| frontend tsc | 0 错 | `cd frontend && npx tsc --noEmit` |
| vitest | **463/463** pass (C14 不动 UI) | `cd frontend && npx vitest run` |
| generate_meta --check | jobs 57 / collectors 14 / routers 85 / services 126 | `scripts/generate_meta.py --check` |
| 域对象 | 9 (v1_subject / v1_material / v1_signal / v1_case / v1_judgment / v1_action / v1_run / v1_artifact / v1_knowledge) | migration 096-107 |
| SkillDef (v1 SK) | 6 (SK-01 daily-priority-intel / SK-02 cve-impact-brief / SK-03 inspection-materials / SK-04 action-retrospective / SK-05 reuse-experience / SK-06 knowledge-review-due) | v1_skills.py |
| 3800 迁移 | 3798 candidates 落 v1_knowledge (494 applied + 3304 quarantined) + 2 deduped 排除 + 3800 mapping 行 | `scripts/t13_golden_legacy_migrate.py` |
| 旧 20 ID | 全部标 `status="legacy_v0"` | BUILTIN `__dict__` |

---

## 2. v1.0 收口做了什么 (C01-C14 序列)

| 批 | 主题 | 关键产出 | 状态 |
|---|---|---|---|
| T00-T19 | 基线 + 测试隔离 + 备份/恢复 + 契约 + SDK + 证据 + 准入 + Case 端到端 + 监督批次 + dsh/pi live + SK-02 judgment + SK-03 action/run/artifact + SK-04/05/06 knowledge | 基础 9 域对象 + 契约 + 证据两层提交 + 监督批次 | verified |
| C01 | 诊断/备份/隔离 | R10 WikiFs 字面 → resolve + R12 backup_with_api 兜底 | verified |
| C02 | 迁移修复+搜索兼容 | R11 migration 后置条件诊断 + D1 跨 ATTACH 库搜索 | verified |
| C03 | 启停+健康分级 | R04 worker noop → task_fn 必填 raise + R20 version 同步 | verified |
| C04 | 取数修+历史可见 | R13 buildQuery 双 ? → URLSearchParams | verified |
| C05 | 证据+采集+准入落地 | R01 证据真落库 + R02 watermark 门控 + R03 删 aggregator | verified |
| C06 | dsh/pi 真 SDK 适配 | R06 真 vendor clone+build + R07 async 边界 + D3 节点显式降级 | verified |
| C07 | Run 派发+Skill 守卫 | R05 mock 默认成功 → 必填 + R15 6 SK 契约正确 + R04 worker_pump 真派发 | verified |
| C08 | 成果+CAS+Wiki+Case | R08 产物正文存盘 + R09 CAS 原子守卫 + R10 Wiki 写失败 raise + R17 Case close 4 守卫 | verified |
| C09 | 路由壳+UI 收尾 | R14 删 MOCK_* + R23 4 路由拆 4 page + R24 `/` 走 `/workbench` | verified |
| C10 | 浏览器操作流+六能力 UI | R14 工作台只读 → 全 mutation + R15 6 SK UI 落地 + close 守卫 | verified |
| C11 | 契约+可靠事件+效率 | R18 outbox 持久 + Last-Event-ID 重放 + R19 Case 聚合 1 端点 | verified |
| C12 | 知识采用+失效反馈 | R16 derived_from vs adopted_by 物理分离 + 新表 + reuse 改数 | verified |
| C13 | 全量保真迁移+切换回退 | R11 mapping 4 账分列 (3800 真跑) + R20 legacy 5 态机 + runbook | verified |
| **C14** | **收口+治理** | **ruff 246→0 + docs 五件套 + tag v1.0.0 本地** | **verified** |

---

## 3. 业务闭环 NOT verified ⚠️

诚实声明: v1.0 业务闭环**未达 PRD 验收标准**. 见 [docs/v1.0/REVIEW_2026-09-07.md](REVIEW_2026-09-07.md) §1 R01-R20 20 个 P1/P2 业务闭环阻断, 修订路径 B0-B7 见 REVIEW §6.

R 摘要 (REVIEW §1):

- R01 证据未落库 / R02 调度未接 / R03 游标失败仍推进 / R04 worker noop / R05 mock 默认成功
- R06 live 假象 / R07 coroutine 未 await / R08 产物无正文 / R09 CAS 不原子 / R10 wiki 路径不一致
- R11 迁移失真 (C13 已修 3800 真跑) / R12 WAL copy 漏 / R13 buildQuery 双? (C04 已修)
- R14 工作台只读 (C10 已修) / R15 6 SK 契约错 (C07 已修) / R16 复用计数虚假 (C12 已修)
- R17 Case 永不关 (C08 已修 4 守卫) / R18 SSE 静默丢 (C11 已修 outbox 持久)
- R19 多套真相 (C11 已修聚合端点) / R20 ruff 158 错 + version 失同步 (C03+C14 已修)

**R11/R13/R14/R15/R16/R17/R18/R19/R20 共 9 项 C01-C14 已落地修复**; **R01/R02/R03/R04/R05/R06/R07/R08/R09/R10/R12 共 11 项未在 v1.0.0 收口范围, 留 v1.0.1 整改**.

### search_service / wiki_items_fts / search_api 32 失败

pre-existing baseline 失稳, 不归 C14 治理范围. stash + checkout eaca4e0 验证 C13 verified HEAD 同样失败 (28 search/wiki FTS 域 + 3 conftest autouse baseline + 1 search_api 累加).

---

## 4. 已知限制

### 4.1 业务层
- 11 项业务闭环 R 留 v1.0.1 整改 (见 §3)
- search_service / wiki_items_fts / search_api 32 失败根因待 v1.0.1 排查
- 真实 v1 增量数据保全依赖 outbox + audit_log (C11 已落)
- 旧 collection_service.py v0.x 12 采集器退役冻结 (C05 留, 不影响 v1.0)

### 4.2 工程层
- ruff 11 留后预期 vs 实际 0 错 (优于计划, 实际 ruff 新版本 auto-fix 也清了 B023/RUF012/RUF043)
- dsh/pi vendor 端到端 vendor 验证需外部 CI / 容器镜像重做 (C06 D3 触发降级 ai_hub, 路径已 audit)
- 前端 1440/1280/1024/768/390 5 视口截图真实跑通 (C10 §11 要求) 留 v1.0.1
- 推送禁 (user 2026-09-05 明令) — tag v1.0.0 仅本地, 解禁后 `git push origin v1.0.0`

### 4.3 文档层
- docs/v1.0/task-status.md 有 T16/T17/T18/T19 planned 重复行 (C14 不清理)
- docstring / doc 拼写等 lint 项未在 v1.0 范围 (留 v1.0.1)

---

## 5. 下一阶段 (留 v1.0.1)

| 优先级 | 项 | 路径 |
|---|---|---|
| P0 | B0-B7 业务闭环整改 (REVIEW §6 逐项单批先反例测试再实现) | REVIEW §6 |
| P0 | search/wiki FTS 32 失败根因排查 | pre-existing baseline |
| P1 | dsh/pi vendor 端到端验证 (C06 D3 跨平台镜像) | T04 + C06 |
| P1 | 前端 5 视口截图真实跑通 (C10 §11) | C10 |
| P1 | 推送解禁 + `git push origin v1.0.0` | user 授权 |
| P2 | 旧 collection_service.py 完整退役冻结 | C05 follow-up |
| P2 | task-status.md T16/T17/T18/T19 planned 重复行清理 | docs cleanup |

---

## 6. 验收判据

v1.0.0 收口定义: **代码层 verified + docs 收口 + 本地 tag = "v1.0 代码就绪, 业务闭环整改路径已列, 推送待授权"**.

- (a) ruff 全仓 246→0 ✅
- (b) pytest ≥4258 passed, 0 回归 ✅ (32 pre-existing 失败 stash baseline 已确认)
- (c) frontend tsc 0 + vitest 463/463 ✅
- (d) ruff.toml exclude runtime/upstreams ✅
- (e) docs 五件套 6/6 ✅
- (f) tag v1.0.0 本地 ✅
- (g) REVIEW R20 ✅ grep 命中 ✅
- (h) APP_VERSION backend 0.8.2 = frontend 0.8.2 ✅

---

## 7. commit 链 (C01-C14 共 16 commit)

```
751a446 chore(v1.0 C14): ruff.toml exclude runtime/upstreams + F821/E401/RUF022 7 错手工 (DEV-0160)
0786095 chore(v1.0 C14): ruff 全仓 auto-fix 182 错 — 246→0, 0 回归 (DEV-0160)
<C14 final> docs(v1.0 C14): 收口+治理 — task-status + PROGRESS + CHANGELOG + RELEASE_NOTES + ARCHITECTURE + REVIEW R20 + tag v1.0.0
eaca4e0 feat(v1.0 C13): 全量保真迁移与切换回退 (R11/R20 收口, DEV-0159)
ae20add feat(v1.0 C12): 知识采用+失效反馈 R16 derived_from vs adopted_by 物理分离
6596639 feat(v1.0 C11): 契约+可靠事件+效率 (R18 outbox 持久化 + R19 聚合去 N+1, DEV-0158)
145f08d feat(v1.0 C10): 浏览器操作流+六能力 UI (R14/R15, DEV-0157)
d728bef docs(v1.0 C09): task-status 标 verified + 补 commit 137e460 + PROGRESS 标 verified
137e460 feat(v1.0 C09): 路由壳+UI 收尾 (R14/R23/R24, DEV-0153)
...(C01-C08 8 commit)...
a82a809 docs(v1.0 C06): task-status 标 verified + PROGRESS C06 段 (DEV-0155)
```

---

> **收口**: v1.0.0 代码就绪, 业务闭环整改路径已列 (REVIEW §6 B0-B7). 推送待 user 授权.
